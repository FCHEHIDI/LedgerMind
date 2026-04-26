"""
apps/api/tasks.py — Tâches Celery RGPD et rétention des données.

Deux tâches périodiques enregistrées via django_celery_beat:
  1. process_pending_erasures — traite les demandes d'effacement en attente
  2. purge_expired_accounting_data — purge les données > 10 ans

Obligations légales (France):
  - Code commerce Art. L.123-22 et L.123-23 : conservation 10 ans minimum
    des livres comptables, factures, et pièces justificatives.
  - RGPD Art. 17 : droit à l'effacement (pseudonymisation si conservation
    légale obligatoire).

Ces tâches doivent être enregistrées dans django_celery_beat via la commande
de management `setup_periodic_tasks` ou directement via l'admin Django.

Enregistrement initial (à lancer une seule fois en post-deploy) :
    docker exec lm_django python manage.py shell -c "
    from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
    import json

    # Tâche 1 : traitement quotidien des effacements (01h00)
    cron_erasure, _ = CrontabSchedule.objects.get_or_create(
        minute='0', hour='1', day_of_week='*', day_of_month='*', month_of_year='*'
    )
    PeriodicTask.objects.get_or_create(
        name='RGPD — traitement effacements en attente',
        defaults=dict(crontab=cron_erasure, task='api.process_pending_erasures', args=json.dumps([]))
    )

    # Tâche 2 : purge annuelle des données > 10 ans (02h00 le 1er janvier)
    cron_purge, _ = CrontabSchedule.objects.get_or_create(
        minute='0', hour='2', day_of_week='*', day_of_month='1', month_of_year='1'
    )
    PeriodicTask.objects.get_or_create(
        name='RGPD — purge données comptables > 10 ans',
        defaults=dict(crontab=cron_purge, task='api.purge_expired_accounting_data', args=json.dumps([]))
    )
    print('Periodic tasks registered.')
    "
"""
import logging
from datetime import datetime, timezone, timedelta

from celery import shared_task

logger = logging.getLogger("api.tasks.gdpr")


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    queue="default",
    name="api.process_pending_erasures",
)
def process_pending_erasures(self) -> dict:
    """Traite toutes les demandes d'effacement RGPD en attente.

    Exécutée quotidiennement par Celery beat. Pour chaque
    GDPRErasureRequest(status=pending) la pseudonymisation est effectuée
    via GDPRService.process_erasure_request().

    Returns:
        Dict avec les compteurs processed et errors.
    """
    from apps.tenants.models import GDPRErasureRequest  # noqa: PLC0415
    from .gdpr import process_erasure_request  # noqa: PLC0415

    pending = GDPRErasureRequest.objects.filter(status=GDPRErasureRequest.STATUS_PENDING)
    total = pending.count()
    logger.info("process_pending_erasures: %d demandes en attente", total)

    processed = 0
    errors = 0
    for req in pending:
        try:
            process_erasure_request(str(req.id), processed_by_id=None)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "process_pending_erasures: erreur sur request %s — %s",
                req.id,
                exc,
            )
            errors += 1

    logger.info(
        "process_pending_erasures: terminé processed=%d errors=%d",
        processed,
        errors,
    )
    return {"processed": processed, "errors": errors}


@shared_task(
    bind=True,
    max_retries=1,
    default_retry_delay=600,
    queue="default",
    name="api.purge_expired_accounting_data",
)
def purge_expired_accounting_data(self) -> dict:
    """Purge les données comptables de plus de 10 ans.

    Obligation légale : Art. L.123-22 Code de commerce — conservation
    minimale 10 ans. Après cette durée, la suppression physique est possible.

    Seules sont supprimées les lignes isolées (sans lien actif vers un
    utilisateur en activité). Les JournalEntryAudit sont conservées
    pour traçabilité légale.

    ATTENTION: cette tâche supprime définitivement des données. Elle est
    enregistrée avec une fréquence annuelle (1er janvier 02h00).

    Returns:
        Dict avec les compteurs par modèle supprimé.
    """
    from apps.documents.models import Invoice  # noqa: PLC0415
    from apps.ledger.models import JournalEntry, BankStatement  # noqa: PLC0415

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=365 * 10)

    # Factures : suppression physique si > 10 ans et status terminal
    invoices_qs = Invoice.objects.filter(
        created_at__lt=cutoff,
        status__in=["validated", "rejected", "error"],
    )
    invoices_count = invoices_qs.count()
    logger.warning(
        "purge_expired: about to delete %d invoices older than %s",
        invoices_count,
        cutoff.date(),
    )
    invoices_qs.delete()

    # Écritures comptables validées > 10 ans
    journals_qs = JournalEntry.objects.filter(
        created_at__lt=cutoff,
        status="validated",
    )
    journals_count = journals_qs.count()
    logger.warning(
        "purge_expired: about to delete %d journal entries older than %s",
        journals_count,
        cutoff.date(),
    )
    journals_qs.delete()

    # Relevés bancaires > 10 ans
    statements_qs = BankStatement.objects.filter(period_to__lt=cutoff.date())
    statements_count = statements_qs.count()
    logger.warning(
        "purge_expired: about to delete %d bank statements older than %s",
        statements_count,
        cutoff.date(),
    )
    statements_qs.delete()

    result = {
        "invoices_deleted": invoices_count,
        "journal_entries_deleted": journals_count,
        "bank_statements_deleted": statements_count,
        "cutoff": cutoff.isoformat(),
    }
    logger.info("purge_expired: completed %s", result)
    return result
