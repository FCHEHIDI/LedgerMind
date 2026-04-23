"""
Development settings for LedgerMind backend.

Usage:
    DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py runserver

Differences from base:
  - DEBUG = True
  - CORS permissif (localhost frontend)
  - No forced HTTPS
  - django-debug-toolbar activé
"""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "django"]

# ---------------------------------------------------------------------------
# CORS — dev: accept all localhost origins
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
]
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Debug toolbar (dev only)
# ---------------------------------------------------------------------------
INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405

MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
] + MIDDLEWARE  # noqa: F405

INTERNAL_IPS = ["127.0.0.1"]

# ---------------------------------------------------------------------------
# Email — console backend (dev only)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Override logging level to DEBUG for local dev
# ---------------------------------------------------------------------------
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["django"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405
