from collections.abc import AsyncIterator
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, status

from ..db import fijar_usuario_actual, get_conn
from ..errors import ApiError, desde_postgres
from ..schemas import (
    CambiarEstadoIn, CambiarRolIn, RestablecerPasswordAdminIn, SesionAdminOut, UsuarioAdminOut,
)
from ..security import requerir_token

router = APIRouter(prefix="/admin", tags=["admin"])


async def requerir_admin(
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
) -> AsyncIterator[asyncpg.Connection]:
    """Valida la sesión, fija el contexto RLS, y exige que quien llama
    tenga rol='admin'. La transacción queda abierta durante todo el
    endpoint (se cierra al terminar la ruta), así SET LOCAL sigue
    vigente para las consultas que haga el endpoint después de este
    chequeo — mismo patrón que fijar_usuario_actual en los demás routers,
    solo que aquí se centraliza una vez para todas las rutas de /admin.
    """
    async with conn.transaction():
        usuario_id = await conn.fetchval("SELECT nexus360.validar_sesion($1)", token)
        if usuario_id is None:
            raise ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "La sesión no es válida o expiró.")

        await fijar_usuario_actual(conn, usuario_id)

        rol = await conn.fetchval("SELECT rol FROM nexus360.usuario WHERE usuario_id = $1", usuario_id)
        if rol != "admin":
            raise ApiError(status.HTTP_403_FORBIDDEN, "PROHIBIDO", "Esta acción requiere una cuenta de administrador.")

        yield conn


def _fila_a_usuario_admin(fila: asyncpg.Record) -> UsuarioAdminOut:
    return UsuarioAdminOut(**dict(fila))


@router.get("/usuarios", response_model=list[UsuarioAdminOut])
async def listar_usuarios(conn: asyncpg.Connection = Depends(requerir_admin)):
    filas = await conn.fetch(
        """
        SELECT usuario_id, email, nombre, rol, activo, intentos_fallidos,
               bloqueado_hasta, email_verificado_en, ultimo_login_en, creado_en
          FROM nexus360.usuario
         ORDER BY creado_en DESC
        """
    )
    return [_fila_a_usuario_admin(f) for f in filas]


@router.patch("/usuarios/{usuario_id}/estado", response_model=UsuarioAdminOut)
async def cambiar_estado(
    usuario_id: UUID,
    payload: CambiarEstadoIn,
    conn: asyncpg.Connection = Depends(requerir_admin),
):
    await conn.execute(
        "UPDATE nexus360.usuario SET activo = $2 WHERE usuario_id = $1", usuario_id, payload.activo,
    )
    fila = await conn.fetchrow(
        """
        SELECT usuario_id, email, nombre, rol, activo, intentos_fallidos,
               bloqueado_hasta, email_verificado_en, ultimo_login_en, creado_en
          FROM nexus360.usuario WHERE usuario_id = $1
        """,
        usuario_id,
    )
    if fila is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "DESCONOCIDO", "Usuario no encontrado.")
    return _fila_a_usuario_admin(fila)


@router.post("/usuarios/{usuario_id}/desbloquear", status_code=status.HTTP_204_NO_CONTENT)
async def desbloquear_usuario(usuario_id: UUID, conn: asyncpg.Connection = Depends(requerir_admin)):
    try:
        await conn.fetchval("SELECT nexus360.admin_desbloquear_usuario($1)", usuario_id)
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc
    return None


@router.post("/usuarios/{usuario_id}/rol", response_model=UsuarioAdminOut)
async def cambiar_rol(
    usuario_id: UUID,
    payload: CambiarRolIn,
    conn: asyncpg.Connection = Depends(requerir_admin),
):
    # Un admin no puede quitarse su propio rol de admin por esta vía — evita
    # que la última cuenta admin quede accidentalmente sin acceso al panel.
    llamante_id = await conn.fetchval("SELECT nexus360.current_usuario_id()")
    if llamante_id == usuario_id and payload.rol != "admin":
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDACION", "No puedes quitarte tu propio rol de admin.",
        )

    try:
        await conn.fetchval("SELECT nexus360.cambiar_rol_usuario($1, $2)", usuario_id, payload.rol)
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc

    fila = await conn.fetchrow(
        """
        SELECT usuario_id, email, nombre, rol, activo, intentos_fallidos,
               bloqueado_hasta, email_verificado_en, ultimo_login_en, creado_en
          FROM nexus360.usuario WHERE usuario_id = $1
        """,
        usuario_id,
    )
    if fila is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "DESCONOCIDO", "Usuario no encontrado.")
    return _fila_a_usuario_admin(fila)


@router.post("/usuarios/{usuario_id}/restablecer-password", status_code=status.HTTP_204_NO_CONTENT)
async def restablecer_password(
    usuario_id: UUID,
    payload: RestablecerPasswordAdminIn,
    conn: asyncpg.Connection = Depends(requerir_admin),
):
    try:
        await conn.fetchval(
            "SELECT nexus360.admin_restablecer_password($1, $2)", usuario_id, payload.password_nueva,
        )
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc
    return None


@router.get("/sesiones", response_model=list[SesionAdminOut])
async def listar_sesiones(
    usuario_id: UUID | None = None,
    conn: asyncpg.Connection = Depends(requerir_admin),
):
    filas = await conn.fetch(
        """
        SELECT sesion_id, usuario_id, creado_en, expira_en, revocado_en,
               ip_origen::text AS ip_origen, user_agent
          FROM nexus360.admin_listar_sesiones($1)
        """,
        usuario_id,
    )
    return [SesionAdminOut(**dict(f)) for f in filas]


@router.post("/sesiones/{sesion_id}/revocar", status_code=status.HTTP_204_NO_CONTENT)
async def revocar_sesion(sesion_id: UUID, conn: asyncpg.Connection = Depends(requerir_admin)):
    try:
        await conn.fetchval("SELECT nexus360.admin_revocar_sesion($1)", sesion_id)
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc
    return None
