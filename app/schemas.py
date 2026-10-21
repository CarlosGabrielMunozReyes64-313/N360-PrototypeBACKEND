from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_core import PydanticCustomError

# Versión vigente de la Política de Tratamiento de Datos Personales. Debe
# coincidir con POLITICA_DATOS.version en src/data/politicaDatos.ts del
# frontend: si el texto cambia, se cambian las dos y el registro exige
# aceptar la nueva (un front viejo en caché no puede registrar con la
# versión anterior).
POLITICA_DATOS_VERSION = "2026-09-29"


class RegistroIn(BaseModel):
    email: EmailStr
    nombre: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    # El autorregistro SIEMPRE es 'empresa'. Se declara explícito (en vez
    # de aceptar cualquier string) para que sea imposible mandar 'admin'
    # desde este endpoint, igual que hace registrar_usuario() en SQL.
    rol: Literal["empresa"] = "empresa"
    # Autorización previa, expresa e informada (Ley 1581 de 2012, art. 9):
    # sin ella no se crea la cuenta. La prueba queda en consentimiento_datos.
    # validate_default: un front viejo que no manda estos campos también debe
    # recibir el mensaje claro (y no llegar a la base sin autorización).
    acepta_politica_datos: bool = Field(default=False, validate_default=True)
    politica_datos_version: str = Field(
        default="", max_length=40, validate_default=True
    )

    @field_validator("acepta_politica_datos")
    @classmethod
    def _autorizacion_obligatoria(cls, v: bool) -> bool:
        if v is not True:
            raise PydanticCustomError(
                "politica_datos",
                "Para crear la cuenta debe autorizar el tratamiento de sus datos personales.",
            )
        return v

    @field_validator("politica_datos_version")
    @classmethod
    def _version_vigente(cls, v: str) -> str:
        if v != POLITICA_DATOS_VERSION:
            raise PydanticCustomError(
                "politica_datos_version",
                "La Política de Tratamiento de Datos se actualizó. Recargue la página, léala y vuelva a intentarlo.",
            )
        return v


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
    # Cuándo subió su foto de perfil. None = usa la foto predeterminada
    # (iniciales), que dibuja el front. El front usa este valor como
    # versión de la foto para su caché (GET /usuarios/{id}/foto?v=...).
    foto_actualizada_en: datetime | None = None


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
    foto_actualizada_en: datetime | None = None


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
    """Un tamizaje «Conozcamos su empresa» (T1, T2, T5a, T5b y T6). Se guarda la
    fecha de creación y la de la última edición, no el historial completo."""

    ciclo_id: UUID
    empresa_id: UUID
    razon_social: str
    anio: int
    tamano: str
    ingresos_rango: str | None
    personas: int
    vinculacion: list[str]
    zonas: list[str]
    territorio: str | None
    vecinos: str | None = None
    clientes: str
    creado_en: datetime
    actualizado_en: datetime


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


class ConteoClienteOut(BaseModel):
    """T6 · tipo de clientes: personas, empresas, publicas o mezcla."""

    clientes: str
    total: int


class ConteoEtapaOut(BaseModel):
    """Respuestas por etapa: '0'..'4', 'diferente' o 'NA'."""

    etapa: str
    total: int


class PromedioDimensionOut(BaseModel):
    """Promedio de la lectura INTERNA 0–4 por materia (uso de NEXUS; a la
    empresa no se le muestra como puntaje)."""

    formato_id: str
    numero: str
    dimension: str
    promedio: float
    respuestas: int


class ConteoRangoOut(BaseModel):
    """Empresas por número de personas (T2), en rangos."""

    rango: str
    total: int


class ConteoMateriaOut(BaseModel):
    numero: str
    materia: str
    total: int


class ConteoMateriaEtapaOut(BaseModel):
    """Respuestas de una materia en una etapa ('0'..'4', 'diferente', 'NA')."""

    numero: str
    materia: str
    etapa: str
    total: int


class AlertasOut(BaseModel):
    """Empresas con cada alerta informativa (mismas reglas que el front)."""

    ley2173: int
    sst: int
    datos: int
    territorio: int


class IndicadoresDiagnosticoOut(BaseModel):
    """Indicadores de la sección 10 del protocolo (diagnóstico ajustado y
    participación). Son conteos descriptivos, no metas."""

    empresas_con_tamizaje: int
    empresas_perfil_piloto: int
    empresas_con_diagnostico: int
    empresas_con_practicas: int
    practicas_registradas: int
    respuestas_diferente: int
    diferente_sin_clasificar: int
    respuestas_na: int
    materias_con_fortalecer: int
    comentarios_finales: int


class EstadisticasOut(BaseModel):
    resumen: ResumenGeneralOut
    empresas_por_sector: list[ConteoSectorOut]
    empresas_por_tamano: list[ConteoTamanoOut]
    empresas_por_cliente: list[ConteoClienteOut]
    diagnosticos_por_estado: list[ConteoEstadoOut]
    respuestas_por_etapa: list[ConteoEtapaOut]
    promedio_por_dimension: list[PromedioDimensionOut]
    indicadores: IndicadoresDiagnosticoOut
    empresas_por_personas: list[ConteoRangoOut]
    etapas_por_materia: list[ConteoMateriaEtapaOut]
    practicas_por_materia: list[ConteoMateriaOut]
    retos_por_materia: list[ConteoMateriaOut]
    alertas: AlertasOut


class EmpresaDetalleOut(BaseModel):
    """Una fila por empresa activa, con el tamizaje de su ciclo más
    reciente y el avance de su autodiagnóstico RSE Express. Si la empresa no
    tiene tamizaje (p. ej. justo después de la migración 009), los campos de
    tamizaje y diagnóstico quedan en None: no se inventa un valor."""

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
    ingresos_rango: str | None
    personas: int | None
    vinculacion: list[str] | None
    vinculacion_detalle: str | None
    zonas: list[str] | None
    territorio: str | None
    vecinos: str | None = None
    clientes: str | None
    clientes_detalle: str | None
    # Criterio de selección del piloto: entre 10 y 50 personas (T2).
    perfil_piloto: bool | None
    diagnostico_estado: str | None
    diagnostico_actualizado_en: datetime | None
    respuestas_con_etapa: int
    practicas_registradas: int
    pendientes_clasificar: int
    # Cuenta de contacto: quien registró la empresa o, si se eliminó, otra
    # cuenta de empresa vinculada. None si no queda ninguna.
    contacto_nombre: str | None = None
    contacto_email: str | None = None


class ActividadUsuarioOut(BaseModel):
    """Todo lo que el sistema sabe del paso de un usuario por la
    plataforma: sus sesiones y su rastro en el diagnóstico."""

    usuario: UsuarioAdminOut
    sesiones: list[SesionAdminOut]
    empresas: list[EmpresaActividadOut]
    tamizajes: list[TamizajeActividadOut]
    diagnosticos: list[DiagnosticoActividadOut]


class ClasificarIn(BaseModel):
    """Clasificación de NEXUS para una respuesta «Hacemos algo diferente»:
    0–4 en la lectura interna, o None para quitarla."""

    valor: int | None = Field(default=None, ge=0, le=4)


class ClasificacionOut(BaseModel):
    respuesta_id: UUID
    codigo: str
    clasificada: int | None
    clasificado_en: datetime | None


class SesionOut(BaseModel):
    token: str
    expira_en: datetime
    usuario: UsuarioOut


class MeOut(BaseModel):
    usuario: UsuarioOut
