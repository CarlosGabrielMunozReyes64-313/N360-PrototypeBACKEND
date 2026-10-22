"""Cliente de Gemini (SDK oficial ``google-genai``) para el análisis IA.

Garantías:
  * La API Key solo se lee aquí, del entorno del backend; nunca se registra
    en logs ni viaja en una respuesta (los mensajes de error se sanean).
  * Gemini responde con salida estructurada (JSON Schema de AnalisisIA) y la
    respuesta se valida con Pydantic antes de usarse. Si no valida, se
    reintenta una vez; si vuelve a fallar, el análisis no se muestra y el
    diagnóstico sigue funcionando.
  * Cualquier fallo (sin clave, sin red, cuota agotada, respuesta inválida)
    se convierte en un ErrorIA con un mensaje amable para el usuario.
"""
import logging
import time
from typing import Any

from pydantic import ValidationError

# El SDK es opcional en tiempo de ejecución: si no está instalado, el backend
# arranca igual y solo el análisis IA queda deshabilitado (con un aviso claro
# en el log). Gemini nunca debe tumbar el diagnóstico.
try:
    from google import genai
    from google.genai import errors, types
except ImportError:  # pragma: no cover - se prueba en un subproceso
    genai = errors = types = None  # type: ignore[assignment]

SDK_DISPONIBLE = genai is not None
MENSAJE_SIN_SDK = (
    "No está instalado el paquete google-genai: el análisis inteligente queda deshabilitado. "
    "Instálelo con «pip install -r requirements.txt» y reinicie el backend."
)

from ..config import Settings
from .prompts import INSTRUCCIONES_SISTEMA, mensaje_usuario
from .schemas import AnalisisIA, esquema_gemini

logger = logging.getLogger("nexus360.ia")

# Fallos rápidos y pasajeros del servidor: vale la pena un segundo intento.
# 429 (cuota) NO se reintenta: en el nivel gratuito solo gasta más cuota.
_CODIGOS_TRANSITORIOS = {500, 502, 503}
# Tiempo agotado (del lado de Google o nuestro): no se reintenta.
_CODIGOS_TIEMPO_AGOTADO = {408, 504}
# Un reintento solo vale la pena si queda al menos este tiempo del total.
_MINIMO_PARA_REINTENTAR = 15.0


class ErrorIA(Exception):
    """Fallo del análisis IA. `mensaje` es seguro para mostrar al usuario."""

    codigo = "IA_NO_DISPONIBLE"
    status_code = 503
    mensaje = (
        "No pudimos generar el análisis inteligente en este momento. "
        "Sus resultados y el informe PDF siguen disponibles."
    )

    def __init__(self, mensaje: str | None = None):
        if mensaje:
            self.mensaje = mensaje
        super().__init__(self.mensaje)


class IANoConfigurada(ErrorIA):
    codigo = "IA_NO_CONFIGURADA"
    mensaje = "El análisis inteligente no está habilitado en este servidor."


class IANoDisponible(ErrorIA):
    pass


class IALimiteAlcanzado(ErrorIA):
    codigo = "IA_LIMITE"
    status_code = 429
    mensaje = (
        "Se alcanzó el número de análisis inteligentes que se pueden generar por hora. "
        "Intente de nuevo más tarde; sus resultados y el informe PDF siguen disponibles."
    )


def ajustar_referencias(analisis: AnalisisIA, materias_aplicables: set[str]) -> AnalisisIA:
    """Post-validación: una recomendación no puede apuntar a una materia que
    no aplica a la empresa (p. ej. Consumidores cuando no vende a personas).
    Si lo hace, queda como transversal en lugar de inventar una relación."""
    cambios = 0
    for r in analisis.recomendaciones:
        if r.materia != "general" and r.materia not in materias_aplicables:
            r.materia = "general"
            cambios += 1
    if cambios:
        logger.warning("Gemini citó %d materia(s) que no aplican; se marcaron como transversales.", cambios)
    return analisis


class ServicioGemini:
    """`timeout_segundos` es el tiempo MÁXIMO TOTAL de espera por análisis,
    sumando todos los intentos: la persona nunca espera más que eso."""

    def __init__(
        self,
        api_key: str,
        modelo: str,
        timeout_segundos: float = 90.0,
        intentos: int = 2,
        cliente: Any = None,
    ):
        self.modelo = modelo
        self._clave = api_key
        self._intentos = max(1, intentos)
        self._tiempo_max = timeout_segundos
        # El tiempo límite se fija en cada llamada (lo que quede del total);
        # el SDK también se lo comunica a Google (X-Server-Timeout).
        self._cliente = cliente or genai.Client(api_key=api_key)
        self._config = types.GenerateContentConfig(
            system_instruction=INSTRUCCIONES_SISTEMA,
            response_mime_type="application/json",
            response_json_schema=esquema_gemini(),
            # No usamos herramientas: sin esto el SDK activa por defecto la
            # llamada automática a funciones y llena el log de avisos.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def _sanear(self, texto: str) -> str:
        """Defensa en profundidad: la clave nunca debe llegar a un log."""
        texto = str(texto)
        return texto.replace(self._clave, "***") if self._clave else texto

    # El asistente (app/ia/asistente.py) reutiliza este cliente: mismas
    # conexiones HTTP, misma clave y el mismo saneamiento de los logs.
    @property
    def cliente(self) -> Any:
        return self._cliente

    def sanear(self, texto: Any) -> str:
        return self._sanear(texto)

    async def analizar(self, contexto: dict, materias_aplicables: set[str]) -> AnalisisIA:
        contenido = mensaje_usuario(contexto)
        comienzo = time.monotonic()
        limite = comienzo + self._tiempo_max
        for intento in range(1, self._intentos + 1):
            ultimo = intento == self._intentos
            restante = limite - time.monotonic()
            if intento > 1 and restante < _MINIMO_PARA_REINTENTAR:
                logger.warning(
                    "No queda tiempo para otro intento con Gemini (%.0f s de %.0f s usados).",
                    time.monotonic() - comienzo, self._tiempo_max,
                )
                raise IANoDisponible()
            config = self._config.model_copy(
                update={"http_options": types.HttpOptions(timeout=int(restante * 1000))},
            )
            inicio = time.monotonic()
            try:
                respuesta = await self._cliente.aio.models.generate_content(
                    model=self.modelo, contents=contenido, config=config,
                )
            except errors.APIError as exc:
                if exc.code in _CODIGOS_TIEMPO_AGOTADO:
                    self._avisar_tiempo_agotado(inicio)
                    raise IANoDisponible() from None
                logger.warning(
                    "Gemini respondió %s %s (intento %d/%d): %s", exc.code, exc.status, intento,
                    self._intentos, self._sanear(exc.message or "")[:300],
                )
                if exc.code in _CODIGOS_TRANSITORIOS and not ultimo:
                    continue
                raise IANoDisponible() from None
            except Exception as exc:  # noqa: BLE001 - red, tiempo agotado, fallo del SDK
                if _es_tiempo_agotado(exc):
                    self._avisar_tiempo_agotado(inicio)
                    raise IANoDisponible() from None
                logger.warning(
                    "No se pudo contactar a Gemini (intento %d/%d): %s: %s", intento, self._intentos,
                    type(exc).__name__, self._sanear(exc)[:300],
                )
                if not ultimo:
                    continue
                raise IANoDisponible() from None

            texto = getattr(respuesta, "text", None) or ""
            try:
                analisis = AnalisisIA.model_validate_json(texto)
            except ValidationError as exc:
                # No se registra el contenido (trae texto de la empresa); solo
                # por qué no sirvió.
                logger.warning(
                    "Gemini devolvió una respuesta que no cumple el esquema (intento %d/%d, "
                    "fin=%s, %d caracteres, %.1f s): %s",
                    intento, self._intentos, _motivo_fin(respuesta), len(texto), time.monotonic() - inicio,
                    "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in exc.errors()[:5]),
                )
                if not ultimo:
                    continue
                raise IANoDisponible() from None

            logger.info(
                "Análisis IA generado con %s en %.1f s (intento %d, %d caracteres).",
                self.modelo, time.monotonic() - comienzo, intento, len(texto),
            )
            return ajustar_referencias(analisis, materias_aplicables)

        raise IANoDisponible()  # inalcanzable: el bucle siempre retorna o lanza

    def _avisar_tiempo_agotado(self, inicio: float) -> None:
        # Reintentar tras un tiempo agotado casi nunca sirve: solo duplica la
        # espera. Si pasa seguido, subir GEMINI_TIMEOUT_SEGUNDOS.
        logger.warning(
            "Gemini no respondió a tiempo (%.0f s; límite total %.0f s). No se reintenta. "
            "Si pasa seguido, suba GEMINI_TIMEOUT_SEGUNDOS en el .env.",
            time.monotonic() - inicio, self._tiempo_max,
        )

    async def cerrar(self) -> None:
        aio = getattr(self._cliente, "aio", None)
        if aio is not None and hasattr(aio, "aclose"):
            await aio.aclose()


def _es_tiempo_agotado(exc: Exception) -> bool:
    """httpx.ReadTimeout, httpx2.*Timeout, asyncio.TimeoutError…"""
    return isinstance(exc, TimeoutError) or "Timeout" in type(exc).__name__


def _motivo_fin(respuesta: Any) -> str:
    try:
        return str(respuesta.candidates[0].finish_reason)
    except (AttributeError, IndexError, TypeError):
        return "desconocido"


# ------------------------------------------------------------ instancia

_servicio: ServicioGemini | None = None
_firma: tuple | None = None


def obtener_servicio(settings: Settings) -> ServicioGemini:
    """Instancia compartida (reutiliza las conexiones HTTP). Sin clave
    configurada lanza IANoConfigurada, que el endpoint traduce a un aviso."""
    global _servicio, _firma
    if not SDK_DISPONIBLE:
        logger.error(MENSAJE_SIN_SDK)
        raise IANoConfigurada()
    if not settings.gemini_configurado:
        raise IANoConfigurada()
    clave = settings.gemini_api_key.get_secret_value().strip()
    firma = (clave, settings.gemini_model, settings.gemini_timeout_segundos, settings.gemini_intentos)
    if _servicio is None or _firma != firma:
        _servicio = ServicioGemini(
            clave, settings.gemini_model, settings.gemini_timeout_segundos, settings.gemini_intentos,
        )
        _firma = firma
    return _servicio


async def cerrar_servicio() -> None:
    global _servicio, _firma
    if _servicio is not None:
        try:
            await _servicio.cerrar()
        except Exception:  # noqa: BLE001 - cierre de recursos, no debe tumbar el apagado
            logger.debug("No se pudo cerrar limpiamente el cliente de Gemini.", exc_info=True)
    _servicio, _firma = None, None
