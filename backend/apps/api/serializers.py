"""
apps/api/serializers.py — Serializers DRF.

Note sécurité (ADR-005):
  Les champs chiffrés (vendor_name, vendor_siren, montants) sont exposés
  dans l'API uniquement en écriture + lecture pour l'org propriétaire.
  Jamais de logging de ces valeurs dans les serializers.

Note ADR-004:
  vendor_siren_hash est calculé automatiquement dans InvoiceSerializer.create/update
  via HMAC-SHA256 sur vendor_siren avant sauvegarde.
"""
import hashlib
import hmac
import logging

from django.conf import settings
from rest_framework import serializers

from apps.documents.models import Invoice, ProcessingJob
from apps.ledger.models import AccountEntry, BankStatement, BankStatementLine, ChartOfAccounts, JournalEntry, JournalEntryAudit, Lettering, LetteringLine
from apps.tenants.models import Organization

logger = logging.getLogger("apps.api.serializers")


class OrganizationSerializer(serializers.ModelSerializer):
    """Serializer pour Organization — liste des orgs de l'utilisateur courant.

    Le champ `role` est annoté par OrganizationViewSet.get_queryset() via
    une valeur Subquery sur TenantMembership.

    Returns:
      id, name, siren, role, is_active, created_at
    """

    role = serializers.CharField(read_only=True, default="")

    class Meta:
        model = Organization
        fields = ["id", "name", "siren", "role", "is_active", "created_at"]
        read_only_fields = ["id", "siren", "created_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer pour Invoice.

    Calcule automatiquement vendor_siren_hash depuis vendor_siren (ADR-004).
    org est injecté par la view (perform_create), non exposé en input.
    """

    class Meta:
        model = Invoice
        fields = [
            "id",
            "reference",
            "status",
            "source_key",
            "vendor_name",
            "vendor_siren",
            "ht_amount",
            "tva_amount",
            "ttc_amount",
            "invoice_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "source_key", "created_at", "updated_at"]

    def _compute_siren_hash(self, siren: str) -> str:
        """Calcule le hash HMAC-SHA256 déterministe pour l'indexation (ADR-004).

        Args:
            siren: SIREN en clair (9 chiffres).

        Returns:
            Hash hexadécimal 64 chars.
        """
        key = settings.SECRET_KEY.encode("utf-8")
        return hmac.new(key, siren.encode("utf-8"), hashlib.sha256).hexdigest()

    def create(self, validated_data: dict) -> Invoice:
        """Crée une facture en calculant vendor_siren_hash.

        Args:
            validated_data: Données validées par le serializer.

        Returns:
            Instance Invoice créée.
        """
        siren = validated_data.get("vendor_siren", "")
        if siren:
            validated_data["vendor_siren_hash"] = self._compute_siren_hash(siren)
        return super().create(validated_data)

    def update(self, instance: Invoice, validated_data: dict) -> Invoice:
        """Met à jour une facture en recalculant vendor_siren_hash si nécessaire.

        Args:
            instance: Instance Invoice existante.
            validated_data: Données validées.

        Returns:
            Instance Invoice mise à jour.
        """
        siren = validated_data.get("vendor_siren", "")
        if siren:
            validated_data["vendor_siren_hash"] = self._compute_siren_hash(siren)
        return super().update(instance, validated_data)


class JournalEntryAuditSerializer(serializers.ModelSerializer):
    """Serializer read-only pour l'audit trail d'une écriture."""

    performed_by_username = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntryAudit
        fields = [
            "id", "action", "from_status", "to_status",
            "performed_by", "performed_by_username", "performed_at", "reason",
        ]
        read_only_fields = fields

    def get_performed_by_username(self, obj: JournalEntryAudit) -> str | None:
        """Retourne le username de l'acteur (jamais le mot de passe).

        Args:
            obj: Instance JournalEntryAudit.

        Returns:
            Username ou None.
        """
        if obj.performed_by_id is None:
            return None
        return getattr(obj.performed_by, "username", None)


class AccountEntrySerializer(serializers.ModelSerializer):
    """Serializer pour une ligne d'écriture comptable."""

    class Meta:
        model = AccountEntry
        fields = ["id", "account_code", "account_label", "debit", "credit"]
        read_only_fields = ["id"]

    def validate(self, attrs: dict) -> dict:
        """Valide qu'une ligne n'a pas à la fois débit ET crédit non nuls.

        Args:
            attrs: Données de la ligne.

        Returns:
            Données validées.

        Raises:
            serializers.ValidationError: Si débit et crédit sont tous deux > 0.
        """
        if attrs.get("debit", 0) > 0 and attrs.get("credit", 0) > 0:
            raise serializers.ValidationError(
                "Une ligne ne peut pas avoir débit ET crédit non nuls."
            )
        return attrs


class JournalEntrySerializer(serializers.ModelSerializer):
    """Serializer pour JournalEntry avec ses lignes imbriquées.

    Valide l'équilibre débit == crédit à la soumission.
    """

    lines = AccountEntrySerializer(many=True)
    audit_logs = JournalEntryAuditSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "reference",
            "journal_code",
            "entry_date",
            "status",
            "invoice",
            "lines",
            "audit_logs",
            "created_at",
        ]
        read_only_fields = ["id", "status", "audit_logs", "created_at"]

    def validate(self, attrs: dict) -> dict:
        """Valide l'équilibre débit == crédit de l'écriture.

        Args:
            attrs: Données de l'écriture avec lignes imbriquées.

        Returns:
            Données validées.

        Raises:
            serializers.ValidationError: Si sum(debit) != sum(credit).
        """
        lines = attrs.get("lines", [])
        total_debit = sum(line.get("debit", 0) for line in lines)
        total_credit = sum(line.get("credit", 0) for line in lines)
        if total_debit != total_credit:
            raise serializers.ValidationError(
                f"Écriture déséquilibrée: débit={total_debit}, crédit={total_credit}."
            )
        if not lines:
            raise serializers.ValidationError(
                "Une écriture doit avoir au moins une ligne."
            )
        return attrs

    def create(self, validated_data: dict) -> JournalEntry:
        """Crée l'écriture et ses lignes en une transaction.

        Args:
            validated_data: Données validées.

        Returns:
            Instance JournalEntry créée avec ses AccountEntry.
        """
        from apps.ledger.models import JournalEntryAudit
        lines_data = validated_data.pop("lines")
        org = validated_data["org"]
        entry = JournalEntry.objects.create(**validated_data)
        for line_data in lines_data:
            AccountEntry.objects.create(journal_entry=entry, org=org, **line_data)

        # Audit trail — ADR-009
        request = self.context.get("request")
        JournalEntryAudit.objects.create(
            entry=entry,
            action=JournalEntryAudit.ACTION_CREATED,
            from_status="",
            to_status="draft",
            performed_by=request.user if request else None,
        )

        logger.info("journal.created id=%s lines=%d", entry.id, len(lines_data))
        return entry


class LetteringLineSerializer(serializers.ModelSerializer):
    """Serializer read-only pour une ligne de lettrage."""

    account_entry_id = serializers.UUIDField(source="account_entry.id", read_only=True)
    account_code = serializers.CharField(source="account_entry.account_code", read_only=True)
    account_label = serializers.CharField(source="account_entry.account_label", read_only=True)
    debit = serializers.DecimalField(
        source="account_entry.debit", max_digits=15, decimal_places=2, read_only=True
    )
    credit = serializers.DecimalField(
        source="account_entry.credit", max_digits=15, decimal_places=2, read_only=True
    )
    entry_date = serializers.DateField(
        source="account_entry.journal_entry.entry_date", read_only=True
    )
    reference = serializers.CharField(
        source="account_entry.journal_entry.reference", read_only=True
    )
    journal_code = serializers.CharField(
        source="account_entry.journal_entry.journal_code", read_only=True
    )

    class Meta:
        model = LetteringLine
        fields = [
            "id",
            "account_entry_id",
            "account_code",
            "account_label",
            "debit",
            "credit",
            "entry_date",
            "reference",
            "journal_code",
        ]
        read_only_fields = fields


class LetteringSerializer(serializers.ModelSerializer):
    """Serializer pour Lettering avec ses lignes imbriquées."""

    lines = LetteringLineSerializer(many=True, read_only=True)
    total_debit = serializers.SerializerMethodField()
    total_credit = serializers.SerializerMethodField()

    class Meta:
        model = Lettering
        fields = [
            "id",
            "letter_code",
            "account_code",
            "is_balanced",
            "created_at",
            "total_debit",
            "total_credit",
            "lines",
        ]
        read_only_fields = fields

    def get_total_debit(self, obj: Lettering) -> str:
        """Calcule le total débit des lignes lettrées.

        Args:
            obj: Instance Lettering.

        Returns:
            Total débit formaté en 2 décimales.
        """
        from decimal import Decimal
        total = sum(
            (line.account_entry.debit or Decimal("0.00"))
            for line in obj.lines.all()
        )
        return f"{total:.2f}"

    def get_total_credit(self, obj: Lettering) -> str:
        """Calcule le total crédit des lignes lettrées.

        Args:
            obj: Instance Lettering.

        Returns:
            Total crédit formaté en 2 décimales.
        """
        from decimal import Decimal
        total = sum(
            (line.account_entry.credit or Decimal("0.00"))
            for line in obj.lines.all()
        )
        return f"{total:.2f}"


class BankStatementLineSerializer(serializers.ModelSerializer):
    """Serializer pour une ligne de relevé bancaire."""

    matched_entry_id = serializers.UUIDField(
        source="matched_entry.id", read_only=True, allow_null=True
    )
    matched_account_code = serializers.CharField(
        source="matched_entry.account_code", read_only=True, allow_null=True
    )
    matched_reference = serializers.SerializerMethodField()

    class Meta:
        model = BankStatementLine
        fields = [
            "id",
            "transaction_date",
            "value_date",
            "label",
            "amount",
            "match_status",
            "matched_entry_id",
            "matched_account_code",
            "matched_reference",
            "matched_at",
        ]
        read_only_fields = fields

    def get_matched_reference(self, obj: BankStatementLine) -> str | None:
        """Retourne la référence de l'écriture rapprochée si elle existe.

        Args:
            obj: Instance BankStatementLine.

        Returns:
            Référence de l'écriture ou None.
        """
        if obj.matched_entry and obj.matched_entry.journal_entry:
            return obj.matched_entry.journal_entry.reference or None
        return None


class BankStatementSerializer(serializers.ModelSerializer):
    """Serializer pour un relevé bancaire avec ses lignes et compteurs."""

    lines = BankStatementLineSerializer(many=True, read_only=True)
    lines_count = serializers.SerializerMethodField()
    matched_count = serializers.SerializerMethodField()
    unmatched_count = serializers.SerializerMethodField()

    class Meta:
        model = BankStatement
        fields = [
            "id",
            "account_code",
            "account_label",
            "period_from",
            "period_to",
            "opening_balance",
            "closing_balance",
            "status",
            "created_at",
            "lines_count",
            "matched_count",
            "unmatched_count",
            "lines",
        ]
        read_only_fields = fields

    def get_lines_count(self, obj: BankStatement) -> int:
        """Nombre total de lignes du relevé.

        Args:
            obj: Instance BankStatement.

        Returns:
            Nombre de lignes.
        """
        return obj.lines.count()

    def get_matched_count(self, obj: BankStatement) -> int:
        """Nombre de lignes rapprochées (auto ou manuel).

        Args:
            obj: Instance BankStatement.

        Returns:
            Nombre de lignes rapprochées.
        """
        return obj.lines.filter(
            match_status__in=[
                BankStatementLine.MATCH_STATUS_MATCHED,
                BankStatementLine.MATCH_STATUS_MANUAL,
            ]
        ).count()

    def get_unmatched_count(self, obj: BankStatement) -> int:
        """Nombre de lignes non rapprochées.

        Args:
            obj: Instance BankStatement.

        Returns:
            Nombre de lignes non rapprochées.
        """
        return obj.lines.filter(
            match_status=BankStatementLine.MATCH_STATUS_UNMATCHED
        ).count()


class ChartOfAccountsSerializer(serializers.ModelSerializer):
    """Serializer pour le plan de comptes.

    En lecture, retourne tous les champs.
    En écriture, account_class et account_type sont calculés automatiquement
    par le modèle (méthode save()), mais peuvent être fournis pour override.

    Les comptes système (is_system=True) ne peuvent pas être supprimés ;
    cette protection est gérée dans le ViewSet.
    """

    class Meta:
        model = ChartOfAccounts
        fields = [
            "id",
            "account_code",
            "account_label",
            "account_class",
            "account_type",
            "is_system",
            "is_active",
            "parent_code",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "account_class", "is_system", "created_at", "updated_at"]

    def validate_account_code(self, value: str) -> str:
        """Valide que le code compte commence par un chiffre 1-9.

        Args:
            value: Code compte fourni.

        Returns:
            Code compte validé (stripped).

        Raises:
            ValidationError: Si le code est invalide.
        """
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Le code compte ne peut pas être vide.")
        if not value[0].isdigit() or value[0] == "0":
            raise serializers.ValidationError(
                "Le code compte doit commencer par un chiffre entre 1 et 9."
            )
        if not value.isdigit():
            raise serializers.ValidationError(
                "Le code compte doit être entièrement numérique."
            )
        return value
