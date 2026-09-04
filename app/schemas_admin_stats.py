from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ResumenGeneral(BaseModel):
    empresas: int
    usuarios: int
    diagnosticos_completados: int
    diagnosticos_totales: int


class ConteoSector(BaseModel):
    sector_id: str
    nombre: str
    total: int


class ConteoTamano(BaseModel):
    tamano: str
    total: int


class ConteoEstadoDiagnostico(BaseModel):
    formato_id: str
    estado: str
    total: int


class PromedioDimension(BaseModel):
    formato_id: str
    numero: str
    dimension: str
    promedio: float
    respuestas: int


class EstadisticasOut(BaseModel):
    resumen: ResumenGeneral
    empresas_por_sector: list[ConteoSector]
    empresas_por_tamano: list[ConteoTamano]
    diagnosticos_por_estado: list[ConteoEstadoDiagnostico]
    promedio_por_dimension: list[PromedioDimension]


class EmpresaDetalleOut(BaseModel):
    empresa_id: UUID
    razon_social: str
    nit: str
    dv: str
    sector_id: str
    sector_nombre: str | None
    municipio: str
    departamento: str | None
    anio: int | None
    tamano: str | None
    empleados: int | None
    areas_de_vida: str | None
    ciclo_previo: bool | None
    comunidades_etnicas: bool | None
    consumidor_final: bool | None
    iso26000_estado: str | None
    ley2173_estado: str | None
    creado_en: datetime
