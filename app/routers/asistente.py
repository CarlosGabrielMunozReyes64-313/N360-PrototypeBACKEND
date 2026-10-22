"""/api/asistente/*: chatbot que guía a la empresa en el tamizaje y el
Autodiagnóstico RSE Express (ver app/ia/asistente.py)."""

import json
import logging

import asyncpg
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse

from ..config import get_settings
from ..db import fijar_usuario_actual
from ..errors import ApiError
from ..ia.analisis import LimitePorHora
from ..ia.asistente import (
    AsistenteNoConfigurado,
    AsistenteNoDisponible,
    ChatIn,
    transmitir,
)
from ..ia.gemini_service import ErrorIA, IALimiteAlcanzado, IANoConfigurada, obtener_servicio
from ..security import requerir_token

router = APIRouter(prefix="/asistente", tags=["asistente"])
logger = logging.getLogger("nexus360.ia")

MENSAJE_LIMITE = (
    "Hiciste muchas preguntas en poco tiempo. Espera unos minutos y vuelve a intentarlo."
)

_limite: LimitePorHora | None = None


def limite(maximo: int) -> LimitePorHora:
    """Tope propio del asistente: no comparte el contador del análisis IA."""
    global _limite
    if _limite is None or _limite.maximo != maximo:
        _limite = LimitePorHora(maximo)
    return _limite


async def verificar_empresa(pool: asyncpg.Pool, token: str) -> str:
    """Valida la sesión y exige rol 'empresa'. Suelta la conexión antes de
    llamar a Gemini: una respuesta puede tardar varios segundos."""
    async with pool.acquire() as conn, conn.transaction():
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
    if rol != "empresa":
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "PROHIBIDO",
            "El asistente está disponible para las cuentas de empresa.",
        )
    return str(usuario_id)


def _linea(evento: dict) -> bytes:
    return (json.dumps(evento, ensure_ascii=False) + "\n").encode("utf-8")


def _error_ia(exc: ErrorIA) -> ApiError:
    return ApiError(exc.status_code, exc.codigo, exc.mensaje)


@router.post("/mensajes")
async def enviar_mensaje(
    chat: ChatIn,
    request: Request,
    token: str = Depends(requerir_token),
):
    """Responde la última pregunta de la conversación, en partes.

    La respuesta es NDJSON (una línea JSON por evento):

        {"tipo": "texto", "texto": "…"}     una parte de la respuesta (0 o más)
        {"tipo": "error", "codigo": "…", "mensaje": "…"}   si se corta a mitad
        {"tipo": "fin"}                       siempre, al final

    Los errores que se conocen antes de empezar (sesión, rol, tope por hora,
    Gemini sin configurar o caído) llegan como siempre: estado HTTP y
    {codigo, mensaje}. Por eso se espera la primera parte de Gemini antes de
    responder.
    """
    settings = get_settings()
    usuario_id = await verificar_empresa(request.app.state.pool, token)

    try:
        limite(settings.asistente_max_mensajes_por_hora).consumir(usuario_id)
    except IALimiteAlcanzado:
        raise ApiError(status.HTTP_429_TOO_MANY_REQUESTS, "IA_LIMITE", MENSAJE_LIMITE) from None

    try:
        servicio = obtener_servicio(settings)
    except IANoConfigurada:
        raise _error_ia(AsistenteNoConfigurado()) from None

    partes = transmitir(servicio, chat, settings.asistente_timeout_segundos)
    try:
        primera = await partes.__anext__()
    except StopAsyncIteration:  # pragma: no cover - transmitir siempre entrega algo o lanza
        raise _error_ia(AsistenteNoDisponible()) from None
    except ErrorIA as exc:
        raise _error_ia(exc) from None

    async def eventos():
        yield _linea({"tipo": "texto", "texto": primera})
        try:
            async for parte in partes:
                yield _linea({"tipo": "texto", "texto": parte})
        except ErrorIA as exc:
            yield _linea({"tipo": "error", "codigo": exc.codigo, "mensaje": exc.mensaje})
        yield _linea({"tipo": "fin"})

    return StreamingResponse(
        eventos(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            # Proxies como nginx no deben juntar las partes: el front las
            # muestra a medida que llegan.
            "X-Accel-Buffering": "no",
        },
    )
