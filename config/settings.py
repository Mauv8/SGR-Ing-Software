"""
Configuración del proyecto SGR.

Los valores sensibles y los que cambian entre desarrollo y producción se leen
del entorno. Así el repositorio no contiene secretos y `DEBUG` no queda
encendido por descuido en el servidor, que son dos de los hallazgos más
frecuentes del riesgo A05 de OWASP (configuración de seguridad incorrecta).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(nombre, por_defecto=False):
    return os.environ.get(nombre, str(por_defecto)).lower() in ("1", "true", "yes", "si", "sí")


# ---------------------------------------------------------------------------
# Seguridad
# ---------------------------------------------------------------------------

# En desarrollo se usa una clave de relleno; en producción la variable es
# obligatoria y el arranque falla si no está definida.
DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY debe definirse en el entorno cuando DEBUG es False.")
    # Sólo en el computador del desarrollador: una clave aleatoria por arranque.
    from django.core.management.utils import get_random_secret_key
    SECRET_KEY = get_random_secret_key()

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# Cabeceras que aplican siempre.
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if not DEBUG:
    # Cabeceras y cookies que sólo tienen sentido sobre HTTPS.
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# ---------------------------------------------------------------------------
# Aplicaciones
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "gestion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "gestion.seguridad.ContentSecurityPolicyMiddleware",
]

# Límite de tamaño de una petición con archivos (evidencia de 5 MB + formulario).
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
# SQLite basta para el prototipo. PostgreSQL es el destino declarado en el
# diagrama de despliegue; el cambio es de configuración, no de código.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "gestion.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "login"

# La sesión caduca a las dos horas y se renueva con cada petición.
SESSION_COOKIE_AGE = 2 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True


# ---------------------------------------------------------------------------
# Localización
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Archivos estáticos
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Evidencias: se guardan fuera de la carpeta pública y sólo se entregan por la
# vista `evidencia_archivo`, que revisa permisos. No se define MEDIA_URL.
MEDIA_ROOT = BASE_DIR / "evidencias_privadas"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
