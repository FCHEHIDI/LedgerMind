"""
apps/api/urls.py — Routes DRF v1.

Pattern:
  /api/v1/auth/token/            POST  — obtenir access + refresh tokens
  /api/v1/auth/token/refresh/    POST  — renouveler access token
  /api/v1/auth/token/blacklist/  POST  — blacklister refresh token (logout)
  /api/v1/auth/request-erasure/  POST  — demande effacement RGPD Art.17
  /api/v1/auth/erasure/<id>/process/ POST — admin: traite une demande (superuser)
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

from .views import (
    BatchDocumentUploadView, BankReconciliationViewSet, BilanView,
    ChartOfAccountsViewSet, CompteDeResultatView, DashboardMetricsView,
    DocumentUploadView, GDPRErasureProcessView, GDPRErasureRequestView,
    InvoiceViewSet, JournalEntryViewSet,
    LetterageViewSet, OrgCreationRequestViewSet, OrganizationViewSet, TvaCA3View,
)

router = DefaultRouter()
router.register(r"invoices", InvoiceViewSet, basename="invoice")
router.register(r"journal", JournalEntryViewSet, basename="journal")
router.register(r"organizations", OrganizationViewSet, basename="organization")
router.register(r"org-requests", OrgCreationRequestViewSet, basename="org-request")
router.register(r"lettrage", LetterageViewSet, basename="lettrage")
router.register(r"bank-statements", BankReconciliationViewSet, basename="bank-statement")
router.register(r"chart", ChartOfAccountsViewSet, basename="chart")

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
    path("documents/upload/batch/", BatchDocumentUploadView.as_view(), name="document-upload-batch"),
    path("tva/ca3/", TvaCA3View.as_view(), name="tva-ca3"),
    path("reports/compte-de-resultat/", CompteDeResultatView.as_view(), name="compte-de-resultat"),
    path("reports/bilan/", BilanView.as_view(), name="bilan"),
    # RGPD — Droit à l'effacement (Art. 17)
    path("auth/request-erasure/", GDPRErasureRequestView.as_view(), name="gdpr-erasure-request"),
    path("auth/erasure/<str:pk>/process/", GDPRErasureProcessView.as_view(), name="gdpr-erasure-process"),
    path("", include(router.urls)),
]
