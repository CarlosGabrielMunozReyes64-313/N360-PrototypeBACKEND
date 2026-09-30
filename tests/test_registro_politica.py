"""El registro exige la autorización de tratamiento de datos (Ley 1581)."""
import pytest
from pydantic import ValidationError

from app.schemas import POLITICA_DATOS_VERSION, RegistroIn

BASE = dict(email="gerencia@empresa.co", nombre="Gerencia", password="ClaveSegura123")


def test_con_autorizacion_y_version_vigente():
    r = RegistroIn(**BASE, acepta_politica_datos=True, politica_datos_version=POLITICA_DATOS_VERSION)
    assert r.acepta_politica_datos is True


@pytest.mark.parametrize("cambio,mensaje", [
    ({}, "debe autorizar el tratamiento"),                                         # front viejo: no manda nada
    ({"acepta_politica_datos": False, "politica_datos_version": POLITICA_DATOS_VERSION}, "debe autorizar"),
    ({"acepta_politica_datos": True, "politica_datos_version": "2020-01-01"}, "se actualizó"),
])
def test_sin_autorizacion_valida_no_hay_registro(cambio, mensaje):
    with pytest.raises(ValidationError) as exc:
        RegistroIn(**BASE, **cambio)
    # Mensaje limpio, apto para mostrarlo tal cual (sin «Value error, …»).
    assert any(mensaje in e["msg"] and not e["msg"].startswith("Value error") for e in exc.value.errors())
