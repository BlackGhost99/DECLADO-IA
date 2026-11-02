import os
import shutil
from pathlib import Path

from django.apps import AppConfig


def locate_tesseract(base_dir: Path, environ=os.environ, which=shutil.which) -> tuple[str, str]:
    """(exécutable Tesseract, dossier des langues) quand OCR_TESSERACT_CMD n'est pas fourni.

    Le script Windows installe Tesseract dans <installation>\\outils\\tesseract et les langues dans
    <installation>\\outils\\tessdata, le code étant dans <installation>\\code\\backend. Un ancien script
    de démarrage ne transmet pas ces chemins à l'API : on les retrouve ici. Rien trouvé : ("", "")."""
    install = base_dir.parent.parent
    tools = install / "outils"
    exe = ""
    if not which("tesseract"):
        candidates = [tools / "tesseract" / "tesseract.exe"]
        for root in (
            environ.get("ProgramFiles"),
            environ.get("LOCALAPPDATA") and Path(environ["LOCALAPPDATA"]) / "Programs",
        ):
            if root:
                candidates.append(Path(root) / "Tesseract-OCR" / "tesseract.exe")
        exe = next((str(c) for c in candidates if c.is_file()), "")
    tessdata = ""
    if not environ.get("TESSDATA_PREFIX") and (tools / "tessdata").is_dir():
        tessdata = str(tools / "tessdata")
    return exe, tessdata


class ExtractionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.extraction"
    verbose_name = "Extraction des factures"

    def ready(self):
        from django.conf import settings

        from . import handlers  # noqa: F401 - enregistre le gestionnaire outbox

        try:
            import pytesseract
        except ImportError:
            return
        command = settings.OCR_TESSERACT_CMD
        if not command:
            command, tessdata = locate_tesseract(Path(settings.BASE_DIR))
            if tessdata:
                os.environ["TESSDATA_PREFIX"] = tessdata
        if command:
            pytesseract.pytesseract.tesseract_cmd = command
