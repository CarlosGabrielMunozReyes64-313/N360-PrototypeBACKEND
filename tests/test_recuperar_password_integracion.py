"""Recuperación de contraseña (013) de punta a punta, con la base real.

Los correos no salen: se atrapan reemplazando la tarea de envío, y de ahí se
saca el enlace igual que lo haría la persona desde su bandeja.

Opcionales, como las demás pruebas de integración (crean cuentas en la base
configurada). Algunas necesitan la conexión del dueño del esquema para
simular cosas que la API no permite (vencer un enlace, desactivar una cuenta):

    N360_PRUEBAS_DB=1 N360_DB_DUENO=postgresql://postgres@localhost/nexus360 \\
        pytest tests/test_recuperar_password_integracion.py
"""
import asyncio
import os
import random
import re
import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.routers import auth as rutas_auth
from app.schemas import POLITICA_DATOS_VERSION

pytestmark = pytest.mark.skipif(
    os.environ.get("N360_PRUEBAS_DB") != "1",
    reason="Pruebas con base de datos: activar con N360_PRUEBAS_DB=1",
)
requiere_dueno = pytest.mark.skipif(not os.environ.get("N360_DB_DUENO"), reason="Requiere N360_DB_DUENO")

ENLACE_RE = re.compile(r"/#/restablecer\?token=([0-9a-f]{64})")
CLAVE_VIEJA = "ClaveVieja123"
CLAVE_NUEVA = "ClaveNueva456"


@pytest.fixture(scope="module")
def cliente():
    # El registro guarda la IP como inet: el host ficticio «testclient» no sirve.
    with TestClient(app, client=("127.0.0.1", 50002)) as c:
        yield c


@pytest.fixture
def buzon(monkeypatch):
    """Activa el correo y atrapa lo que se «enviaría» en lugar de mandarlo."""
    s = get_settings()
    monkeypatch.setattr(s, "correo_proveedor", "smtp")
    monkeypatch.setattr(s, "correo_remitente", "no-responder@nexus360.co")
    monkeypatch.setattr(s, "frontend_url", "https://n360.prueba.co/")
    enviados = []

    async def atrapar(correo, que):
        enviados.append(correo)

    monkeypatch.setattr(rutas_auth, "enviar_sin_fallar", atrapar)
    return enviados


@pytest.fixture
def ip():
    """IP propia por prueba (vía X-Forwarded-For): el límite de 10 enlaces por
    IP y hora no debe cruzarse entre pruebas."""
    return {"X-Forwarded-For": f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"}


def _registrar(cliente: TestClient) -> dict:
    email = f"recup_{uuid.uuid4().hex[:10]}@prueba.co"
    r = cliente.post("/api/auth/register", json={
        "email": email, "nombre": "Ana Prueba", "password": CLAVE_VIEJA, "rol": "empresa",
        "acepta_politica_datos": True, "politica_datos_version": POLITICA_DATOS_VERSION,
    })
    assert r.status_code == 201, r.text
    return {"email": email, "id": r.json()["usuario"]["usuario_id"],
            "h": {"Authorization": f"Bearer {r.json()['token']}"}}


def _pedir(cliente, email, ip):
    r = cliente.post("/api/auth/recuperar-password", json={"email": email}, headers=ip)
    assert r.status_code == 202, r.text
    return r.json()


def _token(correo) -> str:
    m = ENLACE_RE.search(correo.texto)
    assert m, correo.texto
    assert ENLACE_RE.search(correo.html)
    return m.group(1)


def _login(cliente, email, clave):
    return cliente.post("/api/auth/login", json={"email": email, "password": clave})


def _verificar(cliente, token) -> bool:
    r = cliente.post("/api/auth/recuperar-password/verificar", json={"token": token})
    assert r.status_code == 200, r.text
    return r.json()["valido"]


def _restablecer(cliente, token, clave=CLAVE_NUEVA):
    return cliente.post("/api/auth/restablecer-password", json={"token": token, "password_nueva": clave})


def _dueno(sql: str, *args):
    async def correr():
        conn = await asyncpg.connect(os.environ["N360_DB_DUENO"])
        try:
            return await conn.execute(sql, *args)
        finally:
            await conn.close()
    return asyncio.run(correr())


# ------------------------------------------------------------- flujo feliz


def test_flujo_completo(cliente, buzon, ip):
    cuenta = _registrar(cliente)
    otra_sesion = {"Authorization": f"Bearer {_login(cliente, cuenta['email'], CLAVE_VIEJA).json()['token']}"}

    respuesta = _pedir(cliente, cuenta["email"].upper(), ip)  # el correo no distingue mayúsculas
    assert len(buzon) == 1
    correo = buzon[0]
    assert correo.destinatario == cuenta["email"]
    # El enlace sale de FRONTEND_URL (sin la barra final), nunca de la petición.
    assert "https://n360.prueba.co/#/restablecer?token=" in correo.texto
    token = _token(correo)

    assert _verificar(cliente, token) is True
    assert _verificar(cliente, token) is True  # verificar no gasta el token

    r = _restablecer(cliente, token)
    assert r.status_code == 204, r.text

    # Aviso de «tu contraseña cambió» al mismo buzón.
    assert len(buzon) == 2 and "cambió" in buzon[1].asunto
    assert buzon[1].destinatario == cuenta["email"]

    # Todas las sesiones anteriores quedaron cerradas.
    for h in (cuenta["h"], otra_sesion):
        assert cliente.get("/api/auth/me", headers=h).status_code == 401

    assert _login(cliente, cuenta["email"], CLAVE_VIEJA).status_code == 401
    assert _login(cliente, cuenta["email"], CLAVE_NUEVA).status_code == 200

    # El enlace sirve una sola vez.
    assert _verificar(cliente, token) is False
    r = _restablecer(cliente, token, "OtraClave789")
    assert r.status_code == 400 and r.json()["codigo"] == "TOKEN_INVALIDO"
    assert respuesta["mensaje"].startswith("Si el correo está registrado")


# ------------------------------------------------ no revela qué correos existen


def test_correo_inexistente_responde_igual_y_no_envia_nada(cliente, buzon, ip):
    cuenta = _registrar(cliente)
    con_cuenta = _pedir(cliente, cuenta["email"], ip)
    sin_cuenta = _pedir(cliente, f"nadie_{uuid.uuid4().hex[:8]}@prueba.co", ip)
    assert con_cuenta == sin_cuenta
    assert [c.destinatario for c in buzon] == [cuenta["email"]]


# ------------------------------------------------------------------ límites


def test_maximo_tres_enlaces_por_cuenta_y_hora(cliente, buzon, ip):
    cuenta = _registrar(cliente)
    respuestas = [_pedir(cliente, cuenta["email"], ip) for _ in range(5)]
    assert len(buzon) == 3
    assert len({r["mensaje"] for r in respuestas}) == 1  # el cuarto y quinto no se distinguen


def test_maximo_diez_enlaces_por_ip_y_hora(cliente, buzon, ip):
    cuentas = [_registrar(cliente) for _ in range(11)]
    for c in cuentas:
        _pedir(cliente, c["email"], ip)
    assert len(buzon) == 10
    # Desde otra IP, la cuenta número 11 sí recibe su enlace.
    _pedir(cliente, cuentas[-1]["email"], {"X-Forwarded-For": "10.250.250.250"})
    assert len(buzon) == 11


def test_una_ip_inventada_no_tumba_la_peticion(cliente, buzon):
    cuenta = _registrar(cliente)
    _pedir(cliente, cuenta["email"], {"X-Forwarded-For": "esto-no-es-una-ip"})
    assert len(buzon) == 1


# ----------------------------------------------- cuándo un enlace deja de servir


def test_pedir_otro_enlace_anula_el_anterior(cliente, buzon, ip):
    cuenta = _registrar(cliente)
    _pedir(cliente, cuenta["email"], ip)
    _pedir(cliente, cuenta["email"], ip)
    viejo, nuevo = _token(buzon[0]), _token(buzon[1])
    assert _verificar(cliente, viejo) is False
    assert _restablecer(cliente, viejo).status_code == 400
    assert _restablecer(cliente, nuevo).status_code == 204


def test_password_corta_no_gasta_el_enlace(cliente, buzon, ip):
    cuenta = _registrar(cliente)
    _pedir(cliente, cuenta["email"], ip)
    token = _token(buzon[0])
    r = _restablecer(cliente, token, "corta")
    assert r.status_code == 422 and r.json()["codigo"] == "VALIDACION"
    assert _verificar(cliente, token) is True
    assert _restablecer(cliente, token).status_code == 204


def test_cambiar_la_password_desde_mi_cuenta_anula_el_enlace(cliente, buzon, ip):
    cuenta = _registrar(cliente)
    _pedir(cliente, cuenta["email"], ip)
    token = _token(buzon[0])
    r = cliente.post("/api/auth/change-password", headers=cuenta["h"],
                     json={"password_actual": CLAVE_VIEJA, "password_nueva": "LaRecorde123"})
    assert r.status_code == 204, r.text
    assert _verificar(cliente, token) is False


def test_cambiar_el_correo_anula_el_enlace(cliente, buzon, ip):
    """El enlace salió hacia el buzón anterior: ya no debe servir."""
    cuenta = _registrar(cliente)
    _pedir(cliente, cuenta["email"], ip)
    token = _token(buzon[0])
    r = cliente.patch("/api/auth/me", headers=cuenta["h"],
                      json={"email": f"nuevo_{uuid.uuid4().hex[:8]}@prueba.co"})
    assert r.status_code == 200, r.text
    assert _verificar(cliente, token) is False


@requiere_dueno
def test_enlace_vencido(cliente, buzon, ip):
    cuenta = _registrar(cliente)
    _pedir(cliente, cuenta["email"], ip)
    token = _token(buzon[0])
    _dueno("UPDATE nexus360.recuperacion_password SET expira_en = now() - interval '1 minute' "
           "WHERE usuario_id = $1", uuid.UUID(cuenta["id"]))
    assert _verificar(cliente, token) is False
    r = _restablecer(cliente, token)
    assert r.status_code == 400 and r.json()["codigo"] == "TOKEN_INVALIDO"


@requiere_dueno
def test_cuenta_desactivada_no_recibe_enlace_ni_puede_usar_uno_pendiente(cliente, buzon, ip):
    cuenta = _registrar(cliente)
    _pedir(cliente, cuenta["email"], ip)
    token = _token(buzon[0])
    _dueno("UPDATE nexus360.usuario SET activo = false WHERE usuario_id = $1", uuid.UUID(cuenta["id"]))
    assert _restablecer(cliente, token).status_code == 400
    _pedir(cliente, cuenta["email"], ip)
    assert len(buzon) == 1


# ---------------------------------------------------- bloqueo y auditoría


def test_restablecer_levanta_el_bloqueo_por_intentos_fallidos(cliente, buzon, ip):
    cuenta = _registrar(cliente)
    for _ in range(5):
        _login(cliente, cuenta["email"], "equivocada")
    assert _login(cliente, cuenta["email"], CLAVE_VIEJA).status_code == 423
    _pedir(cliente, cuenta["email"], ip)
    assert _restablecer(cliente, _token(buzon[0])).status_code == 204
    assert _login(cliente, cuenta["email"], CLAVE_NUEVA).status_code == 200


@requiere_dueno
def test_el_panel_de_admin_muestra_el_motivo_recuperacion(cliente, buzon, ip):
    """El nuevo motivo de cierre debe pasar la validación de la respuesta del
    panel (antes de 013 solo existían logout, admin y eliminacion)."""
    cuenta = _registrar(cliente)
    _pedir(cliente, cuenta["email"], ip)
    assert _restablecer(cliente, _token(buzon[0])).status_code == 204

    admin = _registrar(cliente)
    _dueno("UPDATE nexus360.usuario SET rol = 'admin' WHERE usuario_id = $1", uuid.UUID(admin["id"]))
    r = cliente.get(f"/api/admin/usuarios/{cuenta['id']}/actividad", headers=admin["h"])
    assert r.status_code == 200, r.text
    motivos = {s["revocado_motivo"] for s in r.json()["sesiones"]}
    assert motivos == {"recuperacion"}


# ------------------------------------------------------------ concurrencia


def test_dos_envios_simultaneos_del_mismo_enlace_solo_uno_gana(cliente, buzon, ip):
    """FOR UPDATE en restablecer_password(): con dos conexiones a la vez, la
    segunda espera a la primera y encuentra el token ya usado."""
    cuenta = _registrar(cliente)
    _pedir(cliente, cuenta["email"], ip)
    token = _token(buzon[0])
    url = get_settings().database_url

    async def correr():
        c1 = await asyncpg.connect(url)
        c2 = await asyncpg.connect(url)
        try:
            t1 = c1.transaction()
            await t1.start()
            await c1.fetchrow("SELECT * FROM nexus360.restablecer_password($1, $2)", token, "PrimeraClave1")
            # La segunda queda esperando el candado de la primera...
            segunda = asyncio.create_task(
                c2.fetchrow("SELECT * FROM nexus360.restablecer_password($1, $2)", token, "SegundaClave2"))
            await asyncio.sleep(0.3)
            assert not segunda.done()
            await t1.commit()
            # ...y al soltarse, el token ya está usado.
            with pytest.raises(asyncpg.RaiseError, match="no es válido o ya expiró"):
                await segunda
        finally:
            await c1.close()
            await c2.close()

    asyncio.run(correr())
    assert _login(cliente, cuenta["email"], "PrimeraClave1").status_code == 200
    assert _login(cliente, cuenta["email"], "SegundaClave2").status_code == 401


# ------------------------------------------------------------ /health


def test_el_backend_detecta_la_migracion_aunque_no_tenga_permisos_sobre_la_tabla():
    """nexus360_app no tiene NINGÚN privilegio sobre recuperacion_password, y
    information_schema solo muestra tablas con algún privilegio: con esa
    consulta /health decía «falta_013» aunque la migración estuviera aplicada."""
    from app.esquema import verificar_esquema

    async def correr():
        pool = await asyncpg.create_pool(get_settings().database_url, min_size=1, max_size=1)
        try:
            return await verificar_esquema(pool)
        finally:
            await pool.close()

    assert asyncio.run(correr())["recuperacion_password"] is True
