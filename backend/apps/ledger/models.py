"""
apps/ledger — Écritures comptables et plan de comptes.

Models:
  JournalEntry       — Écriture comptable (pièce)
  AccountEntry       — Ligne de l'écriture (débit/crédit)
  JournalEntryAudit  — Audit trail des transitions de statut (ADR-009)

ADR-001: org_id (ForeignKey Organization) sur tous les modèles.
ADR-004: Les montants dans JournalEntry/AccountEntry ne sont PAS chiffrés
  ici car le plan comptable est structuré (pas de PII).
  Les montants bruts de la facture source (Invoice) sont chiffrés.
ADR-005: __str__ n'inclut jamais les montants, uniquement les UUIDs.
"""
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.documents.models import Invoice
from apps.tenants.models import Organization
from core.managers import TenantManager


class JournalEntry(models.Model):
    """Écriture comptable — regroupe les lignes débit/crédit.

    Conforme PCG (Plan Comptable Général français).
    Une écriture est équilibrée : sum(debit) == sum(credit).
    """

    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("posted", "Comptabilisé"),
        ("cancelled", "Annulé"),
    ]

    objects = TenantManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="journal_entries",
        db_column="org_id",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="journal_entries",
        null=True,
        blank=True,
    )
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    journal_code = models.CharField(max_length=10, default="ACH")  # ACH, VTE, BQ, ...
    entry_date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="draft", db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ledger_journalentry"
        ordering = ["-entry_date", "-created_at"]

    def __str__(self) -> str:
        # No amounts in __str__ — ADR-005
        return f"JournalEntry {self.id} [{self.journal_code}/{self.status}]"


class AccountEntry(models.Model):
    """Ligne d'écriture comptable — débit ou crédit sur un compte PCG.

    Contrainte: pour une JournalEntry, sum(debit) == sum(credit).
    Cette contrainte est vérifiée au niveau applicatif dans le serializer DRF.
    """

    objects = TenantManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="account_entries",
        db_column="org_id",
    )
    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    account_code = models.CharField(max_length=10, db_index=True)  # PCG: 401, 44566, 512...
    account_label = models.CharField(max_length=255, blank=True)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_accountentry"
        ordering = ["account_code"]

    def __str__(self) -> str:
        # No amounts in __str__ — ADR-005
        return f"AccountEntry {self.id} [{self.account_code}]"


class JournalEntryAudit(models.Model):
    """Audit trail des transitions de statut sur les écritures comptables.

    Chaque appel à validate() ou cancel() crée un enregistrement immuable.
    Conforme ADR-009 : aucune donnée métier (montants, comptes) n'est stockée.
    """

    ACTION_CREATED = "created"
    ACTION_VALIDATED = "validated"
    ACTION_CANCELLED = "cancelled"
    ACTION_REVERSED = "reversed"

    ACTION_CHOICES = [
        (ACTION_CREATED, "Créée"),
        (ACTION_VALIDATED, "Validée"),
        (ACTION_CANCELLED, "Annulée"),
        (ACTION_REVERSED, "Extournée"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_audit_logs",
    )
    performed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Optional free-text reason — stored only for reversals (ADR-005: no PII)
    reason = models.TextField(blank=True)

    class Meta:
        db_table = "ledger_journalentryaudit"
        ordering = ["performed_at"]

    def __str__(self) -> str:
        return f"Audit {self.action} entry={self.entry_id} by={self.performed_by_id}"
