"""Comprobación de que la base tiene aplicada la migración 009 (RSE Express).

El backend de esta versión consulta columnas y tablas que crea
db/009_rse_express.sql. Si la base no la tiene, cada consulta falla con
«column ... does not exist». En lugar de dejar que eso llegue como un 500
opaco, se detecta al arrancar (y en /health) y se responde con un mensaje
que dice exactamente qué hacer.
"""
import logging

import asyncpg

logger = logging.getLogger("nexus360")

CODIGO_ESQUEMA = "ESQUEMA_DESACTUALIZADO"
MENSAJE_ESQUEMA = (
    "La base de datos no tiene aplicada la migración db/009_rse_express.sql "
    "(Autodiagnóstico RSE Express). Aplíquela con el rol dueño del esquema "
    "(psql \"<conexión>\" -f db/009_rse_express.sql) y reinicie el backend."
)

MENSAJE_SIN_011 = (
    "Falta db/011_consentimiento_datos.sql: el REGISTRO de cuentas nuevas está bloqueado, porque "
    "no se puede guardar la autorización de tratamiento de datos. Aplíquela con el rol dueño del "
    "esquema y reinicie el backend. El inicio de sesión y el resto de la aplicación funcionan."
)

MENSAJE_SIN_013 = (
    "Falta db/013_recuperar_password.sql: «¿Olvidaste tu contraseña?» responderá «no disponible» "
    "hasta aplicarla con el rol dueño del esquema. El resto de la aplicación funciona normalmente."
)

# Errores de Postgres que indican una estructura vieja, no un fallo puntual.
ERRORES_DE_ESQUEMA = (
    asyncpg.UndefinedColumnError,
    asyncpg.UndefinedTableError,
    asyncpg.UndefinedFunctionError,
)


async def verificar_esquema(pool: asyncpg.Pool) -> dict:
    """Devuelve {'ok', 'faltantes', 'analisis_ia', 'consentimiento_datos',
    'recuperacion_password'}. No
    lanza: si no puede comprobar (p. ej. la base no responde), lo reporta
    como faltante.

    `analisis_ia` indica si está aplicada db/010_analisis_ia.sql y
    `consentimiento_datos` si lo está db/011. NO afectan a `ok`: sin 010
    todo funciona salvo el análisis inteligente; sin 011, todo salvo el
    registro de cuentas nuevas (que exige guardar la autorización); sin 013,
    todo salvo la recuperación de contraseña por correo."""
    faltantes: list[str] = []
    analisis_ia = False
    consentimiento = False
    recuperacion = False
    try:
        async with pool.acquire() as conn:
            fila = await conn.fetchrow(
                """
                SELECT
                    EXISTS (SELECT 1 FROM information_schema.columns
                             WHERE table_schema = 'nexus360' AND table_name = 'ciclo_tamizaje'
                               AND column_name = 'clientes') AS tamizaje,
                    EXISTS (SELECT 1 FROM information_schema.columns
                             WHERE table_schema = 'nexus360' AND table_name = 'respuesta'
                               AND column_name = 'es_diferente') AS respuesta,
                    EXISTS (SELECT 1 FROM information_schema.tables
                             WHERE table_schema = 'nexus360' AND table_name = 'respuesta_materia') AS materia
                """
            )
            if not fila["tamizaje"]:
                faltantes.append("ciclo_tamizaje.clientes (tamizaje nuevo)")
            if not fila["respuesta"]:
                faltantes.append("respuesta.es_diferente (respuesta abierta)")
            if not fila["materia"]:
                faltantes.append("tabla respuesta_materia")
            if not faltantes:
                catalogo = await conn.fetchval(
                    "SELECT count(*) FROM nexus360.formato WHERE formato_id = 'rse_express' AND activo"
                )
                if not catalogo:
                    faltantes.append("formato 'rse_express' en el catálogo")
            tablas = await conn.fetchrow(
                """
                SELECT
                    EXISTS (SELECT 1 FROM information_schema.tables
                             WHERE table_schema = 'nexus360' AND table_name = 'diagnostico_analisis_ia') AS ia,
                    EXISTS (SELECT 1 FROM information_schema.tables
                             WHERE table_schema = 'nexus360' AND table_name = 'consentimiento_datos') AS consent,
                    -- OJO: no sirve information_schema aquí. Solo lista tablas sobre
                    -- las que el rol que pregunta tiene algún privilegio, y
                    -- nexus360_app no tiene NINGUNO sobre recuperacion_password (a
                    -- propósito). to_regclass lee pg_catalog, que no depende de eso.
                    to_regclass('nexus360.recuperacion_password') IS NOT NULL AS recup
                """
            )
            analisis_ia, consentimiento = bool(tablas["ia"]), bool(tablas["consent"])
            recuperacion = bool(tablas["recup"])
    except Exception as exc:  # noqa: BLE001 - diagnóstico, nunca debe tumbar el arranque
        faltantes.append(f"no se pudo comprobar ({exc.__class__.__name__})")

    if faltantes:
        logger.error(
            "ESQUEMA DESACTUALIZADO: falta %s. %s", ", ".join(faltantes), MENSAJE_ESQUEMA,
        )
    if not analisis_ia and not faltantes:
        logger.warning(
            "Falta db/010_analisis_ia.sql: el análisis inteligente (Gemini) responderá «no disponible» "
            "hasta aplicarla. El resto de la aplicación funciona normalmente."
        )
    if not consentimiento and not faltantes:
        logger.error(MENSAJE_SIN_011)
    if not recuperacion and not faltantes:
        logger.warning(MENSAJE_SIN_013)
    return {
        "ok": not faltantes, "faltantes": faltantes,
        "analisis_ia": analisis_ia, "consentimiento_datos": consentimiento,
        "recuperacion_password": recuperacion,
    }
