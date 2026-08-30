from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración leída de variables de entorno / .env.

    IMPORTANTE: DATABASE_URL debe apuntar al rol `nexus360_app` (el rol de
    aplicación que crea db/001_schema.sql), NUNCA al dueño del esquema.
    Ese rol queda sujeto a Row Level Security; conectarse como el dueño
    del esquema desactivaría toda la seguridad de las tablas usuario,
    sesion y usuario_empresa.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql://nexus360_app:dev_only_change_me@localhost:5432/nexus360"
    )
    db_pool_min: int = 1
    db_pool_max: int = 10

    # Orígenes permitidos para CORS (el front en Vite corre en 5173 por defecto).
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Vercel genera una URL distinta por cada deploy/preview (con un hash
    # aleatorio), así que mantener ALLOWED_ORIGINS exacto sería una pelea
    # constante. Este patrón cubre cualquier subdominio *.vercel.app
    # automáticamente, sin tener que agregar cada URL a mano.
    allowed_origin_regex: str = r"https://.*\.vercel\.app"

    # Duración máxima del token que se refleja en la cookie/almacenamiento
    # del cliente. El límite real de expiración lo fija la función SQL
    # iniciar_sesion() (12 horas); esto es solo informativo.
    session_hint_hours: int = 12

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
