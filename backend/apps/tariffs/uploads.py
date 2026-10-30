"""Import d'un tarif depuis l'écran Administration tarifaire, par un gestionnaire du référentiel.

Même chemin que le script de démarrage (-ImporterTarif) : le fichier passe par la quarantaine et
l'antivirus, puis l'importeur adapté. Un classeur « Tarif CEMAC SWD » apporte aussi le barème des
taxes, activé pour le territoire. L'édition est publiée en consultation : cherchable, sans être
présentée comme vérifiée officiellement.
"""

import logging
import zipfile
from pathlib import Path

from apps.core.exceptions import ApiError
from apps.documents import antivirus, quarantine

from . import services
from .models import PublicationState

logger = logging.getLogger(__name__)

MAX_BYTES = 40 * 1024 * 1024


def _stage(upload):
    try:
        with antivirus.open_stream() as scanner:
            staged = quarantine.stage(upload, MAX_BYTES, on_chunk=scanner.feed)
            scanner.verdict()
    except antivirus.MalwareDetected:
        raise ApiError("MALWARE_DETECTED", "Fichier refusé par l'analyse antivirus.", 422) from None
    except antivirus.ScanUnavailable:
        logger.error("Scanner ClamAV indisponible pendant un import de tarif")
        raise ApiError(
            "SCAN_UNAVAILABLE", "Analyse antivirus indisponible : réessayez quand ClamAV est démarré.", 503
        ) from None
    return staged


def import_upload(*, actor, upload, label: str = "") -> dict:
    name = Path(upload.name or "tarif").name
    kind = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if kind not in ("xlsx", "csv"):
        raise ApiError("UNSUPPORTED_FORMAT", "Format non pris en charge : un classeur .xlsx ou un fichier .csv.", 400)
    staged = _stage(upload)
    # openpyxl reconnaît un classeur à son extension : le fichier en quarantaine n'en a pas.
    path = staged.path.rename(staged.path.with_suffix(f".{kind}"))
    try:
        if kind == "xlsx" and not zipfile.is_zipfile(path):
            raise ApiError("UNSUPPORTED_FORMAT", "Ce fichier n'est pas un classeur Excel .xlsx valide.", 400)
        label = (label or "").strip()[:120] or Path(name).stem
        schedule = None
        if kind == "xlsx":
            from apps.fiscal.importer import LayoutError, import_swd, is_swd_workbook
            from apps.fiscal.services import activate_schedule

            if is_swd_workbook(path):
                try:
                    schedule = import_swd(path, label=label, title=name, actor=actor)
                except LayoutError as exc:
                    raise ApiError("INVALID_LAYOUT", str(exc), 400) from exc
                activate_schedule(schedule=schedule)
                edition = schedule.edition
            else:
                from .importers.xlsx import import_xlsx

                edition = import_xlsx(path, edition_label=label, title=name, actor=actor)
        else:
            from .importers.csv_export import import_csv

            edition = import_csv(path, edition_label=label, title=name, actor=actor)
        edition = services.publish_edition(edition=edition, actor=actor, mode=PublicationState.CONSULTATION)
    finally:
        path.unlink(missing_ok=True)
    run = edition.import_run
    return {
        "edition": {"id": str(edition.id), "label": edition.label, "publication_state": edition.publication_state},
        "counts": run.counts if run else {},
        "taxes": {"id": str(schedule.id), "label": schedule.label, "active": schedule.is_active} if schedule else None,
    }
