import asyncpg
from fastapi import APIRouter, Depends, Request, status

from ..db import fijar_usuario_actual, get_conn
from ..errors import ApiError, desde_postgres
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
        """
        SELECT usuario_id, email, nombre, rol, activo,
               email_verificado_en, ultimo_login_en
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
