from collections.abc import AsyncIterator
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, status

from ..db import SQL_FOTO_ACTUALIZADA_EN, fijar_usuario_actual, get_conn
from ..diagnostico_rse import (
    FORMATO_RSE,
    diagnostico_vigente_id,
    leer_diagnostico,
    ultimo_tamizaje,
)
from ..errors import ApiError, desde_postgres
from ..schemas import (
    ActividadUsuarioOut,
    AlertasOut,
    CambiarEstadoIn,
    CambiarRolIn,
    ClasificacionOut,
    ClasificarIn,
    ConteoClienteOut,
    ConteoEstadoOut,
    ConteoEtapaOut,
    ConteoMateriaEtapaOut,
    ConteoMateriaOut,
    ConteoRangoOut,
    ConteoSectorOut,
    ConteoTamanoOut,
    DiagnosticoActividadOut,
    EliminacionOut,
    EmpresaActividadOut,
    EmpresaDetalleOut,
    EstadisticasOut,
    IndicadoresDiagnosticoOut,
    PromedioDimensionOut,
    RestablecerPasswordAdminIn,
    ResumenGeneralOut,
    ResumenSesionesOut,
    SesionAdminOut,
    TamizajeActividadOut,
    UsuarioAdminOut,
)
from ..schemas_empresa import EmpresaMiaOut, PerfilOut
from ..security import requerir_token

router = APIRouter(prefix="/admin", tags=["admin"])

# Columnas que ve el panel de admin. Se centraliza para que agregar una
# (archivado_en, foto_actualizada_en) no obligue a tocar cuatro consultas y
# arriesgar que una quede desalineada con UsuarioAdminOut.
COLUMNAS_USUARIO = f"""
    usuario_id, email, nombre, rol, activo, intentos_fallidos,
    bloqueado_hasta, email_verificado_en, ultimo_login_en, creado_en,
    archivado_en, {SQL_FOTO_ACTUALIZADA_EN}
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
            raise ApiError(
                status.HTTP_401_UNAUTHORIZED,
                "CREDENCIALES_INVALIDAS",
                "La sesión no es válida o expiró.",
            )

        await fijar_usuario_actual(conn, usuario_id)

        rol = await conn.fetchval(
            "SELECT rol FROM nexus360.usuario WHERE usuario_id = $1", usuario_id
        )
        if rol != "admin":
            raise ApiError(
                status.HTTP_403_FORBIDDEN,
                "PROHIBIDO",
                "Esta acción requiere una cuenta de administrador.",
            )

        yield conn


def _fila_a_usuario_admin(fila: asyncpg.Record) -> UsuarioAdminOut:
    return UsuarioAdminOut(**dict(fila))


async def _leer_usuario(conn: asyncpg.Connection, usuario_id: UUID) -> UsuarioAdminOut:
    fila = await conn.fetchrow(
        f"SELECT {COLUMNAS_USUARIO} FROM nexus360.usuario WHERE usuario_id = $1",
        usuario_id,
    )
    if fila is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "DESCONOCIDO", "Usuario no encontrado."
        )
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
        "UPDATE nexus360.usuario SET activo = $2 WHERE usuario_id = $1",
        usuario_id,
        payload.activo,
    )
    return await _leer_usuario(conn, usuario_id)


@router.post(
    "/usuarios/{usuario_id}/desbloquear", status_code=status.HTTP_204_NO_CONTENT
)
async def desbloquear_usuario(
    usuario_id: UUID, conn: asyncpg.Connection = Depends(requerir_admin)
):
    try:
        await conn.fetchval("SELECT nexus360.admin_desbloquear_usuario($1)", usuario_id)
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc


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
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDACION",
            "No puedes quitarte tu propio rol de admin.",
        )

    try:
        await conn.fetchval(
            "SELECT nexus360.cambiar_rol_usuario($1, $2)", usuario_id, payload.rol
        )
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc

    return await _leer_usuario(conn, usuario_id)


@router.post(
    "/usuarios/{usuario_id}/restablecer-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def restablecer_password(
    usuario_id: UUID,
    payload: RestablecerPasswordAdminIn,
    conn: asyncpg.Connection = Depends(requerir_admin),
):
    try:
        await conn.fetchval(
            "SELECT nexus360.admin_restablecer_password($1, $2)",
            usuario_id,
            payload.password_nueva,
        )
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc


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
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDACION",
            "No puedes eliminar tu propia cuenta.",
        )

    try:
        modo = await conn.fetchval(
            "SELECT nexus360.admin_eliminar_usuario($1, $2)",
            usuario_id,
            conservar_historial,
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
async def restaurar_usuario(
    usuario_id: UUID, conn: asyncpg.Connection = Depends(requerir_admin)
):
    """Deshace un archivado. Solo aplica a cuentas archivadas: si el
    borrado fue físico no hay nada que restaurar."""
    try:
        await conn.fetchval("SELECT nexus360.admin_restaurar_usuario($1)", usuario_id)
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc

    return await _leer_usuario(conn, usuario_id)


# Una práctica registrada (indicador de la sección 10 y de la hipótesis H13):
# la empresa describió algo que ya hace (texto, ejemplo marcado o «algo
# diferente») y no lo marcó como «aún no lo hemos abordado» ni «no aplica».
SQL_ES_PRACTICA = """
    (coalesce(btrim(r.texto), '') <> '' OR cardinality(r.ejemplos) > 0
     OR coalesce(btrim(r.otro_texto), '') <> '')
    AND NOT r.es_na AND (r.es_diferente OR r.valor >= 1)
"""

# Respuestas vigentes: de empresas activas, diagnósticos no archivados y
# preguntas del instrumento vigente (no las del Formato 01/02 archivados).
SQL_RESPUESTAS_VIGENTES = """
      FROM nexus360.respuesta r
      JOIN nexus360.pregunta p     ON p.pregunta_id = r.pregunta_id
      JOIN nexus360.seccion sec    ON sec.seccion_id = p.seccion_id
      JOIN nexus360.dimension dim  ON dim.dimension_id = sec.dimension_id
      JOIN nexus360.diagnostico d  ON d.diagnostico_id = r.diagnostico_id
      JOIN nexus360.empresa e      ON e.empresa_id = d.empresa_id
     WHERE e.archivado_en IS NULL
       AND d.estado <> 'archivado'
       AND dim.archivado_en IS NULL
"""

SQL_ULTIMO_CICLO = """
    SELECT DISTINCT ON (c.empresa_id) c.*
      FROM nexus360.ciclo_tamizaje c
      JOIN nexus360.empresa e ON e.empresa_id = c.empresa_id
     WHERE e.archivado_en IS NULL
     ORDER BY c.empresa_id, c.anio DESC, c.creado_en DESC
"""


@router.get("/estadisticas", response_model=EstadisticasOut)
async def estadisticas(conn: asyncpg.Connection = Depends(requerir_admin)):
    """Vista agregada para el panel: conteos generales, distribuciones e
    indicadores del autodiagnóstico RSE Express.

    Todas las consultas excluyen empresas archivadas. El tamizaje que cuenta
    es el más reciente de cada empresa (DISTINCT ON), para no contar dos
    veces a quien lo editó en años distintos.
    """
    resumen = await conn.fetchrow(
        """
        SELECT
            (SELECT count(*) FROM nexus360.empresa WHERE archivado_en IS NULL) AS empresas,
            (SELECT count(*) FROM nexus360.usuario WHERE archivado_en IS NULL) AS usuarios,
            (SELECT count(*) FROM nexus360.diagnostico d
               JOIN nexus360.empresa e ON e.empresa_id = d.empresa_id
              WHERE e.archivado_en IS NULL AND d.formato_id = $1) AS diagnosticos_totales,
            (SELECT count(*) FROM nexus360.diagnostico d
               JOIN nexus360.empresa e ON e.empresa_id = d.empresa_id
              WHERE e.archivado_en IS NULL AND d.formato_id = $1
                AND d.estado = 'completado') AS diagnosticos_completados
        """,
        FORMATO_RSE,
    )

    por_sector = await conn.fetch(
        """
        SELECT s.sector_id, s.nombre, count(e.empresa_id) AS total
          FROM nexus360.sector s
          LEFT JOIN nexus360.empresa e ON e.sector_id = s.sector_id AND e.archivado_en IS NULL
         GROUP BY s.sector_id, s.nombre
        HAVING count(e.empresa_id) > 0
         ORDER BY total DESC
        """
    )

    por_tamano = await conn.fetch(
        f"SELECT tamano, count(*) AS total FROM ({SQL_ULTIMO_CICLO}) u GROUP BY tamano ORDER BY total DESC"
    )
    por_cliente = await conn.fetch(
        f"SELECT clientes, count(*) AS total FROM ({SQL_ULTIMO_CICLO}) u GROUP BY clientes ORDER BY total DESC"
    )

    por_estado = await conn.fetch(
        """
        SELECT d.formato_id, d.estado, count(*) AS total
          FROM nexus360.diagnostico d
          JOIN nexus360.empresa e ON e.empresa_id = d.empresa_id
          JOIN nexus360.formato f ON f.formato_id = d.formato_id
         WHERE e.archivado_en IS NULL AND f.archivado_en IS NULL
         GROUP BY d.formato_id, d.estado
         ORDER BY d.formato_id, d.estado
        """
    )

    por_etapa = await conn.fetch(
        f"""
        SELECT CASE WHEN r.es_na THEN 'NA'
                    WHEN r.es_diferente THEN 'diferente'
                    ELSE r.valor::text END AS etapa,
               count(*) AS total
          {SQL_RESPUESTAS_VIGENTES}
           AND (r.es_na OR r.es_diferente OR r.valor IS NOT NULL)
         GROUP BY 1
         ORDER BY 1
        """
    )

    # Lectura interna: la etapa elegida, o la clasificación de NEXUS para
    # «Hacemos algo diferente». N/A y lo que falta por clasificar no cuentan.
    promedio_dimension = await conn.fetch(
        f"""
        SELECT dim.formato_id, dim.numero, dim.nombre AS dimension,
               avg(coalesce(r.valor, r.valor_clasificado))::float8 AS promedio,
               count(*) AS respuestas
          {SQL_RESPUESTAS_VIGENTES}
           AND NOT r.es_na
           AND coalesce(r.valor, r.valor_clasificado) IS NOT NULL
         GROUP BY dim.formato_id, dim.numero, dim.nombre
         ORDER BY dim.formato_id, dim.numero
        """
    )

    indicadores = await conn.fetchrow(
        f"""
        WITH r AS (SELECT r.*, d.empresa_id {SQL_RESPUESTAS_VIGENTES}),
             ultimo AS ({SQL_ULTIMO_CICLO})
        SELECT
            (SELECT count(*) FROM ultimo) AS empresas_con_tamizaje,
            (SELECT count(*) FROM ultimo WHERE personas BETWEEN 10 AND 50) AS empresas_perfil_piloto,
            (SELECT count(DISTINCT empresa_id) FROM r
              WHERE r.es_na OR r.es_diferente OR r.valor IS NOT NULL) AS empresas_con_diagnostico,
            (SELECT count(DISTINCT empresa_id) FROM r WHERE {SQL_ES_PRACTICA}) AS empresas_con_practicas,
            (SELECT count(*) FROM r WHERE {SQL_ES_PRACTICA}) AS practicas_registradas,
            (SELECT count(*) FROM r WHERE r.es_diferente) AS respuestas_diferente,
            (SELECT count(*) FROM r WHERE r.es_diferente AND r.valor_clasificado IS NULL) AS diferente_sin_clasificar,
            (SELECT count(*) FROM r WHERE r.es_na) AS respuestas_na,
            (SELECT count(*) FROM nexus360.respuesta_materia rm
               JOIN nexus360.diagnostico d ON d.diagnostico_id = rm.diagnostico_id
               JOIN nexus360.empresa e ON e.empresa_id = d.empresa_id
              WHERE e.archivado_en IS NULL AND d.estado <> 'archivado') AS materias_con_fortalecer,
            (SELECT count(*) FROM nexus360.diagnostico d
               JOIN nexus360.empresa e ON e.empresa_id = d.empresa_id
              WHERE e.archivado_en IS NULL AND d.estado <> 'archivado'
                AND coalesce(btrim(d.comentario_final), '') <> '') AS comentarios_finales
        """
    )

    # --- Estadísticas propias del RSE Express -------------------------------
    por_personas = await conn.fetch(
        f"""
        SELECT rango, count(*) AS total FROM (
            SELECT CASE WHEN personas < 10 THEN '1-9'
                        WHEN personas <= 50 THEN '10-50'
                        WHEN personas <= 200 THEN '51-200'
                        ELSE '201+' END AS rango
              FROM ({SQL_ULTIMO_CICLO}) u
        ) x
         GROUP BY rango
         ORDER BY min(CASE rango WHEN '1-9' THEN 1 WHEN '10-50' THEN 2 WHEN '51-200' THEN 3 ELSE 4 END)
        """
    )

    etapas_materia = await conn.fetch(
        f"""
        SELECT dim.numero, dim.nombre AS materia,
               CASE WHEN r.es_na THEN 'NA'
                    WHEN r.es_diferente THEN 'diferente'
                    ELSE r.valor::text END AS etapa,
               count(*) AS total
          {SQL_RESPUESTAS_VIGENTES}
           AND dim.formato_id = '{FORMATO_RSE}'
           AND (r.es_na OR r.es_diferente OR r.valor IS NOT NULL)
         GROUP BY dim.numero, dim.nombre, 3
         ORDER BY dim.numero, 3
        """
    )

    # Todas las materias, aunque tengan cero: el cero también informa.
    practicas_materia = await conn.fetch(
        f"""
        WITH r AS (
            SELECT r.*, p.seccion_id
              FROM nexus360.respuesta r
              JOIN nexus360.pregunta p    ON p.pregunta_id = r.pregunta_id
              JOIN nexus360.diagnostico d ON d.diagnostico_id = r.diagnostico_id
              JOIN nexus360.empresa e     ON e.empresa_id = d.empresa_id
             WHERE e.archivado_en IS NULL AND d.estado <> 'archivado'
        )
        SELECT dim.numero, dim.nombre AS materia,
               count(r.respuesta_id) FILTER (WHERE {SQL_ES_PRACTICA}) AS total
          FROM nexus360.dimension dim
          LEFT JOIN nexus360.seccion sec ON sec.dimension_id = dim.dimension_id
          LEFT JOIN r ON r.seccion_id = sec.seccion_id
         WHERE dim.formato_id = '{FORMATO_RSE}' AND dim.archivado_en IS NULL
         GROUP BY dim.numero, dim.nombre
         ORDER BY dim.numero
        """
    )

    # La oportunidad elegida en la matriz de priorización se guarda con el
    # código de la pregunta (p. ej. '04b'): sus dos primeros caracteres son
    # el número de la materia.
    retos_materia = await conn.fetch(
        f"""
        SELECT dim.numero, dim.nombre AS materia, count(*) AS total
          FROM nexus360.diagnostico d
          JOIN nexus360.empresa e ON e.empresa_id = d.empresa_id
          JOIN nexus360.dimension dim
            ON dim.formato_id = d.formato_id
           AND dim.numero = left(d.priorizacion->>'elegida', 2)
           AND dim.archivado_en IS NULL
         WHERE e.archivado_en IS NULL
           AND d.estado <> 'archivado'
           AND d.formato_id = '{FORMATO_RSE}'
           AND coalesce(d.priorizacion->>'elegida', '') <> ''
         GROUP BY dim.numero, dim.nombre
         ORDER BY total DESC, dim.numero
        """
    )

    # Mismas reglas que alertasInformativas() en el front: Ley 2173 por
    # tamaño; SG-SST si 03b está en 0, 1 o N/A; datos si 06b está en 0, 1 o
    # N/A y Consumidores aplica; territorio si hay comunidades étnicas.
    alertas = await conn.fetchrow(
        f"""
        WITH ultimo AS ({SQL_ULTIMO_CICLO}),
        diag AS (
            SELECT DISTINCT ON (ciclo_id) diagnostico_id, ciclo_id
              FROM nexus360.diagnostico
             WHERE formato_id = '{FORMATO_RSE}' AND estado <> 'archivado'
             ORDER BY ciclo_id, creado_en DESC
        ),
        bajas AS (
            SELECT r.diagnostico_id,
                   bool_or(p.codigo = '03b') AS sst_baja,
                   bool_or(p.codigo = '06b') AS datos_baja
              FROM nexus360.respuesta r
              JOIN nexus360.pregunta p ON p.pregunta_id = r.pregunta_id
             WHERE p.codigo IN ('03b', '06b') AND (r.es_na OR r.valor IN (0, 1))
             GROUP BY r.diagnostico_id
        ),
        banderas AS (
            SELECT u.tamano IN ('mediana', 'nose') AS ley2173,
                   coalesce(b.sst_baja, FALSE) AS sst,
                   coalesce(b.datos_baja, FALSE) AND u.clientes IN ('personas', 'mezcla') AS datos,
                   u.zonas && ARRAY['indigenas', 'afro']::TEXT[] AS territorio
              FROM ultimo u
              LEFT JOIN diag dg ON dg.ciclo_id = u.ciclo_id
              LEFT JOIN bajas b ON b.diagnostico_id = dg.diagnostico_id
        )
        SELECT count(*) FILTER (WHERE ley2173) AS ley2173,
               count(*) FILTER (WHERE sst) AS sst,
               count(*) FILTER (WHERE datos) AS datos,
               count(*) FILTER (WHERE territorio) AS territorio
          FROM banderas
        """
    )

    return EstadisticasOut(
        resumen=ResumenGeneralOut(**dict(resumen)),
        empresas_por_sector=[ConteoSectorOut(**dict(f)) for f in por_sector],
        empresas_por_tamano=[ConteoTamanoOut(**dict(f)) for f in por_tamano],
        empresas_por_cliente=[ConteoClienteOut(**dict(f)) for f in por_cliente],
        diagnosticos_por_estado=[ConteoEstadoOut(**dict(f)) for f in por_estado],
        respuestas_por_etapa=[ConteoEtapaOut(**dict(f)) for f in por_etapa],
        promedio_por_dimension=[
            PromedioDimensionOut(**dict(f)) for f in promedio_dimension
        ],
        indicadores=IndicadoresDiagnosticoOut(**dict(indicadores)),
        empresas_por_personas=[ConteoRangoOut(**dict(f)) for f in por_personas],
        etapas_por_materia=[ConteoMateriaEtapaOut(**dict(f)) for f in etapas_materia],
        practicas_por_materia=[ConteoMateriaOut(**dict(f)) for f in practicas_materia],
        retos_por_materia=[ConteoMateriaOut(**dict(f)) for f in retos_materia],
        alertas=AlertasOut(**dict(alertas)),
    )


@router.get("/empresas", response_model=list[EmpresaDetalleOut])
async def listar_empresas_detalle(conn: asyncpg.Connection = Depends(requerir_admin)):
    """Una fila por empresa activa: su perfil, su tamizaje vigente (el ciclo
    más reciente), el avance de su autodiagnóstico RSE Express en ese ciclo
    y la cuenta que sirve de contacto (nombre y correo).

    El contacto es quien registró la empresa; si esa cuenta se eliminó, otra
    cuenta de empresa vinculada (la más antigua). Si no queda ninguna, los
    dos campos van en NULL: no se inventa un contacto."""
    filas = await conn.fetch(
        f"""
        WITH ultimo_ciclo AS ({SQL_ULTIMO_CICLO}),
        ultimo_diagnostico AS (
            SELECT DISTINCT ON (ciclo_id) diagnostico_id, ciclo_id, estado, actualizado_en
              FROM nexus360.diagnostico
             WHERE formato_id = '{FORMATO_RSE}' AND estado <> 'archivado'
             ORDER BY ciclo_id, creado_en DESC
        ),
        conteos AS (
            SELECT r.diagnostico_id,
                   count(*) FILTER (WHERE r.es_na OR r.es_diferente OR r.valor IS NOT NULL) AS respuestas_con_etapa,
                   count(*) FILTER (WHERE {SQL_ES_PRACTICA}) AS practicas_registradas,
                   count(*) FILTER (WHERE r.es_diferente AND r.valor_clasificado IS NULL) AS pendientes_clasificar
              FROM nexus360.respuesta r
             GROUP BY r.diagnostico_id
        )
        SELECT
            e.empresa_id, e.razon_social, e.nit, e.dv,
            e.sector_id, sec.nombre AS sector_nombre,
            e.municipio, e.departamento, e.creado_en,
            uc.anio, uc.tamano, uc.ingresos_rango, uc.personas, uc.vinculacion, uc.vinculacion_detalle,
            uc.zonas, uc.territorio, uc.clientes, uc.clientes_detalle,
            CASE WHEN uc.personas IS NULL THEN NULL ELSE uc.personas BETWEEN 10 AND 50 END AS perfil_piloto,
            ud.estado AS diagnostico_estado,
            ud.actualizado_en AS diagnostico_actualizado_en,
            coalesce(co.respuestas_con_etapa, 0) AS respuestas_con_etapa,
            coalesce(co.practicas_registradas, 0) AS practicas_registradas,
            coalesce(co.pendientes_clasificar, 0) AS pendientes_clasificar,
            ct.contacto_nombre,
            ct.contacto_email
          FROM nexus360.empresa e
          JOIN nexus360.sector sec ON sec.sector_id = e.sector_id
          LEFT JOIN ultimo_ciclo uc ON uc.empresa_id = e.empresa_id
          LEFT JOIN ultimo_diagnostico ud ON ud.ciclo_id = uc.ciclo_id
          LEFT JOIN conteos co ON co.diagnostico_id = ud.diagnostico_id
          LEFT JOIN LATERAL (
            SELECT u.nombre AS contacto_nombre, u.email::text AS contacto_email
              FROM nexus360.usuario u
             WHERE u.archivado_en IS NULL
               AND u.rol = 'empresa'
               AND (u.usuario_id = e.creado_por
                    OR EXISTS (SELECT 1 FROM nexus360.usuario_empresa ue
                                WHERE ue.empresa_id = e.empresa_id AND ue.usuario_id = u.usuario_id))
             ORDER BY coalesce(u.usuario_id = e.creado_por, FALSE) DESC, u.creado_en, u.usuario_id
             LIMIT 1
          ) ct ON TRUE
         WHERE e.archivado_en IS NULL
         ORDER BY e.creado_en DESC
        """
    )
    return [EmpresaDetalleOut(**dict(f)) for f in filas]


@router.get("/empresas/{empresa_id}/diagnostico", response_model=EmpresaMiaOut)
async def diagnostico_empresa(
    empresa_id: UUID, conn: asyncpg.Connection = Depends(requerir_admin)
):
    """Lo que respondió una empresa, para que NEXUS lo lea: tamizaje vigente,
    respuestas abiertas, etapas, «qué le gustaría fortalecer», comentario
    final y matriz de priorización. Mismo formato que GET /empresa/mio."""
    empresa = await conn.fetchrow(
        """
        SELECT empresa_id, razon_social, nit, dv, sector_id, municipio, departamento, extranjera
          FROM nexus360.empresa WHERE empresa_id = $1 AND archivado_en IS NULL
        """,
        empresa_id,
    )
    if empresa is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "DESCONOCIDO", "Empresa no encontrada."
        )
    tamizaje = await ultimo_tamizaje(conn, empresa_id)
    diagnostico = None
    if tamizaje is not None:
        diagnostico_id = await diagnostico_vigente_id(
            conn, empresa_id, tamizaje.ciclo_id
        )
        if diagnostico_id is not None:
            diagnostico = await leer_diagnostico(conn, diagnostico_id)
    return EmpresaMiaOut(
        empresa=PerfilOut(**dict(empresa)), tamizaje=tamizaje, diagnostico=diagnostico
    )


@router.put("/respuestas/{respuesta_id}/clasificacion", response_model=ClasificacionOut)
async def clasificar_respuesta(
    respuesta_id: UUID,
    payload: ClasificarIn,
    conn: asyncpg.Connection = Depends(requerir_admin),
):
    """NEXUS clasifica en la lectura interna 0–4 una respuesta «Hacemos algo
    diferente» (sección 6.3 del protocolo). Con `valor: null` se quita la
    clasificación. Solo aplica a esas respuestas: las demás ya tienen etapa."""
    fila = await conn.fetchrow(
        """
        SELECT r.es_diferente, p.codigo
          FROM nexus360.respuesta r JOIN nexus360.pregunta p ON p.pregunta_id = r.pregunta_id
         WHERE r.respuesta_id = $1
        """,
        respuesta_id,
    )
    if fila is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "DESCONOCIDO", "Respuesta no encontrada."
        )
    if not fila["es_diferente"]:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDACION",
            "Solo se clasifican las respuestas «Hacemos algo diferente».",
        )
    try:
        actualizada = await conn.fetchrow(
            """
            UPDATE nexus360.respuesta
               SET valor_clasificado = $2,
                   clasificado_por = CASE WHEN $2::smallint IS NULL THEN NULL ELSE nexus360.current_usuario_id() END,
                   clasificado_en  = CASE WHEN $2::smallint IS NULL THEN NULL ELSE now() END
             WHERE respuesta_id = $1
         RETURNING respuesta_id, valor_clasificado, clasificado_en
            """,
            respuesta_id,
            payload.valor,
        )
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc
    return ClasificacionOut(
        respuesta_id=actualizada["respuesta_id"],
        codigo=fila["codigo"],
        clasificada=actualizada["valor_clasificado"],
        clasificado_en=actualizada["clasificado_en"],
    )


@router.get("/usuarios/{usuario_id}/actividad", response_model=ActividadUsuarioOut)
async def actividad_usuario(
    usuario_id: UUID, conn: asyncpg.Connection = Depends(requerir_admin)
):
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
        SELECT c.ciclo_id, c.empresa_id, e.razon_social, c.anio, c.tamano, c.ingresos_rango,
               c.personas, c.vinculacion, c.zonas, c.territorio, c.clientes,
               c.creado_en, c.actualizado_en
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
async def revocar_sesion(
    sesion_id: UUID, conn: asyncpg.Connection = Depends(requerir_admin)
):
    try:
        await conn.fetchval("SELECT nexus360.admin_revocar_sesion($1)", sesion_id)
    except asyncpg.PostgresError as exc:
        raise desde_postgres(exc) from exc
