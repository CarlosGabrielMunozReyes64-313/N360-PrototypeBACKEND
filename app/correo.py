"""Envío de correos transaccionales (recuperación de contraseña).

Dos formas de enviar, según CORREO_PROVEEDOR:

  * "smtp": cualquier servidor SMTP. En desarrollo, Mailpit (lo levanta
    `docker compose up -d`) en localhost:1025: atrapa todos los correos y los
    muestra en http://localhost:8025 sin mandar nada a internet.
  * "brevo": API HTTPS de Brevo (puerto 443). Para planes de hosting que
    bloquean los puertos SMTP 25/465/587, como el plan gratis de Render.

Reglas que este módulo cumple siempre:
  * El enlace (que lleva el token) y las claves nunca se escriben en el log.
    Del destinatario solo se registra una versión enmascarada (a***@dominio).
  * El nombre de la persona lo escribió ella misma al registrarse: se escapa
    en el HTML y se limpia de saltos de línea en las cabeceras.
  * smtplib bloquea: corre en un hilo aparte para no frenar el servidor.
"""
import html
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import httpx
from starlette.concurrency import run_in_threadpool

from .config import Settings, get_settings

logger = logging.getLogger("nexus360")

URL_BREVO = "https://api.brevo.com/v3/smtp/email"


class CorreoError(Exception):
    """El correo no salió. El mensaje nunca incluye el contenido del correo."""


@dataclass(frozen=True)
class Correo:
    destinatario: str
    nombre: str
    asunto: str
    texto: str
    html: str


def enmascarar(email: str) -> str:
    """ana.perez@empresa.co -> a***@empresa.co (para el log)."""
    usuario, _, dominio = email.partition("@")
    return f"{usuario[:1]}***@{dominio}" if dominio else "***"


def _sin_controles(texto: str) -> str:
    """Quita saltos de línea y caracteres de control de lo que va a una cabecera."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", texto).strip()


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------

_HTML_BASE = """<!doctype html>
<html lang="es"><body style="margin:0;padding:24px;background:#f4f7f5;font-family:Arial,Helvetica,sans-serif;color:#1a2e24">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="100%" style="max-width:520px;background:#ffffff;border-radius:10px;padding:28px" cellpadding="0" cellspacing="0">
<tr><td>
<p style="margin:0 0 18px;font-size:18px;font-weight:bold;color:#024029">NEXUS 360°</p>
{cuerpo}
<p style="margin:24px 0 0;font-size:12px;color:#5a7068">Este es un mensaje automático; no hace falta responderlo.</p>
</td></tr></table>
</td></tr></table>
</body></html>"""


def correo_recuperacion(nombre: str, email: str, enlace: str, minutos: int) -> Correo:
    n = html.escape(nombre)
    e = html.escape(enlace, quote=True)
    cuerpo = f"""
<p style="margin:0 0 12px">Hola, {n}:</p>
<p style="margin:0 0 12px">Recibimos una solicitud para restablecer la contraseña de tu cuenta.
Para elegir una nueva, abre este enlace:</p>
<p style="margin:22px 0;text-align:center">
<a href="{e}" style="display:inline-block;background:#024029;color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:7px;font-weight:bold">Restablecer contraseña</a></p>
<p style="margin:0 0 12px;font-size:13px">El enlace vence en {minutos} minutos y sirve una sola vez.
Si el botón no funciona, copia esta dirección en tu navegador:</p>
<p style="margin:0 0 12px;font-size:12px;word-break:break-all;color:#024029">{e}</p>
<p style="margin:0;font-size:13px">Si no pediste este cambio, ignora este correo: tu contraseña actual sigue funcionando.</p>"""
    texto = (
        f"Hola, {nombre}:\n\n"
        "Recibimos una solicitud para restablecer la contraseña de tu cuenta en NEXUS 360°.\n"
        "Para elegir una nueva, abre este enlace:\n\n"
        f"{enlace}\n\n"
        f"El enlace vence en {minutos} minutos y sirve una sola vez.\n\n"
        "Si no pediste este cambio, ignora este correo: tu contraseña actual sigue funcionando.\n"
    )
    return Correo(email, nombre, "Restablece tu contraseña de NEXUS 360°", texto,
                  _HTML_BASE.format(cuerpo=cuerpo))


def correo_password_cambiada(nombre: str, email: str) -> Correo:
    n = html.escape(nombre)
    cuerpo = f"""
<p style="margin:0 0 12px">Hola, {n}:</p>
<p style="margin:0 0 12px">La contraseña de tu cuenta en NEXUS 360° se acaba de cambiar con un enlace de
recuperación. Por seguridad cerramos todas las sesiones que estaban abiertas.</p>
<p style="margin:0;font-size:13px"><strong>Si no fuiste tú</strong>, pide un enlace nuevo desde
«¿Olvidaste tu contraseña?» en la pantalla de inicio de sesión y avisa al administrador de la plataforma.</p>"""
    texto = (
        f"Hola, {nombre}:\n\n"
        "La contraseña de tu cuenta en NEXUS 360° se acaba de cambiar con un enlace de recuperación.\n"
        "Por seguridad cerramos todas las sesiones que estaban abiertas.\n\n"
        "Si no fuiste tú, pide un enlace nuevo desde «¿Olvidaste tu contraseña?» en la pantalla de "
        "inicio de sesión y avisa al administrador de la plataforma.\n"
    )
    return Correo(email, nombre, "Tu contraseña de NEXUS 360° cambió", texto,
                  _HTML_BASE.format(cuerpo=cuerpo))


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------


def _mensaje_smtp(correo: Correo, settings: Settings) -> EmailMessage:
    remitente = settings.correo_remitente.strip()
    msg = EmailMessage()
    msg["Subject"] = correo.asunto
    msg["From"] = Address(_sin_controles(settings.correo_remitente_nombre), addr_spec=remitente)
    msg["To"] = Address(_sin_controles(correo.nombre), addr_spec=correo.destinatario)
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=remitente.partition("@")[2] or None)
    # Pide a los servidores que no contesten con respuestas automáticas.
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(correo.texto)
    msg.add_alternative(correo.html, subtype="html")
    return msg


def _smtp(settings: Settings):
    """Fábrica de la conexión SMTP (las pruebas la reemplazan)."""
    seguridad = settings.smtp_seguridad.strip().lower()
    timeout = settings.correo_timeout_segundos
    if seguridad == "ssl":
        return smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout,
                                context=ssl.create_default_context())
    return smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)


def _enviar_smtp_bloqueante(correo: Correo, settings: Settings) -> None:
    seguridad = settings.smtp_seguridad.strip().lower()
    if seguridad not in ("starttls", "ssl", "ninguna"):
        raise CorreoError(f"SMTP_SEGURIDAD inválida: {settings.smtp_seguridad!r}")
    try:
        with _smtp(settings) as servidor:
            if seguridad == "starttls":
                servidor.starttls(context=ssl.create_default_context())
            if settings.smtp_usuario:
                clave = settings.smtp_password.get_secret_value() if settings.smtp_password else ""
                servidor.login(settings.smtp_usuario, clave)
            servidor.send_message(_mensaje_smtp(correo, settings))
    except (smtplib.SMTPException, OSError) as exc:
        raise CorreoError(f"SMTP {settings.smtp_host}:{settings.smtp_port}: {type(exc).__name__}") from exc


def _cliente(timeout: float) -> httpx.AsyncClient:
    """Fábrica del cliente HTTP (las pruebas la reemplazan por un transporte simulado)."""
    return httpx.AsyncClient(timeout=timeout)


async def _enviar_brevo(correo: Correo, settings: Settings) -> None:
    clave = settings.brevo_api_key.get_secret_value().strip() if settings.brevo_api_key else ""
    cuerpo = {
        "sender": {"name": _sin_controles(settings.correo_remitente_nombre),
                   "email": settings.correo_remitente.strip()},
        "to": [{"email": correo.destinatario, "name": _sin_controles(correo.nombre)}],
        "subject": correo.asunto,
        "htmlContent": correo.html,
        "textContent": correo.texto,
    }
    try:
        async with _cliente(settings.correo_timeout_segundos) as cliente:
            r = await cliente.post(URL_BREVO, json=cuerpo, headers={
                "api-key": clave, "accept": "application/json",
            })
    except httpx.HTTPError as exc:
        raise CorreoError(f"Brevo: {type(exc).__name__}") from exc
    if r.status_code not in (200, 201, 202):
        # El cuerpo de error de Brevo trae un código («unauthorized»,
        # «invalid_parameter»...), útil para diagnosticar; no trae secretos.
        try:
            detalle = r.json().get("code") or r.json().get("message") or ""
        except ValueError:
            detalle = ""
        raise CorreoError(f"Brevo respondió {r.status_code} {detalle}".strip())


async def enviar(correo: Correo, settings: Settings | None = None) -> None:
    """Envía el correo o lanza CorreoError."""
    settings = settings or get_settings()
    proveedor = settings.correo_proveedor.strip().lower()
    if not settings.correo_configurado:
        raise CorreoError("El envío de correos no está configurado.")
    if proveedor == "smtp":
        await run_in_threadpool(_enviar_smtp_bloqueante, correo, settings)
    elif proveedor == "brevo":
        await _enviar_brevo(correo, settings)
    else:  # pragma: no cover - correo_configurado ya lo descarta
        raise CorreoError(f"CORREO_PROVEEDOR desconocido: {proveedor!r}")


async def enviar_sin_fallar(correo: Correo, que: str) -> None:
    """Para tareas en segundo plano: si el correo no sale, se registra en el
    log (sin el contenido) y la petición, que ya respondió, no se entera."""
    try:
        await enviar(correo)
    except CorreoError as exc:
        logger.error("No se pudo enviar el correo de %s a %s: %s", que, enmascarar(correo.destinatario), exc)
    except Exception:  # noqa: BLE001 - una tarea de fondo nunca debe tumbar nada
        logger.exception("Error inesperado enviando el correo de %s a %s", que, enmascarar(correo.destinatario))
    else:
        logger.info("Correo de %s enviado a %s.", que, enmascarar(correo.destinatario))
