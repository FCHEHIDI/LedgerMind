"""
apps/api/urls.py — Routes DRF v1.

Pattern:
  /api/v1/auth/token/            POST  — obtenir access + refresh tokens
  /api/v1/auth/token/refresh/    POST  — renouveler access token
  /api/v1/auth/token/blacklist/  POST  — blacklister refresh token (logout)
  /api/v1/invoices/              GET/POST
  /api/v1/invoices/<uuid>/       GET/PATCH
  /api/v1/journal/               GET/POST
  /api/v1/journal/<uuid>/        GET
  /api/v1/organizations/         GET (liste des orgs de l'utilisateur)
  /api/v1/dashboard/metrics/     GET (métriques tableau de bord)
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import DashboardMetricsView, DocumentUploadView, InvoiceViewSet, JournalEntryViewSet, OrganizationViewSet

router = DefaultRouter()
router.register(r"invoices", InvoiceViewSet, basename="invoice")
router.register(r"journal", JournalEntryViewSet, basename="journal")
router.register(r"organizations", OrganizationViewSet, basename="organization")

urlpatterns = [
    # JWT auth — ADR-002
    path(
        "auth/token/",
        TokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path(
        "auth/token/refresh/",
        TokenRefreshView.as_view(),
        name="token_refresh",
    ),
    path(
        "auth/token/blacklist/",
        TokenBlacklistView.as_view(),
        name="token_blacklist",
    ),
    path("dashboard/metrics/", DashboardMetricsView.as_view(), name="dashboard-metrics"),
    path("documents/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("", include(router.urls)),
]
