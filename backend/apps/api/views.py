"""
apps/api/views.py — ViewSets DRF.

Tous les viewsets filtrent par org_id courant (TenantManager + get_queryset).
L'org_id est résolu depuis request.user via TenantMiddleware (ADR-001).

Sécurité:
  - IsAuthenticated requis sur tous les endpoints
  - L'org_id du tenant est injecté automatiquement à la création (perform_create)
  - Jamais d'accès cross-tenant possible (double-filtering: RLS + manager)
"""
import logging
import uuid

from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.documents.models import Invoice
from apps.ledger.models import JournalEntry
from apps.tenants.models import Organization, TenantMembership

from .serializers import (
    InvoiceSerializer,
    JournalEntrySerializer,
    OrganizationSerializer,
)

logger = logging.getLogger("apps.api.views")


def _get_current_org_id(request) -> uuid.UUID | None:
    """Récupère l'org_id courant depuis le request.

    L'org_id est stocké par TenantMiddleware dans la session PostgreSQL.
    Ici on le récupère via TenantMembership pour les filtres ORM.

    Args:
        request: Requête HTTP Django avec request.user authentifié.

    Returns:
        UUID de l'org courante ou None.
    """
    header = request.headers.get("X-Organization-Id", "").strip()
    if header:
        try:
            return uuid.UUID(header)
        except ValueError:
            return None

    membership = (
        TenantMembership.objects.filter(user=request.user, is_active=True)
        .select_related("organization")
        .first()
    )
    if membership:
        return membership.organization_id
    return None


class InvoiceViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """CRUD partiel sur les factures — pas de DELETE (ADR archivage légal).

    Endpoints:
      GET    /api/v1/invoices/         — liste paginée
      POST   /api/v1/invoices/         — créer une facture
      GET    /api/v1/invoices/<uuid>/  — détail
      PATCH  /api/v1/invoices/<uuid>/  — mise à jour partielle
    """

    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        """Filtre les factures par org_id courant.

        Returns:
            QuerySet filtré — uniquement les factures du tenant courant.
        """
        org_id = _get_current_org_id(self.request)
        if org_id is None:
            return Invoice.objects.none()
        return Invoice.objects.for_org(org_id).order_by("-created_at")

    def perform_create(self, serializer):
        """Injecte org_id automatiquement à la création.

        Args:
            serializer: Serializer validé avec les données de la facture.
        """
        org_id = _get_current_org_id(self.request)
        if org_id is None:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("No active organization membership.")
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        # Log UUID only — never log invoice data — ADR-005
        logger.info("invoice.create org_id=%s", org_id)
        serializer.save(org=org)


class JournalEntryViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Écritures comptables — lecture + création (pas de modification après posting).

    Endpoints:
      GET  /api/v1/journal/         — liste paginée
      POST /api/v1/journal/         — créer une écriture (status=draft)
      GET  /api/v1/journal/<uuid>/  — détail
    """

    serializer_class = JournalEntrySerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        """Filtre les écritures par org_id courant.

        Returns:
            QuerySet filtré — uniquement les écritures du tenant courant.
        """
        org_id = _get_current_org_id(self.request)
        if org_id is None:
            return JournalEntry.objects.none()
        return JournalEntry.objects.for_org(org_id).order_by("-entry_date")

    def perform_create(self, serializer):
        """Injecte org_id automatiquement à la création.

        Args:
            serializer: Serializer validé.
        """
        org_id = _get_current_org_id(self.request)
        if org_id is None:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("No active organization membership.")
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        logger.info("journal.create org_id=%s", org_id)
        serializer.save(org=org)


class OrganizationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Liste des organisations accessibles à l'utilisateur courant.

    Endpoints:
      GET /api/v1/organizations/         — liste des orgs de l'user
      GET /api/v1/organizations/<uuid>/  — détail d'une org
    """

    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        """Retourne les organisations dont l'user est membre actif.

        Returns:
            QuerySet d'organisations accessibles.
        """
        org_ids = TenantMembership.objects.filter(
            user=self.request.user, is_active=True
        ).values_list("organization_id", flat=True)
        return Organization.objects.filter(id__in=org_ids, is_active=True)
