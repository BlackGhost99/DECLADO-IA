from django.apps import AppConfig


class ScansConfig(AppConfig):
    name = "apps.scans"
    verbose_name = "Numérisation"

    def ready(self):
        from . import handlers  # noqa: F401  (enregistre le gestionnaire outbox)
