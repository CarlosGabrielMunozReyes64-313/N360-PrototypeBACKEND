"""Recuperación de contraseña (013), lo que no necesita base de datos:
plantillas, envío por SMTP y por Brevo (simulados), y las rutas que deben
responder sin tocar la base. El flujo completo contra Postgres está en
test_recuperar_password_integracion.py."""
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app import correo, recaptcha
from app.config import get_settings
from app.correo import (
    URL_BREVO, CorreoError, correo_password_cambiada, correo_recuperacion, enmascarar, enviar,
    enviar_sin_fallar,
)
from app.main import app
from app.schemas import RestablecerPasswordIn

TOKEN = "ab" * 32
ENLACE = f"http://localhost:5173/#/restablecer?token={TOKEN}"
CLAVE_BREVO = "xkeysib-clave-que-no-debe-salir-en-logs"


@pytest.fixture
def smtp_configurado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "correo_proveedor", "smtp")
    monkeypatch.setattr(s, "correo_remitente", "no-responder@nexus360.co")
    monkeypatch.setattr(s, "smtp_host", "smtp.prueba.co")
    monkeypatch.setattr(s, "smtp_port", 587)
    monkeypatch.setattr(s, "smtp_seguridad", "starttls")
    monkeypatch.setattr(s, "smtp_usuario", "usuario-smtp")
    monkeypatch.setattr(s, "smtp_password", SecretStr("clave-smtp"))
    return s


@pytest.fixture
def brevo_configurado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "correo_proveedor", "brevo")
    monkeypatch.setattr(s, "correo_remitente", "no-responder@nexus360.co")
    monkeypatch.setattr(s, "brevo_api_key", SecretStr(CLAVE_BREVO))
    return s


@pytest.fixture
def sin_correo(monkeypatch):
    monkeypatch.setattr(get_settings(), "correo_proveedor", "")
    return get_settings()


# ------------------------------------------------------------- plantillas


def test_correo_de_recuperacion_lleva_enlace_y_vencimiento():
    c = correo_recuperacion("Ana", "ana@empresa.co", ENLACE, 30)
    assert c.destinatario == "ana@empresa.co"
    assert ENLACE in c.texto and "30 minutos" in c.texto
    assert f'href="{ENLACE}"' in c.html
    assert "Si no pediste este cambio" in c.texto


def test_el_nombre_se_escapa_en_el_html():
    """El nombre lo escribió la persona al registrarse: no puede inyectar HTML."""
    malo = '<img src=x onerror="alert(1)">'
    for c in (correo_recuperacion(malo, "a@b.co", ENLACE, 30), correo_password_cambiada(malo, "a@b.co")):
        assert malo not in c.html
        assert "&lt;img" in c.html


def test_aviso_de_password_cambiada():
    c = correo_password_cambiada("Ana", "ana@empresa.co")
    assert "cerramos todas las sesiones" in c.texto
    assert "Si no fuiste tú" in c.texto


def test_enmascarar():
    assert enmascarar("ana.perez@empresa.co") == "a***@empresa.co"
    assert enmascarar("sin-arroba") == "***"


# ------------------------------------------------------------------- SMTP


class SmtpFalso:
    def __init__(self):
        self.pasos: list[str] = []
        self.mensajes = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.pasos.append("quit")

    def starttls(self, context=None):
        self.pasos.append("starttls")

    def login(self, usuario, clave):
        self.pasos.append(f"login:{usuario}:{clave}")

    def send_message(self, msg):
        self.pasos.append("send")
        self.mensajes.append(msg)


async def test_smtp_con_starttls_y_login(smtp_configurado, monkeypatch):
    falso = SmtpFalso()
    monkeypatch.setattr(correo, "_smtp", lambda s: falso)
    await enviar(correo_recuperacion("Ana", "ana@empresa.co", ENLACE, 30))
    assert falso.pasos == ["starttls", "login:usuario-smtp:clave-smtp", "send", "quit"]
    (msg,) = falso.mensajes
    assert msg["To"] == "Ana <ana@empresa.co>"
    assert msg["From"].addresses[0].addr_spec == "no-responder@nexus360.co"
    assert msg["Subject"] == "Restablece tu contraseña de NEXUS 360°"
    assert msg["Message-ID"] and msg["Date"]
    # Texto y HTML: los clientes que no muestran HTML ven el enlace igual.
    assert {p.get_content_type() for p in msg.iter_parts()} == {"text/plain", "text/html"}


async def test_smtp_sin_seguridad_ni_login_para_mailpit(smtp_configurado, monkeypatch):
    monkeypatch.setattr(smtp_configurado, "smtp_seguridad", "ninguna")
    monkeypatch.setattr(smtp_configurado, "smtp_usuario", "")
    falso = SmtpFalso()
    monkeypatch.setattr(correo, "_smtp", lambda s: falso)
    await enviar(correo_password_cambiada("Ana", "ana@empresa.co"))
    assert falso.pasos == ["send", "quit"]


async def test_un_nombre_con_saltos_de_linea_no_inyecta_cabeceras(smtp_configurado, monkeypatch):
    falso = SmtpFalso()
    monkeypatch.setattr(correo, "_smtp", lambda s: falso)
    await enviar(correo_recuperacion("Ana\r\nBcc: victima@otro.co", "ana@empresa.co", ENLACE, 30))
    (msg,) = falso.mensajes
    assert msg["Bcc"] is None
    assert "\n" not in msg["To"] and "\r" not in msg["To"]


async def test_smtp_caido_lanza_correo_error(smtp_configurado, monkeypatch):
    def falla(s):
        raise ConnectionRefusedError("no hay servidor")
    monkeypatch.setattr(correo, "_smtp", falla)
    with pytest.raises(CorreoError, match="ConnectionRefusedError"):
        await enviar(correo_recuperacion("Ana", "ana@empresa.co", ENLACE, 30))


async def test_sin_configurar_no_intenta_enviar(sin_correo):
    with pytest.raises(CorreoError, match="no está configurado"):
        await enviar(correo_recuperacion("Ana", "ana@empresa.co", ENLACE, 30))


# ------------------------------------------------------------------ Brevo


def _brevo(monkeypatch, *respuestas):
    peticiones: list[httpx.Request] = []
    pendientes = list(respuestas)

    def manejar(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return pendientes.pop(0)

    monkeypatch.setattr(correo, "_cliente",
                        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(manejar), timeout=timeout))
    return peticiones


async def test_brevo_envia_por_https(brevo_configurado, monkeypatch):
    peticiones = _brevo(monkeypatch, httpx.Response(201, json={"messageId": "<x@brevo>"}))
    await enviar(correo_recuperacion("Ana", "ana@empresa.co", ENLACE, 30))
    (req,) = peticiones
    assert str(req.url) == URL_BREVO and req.method == "POST"
    assert req.headers["api-key"] == CLAVE_BREVO
    cuerpo = json.loads(req.content)
    assert cuerpo["to"] == [{"email": "ana@empresa.co", "name": "Ana"}]
    assert cuerpo["sender"]["email"] == "no-responder@nexus360.co"
    assert ENLACE in cuerpo["textContent"] and ENLACE in cuerpo["htmlContent"]


async def test_brevo_rechaza_lanza_correo_error(brevo_configurado, monkeypatch):
    _brevo(monkeypatch, httpx.Response(401, json={"code": "unauthorized", "message": "Key not found"}))
    with pytest.raises(CorreoError, match="401 unauthorized"):
        await enviar(correo_recuperacion("Ana", "ana@empresa.co", ENLACE, 30))


async def test_en_segundo_plano_un_fallo_se_registra_sin_token_ni_claves(brevo_configurado, monkeypatch, caplog):
    _brevo(monkeypatch, httpx.Response(500, text="error"))
    with caplog.at_level(logging.DEBUG, logger="nexus360"):
        await enviar_sin_fallar(correo_recuperacion("Ana", "ana@empresa.co", ENLACE, 30), "recuperación")
    assert "No se pudo enviar el correo de recuperación a a***@empresa.co" in caplog.text
    for secreto in (TOKEN, CLAVE_BREVO, "ana@empresa.co"):
        assert secreto not in caplog.text


async def test_en_segundo_plano_un_exito_se_registra_sin_token(brevo_configurado, monkeypatch, caplog):
    _brevo(monkeypatch, httpx.Response(201, json={}))
    with caplog.at_level(logging.DEBUG, logger="nexus360"):
        await enviar_sin_fallar(correo_recuperacion("Ana", "ana@empresa.co", ENLACE, 30), "recuperación")
    assert "enviado a a***@empresa.co" in caplog.text and TOKEN not in caplog.text


# ------------------------------------------------------------------ rutas


class ConexionQueNoSeDebeUsar:
    """Cualquier consulta hace fallar la petición con 500 (y la prueba)."""

    def __getattr__(self, nombre):
        raise AssertionError(f"la ruta tocó la base ({nombre})")


class PoolFalso:
    def acquire(self):
        conexion = ConexionQueNoSeDebeUsar()

        class Contexto:
            async def __aenter__(self):
                return conexion

            async def __aexit__(self, *a):
                return False

        return Contexto()


@pytest.fixture
def cliente():
    # get_conn entrega una conexión antes de que corra la ruta; esta revienta
    # si la ruta llega a consultar algo.
    app.state.pool = PoolFalso()
    return TestClient(app, raise_server_exceptions=False)


def test_sin_correo_configurado_responde_503_sin_tocar_la_base(sin_correo, cliente):
    r = cliente.post("/api/auth/recuperar-password", json={"email": "ana@empresa.co"})
    assert r.status_code == 503, r.text
    assert r.json()["codigo"] == "CORREO_NO_CONFIGURADO"


def test_correo_mal_escrito_es_422(smtp_configurado, cliente):
    r = cliente.post("/api/auth/recuperar-password", json={"email": "no-es-un-correo"})
    assert r.status_code == 422 and r.json()["codigo"] == "VALIDACION"


def test_recaptcha_rechaza_antes_de_tocar_la_base(smtp_configurado, cliente, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "recaptcha_secret_key", SecretStr("secreto"))
    monkeypatch.setattr(s, "recaptcha_solo_observar", False)
    monkeypatch.setattr(s, "recaptcha_umbral_recuperacion", 0.5)
    respuesta = httpx.Response(200, json={"success": True, "score": 0.1, "action": "recuperacion"})
    monkeypatch.setattr(recaptcha, "_cliente", lambda timeout: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: respuesta), timeout=timeout))
    r = cliente.post("/api/auth/recuperar-password", json={"email": "ana@empresa.co"},
                     headers={recaptcha.CABECERA: "token-recaptcha"})
    assert r.status_code == 403 and r.json()["codigo"] == "RECAPTCHA"


def test_un_token_de_login_no_sirve_para_recuperar(monkeypatch):
    """Cada acción de reCAPTCHA es independiente."""
    s = get_settings()
    assert recaptcha._umbral(s, "recuperacion") == s.recaptcha_umbral_recuperacion
    assert "recuperacion" in recaptcha.ACCIONES


@pytest.mark.parametrize("token", ["", "abc", "zz" * 32, "ab" * 33, "<script>"])
def test_token_con_formato_invalido_no_llega_a_la_base(cliente, token):
    r = cliente.post("/api/auth/recuperar-password/verificar", json={"token": token})
    assert r.status_code == 200 and r.json() == {"valido": False}
    r = cliente.post("/api/auth/restablecer-password", json={"token": token, "password_nueva": "ClaveNueva123"})
    assert r.status_code == 400 and r.json()["codigo"] == "TOKEN_INVALIDO"


def test_password_nueva_corta_es_422_antes_de_la_base(cliente):
    r = cliente.post("/api/auth/restablecer-password", json={"token": TOKEN, "password_nueva": "corta"})
    assert r.status_code == 422 and r.json()["codigo"] == "VALIDACION"


def test_esquema_de_entrada():
    with pytest.raises(ValidationError):
        RestablecerPasswordIn(token=TOKEN, password_nueva="1234567")
    assert RestablecerPasswordIn(token=TOKEN, password_nueva="12345678").password_nueva == "12345678"
