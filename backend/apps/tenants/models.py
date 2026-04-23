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
