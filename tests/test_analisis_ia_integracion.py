"""Integración del análisis IA con la base real (RLS, persistencia,
reutilización) y la API completa. Gemini se simula: estas pruebas nunca
llaman a Google ni gastan cuota.

Son opcionales porque crean cuentas y empresas en la base configurada:

    N360_PRUEBAS_DB=1 pytest tests/test_analisis_ia_integracion.py

Para la prueba de «migración 010 sin aplicar» hace falta además la conexión
del dueño del esquema:  N360_DB_DUENO=postgresql://postgres@localhost/nexus360
"""
import asyncio
import os
import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.schemas import POLITICA_DATOS_VERSION
from app.ia.gemini_service import IANoDisponible
from app.ia.schemas import AnalisisIA
from app.main import app
from app.routers import empresa as router_empresa

from test_analisis_ia import analisis_ejemplo, resultados_ejemplo

pytestmark = pytest.mark.skipif(
    os.environ.get("N360_PRUEBAS_DB") != "1",
    reason="Pruebas con base de datos: activar con N360_PRUEBAS_DB=1",
)

RUTA = "/api/empresa/mio/diagnosticos/rse_express/analisis-ia"
PESOS_DV = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]


def _dv(nit: str) -> str:
    s = sum(int(d) * p for d, p in zip(reversed(nit), PESOS_DV))
    r = s % 11
    return str(r if r < 2 else 11 - r)


class GeminiFalso:
    modelo = "gemini-prueba"

    def __init__(self, falla: bool = False):
        self.llamadas = 0
        self.falla = falla
        self.contextos: list[dict] = []

    async def analizar(self, contexto, materias_aplicables):
        self.llamadas += 1
        self.contextos.append(contexto)
        if self.falla:
            raise IANoDisponible()
        return AnalisisIA(**analisis_ejemplo())


@pytest.fixture(scope="module")
def cliente():
    # El registro guarda la IP como inet: el host ficticio «testclient» no sirve.
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        yield c


def _cuenta(cliente: TestClient) -> dict:
    """Registra una cuenta con empresa, tamizaje y algunas respuestas."""
    sufijo = uuid.uuid4().hex[:8]
    r = cliente.post("/api/auth/register", json={
        "email": f"ia_{sufijo}@prueba.co", "nombre": "Prueba IA", "password": "ClaveSegura123", "rol": "empresa",
        "acepta_politica_datos": True, "politica_datos_version": POLITICA_DATOS_VERSION,
    })
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    nit = str(900_000_000 + int(sufijo, 16) % 99_999_999)
    r = cliente.put("/api/empresa/mio", headers=h, json={
        "razon_social": f"Empresa Secreta {sufijo}", "nit": nit, "dv": _dv(nit), "sector_id": "agroindustrial",
        "municipio": "Pasto", "departamento": "Nariño", "tamano": "pequena", "personas": 32,
        "vinculacion": ["laboral"], "zonas": ["veredas", "campesinos"], "clientes": "mezcla",
    })
    assert r.status_code == 200, r.text
    return {"h": h, "nit": nit, "razon": f"Empresa Secreta {sufijo}"}


def _responder(cliente: TestClient, h: dict):
    r = cliente.put("/api/empresa/mio/diagnosticos/rse_express/respuestas", headers=h, json={
        "respuestas": {"01a": {"texto": "Lo decide la gerencia", "etapa": "3"}, "03b": {"etapa": "0"}},
        "fortalecer": {"03": "Capacitar al equipo"},
    })
    assert r.status_code == 200, r.text


def _sql_como(usuario_token: str, consulta: str):
    """Consulta como el rol de aplicación, con la sesión de ese usuario (RLS)."""
    async def correr():
        conn = await asyncpg.connect(get_settings().database_url)
        try:
            async with conn.transaction():
                uid = await conn.fetchval("SELECT nexus360.validar_sesion($1)", usuario_token)
                await conn.execute("SELECT set_config('app.current_usuario_id', $1, true)", str(uid))
                return await conn.fetchval(consulta)
        finally:
            await conn.close()
    return asyncio.run(correr())


def test_flujo_completo_generar_reutilizar_y_regenerar(cliente, monkeypatch):
    gemini = GeminiFalso()
    monkeypatch.setattr(router_empresa, "obtener_servicio", lambda _s: gemini)
    cuenta = _cuenta(cliente)
    h = cuenta["h"]
    cuerpo = {"resultados": resultados_ejemplo()}

    # Sin autodiagnóstico guardado todavía: no hay nada que analizar.
    r = cliente.post(RUTA, headers=h, json=cuerpo)
    assert r.status_code == 422 and r.json()["codigo"] == "SIN_DIAGNOSTICO" and gemini.llamadas == 0

    _responder(cliente, h)

    # 1) Primera vez: se genera y se guarda.
    r = cliente.post(RUTA, headers=h, json=cuerpo)
    assert r.status_code == 200, r.text
    primero = r.json()
    assert primero["reutilizado"] is False and primero["modelo"] == "gemini-prueba"
    assert primero["analisis"]["recomendaciones"][0]["materia"] == "03"
    assert gemini.llamadas == 1

    # Gemini recibió el contexto de la organización leído de la base, sin
    # razón social ni NIT.
    enviado = str(gemini.contextos[0])
    assert "Agroindustrial" in enviado and "Pasto, Nariño" in enviado
    assert cuenta["razon"] not in enviado and cuenta["nit"] not in enviado

    # 2) Recargar la página: mismo resultado → se reutiliza, sin llamar a Gemini.
    r = cliente.post(RUTA, headers=h, json=cuerpo)
    assert r.json()["reutilizado"] is True and r.json()["generado_en"] == primero["generado_en"]
    assert gemini.llamadas == 1

    # 3) Cambian los resultados → se regenera una sola vez.
    otro = {"resultados": resultados_ejemplo(comentario_final="Ahora también reciclamos.")}
    assert cliente.post(RUTA, headers=h, json=otro).json()["reutilizado"] is False
    assert cliente.post(RUTA, headers=h, json=otro).json()["reutilizado"] is True
    assert gemini.llamadas == 2
    assert _sql_como(h["Authorization"][7:], "SELECT count(*) FROM nexus360.diagnostico_analisis_ia") == 1


def test_gemini_caido_o_sin_clave_no_rompe_nada(cliente, monkeypatch):
    cuenta = _cuenta(cliente)
    h = cuenta["h"]
    _responder(cliente, h)
    cuerpo = {"resultados": resultados_ejemplo()}

    # Gemini falla: 503 con mensaje amable, sin detalles internos.
    monkeypatch.setattr(router_empresa, "obtener_servicio", lambda _s: GeminiFalso(falla=True))
    r = cliente.post(RUTA, headers=h, json=cuerpo)
    assert r.status_code == 503
    assert r.json() == {"codigo": "IA_NO_DISPONIBLE", "mensaje": IANoDisponible.mensaje}

    # El resto de la aplicación sigue funcionando.
    assert cliente.get("/api/empresa/mio", headers=h).status_code == 200
    _responder(cliente, h)

    # Sin API Key: aviso claro, sin tocar a Gemini.
    monkeypatch.undo()
    monkeypatch.setattr(router_empresa, "get_settings", lambda: Settings(gemini_api_key=None))
    r = cliente.post(RUTA, headers=h, json=cuerpo)
    assert r.status_code == 503 and r.json()["codigo"] == "IA_NO_CONFIGURADA"

    # Pero si ya había un análisis guardado para esos resultados, se sigue
    # mostrando aunque hoy no haya clave.
    gemini = GeminiFalso()
    monkeypatch.setattr(router_empresa, "get_settings", get_settings)
    monkeypatch.setattr(router_empresa, "obtener_servicio", lambda _s: gemini)
    assert cliente.post(RUTA, headers=h, json=cuerpo).status_code == 200
    monkeypatch.setattr(router_empresa, "get_settings", lambda: Settings(gemini_api_key=None))
    r = cliente.post(RUTA, headers=h, json=cuerpo)
    assert r.status_code == 200 and r.json()["reutilizado"] is True


def test_cada_empresa_solo_ve_su_analisis(cliente, monkeypatch):
    monkeypatch.setattr(router_empresa, "obtener_servicio", lambda _s: GeminiFalso())
    a, b = _cuenta(cliente), _cuenta(cliente)
    _responder(cliente, a["h"])
    assert cliente.post(RUTA, headers=a["h"], json={"resultados": resultados_ejemplo()}).status_code == 200
    consulta = "SELECT count(*) FROM nexus360.diagnostico_analisis_ia"
    assert _sql_como(a["h"]["Authorization"][7:], consulta) == 1
    assert _sql_como(b["h"]["Authorization"][7:], consulta) == 0


def test_validaciones_de_la_ruta(cliente):
    cuerpo = {"resultados": resultados_ejemplo()}
    assert cliente.post(RUTA, json=cuerpo).status_code == 401
    h = _cuenta(cliente)["h"]
    assert cliente.post(RUTA.replace("rse_express", "iso26000"), headers=h, json=cuerpo).status_code == 410
    malo = {"resultados": {**resultados_ejemplo(), "score": 3.2}}
    r = cliente.post(RUTA, headers=h, json=malo)
    assert r.status_code == 422 and r.json()["codigo"] == "VALIDACION"


@pytest.mark.skipif(not os.environ.get("N360_DB_DUENO"), reason="Requiere N360_DB_DUENO")
def test_sin_migracion_010_responde_no_disponible(cliente, monkeypatch, caplog):
    monkeypatch.setattr(router_empresa, "obtener_servicio", lambda _s: GeminiFalso())
    h = _cuenta(cliente)["h"]
    _responder(cliente, h)

    async def renombrar(de, a):
        conn = await asyncpg.connect(os.environ["N360_DB_DUENO"])
        try:
            await conn.execute(f"ALTER TABLE nexus360.{de} RENAME TO {a}")
        finally:
            await conn.close()

    asyncio.run(renombrar("diagnostico_analisis_ia", "diagnostico_analisis_ia_tmp"))
    try:
        r = cliente.post(RUTA, headers=h, json={"resultados": resultados_ejemplo()})
    finally:
        asyncio.run(renombrar("diagnostico_analisis_ia_tmp", "diagnostico_analisis_ia"))
    assert r.status_code == 503 and r.json()["codigo"] == "IA_NO_DISPONIBLE"
    assert "010_analisis_ia.sql" in caplog.text


def test_registro_guarda_la_prueba_de_la_autorizacion(cliente):
    base = {"nombre": "Prueba Datos", "password": "ClaveSegura123", "rol": "empresa"}

    # Sin autorización (o con una versión vieja de la política) no se crea la cuenta.
    correo = f"datos_{uuid.uuid4().hex[:8]}@prueba.co"
    r = cliente.post("/api/auth/register", json={**base, "email": correo})
    assert r.status_code == 422 and "autorizar el tratamiento" in r.json()["mensaje"]
    r = cliente.post("/api/auth/register", json={
        **base, "email": correo, "acepta_politica_datos": True, "politica_datos_version": "2020-01-01"})
    assert r.status_code == 422
    r = cliente.post("/api/auth/login", json={"email": correo, "password": base["password"]})
    assert r.status_code == 401  # la cuenta no existe

    # Con autorización: la cuenta y su prueba quedan juntas.
    r = cliente.post("/api/auth/register", json={
        **base, "email": correo, "acepta_politica_datos": True, "politica_datos_version": POLITICA_DATOS_VERSION,
    }, headers={"User-Agent": "Navegador de prueba"})
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    fila = _sql_como(token, "SELECT row_to_json(c) FROM nexus360.consentimiento_datos c")
    import json
    c = json.loads(fila)
    assert c["politica_version"] == POLITICA_DATOS_VERSION
    assert c["ip_origen"] == "127.0.0.1" and c["user_agent"] == "Navegador de prueba"
    assert c["aceptado_en"]

    # Cada quien ve solo su propia autorización.
    otro = _cuenta(cliente)["h"]["Authorization"][7:]
    assert _sql_como(otro, "SELECT count(*) FROM nexus360.consentimiento_datos") == 1


@pytest.mark.skipif(not os.environ.get("N360_DB_DUENO"), reason="Requiere N360_DB_DUENO")
def test_sin_migracion_011_no_se_crean_cuentas_sin_autorizacion(cliente, caplog):
    async def renombrar(de, a):
        conn = await asyncpg.connect(os.environ["N360_DB_DUENO"])
        try:
            await conn.execute(f"ALTER TABLE nexus360.{de} RENAME TO {a}")
        finally:
            await conn.close()

    correo = f"sin011_{uuid.uuid4().hex[:8]}@prueba.co"
    asyncio.run(renombrar("consentimiento_datos", "consentimiento_datos_tmp"))
    try:
        r = cliente.post("/api/auth/register", json={
            "email": correo, "nombre": "Sin 011", "password": "ClaveSegura123", "rol": "empresa",
            "acepta_politica_datos": True, "politica_datos_version": POLITICA_DATOS_VERSION,
        })
    finally:
        asyncio.run(renombrar("consentimiento_datos_tmp", "consentimiento_datos"))
    assert r.status_code == 503 and "mantenimiento" in r.json()["mensaje"]
    assert "011_consentimiento_datos.sql" in caplog.text
    # La cuenta no quedó creada a medias.
    assert cliente.post("/api/auth/login", json={"email": correo, "password": "ClaveSegura123"}).status_code == 401
