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


def _int_to_letter_code(n: int) -> str:
    """Convertit un entier (0-based) en code alphabétique de lettrage.

    0→A, 1→B, …, 25→Z, 26→AA, 27→AB, …

    Args:
        n: Index 0-based du lettrage pour un couple (org, account_code).

    Returns:
        Code alphabétique (ex: 'A', 'Z', 'AA', 'ZZ').
    """
    result = ""
    n += 1
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


class Lettering(models.Model):
    """Lettrage — pointage de lignes de comptes tiers (401/411).

    Un lettrage regroupe des lignes AccountEntry pour indiquer leur correspondance
    (une facture fournisseur soldée par un paiement, par exemple).

    Le lettrage est dit «soldé» (is_balanced=True) quand la somme des débits
    des lignes lettrées égale la somme des crédits.

    ADR-001: org_id sur toutes les tables métier.
    ADR-005: __str__ n'expose jamais les montants.
    """

    objects = TenantManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="letterings",
        db_column="org_id",
    )
    letter_code = models.CharField(max_length=10, db_index=True)
    account_code = models.CharField(max_length=10, db_index=True)
    is_balanced = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_letterings",
    )

    class Meta:
        db_table = "ledger_lettering"
        ordering = ["account_code", "letter_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "account_code", "letter_code"],
                name="unique_lettering_code_per_org_account",
            )
        ]

    def __str__(self) -> str:
        return f"Lettering {self.letter_code} [{self.account_code}] org={self.org_id}"


class LetteringLine(models.Model):
    """Ligne de lettrage — associe une AccountEntry à un Lettering.

    Contrainte OneToOne : une AccountEntry ne peut appartenir qu'à un seul Lettering.
    La suppression du Lettering parent supprime toutes ses lignes en cascade.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lettering = models.ForeignKey(
        Lettering,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    account_entry = models.OneToOneField(
        AccountEntry,
        on_delete=models.CASCADE,
        related_name="lettering_line",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_letteringline"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"LetteringLine lettering={self.lettering_id} entry={self.account_entry_id}"


# ---------------------------------------------------------------------------
# Rapprochement bancaire
# ---------------------------------------------------------------------------


class BankStatement(models.Model):
    """Relevé bancaire importé — un fichier CSV/OFX par compte et par période.

    Représente un relevé importé pour un compte bancaire (account_code 512xxx).
    Les lignes du relevé sont dans BankStatementLine.

    ADR-001: org_id sur tous les modèles métier.
    ADR-005: __str__ n'expose jamais les montants.
    """

    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RECONCILED = "reconciled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_RECONCILED, "Rapproché"),
    ]

    objects = TenantManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="bank_statements",
        db_column="org_id",
    )
    account_code = models.CharField(max_length=10, db_index=True)  # ex: "512", "512001"
    account_label = models.CharField(max_length=255, blank=True)
    period_from = models.DateField()
    period_to = models.DateField()
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imported_bank_statements",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ledger_bankstatement"
        ordering = ["-period_to", "-created_at"]

    def __str__(self) -> str:
        return f"BankStatement {self.id} [{self.account_code} {self.period_from}→{self.period_to}]"


class BankStatementLine(models.Model):
    """Ligne d'un relevé bancaire — une opération bancaire à rapprocher.

    Chaque ligne peut être rapprochée à une AccountEntry du plan comptable
    (compte 512) via le champ `matched_entry`.

    Statuts:
      unmatched — ligne importée, pas encore rapprochée
      matched   — rapprochée automatiquement ou manuellement
      manual    — rapprochée manuellement (override du matching auto)
      ignored   — ignorée volontairement (ex: intérêts automatiques)
    """

    MATCH_STATUS_UNMATCHED = "unmatched"
    MATCH_STATUS_MATCHED = "matched"
    MATCH_STATUS_MANUAL = "manual"
    MATCH_STATUS_IGNORED = "ignored"

    MATCH_STATUS_CHOICES = [
        (MATCH_STATUS_UNMATCHED, "Non rapproché"),
        (MATCH_STATUS_MATCHED, "Rapproché (auto)"),
        (MATCH_STATUS_MANUAL, "Rapproché (manuel)"),
        (MATCH_STATUS_IGNORED, "Ignoré"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    statement = models.ForeignKey(
        BankStatement,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    transaction_date = models.DateField(db_index=True)
    value_date = models.DateField(null=True, blank=True)
    label = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    # amount > 0 → crédit banque (encaissement) ; amount < 0 → débit banque (paiement)
    match_status = models.CharField(
        max_length=20,
        choices=MATCH_STATUS_CHOICES,
        default=MATCH_STATUS_UNMATCHED,
        db_index=True,
    )
    matched_entry = models.ForeignKey(
        AccountEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_reconciliation_lines",
    )
    matched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_bankstatementline"
        ordering = ["transaction_date", "id"]

    def __str__(self) -> str:
        return f"BankStatementLine {self.id} [{self.match_status}]"


class ChartOfAccounts(models.Model):
    """Plan de comptes PCG — un compte par ligne, par organisation.

    Chaque organisation dispose de son propre plan de comptes.
    Les comptes système (is_system=True) correspondent au PCG standard
    et ne peuvent pas être supprimés ni modifier leur account_code.

    ADR-001: org_id multi-tenant avec TenantManager.

    Attributes:
        id: UUID PK.
        org: Organisation propriétaire (FK).
        account_code: Code PCG (ex: "401000", "512100").
        account_label: Libellé du compte.
        account_class: Classe comptable 1-9 (calculée depuis account_code).
        account_type: Catégorie fonctionnelle du compte.
        is_system: True si compte issu du plan PCG standard.
        is_active: False pour masquer sans supprimer.
        parent_code: Code du compte parent pour l'arborescence (optionnel).
        created_at: Horodatage de création.
        updated_at: Horodatage de dernière modification.
    """

    ACCOUNT_TYPE_ACTIF = "actif"
    ACCOUNT_TYPE_PASSIF = "passif"
    ACCOUNT_TYPE_CHARGE = "charge"
    ACCOUNT_TYPE_PRODUIT = "produit"
    ACCOUNT_TYPE_TIERS = "tiers"
    ACCOUNT_TYPE_TRESORERIE = "tresorerie"
    ACCOUNT_TYPE_CHOICES = [
        (ACCOUNT_TYPE_ACTIF, "Actif"),
        (ACCOUNT_TYPE_PASSIF, "Passif"),
        (ACCOUNT_TYPE_CHARGE, "Charge"),
        (ACCOUNT_TYPE_PRODUIT, "Produit"),
        (ACCOUNT_TYPE_TIERS, "Comptes de tiers"),
        (ACCOUNT_TYPE_TRESORERIE, "Trésorerie"),
    ]

    # Mapping classe → type par défaut (PCG)
    _CLASS_TYPE_MAP: dict[int, str] = {
        1: ACCOUNT_TYPE_PASSIF,
        2: ACCOUNT_TYPE_ACTIF,
        3: ACCOUNT_TYPE_ACTIF,
        4: ACCOUNT_TYPE_TIERS,
        5: ACCOUNT_TYPE_TRESORERIE,
        6: ACCOUNT_TYPE_CHARGE,
        7: ACCOUNT_TYPE_PRODUIT,
        8: ACCOUNT_TYPE_ACTIF,
        9: ACCOUNT_TYPE_ACTIF,
    }

    objects = TenantManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="chart_of_accounts",
        db_column="org_id",
    )
    account_code = models.CharField(max_length=20, db_index=True)
    account_label = models.CharField(max_length=255)
    account_class = models.PositiveSmallIntegerField(
        help_text="Classe comptable 1-9 (premier chiffre du compte).",
    )
    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        default=ACCOUNT_TYPE_TIERS,
    )
    is_system = models.BooleanField(
        default=False,
        help_text="Compte PCG standard non supprimable.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    parent_code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Code du compte parent pour l'arborescence.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ledger_chartofaccounts"
        unique_together = [["org", "account_code"]]
        ordering = ["account_code"]

    def save(self, *args, **kwargs) -> None:
        """Déduit account_class et account_type avant sauvegarde."""
        if self.account_code:
            self.account_class = int(self.account_code[0])
            if not self.account_type or self.account_type == self.ACCOUNT_TYPE_TIERS:
                self.account_type = self._CLASS_TYPE_MAP.get(
                    self.account_class, self.ACCOUNT_TYPE_TIERS
                )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.account_code} — {self.account_label}"
