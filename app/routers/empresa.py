"""/api/empresa/*: perfil, tamizaje y autodiagnóstico RSE Express de la
empresa vinculada a la cuenta en sesión."""

import logging
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, Request, status

from ..config import get_settings
from ..db import fijar_usuario_actual, get_conn
from ..diagnostico_rse import (
    FORMATO_RSE,
    diagnostico_vigente_id,
    guardar_diagnostico,
    leer_diagnostico,
    ultimo_tamizaje,
)
from ..errors import ApiError
from ..ia.analisis import (
    generar_una_vez,
    guardar_analisis,
    leer_analisis,
    leer_organizacion,
    tabla_faltante,
)
from ..ia.gemini_service import ErrorIA, obtener_servicio
from ..ia.prompts import (
    VERSION_PROMPT,
    construir_contexto,
    contexto_organizacion,
    huella,
)
from ..ia.schemas import AnalisisIAIn, AnalisisIAOut
from ..schemas_empresa import (
    DiagnosticoIn,
    DiagnosticoOut,
    EmpresaIn,
    EmpresaMiaOut,
    PerfilOut,
)
from ..security import requerir_token

router = APIRouter(prefix="/empresa", tags=["empresa"])
logger = logging.getLogger("nexus360.ia")


async def _contexto(token: str, conn: asyncpg.Connection) -> str:
    """Valida el token y fija app.current_usuario_id. Debe llamarse DENTRO
    de una transacción abierta para que el SET LOCAL siga vigente."""
    usuario_id = await conn.fetchval("SELECT nexus360.validar_sesion($1)", token)
    if usuario_id is None:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            "CREDENCIALES_INVALIDAS",
            "La sesión no es válida o expiró.",
        )
    await fijar_usuario_actual(conn, usuario_id)
    return usuario_id


async def _mi_empresa(conn: asyncpg.Connection) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT e.empresa_id, e.razon_social, e.nit, e.dv, e.sector_id, e.municipio,
               e.departamento, e.extranjera
          FROM nexus360.empresa e
          JOIN nexus360.usuario_empresa ue ON ue.empresa_id = e.empresa_id
         WHERE ue.usuario_id = nexus360.current_usuario_id()
           AND e.archivado_en IS NULL
         ORDER BY e.creado_en
         LIMIT 1
        """
    )


async def _estado_completo(
    conn: asyncpg.Connection, empresa: asyncpg.Record
) -> EmpresaMiaOut:
    tamizaje = await ultimo_tamizaje(conn, empresa["empresa_id"])
    diagnostico = None
    if tamizaje is not None:
        diagnostico_id = await diagnostico_vigente_id(
            conn, empresa["empresa_id"], tamizaje.ciclo_id
        )
        if diagnostico_id is not None:
            diagnostico = await leer_diagnostico(conn, diagnostico_id)
    return EmpresaMiaOut(
        empresa=PerfilOut(**dict(empresa)), tamizaje=tamizaje, diagnostico=diagnostico
    )


@router.get("/mio", response_model=EmpresaMiaOut)
async def obtener_mi_empresa(
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Todo lo que la empresa tiene guardado: perfil, tamizaje vigente y
    autodiagnóstico. 404 solo si la cuenta aún no registró su empresa; si la
    empresa existe pero falta el tamizaje (p. ej. tras la migración 009),
    responde 200 con `tamizaje: null` para que el front lo pida de nuevo con
    el perfil ya lleno."""
    async with conn.transaction():
        await _contexto(token, conn)
        empresa = await _mi_empresa(conn)
        if empresa is None:
            raise ApiError(
                status.HTTP_404_NOT_FOUND,
                "DESCONOCIDO",
                "Todavía no hay datos guardados para esta cuenta.",
            )
        return await _estado_completo(conn, empresa)


@router.put("/mio", response_model=EmpresaMiaOut, status_code=status.HTTP_200_OK)
async def guardar_mi_empresa(
    payload: EmpresaIn,
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Crea o actualiza el perfil de la empresa y su tamizaje vigente.

    El tamizaje vigente es el ciclo más reciente: si existe se actualiza, y
    si no existe se crea con el año en curso. Así la empresa no tiene que
    volver a empezar el autodiagnóstico cuando cambia el año."""
    anio_actual = datetime.now(timezone.utc).year

    async with conn.transaction():
        await _contexto(token, conn)
        existente = await _mi_empresa(conn)

        try:
            if existente:
                empresa_id = existente["empresa_id"]
                await conn.execute(
                    """
                    UPDATE nexus360.empresa
                       SET razon_social = $2, nit = $3, dv = $4, sector_id = $5,
                           municipio = $6, departamento = $7, extranjera = $8
                     WHERE empresa_id = $1
                    """,
                    empresa_id,
                    payload.razon_social,
                    payload.nit,
                    payload.dv,
                    payload.sector_id,
                    payload.municipio,
                    payload.departamento,
                    payload.extranjera,
                )
            else:
                empresa_id = await conn.fetchval(
                    """
                    INSERT INTO nexus360.empresa (razon_social, nit, dv, sector_id, municipio, departamento, extranjera)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING empresa_id
                    """,
                    payload.razon_social,
                    payload.nit,
                    payload.dv,
                    payload.sector_id,
                    payload.municipio,
                    payload.departamento,
                    payload.extranjera,
                )
        except asyncpg.UniqueViolationError as exc:
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "CONFLICTO",
                "Ese NIT ya está registrado por otra cuenta. Contacta al administrador para vincular el acceso.",
            ) from exc
        except asyncpg.CheckViolationError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "VALIDACION",
                "El dígito de verificación no corresponde al NIT.",
            ) from exc
        except asyncpg.ForeignKeyViolationError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "VALIDACION",
                "El sector no es válido.",
            ) from exc

        valores = (
            payload.tamano,
            payload.ingresos_rango,
            payload.personas,
            payload.vinculacion,
            payload.vinculacion_detalle,
            payload.zonas,
            payload.territorio,
            payload.clientes,
            payload.clientes_detalle,
            payload.vecinos,
        )
        ciclo_id = await conn.fetchval(
            """
            SELECT ciclo_id FROM nexus360.ciclo_tamizaje
             WHERE empresa_id = $1 ORDER BY anio DESC, creado_en DESC LIMIT 1
            """,
            empresa_id,
        )
        if ciclo_id is not None:
            await conn.execute(
                """
                UPDATE nexus360.ciclo_tamizaje
                   SET tamano = $2, ingresos_rango = $3, personas = $4, vinculacion = $5,
                       vinculacion_detalle = $6, zonas = $7, territorio = $8, clientes = $9,
                       clientes_detalle = $10, vecinos = $11, actualizado_en = now()
                 WHERE ciclo_id = $1
                """,
                ciclo_id,
                *valores,
            )
        else:
            await conn.execute(
                """
                INSERT INTO nexus360.ciclo_tamizaje
                    (empresa_id, anio, tamano, ingresos_rango, personas, vinculacion,
                     vinculacion_detalle, zonas, territorio, clientes, clientes_detalle, vecinos)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                empresa_id,
                anio_actual,
                *valores,
            )

        empresa = await _mi_empresa(conn)
        return await _estado_completo(conn, empresa)


@router.put("/mio/diagnosticos/{formato_id}/respuestas", response_model=DiagnosticoOut)
async def guardar_respuestas(
    formato_id: str,
    payload: DiagnosticoIn,
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Guarda el autodiagnóstico RSE Express (respuestas abiertas, etapas,
    cierre por materia, comentario final y matriz de priorización)."""
    if formato_id != FORMATO_RSE:
        raise ApiError(
            status.HTTP_410_GONE,
            "VALIDACION",
            "Ese formato fue retirado. El diagnóstico vigente es el Autodiagnóstico RSE Express.",
        )

    async with conn.transaction():
        await _contexto(token, conn)
        empresa = await _mi_empresa(conn)
        if empresa is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "VALIDACION",
                "Primero hay que guardar el perfil y el tamizaje de la empresa.",
            )
        tamizaje = await ultimo_tamizaje(conn, empresa["empresa_id"])
        if tamizaje is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "VALIDACION",
                "Primero hay que responder el tamizaje «Conozcamos su empresa».",
            )
        diagnostico_id = await guardar_diagnostico(
            conn, empresa["empresa_id"], tamizaje.ciclo_id, payload
        )
        return await leer_diagnostico(conn, diagnostico_id)


# ---------------------------------------------------------------------------
# Análisis inteligente (Gemini)
# ---------------------------------------------------------------------------


def _error_ia(exc: ErrorIA) -> ApiError:
    return ApiError(exc.status_code, exc.codigo, exc.mensaje)


@router.post("/mio/diagnosticos/{formato_id}/analisis-ia", response_model=AnalisisIAOut)
async def analisis_ia(
    formato_id: str,
    payload: AnalisisIAIn,
    request: Request,
    token: str = Depends(requerir_token),
):
    """Interpretación con IA de los resultados del autodiagnóstico.

    Recibe los resultados que el motor existente ya calculó (capa 1) y
    devuelve la interpretación de Gemini (capa 2): resumen, fortalezas,
    oportunidades, prioridades, recomendaciones, acciones y conclusión.
    Gemini nunca recalcula ni cambia niveles o prioridades.

    Si ya hay un análisis guardado para estos mismos resultados, se devuelve
    sin llamar a Gemini (`reutilizado: true`). Si Gemini falla, responde
    503 IA_NO_DISPONIBLE con un mensaje amable: el diagnóstico y el PDF
    siguen funcionando igual en el front.

    La conexión a la base no se retiene mientras Gemini responde: se usa una
    para leer, se suelta, y se toma otra solo para guardar.
    """
    if formato_id != FORMATO_RSE:
        raise ApiError(
            status.HTTP_410_GONE,
            "VALIDACION",
            "Ese formato fue retirado. El diagnóstico vigente es el Autodiagnóstico RSE Express.",
        )
    settings = get_settings()
    pool: asyncpg.Pool = request.app.state.pool
    resultados = payload.resultados

    # 1) Sesión, diagnóstico de la empresa y análisis guardado.
    async with pool.acquire() as conn, conn.transaction():
        usuario_id = await _contexto(token, conn)
        empresa = await _mi_empresa(conn)
        tamizaje = (
            await ultimo_tamizaje(conn, empresa["empresa_id"]) if empresa else None
        )
        diagnostico_id = (
            await diagnostico_vigente_id(conn, empresa["empresa_id"], tamizaje.ciclo_id)
            if tamizaje
            else None
        )
        if diagnostico_id is None:
            # Código propio: el front lo distingue de un fallo de Gemini.
            raise ApiError(
                422,
                "SIN_DIAGNOSTICO",
                "Todavía no hay datos de la empresa ni un autodiagnóstico guardados para analizar.",
            )
        organizacion = await leer_organizacion(
            conn, empresa["empresa_id"], tamizaje.ciclo_id
        )
        contexto = construir_contexto(contexto_organizacion(organizacion), resultados)
        firma = huella(contexto)
        try:
            guardado = await leer_analisis(conn, diagnostico_id)
        except asyncpg.UndefinedTableError:
            raise _error_ia(tabla_faltante()) from None

    if guardado is not None and guardado.huella == firma:
        return guardado.salida(reutilizado=True)

    # 2) Gemini (sin conexión a la base tomada).
    try:
        servicio = obtener_servicio(settings)
        analisis = await generar_una_vez(
            usuario_id,
            diagnostico_id,
            firma,
            settings.ia_max_generaciones_por_hora,
            lambda: servicio.analizar(contexto, resultados.materias_aplicables),
        )
    except ErrorIA as exc:
        raise _error_ia(exc) from None

    # 3) Guardar. Si no se puede guardar, el análisis igual se entrega: ya se
    #    pagó la llamada y el usuario no tiene por qué perderlo.
    try:
        async with pool.acquire() as conn, conn.transaction():
            await _contexto(token, conn)
            nuevo = await guardar_analisis(
                conn, diagnostico_id, analisis, firma, servicio.modelo, VERSION_PROMPT
            )
        return nuevo.salida(reutilizado=False)
    except asyncpg.UndefinedTableError:
        tabla_faltante()
    except asyncpg.PostgresError:
        logger.exception(
            "No se pudo guardar el análisis IA del diagnóstico %s", diagnostico_id
        )
    return AnalisisIAOut(
        diagnostico_id=diagnostico_id,
        analisis=analisis,
        generado_en=datetime.now(timezone.utc),
        modelo=servicio.modelo,
        version_prompt=VERSION_PROMPT,
        reutilizado=False,
    )
