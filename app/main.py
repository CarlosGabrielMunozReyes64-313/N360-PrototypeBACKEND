import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import crear_pool
from .errors import ApiError
from .routers import auth

logger = logging.getLogger("nexus360")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await crear_pool()
    logger.info("Pool de PostgreSQL creado.")
    try:
        yield
    finally:
        await app.state.pool.close()
        logger.info("Pool de PostgreSQL cerrado.")


app = FastAPI(title="NEXUS 360° API", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"codigo": exc.codigo, "mensaje": exc.mensaje},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    primero = exc.errors()[0] if exc.errors() else None
    mensaje = primero["msg"] if primero else "Datos inválidos."
    return JSONResponse(
        status_code=422, content={"codigo": "VALIDACION", "mensaje": mensaje}
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Error no controlado", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"codigo": "DESCONOCIDO", "mensaje": "Error interno del servidor."},
    )


@app.get("/")
async def raiz():
    return {"mensaje": "NEXUS 360° backend funcionando"}


@app.get("/health")
async def salud(request: Request):
    try:
        async with request.app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"estado": "ok", "db": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503, content={"estado": "error", "db": "sin_conexion"}
        )
