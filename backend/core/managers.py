"""
core/managers.py — TenantManager (ADR-001).

Double protection Django : filtre automatiquement tous les querysets
par org_id, en plus du RLS PostgreSQL.

Usage:
    class Invoice(models.Model):
        objects = TenantManager()
        org = models.ForeignKey(Organization, ...)

    # Dans une view/service — filtre automatique par org courante:
    Invoice.objects.for_org(org_id).filter(status='pending')
"""
import logging
import uuid

from django.db import models

logger = logging.getLogger("core.managers")


class TenantQuerySet(models.QuerySet):
    """QuerySet avec méthode de filtrage par org_id.

    Double protection applicative en plus du RLS PostgreSQL (ADR-001).
    """

    def for_org(self, org_id: uuid.UUID) -> "TenantQuerySet":
        """Filtre le queryset par org_id.

        Args:
            org_id: UUID de l'organisation à filtrer.

        Returns:
            QuerySet filtré par org_id.
        """
        return self.filter(org_id=org_id)

    def active(self) -> "TenantQuerySet":
        """Filtre les enregistrements actifs (is_active=True si le champ existe).

        Returns:
            QuerySet filtré sur is_active=True.
        """
        return self.filter(is_active=True)


class TenantManager(models.Manager):
    """Manager Django avec isolation tenant automatique (ADR-001).

    Fournit la méthode for_org() pour filtrer explicitement par organisation.
    Le RLS PostgreSQL est la protection principale ; ce manager est
    la protection secondaire côté applicatif.

    Usage:
        class MyModel(models.Model):
            objects = TenantManager()
            org = models.ForeignKey(Organization, on_delete=models.PROTECT)
    """

    def get_queryset(self) -> TenantQuerySet:
        """Retourne un TenantQuerySet.

        Returns:
            TenantQuerySet de base sans filtres supplémentaires.
        """
        return TenantQuerySet(self.model, using=self._db)

    def for_org(self, org_id: uuid.UUID) -> TenantQuerySet:
        """Retourne un queryset filtré par org_id.

        Méthode principale à utiliser dans les views et services.
        Préférer cette méthode à filter(org_id=...) direct pour
        assurer la cohérence du double-filtering pattern.

        Args:
            org_id: UUID de l'organisation courante.

        Returns:
            QuerySet filtré par org_id.
        """
        return self.get_queryset().for_org(org_id)
