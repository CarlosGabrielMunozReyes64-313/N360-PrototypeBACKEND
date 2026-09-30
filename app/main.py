import logging
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import crear_pool
from .errors import ApiError
from .esquema import CODIGO_ESQUEMA, ERRORES_DE_ESQUEMA, MENSAJE_ESQUEMA, verificar_esquema
from .ia.gemini_service import MENSAJE_SIN_SDK, SDK_DISPONIBLE, cerrar_servicio
from .routers import admin, auth, empresa, usuarios

logger = logging.getLogger("nexus360")
# uvicorn solo configura sus propios loggers: sin esto, los mensajes
# informativos de la app (p. ej. «Análisis IA generado … en 23.4 s») no se
# ven en la terminal. Propaga igual, así pytest los sigue capturando.
if not logger.handlers:
    _consola = logging.StreamHandler()
    _consola.setFormatter(logging.Formatter("%(levelname)-9s %(message)s"))
    logger.addHandler(_consola)
    logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await crear_pool()
    logger.info("Pool de PostgreSQL creado.")
    app.state.esquema = await verificar_esquema(app.state.pool)
    if not SDK_DISPONIBLE:
        logger.warning(MENSAJE_SIN_SDK)
    elif get_settings().gemini_configurado:
        logger.info("Análisis inteligente habilitado con el modelo %s.", get_settings().gemini_model)
    else:
        logger.warning(
            "GEMINI_API_KEY no está configurada: el análisis inteligente queda deshabilitado; "
            "el diagnóstico y el PDF funcionan normalmente."
        )
    try:
        yield
    finally:
        await cerrar_servicio()
        await app.state.pool.close()
        logger.info("Pool de PostgreSQL cerrado.")


app = FastAPI(title="NEXUS 360° API", version="0.1.0", lifespan=lifespan)


def respuesta_de_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, ERRORES_DE_ESQUEMA):
        logger.error("Consulta contra un esquema desactualizado: %s", exc)
        return JSONResponse(status_code=503, content={"codigo": CODIGO_ESQUEMA, "mensaje": MENSAJE_ESQUEMA})
    if isinstance(exc, asyncpg.PostgresError):
        logger.exception("Error de base de datos no controlado", exc_info=exc)
    else:
        logger.exception("Error no controlado", exc_info=exc)
    return JSONResponse(status_code=500, content={"codigo": "DESCONOCIDO", "mensaje": "Error interno del servidor."})


class CapturarErrores:
    """Convierte cualquier excepción no controlada en una respuesta JSON
    DENTRO del middleware de CORS. El manejador de `Exception` de FastAPI
    corre por fuera de CORS: su 500 llega sin Access-Control-Allow-Origin y
    el navegador lo reporta como «No se pudo conectar con el servidor»,
    escondiendo el error real."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        iniciada = False

        async def enviar(mensaje):
            nonlocal iniciada
            if mensaje["type"] == "http.response.start":
                iniciada = True
            await send(mensaje)

        try:
            await self.app(scope, receive, enviar)
        except Exception as exc:
            if iniciada:
                raise
            await respuesta_de_error(exc)(scope, receive, send)


settings = get_settings()
# Orden: el último middleware agregado queda por fuera. CapturarErrores se
# agrega primero para quedar por DENTRO de CORS.
app.add_middleware(CapturarErrores)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(empresa.router, prefix="/api")
app.include_router(usuarios.router, prefix="/api")


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"codigo": exc.codigo, "mensaje": exc.mensaje})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    primero = exc.errors()[0] if exc.errors() else None
    mensaje = primero["msg"] if primero else "Datos inválidos."
    return JSONResponse(status_code=422, content={"codigo": "VALIDACION", "mensaje": mensaje})


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Último recurso (CapturarErrores atiende casi todo antes, con CORS).
    return respuesta_de_error(exc)


@app.get("/")
async def raiz():
    return {"mensaje": "NEXUS 360° backend funcionando"}


@app.get("/health")
async def salud(request: Request):
    try:
        async with request.app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception:
        return JSONResponse(status_code=503, content={"estado": "error", "db": "sin_conexion"})
    esquema = await verificar_esquema(request.app.state.pool)
    request.app.state.esquema = esquema
    if not esquema["ok"]:
        return JSONResponse(status_code=503, content={
            "estado": "error", "db": "ok", "esquema": "falta_009",
            "faltantes": esquema["faltantes"], "mensaje": MENSAJE_ESQUEMA,
        })
    return {
        "estado": "ok", "db": "ok", "esquema": "ok",
        # Sin 011 el registro de cuentas nuevas queda bloqueado (ver esquema.py).
        "consentimiento_datos": "ok" if esquema.get("consentimiento_datos") else "falta_011",
        # Informativo: el análisis IA es opcional y nunca tumba el servicio.
        "analisis_ia": {
            "tabla": "ok" if esquema.get("analisis_ia") else "falta_010",
            "gemini": (
                "sin_sdk" if not SDK_DISPONIBLE
                else "configurado" if get_settings().gemini_configurado else "sin_clave"
            ),
        },
    }
