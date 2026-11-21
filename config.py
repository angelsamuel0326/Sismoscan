"""Configuración central de SismoScan. Todo se controla con variables de entorno (ver .env.example)."""
import os

def _cargar_dotenv():
    """Lee el archivo .env junto a app.py (si existe) sin librerías extra. Las variables ya definidas en el sistema mandan."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                k, v = linea.split("=", 1)
                v = v.strip()
                if v[:1] in "\"'" and v[-1:] == v[:1] and len(v) > 1:
                    v = v[1:-1]
                else:
                    v = v.split(" #", 1)[0].strip()
                if k.strip():
                    os.environ.setdefault(k.strip(), v)
    except OSError:
        pass


_cargar_dotenv()



def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "si", "sí", "on")


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development")           # "production" activa controles estrictos
    SECRET_KEY = os.environ.get("SECRET_KEY", "")                # obligatorio en producción
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "")          # SQLite; por defecto: instance/sismoscan.db
    DATABASE_URL = os.environ.get("DATABASE_URL", "")            # PostgreSQL (postgresql://...); si existe, tiene prioridad
    TIMEZONE = os.environ.get("TIMEZONE", "America/Bogota")      # zona horaria para mostrar fechas
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")      # opcional: https://tu-app.onrender.com (enlaces compartidos)

    # Sesión (JWT en cookie HttpOnly)
    SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "8"))
    COOKIE_SECURE = _bool("COOKIE_SECURE", os.environ.get("APP_ENV") == "production")
    TRUST_PROXY = _bool("TRUST_PROXY", os.environ.get("APP_ENV") == "production")  # Render/PythonAnywhere van tras proxy

    # Correo (restablecer clave y verificar correo). Sin SMTP el enlace queda en el registro del servidor
    # y, solo fuera de producción, se muestra en pantalla para poder probar.
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "") or os.environ.get("SMTP_USER", "")
    SMTP_SSL = _bool("SMTP_SSL", False)                          # True = SSL directo (puerto 465); False = STARTTLS
    MOSTRAR_ENLACES_DEMO = _bool("MOSTRAR_ENLACES_DEMO", False)   # el enlace sin SMTP solo se escribe en el log; actívalo con 1 si quieres verlo en pantalla
    REMEMBER_DAYS = int(os.environ.get("REMEMBER_DAYS", "30"))   # duración de «Recordarme»
    SENTRY_DSN = os.environ.get("SENTRY_DSN", "")                # opcional: requiere `pip install sentry-sdk`

    # Subidas
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "10")) * 1024 * 1024
    MAX_IMAGE_SIDE = 1600           # px, lado mayor que se analiza
    THUMB_SIDE = 640                # px, miniatura que se guarda
    STORE_THUMBNAIL = _bool("STORE_THUMBNAIL", True)   # False = no se guarda ninguna imagen

    # Visión por computador: auto | openai | google | local
    VISION_PROVIDER = os.environ.get("VISION_PROVIDER", "auto").lower()
    VISION_TIMEOUT = int(os.environ.get("VISION_TIMEOUT", "30"))
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    GOOGLE_VISION_API_KEY = os.environ.get("GOOGLE_VISION_API_KEY", "")

    # Límites de intentos (en memoria; con varios workers usa Redis)
    RATELIMIT_ENABLED = _bool("RATELIMIT_ENABLED", True)
    MIN_PASSWORD = 8

    # Chat conversacional (usa la misma clave de OpenAI; sin clave responde con reglas locales)
    CHAT_MODEL = os.environ.get("CHAT_MODEL", "") or os.environ.get("OPENAI_MODEL", "gpt-4o")
    CHAT_ENABLED_LLM = _bool("CHAT_ENABLED_LLM", True)

    # Datos del proyecto (footer, «Acerca de» y privacidad)
    EQUIPO = ["Juan Felipe Rivera Sánchez", "Juan Camilo Rojas Insuasti", "Ángel Samuel Rosales Mejía", "Cristian Andrés Giraldo Coral", "Kevin Rodríguez Quigua"]
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")

    # Directorio de emergencia (Colombia). Se puede reemplazar con EMERGENCY_JSON='[["Nombre","123","nota"],...]'
    EMERGENCY_NUMBERS = [
        ("Línea única de emergencias", "123", "Policía, ambulancia y coordinación de emergencias."),
        ("Bomberos", "119", "Rescate, incendios, fugas de gas y estructuras comprometidas."),
        ("Cruz Roja Colombiana", "132", "Atención de emergencias y primeros auxilios."),
        ("Defensa Civil", "144", "Apoyo en rescate y atención de desastres."),
        ("Gestión del Riesgo", "123", "Pide que te comuniquen con la oficina de Gestión del Riesgo de tu municipio."),
    ]
    try:
        import json as _json
        _custom = os.environ.get("EMERGENCY_JSON")
        if _custom:
            EMERGENCY_NUMBERS = [tuple(x) for x in _json.loads(_custom)]
    except Exception:       # una variable mal escrita no debe tumbar la app
        pass
