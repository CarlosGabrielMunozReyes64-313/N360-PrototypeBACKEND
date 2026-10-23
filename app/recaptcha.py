"""reCAPTCHA v3 en el registro, el inicio de sesión y la recuperación de contraseña.

El front pide un token a Google justo al enviar el formulario (acción
«registro» o «login») y lo manda en la cabecera `X-Recaptcha-Token`. Aquí se
verifica con Google (API SiteVerify, clave secreta «legacy» de la consola de
reCAPTCHA) ANTES de tocar la base de datos:

  * `success` tiene que ser true (token válido, de este sitio, no reutilizado
    y con menos de dos minutos);
  * `action` tiene que ser la de la ruta (un token de «login» no sirve para
    registrarse);
  * `score` tiene que alcanzar el umbral de la acción (más estricto en el
    registro que en el login, donde personas reales con VPN o navegadores muy
    privados a veces sacan puntajes bajos).

Si se rechaza, la petición no llega a iniciar_sesion(): un bot no suma
intentos fallidos y no puede bloquear a propósito la cuenta de una empresa.

Decisiones:
  * Sin RECAPTCHA_SECRET_KEY la verificación queda apagada (desarrollo,
    pruebas) y el arranque lo avisa en el log.
  * RECAPTCHA_SOLO_OBSERVAR=true registra los puntajes y lo que se habría
    rechazado, sin bloquear: sirve para fijar los umbrales con tráfico real.
  * Si Google no responde, se deja pasar y se avisa en el log: una caída de
    Google no debe impedir que las empresas entren. El bloqueo por intentos
    fallidos sigue protegiendo el login.
  * La clave secreta y el token nunca se escriben en el log.
"""
import logging

import httpx
from fastapi import Header, Request, status

from .config import Settings, get_settings
from .errors import ApiError
from .security import obtener_ip

logger = logging.getLogger("nexus360")

URL_SITEVERIFY = "https://www.google.com/recaptcha/api/siteverify"
CABECERA = "X-Recaptcha-Token"
ACCIONES = ("registro", "login", "recuperacion")

CODIGO = "RECAPTCHA"
MENSAJE = (
    "No pudimos confirmar que esta solicitud la hace una persona. Recarga la página e "
    "inténtalo de nuevo. Si sigue pasando, desactiva el bloqueador de anuncios o la VPN "
    "para este sitio."
)


def _cliente(timeout: float) -> httpx.AsyncClient:
    """Fábrica del cliente HTTP (las pruebas la reemplazan por un transporte simulado)."""
    return httpx.AsyncClient(timeout=timeout)


def _umbral(settings: Settings, accion: str) -> float:
    if accion == "registro":
        return settings.recaptcha_umbral_registro
    if accion == "recuperacion":
        return settings.recaptcha_umbral_recuperacion
    return settings.recaptcha_umbral_login


async def verificar(token: str | None, accion: str, ip: str | None, settings: Settings | None = None) -> None:
    """Lanza ApiError 403 RECAPTCHA si la solicitud no parece de una persona."""
    settings = settings or get_settings()
    if not settings.recaptcha_configurado:
        return
    if accion not in ACCIONES:  # pragma: no cover - error de programación
        raise ValueError(f"Acción de reCAPTCHA desconocida: {accion}")

    if not token or not token.strip():
        _rechazar(settings, accion, "llegó sin token (¿bloqueador de anuncios o front sin la clave del sitio?)")
        return

    secreto = settings.recaptcha_secret_key.get_secret_value().strip()
    datos_envio = {"secret": secreto, "response": token.strip()}
    if ip:
        datos_envio["remoteip"] = ip
    try:
        async with _cliente(settings.recaptcha_timeout_segundos) as cliente:
            respuesta = await cliente.post(URL_SITEVERIFY, data=datos_envio)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "reCAPTCHA: no se pudo verificar con Google (%s); se deja pasar la solicitud de %s.",
            type(exc).__name__, accion,
        )
        return

    puntaje = datos.get("score")
    umbral = _umbral(settings, accion)
    if not datos.get("success"):
        motivo = f"token no válido ({', '.join(datos.get('error-codes') or ['sin detalle'])})"
    elif datos.get("action") != accion:
        motivo = f"el token es de la acción «{datos.get('action')}»"
    elif not isinstance(puntaje, (int, float)) or puntaje < umbral:
        motivo = f"puntaje {puntaje} por debajo de {umbral}"
    else:
        logger.info("reCAPTCHA %s: puntaje %.1f (umbral %.1f).", accion, puntaje, umbral)
        return
    _rechazar(settings, accion, motivo)


def _rechazar(settings: Settings, accion: str, motivo: str) -> None:
    if settings.recaptcha_solo_observar:
        logger.warning("reCAPTCHA (solo observar) habría rechazado %s: %s.", accion, motivo)
        return
    logger.warning("reCAPTCHA rechazó %s: %s.", accion, motivo)
    raise ApiError(status.HTTP_403_FORBIDDEN, CODIGO, MENSAJE)


def requerir_recaptcha(accion: str):
    """Dependencia de FastAPI para una ruta pública. Debe declararse ANTES de
    `get_conn` en la firma: así se verifica con Google sin tener tomada una
    conexión de la base (un ataque de bots no agota el pool)."""

    async def dependencia(
        request: Request,
        x_recaptcha_token: str | None = Header(default=None, alias=CABECERA),
    ) -> None:
        await verificar(x_recaptcha_token, accion, obtener_ip(request))

    return dependencia
