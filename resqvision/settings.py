"""ResQVision - Django settings.

Secure by default: with no environment configuration the app runs with DEBUG off and refuses to
start without a real secret key, explicit ALLOWED_HOSTS and a real AI service key. For local
development put DJANGO_DEBUG=1 in .env (see .env.example).
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from the .env file in the project root (if python-dotenv is installed).
# Real environment variables already set in the terminal / hosting take priority.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_int(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ImproperlyConfigured(f"{name} must be a whole number, got {raw!r}.")


def env_list(name, default=""):
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


# ---------------------------------------------------------------- Core / security
DEBUG = env_bool("DJANGO_DEBUG", False)

_DEV_SECRET_KEY = "dev-insecure-change-me-in-production"
_DEV_AI_KEY = "dev-ai-key-change-me"
_PLACEHOLDER_SECRETS = {"", "change-me", _DEV_SECRET_KEY}
_PLACEHOLDER_AI_KEYS = {"", "change-me", _DEV_AI_KEY}

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
AI_SERVICE_API_KEY = os.environ.get("AI_SERVICE_API_KEY", "")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]" if DEBUG else "")

if DEBUG:
    # Convenience fallbacks, only ever used in development.
    SECRET_KEY = SECRET_KEY or _DEV_SECRET_KEY
    AI_SERVICE_API_KEY = AI_SERVICE_API_KEY or _DEV_AI_KEY
else:
    if SECRET_KEY in _PLACEHOLDER_SECRETS or len(SECRET_KEY) < 32:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set to a unique random value of at least 32 characters "
            "when DJANGO_DEBUG is off. For local development set DJANGO_DEBUG=1."
        )
    if AI_SERVICE_API_KEY in _PLACEHOLDER_AI_KEYS or len(AI_SERVICE_API_KEY) < 16:
        raise ImproperlyConfigured(
            "AI_SERVICE_API_KEY must be set to a unique random value of at least 16 characters "
            "when DJANGO_DEBUG is off."
        )
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS must list the real host names (comma separated, no '*') "
            "when DJANGO_DEBUG is off."
        )

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# The single-page frontend reads the CSRF cookie from JavaScript, so CSRF_COOKIE_HTTPONLY stays False.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
    # Preload is a long-lived commitment, so it is opt-in (SECURE_HSTS_PRELOAD=1).
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Set USE_X_FORWARDED_PROTO=1 ONLY when a trusted reverse proxy terminates TLS and sets this header;
    # otherwise SECURE_SSL_REDIRECT would redirect forever.
    if env_bool("USE_X_FORWARDED_PROTO", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",    # custom user model, role-based login, OTP password reset
    "emergency",   # accidents, alerts, hospitals, police stations, cameras, notifications
    "web",         # HTML / CSS / JavaScript frontend (served by Django)
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "resqvision.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "resqvision.wsgi.application"

# ---------------------------------------------------------------- Database
# SQLite by default so the project runs out of the box (SQLITE_PATH overrides the file, used by the
# browser tests so they never touch the shared demo database).
# PostgreSQL is used automatically when DB_NAME is set (plus DB_USER, DB_PASSWORD, DB_HOST, DB_PORT).
if os.environ.get("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {"sslmode": os.environ["DB_SSLMODE"]} if os.environ.get("DB_SSLMODE") else {},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("SQLITE_PATH") or BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT") or BASE_DIR / "media")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Uploads from the AI service (evidence). The ingest endpoint also validates type and size.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
MAX_SNAPSHOT_BYTES = env_int("MAX_SNAPSHOT_BYTES", 8 * 1024 * 1024)
MAX_VIDEO_BYTES = env_int("MAX_VIDEO_BYTES", 100 * 1024 * 1024)

LOGIN_URL = "/"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    # Unexpected errors become a logged JSON 500 instead of an HTML page the frontend cannot read.
    "EXCEPTION_HANDLER": "resqvision.exceptions.api_exception_handler",
    # Brute-force protection for sign-in and the one-time-code password reset (per client IP).
    "DEFAULT_THROTTLE_RATES": {
        "login": os.environ.get("THROTTLE_LOGIN", "20/min"),
        "otp": os.environ.get("THROTTLE_OTP", "10/min"),
    },
}

# Password-reset codes are e-mailed. The console backend (development default) prints them to the server console.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 25)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "ResQVision <no-reply@resqvision.local>")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
