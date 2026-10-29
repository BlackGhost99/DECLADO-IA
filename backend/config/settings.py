"""Configuration Django de ClairTransit.

Toute la configuration sensible vient de variables d'environnement (voir .env.example).
Aucun secret réel ne doit figurer dans le dépôt.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

DEBUG = env.bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env("DJANGO_SECRET_KEY") if not DEBUG else env("DJANGO_SECRET_KEY", default="dev-only-insecure-key")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.localization",
    "apps.document_graph",
    "apps.audit",
    "apps.clients",
    "apps.tariffs",
    "apps.documents",
    "apps.regulations",
    "apps.cases",
    "apps.extraction",
    "apps.scans",
    "apps.onboarding",
    "apps.fiscal",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.mfa_middleware.MFAEnforcementMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://clairtransit:clairtransit@localhost:5432/clairtransit",
    )
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Français"), ("en", "English"), ("es", "Español"), ("ar", "العربية")]
TIME_ZONE = "UTC"  # stockage en UTC ; affichage selon le fuseau de la société
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sessions serveur, cookie HttpOnly ; Secure hors développement.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
# Le cookie CSRF reste lisible par le client web pour l'en-tête X-CSRFToken.
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=60 * 60 * 10)

# Envoi des invitations par e-mail : facultatif. Sans serveur SMTP, le lien se copie à la main.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER or "ClairTransit <no-reply@localhost>")
INVITATION_EMAIL_ENABLED = env.bool("INVITATION_EMAIL_ENABLED", default=bool(EMAIL_HOST))
# Adresse de l'interface telle que les invités l'ouvrent, pour les liens envoyés par e-mail.
PUBLIC_APP_URL = env("PUBLIC_APP_URL", default="")

# MFA is required for every production user, including technical administrators.
# A dedicated Fernet key is required. See the security deployment instructions.
MFA_ENFORCE = env.bool("MFA_ENFORCE", default=not DEBUG)
MFA_ENCRYPTION_KEY = env("MFA_ENCRYPTION_KEY", default="")
AUTH_RATE_LIMIT_ENABLED = env.bool("AUTH_RATE_LIMIT_ENABLED", default=not DEBUG)
if MFA_ENFORCE and not MFA_ENCRYPTION_KEY:
    raise ImproperlyConfigured("MFA_ENCRYPTION_KEY is required when MFA_ENFORCE is enabled")

# All production login attempt counters are shared between workers.
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "clairtransit-test"}
        if DEBUG
        else {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("CACHE_URL", default="redis://localhost:6379/1"),
        }
    )
}


if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_SSL_REDIRECT = True
    SECURE_REFERRER_POLICY = "same-origin"
    SECURE_CONTENT_TYPE_NOSNIFF = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "COERCE_DECIMAL_TO_STRING": True,
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
    "DEFAULT_THROTTLE_CLASSES": []
    if DEBUG
    else [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "100/minute", "user": "600/minute"},
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
# Relance périodique de la boîte d'envoi : reprend les événements en attente (courtier indisponible
# au moment de l'enregistrement, nouvelle tentative après échec, bail expiré d'un travail interrompu).
CELERY_BEAT_SCHEDULE = {
    "outbox": {"task": "core.dispatch_outbox", "schedule": env.int("OUTBOX_POLL_SECONDS", default=30)},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.middleware.RequestIdLogFilter"}},
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain", "filters": ["request_id"]},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

# Stockage privé des sources et pièces : jamais servi directement par le serveur web.
PRIVATE_STORAGE_ROOT = Path(env("PRIVATE_STORAGE_ROOT", default=str(BASE_DIR / "var" / "private")))

# Pièces des dossiers (DOC-01) : limites configurables, à réviser après mesure.
DOCUMENT_MAX_BYTES = env.int("DOCUMENT_MAX_BYTES", default=50 * 1024 * 1024)
DOCUMENT_LINK_TTL_SECONDS = env.int("DOCUMENT_LINK_TTL_SECONDS", default=300)

# Security gate for every external document upload. Never bypass the daemon.
CLAMAV_HOST = env("CLAMAV_HOST", default="127.0.0.1")
CLAMAV_PORT = env.int("CLAMAV_PORT", default=3310)
CLAMAV_CONNECT_TIMEOUT = env.int("CLAMAV_CONNECT_TIMEOUT", default=5)
CLAMAV_SCAN_TIMEOUT = env.int("CLAMAV_SCAN_TIMEOUT", default=120)

# Extraction des factures (lot 3). Limite de pages proposée par le cahier des charges, révisable après mesure.
EXTRACTION_MAX_PAGES = env.int("EXTRACTION_MAX_PAGES", default=500)
OCR_LANGUAGES = env("OCR_LANGUAGES", default="fra+eng+spa+ara")
OCR_PAGE_TIMEOUT_SECONDS = env.int("OCR_PAGE_TIMEOUT_SECONDS", default=120)
# Numérisation : nombre de pages au plus dans un lot (scanner ou téléphone).
SCAN_BATCH_MAX_PAGES = env.int("SCAN_BATCH_MAX_PAGES", default=300)
# Un lot du scanner peut arriver en dizaines d'images : le plafond de Django (100) suit celui du lot.
DATA_UPLOAD_MAX_NUMBER_FILES = SCAN_BATCH_MAX_PAGES + 10
# IA en ligne facultative (apps/extraction/ai.py) : « disabled » par défaut, « anthropic » ou « gemini ».
# La clé reste sur le serveur ; chaque société l'active ensuite pour elle-même (Administration > IA en ligne).
AI_PROVIDER = env("AI_PROVIDER", default="disabled")
AI_API_KEY = env("AI_API_KEY", default="")
AI_MODEL = env("AI_MODEL", default="")  # vide : modèle par défaut du fournisseur
# Offre gratuite : le fournisseur peut réutiliser ce qui lui est envoyé. Essais sur pièces fictives seulement.
AI_FREE_TIER = env.bool("AI_FREE_TIER", default=False)
AI_TIMEOUT_SECONDS = env.int("AI_TIMEOUT_SECONDS", default=60)
AI_MAX_TEXT_CHARS = env.int("AI_MAX_TEXT_CHARS", default=30000)
# Au-delà, Django écrit le fichier reçu sur disque plutôt qu'en mémoire.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
