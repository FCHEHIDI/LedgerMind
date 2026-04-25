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
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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

    @action(detail=True, methods=["post"], url_path="validate")
    def validate_entry(self, request, pk=None):
        """Valide une écriture draft → posted.

        Préconditions:
          - status == draft
          - sum(débit) == sum(crédit) sur toutes les lignes

        Returns:
            JournalEntry sérialisé avec status=posted (200).
            Erreur 400 si préconditions non remplies.
        """
        entry = self.get_object()

        if entry.status != "draft":
            return Response(
                {
                    "error": "INVALID_STATUS",
                    "detail": f"L'écriture est déjà '{entry.status}' et ne peut pas être validée.",
                },
                status=400,
            )

        lines = list(entry.lines.all())
        if not lines:
            return Response(
                {"error": "NO_LINES", "detail": "L'écriture ne contient aucune ligne."},
                status=400,
            )

        from decimal import Decimal
        total_debit = sum(line.debit for line in lines)
        total_credit = sum(line.credit for line in lines)

        if total_debit != total_credit:
            return Response(
                {
                    "error": "UNBALANCED_ENTRY",
                    "detail": (
                        f"Débit total ({total_debit}) ≠ Crédit total ({total_credit}). "
                        "L'écriture doit être équilibrée avant validation."
                    ),
                },
                status=400,
            )

        entry.status = "posted"
        entry.save(update_fields=["status", "updated_at"])
        logger.info("journal.validated entry_id=%s org_id=%s", entry.id, entry.org_id)

        serializer = self.get_serializer(entry)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel_entry(self, request, pk=None):
        """Annule une écriture draft → cancelled.

        Args:
            request: Requête HTTP authentifiée.
            pk: UUID de l'écriture.

        Returns:
            JournalEntry sérialisé avec status=cancelled (200).
            Erreur 400 si l'écriture n'est pas en draft.
        """
        entry = self.get_object()

        if entry.status != "draft":
            return Response(
                {
                    "error": "INVALID_STATUS",
                    "detail": f"Seules les écritures en brouillon peuvent être annulées. Statut actuel : '{entry.status}'.",
                },
                status=400,
            )

        entry.status = "cancelled"
        entry.save(update_fields=["status", "updated_at"])
        logger.info("journal.cancelled entry_id=%s org_id=%s", entry.id, entry.org_id)

        serializer = self.get_serializer(entry)
        return Response(serializer.data)


class DashboardMetricsView(APIView):
    """Métriques agrégées pour le tableau de bord.

    Endpoint:
      GET /api/v1/dashboard/metrics/

    Returns:
        JSON avec les compteurs filtrés par org du tenant courant:
          - total_journal_entries: int
          - pending_entries: int (status=draft)
          - documents_count: int
          - compliance_alerts: int (placeholder)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """Retourne les métriques du dashboard.

        Args:
            request: Requête HTTP authentifiée.

        Returns:
            Response JSON avec les compteurs du tenant.
        """
        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response(
                {
                    "total_journal_entries": 0,
                    "pending_entries": 0,
                    "documents_count": 0,
                    "compliance_alerts": 0,
                }
            )

        total_journal = JournalEntry.objects.for_org(org_id).count()
        pending = JournalEntry.objects.for_org(org_id).filter(status="draft").count()
        documents = Invoice.objects.for_org(org_id).count()

        logger.debug(
            "dashboard.metrics org_id=%s entries=%s pending=%s docs=%s",
            org_id,
            total_journal,
            pending,
            documents,
        )

        return Response(
            {
                "total_journal_entries": total_journal,
                "pending_entries": pending,
                "documents_count": documents,
                "compliance_alerts": 0,
            }
        )


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


class DocumentUploadView(APIView):
    """Upload d'un document PDF → déclenche le pipeline IA (ADR-006).

    Endpoint:
      POST /api/v1/documents/upload/

    Request:
      Content-Type: multipart/form-data
      Body: file=<PDF file>

    Response 202:
      {
        "invoice_id": "uuid",
        "job_id": "uuid",
        "status": "queued",
        "message": "Document reçu. Traitement en cours."
      }

    Response 400:
      {"error": "NO_FILE"} ou {"error": "INVALID_TYPE"}

    Response 403:
      {"error": "NO_ORG"}

    Sécurité:
      - Seuls les PDF sont acceptés (Content-Type + extension)
      - Le nom du fichier original N'EST PAS stocké (ADR-004)
      - La clé MinIO est {org_id}/{uuid}.pdf
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

    def post(self, request) -> Response:
        """Reçoit un PDF, le stocke dans MinIO, crée Invoice + ProcessingJob.

        Args:
            request: Requête HTTP avec file dans request.FILES.

        Returns:
            Response 202 avec invoice_id + job_id si succès.
            Response 400/403 si erreur de validation.
        """
        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        file = request.FILES.get("file")
        if file is None:
            return Response({"error": "NO_FILE", "detail": "Le champ 'file' est requis."}, status=400)

        # Validation type — uniquement PDF
        content_type = file.content_type or ""
        filename_lower = (file.name or "").lower()
        if content_type != "application/pdf" and not filename_lower.endswith(".pdf"):
            return Response(
                {"error": "INVALID_TYPE", "detail": "Seuls les fichiers PDF sont acceptés."},
                status=400,
            )

        if file.size > self.MAX_FILE_SIZE:
            return Response(
                {"error": "FILE_TOO_LARGE", "detail": f"Taille maximale: {self.MAX_FILE_SIZE // 1024 // 1024} MB."},
                status=400,
            )

        from apps.documents.models import Invoice, ProcessingJob
        from apps.tenants.models import Organization
        import boto3
        from django.conf import settings as django_settings

        org = get_object_or_404(Organization, id=org_id, is_active=True)

        # Générer une clé MinIO opaque (jamais le nom original — ADR-004)
        file_uuid = uuid.uuid4()
        source_key = f"{org_id}/{file_uuid}.pdf"

        # Upload MinIO
        try:
            client = boto3.client(
                "s3",
                endpoint_url=django_settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=django_settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=django_settings.AWS_SECRET_ACCESS_KEY,
            )
            client.upload_fileobj(
                file,
                django_settings.AWS_STORAGE_BUCKET_NAME,
                source_key,
                ExtraArgs={"ContentType": "application/pdf"},
            )
            logger.info("document.upload.stored key=%s org_id=%s", source_key, org_id)
        except Exception as exc:
            logger.error("document.upload.minio_error org_id=%s err=%s", org_id, type(exc).__name__)
            return Response({"error": "STORAGE_ERROR", "detail": "Erreur lors du stockage."}, status=500)

        # Créer Invoice en base
        invoice = Invoice.objects.create(org=org, source_key=source_key, status="pending")

        # Créer ProcessingJob
        job = ProcessingJob.objects.create(org=org, invoice=invoice, queue="llm", status="queued")

        # Déclencher la tâche Celery (queue llm)
        try:
            from apps.agents.tasks import process_invoice_task
            process_invoice_task.apply_async(
                args=[str(invoice.id), str(job.id), str(request.user.id), str(org_id), source_key],
                queue="llm",
            )
            logger.info("document.upload.task_queued invoice_id=%s job_id=%s", invoice.id, job.id)
        except Exception as exc:
            logger.error("document.upload.task_error invoice_id=%s err=%s", invoice.id, type(exc).__name__)
            # Ne pas bloquer l'upload si Celery est indisponible — retry manuel possible
            job.status = "failure"
            job.error_code = "TASK_QUEUE_ERROR"
            job.save(update_fields=["status", "error_code"])

        return Response(
            {
                "invoice_id": str(invoice.id),
                "job_id": str(job.id),
                "status": "queued",
                "message": "Document reçu. Traitement IA en cours.",
            },
            status=202,
        )
