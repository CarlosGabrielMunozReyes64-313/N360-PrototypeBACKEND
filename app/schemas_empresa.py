"""Contratos de /api/empresa/* (perfil, tamizaje y autodiagnóstico RSE Express).

Reflejan src/types.ts y src/auth/empresaApi.ts del frontend. El instrumento
es el del Anexo 1 del Protocolo de Validación NEXUS RSE Express + RSE por
Retos (v2, septiembre de 2026).
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------- tamizaje

# T1 · ¿Cómo describiría el tamaño de su empresa? (sin UVT: el protocolo lo
# retiró porque generaba desconfianza al inicio).
Tamano = Literal["micro", "pequena", "mediana", "nose"]
# T1 (opcional) · rango de ingresos anuales, si lo conoce.
RangoIngresos = Literal["menos_1000m", "1000m_10000m", "10000m_50000m", "mas_50000m", "no_indica"]
# T2 · cómo están vinculadas las personas que trabajan con la empresa.
Vinculacion = Literal["laboral", "servicios", "socios", "temporada", "otra"]
# T5 · lugares y comunidades cercanas.
Zona = Literal["barrios", "veredas", "rural", "indigenas", "afro", "otras"]
# T6 · ¿Quiénes son principalmente sus clientes?
TipoCliente = Literal["personas", "empresas", "publicas", "mezcla"]


def _limpiar(texto: str | None) -> str | None:
    if texto is None:
        return None
    texto = texto.strip()
    return texto or None


def _sin_repetidos(valores: list) -> list:
    vistos: list = []
    for v in valores:
        if v not in vistos:
            vistos.append(v)
    return vistos


class EmpresaIn(BaseModel):
    """Perfil + tamizaje en un solo envío, como los maneja el front."""
    razon_social: str = Field(min_length=1, max_length=300)
    nit: str = Field(min_length=5, max_length=15)
    dv: str = Field(min_length=1, max_length=1)
    sector_id: str
    municipio: str = Field(min_length=1, max_length=200)
    departamento: str | None = None
    extranjera: bool = False

    tamano: Tamano
    ingresos_rango: RangoIngresos | None = None
    personas: int = Field(gt=0, le=1_000_000)
    vinculacion: list[Vinculacion] = Field(min_length=1, max_length=5)
    vinculacion_detalle: str | None = Field(default=None, max_length=1000)
    zonas: list[Zona] = Field(default_factory=list, max_length=6)
    territorio: str | None = Field(default=None, max_length=2000)
    clientes: TipoCliente
    clientes_detalle: str | None = Field(default=None, max_length=1000)

    @field_validator("vinculacion_detalle", "territorio", "clientes_detalle")
    @classmethod
    def _texto_opcional(cls, v: str | None) -> str | None:
        return _limpiar(v)

    @field_validator("vinculacion", "zonas")
    @classmethod
    def _listas(cls, v: list) -> list:
        return _sin_repetidos(v)

    @model_validator(mode="after")
    def _territorio_obligatorio(self) -> "EmpresaIn":
        if not self.zonas and not self.territorio:
            raise ValueError("Cuéntenos dónde desarrolla su actividad: marque un lugar o escríbalo.")
        return self


class PerfilOut(BaseModel):
    empresa_id: UUID
    razon_social: str
    nit: str
    dv: str
    sector_id: str
    municipio: str
    departamento: str | None
    extranjera: bool


class TamizajeOut(BaseModel):
    ciclo_id: UUID
    anio: int
    tamano: str
    ingresos_rango: str | None
    personas: int
    vinculacion: list[str]
    vinculacion_detalle: str | None
    zonas: list[str]
    territorio: str | None
    clientes: str
    clientes_detalle: str | None
    actualizado_en: datetime


# ------------------------------------------------------------- diagnóstico

# «¿En qué punto está?» (sección 6.3). '0'..'4' es la lectura interna;
# 'diferente' = «Hacemos algo diferente»; 'NA' = «No aplica a nuestra empresa».
Etapa = Literal["0", "1", "2", "3", "4", "diferente", "NA"]


class RespuestaIn(BaseModel):
    texto: str = Field(default="", max_length=4000)
    ejemplos: list[str] = Field(default_factory=list, max_length=20)
    otro: str = Field(default="", max_length=1000)
    etapa: Etapa | None = None

    @field_validator("ejemplos")
    @classmethod
    def _ejemplos(cls, v: list[str]) -> list[str]:
        limpios = [e.strip()[:200] for e in v if e and e.strip()]
        return _sin_repetidos(limpios)

    @property
    def vacia(self) -> bool:
        return self.etapa is None and not self.texto.strip() and not self.ejemplos and not self.otro.strip()


class CalificacionIn(BaseModel):
    """Una fila de la matriz de priorización (sección 7): escala 1–3."""
    importancia: int | None = Field(default=None, ge=1, le=3)
    viabilidad: int | None = Field(default=None, ge=1, le=3)
    potencial: int | None = Field(default=None, ge=1, le=3)
    interes: int | None = Field(default=None, ge=1, le=3)


class PriorizacionIn(BaseModel):
    filas: dict[str, CalificacionIn] = Field(default_factory=dict, max_length=30)
    elegida: str | None = Field(default=None, max_length=10)


class DiagnosticoIn(BaseModel):
    """Envío completo del autodiagnóstico: el front manda todo cada vez
    (con un respiro entre envíos) y el backend solo reescribe lo que cambió."""
    respuestas: dict[str, RespuestaIn] = Field(default_factory=dict, max_length=40)
    # Clave: número de la materia ('01'…'07').
    fortalecer: dict[str, str] = Field(default_factory=dict, max_length=10)
    comentario_final: str | None = Field(default=None, max_length=4000)
    priorizacion: PriorizacionIn | None = None
    completo: bool = False

    @field_validator("fortalecer")
    @classmethod
    def _fortalecer(cls, v: dict[str, str]) -> dict[str, str]:
        for texto in v.values():
            if len(texto) > 2000:
                raise ValueError("Cada respuesta de «¿Qué le gustaría fortalecer?» admite hasta 2.000 caracteres.")
        return v


class RespuestaOut(BaseModel):
    respuesta_id: UUID
    texto: str
    ejemplos: list[str]
    otro: str
    etapa: Etapa | None
    # Clasificación de NEXUS para «Hacemos algo diferente» (0–4) o None.
    clasificada: int | None
    clasificado_en: datetime | None
    respondido_en: datetime


class DiagnosticoOut(BaseModel):
    diagnostico_id: UUID
    formato_id: str
    estado: str
    creado_en: datetime
    completado_en: datetime | None
    actualizado_en: datetime
    respuestas: dict[str, RespuestaOut]
    fortalecer: dict[str, str]
    comentario_final: str | None
    priorizacion: dict | None


class EmpresaMiaOut(BaseModel):
    """GET/PUT /empresa/mio. `tamizaje` y `diagnostico` son None cuando la
    empresa todavía no ha respondido el tamizaje nuevo (por ejemplo, justo
    después de la migración 009)."""
    empresa: PerfilOut
    tamizaje: TamizajeOut | None
    diagnostico: DiagnosticoOut | None
