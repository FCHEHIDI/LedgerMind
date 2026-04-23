"""
Root URL configuration for LedgerMind backend.

URL patterns:
  /admin/          — Django admin (2FA + IP allowlist via Traefik)
  /api/v1/         — DRF REST API
  /api/token/      — SimpleJWT access token
  /api/token/refresh/ — SimpleJWT refresh token
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.api.urls")),
]
