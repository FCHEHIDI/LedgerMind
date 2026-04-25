# config/__init__.py
# Expose l'app Celery au niveau du package pour `celery -A config worker`.
from .celery import app as celery_app

__all__ = ("celery_app",)

