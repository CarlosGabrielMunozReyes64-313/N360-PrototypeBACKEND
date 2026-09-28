"""Los errores no controlados deben salir con cabeceras CORS: si no, el
navegador los muestra como «No se pudo conectar con el servidor» y el
error real (p. ej. falta aplicar la migración 009) queda escondido."""
import asyncpg
from fastapi.testclient import TestClient

from app.esquema import CODIGO_ESQUEMA
from app.main import app
from app.config import get_settings

ORIGEN = get_settings().cors_origins[0] if get_settings().cors_origins else "http://localhost:5173"


def _con_ruta(path: str, exc: Exception):
    async def falla():
        raise exc
    app.add_api_route(path, falla, methods=["GET"])


def test_esquema_viejo_responde_503_con_cors_y_mensaje_claro():
    _con_ruta("/api/_prueba_esquema", asyncpg.UndefinedColumnError('column "clientes" does not exist'))
    r = TestClient(app, raise_server_exceptions=False).get("/api/_prueba_esquema", headers={"Origin": ORIGEN})
    assert r.status_code == 503
    assert r.headers.get("access-control-allow-origin") == ORIGEN
    assert r.json()["codigo"] == CODIGO_ESQUEMA
    assert "009_rse_express.sql" in r.json()["mensaje"]


def test_error_generico_responde_500_con_cors():
    _con_ruta("/api/_prueba_error", RuntimeError("fallo inesperado"))
    r = TestClient(app, raise_server_exceptions=False).get("/api/_prueba_error", headers={"Origin": ORIGEN})
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == ORIGEN
    assert r.json() == {"codigo": "DESCONOCIDO", "mensaje": "Error interno del servidor."}
