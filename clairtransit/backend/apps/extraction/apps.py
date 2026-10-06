from django.apps import AppConfig


class ExtractionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.extraction"
    verbose_name = "Extraction des factures"

    def ready(self):
        from . import handlers  # noqa: F401 - enregistre le gestionnaire outbox
