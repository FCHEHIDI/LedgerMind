from django.apps import AppConfig


class TenantsConfig(AppConfig):
    """Configuration de l'app tenants."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenants"
    verbose_name = "Organisations"
