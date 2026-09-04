from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegistroIn(BaseModel):
    email: EmailStr
    nombre: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    # El autorregistro SIEMPRE es 'empresa'. Se declara explícito (en vez
    # de aceptar cualquier string) para que sea imposible mandar 'admin'
    # desde este endpoint, igual que hace registrar_usuario() en SQL.
    rol: Literal["empresa"] = "empresa"


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UsuarioOut(BaseModel):
    usuario_id: UUID
    email: str
    nombre: str
    rol: str
    activo: bool
    email_verificado_en: datetime | None
    ultimo_login_en: datetime | None


class ActualizarPerfilIn(BaseModel):
    """Ambos campos opcionales: se puede mandar solo el que cambió."""
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    email: EmailStr | None = None


class CambiarPasswordIn(BaseModel):
    password_actual: str = Field(min_length=1, max_length=200)
    password_nueva: str = Field(min_length=8, max_length=200)


# ---- Solo para /api/admin/* ----

class UsuarioAdminOut(BaseModel):
    """Vista de usuario para el panel de admin — incluye campos que un
    usuario normal nunca ve de sí mismo (intentos_fallidos, bloqueado_hasta)
    y el marcador de eliminación (archivado_en)."""
    usuario_id: UUID
    email: str
    nombre: str
    rol: str
    activo: bool
    intentos_fallidos: int
    bloqueado_hasta: datetime | None
    email_verificado_en: datetime | None
    ultimo_login_en: datetime | None
    creado_en: datetime
    archivado_en: datetime | None = None


class CambiarEstadoIn(BaseModel):
    activo: bool


class CambiarRolIn(BaseModel):
    rol: Literal["empresa", "admin"]


class RestablecerPasswordAdminIn(BaseModel):
    password_nueva: str = Field(min_length=8, max_length=200)


class EliminacionOut(BaseModel):
    """Resultado de DELETE /admin/usuarios/{id}.

    `modo` dice qué ocurrió de verdad: 'fisico' cuando la cuenta no tenía
    rastro y se borró, 'archivado' cuando se conservó por trazabilidad.
    El panel lo usa para no prometerle al admin algo que no pasó."""
    usuario_id: UUID
    modo: Literal["fisico", "archivado"]
    mensaje: str


class SesionAdminOut(BaseModel):
    sesion_id: UUID
    usuario_id: UUID
    creado_en: datetime
    expira_en: datetime
    revocado_en: datetime | None
    # 'logout' (el usuario salió), 'admin' (se la revocaron), 'eliminacion'
    # (se eliminó la cuenta). None en sesiones vivas y en las cerradas
    # antes de la migración 006: ese dato no existe y no se inventa.
    revocado_motivo: Literal["logout", "admin", "eliminacion"] | None = None
    ip_origen: str | None
    user_agent: str | None


class ResumenSesionesOut(BaseModel):
    """Una fila por usuario para la lista de actividad."""
    usuario_id: UUID
    total: int
    activas: int
    ultima_sesion: datetime | None


class EmpresaActividadOut(BaseModel):
    empresa_id: UUID
    razon_social: str
    nit: str
    dv: str
    municipio: str
    creado_en: datetime
    es_creador: bool


class TamizajeActividadOut(BaseModel):
    """Un ciclo de tamizaje. `creado_en` es la única marca de tiempo que
    guarda el esquema para el tamizaje: no hay historial de ediciones."""
    ciclo_id: UUID
    empresa_id: UUID
    razon_social: str
    anio: int
    tamano: str
    empleados: int
    areas_de_vida: str
    ciclo_previo: bool
    comunidades_etnicas: bool
    consumidor_final: bool
    creado_en: datetime


class DiagnosticoActividadOut(BaseModel):
    diagnostico_id: UUID
    formato_id: str
    codigo: str
    formato_nombre: str
    razon_social: str
    anio: int
    estado: str
    creado_en: datetime
    completado_en: datetime | None
    respuestas_total: int
    respuestas_usuario: int
    primera_respuesta: datetime | None
    ultima_respuesta: datetime | None


# ---- Solo para /api/admin/estadisticas y /api/admin/empresas ----

class ResumenGeneralOut(BaseModel):
    empresas: int
    usuarios: int
    diagnosticos_totales: int
    diagnosticos_completados: int


class ConteoSectorOut(BaseModel):
    sector_id: str
    nombre: str
    total: int


class ConteoTamanoOut(BaseModel):
    tamano: str
    total: int


class ConteoEstadoOut(BaseModel):
    formato_id: str
    estado: str
    total: int


class PromedioDimensionOut(BaseModel):
    formato_id: str
    numero: str
    dimension: str
    promedio: float
    respuestas: int


class EstadisticasOut(BaseModel):
    resumen: ResumenGeneralOut
    empresas_por_sector: list[ConteoSectorOut]
    empresas_por_tamano: list[ConteoTamanoOut]
    diagnosticos_por_estado: list[ConteoEstadoOut]
    promedio_por_dimension: list[PromedioDimensionOut]


class EmpresaDetalleOut(BaseModel):
    """Una fila por empresa activa, con el tamizaje de su ciclo más
    reciente y el estado actual de cada formato en ese ciclo. Si la
    empresa no tiene ningún ciclo registrado, los campos de tamizaje y
    diagnóstico quedan en None: no se inventa un valor por defecto."""
    empresa_id: UUID
    razon_social: str
    nit: str
    dv: str
    sector_id: str
    sector_nombre: str
    municipio: str
    departamento: str | None
    creado_en: datetime
    anio: int | None
    tamano: str | None
    empleados: int | None
    areas_de_vida: str | None
    ciclo_previo: bool | None
    comunidades_etnicas: bool | None
    consumidor_final: bool | None
    iso26000_estado: str | None
    ley2173_estado: str | None


class ActividadUsuarioOut(BaseModel):
    """Todo lo que el sistema sabe del paso de un usuario por la
    plataforma: sus sesiones y su rastro en el diagnóstico."""
    usuario: UsuarioAdminOut
    sesiones: list[SesionAdminOut]
    empresas: list[EmpresaActividadOut]
    tamizajes: list[TamizajeActividadOut]
    diagnosticos: list[DiagnosticoActividadOut]


class SesionOut(BaseModel):
    token: str
    expira_en: datetime
    usuario: UsuarioOut


class MeOut(BaseModel):
    usuario: UsuarioOut
