from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Configuration de l'app api."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.api"
    verbose_name = "API"
