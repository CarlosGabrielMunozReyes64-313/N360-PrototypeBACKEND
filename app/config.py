from functools import lru_cache

from pydantic import SecretStr
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

    # --- Análisis inteligente (Gemini API) --------------------------------
    # La API Key vive SOLO aquí, en el backend. SecretStr evita que aparezca
    # en logs, repr() o trazas: para leerla hay que pedir
    # get_secret_value() de forma explícita. Sin clave, el análisis IA
    # queda deshabilitado y el resto de la aplicación funciona igual.
    gemini_api_key: SecretStr | None = None
    # Modelo estable recomendado por Google para proyectos nuevos, con
    # límites holgados en el nivel gratuito. Se puede cambiar sin tocar código.
    gemini_model: str = "gemini-3.5-flash-lite"
    # Tiempo máximo por llamada. El front muestra «Analizando resultados…».
    gemini_timeout_segundos: float = 40.0
    # Intentos en total ante una respuesta inválida o un error transitorio
    # (5xx, tiempo agotado). Los 4xx (clave inválida, cuota agotada) no se
    # reintentan: gastarían cuota sin posibilidad de éxito.
    gemini_intentos: int = 2
    # Tope de análisis NUEVOS por usuario y por hora (los reutilizados no
    # cuentan). Protege la cuota gratuita frente a abusos o errores del front.
    ia_max_generaciones_por_hora: int = 6

    @property
    def gemini_configurado(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.get_secret_value().strip())

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
