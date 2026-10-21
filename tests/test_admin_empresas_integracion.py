"""«Datos de empresa» (GET /api/admin/empresas) con la base real.

Comprueba que la lista devuelve el contacto de cada empresa y que una
empresa deja de aparecer cuando se eliminan todas sus cuentas (y vuelve si
se restaura alguna).

Son opcionales porque crean cuentas y empresas en la base configurada, y
necesitan la conexión del dueño del esquema para crear el admin de prueba:

    N360_PRUEBAS_DB=1 N360_DB_DUENO=postgresql://postgres@localhost/nexus360 \\
        pytest tests/test_admin_empresas_integracion.py
"""
import asyncio
import os
import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import POLITICA_DATOS_VERSION

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("N360_PRUEBAS_DB") != "1",
        reason="Pruebas con base de datos: activar con N360_PRUEBAS_DB=1",
    ),
    pytest.mark.skipif(not os.environ.get("N360_DB_DUENO"), reason="Requiere N360_DB_DUENO"),
]

PESOS_DV = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]


def _dv(nit: str) -> str:
    s = sum(int(d) * p for d, p in zip(reversed(nit), PESOS_DV))
    r = s % 11
    return str(r if r < 2 else 11 - r)


@pytest.fixture(scope="module")
def cliente():
    # El registro guarda la IP como inet: el host ficticio «testclient» no sirve.
    with TestClient(app, client=("127.0.0.1", 50001)) as c:
        yield c


def _registrar(cliente: TestClient, prefijo: str, nombre: str) -> dict:
    sufijo = uuid.uuid4().hex[:8]
    email = f"{prefijo}_{sufijo}@prueba.co"
    r = cliente.post("/api/auth/register", json={
        "email": email, "nombre": nombre, "password": "ClaveSegura123", "rol": "empresa",
        "acepta_politica_datos": True, "politica_datos_version": POLITICA_DATOS_VERSION,
    })
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    return {
        "email": email, "nombre": nombre, "id": cuerpo["usuario"]["usuario_id"],
        "h": {"Authorization": f"Bearer {cuerpo['token']}"}, "sufijo": sufijo,
    }


def _crear_empresa(cliente: TestClient, cuenta: dict) -> str:
    """La cuenta registra su empresa (perfil + tamizaje). Devuelve la razón social."""
    nit = str(900_000_000 + int(cuenta["sufijo"], 16) % 99_999_999)
    razon = f"Empresa Admin Lista {cuenta['sufijo']}"
    r = cliente.put("/api/empresa/mio", headers=cuenta["h"], json={
        "razon_social": razon, "nit": nit, "dv": _dv(nit), "sector_id": "servicios",
        "municipio": "Candelaria", "departamento": "Valle del Cauca", "tamano": "pequena", "personas": 20,
        "vinculacion": ["laboral"], "zonas": ["barrios"], "vecinos": "Colegio al frente", "clientes": "mezcla",
    })
    assert r.status_code == 200, r.text
    return razon


def _hacer_admin(usuario_id: str) -> None:
    async def correr():
        conn = await asyncpg.connect(os.environ["N360_DB_DUENO"])
        try:
            await conn.execute("UPDATE nexus360.usuario SET rol = 'admin' WHERE usuario_id = $1", uuid.UUID(usuario_id))
        finally:
            await conn.close()
    asyncio.run(correr())


def _lista(cliente: TestClient, admin: dict) -> dict[str, dict]:
    r = cliente.get("/api/admin/empresas", headers=admin["h"])
    assert r.status_code == 200, r.text
    return {e["razon_social"]: e for e in r.json()}


def test_contacto_y_empresas_con_cuentas_eliminadas(cliente):
    admin = _registrar(cliente, "admin_lista", "Admin Lista")
    _hacer_admin(admin["id"])

    sola = _registrar(cliente, "sola", "Cuenta Sola")
    empresa_sola = _crear_empresa(cliente, sola)
    otra = _registrar(cliente, "otra", "Cuenta Otra")
    empresa_otra = _crear_empresa(cliente, otra)

    # Las dos aparecen, cada una con su contacto.
    lista = _lista(cliente, admin)
    assert lista[empresa_sola]["contacto_nombre"] == "Cuenta Sola"
    assert lista[empresa_sola]["contacto_email"] == sola["email"]
    assert lista[empresa_otra]["contacto_email"] == otra["email"]

    # Se elimina la única cuenta de una: se archiva (tiene empresa) y la
    # empresa sale de la lista. La otra sigue.
    r = cliente.delete(f"/api/admin/usuarios/{sola['id']}", headers=admin["h"])
    assert r.status_code == 200, r.text
    assert r.json()["modo"] == "archivado"
    lista = _lista(cliente, admin)
    assert empresa_sola not in lista
    assert empresa_otra in lista

    # Desactivar (no eliminar) no la saca de la lista.
    r = cliente.patch(f"/api/admin/usuarios/{otra['id']}/estado", headers=admin["h"], json={"activo": False})
    assert r.status_code == 200, r.text
    assert empresa_otra in _lista(cliente, admin)

    # Al restaurar la cuenta, la empresa vuelve con su contacto.
    r = cliente.post(f"/api/admin/usuarios/{sola['id']}/restaurar", headers=admin["h"])
    assert r.status_code == 200, r.text
    lista = _lista(cliente, admin)
    assert lista[empresa_sola]["contacto_email"] == sola["email"]
