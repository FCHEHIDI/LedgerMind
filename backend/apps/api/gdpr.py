"""
apps/api/gdpr.py — Service RGPD (ADR-GDPR).

Implémente le droit à l'effacement (RGPD Art. 17) via pseudonymisation.
La suppression physique des données comptables est interdite par le Code
de commerce (Art. L.123-22 et L.123-23 — 10 ans de conservation).

Stratégie:
  1. L'utilisateur soumet une demande via POST /api/v1/auth/request-erasure/
  2. Un GDPRErasureRequest(status=pending) est créé.
  3. process_erasure_request() est appelé (manuellement ou par Celery beat).
  4. pseudonymize_user() anonymise les champs PII du User Django.
  5. Le User devient inutilisable mais les FK comptables (JournalEntryAudit
     etc.) restent intactes pour l'obligation légale.

Pseudonymisation appliquée:
  - User.email     → "deleted_<uuid4>@anonymized.invalid"
  - User.username  → "deleted_<uuid4>"
  - User.first_name, User.last_name → ""
  - User.is_active → False
  - User.password  → mot de passe inutilisable (set_unusable_password)
  - TenantMembership.is_active → False pour toutes les memberships
"""
import logging
import uuid
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.db import transaction

logger = logging.getLogger("api.gdpr")

User = get_user_model()


def pseudonymize_user(user_id: int) -> None:
    """Pseudonymise un utilisateur — supprime ses PII sans détruire les FK.

    Args:
        user_id: PK Django de l'utilisateur à pseudonymiser.

    Raises:
        User.DoesNotExist: Si l'utilisateur n'existe pas ou a déjà été
            pseudonymisé (is_active=False et email contient @anonymized.invalid).
        ValueError: Si user_id est None.
    """
    if user_id is None:
        raise ValueError("user_id cannot be None")

    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(pk=user_id)
        except User.DoesNotExist:
            logger.warning("pseudonymize_user: user %s not found — skipping", user_id)
            raise

        # Idempotency guard — déjà pseudonymisé
        if not user.is_active and "@anonymized.invalid" in (user.email or ""):
            logger.info("pseudonymize_user: user %s already pseudonymized", user_id)
            return

        anon_suffix = uuid.uuid4().hex
        user.email = f"deleted_{anon_suffix}@anonymized.invalid"
        user.username = f"deleted_{anon_suffix}"
        user.first_name = ""
        user.last_name = ""
        user.is_active = False
        user.set_unusable_password()
        user.save(update_fields=[
            "email", "username", "first_name", "last_name",
            "is_active", "password",
        ])

        # Désactiver toutes les memberships (accès multi-org)
        # Import local pour éviter les circular imports
        from apps.tenants.models import TenantMembership  # noqa: PLC0415
        TenantMembership.objects.filter(user_id=user_id).update(is_active=False)

        logger.info(
            "pseudonymize_user: user %s pseudonymized → %s",
            user_id,
            user.username,
        )


def process_erasure_request(erasure_request_id: str, processed_by_id: int | None = None) -> None:
    """Traite une demande d'effacement RGPD.

    Pseudonymise l'utilisateur associé et marque la demande comme traitée.

    Args:
        erasure_request_id: UUID (str) du GDPRErasureRequest à traiter.
        processed_by_id: PK Django de l'admin qui traite la demande,
            ou None si traitement automatique (Celery).

    Raises:
        GDPRErasureRequest.DoesNotExist: Si la demande n'existe pas.
    """
    from apps.tenants.models import GDPRErasureRequest  # noqa: PLC0415

    with transaction.atomic():
        try:
            req = GDPRErasureRequest.objects.select_for_update().get(pk=erasure_request_id)
        except GDPRErasureRequest.DoesNotExist:
            logger.error("process_erasure_request: request %s not found", erasure_request_id)
            raise

        if req.status == GDPRErasureRequest.STATUS_PROCESSED:
            logger.info("process_erasure_request: request %s already processed", erasure_request_id)
            return

        if req.user_id is not None:
            pseudonymize_user(req.user_id)

        req.status = GDPRErasureRequest.STATUS_PROCESSED
        req.processed_at = datetime.now(tz=timezone.utc)
        req.processed_by_id = processed_by_id
        req.save(update_fields=["status", "processed_at", "processed_by_id"])

    logger.info(
        "process_erasure_request: request %s processed by %s",
        erasure_request_id,
        processed_by_id,
    )
