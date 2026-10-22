"""reCAPTCHA v3 en registro e inicio de sesión. Sin red ni base: la API
SiteVerify de Google se simula con httpx.MockTransport."""
import logging
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import recaptcha
from app.config import get_settings
from app.errors import ApiError
from app.main import app
from app.recaptcha import CABECERA, URL_SITEVERIFY, verificar

SECRETO = "6Lc-secreto-de-prueba-que-no-debe-salir-en-logs"
TOKEN = "token-del-navegador-que-no-debe-salir-en-logs"


class Google:
    """Simula SiteVerify: devuelve en orden las respuestas dadas."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.peticiones: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.peticiones.append(request)
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def campos(self, i=0) -> dict:
        return {k: v[0] for k, v in parse_qs(self.peticiones[i].content.decode()).items()}


def ok(score=0.9, action="registro", success=True, **extra):
    return httpx.Response(200, json={"success": success, "score": score, "action": action,
                                     "hostname": "localhost", **extra})


@pytest.fixture
def ajustes(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "recaptcha_secret_key", SecretStr(SECRETO))
    monkeypatch.setattr(s, "recaptcha_solo_observar", False)
    monkeypatch.setattr(s, "recaptcha_umbral_registro", 0.5)
    monkeypatch.setattr(s, "recaptcha_umbral_login", 0.3)
    return s


@pytest.fixture
def google(monkeypatch):
    def instalar(*respuestas) -> Google:
        g = Google(*respuestas)
        monkeypatch.setattr(recaptcha, "_cliente",
                            lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(g), timeout=timeout))
        return g
    return instalar


async def _rechaza(token, accion, ip="1.2.3.4"):
    with pytest.raises(ApiError) as exc:
        await verificar(token, accion, ip)
    assert exc.value.status_code == 403 and exc.value.codigo == "RECAPTCHA"
    return exc.value


# ------------------------------------------------------------- verificación


async def test_sin_clave_secreta_queda_apagado(monkeypatch, google):
    monkeypatch.setattr(get_settings(), "recaptcha_secret_key", None)
    g = google()
    await verificar(None, "registro", "1.2.3.4")  # no lanza
    assert g.peticiones == []


async def test_puntaje_suficiente_pasa_y_manda_secreto_token_e_ip(ajustes, google):
    g = google(ok(0.9, "registro"))
    await verificar(TOKEN, "registro", "1.2.3.4")
    (req,) = g.peticiones
    assert str(req.url) == URL_SITEVERIFY and req.method == "POST"
    assert g.campos() == {"secret": SECRETO, "response": TOKEN, "remoteip": "1.2.3.4"}


async def test_sin_token_rechaza_sin_llamar_a_google(ajustes, google):
    g = google()
    e = await _rechaza(None, "login")
    assert "bloqueador de anuncios" in e.mensaje
    assert g.peticiones == []


@pytest.mark.parametrize("respuesta,accion", [
    (ok(0.3, "registro"), "registro"),                                   # bajo el umbral de registro
    (ok(0.2, "login"), "login"),                                         # bajo el umbral de login
    (ok(0.9, "login"), "registro"),                                      # token de otra acción
    (ok(success=False, score=None, action=None, **{"error-codes": ["timeout-or-duplicate"]}), "registro"),
    (httpx.Response(200, json={"success": True, "action": "login"}), "login"),  # sin puntaje
])
async def test_rechazos(ajustes, google, respuesta, accion):
    google(respuesta)
    await _rechaza(TOKEN, accion)


async def test_el_login_es_mas_tolerante_que_el_registro(ajustes, google):
    google(ok(0.4, "login"), ok(0.4, "registro"))
    await verificar(TOKEN, "login", None)
    await _rechaza(TOKEN, "registro")


async def test_solo_observar_registra_pero_no_bloquea(ajustes, google, monkeypatch, caplog):
    monkeypatch.setattr(ajustes, "recaptcha_solo_observar", True)
    google(ok(0.1, "registro"))
    with caplog.at_level(logging.WARNING, logger="nexus360"):
        await verificar(TOKEN, "registro", None)
    assert "habría rechazado registro" in caplog.text


@pytest.mark.parametrize("falla", [httpx.ConnectError("sin red"), httpx.Response(500, text="error"),
                                   httpx.Response(200, text="no es json")])
async def test_si_google_falla_deja_pasar_y_avisa(ajustes, google, falla, caplog):
    google(falla)
    with caplog.at_level(logging.WARNING, logger="nexus360"):
        await verificar(TOKEN, "login", None)
    assert "se deja pasar" in caplog.text


async def test_secreto_y_token_nunca_van_al_log(ajustes, google, caplog):
    google(ok(0.1, "login"), ok(0.9, "login"))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ApiError):
            await verificar(TOKEN, "login", None)
        await verificar(TOKEN, "login", None)
    assert SECRETO not in caplog.text and TOKEN not in caplog.text


# --------------------------------------------------------------- las rutas


@pytest.fixture
def cliente():
    app.state.pool = None  # si la ruta llegara a pedir una conexión, fallaría con 500
    return TestClient(app, raise_server_exceptions=False)


REGISTRO = {"email": "ana@empresa.co", "nombre": "Ana", "password": "una-clave-larga",
            "rol": "empresa", "acepta_politica_datos": True, "politica_datos_version": "1.0"}


@pytest.mark.parametrize("ruta,cuerpo", [("/api/auth/register", REGISTRO),
                                         ("/api/auth/login", {"email": "ana@empresa.co", "password": "x"})])
def test_ruta_rechazada_antes_de_tocar_la_base(ajustes, google, cliente, ruta, cuerpo):
    accion = "registro" if "register" in ruta else "login"
    g = google(ok(0.0, accion))
    r = cliente.post(ruta, json=cuerpo, headers={CABECERA: TOKEN})
    assert r.status_code == 403, r.text
    assert r.json()["codigo"] == "RECAPTCHA"
    assert g.campos()["response"] == TOKEN


def test_ruta_sin_cabecera_rechazada(ajustes, google, cliente):
    google()
    r = cliente.post("/api/auth/login", json={"email": "ana@empresa.co", "password": "x"})
    assert r.status_code == 403 and r.json()["codigo"] == "RECAPTCHA"

