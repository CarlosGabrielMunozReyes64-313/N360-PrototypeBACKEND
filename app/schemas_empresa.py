from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class EmpresaIn(BaseModel):
    """Perfil + tamizaje en un solo envío — así es como el front los maneja
    (un solo paso completo antes de pasar a Diagnóstico)."""
    razon_social: str = Field(min_length=1, max_length=300)
    nit: str = Field(min_length=5, max_length=15)
    dv: str = Field(min_length=1, max_length=1)
    sector_id: str
    municipio: str = Field(min_length=1, max_length=200)
    departamento: str | None = None
    extranjera: bool = False

    tamano: Literal["micro", "pequena", "mediana", "grande"]
    empleados: int = Field(gt=0)
    areas_de_vida: Literal["si", "no", "nose"]
    ciclo_previo: bool
    comunidades_etnicas: bool
    consumidor_final: bool


class EmpresaOut(BaseModel):
    empresa_id: UUID
    razon_social: str
    nit: str
    dv: str
    sector_id: str
    municipio: str
    departamento: str | None
    extranjera: bool

    ciclo_id: UUID
    anio: int
    tamano: str
    empleados: int
    areas_de_vida: str
    ciclo_previo: bool
    comunidades_etnicas: bool
    consumidor_final: bool


class RespuestasIn(BaseModel):
    """codigo de pregunta -> '0'..'4' o 'NA'."""
    respuestas: dict[str, str]
    completo: bool = False


class RespuestasOut(BaseModel):
    formato_id: str
    estado: str
    respuestas: dict[str, str]
