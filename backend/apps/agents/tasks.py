"""
apps/agents/tasks.py — Tâches Celery pour déclencher le pipeline d'agents.

Les tâches sont sur la queue "llm" (worker séparé, I/O-bound Ollama).

Usage (depuis les views Django) :
    process_invoice_task.apply_async(
        args=[str(invoice.id), str(job.id), str(request.user.id)],
        queue="llm",
    )

ADR-007 — Architecture des agents.
ADR-005 — Logs sans données métier.
"""
import logging

from celery import shared_task

from apps.agents.state import make_initial_state
from apps.agents.graph import run_invoice_pipeline

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="llm",
    name="agents.process_invoice",
)
def process_invoice_task(
    self,
    invoice_id: str,
    job_id: str,
    user_id: str,
    org_id: str,
    source_key: str,
) -> dict:
    """Tâche Celery : exécute le pipeline IA complet pour une facture.

    Séquence :
      1. Crée l'AgentState initial
      2. Invoque le graphe LangGraph (doc_intake → accounting_reasoner)
      3. Retourne le résumé du résultat (sans données métier — ADR-005)

    Args:
        invoice_id: UUID de la facture à traiter.
        job_id: UUID du ProcessingJob associé.
        user_id: UUID de l'utilisateur déclencheur.
        org_id: UUID de l'organisation (tenant).
        source_key: Clé MinIO du PDF (format: {org_id}/{uuid}.pdf).

    Returns:
        Dict avec le résumé du résultat :
            - invoice_id (str)
            - journal_entry_id (str | None)
            - errors (list[str])
            - warnings (list[str])
            - requires_human_review (bool)

    Raises:
        self.retry: Relance automatique sur erreur transitoire.
    """
    logger.info(
        "task.process_invoice.start invoice_id=%s job_id=%s attempt=%d",
        invoice_id, job_id, self.request.retries + 1,
    )

    try:
        initial_state = make_initial_state(
            org_id=org_id,
            user_id=user_id,
            invoice_id=invoice_id,
            job_id=job_id,
            source_key=source_key,
        )
        final_state = run_invoice_pipeline(initial_state)

    except Exception as exc:
        logger.error(
            "task.process_invoice.error invoice_id=%s attempt=%d err=%s",
            invoice_id, self.request.retries + 1, type(exc).__name__,
        )
        # Retry sur erreurs transitoires (connexion Ollama, MinIO)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))

        # Marquer le job en échec après épuisement des retries
        try:
            from apps.agents.tools import update_job_status
            update_job_status(job_id, "failure", error_code="TASK_MAX_RETRIES")
        except Exception:
            pass

        return {
            "invoice_id": invoice_id,
            "journal_entry_id": None,
            "errors": ["TASK_MAX_RETRIES"],
            "warnings": [],
            "requires_human_review": True,
        }

    result = {
        "invoice_id": invoice_id,
        "journal_entry_id": final_state.get("journal_entry_id"),
        "errors": final_state.get("errors", []),
        "warnings": final_state.get("warnings", []),
        "requires_human_review": final_state.get("requires_human_review", False),
    }

    logger.info(
        "task.process_invoice.end invoice_id=%s success=%s entry_id=%s",
        invoice_id,
        not result["errors"],
        result["journal_entry_id"],
    )
    return result
