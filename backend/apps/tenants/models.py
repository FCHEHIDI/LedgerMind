"""
apps/tenants — Gestion des organisations et des membres.

Models:
  Organization      — Tenant racine (1 ligne = 1 entreprise cliente)
  TenantMembership  — Association user ↔ organization + rôle

ADR-001: org_id présent sur tous les modèles métier.
ADR-002: rôles org_owner, org_admin, accountant, auditor, ledgermind_staff.
"""
import uuid

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Organization(models.Model):
    """Tenant racine — représente une entreprise cliente.

    Chaque organization est isolée via PostgreSQL Row-Level Security (ADR-001).
    Le champ `siren` est stocké en clair ici car il sert d'identifiant métier ;
    la donnée SIREN dans les factures est chiffrée (ADR-004).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    siren = models.CharField(max_length=9, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_organization"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.siren})"


class TenantMembership(models.Model):
    """Association user ↔ organization avec rôle — ADR-002.

    Rôles:
      org_owner       — propriétaire, tous les droits
      org_admin       — admin organisationnel
      accountant      — comptable, lecture/écriture factures + écritures
      auditor         — lecture seule (export, rapports)
      ledgermind_staff — support interne LedgerMind (accès restreint)
    """

    ROLE_CHOICES = [
        ("org_owner", "Propriétaire"),
        ("org_admin", "Administrateur"),
        ("accountant", "Comptable"),
        ("auditor", "Auditeur"),
        ("ledgermind_staff", "Staff LedgerMind"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_membership"
        unique_together = [("user", "organization")]
        ordering = ["organization", "user"]

    def __str__(self) -> str:
        return f"{self.user.username} @ {self.organization.name} ({self.role})"


class OrgCreationRequest(models.Model):
    """Demande de création d'organisation soumise par un utilisateur invité.

    Workflow:
      pending  → approved (superuser) → Organization + TenantMembership créés
      pending  → rejected (superuser)

    Le champ `reviewer` est NULL jusqu'à la décision.
    Les notifications sont déléguées à NotificationService (apps/api/notifications.py).
    """

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_APPROVED, "Approuvée"),
        (STATUS_REJECTED, "Refusée"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requester = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="org_requests",
    )
    name = models.CharField(max_length=255)
    siren = models.CharField(max_length=9)
    message = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    reviewer = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_org_requests",
    )
    reviewer_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tenants_org_creation_request"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"OrgRequest({self.name}, {self.siren}) by {self.requester.username} [{self.status}]"


class GDPRErasureRequest(models.Model):
    """Demande de suppression RGPD (Article 17 — Droit à l'effacement).

    Lorsqu'un utilisateur demande la suppression de son compte, une instance
    est créée. Le traitement effectue une pseudonymisation (pas une suppression
    physique) afin de respecter l'obligation de conservation comptable de
    10 ans (Code commerce L.123-22 & L.123-23).

    Workflow:
      pending  → processed (superuser ou tâche Celery)

    Pseudonymisation effectuée par GDPRService.pseudonymize_user() :
      - User.email     → f"deleted_{uuid}@anonymized.invalid"
      - User.username  → f"deleted_{uuid}"
      - User.first_name, User.last_name → ""
      - User.is_active → False
      - User.password  → unusable password (set_unusable_password)
    Les FK vers User dans JournalEntryAudit etc. sont conservées (obligation légale).
    """

    STATUS_PENDING = "pending"
    STATUS_PROCESSED = "processed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_PROCESSED, "Traité"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="erasure_requests",
    )
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    processed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="processed_erasures",
    )

    class Meta:
        db_table = "tenants_gdpr_erasure_request"
        ordering = ["-requested_at"]

    def __str__(self) -> str:
        return f"GDPRErasureRequest({self.user_id}) [{self.status}]"
