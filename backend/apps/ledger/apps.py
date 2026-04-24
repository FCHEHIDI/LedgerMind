from django.apps import AppConfig


class LedgerConfig(AppConfig):
    """Configuration de l'app ledger."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ledger"
    verbose_name = "Comptabilité"
