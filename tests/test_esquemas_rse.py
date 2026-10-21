"""Validaciones del contrato RSE Express que no necesitan base de datos."""
import pytest
from pydantic import ValidationError

from app.diagnostico_rse import columnas_de
from app.schemas_empresa import DiagnosticoIn, EmpresaIn, RespuestaIn

PERFIL = dict(razon_social="Acme", nit="900123456", dv="8", sector_id="industrial", municipio="Candelaria")
TAMIZAJE = dict(tamano="pequena", personas=18, vinculacion=["laboral"], zonas=["barrios", "viviendas"], clientes="personas")


def test_tamizaje_valido_y_sin_repetidos():
    e = EmpresaIn(**PERFIL, **{**TAMIZAJE, "vinculacion": ["laboral", "socios", "laboral"]})
    assert e.vinculacion == ["laboral", "socios"]


@pytest.mark.parametrize("cambio", [
    {"tamano": "grande"},             # T1 ya no tiene «grande»
    {"personas": 0},                  # T2 exige al menos una persona
    {"vinculacion": []},              # T2 exige cómo están vinculadas
    {"clientes": "consumidor"},       # T6 solo acepta las cuatro opciones
    {"zonas": ["viviendas"], "territorio": " "},     # T5a exige un lugar o el texto
    {"zonas": ["barrios"], "vecinos": "  "},          # T5b exige un vecino o el texto
    {"zonas": ["barrios", "ninguno", "afro"]},        # «ninguno» excluye a los demás vecinos
    {"zonas": ["barrios", "playa"]},                  # código desconocido
])
def test_tamizaje_invalido(cambio):
    with pytest.raises(ValidationError):
        EmpresaIn(**PERFIL, **{**TAMIZAJE, **cambio})


def test_territorio_solo_con_texto_es_valido():
    e = EmpresaIn(**PERFIL, **{**TAMIZAJE, "zonas": ["viviendas"], "territorio": "Vereda El Tiple"})
    assert e.territorio == "Vereda El Tiple"


def test_t5b_con_texto_o_sin_vecinos_es_valido():
    e = EmpresaIn(**PERFIL, **{**TAMIZAJE, "zonas": ["veredas"], "vecinos": "  Escuela rural  "})
    assert e.vecinos == "Escuela rural"
    assert EmpresaIn(**PERFIL, **{**TAMIZAJE, "zonas": ["rural", "ninguno"]}).vecinos is None
    # Todos los códigos de T5a y T5b, juntos (salvo «ninguno»), caben.
    todos = ["barrios", "comercial", "industrial", "veredas", "rural", "otras", "viviendas",
             "instituciones", "campesinos", "negocios", "indigenas", "afro", "otros_vecinos"]
    assert EmpresaIn(**PERFIL, **{**TAMIZAJE, "zonas": todos}).zonas == todos


@pytest.mark.parametrize("etapa,esperado", [
    ("0", (0, False, False)), ("4", (4, False, False)),
    ("NA", (None, True, False)), ("diferente", (None, False, True)), (None, (None, False, False)),
])
def test_etapa_a_columnas(etapa, esperado):
    assert columnas_de(RespuestaIn(etapa=etapa)) == esperado


def test_respuesta_vacia_y_ejemplos_limpios():
    assert RespuestaIn().vacia
    r = RespuestaIn(texto=" ", ejemplos=["  Buzón ", "Buzón", ""])
    assert r.ejemplos == ["Buzón"] and r.vacia is False


def test_etapa_y_priorizacion_fuera_de_rango():
    with pytest.raises(ValidationError):
        RespuestaIn(etapa="5")
    with pytest.raises(ValidationError):
        DiagnosticoIn(priorizacion={"filas": {"01a": {"importancia": 4}}})
