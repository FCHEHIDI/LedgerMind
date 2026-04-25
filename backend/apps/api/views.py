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

        from apps.ledger.models import JournalEntryAudit
        JournalEntryAudit.objects.create(
            entry=entry,
            action=JournalEntryAudit.ACTION_VALIDATED,
            from_status="draft",
            to_status="posted",
            performed_by=request.user,
        )

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

        from apps.ledger.models import JournalEntryAudit
        JournalEntryAudit.objects.create(
            entry=entry,
            action=JournalEntryAudit.ACTION_CANCELLED,
            from_status="draft",
            to_status="cancelled",
            performed_by=request.user,
        )

        serializer = self.get_serializer(entry)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # FEC Export — ADR-010
    # ------------------------------------------------------------------

    def _get_fec_queryset(self, request, date_from, date_to):
        """Retourne le QuerySet d'écritures pour le FEC.

        Args:
            request: Requête HTTP authentifiée.
            date_from: date de début (inclusive).
            date_to: date de fin (inclusive).

        Returns:
            QuerySet JournalEntry filtré, préfiltré posted.
        """
        org_id = _get_current_org_id(request)
        if org_id is None:
            return JournalEntry.objects.none()
        return (
            JournalEntry.objects
            .for_org(org_id)
            .filter(status="posted", entry_date__gte=date_from, entry_date__lte=date_to)
            .prefetch_related("lines", "invoice")
            .order_by("entry_date", "reference")
        )

    @action(detail=False, methods=["get"], url_path="export/fec")
    def export_fec(self, request):
        """Génère et retourne le Fichier des Écritures Comptables (FEC).

        Format DGFiP — ADR-010 :
          - Encodage UTF-8
          - Séparateur pipe |
          - Terminateur CRLF
          - 18 colonnes
          - Uniquement les écritures status=posted

        Query params:
          from (str): Date début YYYY-MM-DD (défaut: 1er janv. de l'année courante)
          to   (str): Date fin YYYY-MM-DD (défaut: aujourd'hui)

        Returns:
            Response 200 text/plain attachment.
            Response 400 si dates invalides.
        """
        import csv
        import io
        from datetime import date, datetime
        from django.http import StreamingHttpResponse

        today = date.today()
        raw_from = request.query_params.get("from", f"{today.year}-01-01")
        raw_to = request.query_params.get("to", today.isoformat())

        try:
            date_from = datetime.strptime(raw_from, "%Y-%m-%d").date()
            date_to = datetime.strptime(raw_to, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"error": "INVALID_DATE", "detail": "Utilisez le format YYYY-MM-DD."},
                status=400,
            )

        if date_from > date_to:
            return Response(
                {"error": "INVALID_RANGE", "detail": "'from' doit être antérieur à 'to'."},
                status=400,
            )

        entries = self._get_fec_queryset(request, date_from, date_to)
        rows = _build_fec_lines(entries)

        # Build FEC content in-memory (UTF-8, pipe-separated, CRLF)
        buf = io.StringIO()
        writer = csv.writer(
            buf, delimiter="|", lineterminator="\r\n",
            quoting=csv.QUOTE_NONE, escapechar="\\"
        )
        writer.writerow([
            "JournalCode", "JournalLib", "EcritureNum", "EcritureDate",
            "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib",
            "PieceRef", "PieceDate", "EcritureLib", "Debit", "Credit",
            "EcritureLet", "DateLet", "ValidDate", "Montantdevise", "Idevise",
        ])
        for row in rows:
            # Sanitize: no pipe characters allowed inside values (DGFiP spec)
            writer.writerow([v.replace("|", " ") for v in row])

        content = buf.getvalue()

        # Resolve SIREN from org
        org_id = _get_current_org_id(request)
        from apps.tenants.models import Organization as _Org
        try:
            org = _Org.objects.get(id=org_id)
            siren = (org.siren or "000000000").replace(" ", "")[:9]
        except _Org.DoesNotExist:
            siren = "000000000"

        filename = f"{siren}FEC{date_to.strftime('%Y%m%d')}.txt"
        logger.info(
            "fec.export org_id=%s from=%s to=%s lines=%s filename=%s",
            org_id, date_from, date_to, len(rows), filename,
        )

        response = StreamingHttpResponse(
            iter([content.encode("utf-8")]),
            content_type="text/plain; charset=utf-8",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(detail=False, methods=["get"], url_path="export/fec/validate")
    def validate_fec(self, request):
        """Valide le FEC avant remise au DGFiP.

        Vérifie la balance générale (∑ Débit == ∑ Crédit) et l'absence
        de lignes avec Debit=0 ET Credit=0.

        Query params:
          from (str): Date début YYYY-MM-DD
          to   (str): Date fin YYYY-MM-DD

        Returns:
            Response 200:
              {
                "is_valid": bool,
                "total_lines": int,
                "total_debit": "decimal",
                "total_credit": "decimal",
                "balance_ok": bool,
                "errors": [str]
              }
        """
        from datetime import date, datetime
        from decimal import Decimal

        today = date.today()
        raw_from = request.query_params.get("from", f"{today.year}-01-01")
        raw_to = request.query_params.get("to", today.isoformat())

        try:
            date_from = datetime.strptime(raw_from, "%Y-%m-%d").date()
            date_to = datetime.strptime(raw_to, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"error": "INVALID_DATE", "detail": "Utilisez le format YYYY-MM-DD."},
                status=400,
            )

        entries = self._get_fec_queryset(request, date_from, date_to)
        rows = _build_fec_lines(entries)

        errors: list[str] = []
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")

        for row in rows:
            debit = Decimal(row[11])
            credit = Decimal(row[12])
            ecriture_num = row[2]

            if debit == Decimal("0") and credit == Decimal("0"):
                errors.append(f"EcritureNum {ecriture_num}: Debit=0 ET Credit=0 interdit.")

            total_debit += debit
            total_credit += credit

        balance_ok = total_debit == total_credit
        if not balance_ok:
            errors.append(
                f"Déséquilibre général : ∑ Débit={total_debit} ≠ ∑ Crédit={total_credit}."
            )

        return Response({
            "is_valid": len(errors) == 0,
            "total_lines": len(rows),
            "total_debit": str(total_debit),
            "total_credit": str(total_credit),
            "balance_ok": balance_ok,
            "errors": errors,
        })

    # ------------------------------------------------------------------
    # Extourne — ADR-009
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"], url_path="reverse")
    def reverse_entry(self, request, pk=None):
        """Crée une écriture d'extourne (contre-écriture) à partir d'une écriture postée.

        L'écriture originale reste `posted` et immuable.
        Une nouvelle écriture `draft` est créée avec les débits/crédits inversés.
        L'opérateur doit ensuite valider la contre-écriture.

        Request body:
          {
            "reason": "Facture annulée par le fournisseur",   // requis
            "reversal_date": "2026-04-30"                     // optionnel, défaut: aujourd'hui
          }

        Returns:
            Response 201 avec la nouvelle JournalEntry draft (extourne).
            Response 400 si préconditions non remplies.
        """
        from datetime import date, datetime
        from decimal import Decimal

        entry = self.get_object()

        if entry.status != "posted":
            return Response(
                {
                    "error": "INVALID_STATUS",
                    "detail": "Seules les écritures validées (posted) peuvent être extournées.",
                },
                status=400,
            )

        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {"error": "REASON_REQUIRED", "detail": "Le motif de l'extourne est obligatoire."},
                status=400,
            )

        raw_date = request.data.get("reversal_date")
        if raw_date:
            try:
                reversal_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": "INVALID_DATE", "detail": "Format attendu: YYYY-MM-DD."},
                    status=400,
                )
        else:
            reversal_date = date.today()

        lines = list(entry.lines.all())
        if not lines:
            return Response(
                {"error": "NO_LINES", "detail": "L'écriture ne contient aucune ligne."},
                status=400,
            )

        # Create the reversal entry
        from apps.ledger.models import AccountEntry, JournalEntryAudit

        reversal_reference = f"EXT-{entry.reference or str(entry.id)[:8]}"

        reversal = JournalEntry.objects.create(
            org=entry.org,
            invoice=entry.invoice,
            reference=reversal_reference[:100],
            journal_code=entry.journal_code,
            entry_date=reversal_date,
            status="draft",
        )

        # Invert debit/credit on each line
        for line in lines:
            AccountEntry.objects.create(
                org=entry.org,
                journal_entry=reversal,
                account_code=line.account_code,
                account_label=line.account_label,
                debit=line.credit,   # inverted
                credit=line.debit,   # inverted
            )

        # Audit trail on the original entry
        JournalEntryAudit.objects.create(
            entry=entry,
            action=JournalEntryAudit.ACTION_REVERSED,
            from_status="posted",
            to_status="posted",
            performed_by=request.user,
            reason=reason[:500],
        )
        # Audit trail on the new reversal entry
        JournalEntryAudit.objects.create(
            entry=reversal,
            action=JournalEntryAudit.ACTION_CREATED,
            from_status="",
            to_status="draft",
            performed_by=request.user,
            reason=f"Extourne de {entry.id}: {reason}"[:500],
        )

        logger.info(
            "journal.reversed original=%s reversal=%s org=%s",
            entry.id, reversal.id, entry.org_id,
        )

        serializer = self.get_serializer(reversal)
        return Response(serializer.data, status=201)


_JOURNAL_LABELS: dict[str, str] = {
    "ACH": "Achats",
    "VTE": "Ventes",
    "BQ": "Banque",
    "OD": "Opérations diverses",
    "AN": "À-nouveaux",
    "PAI": "Paiements",
}

# Comptes collectifs tiers (fournisseurs / clients) — nécessitent CompAuxNum
_TIERS_PREFIXES = ("401", "411")


def _fec_date(d) -> str:
    """Formate une date en AAAAMMJJ pour le FEC.

    Args:
        d: date ou None.

    Returns:
        Chaîne AAAAMMJJ ou vide.
    """
    if d is None:
        return ""
    return d.strftime("%Y%m%d")


def _fec_amount(value) -> str:
    """Formate un montant en 2 décimales avec point.

    Args:
        value: Decimal ou numérique.

    Returns:
        Chaîne ex: '1200.00'.
    """
    from decimal import Decimal
    return f"{Decimal(value):.2f}"


def _build_fec_lines(entries) -> list[list[str]]:
    """Construit les lignes FEC (hors en-tête) depuis les JournalEntry.

    Chaque AccountEntry génère une ligne FEC.
    Les colonnes respectent strictement l'ADR-010 / spécification DGFiP.

    Args:
        entries: QuerySet de JournalEntry avec prefetch_related('lines', 'invoice').

    Returns:
        Liste de listes de 18 valeurs (str) triées par date puis référence.
    """
    rows: list[list[str]] = []

    for entry in entries:
        journal_lib = _JOURNAL_LABELS.get(entry.journal_code, entry.journal_code)
        piece_ref = entry.reference or str(entry.id)[:8]
        piece_date = _fec_date(entry.entry_date)
        valid_date = _fec_date(entry.updated_at.date() if entry.updated_at else entry.entry_date)
        ecriture_lib = f"{journal_lib} — {piece_ref}"

        # Données tiers issues de la facture liée (peut être null)
        invoice = getattr(entry, "invoice", None)
        vendor_name = (invoice.vendor_name if invoice and hasattr(invoice, "vendor_name") else "") or ""
        inv_number = (invoice.invoice_number if invoice and hasattr(invoice, "invoice_number") else "") or ""

        for line in entry.lines.all():
            # Compte auxiliaire : requis pour comptes collectifs 401/411
            comp_aux_num = ""
            comp_aux_lib = ""
            if line.account_code.startswith(_TIERS_PREFIXES):
                comp_aux_num = inv_number[:20] if inv_number else piece_ref[:20]
                comp_aux_lib = vendor_name[:99] if vendor_name else ""

            row = [
                entry.journal_code[:6],          # 1  JournalCode
                journal_lib[:99],                  # 2  JournalLib
                piece_ref[:10],                    # 3  EcritureNum
                piece_date,                        # 4  EcritureDate
                line.account_code[:20],            # 5  CompteNum
                (line.account_label or line.account_code)[:99],  # 6  CompteLib
                comp_aux_num,                      # 7  CompAuxNum
                comp_aux_lib,                      # 8  CompAuxLib
                piece_ref[:99],                    # 9  PieceRef
                piece_date,                        # 10 PieceDate
                ecriture_lib[:99],                 # 11 EcritureLib
                _fec_amount(line.debit),           # 12 Debit
                _fec_amount(line.credit),          # 13 Credit
                "",                                # 14 EcritureLet
                "",                                # 15 DateLet
                valid_date,                        # 16 ValidDate
                "",                                # 17 Montantdevise
                "",                                # 18 Idevise
            ]
            rows.append(row)

    return rows


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
