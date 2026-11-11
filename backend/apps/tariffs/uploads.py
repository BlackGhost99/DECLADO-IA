"""Import d'un tarif depuis l'écran Administration tarifaire, par un gestionnaire du référentiel.

Même chemin que le script de démarrage (-ImporterTarif) : le fichier passe par la quarantaine et
l'antivirus, puis l'importeur adapté. Un classeur « Tarif CEMAC SWD » apporte aussi le barème des
taxes, activé pour le territoire. L'édition est publiée en consultation : cherchable, sans être
présentée comme vérifiée officiellement.
"""

import logging
import os
import zipfile
from pathlib import Path

from django.conf import settings

from apps.core.exceptions import ApiError
from apps.documents import antivirus, quarantine
from apps.supervision import recorder

from . import services
from .models import PublicationState

logger = logging.getLogger(__name__)

MAX_BYTES = 40 * 1024 * 1024
STAGING_UNSCANNED_TARIFF_MAX_BYTES = 5 * 1024 * 1024
STAGING_UNSCANNED_TARIFF_MAX_UNPACKED_BYTES = 32 * 1024 * 1024


def staging_tariff_bypass(*, actor, kind: str) -> bool:
    """Allow only a reference manager to import a test workbook on non-debug staging."""
    return bool(
        kind == "xlsx"
        and actor is not None
        and actor.is_authenticated
        and actor.is_reference_manager
        and settings.STAGING_SKIP_ANTIVIRUS
        and settings.STAGING_SIMPLE_LOGIN
        and not settings.DEBUG
        and os.environ.get("APP_ENV", "").lower() == "staging"
    )


def _stage(upload, *, actor, kind: str):
    bypass = staging_tariff_bypass(actor=actor, kind=kind)
    try:
        if bypass:
            staged = quarantine.stage(upload, STAGING_UNSCANNED_TARIFF_MAX_BYTES)
            recorder.note(
                category="antivirus",
                level="warning",
                code="STAGING_TARIFF_SCAN_BYPASSED",
                message="Import de tarif de test sans analyse antivirus (gestionnaire uniquement).",
                actor=actor,
                details={"context": "tariff_import", "bytes": staged.size, "sha256_prefix": staged.sha256[:12]},
            )
        else:
            with antivirus.open_stream() as scanner:
                staged = quarantine.stage(upload, MAX_BYTES, on_chunk=scanner.feed)
                scanner.verdict()
    except antivirus.MalwareDetected:
        recorder.note(category="antivirus", level="error", code="MALWARE_DETECTED",
                      message="Signature malveillante détectée par ClamAV dans un tarif importé.",
                      details={"bytes": upload.size, "context": "tariff_import"})  # fmt: skip
        raise ApiError("MALWARE_DETECTED", "Fichier refusé par l'analyse antivirus.", 422) from None
    except antivirus.ScanUnavailable:
        logger.error("Scanner ClamAV indisponible pendant un import de tarif")
        recorder.note(category="antivirus", level="error", code="SCAN_UNAVAILABLE",
                      message="ClamAV n'a pas répondu pendant un import de tarif.",
                      details={"bytes": upload.size, "context": "tariff_import"})  # fmt: skip
        raise ApiError(
            "SCAN_UNAVAILABLE", "Analyse antivirus indisponible : réessayez quand ClamAV est démarré.", 503
        ) from None
    return staged


def import_upload(*, actor, upload, label: str = "") -> dict:
    name = Path(upload.name or "tarif").name
    kind = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if kind not in ("xlsx", "csv"):
        raise ApiError("UNSUPPORTED_FORMAT", "Format non pris en charge : un classeur .xlsx ou un fichier .csv.", 400)
    staged = _stage(upload, actor=actor, kind=kind)
    # openpyxl reconnaît un classeur à son extension : le fichier en quarantaine n'en a pas.
    path = staged.path.rename(staged.path.with_suffix(f".{kind}"))
    try:
        if kind == "xlsx":
            if not zipfile.is_zipfile(path):
                raise ApiError("UNSUPPORTED_FORMAT", "Ce fichier n'est pas un classeur Excel .xlsx valide.", 400)
            if staging_tariff_bypass(actor=actor, kind=kind):
                # Reject malformed or decompression-bomb archives before openpyxl parses them.
                with zipfile.ZipFile(path) as archive:
                    entries = archive.infolist()
                    total = sum(entry.file_size for entry in entries)
                    if total > STAGING_UNSCANNED_TARIFF_MAX_UNPACKED_BYTES or len(entries) > 250:
                        raise ApiError("UNSAFE_ARCHIVE", "Classeur de test trop volumineux une fois décompressé.", 413)
                    if any(
                        entry.file_size > 0 and entry.file_size / max(entry.compress_size, 1) > 150 for entry in entries
                    ):
                        raise ApiError("UNSAFE_ARCHIVE", "Archive de test anormalement compressée.", 422)
                    if archive.testzip() is not None:
                        raise ApiError("INVALID_FILE", "Archive Excel endommagée.", 422)
        label = (label or "").strip()[:120] or Path(name).stem
        schedule = None
        if kind == "xlsx":
            from apps.fiscal.importer import LayoutError, import_swd, is_swd_workbook
            from apps.fiscal.services import activate_schedule

            if is_swd_workbook(path):
                try:
                    schedule = import_swd(
                        path,
                        label=label,
                        title=name,
                        actor=actor,
                        low_pressure=staging_tariff_bypass(actor=actor, kind=kind),
                    )
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
