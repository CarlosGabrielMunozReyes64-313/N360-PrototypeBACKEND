"""Prueba de contrato: la API expone las rutas que el frontend llama.

No necesita base de datos: solo construye la app y lee su OpenAPI. Es la
prueba más barata del repo y atrapa la clase de error más silenciosa que
hay aquí — un router que existe pero que nadie registró en app/main.py.
"""

import pytest

from app.main import app

# Cada entrada es (método, ruta) tal como la llama el frontend.
# Fuente: src/auth/api.ts, src/auth/adminApi.ts, src/auth/empresaApi.ts,
# src/auth/analisisIaApi.ts,
# src/perfil/fotoCache.ts
RUTAS_QUE_USA_EL_FRONT = [
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/me"),
    ("GET", "/api/empresa/mio"),
    ("PUT", "/api/empresa/mio"),
    ("PUT", "/api/empresa/mio/diagnosticos/{formato_id}/respuestas"),
    ("POST", "/api/empresa/mio/diagnosticos/{formato_id}/analisis-ia"),
    ("PATCH", "/api/auth/me"),
    ("POST", "/api/auth/change-password"),
    ("PUT", "/api/auth/me/foto"),
    ("DELETE", "/api/auth/me/foto"),
    ("GET", "/api/usuarios/{usuario_id}/foto"),
    ("GET", "/api/admin/estadisticas"),
    ("GET", "/api/admin/empresas"),
    ("GET", "/api/admin/empresas/{empresa_id}/diagnostico"),
    ("PUT", "/api/admin/respuestas/{respuesta_id}/clasificacion"),
]


@pytest.fixture(scope="module")
def rutas_expuestas() -> set[tuple[str, str]]:
    esquema = app.openapi()
    return {
        (metodo.upper(), ruta)
        for ruta, metodos in esquema["paths"].items()
        for metodo in metodos
    }


@pytest.mark.parametrize("metodo,ruta", RUTAS_QUE_USA_EL_FRONT)
def test_la_ruta_existe(metodo: str, ruta: str, rutas_expuestas: set[tuple[str, str]]):
    assert (metodo, ruta) in rutas_expuestas, (
        f"El frontend llama {metodo} {ruta} pero la API no la expone. "
        f"¿Falta un include_router en app/main.py?"
    )


def test_todos_los_routers_estan_registrados():
    """Si existe un módulo en app/routers/ con un `router`, debe estar montado."""
    import importlib
    import pkgutil

    import app.routers as paquete

    prefijos_montados = set(app.openapi()["paths"])

    faltantes = []
    for info in pkgutil.iter_modules(paquete.__path__):
        modulo = importlib.import_module(f"app.routers.{info.name}")
        router = getattr(modulo, "router", None)
        if router is None:
            continue
        prefijo = f"/api{router.prefix}"
        if not any(r.startswith(prefijo) for r in prefijos_montados):
            faltantes.append(f"app.routers.{info.name} (prefijo {prefijo})")

    assert not faltantes, (
        "Estos routers existen pero no están registrados en app/main.py: "
        + ", ".join(faltantes)
    )
