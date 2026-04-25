"""
Configuration Celery pour LedgerMind.

L'instance `app` est importée dans config/__init__.py pour que
`celery -A config worker` la trouve automatiquement.

Queues :
  default  — tâches générales
  pdf      — extraction PDF (CPU-bound)
  llm      — appels Ollama (I/O-bound, peut être long)

ADR-005 : résultats persistés en base via django-celery-results.
"""
import logging
import os

from celery import Celery
from celery.utils.log import get_task_logger

logger = logging.getLogger(__name__)
task_logger = get_task_logger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("ledgermind")

# Charge la config depuis CELERY_* dans settings Django (namespace évite
# les collisions avec d'autres settings).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Découverte automatique des tâches dans apps/*/tasks.py
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:
    """Tâche de diagnostic — affiche la requête Celery en cours.

    Args:
        self: Instance de la tâche (bind=True).
    """
    task_logger.info("Request: %r", self.request)
