from fastapi import Header, Request, status

from .errors import ApiError


async def requerir_token(authorization: str | None = Header(default=None)) -> str:
    """Extrae el token del header `Authorization: Bearer <token>`.

    No valida el token contra la base de datos aquí (eso lo hace
    validar_sesion() en SQL, en cada endpoint) — solo exige que venga
    presente y bien formado.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            "CREDENCIALES_INVALIDAS",
            "Falta el token de sesión (header Authorization: Bearer <token>).",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "Token vacío."
        )
    return token


def obtener_ip(request: Request) -> str | None:
    # Respeta un proxy/inverso si existiera (Render, Railway, nginx, etc.)
    reenviado = request.headers.get("x-forwarded-for")
    if reenviado:
        return reenviado.split(",")[0].strip()
    return request.client.host if request.client else None


def obtener_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")
