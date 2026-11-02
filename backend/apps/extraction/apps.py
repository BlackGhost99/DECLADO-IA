from django.apps import AppConfig


class ExtractionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.extraction"
    verbose_name = "Extraction des factures"

    def ready(self):
        from django.conf import settings

        from . import handlers  # noqa: F401 - enregistre le gestionnaire outbox

        if settings.OCR_TESSERACT_CMD:
            try:
                import pytesseract
            except ImportError:
                return
            pytesseract.pytesseract.tesseract_cmd = settings.OCR_TESSERACT_CMD
