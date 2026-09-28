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

# Errores de Postgres que indican una estructura vieja, no un fallo puntual.
ERRORES_DE_ESQUEMA = (
    asyncpg.UndefinedColumnError,
    asyncpg.UndefinedTableError,
    asyncpg.UndefinedFunctionError,
)


async def verificar_esquema(pool: asyncpg.Pool) -> dict:
    """Devuelve {'ok': bool, 'faltantes': [...]}. No lanza: si no puede
    comprobar (p. ej. la base no responde), lo reporta como faltante."""
    faltantes: list[str] = []
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
    except Exception as exc:  # noqa: BLE001 - diagnóstico, nunca debe tumbar el arranque
        faltantes.append(f"no se pudo comprobar ({exc.__class__.__name__})")

    if faltantes:
        logger.error(
            "ESQUEMA DESACTUALIZADO: falta %s. %s", ", ".join(faltantes), MENSAJE_ESQUEMA,
        )
    return {"ok": not faltantes, "faltantes": faltantes}
