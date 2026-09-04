from collections.abc import AsyncIterator
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, status

from ..db import fijar_usuario_actual, get_conn
from ..errors import ApiError, desde_postgres
from ..schemas import (
    ActividadUsuarioOut, CambiarEstadoIn, CambiarRolIn, DiagnosticoActividadOut,
    EliminacionOut, EmpresaActividadOut, RestablecerPasswordAdminIn,
    ResumenSesionesOut, SesionAdminOut, TamizajeActividadOut, UsuarioAdminOut,
)
from ..security import requerir_token

router = APIRouter(prefix="/admin", tags=["admin"])

# Columnas que ve el panel de admin. Se centraliza para que agregar una
# (archivado_en) no obligue a tocar cuatro consultas y arriesgar que una
# quede desalineada con UsuarioAdminOut.
COLUMNAS_USUARIO = """
    usuario_id, email, nombre, rol, activo, intentos_fallidos,
    bloqueado_hasta, email_verificado_en, ultimo_login_en, creado_en,
    archivado_en
"""


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


async def _leer_usuario(conn: asyncpg.Connection, usuario_id: UUID) -> UsuarioAdminOut:
    fila = await conn.fetchrow(
        f"SELECT {COLUMNAS_USUARIO} FROM nexus360.usuario WHERE usuario_id = $1", usuario_id,
    )
    if fila is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "DESCONOCIDO", "Usuario no encontrado.")
    return _fila_a_usuario_admin(fila)


@router.get("/usuarios", response_model=list[UsuarioAdminOut])
async def listar_usuarios(
    incluir_archivados: bool = False,
    conn: asyncpg.Connection = Depends(requerir_admin),
):
    """Lista los usuarios. Las cuentas eliminadas (archivadas) quedan
    fuera salvo que se pidan explícitamente, para que el panel no muestre
    por defecto filas sobre las que casi ninguna acción tiene sentido."""
    filas = await conn.fetch(
        f"""
        SELECT {COLUMNAS_USUARIO}
          FROM nexus360.usuario
         WHERE $1 OR archivado_en IS NULL
         ORDER BY archivado_en IS NOT NULL, creado_en DESC
        """,
        incluir_archivados,
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
    return await _leer_usuario(conn, usuario_id)


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

    return await _leer_usuario(conn, usuario_id)


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


@router.delete("/usuarios/{usuario_id}", response_model=EliminacionOut)
async def eliminar_usuario(
    usuario_id: UUID,
    conservar_historial: bool = False,
    conn: asyncpg.Connection = Depends(requerir_admin),
):
    """Elimina una cuenta.

    La decisión entre borrado físico y archivado NO se toma aquí: la toma
    admin_eliminar_usuario() en SQL, que es quien puede ver si el usuario
    dejó rastro (empresas creadas, vínculos, respuestas). Poner esa lógica
    en Python obligaría a repetir las mismas consultas fuera de la
    transacción que hace el borrado, con el riesgo de que algo cambie
    entre el chequeo y el DELETE.

    conservar_historial=true fuerza el archivado incluso si la cuenta
    está limpia.
    """
    # Se valida también aquí, antes de bajar a SQL, para devolver el
    # mensaje exacto del front (la función también lo impide).
    llamante_id = await conn.fetchval("SELECT nexus360.current_usuario_id()")
    if llamante_id == usuario_id:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDACION", "No puedes eliminar tu propia cuenta.",
        )

    try:
        modo = await conn.fetchval(
            "SELECT nexus360.admin_eliminar_usuario($1, $2)", usuario_id, conservar_historial,
        )
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc

    mensaje = (
        "La cuenta se borró definitivamente: no tenía empresas ni respuestas asociadas."
        if modo == "fisico"
        else "La cuenta se archivó: conservaba historial, así que se conserva la trazabilidad. "
             "Su correo queda libre para un registro nuevo."
    )
    return EliminacionOut(usuario_id=usuario_id, modo=modo, mensaje=mensaje)


@router.post("/usuarios/{usuario_id}/restaurar", response_model=UsuarioAdminOut)
async def restaurar_usuario(usuario_id: UUID, conn: asyncpg.Connection = Depends(requerir_admin)):
    """Deshace un archivado. Solo aplica a cuentas archivadas: si el
    borrado fue físico no hay nada que restaurar."""
    try:
        await conn.fetchval("SELECT nexus360.admin_restaurar_usuario($1)", usuario_id)
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc

    return await _leer_usuario(conn, usuario_id)


@router.get("/usuarios/{usuario_id}/actividad", response_model=ActividadUsuarioOut)
async def actividad_usuario(usuario_id: UUID, conn: asyncpg.Connection = Depends(requerir_admin)):
    """Todo el rastro de un usuario en un solo viaje: sesiones, empresas,
    tamizajes y diagnósticos.

    Las tablas de negocio están protegidas por RLS con FORCE, pero
    empresa_visible() deja pasar al admin, y requerir_admin ya fijó el
    contexto — por eso aquí se consulta directo y no hace falta una
    función SECURITY DEFINER como con `sesion`.
    """
    usuario = await _leer_usuario(conn, usuario_id)

    sesiones = await conn.fetch(
        """
        SELECT sesion_id, usuario_id, creado_en, expira_en, revocado_en,
               revocado_motivo, ip_origen::text AS ip_origen, user_agent
          FROM nexus360.admin_listar_sesiones($1)
        """,
        usuario_id,
    )

    empresas = await conn.fetch(
        """
        SELECT e.empresa_id, e.razon_social, e.nit, e.dv, e.municipio, e.creado_en,
               (e.creado_por = $1) AS es_creador
          FROM nexus360.empresa e
         WHERE e.creado_por = $1
            OR EXISTS (
                SELECT 1 FROM nexus360.usuario_empresa ue
                 WHERE ue.empresa_id = e.empresa_id AND ue.usuario_id = $1
            )
         ORDER BY e.creado_en DESC
        """,
        usuario_id,
    )

    tamizajes = await conn.fetch(
        """
        SELECT c.ciclo_id, c.empresa_id, e.razon_social, c.anio, c.tamano, c.empleados,
               c.areas_de_vida, c.ciclo_previo, c.comunidades_etnicas,
               c.consumidor_final, c.creado_en
          FROM nexus360.ciclo_tamizaje c
          JOIN nexus360.empresa e ON e.empresa_id = c.empresa_id
         WHERE e.creado_por = $1
            OR EXISTS (
                SELECT 1 FROM nexus360.usuario_empresa ue
                 WHERE ue.empresa_id = e.empresa_id AND ue.usuario_id = $1
            )
         ORDER BY c.anio DESC, c.creado_en DESC
        """,
        usuario_id,
    )

    # respuestas_usuario separa lo que respondió ESTA persona de lo que
    # respondió cualquiera de la empresa: en un diagnóstico compartido las
    # dos cifras no coinciden, y la que importa para auditar es la primera.
    diagnosticos = await conn.fetch(
        """
        SELECT d.diagnostico_id, d.formato_id, f.codigo, f.nombre AS formato_nombre,
               e.razon_social, c.anio, d.estado, d.creado_en, d.completado_en,
               count(r.respuesta_id)::int AS respuestas_total,
               count(r.respuesta_id) FILTER (WHERE r.respondido_por = $1)::int AS respuestas_usuario,
               min(r.respondido_en) FILTER (WHERE r.respondido_por = $1) AS primera_respuesta,
               max(r.respondido_en) FILTER (WHERE r.respondido_por = $1) AS ultima_respuesta
          FROM nexus360.diagnostico d
          JOIN nexus360.empresa e        ON e.empresa_id = d.empresa_id
          JOIN nexus360.ciclo_tamizaje c ON c.ciclo_id   = d.ciclo_id
          JOIN nexus360.formato f        ON f.formato_id = d.formato_id
          LEFT JOIN nexus360.respuesta r ON r.diagnostico_id = d.diagnostico_id
         WHERE e.creado_por = $1
            OR EXISTS (
                SELECT 1 FROM nexus360.usuario_empresa ue
                 WHERE ue.empresa_id = e.empresa_id AND ue.usuario_id = $1
            )
         GROUP BY d.diagnostico_id, d.formato_id, f.codigo, f.nombre,
                  e.razon_social, c.anio, d.estado, d.creado_en, d.completado_en
         ORDER BY d.creado_en DESC
        """,
        usuario_id,
    )

    return ActividadUsuarioOut(
        usuario=usuario,
        sesiones=[SesionAdminOut(**dict(f)) for f in sesiones],
        empresas=[EmpresaActividadOut(**dict(f)) for f in empresas],
        tamizajes=[TamizajeActividadOut(**dict(f)) for f in tamizajes],
        diagnosticos=[DiagnosticoActividadOut(**dict(f)) for f in diagnosticos],
    )


@router.get("/sesiones/resumen", response_model=list[ResumenSesionesOut])
async def resumen_sesiones(conn: asyncpg.Connection = Depends(requerir_admin)):
    """Conteo por usuario, para no traer 200 sesiones solo para contarlas."""
    filas = await conn.fetch(
        "SELECT usuario_id, total, activas, ultima_sesion FROM nexus360.admin_resumen_sesiones()"
    )
    return [ResumenSesionesOut(**dict(f)) for f in filas]


@router.get("/sesiones", response_model=list[SesionAdminOut])
async def listar_sesiones(
    usuario_id: UUID | None = None,
    conn: asyncpg.Connection = Depends(requerir_admin),
):
    filas = await conn.fetch(
        """
        SELECT sesion_id, usuario_id, creado_en, expira_en, revocado_en,
               revocado_motivo, ip_origen::text AS ip_origen, user_agent
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
