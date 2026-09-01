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
    usuario normal nunca ve de sí mismo (intentos_fallidos, bloqueado_hasta)."""
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


class CambiarEstadoIn(BaseModel):
    activo: bool


class CambiarRolIn(BaseModel):
    rol: Literal["empresa", "admin"]


class RestablecerPasswordAdminIn(BaseModel):
    password_nueva: str = Field(min_length=8, max_length=200)


class SesionAdminOut(BaseModel):
    sesion_id: UUID
    usuario_id: UUID
    creado_en: datetime
    expira_en: datetime
    revocado_en: datetime | None
    ip_origen: str | None
    user_agent: str | None


class SesionOut(BaseModel):
    token: str
    expira_en: datetime
    usuario: UsuarioOut


class MeOut(BaseModel):
    usuario: UsuarioOut
