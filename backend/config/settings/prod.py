"""
Production settings for LedgerMind backend.

Usage:
    DJANGO_SETTINGS_MODULE=config.settings.prod

Additional required environment variables (beyond base.py):
  DOMAIN            — primary domain (e.g. ledgermind.example.com)
  DJANGO_ADMIN_URL  — obfuscated admin path (e.g. xk9q2p-admin/)
  SENTRY_DSN        — Sentry error tracking DSN (optional)
"""
import os

from .base import *  # noqa: F401, F403

DEBUG = False

DOMAIN = os.environ["DOMAIN"]
ALLOWED_HOSTS = [DOMAIN, f"www.{DOMAIN}"]

# ---------------------------------------------------------------------------
# HTTPS / HSTS
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 63072000  # 2 years
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [f"https://{DOMAIN}", f"https://www.{DOMAIN}"]

# ---------------------------------------------------------------------------
# CORS — prod: explicit frontend origin only
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    f"https://{DOMAIN}",
    f"https://www.{DOMAIN}",
]
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Admin URL obfuscation — ADR-002
# ---------------------------------------------------------------------------
DJANGO_ADMIN_URL = os.environ.get("DJANGO_ADMIN_URL", "admin/")

# ---------------------------------------------------------------------------
# Email — SMTP
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", f"noreply@{DOMAIN}")

# ---------------------------------------------------------------------------
# Sentry (optional)
# ---------------------------------------------------------------------------
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,  # NEVER send PII to Sentry — ADR-005
    )
