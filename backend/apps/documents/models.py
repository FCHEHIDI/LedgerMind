"""
apps/documents — Factures et jobs de traitement OCR/LLM.

Models:
  Invoice        — Facture fournisseur (champs sensibles chiffrés — ADR-004)
  ProcessingJob  — Job de traitement asynchrone (Celery)

ADR-001: org_id (ForeignKey Organization) sur tous les modèles.
ADR-004: EncryptedCharField pour vendor_name, vendor_siren, ht_amount,
         tva_amount, ttc_amount, raw_text.
"""
import uuid

from django.db import models
from fernet_fields import EncryptedCharField, EncryptedTextField

from apps.tenants.models import Organization


class Invoice(models.Model):
    """Facture fournisseur — données sensibles chiffrées au repos (ADR-004).

    Champs non chiffrés (index requis) :
      id, org, created_at, status, reference, source_key

    Champs chiffrés (fernet AES-128-CBC + HMAC-SHA256) :
      vendor_name, vendor_siren, ht_amount, tva_amount, ttc_amount, raw_text

    Note: vendor_siren_hash est un hash HMAC déterministe pour permettre
    la recherche par SIREN sans déchiffrer (ADR-004).
    """

    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("processing", "En traitement"),
        ("extracted", "Extrait"),
        ("validated", "Validé"),
        ("rejected", "Rejeté"),
        ("error", "Erreur"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="invoices",
        db_column="org_id",
    )
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )

    # Object storage key — format: {org_id}/{uuid}.pdf (ADR-004)
    # Never the original filename.
    source_key = models.CharField(max_length=512, blank=True)

    # Encrypted fields — ADR-004
    vendor_name = EncryptedCharField(max_length=255, blank=True)
    vendor_siren = EncryptedCharField(max_length=9, blank=True)
    # HMAC hash for indexed search on SIREN without decryption — ADR-004
    vendor_siren_hash = models.CharField(max_length=64, blank=True, db_index=True)
    ht_amount = EncryptedCharField(max_length=30, blank=True)   # Decimal as string
    tva_amount = EncryptedCharField(max_length=30, blank=True)
    ttc_amount = EncryptedCharField(max_length=30, blank=True)
    raw_text = EncryptedTextField(blank=True)

    invoice_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "documents_invoice"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        # NEVER include vendor_name or amounts in __str__ — ADR-005
        return f"Invoice {self.id} [{self.status}]"


class ProcessingJob(models.Model):
    """Job de traitement asynchrone Celery pour une facture.

    Traces le cycle de vie d'un job OCR/LLM sans stocker de données métier.
    Toutes les erreurs sont loggées avec l'UUID du job, jamais avec
    les données de la facture (ADR-005).
    """

    STATUS_CHOICES = [
        ("queued", "En file"),
        ("started", "Démarré"),
        ("success", "Succès"),
        ("failure", "Échec"),
        ("retry", "Relancé"),
    ]

    QUEUE_CHOICES = [
        ("pdf", "Queue PDF"),
        ("llm", "Queue LLM"),
        ("default", "Queue par défaut"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="processing_jobs",
        db_column="org_id",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    queue = models.CharField(max_length=20, choices=QUEUE_CHOICES, default="default")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="queued", db_index=True
    )
    error_code = models.CharField(max_length=50, blank=True)  # Code d'erreur, pas le message
    retry_count = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "documents_processingjob"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Job {self.id} [{self.status}]"
