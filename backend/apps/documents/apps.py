from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    """Configuration de l'app documents."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.documents"
    verbose_name = "Factures et traitements"
