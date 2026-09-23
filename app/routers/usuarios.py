from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Request, Response, status

from ..db import fijar_usuario_actual, get_conn
from ..errors import ApiError
from ..security import requerir_token

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get(
    "/{usuario_id}/foto",
    response_class=Response,
    responses={
        200: {"content": {"image/webp": {}, "image/jpeg": {}, "image/png": {}}},
        304: {"description": "La versión que ya tiene el cliente sigue vigente."},
        404: {"description": "Sin foto propia (usa la predeterminada) o sin permiso para verla."},
    },
)
async def obtener_foto(
    usuario_id: UUID,
    request: Request,
    v: str | None = None,
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Devuelve la foto de perfil subida por un usuario.

    Quién puede verla lo decide el RLS de usuario_foto, no este código:
    cada quien la suya, y el admin la de todos (para la lista de
    usuarios). Tanto "no tiene foto" como "no puedes verla" responden 404,
    así esta ruta no sirve para averiguar qué cuentas existen.

    `v` es la versión (foto_actualizada_en) que el front ya conoce: con
    ella la respuesta se puede cachear como inmutable, porque cuando la
    foto cambia cambia también la URL.
    """
    async with conn.transaction():
        llamante = await conn.fetchval("SELECT nexus360.validar_sesion($1)", token)
        if llamante is None:
            raise ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "La sesión no es válida o expiró.")
        await fijar_usuario_actual(conn, llamante)

        fila = await conn.fetchrow(
            "SELECT imagen, mime, actualizado_en FROM nexus360.usuario_foto WHERE usuario_id = $1",
            usuario_id,
        )

    if fila is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "DESCONOCIDO", "Este usuario no tiene foto de perfil.")

    etag = f'"{int(fila["actualizado_en"].timestamp() * 1_000_000)}"'
    cabeceras = {
        "ETag": etag,
        # `private`: la respuesta depende del token; ningún proxy
        # compartido debe guardarla.
        "Cache-Control": "private, max-age=31536000, immutable" if v else "private, no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=cabeceras)

    return Response(content=bytes(fila["imagen"]), media_type=fila["mime"], headers=cabeceras)
