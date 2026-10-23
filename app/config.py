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
    # Tiempo MÁXIMO TOTAL de espera por análisis, sumando intentos. Con
    # diagnósticos largos Gemini puede tardar 30–60 s; el front muestra
    # «Analizando resultados…» mientras tanto.
    gemini_timeout_segundos: float = 90.0
    # Intentos en total ante una respuesta inválida o un fallo pasajero del
    # servidor (500/502/503, sin conexión), si queda tiempo. No se reintenta
    # un tiempo agotado (solo duplicaría la espera) ni un 4xx (clave
    # inválida, cuota agotada: gastaría cuota sin posibilidad de éxito).
    gemini_intentos: int = 2
    # Tope de análisis NUEVOS por usuario y por hora (los reutilizados no
    # cuentan). Protege la cuota gratuita frente a abusos o errores del front.
    ia_max_generaciones_por_hora: int = 6

    # --- Asistente de la empresa (chatbot, usa la misma GEMINI_API_KEY) ----
    # Tope de mensajes por usuario y por hora. Cada pregunta es una llamada
    # corta a Gemini; el tope evita que un error del front o un abuso agote
    # la cuota que también usa el análisis inteligente.
    asistente_max_mensajes_por_hora: int = 40
    # Tiempo máximo para terminar una respuesta (las respuestas son cortas;
    # suelen tardar de 2 a 8 s).
    asistente_timeout_segundos: float = 45.0

    # --- reCAPTCHA v3 (registro e inicio de sesión) -----------------------
    # Clave secreta «legacy» de la consola de reCAPTCHA (la del sitio va en el
    # .env del front como VITE_RECAPTCHA_SITE_KEY). Sin clave, la
    # verificación queda apagada y el arranque lo avisa. Ver app/recaptcha.py.
    recaptcha_secret_key: SecretStr | None = None
    # Puntaje mínimo (0.0 = bot, 1.0 = persona) por acción. El login es más
    # tolerante: un falso positivo ahí deja por fuera a una empresa real.
    recaptcha_umbral_registro: float = 0.5
    recaptcha_umbral_login: float = 0.3
    # true = solo registra en el log lo que se habría rechazado, sin
    # bloquear. Recomendado las primeras semanas para fijar los umbrales.
    recaptcha_solo_observar: bool = False
    # Espera máxima de la respuesta de Google; si no llega, se deja pasar.
    recaptcha_timeout_segundos: float = 5.0
    # «¿Olvidaste tu contraseña?» manda correos: un bot que la abuse llena
    # buzones ajenos y gasta la cuota del proveedor. Mismo rigor que el registro.
    recaptcha_umbral_recuperacion: float = 0.5

    # --- Recuperación de contraseña por correo (013) -----------------------
    # URL pública del FRONT, de donde sale el enlace del correo
    # (FRONTEND_URL/#/restablecer?token=...). Se lee de aquí y NUNCA de las
    # cabeceras de la petición (Host, Origin): esas las controla quien llama,
    # y un atacante podría hacer que el enlace apunte a su propio sitio.
    frontend_url: str = "http://localhost:5173"
    # Minutos que dura un enlace. La base lo acota entre 5 y 120.
    recuperacion_minutos: int = 30

    # Cómo sale el correo: "smtp", "brevo" o vacío (apagado: el endpoint
    # responde 503 CORREO_NO_CONFIGURADO y el resto de la app funciona igual).
    #  * smtp: cualquier servidor SMTP. En desarrollo, Mailpit
    #    (docker compose up -d) en localhost:1025 sin seguridad.
    #  * brevo: API HTTPS de Brevo. Úsela si el backend corre en un plan que
    #    bloquea los puertos SMTP (p. ej. Render gratis).
    correo_proveedor: str = ""
    correo_remitente: str = ""                  # p. ej. no-responder@tudominio.co
    correo_remitente_nombre: str = "NEXUS 360°"
    correo_timeout_segundos: float = 15.0

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_usuario: str = ""
    smtp_password: SecretStr | None = None
    # "starttls" (puerto 587), "ssl" (puerto 465) o "ninguna" (solo Mailpit/local).
    smtp_seguridad: str = "ninguna"

    brevo_api_key: SecretStr | None = None

    @property
    def correo_configurado(self) -> bool:
        if not self.correo_remitente.strip():
            return False
        if self.correo_proveedor == "smtp":
            return bool(self.smtp_host.strip())
        if self.correo_proveedor == "brevo":
            return bool(self.brevo_api_key and self.brevo_api_key.get_secret_value().strip())
        return False

    @property
    def frontend_base(self) -> str:
        return self.frontend_url.strip().rstrip("/")

    @property
    def gemini_configurado(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.get_secret_value().strip())

    @property
    def recaptcha_configurado(self) -> bool:
        return bool(self.recaptcha_secret_key and self.recaptcha_secret_key.get_secret_value().strip())

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
