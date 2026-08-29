from collections.abc import AsyncIterator

import asyncpg
from fastapi import Request

from .config import get_settings


async def crear_pool() -> asyncpg.Pool:
    settings = get_settings()
    return await asyncpg.create_pool(
        settings.database_url,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )


async def get_conn(request: Request) -> AsyncIterator[asyncpg.Connection]:
    """Entrega una conexión del pool para toda la duración del request.

    Se usa la MISMA conexión en endpoints que necesitan fijar
    app.current_usuario_id con SET LOCAL (dentro de una transacción) y
    luego consultar una tabla protegida por RLS con ese contexto activo.
    """
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        yield conn


async def fijar_usuario_actual(conn: asyncpg.Connection, usuario_id: str) -> None:
    """Fija app.current_usuario_id para la transacción en curso (RLS).

    Debe llamarse dentro de un `async with conn.transaction():` — SET LOCAL
    (aquí vía set_config con is_local=true) solo vive dentro de esa
    transacción, tal como espera el schema (ver current_usuario_id() en
    nexus360_schema.sql).
    """
    await conn.execute(
        "SELECT set_config('app.current_usuario_id', $1, true)", str(usuario_id)
    )
