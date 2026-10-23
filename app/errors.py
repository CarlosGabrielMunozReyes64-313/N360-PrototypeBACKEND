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

    if (
        isinstance(exc, asyncpg.UniqueViolationError)
        or "Ya existe una cuenta registrada" in mensaje
    ):
        return ApiError(status.HTTP_409_CONFLICT, "EMAIL_YA_REGISTRADO", mensaje)

    if "contraseña debe tener" in mensaje or "Correo electrónico inválido" in mensaje:
        return ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDACION", mensaje)

    if "contraseña actual no es correcta" in mensaje:
        return ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", mensaje)

    if "enlace de recuperación no es válido" in mensaje:
        return ApiError(status.HTTP_400_BAD_REQUEST, "TOKEN_INVALIDO", mensaje)

    if "No hay una sesión activa" in mensaje:
        return ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", mensaje)

    # --- Guardas de las funciones de administración (004 y 005) ---

    if mensaje.startswith("Solo un administrador"):
        return ApiError(status.HTTP_403_FORBIDDEN, "PROHIBIDO", mensaje)

    if "El usuario no existe" in mensaje:
        return ApiError(status.HTTP_404_NOT_FOUND, "DESCONOCIDO", mensaje)

    if (
        "La cuenta ya fue eliminada" in mensaje
        or "Ya existe una cuenta activa con ese correo" in mensaje
    ):
        return ApiError(status.HTTP_409_CONFLICT, "CONFLICTO", mensaje)

    if (
        "No puedes eliminar tu propia cuenta" in mensaje
        or "último administrador activo" in mensaje
        or "La cuenta no está eliminada" in mensaje
    ):
        return ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDACION", mensaje)

    return ApiError(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "DESCONOCIDO",
        "No se pudo completar la operación.",
    )
