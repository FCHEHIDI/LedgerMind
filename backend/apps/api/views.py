"""
apps/api/views.py — ViewSets DRF.

Tous les viewsets filtrent par org_id courant (TenantManager + get_queryset).
L'org_id est résolu depuis request.user via TenantMiddleware (ADR-001).

Sécurité:
  - IsAuthenticated requis sur tous les endpoints
  - L'org_id du tenant est injecté automatiquement à la création (perform_create)
  - Jamais d'accès cross-tenant possible (double-filtering: RLS + manager)
"""
import csv
import io
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Invoice
from apps.ledger.models import ChartOfAccounts, JournalEntry
from apps.tenants.models import Organization, TenantMembership

from .serializers import (
    ChartOfAccountsSerializer,
    InvoiceSerializer,
    JournalEntrySerializer,
    OrganizationSerializer,
)

logger = logging.getLogger("apps.api.views")


def _get_current_org_id(request) -> uuid.UUID | None:
    """Récupère l'org_id courant depuis le request.

    L'org_id est stocké par TenantMiddleware dans la session PostgreSQL.
    Ici on le récupère via TenantMembership pour les filtres ORM.

    Sécurité (OWASP A01 — Broken Access Control) : lorsque le header
    X-Organization-Id est fourni, on vérifie que l'utilisateur courant
    est bien membre actif de cette organisation avant de retourner l'UUID.
    Sans cette vérification, un utilisateur authentifié pourrait fournir
    l'UUID d'une org tierce et y écrire des données (IDOR).

    Args:
        request: Requête HTTP Django avec request.user authentifié.

    Returns:
        UUID de l'org courante ou None si introuvable / accès non autorisé.
    """
    header = request.headers.get("X-Organization-Id", "").strip()
    if header:
        try:
            org_id = uuid.UUID(header)
        except ValueError:
            return None
        # Validate that the authenticated user actually belongs to this org
        is_member = TenantMembership.objects.filter(
            user=request.user,
            organization_id=org_id,
            is_active=True,
        ).exists()
        return org_id if is_member else None

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
    # Main courante, Grand Livre, Balance — rapports comptables
    # ------------------------------------------------------------------

    def _parse_date_range(self, request):
        """Parse et valide les paramètres de période from/to depuis la requête.

        Args:
            request: Requête HTTP avec query params 'from' et 'to' (YYYY-MM-DD).

        Returns:
            Tuple (date_from, date_to, error_response) où error_response est None
            si la validation réussit, sinon une Response DRF 400.
        """
        from datetime import date, datetime
        today = date.today()
        raw_from = request.query_params.get("from", f"{today.year}-01-01")
        raw_to = request.query_params.get("to", today.isoformat())
        try:
            date_from = datetime.strptime(raw_from, "%Y-%m-%d").date()
            date_to = datetime.strptime(raw_to, "%Y-%m-%d").date()
        except ValueError:
            return None, None, Response(
                {"error": "INVALID_DATE", "detail": "Utilisez le format YYYY-MM-DD."},
                status=400,
            )
        if date_from > date_to:
            return None, None, Response(
                {"error": "INVALID_RANGE", "detail": "'from' doit être antérieur à 'to'."},
                status=400,
            )
        return date_from, date_to, None

    def _get_account_entries(self, request, date_from, date_to, journal_code=None):
        """QuerySet d'AccountEntry filtrées par org, période et statut posted.

        Args:
            request: Requête HTTP authentifiée.
            date_from: Date de début inclusive.
            date_to: Date de fin inclusive.
            journal_code: Code journal optionnel pour filtrer (ex: 'BQ').

        Returns:
            QuerySet AccountEntry avec select_related('journal_entry'),
            ordonné par date → référence → id → account_code.
        """
        from apps.ledger.models import AccountEntry
        org_id = _get_current_org_id(request)
        if org_id is None:
            return AccountEntry.objects.none()
        qs = (
            AccountEntry.objects
            .filter(
                org_id=org_id,
                journal_entry__status="posted",
                journal_entry__entry_date__gte=date_from,
                journal_entry__entry_date__lte=date_to,
            )
            .select_related("journal_entry")
            .order_by(
                "journal_entry__entry_date",
                "journal_entry__reference",
                "journal_entry__id",
                "account_code",
            )
        )
        if journal_code:
            qs = qs.filter(journal_entry__journal_code=journal_code)
        return qs

    @action(detail=False, methods=["get"], url_path="export/main-courante")
    def export_main_courante(self, request):
        """Main courante — journal chronologique toutes pièces confondues.

        Liste toutes les AccountEntry d'écritures postées sur la période,
        triées chronologiquement, avec le solde cumulatif courant.
        Filtrable par journal_code (ex: 'BQ' pour rapprochement bancaire).

        Query params:
          from (str): Date début YYYY-MM-DD (défaut: 1er janv. de l'année courante)
          to   (str): Date fin YYYY-MM-DD (défaut: aujourd'hui)
          journal_code (str): Filtrer par journal (ex: 'BQ', 'ACH', 'VTE')
          format (str): 'json' (défaut) ou 'csv' (avec BOM UTF-8 pour Excel)

        Returns:
            JSON 200 avec period, total_lines, total_debit, total_credit, lines[].
            CSV 200 avec colonnes: Date, Journal, Référence, Compte, Libellé,
                                   Débit, Crédit, Solde cumulatif.
            Response 400 si dates invalides.
        """
        from decimal import Decimal

        date_from, date_to, err = self._parse_date_range(request)
        if err:
            return err

        journal_code = request.query_params.get("journal_code", "").strip().upper() or None
        output_format = request.query_params.get("format", "json").lower()

        entries = list(self._get_account_entries(request, date_from, date_to, journal_code))

        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        running_balance = Decimal("0.00")
        lines = []

        for ae in entries:
            je = ae.journal_entry
            debit = ae.debit or Decimal("0.00")
            credit = ae.credit or Decimal("0.00")
            running_balance += debit - credit
            total_debit += debit
            total_credit += credit
            lines.append({
                "date": je.entry_date.isoformat(),
                "journal_code": je.journal_code,
                "reference": je.reference or "",
                "account_code": ae.account_code,
                "account_label": ae.account_label or "",
                "debit": f"{debit:.2f}",
                "credit": f"{credit:.2f}",
                "running_balance": f"{running_balance:.2f}",
            })

        org_id = _get_current_org_id(request)
        logger.info(
            "main_courante.export org_id=%s from=%s to=%s lines=%d journal=%s",
            org_id, date_from, date_to, len(lines), journal_code,
        )

        if output_format == "csv":
            import csv
            import io
            from django.http import StreamingHttpResponse
            buf = io.StringIO()
            writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
            writer.writerow([
                "Date", "Journal", "Référence", "Compte",
                "Libellé", "Débit", "Crédit", "Solde cumulatif",
            ])
            for line in lines:
                writer.writerow([
                    line["date"], line["journal_code"], line["reference"],
                    line["account_code"], line["account_label"],
                    line["debit"], line["credit"], line["running_balance"],
                ])
            content = buf.getvalue()
            resp = StreamingHttpResponse(
                iter([content.encode("utf-8-sig")]),  # BOM pour Excel
                content_type="text/csv; charset=utf-8",
            )
            resp["Content-Disposition"] = (
                f'attachment; filename="main_courante_{date_from}_{date_to}.csv"'
            )
            return resp

        return Response({
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "journal_code": journal_code,
            "total_lines": len(lines),
            "total_debit": f"{total_debit:.2f}",
            "total_credit": f"{total_credit:.2f}",
            "lines": lines,
        })

    @action(detail=False, methods=["get"], url_path="export/grand-livre")
    def export_grand_livre(self, request):
        """Grand Livre — écritures détaillées regroupées par compte PCG.

        Pour chaque compte rencontré sur la période, liste les écritures
        chronologiques avec sous-total débit/crédit/solde.

        Query params:
          from (str): Date début YYYY-MM-DD
          to   (str): Date fin YYYY-MM-DD
          account_prefix (str): Filtrer par préfixe PCG (ex: '4' pour tiers,
                                '512' pour banque uniquement)
          format (str): 'json' (défaut) ou 'csv'

        Returns:
            JSON 200 avec period, total_accounts, accounts[].
            CSV 200 avec sous-totaux par compte et ligne vide de séparation.
            Response 400 si dates invalides.
        """
        from decimal import Decimal

        date_from, date_to, err = self._parse_date_range(request)
        if err:
            return err

        account_prefix = request.query_params.get("account_prefix", "").strip()
        output_format = request.query_params.get("format", "json").lower()

        qs = self._get_account_entries(request, date_from, date_to)
        if account_prefix:
            qs = qs.filter(account_code__startswith=account_prefix)

        # Regroupement par compte en Python (ordre chronologique préservé)
        accounts_dict: dict[str, dict] = {}
        for ae in qs:
            je = ae.journal_entry
            code = ae.account_code
            if code not in accounts_dict:
                accounts_dict[code] = {
                    "account_code": code,
                    "account_label": ae.account_label or "",
                    "total_debit": Decimal("0.00"),
                    "total_credit": Decimal("0.00"),
                    "lines": [],
                }
            debit = ae.debit or Decimal("0.00")
            credit = ae.credit or Decimal("0.00")
            accounts_dict[code]["total_debit"] += debit
            accounts_dict[code]["total_credit"] += credit
            # Mettre à jour le libellé si une valeur est disponible
            if not accounts_dict[code]["account_label"] and ae.account_label:
                accounts_dict[code]["account_label"] = ae.account_label
            accounts_dict[code]["lines"].append({
                "date": je.entry_date.isoformat(),
                "journal_code": je.journal_code,
                "reference": je.reference or "",
                "debit": f"{debit:.2f}",
                "credit": f"{credit:.2f}",
            })

        accounts = []
        for acc in accounts_dict.values():
            solde = acc["total_debit"] - acc["total_credit"]
            accounts.append({
                "account_code": acc["account_code"],
                "account_label": acc["account_label"],
                "total_debit": f"{acc['total_debit']:.2f}",
                "total_credit": f"{acc['total_credit']:.2f}",
                "solde": f"{solde:.2f}",
                "lines": acc["lines"],
            })

        org_id = _get_current_org_id(request)
        logger.info(
            "grand_livre.export org_id=%s from=%s to=%s accounts=%d prefix=%s",
            org_id, date_from, date_to, len(accounts), account_prefix or None,
        )

        if output_format == "csv":
            import csv
            import io
            from django.http import StreamingHttpResponse
            buf = io.StringIO()
            writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
            writer.writerow([
                "Compte", "Libellé compte", "Date", "Journal",
                "Référence", "Débit", "Crédit",
            ])
            for acc in accounts:
                for line in acc["lines"]:
                    writer.writerow([
                        acc["account_code"], acc["account_label"],
                        line["date"], line["journal_code"], line["reference"],
                        line["debit"], line["credit"],
                    ])
                # Sous-total compte
                writer.writerow([
                    acc["account_code"], f"TOTAL {acc['account_label']}",
                    "", "", "",
                    acc["total_debit"], acc["total_credit"],
                ])
                writer.writerow([])  # Séparateur entre comptes
            content = buf.getvalue()
            resp = StreamingHttpResponse(
                iter([content.encode("utf-8-sig")]),
                content_type="text/csv; charset=utf-8",
            )
            resp["Content-Disposition"] = (
                f'attachment; filename="grand_livre_{date_from}_{date_to}.csv"'
            )
            return resp

        return Response({
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "account_prefix": account_prefix or None,
            "total_accounts": len(accounts),
            "accounts": accounts,
        })

    @action(detail=False, methods=["get"], url_path="export/balance")
    def export_balance(self, request):
        """Balance des comptes — synthèse débit/crédit/solde par compte PCG.

        Une ligne par compte avec totaux cumulés sur la période.
        Conforme au format balance de vérification (balance avant inventaire).
        Un total général valide l'équilibre du plan comptable (is_balanced).

        Query params:
          from (str): Date début YYYY-MM-DD
          to   (str): Date fin YYYY-MM-DD
          account_prefix (str): Filtrer par préfixe PCG (ex: '6' charges, '7' produits)
          format (str): 'json' (défaut) ou 'csv'

        Returns:
            JSON 200:
              {
                "period": {"from": "...", "to": "..."},
                "is_balanced": true,
                "total_debit": "24000.00",
                "total_credit": "24000.00",
                "accounts": [
                  {
                    "account_code": "401",
                    "account_label": "Fournisseurs",
                    "total_debit": "1200.00",
                    "total_credit": "1200.00",
                    "solde_debiteur": "0.00",
                    "solde_crediteur": "0.00"
                  }
                ]
              }
            CSV 200 avec ligne de total général.
            Response 400 si dates invalides.
            Response 403 si org introuvable.
        """
        from decimal import Decimal
        from django.db.models import Max, Sum

        date_from, date_to, err = self._parse_date_range(request)
        if err:
            return err

        account_prefix = request.query_params.get("account_prefix", "").strip()
        output_format = request.query_params.get("format", "json").lower()

        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        from apps.ledger.models import AccountEntry
        qs = AccountEntry.objects.filter(
            org_id=org_id,
            journal_entry__status="posted",
            journal_entry__entry_date__gte=date_from,
            journal_entry__entry_date__lte=date_to,
        )
        if account_prefix:
            qs = qs.filter(account_code__startswith=account_prefix)

        rows = (
            qs
            .values("account_code")
            .annotate(
                total_debit=Sum("debit"),
                total_credit=Sum("credit"),
                account_label=Max("account_label"),
            )
            .order_by("account_code")
        )

        grand_total_debit = Decimal("0.00")
        grand_total_credit = Decimal("0.00")
        accounts = []

        for row in rows:
            td = row["total_debit"] or Decimal("0.00")
            tc = row["total_credit"] or Decimal("0.00")
            solde = td - tc
            grand_total_debit += td
            grand_total_credit += tc
            accounts.append({
                "account_code": row["account_code"],
                "account_label": row["account_label"] or "",
                "total_debit": f"{td:.2f}",
                "total_credit": f"{tc:.2f}",
                "solde_debiteur": f"{solde:.2f}" if solde > 0 else "0.00",
                "solde_crediteur": f"{abs(solde):.2f}" if solde < 0 else "0.00",
            })

        is_balanced = grand_total_debit == grand_total_credit
        logger.info(
            "balance.export org_id=%s from=%s to=%s accounts=%d balanced=%s",
            org_id, date_from, date_to, len(accounts), is_balanced,
        )

        if output_format == "csv":
            import csv
            import io
            from django.http import StreamingHttpResponse
            buf = io.StringIO()
            writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
            writer.writerow([
                "Compte", "Libellé", "Total Débit", "Total Crédit",
                "Solde Débiteur", "Solde Créditeur",
            ])
            for acc in accounts:
                writer.writerow([
                    acc["account_code"], acc["account_label"],
                    acc["total_debit"], acc["total_credit"],
                    acc["solde_debiteur"], acc["solde_crediteur"],
                ])
            # Ligne de total général
            writer.writerow([
                "TOTAL GÉNÉRAL", "",
                f"{grand_total_debit:.2f}", f"{grand_total_credit:.2f}",
                "", "",
            ])
            content = buf.getvalue()
            resp = StreamingHttpResponse(
                iter([content.encode("utf-8-sig")]),
                content_type="text/csv; charset=utf-8",
            )
            resp["Content-Disposition"] = (
                f'attachment; filename="balance_{date_from}_{date_to}.csv"'
            )
            return resp

        return Response({
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "account_prefix": account_prefix or None,
            "is_balanced": is_balanced,
            "total_debit": f"{grand_total_debit:.2f}",
            "total_credit": f"{grand_total_credit:.2f}",
            "accounts": accounts,
        })

    # ------------------------------------------------------------------
    # Journaux auxiliaires
    # ------------------------------------------------------------------

    @action(detail=False, methods=["get"], url_path="export/journaux")
    def export_journaux_auxiliaires(self, request):
        """Journal auxiliaire détaillé — pièces et lignes pour un journal donné.

        Retourne l'ensemble des écritures postées d'un journal (ACH, VTE, BQ, OD…)
        sur la période, avec leurs lignes de compte et sous-totaux par pièce.
        Utilisable pour imprimer ou exporter le journal mensuel.

        Query params:
          journal_code (str): Code journal requis (ACH, VTE, BQ, OD, AN, PAI)
          from (str): Date début YYYY-MM-DD (défaut: 1er janv. de l'année courante)
          to   (str): Date fin YYYY-MM-DD (défaut: aujourd'hui)
          format (str): 'json' (défaut) ou 'csv'

        Returns:
            JSON 200:
              {
                "period": {"from": "...", "to": "..."},
                "journal_code": "ACH",
                "journal_label": "Achats",
                "total_entries": 5,
                "total_debit": "12000.00",
                "total_credit": "12000.00",
                "entries": [
                  {
                    "id": "uuid",
                    "entry_date": "2026-04-01",
                    "reference": "FAC-001",
                    "total_debit": "12000.00",
                    "total_credit": "12000.00",
                    "lines": [
                      {"account_code": "607", "account_label": "...",
                       "debit": "10000.00", "credit": "0.00"},
                      ...
                    ]
                  }
                ]
              }
            CSV 200 avec sous-total par pièce et total général.
            Response 400 si journal_code manquant ou dates invalides.
        """
        from decimal import Decimal

        journal_code = request.query_params.get("journal_code", "").strip().upper()
        if not journal_code:
            return Response(
                {
                    "error": "JOURNAL_CODE_REQUIRED",
                    "detail": (
                        "Le paramètre 'journal_code' est obligatoire. "
                        "Valeurs valides: ACH, VTE, BQ, OD, AN, PAI."
                    ),
                },
                status=400,
            )

        valid_codes = set(_JOURNAL_LABELS.keys())
        if journal_code not in valid_codes:
            return Response(
                {
                    "error": "INVALID_JOURNAL_CODE",
                    "detail": f"Code journal inconnu. Valeurs valides: {sorted(valid_codes)}.",
                },
                status=400,
            )

        date_from, date_to, err = self._parse_date_range(request)
        if err:
            return err

        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        entries = (
            JournalEntry.objects
            .filter(
                org_id=org_id,
                journal_code=journal_code,
                status="posted",
                entry_date__gte=date_from,
                entry_date__lte=date_to,
            )
            .prefetch_related("lines")
            .order_by("entry_date", "reference", "id")
        )

        journal_label = _JOURNAL_LABELS.get(journal_code, journal_code)
        grand_debit = Decimal("0.00")
        grand_credit = Decimal("0.00")
        output_format = request.query_params.get("format", "json").lower()
        entries_data = []

        for entry in entries:
            lines = list(entry.lines.all())
            entry_debit = sum(l.debit for l in lines)
            entry_credit = sum(l.credit for l in lines)
            grand_debit += entry_debit
            grand_credit += entry_credit
            entries_data.append({
                "id": str(entry.id),
                "entry_date": entry.entry_date.isoformat(),
                "reference": entry.reference or "",
                "total_debit": f"{entry_debit:.2f}",
                "total_credit": f"{entry_credit:.2f}",
                "lines": [
                    {
                        "account_code": l.account_code,
                        "account_label": l.account_label or "",
                        "debit": f"{l.debit:.2f}",
                        "credit": f"{l.credit:.2f}",
                    }
                    for l in lines
                ],
            })

        logger.info(
            "journaux.export org_id=%s journal=%s from=%s to=%s entries=%d",
            org_id, journal_code, date_from, date_to, len(entries_data),
        )

        if output_format == "csv":
            import csv
            import io
            from django.http import StreamingHttpResponse

            buf = io.StringIO()
            writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
            writer.writerow([
                "Date", "Référence", "Compte", "Libellé", "Débit", "Crédit",
            ])
            for ed in entries_data:
                for line in ed["lines"]:
                    writer.writerow([
                        ed["entry_date"], ed["reference"],
                        line["account_code"], line["account_label"],
                        line["debit"], line["credit"],
                    ])
                # Sous-total pièce
                writer.writerow([
                    ed["entry_date"],
                    f"TOTAL PIÈCE {ed['reference']}",
                    "", "", ed["total_debit"], ed["total_credit"],
                ])
                writer.writerow([])
            # Total journal
            writer.writerow(["TOTAL JOURNAL", journal_label, "", "",
                             f"{grand_debit:.2f}", f"{grand_credit:.2f}"])

            resp = StreamingHttpResponse(
                iter([buf.getvalue().encode("utf-8-sig")]),
                content_type="text/csv; charset=utf-8",
            )
            resp["Content-Disposition"] = (
                f'attachment; filename="journal_{journal_code.lower()}_{date_from}_{date_to}.csv"'
            )
            return resp

        return Response({
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "journal_code": journal_code,
            "journal_label": journal_label,
            "total_entries": len(entries_data),
            "total_debit": f"{grand_debit:.2f}",
            "total_credit": f"{grand_credit:.2f}",
            "entries": entries_data,
        })

    @action(detail=False, methods=["get"], url_path="export/journaux-summary")
    def export_journaux_summary(self, request):
        """Récapitulatif de tous les journaux — tableau de bord par code journal.

        Pour chaque journal actif sur la période, retourne le nombre de pièces
        et le total débit/crédit. Utile pour la vue d'ensemble des journaux.

        Query params:
          from (str): Date début YYYY-MM-DD (défaut: 1er janv. de l'année courante)
          to   (str): Date fin YYYY-MM-DD (défaut: aujourd'hui)

        Returns:
            JSON 200:
              {
                "period": {"from": "...", "to": "..."},
                "journals": [
                  {
                    "journal_code": "ACH",
                    "journal_label": "Achats",
                    "entries_count": 10,
                    "total_debit": "45000.00",
                    "total_credit": "45000.00"
                  },
                  ...
                ]
              }
        """
        from decimal import Decimal
        from django.db.models import Count, Sum

        date_from, date_to, err = self._parse_date_range(request)
        if err:
            return err

        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        from apps.ledger.models import AccountEntry

        rows = (
            AccountEntry.objects
            .filter(
                org_id=org_id,
                journal_entry__status="posted",
                journal_entry__entry_date__gte=date_from,
                journal_entry__entry_date__lte=date_to,
            )
            .values("journal_entry__journal_code")
            .annotate(
                total_debit=Sum("debit"),
                total_credit=Sum("credit"),
                entries_count=Count("journal_entry", distinct=True),
            )
            .order_by("journal_entry__journal_code")
        )

        journals = []
        for row in rows:
            code = row["journal_entry__journal_code"]
            td = row["total_debit"] or Decimal("0.00")
            tc = row["total_credit"] or Decimal("0.00")
            journals.append({
                "journal_code": code,
                "journal_label": _JOURNAL_LABELS.get(code, code),
                "entries_count": row["entries_count"],
                "total_debit": f"{td:.2f}",
                "total_credit": f"{tc:.2f}",
            })

        logger.info(
            "journaux.summary org_id=%s from=%s to=%s journals=%d",
            org_id, date_from, date_to, len(journals),
        )

        return Response({
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "journals": journals,
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


class BatchDocumentUploadView(APIView):
    """Upload de plusieurs PDF en une requête → déclenche un groupe de tâches IA.

    Endpoint:
      POST /api/v1/documents/upload/batch/

    Request:
      Content-Type: multipart/form-data
      Body: files=<PDF1>, files=<PDF2>, ...  (champ 'files' répété)

    Response 202:
      {
        "queued": 3,
        "failed": 1,
        "jobs": [
          {"index": 0, "invoice_id": "uuid", "job_id": "uuid", "status": "queued"},
          {"index": 1, "error": "INVALID_TYPE"},
          ...
        ]
      }

    Response 400:
      {"error": "NO_FILES"} | {"error": "TOO_MANY_FILES", "max": 20}

    Response 403:
      {"error": "NO_ORG"}

    Sécurité:
      - Seuls les PDF sont acceptés (Content-Type + extension)
      - Le nom du fichier original N'EST PAS stocké (ADR-004)
      - La clé MinIO est {org_id}/{uuid}.pdf
      - Les fichiers invalides sont signalés sans bloquer les valides
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    MAX_FILES = 20
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB par fichier

    def post(self, request) -> Response:
        """Reçoit N PDFs, les stocke dans MinIO et dispatche un groupe Celery.

        Args:
            request: Requête HTTP avec 'files' (champ répété) dans request.FILES.

        Returns:
            Response 202 avec la liste des jobs créés et les erreurs par fichier.
            Response 400/403 si erreur globale de validation.
        """
        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        files = request.FILES.getlist("files")
        if not files:
            return Response({"error": "NO_FILES", "detail": "Le champ 'files' est requis."}, status=400)

        if len(files) > self.MAX_FILES:
            return Response(
                {"error": "TOO_MANY_FILES", "max": self.MAX_FILES,
                 "detail": f"Maximum {self.MAX_FILES} fichiers par requête."},
                status=400,
            )

        from apps.documents.models import Invoice, ProcessingJob
        from apps.tenants.models import Organization
        import boto3
        from celery import group
        from django.conf import settings as django_settings
        from apps.agents.tasks import process_invoice_task

        org = get_object_or_404(Organization, id=org_id, is_active=True)

        # Initialiser le client MinIO une seule fois pour tout le batch
        try:
            minio_client = boto3.client(
                "s3",
                endpoint_url=django_settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=django_settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=django_settings.AWS_SECRET_ACCESS_KEY,
            )
        except Exception as exc:
            logger.error("batch.upload.minio_init_error org_id=%s err=%s", org_id, type(exc).__name__)
            return Response({"error": "STORAGE_ERROR", "detail": "Impossible de contacter le stockage."}, status=500)

        results: list[dict] = []
        signatures: list = []

        for index, file in enumerate(files):
            # Validation type
            content_type = file.content_type or ""
            filename_lower = (file.name or "").lower()
            if content_type != "application/pdf" and not filename_lower.endswith(".pdf"):
                results.append({"index": index, "status": "error", "error": "INVALID_TYPE"})
                continue

            # Validation taille
            if file.size > self.MAX_FILE_SIZE:
                results.append({
                    "index": index, "status": "error", "error": "FILE_TOO_LARGE",
                    "detail": f"Taille maximale: {self.MAX_FILE_SIZE // 1024 // 1024} MB.",
                })
                continue

            # Upload MinIO — clé opaque (ADR-004)
            file_uuid = uuid.uuid4()
            source_key = f"{org_id}/{file_uuid}.pdf"
            try:
                minio_client.upload_fileobj(
                    file,
                    django_settings.AWS_STORAGE_BUCKET_NAME,
                    source_key,
                    ExtraArgs={"ContentType": "application/pdf"},
                )
                logger.info("batch.upload.stored index=%d key=%s org_id=%s", index, source_key, org_id)
            except Exception as exc:
                logger.error(
                    "batch.upload.minio_error index=%d org_id=%s err=%s",
                    index, org_id, type(exc).__name__,
                )
                results.append({"index": index, "status": "error", "error": "STORAGE_ERROR"})
                continue

            # Créer Invoice + ProcessingJob
            invoice = Invoice.objects.create(org=org, source_key=source_key, status="pending")
            job = ProcessingJob.objects.create(org=org, invoice=invoice, queue="llm", status="queued")

            results.append({
                "index": index,
                "invoice_id": str(invoice.id),
                "job_id": str(job.id),
                "status": "queued",
            })

            # Préparer la signature de tâche Celery (pas encore dispatché)
            signatures.append(
                process_invoice_task.s(
                    str(invoice.id), str(job.id),
                    str(request.user.id), str(org_id),
                    source_key,
                )
            )

        # Dispatcher le groupe Celery en une seule opération atomique
        queued_count = len(signatures)
        failed_count = len(results) - queued_count

        if signatures:
            try:
                group(*signatures).apply_async(queue="llm")
                logger.info(
                    "batch.upload.group_dispatched org_id=%s count=%d",
                    org_id, queued_count,
                )
            except Exception as exc:
                logger.error(
                    "batch.upload.group_error org_id=%s err=%s",
                    org_id, type(exc).__name__,
                )
                # Marquer tous les jobs en attente comme failure
                for result in results:
                    if result.get("status") == "queued":
                        try:
                            ProcessingJob.objects.filter(
                                id=result["job_id"]
                            ).update(status="failure", error_code="TASK_QUEUE_ERROR")
                        except Exception:
                            pass
                        result["status"] = "error"
                        result["error"] = "TASK_QUEUE_ERROR"

        return Response(
            {
                "queued": queued_count,
                "failed": failed_count,
                "jobs": results,
            },
            status=202,
        )


class LetterageViewSet(
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Gestion du lettrage — pointage des comptes tiers (401/411).

    Le lettrage associe plusieurs lignes de compte (AccountEntry) sur un même
    compte tiers pour indiquer leur correspondance (facture ↔ règlement).

    Endpoints:
      GET    /api/v1/lettrage/                — liste des lettrages
      POST   /api/v1/lettrage/               — créer un lettrage
      GET    /api/v1/lettrage/<uuid>/         — détail d'un lettrage
      DELETE /api/v1/lettrage/<uuid>/         — supprimer un lettrage (délettrage)
      GET    /api/v1/lettrage/open-items/     — lignes non lettrées 401/411

    Query params (liste):
      account_code (str): Préfixe de compte (ex: "401", "411001")
      is_balanced  (str): "true" | "false"
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_serializer_class(self):
        """Retourne le serializer Lettering.

        Returns:
            Classe LetteringSerializer.
        """
        from .serializers import LetteringSerializer
        return LetteringSerializer

    def get_queryset(self):
        """Retourne les lettrages de l'org courante avec prefetch.

        Returns:
            QuerySet Lettering filtré par org et paramètres optionnels.
        """
        from apps.ledger.models import Lettering
        org_id = _get_current_org_id(self.request)
        if org_id is None:
            return Lettering.objects.none()

        qs = (
            Lettering.objects
            .filter(org_id=org_id)
            .prefetch_related(
                "lines",
                "lines__account_entry",
                "lines__account_entry__journal_entry",
            )
        )

        account_code = self.request.query_params.get("account_code", "").strip()
        if account_code:
            qs = qs.filter(account_code__startswith=account_code)

        balanced_param = self.request.query_params.get("is_balanced", "").lower()
        if balanced_param == "true":
            qs = qs.filter(is_balanced=True)
        elif balanced_param == "false":
            qs = qs.filter(is_balanced=False)

        return qs.order_by("account_code", "letter_code")

    def create(self, request):
        """Crée un lettrage en pointant plusieurs AccountEntry.

        Request body:
          {
            "account_entry_ids": ["uuid1", "uuid2", ...]
          }

        Validations:
          - Au moins 2 lignes
          - Toutes les lignes appartiennent à la même org
          - Même account_code sur toutes les lignes
          - Compte 401 (fournisseurs) ou 411 (clients) uniquement
          - Écritures parentes status=posted
          - Aucune ligne déjà lettrée

        Returns:
            Lettering créé 201 ou erreur 400/403.
        """
        from decimal import Decimal
        from django.db import transaction
        from apps.ledger.models import AccountEntry, Lettering, LetteringLine, _int_to_letter_code

        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        entry_ids = request.data.get("account_entry_ids", [])
        if not isinstance(entry_ids, list) or len(entry_ids) < 2:
            return Response(
                {"error": "MIN_ENTRIES", "detail": "Le lettrage nécessite au moins 2 lignes."},
                status=400,
            )

        # Dédupliquer et valider les UUIDs
        try:
            unique_ids = list({uuid.UUID(str(eid)) for eid in entry_ids})
        except (ValueError, AttributeError):
            return Response(
                {"error": "INVALID_ID", "detail": "Identifiants de ligne invalides."},
                status=400,
            )

        entries = list(
            AccountEntry.objects
            .filter(org_id=org_id, id__in=unique_ids)
            .select_related("journal_entry")
        )

        if len(entries) != len(unique_ids):
            return Response(
                {
                    "error": "NOT_FOUND",
                    "detail": "Certaines lignes sont introuvables ou n'appartiennent pas à votre organisation.",
                },
                status=400,
            )

        # Vérifier que toutes les lignes sont sur le même compte
        account_codes = {ae.account_code for ae in entries}
        if len(account_codes) > 1:
            return Response(
                {
                    "error": "MIXED_ACCOUNTS",
                    "detail": f"Toutes les lignes doivent appartenir au même compte. Comptes trouvés: {sorted(account_codes)}.",
                },
                status=400,
            )

        account_code = entries[0].account_code

        # Vérifier que c'est un compte tiers (fournisseurs ou clients)
        if not (account_code.startswith("401") or account_code.startswith("411")):
            return Response(
                {
                    "error": "INVALID_ACCOUNT",
                    "detail": "Le lettrage ne s'applique qu'aux comptes fournisseurs (401) et clients (411).",
                },
                status=400,
            )

        # Vérifier que les écritures parentes sont postées
        unposted = [ae for ae in entries if ae.journal_entry.status != "posted"]
        if unposted:
            return Response(
                {
                    "error": "UNPOSTED_ENTRIES",
                    "detail": "Toutes les lignes doivent appartenir à des écritures validées (posted).",
                },
                status=400,
            )

        # Vérifier qu'aucune ligne n'est déjà lettrée
        already_lettered = list(
            LetteringLine.objects
            .filter(account_entry__in=entries)
            .values_list("account_entry_id", flat=True)
        )
        if already_lettered:
            return Response(
                {
                    "error": "ALREADY_LETTERED",
                    "detail": f"{len(already_lettered)} ligne(s) sont déjà lettrées.",
                },
                status=400,
            )

        total_debit = sum(ae.debit for ae in entries)
        total_credit = sum(ae.credit for ae in entries)
        is_balanced = total_debit == total_credit

        with transaction.atomic():
            # Générer le code de lettrage — protégé contre race condition par select_for_update
            count = (
                Lettering.objects
                .filter(org_id=org_id, account_code=account_code)
                .select_for_update()
                .count()
            )
            letter_code = _int_to_letter_code(count)
            lettering = Lettering.objects.create(
                org_id=org_id,
                letter_code=letter_code,
                account_code=account_code,
                is_balanced=is_balanced,
                created_by=request.user,
            )
            LetteringLine.objects.bulk_create([
                LetteringLine(lettering=lettering, account_entry=ae)
                for ae in entries
            ])

        logger.info(
            "lettering.created id=%s code=%s account=%s balanced=%s org=%s",
            lettering.id, letter_code, account_code, is_balanced, org_id,
        )

        # Recharger avec prefetch pour le serializer
        lettering = (
            Lettering.objects
            .prefetch_related(
                "lines",
                "lines__account_entry",
                "lines__account_entry__journal_entry",
            )
            .get(id=lettering.id)
        )
        from .serializers import LetteringSerializer
        return Response(LetteringSerializer(lettering).data, status=201)

    def destroy(self, request, pk=None):
        """Supprime un lettrage (délettrage).

        Les AccountEntry elles-mêmes restent intactes.
        Toutes les LetteringLine sont supprimées en cascade.

        Args:
            request: Requête HTTP authentifiée.
            pk: UUID du lettrage.

        Returns:
            Response 204 si succès.
            Response 404 si lettrage introuvable.
        """
        from apps.ledger.models import Lettering
        org_id = _get_current_org_id(request)
        lettering = get_object_or_404(Lettering, id=pk, org_id=org_id)
        letter_code = lettering.letter_code
        account_code = lettering.account_code
        lettering.delete()
        logger.info(
            "lettering.deleted code=%s account=%s org=%s",
            letter_code, account_code, org_id,
        )
        return Response(status=204)

    @action(detail=False, methods=["get"], url_path="open-items")
    def open_items(self, request):
        """Liste les lignes non lettrées sur les comptes tiers (401/411).

        Query params:
          account_code (str): Préfixe de compte (ex: "401", "411001")
          from (str): Date début YYYY-MM-DD (défaut: 1er janv. de l'année courante)
          to   (str): Date fin YYYY-MM-DD (défaut: aujourd'hui)

        Returns:
            JSON 200:
              {
                "period": {"from": "...", "to": "..."},
                "account_code": "401" | null,
                "total_open_items": int,
                "entries": [
                  {
                    "id": "uuid",
                    "account_code": "401001",
                    "account_label": "Fournisseur X",
                    "debit": "1200.00",
                    "credit": "0.00",
                    "date": "2026-04-01",
                    "reference": "FAC-2026-001",
                    "journal_code": "ACH",
                    "journal_entry_id": "uuid"
                  }
                ]
              }
        """
        from datetime import date, datetime
        from django.db.models import Q
        from apps.ledger.models import AccountEntry, LetteringLine

        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        # Parse date range
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

        account_code_filter = request.query_params.get("account_code", "").strip()

        # IDs déjà lettrés dans cette org
        lettered_ids = LetteringLine.objects.filter(
            lettering__org_id=org_id
        ).values_list("account_entry_id", flat=True)

        qs = (
            AccountEntry.objects
            .filter(
                org_id=org_id,
                journal_entry__status="posted",
                journal_entry__entry_date__gte=date_from,
                journal_entry__entry_date__lte=date_to,
            )
            .exclude(id__in=lettered_ids)
            .select_related("journal_entry")
        )

        if account_code_filter:
            qs = qs.filter(account_code__startswith=account_code_filter)
        else:
            # Par défaut : uniquement les comptes tiers
            qs = qs.filter(
                Q(account_code__startswith="401") | Q(account_code__startswith="411")
            )

        qs = qs.order_by("account_code", "journal_entry__entry_date", "journal_entry__reference")

        entries = [
            {
                "id": str(ae.id),
                "account_code": ae.account_code,
                "account_label": ae.account_label or "",
                "debit": f"{ae.debit:.2f}",
                "credit": f"{ae.credit:.2f}",
                "date": ae.journal_entry.entry_date.isoformat(),
                "reference": ae.journal_entry.reference or "",
                "journal_code": ae.journal_entry.journal_code,
                "journal_entry_id": str(ae.journal_entry.id),
            }
            for ae in qs
        ]

        logger.info(
            "lettrage.open_items org_id=%s account=%s from=%s to=%s count=%d",
            org_id, account_code_filter or None, date_from, date_to, len(entries),
        )

        return Response({
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "account_code": account_code_filter or None,
            "total_open_items": len(entries),
            "entries": entries,
        })


class BankReconciliationViewSet(
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Rapprochement bancaire — import relevé + matching automatique/manuel.

    Endpoints:
      GET    /api/v1/bank-statements/                       — liste des relevés
      GET    /api/v1/bank-statements/<uuid>/                — détail + lignes
      DELETE /api/v1/bank-statements/<uuid>/                — supprimer un relevé
      POST   /api/v1/bank-statements/import/               — importer CSV
      POST   /api/v1/bank-statements/<uuid>/auto-match/     — matching automatique
      POST   /api/v1/bank-statements/<uuid>/match-line/     — match manuel d'une ligne
      POST   /api/v1/bank-statements/<uuid>/unmatch-line/   — dé-matcher une ligne
      POST   /api/v1/bank-statements/<uuid>/ignore-line/    — ignorer une ligne
      GET    /api/v1/bank-statements/<uuid>/report/         — rapport de rapprochement
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_serializer_class(self):
        """Retourne le serializer BankStatement.

        Returns:
            Classe BankStatementSerializer.
        """
        from .serializers import BankStatementSerializer
        return BankStatementSerializer

    def get_queryset(self):
        """Retourne les relevés de l'org courante.

        Returns:
            QuerySet BankStatement filtré par org.
        """
        from apps.ledger.models import BankStatement
        org_id = _get_current_org_id(self.request)
        if org_id is None:
            return BankStatement.objects.none()
        qs = BankStatement.objects.filter(org_id=org_id)

        account_code = self.request.query_params.get("account_code", "").strip()
        if account_code:
            qs = qs.filter(account_code__startswith=account_code)

        return qs.order_by("-period_to", "-created_at")

    @action(detail=False, methods=["post"], url_path="import",
            parser_classes=[MultiPartParser])
    def import_csv(self, request):
        """Importe un relevé bancaire depuis un fichier CSV.

        Format CSV attendu (séparateur ; ou ,) — ligne d'en-tête obligatoire:
          date;libelle;montant
          2026-04-01;VIR FOURNISSEUR X;-1200.00
          2026-04-02;REMISE CHEQUE;500.00

        Colonnes reconnues (insensible à la casse):
          date / transaction_date / date_operation  → transaction_date
          libelle / label / description             → label
          montant / amount / credit_debit           → amount (négatif = débit banque)

        Query params (ou form fields):
          account_code (str): Compte bancaire PCG (ex: "512", "512001") — requis
          account_label (str): Libellé du compte — optionnel
          opening_balance (str): Solde initial du relevé — défaut 0.00
          closing_balance (str): Solde final du relevé — défaut 0.00

        Returns:
            BankStatement créé avec ses lignes (201).
            400 si CSV invalide ou compte manquant.
        """
        import csv
        import io
        from datetime import datetime
        from decimal import Decimal, InvalidOperation

        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        # Paramètres du relevé
        account_code = (
            request.data.get("account_code", "") or
            request.query_params.get("account_code", "")
        ).strip()
        if not account_code:
            return Response(
                {"error": "ACCOUNT_CODE_REQUIRED",
                 "detail": "Le paramètre 'account_code' est requis (ex: '512', '512001')."},
                status=400,
            )
        if not account_code.startswith("512"):
            return Response(
                {"error": "INVALID_ACCOUNT",
                 "detail": "Le rapprochement bancaire s'applique uniquement aux comptes 512."},
                status=400,
            )

        account_label = (
            request.data.get("account_label", "") or
            request.query_params.get("account_label", "")
        ).strip()

        try:
            opening_balance = Decimal(
                request.data.get("opening_balance", "0") or
                request.query_params.get("opening_balance", "0")
            )
            closing_balance = Decimal(
                request.data.get("closing_balance", "0") or
                request.query_params.get("closing_balance", "0")
            )
        except InvalidOperation:
            return Response(
                {"error": "INVALID_BALANCE", "detail": "Soldes invalides — format attendu: 12345.67"},
                status=400,
            )

        # Fichier CSV
        csv_file = request.FILES.get("file")
        if csv_file is None:
            return Response(
                {"error": "NO_FILE", "detail": "Le champ 'file' est requis."},
                status=400,
            )

        # OWASP A05 — limiter la taille à 10 Mo pour éviter un DoS par upload massif
        _MAX_CSV_BYTES = 10 * 1024 * 1024  # 10 MB
        if csv_file.size > _MAX_CSV_BYTES:
            return Response(
                {
                    "error": "FILE_TOO_LARGE",
                    "detail": f"Le fichier dépasse la limite de {_MAX_CSV_BYTES // (1024 * 1024)} Mo.",
                },
                status=400,
            )

        try:
            content = csv_file.read().decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            try:
                csv_file.seek(0)
                content = csv_file.read().decode("latin-1").strip()
            except Exception:
                return Response(
                    {"error": "ENCODING_ERROR", "detail": "Impossible de décoder le fichier."},
                    status=400,
                )

        # Détecter le séparateur (;  ou ,)
        first_line = content.split("\n")[0]
        delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","

        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        if reader.fieldnames is None:
            return Response(
                {"error": "EMPTY_CSV", "detail": "Le fichier CSV est vide ou sans en-tête."},
                status=400,
            )

        # Normaliser les noms de colonnes
        COL_DATE = None
        COL_LABEL = None
        COL_AMOUNT = None
        COL_VALUE_DATE = None

        for fn in reader.fieldnames:
            fnl = fn.strip().lower()
            if fnl in ("date", "transaction_date", "date_operation", "date opération"):
                COL_DATE = fn
            elif fnl in ("date_valeur", "value_date", "date valeur"):
                COL_VALUE_DATE = fn
            elif fnl in ("libelle", "libellé", "label", "description", "motif"):
                COL_LABEL = fn
            elif fnl in ("montant", "amount", "credit_debit", "crédit/débit", "solde mouvement"):
                COL_AMOUNT = fn

        if not COL_DATE or not COL_AMOUNT:
            return Response(
                {
                    "error": "MISSING_COLUMNS",
                    "detail": (
                        f"Colonnes requises non trouvées dans: {list(reader.fieldnames)}. "
                        "Attendu: date (ou transaction_date), montant (ou amount)."
                    ),
                },
                status=400,
            )

        # Parser les lignes
        from apps.ledger.models import BankStatement, BankStatementLine
        from apps.tenants.models import Organization
        from django.db import transaction

        org = get_object_or_404(Organization, id=org_id, is_active=True)

        parsed_lines = []
        parse_errors = []
        dates = []

        for i, row in enumerate(reader, start=2):  # start=2 car ligne 1 = en-tête
            raw_date = (row.get(COL_DATE) or "").strip()
            raw_amount = (row.get(COL_AMOUNT) or "").strip().replace(",", ".")
            raw_label = (row.get(COL_LABEL) or "").strip() if COL_LABEL else ""
            raw_value_date = (row.get(COL_VALUE_DATE) or "").strip() if COL_VALUE_DATE else ""

            if not raw_date and not raw_amount:
                continue  # Ligne vide

            # Date
            parsed_date = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
                try:
                    parsed_date = datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_date is None:
                parse_errors.append(f"Ligne {i}: date invalide '{raw_date}'")
                continue

            # Montant
            try:
                amount = Decimal(raw_amount.replace(" ", ""))
            except InvalidOperation:
                parse_errors.append(f"Ligne {i}: montant invalide '{raw_amount}'")
                continue

            # Date valeur (optionnel)
            value_date = None
            if raw_value_date:
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
                    try:
                        value_date = datetime.strptime(raw_value_date, fmt).date()
                        break
                    except ValueError:
                        continue

            dates.append(parsed_date)
            parsed_lines.append({
                "transaction_date": parsed_date,
                "value_date": value_date,
                "label": raw_label[:255],
                "amount": amount,
            })

        if not parsed_lines:
            return Response(
                {
                    "error": "NO_VALID_LINES",
                    "detail": "Aucune ligne valide trouvée dans le CSV.",
                    "parse_errors": parse_errors,
                },
                status=400,
            )

        period_from = min(dates)
        period_to = max(dates)

        with transaction.atomic():
            statement = BankStatement.objects.create(
                org=org,
                account_code=account_code,
                account_label=account_label,
                period_from=period_from,
                period_to=period_to,
                opening_balance=opening_balance,
                closing_balance=closing_balance,
                status=BankStatement.STATUS_PENDING,
                imported_by=request.user,
            )
            BankStatementLine.objects.bulk_create([
                BankStatementLine(statement=statement, **line_data)
                for line_data in parsed_lines
            ])

        logger.info(
            "bank.import org_id=%s account=%s period=%s→%s lines=%d errors=%d",
            org_id, account_code, period_from, period_to,
            len(parsed_lines), len(parse_errors),
        )

        from .serializers import BankStatementSerializer
        statement.refresh_from_db()
        resp_data = BankStatementSerializer(statement).data
        resp_data["parse_errors"] = parse_errors
        resp_data["lines_imported"] = len(parsed_lines)
        return Response(resp_data, status=201)

    @action(detail=True, methods=["post"], url_path="auto-match")
    def auto_match(self, request, pk=None):
        """Lance le matching automatique sur un relevé.

        Algorithme :
          Pour chaque ligne BankStatementLine non encore rapprochée :
            1. Convertir amount en débit/crédit (amount > 0 → crédit banque → debit AccountEntry 512,
               amount < 0 → débit banque → credit AccountEntry 512)
            2. Chercher dans AccountEntry où account_code startswith statement.account_code,
               status=posted, date dans [transaction_date - DATE_TOLERANCE, + DATE_TOLERANCE],
               montant exact (debit si amount>0, credit si amount<0), pas encore rapproché
            3. Si correspondance unique → match automatique

        Query params:
          date_tolerance (int): Fenêtre de date ±jours — défaut 3, max 15

        Returns:
            {"matched": N, "unmatched": M, "already_matched": K}
        """
        from datetime import timedelta
        from apps.ledger.models import BankStatement, BankStatementLine, AccountEntry

        org_id = _get_current_org_id(request)
        statement = get_object_or_404(BankStatement, id=pk, org_id=org_id)

        try:
            tolerance = min(int(request.data.get("date_tolerance", 3)), 15)
        except (ValueError, TypeError):
            tolerance = 3

        # IDs AccountEntry déjà rapprochés dans cet org
        already_used_ids = set(
            BankStatementLine.objects
            .filter(
                statement__org_id=org_id,
                match_status__in=[
                    BankStatementLine.MATCH_STATUS_MATCHED,
                    BankStatementLine.MATCH_STATUS_MANUAL,
                ],
            )
            .exclude(matched_entry__isnull=True)
            .values_list("matched_entry_id", flat=True)
        )

        lines_to_process = statement.lines.filter(
            match_status=BankStatementLine.MATCH_STATUS_UNMATCHED
        )

        from django.utils import timezone
        matched_count = 0
        unmatched_count = 0

        for bsl in lines_to_process:
            date_min = bsl.transaction_date - timedelta(days=tolerance)
            date_max = bsl.transaction_date + timedelta(days=tolerance)
            amount = bsl.amount

            # amount > 0 → encaissement → côté débit sur le compte 512 dans la compta
            # amount < 0 → décaissement → côté crédit sur le compte 512 dans la compta
            from decimal import Decimal
            abs_amount = abs(amount)

            if amount > Decimal("0"):
                candidates = AccountEntry.objects.filter(
                    org_id=org_id,
                    account_code__startswith=statement.account_code,
                    journal_entry__status="posted",
                    journal_entry__entry_date__gte=date_min,
                    journal_entry__entry_date__lte=date_max,
                    debit=abs_amount,
                    credit=Decimal("0.00"),
                ).exclude(id__in=already_used_ids)
            else:
                candidates = AccountEntry.objects.filter(
                    org_id=org_id,
                    account_code__startswith=statement.account_code,
                    journal_entry__status="posted",
                    journal_entry__entry_date__gte=date_min,
                    journal_entry__entry_date__lte=date_max,
                    credit=abs_amount,
                    debit=Decimal("0.00"),
                ).exclude(id__in=already_used_ids)

            if candidates.count() == 1:
                entry = candidates.first()
                bsl.match_status = BankStatementLine.MATCH_STATUS_MATCHED
                bsl.matched_entry = entry
                bsl.matched_at = timezone.now()
                bsl.save(update_fields=["match_status", "matched_entry", "matched_at"])
                already_used_ids.add(entry.id)
                matched_count += 1
            else:
                unmatched_count += 1

        # Mettre à jour le statut du relevé
        total = statement.lines.count()
        remaining_unmatched = statement.lines.filter(
            match_status=BankStatementLine.MATCH_STATUS_UNMATCHED
        ).count()
        if remaining_unmatched == 0:
            statement.status = BankStatement.STATUS_RECONCILED
        elif matched_count > 0 or statement.lines.filter(
            match_status__in=[
                BankStatementLine.MATCH_STATUS_MATCHED,
                BankStatementLine.MATCH_STATUS_MANUAL,
            ]
        ).exists():
            statement.status = BankStatement.STATUS_IN_PROGRESS
        statement.save(update_fields=["status", "updated_at"])

        logger.info(
            "bank.auto_match statement=%s org=%s matched=%d unmatched=%d tolerance=%d",
            pk, org_id, matched_count, unmatched_count, tolerance,
        )

        return Response({
            "statement_id": str(statement.id),
            "matched": matched_count,
            "unmatched": unmatched_count,
            "already_matched": total - len(lines_to_process),
            "statement_status": statement.status,
        })

    @action(detail=True, methods=["post"], url_path="match-line")
    def match_line(self, request, pk=None):
        """Rapproche manuellement une ligne de relevé avec une AccountEntry.

        Request body:
          {
            "line_id": "uuid",           // BankStatementLine à rapprocher
            "account_entry_id": "uuid"   // AccountEntry du compte 512
          }

        Returns:
            BankStatementLine mis à jour (200).
            400 si ligne déjà rapprochée ou entrée incompatible.
        """
        from decimal import Decimal
        from django.utils import timezone
        from apps.ledger.models import BankStatement, BankStatementLine, AccountEntry

        org_id = _get_current_org_id(request)
        statement = get_object_or_404(BankStatement, id=pk, org_id=org_id)

        line_id = request.data.get("line_id")
        entry_id = request.data.get("account_entry_id")

        if not line_id or not entry_id:
            return Response(
                {"error": "MISSING_PARAMS",
                 "detail": "Les champs 'line_id' et 'account_entry_id' sont requis."},
                status=400,
            )

        try:
            line = BankStatementLine.objects.get(id=line_id, statement=statement)
        except BankStatementLine.DoesNotExist:
            return Response({"error": "LINE_NOT_FOUND"}, status=404)

        if line.match_status in [
            BankStatementLine.MATCH_STATUS_MATCHED,
            BankStatementLine.MATCH_STATUS_MANUAL,
        ]:
            return Response(
                {"error": "ALREADY_MATCHED",
                 "detail": "Cette ligne est déjà rapprochée. Dé-matchez-la d'abord."},
                status=400,
            )

        try:
            entry = AccountEntry.objects.select_related("journal_entry").get(
                id=entry_id, org_id=org_id
            )
        except AccountEntry.DoesNotExist:
            return Response({"error": "ENTRY_NOT_FOUND"}, status=404)

        if entry.journal_entry.status != "posted":
            return Response(
                {"error": "ENTRY_NOT_POSTED",
                 "detail": "L'écriture doit être validée (posted) pour le rapprochement."},
                status=400,
            )

        if not entry.account_code.startswith(statement.account_code):
            return Response(
                {"error": "ACCOUNT_MISMATCH",
                 "detail": f"Le compte de l'écriture ({entry.account_code}) ne correspond pas "
                           f"au compte du relevé ({statement.account_code})."},
                status=400,
            )

        # Vérifier que l'AccountEntry n'est pas déjà rapprochée dans un autre relevé
        if BankStatementLine.objects.filter(
            matched_entry=entry,
            match_status__in=[
                BankStatementLine.MATCH_STATUS_MATCHED,
                BankStatementLine.MATCH_STATUS_MANUAL,
            ],
        ).exclude(id=line.id).exists():
            return Response(
                {"error": "ENTRY_ALREADY_MATCHED",
                 "detail": "Cette écriture est déjà rapprochée dans un autre relevé."},
                status=400,
            )

        line.match_status = BankStatementLine.MATCH_STATUS_MANUAL
        line.matched_entry = entry
        line.matched_at = timezone.now()
        line.save(update_fields=["match_status", "matched_entry", "matched_at"])

        # Mettre à jour statut relevé
        if not statement.lines.filter(
            match_status=BankStatementLine.MATCH_STATUS_UNMATCHED
        ).exists():
            statement.status = BankStatement.STATUS_RECONCILED
        else:
            statement.status = BankStatement.STATUS_IN_PROGRESS
        statement.save(update_fields=["status", "updated_at"])

        logger.info(
            "bank.match_line line=%s entry=%s org=%s manual=True",
            line.id, entry.id, org_id,
        )

        from .serializers import BankStatementLineSerializer
        return Response(BankStatementLineSerializer(line).data)

    @action(detail=True, methods=["post"], url_path="unmatch-line")
    def unmatch_line(self, request, pk=None):
        """Supprime le rapprochement d'une ligne de relevé.

        Request body:
          {"line_id": "uuid"}

        Returns:
            BankStatementLine remis à unmatched (200).
        """
        from apps.ledger.models import BankStatement, BankStatementLine

        org_id = _get_current_org_id(request)
        statement = get_object_or_404(BankStatement, id=pk, org_id=org_id)

        line_id = request.data.get("line_id")
        if not line_id:
            return Response({"error": "MISSING_PARAMS", "detail": "'line_id' est requis."}, status=400)

        try:
            line = BankStatementLine.objects.get(id=line_id, statement=statement)
        except BankStatementLine.DoesNotExist:
            return Response({"error": "LINE_NOT_FOUND"}, status=404)

        line.match_status = BankStatementLine.MATCH_STATUS_UNMATCHED
        line.matched_entry = None
        line.matched_at = None
        line.save(update_fields=["match_status", "matched_entry", "matched_at"])

        statement.status = BankStatement.STATUS_IN_PROGRESS
        statement.save(update_fields=["status", "updated_at"])

        logger.info("bank.unmatch_line line=%s org=%s", line.id, org_id)

        from .serializers import BankStatementLineSerializer
        return Response(BankStatementLineSerializer(line).data)

    @action(detail=True, methods=["post"], url_path="ignore-line")
    def ignore_line(self, request, pk=None):
        """Marque une ligne comme ignorée (ex: frais bancaires automatiques).

        Request body:
          {"line_id": "uuid"}

        Returns:
            BankStatementLine avec match_status=ignored (200).
        """
        from apps.ledger.models import BankStatement, BankStatementLine

        org_id = _get_current_org_id(request)
        statement = get_object_or_404(BankStatement, id=pk, org_id=org_id)

        line_id = request.data.get("line_id")
        if not line_id:
            return Response({"error": "MISSING_PARAMS", "detail": "'line_id' est requis."}, status=400)

        try:
            line = BankStatementLine.objects.get(id=line_id, statement=statement)
        except BankStatementLine.DoesNotExist:
            return Response({"error": "LINE_NOT_FOUND"}, status=404)

        line.match_status = BankStatementLine.MATCH_STATUS_IGNORED
        line.matched_entry = None
        line.matched_at = None
        line.save(update_fields=["match_status", "matched_entry", "matched_at"])

        if not statement.lines.filter(
            match_status=BankStatementLine.MATCH_STATUS_UNMATCHED
        ).exists():
            statement.status = BankStatement.STATUS_RECONCILED
            statement.save(update_fields=["status", "updated_at"])

        logger.info("bank.ignore_line line=%s org=%s", line.id, org_id)

        from .serializers import BankStatementLineSerializer
        return Response(BankStatementLineSerializer(line).data)

    @action(detail=True, methods=["get"], url_path="report")
    def report(self, request, pk=None):
        """Rapport de rapprochement bancaire.

        Retourne le récapitulatif : soldes, écarts, lignes non rapprochées
        côté relevé et côté comptabilité.

        Returns:
            JSON 200:
              {
                "statement_id": "uuid",
                "account_code": "512001",
                "period": {"from": "...", "to": "..."},
                "opening_balance": "10000.00",
                "closing_balance": "12500.00",
                "sum_matched_bank": "2500.00",      // ∑ montants rapprochés côté relevé
                "sum_matched_accounting": "2500.00", // ∑ montants rapprochés côté compta
                "unmatched_bank_lines": [...],        // lignes relevé non rapprochées
                "unmatched_accounting_entries": [...], // AccountEntry 512 non rapprochées sur la période
                "is_balanced": true
              }
        """
        from decimal import Decimal
        from apps.ledger.models import BankStatement, BankStatementLine, AccountEntry

        org_id = _get_current_org_id(request)
        statement = get_object_or_404(BankStatement, id=pk, org_id=org_id)

        # Lignes relevé rapprochées
        matched_lines = statement.lines.filter(
            match_status__in=[
                BankStatementLine.MATCH_STATUS_MATCHED,
                BankStatementLine.MATCH_STATUS_MANUAL,
            ]
        )
        sum_matched_bank = sum(l.amount for l in matched_lines)

        # Lignes relevé non rapprochées
        unmatched_bank = statement.lines.filter(
            match_status=BankStatementLine.MATCH_STATUS_UNMATCHED
        ).order_by("transaction_date")

        # AccountEntry 512 sur la période — non rapprochées dans ce relevé
        matched_entry_ids = set(
            matched_lines.exclude(matched_entry__isnull=True)
            .values_list("matched_entry_id", flat=True)
        )
        unmatched_accounting = AccountEntry.objects.filter(
            org_id=org_id,
            account_code__startswith=statement.account_code,
            journal_entry__status="posted",
            journal_entry__entry_date__gte=statement.period_from,
            journal_entry__entry_date__lte=statement.period_to,
        ).exclude(id__in=matched_entry_ids).select_related("journal_entry")

        sum_matched_accounting = sum(
            (ae.debit - ae.credit) for ae in
            AccountEntry.objects.filter(
                id__in=matched_entry_ids,
                org_id=org_id,
            )
        )

        is_balanced = sum_matched_bank == sum_matched_accounting

        return Response({
            "statement_id": str(statement.id),
            "account_code": statement.account_code,
            "account_label": statement.account_label,
            "period": {
                "from": statement.period_from.isoformat(),
                "to": statement.period_to.isoformat(),
            },
            "opening_balance": f"{statement.opening_balance:.2f}",
            "closing_balance": f"{statement.closing_balance:.2f}",
            "sum_matched_bank": f"{sum_matched_bank:.2f}",
            "sum_matched_accounting": f"{sum_matched_accounting:.2f}",
            "is_balanced": is_balanced,
            "statement_status": statement.status,
            "unmatched_bank_lines": [
                {
                    "id": str(l.id),
                    "transaction_date": l.transaction_date.isoformat(),
                    "label": l.label,
                    "amount": f"{l.amount:.2f}",
                }
                for l in unmatched_bank
            ],
            "unmatched_accounting_entries": [
                {
                    "id": str(ae.id),
                    "account_code": ae.account_code,
                    "date": ae.journal_entry.entry_date.isoformat(),
                    "reference": ae.journal_entry.reference or "",
                    "debit": f"{ae.debit:.2f}",
                    "credit": f"{ae.credit:.2f}",
                }
                for ae in unmatched_accounting
            ],
        })


class ChartOfAccountsViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """CRUD du plan de comptes de l'organisation courante.

    Endpoints:
      GET    /api/v1/chart/          — liste (filtrable)
      POST   /api/v1/chart/          — créer un compte
      GET    /api/v1/chart/{id}/     — détail
      PATCH  /api/v1/chart/{id}/     — modifier libellé / actif
      DELETE /api/v1/chart/{id}/     — supprimer (non-système uniquement)
      POST   /api/v1/chart/seed-pcg/ — peupler le plan PCG standard

    Filtres (query params):
      ?class=4        → filtrer par classe comptable (1-9)
      ?type=tiers     → filtrer par account_type
      ?active=true    → uniquement les comptes actifs
      ?search=fournisseur → cherche dans account_code et account_label

    Raises:
        403: Pas d'organisation associée à l'utilisateur.
        400: Données de création invalides.
        409: Code compte déjà existant dans l'organisation.
    """

    serializer_class = ChartOfAccountsSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Retourne les comptes de l'organisation courante avec filtres optionnels.

        Returns:
            QuerySet ChartOfAccounts filtré.
        """
        org_id = _get_current_org_id(self.request)
        if org_id is None:
            return ChartOfAccounts.objects.none()

        qs = ChartOfAccounts.objects.filter(org_id=org_id)

        # Filtre par classe
        account_class = self.request.query_params.get("class", "").strip()
        if account_class.isdigit():
            qs = qs.filter(account_class=int(account_class))

        # Filtre par type
        account_type = self.request.query_params.get("type", "").strip()
        if account_type:
            qs = qs.filter(account_type=account_type)

        # Filtre actif
        active_param = self.request.query_params.get("active", "").lower()
        if active_param == "true":
            qs = qs.filter(is_active=True)
        elif active_param == "false":
            qs = qs.filter(is_active=False)

        # Recherche textuelle
        search = self.request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q as DQ
            qs = qs.filter(
                DQ(account_code__icontains=search) | DQ(account_label__icontains=search)
            )

        return qs

    def perform_create(self, serializer) -> None:
        """Injecte l'org de l'utilisateur courant à la création.

        Args:
            serializer: Serializer validé.
        """
        org_id = _get_current_org_id(self.request)
        if org_id is None:
            raise PermissionError("NO_ORG")
        from apps.tenants.models import Organization as Org
        org = Org.objects.get(id=org_id)
        serializer.save(org=org)

    def destroy(self, request, *args, **kwargs):
        """Suppression — interdit pour les comptes système PCG.

        Args:
            request: Requête HTTP.

        Returns:
            204 si supprimé, 409 si compte système.
        """
        instance = self.get_object()
        if instance.is_system:
            return Response(
                {"error": "SYSTEM_ACCOUNT",
                 "detail": "Les comptes du plan PCG standard ne peuvent pas être supprimés."},
                status=409,
            )
        self.perform_destroy(instance)
        return Response(status=204)

    @action(detail=False, methods=["post"], url_path="seed-pcg")
    def seed_pcg(self, request):
        """Peuple le plan de comptes avec le PCG standard français.

        Crée uniquement les comptes absents (pas d'écrasement des comptes
        personnalisés existants). Les comptes créés sont marqués is_system=True.

        Args:
            request: Requête HTTP POST.

        Returns:
            200 JSON {"created": N, "skipped": N, "total": N}
            403 si pas d'organisation.
        """
        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        from apps.tenants.models import Organization as Org
        org = Org.objects.get(id=org_id)

        pcg = _PCG_STANDARD  # liste de (code, label, parent_code) définie ci-dessous

        # Codes déjà présents dans l'org
        existing_codes = set(
            ChartOfAccounts.objects.filter(org_id=org_id).values_list("account_code", flat=True)
        )

        to_create = []
        skipped = 0
        for code, label, parent in pcg:
            if code in existing_codes:
                skipped += 1
                continue
            account_class = int(code[0])
            account_type = ChartOfAccounts._CLASS_TYPE_MAP.get(
                account_class, ChartOfAccounts.ACCOUNT_TYPE_TIERS
            )
            to_create.append(ChartOfAccounts(
                org=org,
                account_code=code,
                account_label=label,
                account_class=account_class,
                account_type=account_type,
                is_system=True,
                is_active=True,
                parent_code=parent,
            ))

        ChartOfAccounts.objects.bulk_create(to_create, ignore_conflicts=True)
        created = len(to_create)

        logger.info("chart.seed_pcg org=%s created=%s skipped=%s", org_id, created, skipped)
        return Response({
            "created": created,
            "skipped": skipped,
            "total": created + skipped,
        })


# ── Plan Comptable Général (PCG) standard — liste (code, libellé, parent_code) ──

_PCG_STANDARD: list[tuple[str, str, str]] = [
    # ── Classe 1 : Comptes de capitaux ──────────────────────────────────────
    ("101", "Capital souscrit - appelé, versé", ""),
    ("1011", "Capital souscrit - non appelé", "101"),
    ("1012", "Capital souscrit - appelé, non versé", "101"),
    ("1013", "Capital souscrit - appelé, versé", "101"),
    ("106", "Réserves", ""),
    ("1061", "Réserve légale", "106"),
    ("1063", "Réserves statutaires ou contractuelles", "106"),
    ("1064", "Réserves réglementées", "106"),
    ("1068", "Autres réserves", "106"),
    ("108", "Compte de l'exploitant", ""),
    ("110", "Report à nouveau (solde créditeur)", ""),
    ("119", "Report à nouveau (solde débiteur)", ""),
    ("120", "Résultat de l'exercice (bénéfice)", ""),
    ("129", "Résultat de l'exercice (perte)", ""),
    ("131", "Subventions d'équipement", ""),
    ("138", "Autres subventions d'investissement", ""),
    ("142", "Provisions réglementées relatives aux stocks", ""),
    ("143", "Provisions réglementées relatives aux autres éléments d'actif", ""),
    ("151", "Provisions pour risques", ""),
    ("153", "Provisions pour pensions et obligations similaires", ""),
    ("155", "Provisions pour impôts", ""),
    ("158", "Autres provisions pour charges", ""),
    ("161", "Emprunts obligataires convertibles", ""),
    ("163", "Autres emprunts obligataires", ""),
    ("164", "Emprunts auprès des établissements de crédit", ""),
    ("165", "Dépôts et cautionnements reçus", ""),
    ("166", "Participation des salariés aux résultats", ""),
    ("167", "Emprunts et dettes assortis de conditions particulières", ""),
    ("168", "Autres emprunts et dettes assimilées", ""),
    ("169", "Primes de remboursement des obligations", ""),
    ("171", "Dettes rattachées à des participations (groupe)", ""),
    ("174", "Dettes rattachées à des participations (hors groupe)", ""),
    ("175", "Dettes rattachées à des sociétés en participation", ""),
    ("181", "Comptes de liaison des établissements et sociétés en participation", ""),
    # ── Classe 2 : Comptes d'immobilisations ────────────────────────────────
    ("201", "Frais d'établissement", ""),
    ("203", "Frais de recherche et de développement", ""),
    ("205", "Concessions et droits similaires, brevets, licences", ""),
    ("206", "Droit au bail", ""),
    ("207", "Fonds commercial", ""),
    ("208", "Autres immobilisations incorporelles", ""),
    ("211", "Terrains", ""),
    ("212", "Agencements et aménagements de terrains", ""),
    ("213", "Constructions", ""),
    ("214", "Constructions sur sol d'autrui", ""),
    ("215", "Installations techniques, matériel et outillage industriels", ""),
    ("218", "Autres immobilisations corporelles", ""),
    ("2181", "Installations générales, agencements, aménagements divers", "218"),
    ("2182", "Matériel de transport", "218"),
    ("2183", "Matériel de bureau et matériel informatique", "218"),
    ("2184", "Mobilier", "218"),
    ("231", "Immobilisations corporelles en cours", ""),
    ("232", "Immobilisations incorporelles en cours", ""),
    ("237", "Avances et acomptes versés sur commandes d'immobilisations", ""),
    ("261", "Titres de participation", ""),
    ("267", "Créances rattachées à des participations", ""),
    ("271", "Titres immobilisés autres que les titres immobilisés de l'activité de portefeuille", ""),
    ("272", "Titres immobilisés de l'activité de portefeuille (TIAP)", ""),
    ("274", "Prêts", ""),
    ("275", "Dépôts et cautionnements versés", ""),
    ("280", "Amortissements des immobilisations incorporelles", ""),
    ("2805", "Amortissements des concessions, brevets, licences", "280"),
    ("281", "Amortissements des immobilisations corporelles", ""),
    ("2811", "Amortissements des agencements et aménagements de terrains", "281"),
    ("2813", "Amortissements des constructions", "281"),
    ("2815", "Amortissements des installations techniques", "281"),
    ("2818", "Amortissements des autres immobilisations corporelles", "281"),
    ("291", "Dépréciations des immobilisations incorporelles", ""),
    ("293", "Dépréciations des immobilisations en cours", ""),
    # ── Classe 3 : Comptes de stocks et en-cours ────────────────────────────
    ("310", "Stocks de matières et fournitures consommables", ""),
    ("311", "Matières premières (et fournitures)", ""),
    ("321", "Matières consommables", ""),
    ("326", "Emballages", ""),
    ("331", "Produits en cours", ""),
    ("335", "Travaux en cours", ""),
    ("351", "Produits intermédiaires", ""),
    ("355", "Produits finis", ""),
    ("358", "Produits résiduels ou matières de récupération", ""),
    ("371", "Marchandises (groupe A)", ""),
    ("372", "Marchandises (groupe B)", ""),
    # ── Classe 4 : Comptes de tiers ─────────────────────────────────────────
    ("401", "Fournisseurs", ""),
    ("4011", "Fournisseurs - achats de biens ou de prestations de services", "401"),
    ("4017", "Fournisseurs - retenues de garantie", "401"),
    ("403", "Fournisseurs - effets à payer", ""),
    ("404", "Fournisseurs d'immobilisations", ""),
    ("405", "Fournisseurs d'immobilisations - effets à payer", ""),
    ("408", "Fournisseurs - factures non parvenues", ""),
    ("409", "Fournisseurs débiteurs", ""),
    ("4091", "Fournisseurs - avances et acomptes versés sur commandes", "409"),
    ("4096", "Fournisseurs - créances pour emballages et matériels à rendre", "409"),
    ("411", "Clients", ""),
    ("4111", "Clients - ventes de biens ou de prestations de services", "411"),
    ("4117", "Clients - retenues de garantie", "411"),
    ("413", "Clients - effets à recevoir", ""),
    ("416", "Clients douteux ou litigieux", ""),
    ("418", "Clients - produits non encore facturés", ""),
    ("419", "Clients créditeurs", ""),
    ("4191", "Clients - avances et acomptes reçus sur commandes", "419"),
    ("4196", "Clients - dettes pour emballages et matériels consignés", "419"),
    ("421", "Personnel - rémunérations dues", ""),
    ("422", "Comités d'entreprise", ""),
    ("425", "Personnel - avances et acomptes", ""),
    ("426", "Personnel - dépôts", ""),
    ("427", "Personnel - oppositions", ""),
    ("428", "Personnel - charges à payer et produits à recevoir", ""),
    ("4281", "Charges à payer - dettes provisionnées pour congés à payer", "428"),
    ("4282", "Dettes provisionnées pour participation des salariés", "428"),
    ("431", "Sécurité sociale", ""),
    ("437", "Autres organismes sociaux", ""),
    ("438", "Organismes sociaux - charges à payer et produits à recevoir", ""),
    ("441", "État - subventions à recevoir", ""),
    ("442", "État - impôts et taxes recouvrables sur des tiers", ""),
    ("443", "Opérations particulières avec l'État, les collectivités publiques", ""),
    ("444", "État - impôts sur les bénéfices", ""),
    ("445", "État - Taxes sur le chiffre d'affaires", ""),
    ("4452", "TVA due intracommunautaire", "445"),
    ("4455", "Taxes sur le chiffre d'affaires à décaisser", "445"),
    ("44551", "TVA à décaisser", "4455"),
    ("4456", "Taxes sur le chiffre d'affaires déductibles", "445"),
    ("44562", "TVA déductible sur immobilisations", "4456"),
    ("44566", "TVA déductible sur autres biens et services", "4456"),
    ("4457", "Taxes sur le chiffre d'affaires collectées", "445"),
    ("44571", "TVA collectée", "4457"),
    ("44572", "TVA collectée sur encaissements", "4457"),
    ("4458", "Taxes sur le chiffre d'affaires - régularisations", "445"),
    ("44583", "Remboursements de TVA demandés", "4458"),
    ("44586", "Taxes sur le chiffre d'affaires sur factures non parvenues", "4458"),
    ("44587", "Taxes sur le chiffre d'affaires sur factures à établir", "4458"),
    ("447", "Autres impôts, taxes et versements assimilés", ""),
    ("448", "État - charges à payer et produits à recevoir", ""),
    ("455", "Associés - comptes courants", ""),
    ("456", "Associés - opérations sur le capital", ""),
    ("457", "Associés - dividendes à payer", ""),
    ("462", "Créances sur cessions d'immobilisations", ""),
    ("467", "Autres comptes débiteurs ou créditeurs", ""),
    ("471", "Comptes d'attente", ""),
    ("472", "Comptes transitoires ou d'attente", ""),
    ("481", "Charges à répartir sur plusieurs exercices", ""),
    ("486", "Charges constatées d'avance", ""),
    ("487", "Produits constatés d'avance", ""),
    ("491", "Dépréciations des comptes de clients", ""),
    ("496", "Dépréciations des comptes de débiteurs divers", ""),
    # ── Classe 5 : Comptes financiers ────────────────────────────────────────
    ("512", "Banque", ""),
    ("5121", "Banque - compte principal", "512"),
    ("5122", "Banque - compte secondaire", "512"),
    ("514", "Chèques postaux", ""),
    ("515", "Caisses des établissements à l'étranger", ""),
    ("516", "Valeurs mobilières de placement", ""),
    ("517", "Autres titres de placement", ""),
    ("519", "Concours bancaires courants", ""),
    ("530", "Caisse", ""),
    ("531", "Caisse en devises", ""),
    ("580", "Virements internes", ""),
    ("590", "Dépréciations des valeurs mobilières de placement", ""),
    # ── Classe 6 : Comptes de charges ────────────────────────────────────────
    ("601", "Achats stockés - matières premières (et fournitures)", ""),
    ("602", "Achats stockés - autres approvisionnements", ""),
    ("604", "Achats d'études et prestations de services", ""),
    ("605", "Achats de matériel, équipements et travaux", ""),
    ("606", "Achats non stockés de matières et fournitures", ""),
    ("607", "Achats de marchandises", ""),
    ("608", "Frais accessoires d'achat", ""),
    ("609", "Rabais, remises et ristournes obtenus sur achats", ""),
    ("611", "Sous-traitance générale", ""),
    ("612", "Redevances de crédit-bail et contrats assimilés", ""),
    ("613", "Locations", ""),
    ("614", "Charges locatives et de copropriété", ""),
    ("615", "Entretien et réparations", ""),
    ("616", "Primes d'assurances", ""),
    ("617", "Études et recherches", ""),
    ("618", "Divers (documentation, frais de colloques, séminaires, conférences)", ""),
    ("621", "Personnel extérieur à l'entreprise", ""),
    ("622", "Rémunérations d'intermédiaires et honoraires", ""),
    ("623", "Publicité, publications, relations publiques", ""),
    ("624", "Transports de biens et transports collectifs du personnel", ""),
    ("625", "Déplacements, missions et réceptions", ""),
    ("626", "Frais postaux et frais de télécommunications", ""),
    ("627", "Services bancaires et assimilés", ""),
    ("628", "Divers (frais de services)", ""),
    ("631", "Impôts, taxes et versements assimilés sur rémunérations (autres organismes)", ""),
    ("633", "Impôts, taxes et versements assimilés sur rémunérations (organismes publics)", ""),
    ("635", "Autres impôts, taxes et versements assimilés (autres organismes)", ""),
    ("637", "Autres impôts, taxes et versements assimilés (organismes publics)", ""),
    ("641", "Rémunérations du personnel", ""),
    ("6411", "Salaires, appointements", "641"),
    ("6412", "Congés payés", "641"),
    ("6413", "Primes et gratifications", "641"),
    ("6414", "Indemnités et avantages divers", "641"),
    ("645", "Charges de sécurité sociale et de prévoyance", ""),
    ("6451", "Cotisations à l'URSSAF", "645"),
    ("6452", "Cotisations aux mutuelles", "645"),
    ("6453", "Cotisations aux caisses de retraite", "645"),
    ("6454", "Cotisations aux ASSEDIC", "645"),
    ("647", "Autres charges sociales", ""),
    ("648", "Autres charges de personnel", ""),
    ("651", "Redevances pour concessions, brevets, licences", ""),
    ("654", "Pertes sur créances irrécouvrables", ""),
    ("655", "Quotes-parts de résultat sur opérations faites en commun", ""),
    ("658", "Charges diverses de gestion courante", ""),
    ("661", "Charges d'intérêts", ""),
    ("664", "Pertes sur créances liées à des participations", ""),
    ("665", "Escomptes accordés", ""),
    ("666", "Pertes de change", ""),
    ("667", "Charges nettes sur cessions de valeurs mobilières de placement", ""),
    ("668", "Autres charges financières", ""),
    ("671", "Charges exceptionnelles sur opérations de gestion", ""),
    ("672", "Charges sur exercices antérieurs", ""),
    ("675", "Valeurs comptables des éléments d'actifs cédés", ""),
    ("678", "Autres charges exceptionnelles", ""),
    ("681", "Dotations aux amortissements, dépréciations et provisions - charges d'exploitation", ""),
    ("6811", "Dotations aux amortissements des immobilisations incorporelles et corporelles", "681"),
    ("6815", "Dotations aux provisions pour risques et charges d'exploitation", "681"),
    ("686", "Dotations aux amortissements, dépréciations et provisions - charges financières", ""),
    ("687", "Dotations aux amortissements, dépréciations et provisions - charges exceptionnelles", ""),
    ("691", "Participation des salariés aux résultats", ""),
    ("695", "Impôts sur les bénéfices", ""),
    ("699", "Produits - report en arrière des déficits", ""),
    # ── Classe 7 : Comptes de produits ───────────────────────────────────────
    ("701", "Ventes de produits finis", ""),
    ("702", "Ventes de produits intermédiaires", ""),
    ("703", "Ventes de produits résiduels", ""),
    ("704", "Travaux", ""),
    ("705", "Études", ""),
    ("706", "Prestations de services", ""),
    ("707", "Ventes de marchandises", ""),
    ("708", "Produits des activités annexes", ""),
    ("709", "Rabais, remises et ristournes accordés par l'entreprise", ""),
    ("711", "Variation des stocks de produits finis et en-cours", ""),
    ("713", "Variation des stocks de produits intermédiaires", ""),
    ("721", "Production immobilisée - immobilisations incorporelles", ""),
    ("722", "Production immobilisée - immobilisations corporelles", ""),
    ("731", "Produits nets partiels sur opérations à long terme", ""),
    ("740", "Subventions d'exploitation", ""),
    ("741", "Subventions d'exploitation reçues", ""),
    ("751", "Redevances pour concessions, brevets, licences", ""),
    ("752", "Revenus des immeubles non affectés aux activités professionnelles", ""),
    ("753", "Jetons de présence et rémunérations d'administrateurs", ""),
    ("754", "Ristournes perçues des coopératives (provenant des excédents)", ""),
    ("755", "Quotes-parts de résultat sur opérations faites en commun", ""),
    ("758", "Produits divers de gestion courante", ""),
    ("761", "Produits de participations", ""),
    ("762", "Produits des autres immobilisations financières", ""),
    ("763", "Revenus des autres créances", ""),
    ("764", "Revenus des valeurs mobilières de placement", ""),
    ("765", "Escomptes obtenus", ""),
    ("766", "Gains de change", ""),
    ("767", "Produits nets sur cessions de valeurs mobilières de placement", ""),
    ("768", "Autres produits financiers", ""),
    ("771", "Produits exceptionnels sur opérations de gestion", ""),
    ("772", "Produits sur exercices antérieurs", ""),
    ("775", "Produits des cessions d'éléments d'actifs", ""),
    ("777", "Quote-part des subventions d'investissement virée au résultat", ""),
    ("778", "Autres produits exceptionnels", ""),
    ("781", "Reprises sur amortissements, dépréciations et provisions (à inscrire dans les produits d'exploitation)", ""),
    ("786", "Reprises sur dépréciations et provisions (à inscrire dans les produits financiers)", ""),
    ("787", "Reprises sur provisions (à inscrire dans les produits exceptionnels)", ""),
    ("791", "Transferts de charges d'exploitation", ""),
    ("796", "Transferts de charges financières", ""),
    ("797", "Transferts de charges exceptionnelles", ""),
]


class TvaCA3View(APIView):
    """Déclaration TVA — formulaire CA3 simplifié.

    Agrège les mouvements des comptes TVA sur une période et calcule le
    net à décaisser (44551) ou le crédit de TVA (44567).

    Comptes pris en charge :
      - 44571x  TVA collectée (sur ventes / prestations)
      - 44572x  TVA collectée sur encaissements
      - 4458x   TVA sur factures non parvenues / à régulariser
      - 4456x   TVA déductible (44566, 44562, 44564…)

    Algorithme :
      tva_collectee  = ∑ credit(445[57]x) - ∑ debit(445[57]x)
      tva_deductible = ∑ debit(4456x)     - ∑ credit(4456x)
      solde_net      = tva_collectee - tva_deductible
      → solde_net > 0 : TVA à payer (44551)
      → solde_net < 0 : Crédit de TVA (44567)

    Query params:
      from (str): Date de début YYYY-MM-DD — requis
      to   (str): Date de fin   YYYY-MM-DD — requis
      format (str): "csv" pour export CSV — optionnel (défaut JSON)

    Returns:
        200 JSON:
          {
            "period": {"from": "...", "to": "..."},
            "tva_collectee": {
              "total": "1200.00",
              "lines": [{"account_code": "44571", "account_label": "...",
                         "credit": "1200.00", "debit": "0.00", "net": "1200.00"}]
            },
            "tva_deductible": {
              "total": "480.00",
              "lines": [...]
            },
            "solde_net": "720.00",
            "resultat": "tva_a_payer",   // ou "credit_tva" ou "equilibre"
            "compte_solde": "44551"       // ou "44567" ou None
          }
        200 CSV si ?format=csv
        400 si paramètres manquants / invalides
    """

    permission_classes = [IsAuthenticated]

    # Préfixes PCG des comptes TVA collectée (crédits → produits TVA)
    _COLLECTEE_PREFIXES = ("44571", "44572", "44573", "44574", "44575", "4458")
    # Préfixes PCG des comptes TVA déductible (débits → charges TVA récupérées)
    _DEDUCTIBLE_PREFIXES = ("44562", "44563", "44564", "44566", "44567", "44568")

    def get(self, request) -> Response:
        """Calcule et retourne la CA3 pour la période demandée.

        Args:
            request: Requête DRF avec query params from/to.

        Returns:
            Response JSON ou CSV selon le paramètre format.
        """
        import csv as csv_module
        import io
        from datetime import datetime
        from decimal import Decimal
        from django.db.models import Sum, Q
        from apps.ledger.models import AccountEntry

        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        # Parsing des dates
        raw_from = request.query_params.get("from", "").strip()
        raw_to = request.query_params.get("to", "").strip()

        if not raw_from or not raw_to:
            return Response(
                {"error": "MISSING_PARAMS",
                 "detail": "Les paramètres 'from' et 'to' (YYYY-MM-DD) sont requis."},
                status=400,
            )
        try:
            date_from = datetime.strptime(raw_from, "%Y-%m-%d").date()
            date_to = datetime.strptime(raw_to, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"error": "INVALID_DATE", "detail": "Format attendu : YYYY-MM-DD"},
                status=400,
            )
        if date_from > date_to:
            return Response(
                {"error": "INVALID_RANGE", "detail": "'from' doit être antérieur à 'to'."},
                status=400,
            )

        # Récupérer toutes les AccountEntry TVA sur la période (écritures validées)
        base_qs = AccountEntry.objects.filter(
            org_id=org_id,
            journal_entry__status="posted",
            journal_entry__entry_date__gte=date_from,
            journal_entry__entry_date__lte=date_to,
        )

        def _prefix_filter(prefixes):
            """Construit un Q pour filtrer par liste de préfixes."""
            q = Q()
            for p in prefixes:
                q |= Q(account_code__startswith=p)
            return q

        # ── TVA collectée ──────────────────────────────────────────────
        collectee_qs = (
            base_qs.filter(_prefix_filter(self._COLLECTEE_PREFIXES))
            .values("account_code", "account_label")
            .annotate(
                total_credit=Sum("credit"),
                total_debit=Sum("debit"),
            )
            .order_by("account_code")
        )

        collectee_lines = []
        total_collectee = Decimal("0.00")
        for row in collectee_qs:
            credit = row["total_credit"] or Decimal("0.00")
            debit = row["total_debit"] or Decimal("0.00")
            net = credit - debit  # net positif = TVA collectée nette
            total_collectee += net
            collectee_lines.append({
                "account_code": row["account_code"],
                "account_label": row["account_label"] or "",
                "credit": f"{credit:.2f}",
                "debit": f"{debit:.2f}",
                "net": f"{net:.2f}",
            })

        # ── TVA déductible ─────────────────────────────────────────────
        deductible_qs = (
            base_qs.filter(_prefix_filter(self._DEDUCTIBLE_PREFIXES))
            .values("account_code", "account_label")
            .annotate(
                total_credit=Sum("credit"),
                total_debit=Sum("debit"),
            )
            .order_by("account_code")
        )

        deductible_lines = []
        total_deductible = Decimal("0.00")
        for row in deductible_qs:
            credit = row["total_credit"] or Decimal("0.00")
            debit = row["total_debit"] or Decimal("0.00")
            net = debit - credit  # net positif = TVA déductible nette
            total_deductible += net
            deductible_lines.append({
                "account_code": row["account_code"],
                "account_label": row["account_label"] or "",
                "debit": f"{debit:.2f}",
                "credit": f"{credit:.2f}",
                "net": f"{net:.2f}",
            })

        # ── Solde net ──────────────────────────────────────────────────
        solde_net = total_collectee - total_deductible

        if solde_net > Decimal("0.00"):
            resultat = "tva_a_payer"
            compte_solde = "44551"
        elif solde_net < Decimal("0.00"):
            resultat = "credit_tva"
            compte_solde = "44567"
        else:
            resultat = "equilibre"
            compte_solde = None

        logger.info(
            "tva.ca3 org=%s period=%s→%s collectee=%s deductible=%s net=%s",
            org_id, date_from, date_to,
            total_collectee, total_deductible, solde_net,
        )

        # ── Export CSV ─────────────────────────────────────────────────
        if request.query_params.get("format", "").lower() == "csv":
            return self._build_csv_response(
                date_from, date_to,
                collectee_lines, total_collectee,
                deductible_lines, total_deductible,
                solde_net, resultat, compte_solde,
            )

        return Response({
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "tva_collectee": {
                "total": f"{total_collectee:.2f}",
                "lines": collectee_lines,
            },
            "tva_deductible": {
                "total": f"{total_deductible:.2f}",
                "lines": deductible_lines,
            },
            "solde_net": f"{solde_net:.2f}",
            "resultat": resultat,
            "compte_solde": compte_solde,
        })

    def _build_csv_response(
        self,
        date_from,
        date_to,
        collectee_lines: list,
        total_collectee,
        deductible_lines: list,
        total_deductible,
        solde_net,
        resultat: str,
        compte_solde: str | None,
    ):
        """Construit la réponse CSV de la CA3.

        Args:
            date_from: Date de début.
            date_to: Date de fin.
            collectee_lines: Lignes TVA collectée.
            total_collectee: Total TVA collectée (Decimal).
            deductible_lines: Lignes TVA déductible.
            total_deductible: Total TVA déductible (Decimal).
            solde_net: Solde net (Decimal).
            resultat: "tva_a_payer" | "credit_tva" | "equilibre".
            compte_solde: Code compte solde ou None.

        Returns:
            HttpResponse CSV avec les en-têtes appropriés.
        """
        import csv as csv_module
        import io
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv_module.writer(output, delimiter=";")

        writer.writerow(["DÉCLARATION TVA CA3"])
        writer.writerow([f"Période: {date_from} → {date_to}"])
        writer.writerow([])

        writer.writerow(["=== TVA COLLECTÉE ==="])
        writer.writerow(["Compte", "Libellé", "Crédit", "Débit", "Net"])
        for line in collectee_lines:
            writer.writerow([
                line["account_code"], line["account_label"],
                line["credit"], line["debit"], line["net"],
            ])
        writer.writerow(["", "TOTAL TVA COLLECTÉE", "", "", f"{total_collectee:.2f}"])
        writer.writerow([])

        writer.writerow(["=== TVA DÉDUCTIBLE ==="])
        writer.writerow(["Compte", "Libellé", "Débit", "Crédit", "Net"])
        for line in deductible_lines:
            writer.writerow([
                line["account_code"], line["account_label"],
                line["debit"], line["credit"], line["net"],
            ])
        writer.writerow(["", "TOTAL TVA DÉDUCTIBLE", "", "", f"{total_deductible:.2f}"])
        writer.writerow([])

        resultat_label = {
            "tva_a_payer": "TVA À PAYER",
            "credit_tva": "CRÉDIT DE TVA",
            "equilibre": "ÉQUILIBRE",
        }.get(resultat, resultat)

        writer.writerow(["=== SOLDE NET ==="])
        writer.writerow(["Résultat", "Montant", "Compte"])
        writer.writerow([resultat_label, f"{solde_net:.2f}", compte_solde or "—"])

        filename = f"CA3_{date_from}_{date_to}.csv"
        response = HttpResponse(
            output.getvalue().encode("utf-8-sig"),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


# ── Helpers partagés pour les états financiers ──────────────────────────────


def _parse_date_params(request, *param_names):
    """Parse et valide des paramètres de date (YYYY-MM-DD) depuis la requête.

    Args:
        request: Requête DRF.
        *param_names: Noms des paramètres à parser.

    Returns:
        Tuple de dates parsées dans le même ordre que param_names,
        ou tuple (None, Response erreur) si un paramètre est invalide.
    """
    from datetime import datetime
    dates = []
    for name in param_names:
        raw = request.query_params.get(name, "").strip()
        if not raw:
            return None, Response(
                {"error": "MISSING_PARAMS", "detail": f"Le paramètre '{name}' (YYYY-MM-DD) est requis."},
                status=400,
            )
        try:
            dates.append(datetime.strptime(raw, "%Y-%m-%d").date())
        except ValueError:
            return None, Response(
                {"error": "INVALID_DATE", "detail": f"'{name}': format attendu YYYY-MM-DD."},
                status=400,
            )
    return tuple(dates), None


def _aggregate_by_account(qs):
    """Agrège débit/crédit par (account_code, account_label) depuis un QuerySet AccountEntry.

    Args:
        qs: QuerySet AccountEntry déjà filtré.

    Returns:
        Dict {account_code: {"account_label": str, "debit": Decimal, "credit": Decimal}}
    """
    from decimal import Decimal
    from django.db.models import Sum

    rows = (
        qs.values("account_code", "account_label")
        .annotate(total_debit=Sum("debit"), total_credit=Sum("credit"))
        .order_by("account_code")
    )
    result = {}
    for row in rows:
        code = row["account_code"]
        result[code] = {
            "account_label": row["account_label"] or "",
            "debit": row["total_debit"] or Decimal("0.00"),
            "credit": row["total_credit"] or Decimal("0.00"),
        }
    return result


def _build_section(accounts: dict, prefixes: tuple, net_fn) -> tuple:
    """Construit une section (lignes + total) à partir du dict accounts agrégé.

    Args:
        accounts: Dict issu de _aggregate_by_account.
        prefixes: Tuple de préfixes à inclure.
        net_fn: Callable(debit, credit) → Decimal — calcule le montant net de la ligne.

    Returns:
        Tuple (lines: list[dict], total: Decimal).
    """
    from decimal import Decimal
    lines = []
    total = Decimal("0.00")
    for code, data in accounts.items():
        if not any(code.startswith(p) for p in prefixes):
            continue
        net = net_fn(data["debit"], data["credit"])
        if net == Decimal("0.00"):
            continue
        lines.append({
            "account_code": code,
            "account_label": data["account_label"],
            "debit": f"{data['debit']:.2f}",
            "credit": f"{data['credit']:.2f}",
            "net": f"{net:.2f}",
        })
        total += net
    return lines, total


# ── Compte de résultat ───────────────────────────────────────────────────────


class CompteDeResultatView(APIView):
    """Compte de résultat sur une période donnée.

    Calcule produits (7xx) et charges (6xx) sur les écritures validées (status=posted)
    entre les dates `from` et `to`, et produit le résultat net.

    Structure :
      Produits d'exploitation    : 70–75
      Produits financiers        : 76
      Produits exceptionnels     : 77–78
      ─────────────────────────────────
      Total produits

      Charges d'exploitation     : 60–65
      Charges de personnel       : 64
      Dotations aux amortissements : 68
      Charges financières        : 66
      Charges exceptionnelles    : 67
      Impôts sur bénéfices       : 69
      ─────────────────────────────────
      Total charges

      Résultat net = Total produits - Total charges

    Query params:
      from (str): Date de début YYYY-MM-DD — requis.
      to   (str): Date de fin   YYYY-MM-DD — requis.
      format (str): "csv" pour export — optionnel.

    Returns:
        200 JSON avec la structure complète du compte de résultat.
        200 CSV si ?format=csv.
        400 si dates manquantes / invalides.
        403 si pas d'organisation.
    """

    permission_classes = [IsAuthenticated]

    # Sections PCG avec (label_section, prefixes, net_fn: "credit_minus_debit"|"debit_minus_credit")
    _PRODUITS_SECTIONS = [
        ("exploitation", ("70", "71", "72", "73", "74", "75"), "credit_minus_debit"),
        ("financier",    ("76",),                               "credit_minus_debit"),
        ("exceptionnel", ("77", "78", "79"),                    "credit_minus_debit"),
    ]
    _CHARGES_SECTIONS = [
        ("exploitation",   ("60", "61", "62", "63"),   "debit_minus_credit"),
        ("personnel",      ("64",),                    "debit_minus_credit"),
        ("amortissements", ("68",),                    "debit_minus_credit"),
        ("financier",      ("66",),                    "debit_minus_credit"),
        ("exceptionnel",   ("67",),                    "debit_minus_credit"),
        ("impots",         ("69",),                    "debit_minus_credit"),
    ]

    def get(self, request) -> Response:
        """Calcule le compte de résultat pour la période.

        Args:
            request: Requête DRF avec query params from/to.

        Returns:
            Response JSON ou CSV.
        """
        from decimal import Decimal
        from apps.ledger.models import AccountEntry
        from django.db.models import Q as DQ

        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        dates, err = _parse_date_params(request, "from", "to")
        if err:
            return err
        date_from, date_to = dates

        if date_from > date_to:
            return Response(
                {"error": "INVALID_RANGE", "detail": "'from' doit être antérieur à 'to'."},
                status=400,
            )

        qs = AccountEntry.objects.filter(
            org_id=org_id,
            journal_entry__status="posted",
            journal_entry__entry_date__gte=date_from,
            journal_entry__entry_date__lte=date_to,
        )

        qs_6 = qs.filter(account_code__startswith="6")
        qs_7 = qs.filter(account_code__startswith="7")

        accounts_6 = _aggregate_by_account(qs_6)
        accounts_7 = _aggregate_by_account(qs_7)

        net_fns = {
            "credit_minus_debit": lambda d, c: c - d,
            "debit_minus_credit": lambda d, c: d - c,
        }

        # Construire les sections produits
        produits = {}
        total_produits = Decimal("0.00")
        for key, prefixes, fn_name in self._PRODUITS_SECTIONS:
            lines, total = _build_section(accounts_7, prefixes, net_fns[fn_name])
            produits[key] = {"lines": lines, "total": f"{total:.2f}"}
            total_produits += total

        # Construire les sections charges
        charges = {}
        total_charges = Decimal("0.00")
        for key, prefixes, fn_name in self._CHARGES_SECTIONS:
            lines, total = _build_section(accounts_6, prefixes, net_fns[fn_name])
            charges[key] = {"lines": lines, "total": f"{total:.2f}"}
            total_charges += total

        resultat_net = total_produits - total_charges
        resultat_type = "benefice" if resultat_net >= Decimal("0.00") else "perte"

        logger.info(
            "compte_resultat org=%s period=%s→%s produits=%s charges=%s net=%s",
            org_id, date_from, date_to, total_produits, total_charges, resultat_net,
        )

        if request.query_params.get("format", "").lower() == "csv":
            return self._build_csv_response(
                date_from, date_to, produits, total_produits,
                charges, total_charges, resultat_net, resultat_type,
            )

        return Response({
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "produits": {**produits, "total": f"{total_produits:.2f}"},
            "charges": {**charges, "total": f"{total_charges:.2f}"},
            "resultat_net": f"{resultat_net:.2f}",
            "resultat_type": resultat_type,
        })

    def _build_csv_response(
        self, date_from, date_to,
        produits: dict, total_produits,
        charges: dict, total_charges,
        resultat_net, resultat_type: str,
    ):
        """Construit la réponse CSV du compte de résultat.

        Args:
            date_from: Date de début.
            date_to: Date de fin.
            produits: Dict sections produits.
            total_produits: Total produits (Decimal).
            charges: Dict sections charges.
            total_charges: Total charges (Decimal).
            resultat_net: Résultat net (Decimal).
            resultat_type: "benefice" ou "perte".

        Returns:
            HttpResponse CSV.
        """
        import csv as csv_module
        import io
        from django.http import HttpResponse

        section_labels = {
            "exploitation": "Exploitation",
            "financier": "Financier",
            "exceptionnel": "Exceptionnel",
            "personnel": "Personnel",
            "amortissements": "Dotations aux amortissements",
            "impots": "Impôts sur bénéfices",
        }

        output = io.StringIO()
        writer = csv_module.writer(output, delimiter=";")
        writer.writerow(["COMPTE DE RÉSULTAT"])
        writer.writerow([f"Période: {date_from} → {date_to}"])
        writer.writerow([])

        writer.writerow(["=== PRODUITS ==="])
        writer.writerow(["Compte", "Libellé", "Crédit", "Débit", "Net"])
        for key, data in produits.items():
            writer.writerow([f"--- {section_labels.get(key, key)} ---"])
            for line in data["lines"]:
                writer.writerow([line["account_code"], line["account_label"],
                                  line["credit"], line["debit"], line["net"]])
            writer.writerow(["", f"Sous-total {section_labels.get(key, key)}", "", "", data["total"]])
        writer.writerow(["", "TOTAL PRODUITS", "", "", f"{total_produits:.2f}"])
        writer.writerow([])

        writer.writerow(["=== CHARGES ==="])
        writer.writerow(["Compte", "Libellé", "Débit", "Crédit", "Net"])
        for key, data in charges.items():
            writer.writerow([f"--- {section_labels.get(key, key)} ---"])
            for line in data["lines"]:
                writer.writerow([line["account_code"], line["account_label"],
                                  line["debit"], line["credit"], line["net"]])
            writer.writerow(["", f"Sous-total {section_labels.get(key, key)}", "", "", data["total"]])
        writer.writerow(["", "TOTAL CHARGES", "", "", f"{total_charges:.2f}"])
        writer.writerow([])

        writer.writerow(["=== RÉSULTAT NET ==="])
        result_label = "BÉNÉFICE" if resultat_type == "benefice" else "PERTE"
        writer.writerow([result_label, f"{resultat_net:.2f}"])

        filename = f"CompteResultat_{date_from}_{date_to}.csv"
        result_response = HttpResponse(
            output.getvalue().encode("utf-8-sig"),
            content_type="text/csv; charset=utf-8",
        )
        result_response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return result_response


# ── Bilan ────────────────────────────────────────────────────────────────────


class BilanView(APIView):
    """Bilan comptable à une date de clôture donnée.

    Agrège TOUTES les écritures validées (status=posted) depuis l'origine
    jusqu'à la date `at` incluse, et calcule les soldes nets par compte.

    Structure du bilan (PCG français) :

    ACTIF
      Immobilisations incorporelles nettes  (20x − 280x − 290x)
      Immobilisations corporelles nettes    (21x, 22x, 23x − 281x, 282x, 283x − 291x, 293x)
      Immobilisations financières           (26x, 27x − 296x, 297x)
      Stocks et en-cours                    (3xx)
      Créances clients et comptes rattachés (411x, 413x, 416x, 418x)
      Autres créances                       (40x débiteur, 42x–48x débiteur)
      Disponibilités                        (51x, 52x, 53x, 58x)
      ─────────────────────────────────
      Total actif

    PASSIF
      Capitaux propres                      (101x–108x, 110x)
      Résultat de l'exercice                (calculé 7xx − 6xx sur exercice)
      Provisions pour risques et charges    (15x)
      Emprunts et dettes financières        (16x, 17x)
      Dettes fournisseurs                   (401x, 403x, 404x, 408x)
      Dettes fiscales et sociales           (42x–44x créditeur)
      Autres dettes                         (46x, 47x, 48x créditeur)
      ─────────────────────────────────
      Total passif

    Query params:
      at (str): Date de clôture YYYY-MM-DD — requis.
      exercice_from (str): Début exercice pour le résultat (défaut: 1er jan de l'année `at`).
      format (str): "csv" pour export — optionnel.

    Returns:
        200 JSON avec actif / passif / ecart_bilan (doit être 0 si écritures équilibrées).
        200 CSV si ?format=csv.
        400 si dates manquantes / invalides.
        403 si pas d'organisation.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """Calcule le bilan à la date de clôture.

        Args:
            request: Requête DRF avec query param at.

        Returns:
            Response JSON ou CSV.
        """
        from decimal import Decimal
        from datetime import date
        from apps.ledger.models import AccountEntry

        org_id = _get_current_org_id(request)
        if org_id is None:
            return Response({"error": "NO_ORG"}, status=403)

        dates, err = _parse_date_params(request, "at")
        if err:
            return err
        (date_at,) = dates

        # Début d'exercice (défaut: 1er janvier de l'année de clôture)
        raw_exercice_from = request.query_params.get("exercice_from", "").strip()
        if raw_exercice_from:
            from datetime import datetime
            try:
                exercice_from = datetime.strptime(raw_exercice_from, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": "INVALID_DATE", "detail": "'exercice_from': format YYYY-MM-DD."},
                    status=400,
                )
        else:
            exercice_from = date(date_at.year, 1, 1)

        # Toutes les écritures jusqu'à la clôture (soldes cumulés)
        qs_all = AccountEntry.objects.filter(
            org_id=org_id,
            journal_entry__status="posted",
            journal_entry__entry_date__lte=date_at,
        )
        accounts = _aggregate_by_account(qs_all)

        # Fonctions de calcul du solde net
        def net_debit(d, c):
            return max(d - c, Decimal("0.00"))

        def net_credit(d, c):
            return max(c - d, Decimal("0.00"))

        # ── ACTIF ─────────────────────────────────────────────────────────
        immo_brutes_lines, total_immo_brutes = _build_section(
            accounts, ("20", "21", "22", "23", "26", "27"), net_debit
        )
        amortissements_lines, total_amortissements = _build_section(
            accounts, ("28", "29"), net_credit
        )
        immo_nettes = total_immo_brutes - total_amortissements

        stocks_lines, total_stocks = _build_section(accounts, ("3",), net_debit)

        clients_lines, total_clients = _build_section(
            accounts, ("411", "413", "416", "418"), net_debit
        )
        autres_creances_lines, total_autres_creances = _build_section(
            accounts,
            ("409", "425", "441", "442", "443", "444", "45", "46", "467", "486"),
            net_debit,
        )
        tresorerie_lines, total_tresorerie = _build_section(
            accounts, ("51", "52", "53", "58"), net_debit
        )

        total_actif = (
            immo_nettes + total_stocks + total_clients
            + total_autres_creances + total_tresorerie
        )

        # ── PASSIF ────────────────────────────────────────────────────────
        capitaux_lines, total_capitaux = _build_section(
            accounts, ("101", "102", "103", "104", "106", "107", "108", "110"), net_credit
        )
        report_debiteur_lines, total_report_debiteur = _build_section(
            accounts, ("119",), net_debit
        )
        total_capitaux_nets = total_capitaux - total_report_debiteur

        provisions_lines, total_provisions = _build_section(
            accounts, ("15",), net_credit
        )
        emprunts_lines, total_emprunts = _build_section(
            accounts, ("16", "17"), net_credit
        )
        fournisseurs_lines, total_fournisseurs = _build_section(
            accounts, ("401", "403", "404", "405", "408"), net_credit
        )
        dettes_fiscales_lines, total_dettes_fiscales = _build_section(
            accounts,
            ("421", "422", "427", "428", "431", "437", "438",
             "44551", "4455", "447", "448"),
            net_credit,
        )
        autres_dettes_lines, total_autres_dettes = _build_section(
            accounts, ("455", "456", "457", "462", "487"), net_credit
        )

        # Résultat de l'exercice (calculé sur exercice_from → date_at)
        # Utiliser startswith au lieu de regex pour exploiter l'index btree sur account_code
        from django.db.models import Q as DQ
        qs_exercice = AccountEntry.objects.filter(
            org_id=org_id,
            journal_entry__status="posted",
            journal_entry__entry_date__gte=exercice_from,
            journal_entry__entry_date__lte=date_at,
        ).filter(
            DQ(account_code__startswith="6") | DQ(account_code__startswith="7")
        )
        acc_ex = _aggregate_by_account(qs_exercice)
        _, total_produits_ex = _build_section(acc_ex, ("7",), lambda d, c: c - d)
        _, total_charges_ex = _build_section(acc_ex, ("6",), lambda d, c: d - c)
        resultat_exercice = total_produits_ex - total_charges_ex
        resultat_type = "benefice" if resultat_exercice >= Decimal("0.00") else "perte"

        total_passif = (
            total_capitaux_nets + total_provisions + total_emprunts
            + total_fournisseurs + total_dettes_fiscales + total_autres_dettes
            + resultat_exercice
        )
        ecart = total_actif - total_passif

        logger.info(
            "bilan org=%s at=%s actif=%s passif=%s ecart=%s",
            org_id, date_at, total_actif, total_passif, ecart,
        )

        result = {
            "at": date_at.isoformat(),
            "exercice_from": exercice_from.isoformat(),
            "actif": {
                "immobilisations": {
                    "brutes": {"lines": immo_brutes_lines, "total": f"{total_immo_brutes:.2f}"},
                    "amortissements": {"lines": amortissements_lines, "total": f"{total_amortissements:.2f}"},
                    "nettes": f"{immo_nettes:.2f}",
                },
                "stocks": {"lines": stocks_lines, "total": f"{total_stocks:.2f}"},
                "clients": {"lines": clients_lines, "total": f"{total_clients:.2f}"},
                "autres_creances": {"lines": autres_creances_lines, "total": f"{total_autres_creances:.2f}"},
                "tresorerie": {"lines": tresorerie_lines, "total": f"{total_tresorerie:.2f}"},
                "total": f"{total_actif:.2f}",
            },
            "passif": {
                "capitaux_propres": {
                    "lines": capitaux_lines,
                    "total_brut": f"{total_capitaux:.2f}",
                    "report_debiteur": f"{total_report_debiteur:.2f}",
                    "total": f"{total_capitaux_nets:.2f}",
                },
                "resultat_exercice": {
                    "produits": f"{total_produits_ex:.2f}",
                    "charges": f"{total_charges_ex:.2f}",
                    "net": f"{resultat_exercice:.2f}",
                    "type": resultat_type,
                },
                "provisions": {"lines": provisions_lines, "total": f"{total_provisions:.2f}"},
                "emprunts": {"lines": emprunts_lines, "total": f"{total_emprunts:.2f}"},
                "fournisseurs": {"lines": fournisseurs_lines, "total": f"{total_fournisseurs:.2f}"},
                "dettes_fiscales_sociales": {
                    "lines": dettes_fiscales_lines,
                    "total": f"{total_dettes_fiscales:.2f}",
                },
                "autres_dettes": {"lines": autres_dettes_lines, "total": f"{total_autres_dettes:.2f}"},
                "total": f"{total_passif:.2f}",
            },
            "ecart_bilan": f"{ecart:.2f}",
        }

        if request.query_params.get("format", "").lower() == "csv":
            return self._build_csv_response(result, date_at, exercice_from)

        return Response(result)

    def _build_csv_response(self, result: dict, date_at, exercice_from):
        """Construit la réponse CSV du bilan.

        Args:
            result: Dict résultat JSON déjà calculé.
            date_at: Date de clôture.
            exercice_from: Début d'exercice.

        Returns:
            HttpResponse CSV.
        """
        import csv as csv_module
        import io
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv_module.writer(output, delimiter=";")
        writer.writerow(["BILAN COMPTABLE"])
        writer.writerow([f"Arrêté au: {date_at}"])
        writer.writerow([f"Exercice du: {exercice_from} au {date_at}"])
        writer.writerow([])

        def write_section(title, lines, total_label, total_val):
            writer.writerow([f"=== {title} ==="])
            writer.writerow(["Compte", "Libellé", "Net"])
            for line in lines:
                writer.writerow([line["account_code"], line["account_label"], line["net"]])
            writer.writerow(["", total_label, total_val])
            writer.writerow([])

        writer.writerow(["====== ACTIF ======"])
        actif = result["actif"]
        immo = actif["immobilisations"]
        write_section("Immobilisations brutes", immo["brutes"]["lines"],
                      "Total brut", immo["brutes"]["total"])
        write_section("Amortissements et dépréciations", immo["amortissements"]["lines"],
                      "Total amortissements", immo["amortissements"]["total"])
        writer.writerow(["", "IMMOBILISATIONS NETTES", immo["nettes"]])
        writer.writerow([])
        write_section("Stocks", actif["stocks"]["lines"],
                      "Total stocks", actif["stocks"]["total"])
        write_section("Créances clients", actif["clients"]["lines"],
                      "Total clients", actif["clients"]["total"])
        write_section("Autres créances", actif["autres_creances"]["lines"],
                      "Total autres créances", actif["autres_creances"]["total"])
        write_section("Trésorerie", actif["tresorerie"]["lines"],
                      "Total trésorerie", actif["tresorerie"]["total"])
        writer.writerow(["", "TOTAL ACTIF", actif["total"]])
        writer.writerow([])

        writer.writerow(["====== PASSIF ======"])
        passif = result["passif"]
        write_section("Capitaux propres", passif["capitaux_propres"]["lines"],
                      "Total capitaux propres", passif["capitaux_propres"]["total"])
        resultat_ex = passif["resultat_exercice"]
        writer.writerow(["", "Résultat de l'exercice",
                         f"{resultat_ex['net']} ({resultat_ex['type']})"])
        writer.writerow([])
        write_section("Provisions", passif["provisions"]["lines"],
                      "Total provisions", passif["provisions"]["total"])
        write_section("Emprunts", passif["emprunts"]["lines"],
                      "Total emprunts", passif["emprunts"]["total"])
        write_section("Fournisseurs", passif["fournisseurs"]["lines"],
                      "Total fournisseurs", passif["fournisseurs"]["total"])
        write_section("Dettes fiscales et sociales",
                      passif["dettes_fiscales_sociales"]["lines"],
                      "Total dettes fiscales", passif["dettes_fiscales_sociales"]["total"])
        write_section("Autres dettes", passif["autres_dettes"]["lines"],
                      "Total autres dettes", passif["autres_dettes"]["total"])
        writer.writerow(["", "TOTAL PASSIF", passif["total"]])
        writer.writerow([])
        writer.writerow(["", "ÉCART BILAN (doit être 0)", result["ecart_bilan"]])

        filename = f"Bilan_{date_at}.csv"
        bilan_response = HttpResponse(
            output.getvalue().encode("utf-8-sig"),
            content_type="text/csv; charset=utf-8",
        )
        bilan_response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return bilan_response
