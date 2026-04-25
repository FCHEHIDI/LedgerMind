"""
apps/agents — Agents LangGraph pour l'automatisation comptable.

ADR-007 : un agent = une responsabilité = un modèle LLM adapté.
"""
from django.apps import AppConfig


class AgentsConfig(AppConfig):
    """Configuration de l'application agents."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agents"
    verbose_name = "Agents IA"
