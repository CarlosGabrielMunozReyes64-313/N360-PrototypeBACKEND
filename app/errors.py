import asyncpg
from fastapi import status


class ApiError(Exception):
    """Error de API con forma {codigo, mensaje}, la misma que espera el front
    (ver src/auth/api.ts::parseError en el frontend)."""

    def __init__(self, status_code: int, codigo: str, mensaje: str):
        self.status_code = status_code
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(mensaje)


def desde_postgres(exc: asyncpg.PostgresError) -> ApiError:
    """Traduce las excepciones que lanzan registrar_usuario()/iniciar_sesion()
    (RAISE EXCEPTION con mensajes en español) a un ApiError con el código
    correcto para el front."""
    mensaje = str(exc.args[0]) if exc.args else str(exc)

    if isinstance(exc, asyncpg.UniqueViolationError) or "Ya existe una cuenta" in mensaje:
        return ApiError(status.HTTP_409_CONFLICT, "EMAIL_YA_REGISTRADO", mensaje)

    if "contraseña debe tener" in mensaje or "Correo electrónico inválido" in mensaje:
        return ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDACION", mensaje)

    if "contraseña actual no es correcta" in mensaje:
        return ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", mensaje)

    if "No hay una sesión activa" in mensaje:
        return ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", mensaje)

    return ApiError(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "DESCONOCIDO",
        "No se pudo completar la operación.",
    )
