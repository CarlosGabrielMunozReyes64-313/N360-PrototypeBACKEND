import asyncpg
from fastapi import APIRouter, Depends, Request, status
from starlette.concurrency import run_in_threadpool

from ..db import SQL_FOTO_ACTUALIZADA_EN, fijar_usuario_actual, get_conn
from ..errors import ApiError, desde_postgres
from ..imagenes import MAX_BYTES_ENTRADA, ImagenInvalida, procesar_foto_perfil
from ..schemas import (
    ActualizarPerfilIn, CambiarPasswordIn, LoginIn, MeOut, RegistroIn, SesionOut, UsuarioOut,
)
from ..security import obtener_ip, obtener_user_agent, requerir_token

router = APIRouter(prefix="/auth", tags=["auth"])


async def _usuario_actual(conn: asyncpg.Connection, usuario_id) -> UsuarioOut:
    """Lee la fila de `usuario` para usuario_id. Debe llamarse DESPUÉS de
    fijar_usuario_actual() dentro de la misma transacción: la política
    usuario_select_pol solo deja ver la propia fila (o todas, si admin)."""
    fila = await conn.fetchrow(
        f"""
        SELECT usuario_id, email, nombre, rol, activo,
               email_verificado_en, ultimo_login_en,
               {SQL_FOTO_ACTUALIZADA_EN}
          FROM nexus360.usuario
         WHERE usuario_id = $1
        """,
        usuario_id,
    )
    if fila is None:
        # No debería pasar: el usuario_id vino de una sesión/registro válidos.
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "Usuario no encontrado.")
    return UsuarioOut(**dict(fila))


@router.post("/register", response_model=SesionOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegistroIn,
    request: Request,
    conn: asyncpg.Connection = Depends(get_conn),
):
    # 1) Alta vía registrar_usuario() — hashea con pgcrypto, valida
    #    formato de correo y longitud de password, y garantiza rol='empresa'.
    try:
        async with conn.transaction():
            await conn.fetchval(
                "SELECT nexus360.registrar_usuario($1, $2, $3)",
                payload.email, payload.password, payload.nombre,
            )
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc

    # 2) Inicia sesión de una vez con las mismas credenciales, para que el
    #    front reciba token + usuario en la misma respuesta de registro
    #    (así lo espera src/auth/api.ts::registrar en el frontend).
    return await _iniciar_sesion_y_responder(conn, payload.email, payload.password, request)


@router.post("/login", response_model=SesionOut)
async def login(
    payload: LoginIn,
    request: Request,
    conn: asyncpg.Connection = Depends(get_conn),
):
    return await _iniciar_sesion_y_responder(conn, payload.email, payload.password, request)


async def _iniciar_sesion_y_responder(
    conn: asyncpg.Connection, email: str, password: str, request: Request
) -> SesionOut:
    ip = obtener_ip(request)
    user_agent = obtener_user_agent(request)

    # OJO: esta llamada va SOLA, sin envolver en `async with conn.transaction()`.
    # iniciar_sesion() internamente hace su propio UPDATE de intentos_fallidos
    # (y su propio INSERT en sesion si hay éxito) como un único statement
    # atómico de Postgres. Si esto se envolviera en una transacción explícita
    # y más abajo lanzáramos un ApiError con credenciales inválidas, esa
    # excepción haría ROLLBACK de la transacción completa — deshaciendo el
    # UPDATE del contador de intentos fallidos y dejando el bloqueo de cuenta
    # completamente inoperante. Por eso el statement se ejecuta y confirma
    # por sí solo antes de decidir si lanzamos un error HTTP.
    fila = await conn.fetchrow(
        "SELECT * FROM nexus360.iniciar_sesion($1, $2, $3, $4)",
        email, password, ip, user_agent,
    )

    # iniciar_sesion() NUNCA lanza excepción por credenciales: devuelve
    # una fila con `error` poblado (ver comentario extenso en el SQL
    # sobre por qué — evita que un RAISE deshaga el contador de
    # intentos fallidos que se acaba de actualizar).
    if fila["error"] == "credenciales_invalidas":
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            "CREDENCIALES_INVALIDAS",
            "El correo o la contraseña no son correctos.",
        )
    if fila["error"] == "cuenta_bloqueada":
        raise ApiError(
            status.HTTP_423_LOCKED,
            "CUENTA_BLOQUEADA",
            "La cuenta está bloqueada temporalmente por intentos fallidos. Intenta de nuevo en unos minutos.",
        )
    if fila["error"] is not None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "No se pudo iniciar sesión.")

    usuario_id = fila["usuario_id"]
    token = fila["token"]
    expira_en = fila["expira_en"]

    # Login ya confirmado con éxito: ahora sí, en una transacción aparte,
    # fijamos el contexto RLS para poder leer la propia fila de `usuario`.
    async with conn.transaction():
        await fijar_usuario_actual(conn, usuario_id)
        usuario = await _usuario_actual(conn, usuario_id)

    return SesionOut(token=token, expira_en=expira_en, usuario=usuario)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    # cerrar_sesion() es idempotente (WHERE revocado_en IS NULL); un token
    # ya inválido o inexistente simplemente no actualiza ninguna fila.
    await conn.execute("SELECT nexus360.cerrar_sesion($1)", token)
    return None


@router.get("/me", response_model=MeOut)
async def me(
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    async with conn.transaction():
        usuario_id = await conn.fetchval("SELECT nexus360.validar_sesion($1)", token)
        if usuario_id is None:
            raise ApiError(
                status.HTTP_401_UNAUTHORIZED,
                "CREDENCIALES_INVALIDAS",
                "La sesión no es válida o expiró.",
            )
        await fijar_usuario_actual(conn, usuario_id)
        usuario = await _usuario_actual(conn, usuario_id)

    return MeOut(usuario=usuario)


@router.patch("/me", response_model=MeOut)
async def actualizar_perfil(
    payload: ActualizarPerfilIn,
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Cambia nombre y/o correo. La contraseña NUNCA pasa por aquí (ver
    /auth/change-password) — password_hash está deliberadamente fuera del
    GRANT UPDATE de esta tabla, por diseño del schema."""
    if payload.nombre is None and payload.email is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDACION", "Nada que actualizar.")

    async with conn.transaction():
        usuario_id = await conn.fetchval("SELECT nexus360.validar_sesion($1)", token)
        if usuario_id is None:
            raise ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "La sesión no es válida o expiró.")
        await fijar_usuario_actual(conn, usuario_id)

        try:
            await conn.execute(
                """
                UPDATE nexus360.usuario
                   SET nombre = COALESCE($2, nombre),
                       email  = COALESCE($3, email)
                 WHERE usuario_id = $1
                """,
                usuario_id, payload.nombre, payload.email,
            )
        except asyncpg.UniqueViolationError as exc:
            raise ApiError(
                status.HTTP_409_CONFLICT, "EMAIL_YA_REGISTRADO", "Ya existe una cuenta con ese correo.",
            ) from exc

        usuario = await _usuario_actual(conn, usuario_id)

    return MeOut(usuario=usuario)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def cambiar_password(
    payload: CambiarPasswordIn,
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    async with conn.transaction():
        usuario_id = await conn.fetchval("SELECT nexus360.validar_sesion($1)", token)
        if usuario_id is None:
            raise ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "La sesión no es válida o expiró.")
        await fijar_usuario_actual(conn, usuario_id)

        try:
            await conn.fetchval(
                "SELECT nexus360.cambiar_password_usuario($1, $2)",
                payload.password_actual, payload.password_nueva,
            )
        except asyncpg.PostgresError as exc:
            raise desde_postgres(exc) from exc

    return None


# ---------------------------------------------------------------------
# Foto de perfil
# ---------------------------------------------------------------------
# Sin foto propia, cada usuario usa su foto predeterminada (iniciales
# sobre un color estable), que dibuja el front: no hay nada que guardar.
# Leer la foto de cualquier usuario va por GET /usuarios/{id}/foto
# (ver routers/usuarios.py); aquí solo se cambia o se quita la propia.


async def _leer_cuerpo_limitado(request: Request, limite: int) -> bytes:
    """Lee el cuerpo del request cortando en cuanto pasa `limite`, en vez
    de cargarlo entero en memoria y medirlo después. Content-Length puede
    faltar (subidas por partes) o mentir, así que se cuenta lo recibido."""
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > limite:
        raise ApiError(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "VALIDACION",
            "La imagen es demasiado pesada (máximo 5 MB).",
        )

    partes: list[bytes] = []
    recibido = 0
    async for parte in request.stream():
        recibido += len(parte)
        if recibido > limite:
            raise ApiError(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "VALIDACION",
                "La imagen es demasiado pesada (máximo 5 MB).",
            )
        partes.append(parte)
    return b"".join(partes)


@router.put("/me/foto", response_model=MeOut)
async def subir_foto(
    request: Request,
    token: str = Depends(requerir_token),
):
    """Reemplaza la foto de perfil del usuario en sesión.

    El cuerpo es la imagen en binario (Content-Type: image/webp, image/jpeg
    o image/png), no un formulario multipart: el front ya la recorta y la
    manda tal cual. El Content-Type declarado no se usa para nada: el
    formato real lo decide Pillow al decodificarla.

    A diferencia del resto de rutas, esta no usa la dependencia get_conn:
    tomaría una conexión del pool durante toda la subida y el procesado
    de la imagen. Aquí se pide una conexión corta para validar la sesión
    (así una petición sin sesión no llega a subir megas), se suelta, y se
    pide otra solo para escribir.
    """
    pool: asyncpg.Pool = request.app.state.pool

    async with pool.acquire() as conn:
        usuario_id = await conn.fetchval("SELECT nexus360.validar_sesion($1)", token)
    if usuario_id is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "La sesión no es válida o expiró.")

    datos = await _leer_cuerpo_limitado(request, MAX_BYTES_ENTRADA)
    try:
        imagen, mime = await run_in_threadpool(procesar_foto_perfil, datos)
    except ImagenInvalida as exc:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDACION", str(exc)) from exc

    async with pool.acquire() as conn, conn.transaction():
        # Se revalida dentro de la transacción que escribe: la sesión pudo
        # revocarse mientras se subía o procesaba la imagen.
        usuario_id = await conn.fetchval("SELECT nexus360.validar_sesion($1)", token)
        if usuario_id is None:
            raise ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "La sesión no es válida o expiró.")
        await fijar_usuario_actual(conn, usuario_id)

        # clock_timestamp() y no now(): now() es la hora de inicio de la
        # transacción, y es la versión que usa el front para su caché —
        # cada cambio debe producir una marca distinta.
        await conn.execute(
            """
            INSERT INTO nexus360.usuario_foto (usuario_id, imagen, mime, actualizado_en)
            VALUES (nexus360.current_usuario_id(), $1, $2, clock_timestamp())
            ON CONFLICT (usuario_id) DO UPDATE SET
                imagen = EXCLUDED.imagen,
                mime = EXCLUDED.mime,
                actualizado_en = EXCLUDED.actualizado_en
            """,
            imagen, mime,
        )
        usuario = await _usuario_actual(conn, usuario_id)

    return MeOut(usuario=usuario)


@router.delete("/me/foto", response_model=MeOut)
async def quitar_foto(
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Quita la foto propia: el usuario vuelve a su foto predeterminada.
    Idempotente — quitarla cuando no hay ninguna no es un error."""
    async with conn.transaction():
        usuario_id = await conn.fetchval("SELECT nexus360.validar_sesion($1)", token)
        if usuario_id is None:
            raise ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "La sesión no es válida o expiró.")
        await fijar_usuario_actual(conn, usuario_id)

        await conn.execute(
            "DELETE FROM nexus360.usuario_foto WHERE usuario_id = nexus360.current_usuario_id()"
        )
        usuario = await _usuario_actual(conn, usuario_id)

    return MeOut(usuario=usuario)
