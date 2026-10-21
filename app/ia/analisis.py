"""Persistencia del análisis IA y control de llamadas a Gemini.

Flujo (ver POST /empresa/mio/diagnosticos/{formato}/analisis-ia):

    ¿Hay un análisis guardado con la misma huella?  → sí: se reutiliza
                                                     → no: Gemini → validar → guardar

La huella es el SHA-256 del contexto enviado a Gemini más la versión del
prompt: si la empresa cambia una respuesta (o NEXUS clasifica una práctica
propia), los resultados cambian, la huella cambia y el análisis se regenera
la próxima vez que abra sus resultados. Si nada cambió, no se llama a Gemini.

Todas las funciones de base de datos reciben una conexión que ya tiene fijado
app.current_usuario_id dentro de una transacción: el RLS de la tabla
diagnostico_analisis_ia decide qué filas ve cada quien.
"""
import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from .gemini_service import IALimiteAlcanzado, IANoDisponible
from .schemas import AnalisisIA, AnalisisIAOut

logger = logging.getLogger("nexus360.ia")

MENSAJE_MIGRACION = (
    "Falta aplicar db/010_analisis_ia.sql: el análisis inteligente no se puede guardar ni reutilizar. "
    "Aplíquela con el rol dueño del esquema y reinicie el backend."
)


# ------------------------------------------------------------ base de datos

SQL_ORGANIZACION = """
    SELECT s.nombre AS sector, e.municipio, e.departamento,
           t.tamano, t.ingresos_rango, t.personas, t.vinculacion, t.zonas, t.territorio, t.vecinos, t.clientes
      FROM nexus360.empresa e
      JOIN nexus360.sector s ON s.sector_id = e.sector_id
      JOIN nexus360.ciclo_tamizaje t ON t.ciclo_id = $2
     WHERE e.empresa_id = $1
"""


async def leer_organizacion(conn: asyncpg.Connection, empresa_id: UUID, ciclo_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(SQL_ORGANIZACION, empresa_id, ciclo_id)


@dataclass
class AnalisisGuardado:
    diagnostico_id: UUID
    analisis: AnalisisIA
    huella: str
    modelo: str
    version_prompt: str
    generado_en: datetime

    def salida(self, reutilizado: bool) -> AnalisisIAOut:
        return AnalisisIAOut(
            diagnostico_id=self.diagnostico_id, analisis=self.analisis, generado_en=self.generado_en,
            modelo=self.modelo, version_prompt=self.version_prompt, reutilizado=reutilizado,
        )


async def leer_analisis(conn: asyncpg.Connection, diagnostico_id: UUID) -> AnalisisGuardado | None:
    fila = await conn.fetchrow(
        """
        SELECT contenido, huella, modelo, version_prompt, generado_en
          FROM nexus360.diagnostico_analisis_ia
         WHERE diagnostico_id = $1
        """,
        diagnostico_id,
    )
    if fila is None:
        return None
    contenido = fila["contenido"]
    if isinstance(contenido, str):
        contenido = json.loads(contenido)
    try:
        analisis = AnalisisIA.model_validate(contenido)
    except ValueError:
        # Un análisis guardado que ya no cumple el contrato (p. ej. tras
        # cambiar el esquema) no se muestra: se regenera.
        logger.warning("El análisis IA guardado de %s no es válido; se regenerará.", diagnostico_id)
        return None
    return AnalisisGuardado(
        diagnostico_id=diagnostico_id, analisis=analisis, huella=fila["huella"], modelo=fila["modelo"],
        version_prompt=fila["version_prompt"], generado_en=fila["generado_en"],
    )


async def guardar_analisis(
    conn: asyncpg.Connection, diagnostico_id: UUID, analisis: AnalisisIA, huella: str,
    modelo: str, version_prompt: str,
) -> AnalisisGuardado:
    """Un análisis vigente por diagnóstico: el nuevo reemplaza al anterior."""
    generado_en = await conn.fetchval(
        """
        INSERT INTO nexus360.diagnostico_analisis_ia
            (diagnostico_id, contenido, huella, modelo, version_prompt, generado_por)
        VALUES ($1, $2::jsonb, $3, $4, $5, nexus360.current_usuario_id())
        ON CONFLICT (diagnostico_id) DO UPDATE SET
            contenido = EXCLUDED.contenido, huella = EXCLUDED.huella, modelo = EXCLUDED.modelo,
            version_prompt = EXCLUDED.version_prompt, generado_en = now(),
            generado_por = EXCLUDED.generado_por
        RETURNING generado_en
        """,
        diagnostico_id, analisis.model_dump_json(), huella, modelo, version_prompt,
    )
    return AnalisisGuardado(
        diagnostico_id=diagnostico_id, analisis=analisis, huella=huella, modelo=modelo,
        version_prompt=version_prompt, generado_en=generado_en,
    )


# ------------------------------------------------------ control de llamadas

class LimitePorHora:
    """Ventana deslizante en memoria: como mucho `maximo` análisis NUEVOS
    por usuario en la última hora. Es por proceso (se reinicia con el
    backend); basta para proteger la cuota gratuita de un prototipo."""

    def __init__(self, maximo: int, ventana_segundos: float = 3600.0):
        self.maximo = maximo
        self.ventana = ventana_segundos
        self._marcas: dict[str, deque[float]] = {}

    def consumir(self, clave: str) -> None:
        if self.maximo <= 0:
            return
        ahora = time.monotonic()
        marcas = self._marcas.setdefault(clave, deque())
        while marcas and ahora - marcas[0] > self.ventana:
            marcas.popleft()
        if len(marcas) >= self.maximo:
            raise IALimiteAlcanzado()
        marcas.append(ahora)


class EnVuelo:
    """Si llegan dos peticiones iguales a la vez (p. ej. el doble montaje de
    React en modo estricto, o dos pestañas), comparten UNA sola llamada a
    Gemini en lugar de gastar dos."""

    def __init__(self) -> None:
        self._tareas: dict[tuple, asyncio.Task] = {}

    def activa(self, clave: tuple) -> bool:
        return clave in self._tareas

    async def ejecutar(self, clave: tuple, fabrica: Callable[[], Awaitable[AnalisisIA]]) -> AnalisisIA:
        tarea = self._tareas.get(clave)
        if tarea is None:
            tarea = asyncio.ensure_future(fabrica())
            self._tareas[clave] = tarea
            tarea.add_done_callback(lambda _t: self._tareas.pop(clave, None))
        # shield: si un cliente cierra la conexión, la llamada sigue para el otro.
        return await asyncio.shield(tarea)


_en_vuelo = EnVuelo()
_limite: LimitePorHora | None = None


def limite(maximo: int) -> LimitePorHora:
    global _limite
    if _limite is None or _limite.maximo != maximo:
        _limite = LimitePorHora(maximo)
    return _limite


async def generar_una_vez(
    usuario_id: str, diagnostico_id: UUID, huella: str, maximo_por_hora: int,
    fabrica: Callable[[], Awaitable[AnalisisIA]],
) -> AnalisisIA:
    clave = (str(diagnostico_id), huella)
    if not _en_vuelo.activa(clave):
        # Solo cuenta para el límite quien de verdad dispara la llamada.
        limite(maximo_por_hora).consumir(str(usuario_id))
    return await _en_vuelo.ejecutar(clave, fabrica)


def tabla_faltante() -> IANoDisponible:
    """La base no tiene la migración 010: se registra con la instrucción
    exacta y el usuario ve el mensaje amable de siempre."""
    logger.error(MENSAJE_MIGRACION)
    return IANoDisponible()
