"""Temporary background SWD imports on free staging, without a separate paid worker.

The uploaded XLSX and the job state live in Django's staging database cache.
This path is enabled only by the existing staging-only reference-manager bypass.
It is deliberately not used in production, where scanning remains mandatory.
"""

import hashlib
import logging
import threading
import time
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError, close_old_connections, transaction

from apps.core.exceptions import ApiError

from .uploads import STAGING_UNSCANNED_TARIFF_MAX_BYTES, import_upload, staging_tariff_bypass

logger = logging.getLogger(__name__)
ACTIVE_KEY = "declado:staging:tariff-import:active"
JOB_PREFIX = "declado:staging:tariff-import:"
CACHE_TTL = 60 * 60
STALE_SECONDS = 60 * 60
WORKER_EPOCH = uuid.uuid4().hex
ORPHAN_GRACE_SECONDS = 5 * 60


def _key(job_id: str) -> str:
    return f"{JOB_PREFIX}{job_id}"


def _retry_database_cache(action):
    """Staging Postgres may restart briefly; never lose an import verdict immediately."""
    for attempt in range(5):
        try:
            return action()
        except OperationalError:
            close_old_connections()
            if attempt == 4:
                raise
            time.sleep(2**attempt)


def _state(job_id: str) -> dict | None:
    return _retry_database_cache(lambda: cache.get(_key(job_id)))


def _put(job_id: str, data: dict) -> None:
    _retry_database_cache(lambda: cache.set(_key(job_id), data, timeout=CACHE_TTL))


def _cleanup(job_id: str) -> None:
    def clean():
        cache.delete(_key(job_id) + ":data")
        if cache.get(ACTIVE_KEY) == job_id:
            cache.delete(ACTIVE_KEY)

    try:
        _retry_database_cache(clean)
    except OperationalError:
        logger.warning("Staging tariff cache cleanup postponed after PostgreSQL interruption")


def _abandoned(state: dict) -> bool:
    age = time.time() - state["created_timestamp"]
    return age > STALE_SECONDS or (age > ORPHAN_GRACE_SECONDS and state.get("worker_epoch") != WORKER_EPOCH)


def job_for_actor(*, job_id, actor) -> dict:
    state = _state(str(job_id))
    if state is None or state.get("actor_id") != str(actor.pk):
        raise ApiError("NOT_FOUND", "Import de test introuvable.", 404)
    if state["state"] in ("queued", "running") and _abandoned(state):
        state = {
            **state,
            "state": "failed",
            "message": "Import interrompu ou trop long ; vérifiez les éditions avant un nouvel envoi.",
        }
        _put(str(job_id), state)
        if cache.get(ACTIVE_KEY) == str(job_id):
            cache.delete(ACTIVE_KEY)
        cache.delete(_key(str(job_id)) + ":data")
    return {k: v for k, v in state.items() if k not in ("actor_id", "created_timestamp", "worker_epoch")}


def _execute(job_id: str, actor_id: str, filename: str, label: str) -> None:
    close_old_connections()
    try:
        state = _state(job_id)
        if not state:
            return
        _put(job_id, {**state, "state": "running", "message": "Analyse et insertion des codes et des taxes en cours…"})
        raw = cache.get(_key(job_id) + ":data")
        if not raw:
            raise RuntimeError("Le fichier temporaire n'est plus disponible.")
        actor = get_user_model().objects.get(pk=actor_id)
        result = import_upload(
            actor=actor,
            upload=SimpleUploadedFile(
                filename,
                raw,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            label=label,
        )
        state = _state(job_id) or {}
        _put(job_id, {**state, "state": "succeeded", "message": "Tarif importé avec succès.", "result": result})
    except ApiError as exc:
        logger.warning("Staging tariff import %s rejected: %s", job_id, exc.error_code)
        state = _state(job_id) or {}
        _put(job_id, {**state, "state": "failed", "message": str(exc.detail), "error_code": exc.error_code})
    except Exception:
        logger.exception("Staging tariff import %s failed", job_id)
        state = _state(job_id) or {}
        _put(
            job_id,
            {
                **state,
                "state": "failed",
                "message": "L'import a échoué côté serveur. Consulter les journaux Render.",
                "error_code": "IMPORT_FAILED",
            },
        )
    finally:
        _cleanup(job_id)
        close_old_connections()


def _start_thread(job_id: str, actor_id: str, filename: str, label: str) -> None:
    threading.Thread(
        target=_execute, args=(job_id, actor_id, filename, label), name="staging-tariff-import", daemon=True
    ).start()


def queue_import(*, actor, upload, label: str) -> dict:
    """Return quickly with a job ID; the expensive importer runs outside the HTTP request."""
    filename = Path(upload.name or "tarif.xlsx").name
    if not filename.lower().endswith(".xlsx") or not staging_tariff_bypass(actor=actor, kind="xlsx"):
        raise ApiError("FORBIDDEN", "Import asynchrone réservé au gestionnaire du staging.", 403)
    if upload.size is not None and upload.size > STAGING_UNSCANNED_TARIFF_MAX_BYTES:
        raise ApiError("FILE_TOO_LARGE", "Classeur de test trop volumineux (maximum 5 Mo).", 413)
    raw = upload.read(STAGING_UNSCANNED_TARIFF_MAX_BYTES + 1)
    if len(raw) > STAGING_UNSCANNED_TARIFF_MAX_BYTES:
        raise ApiError("FILE_TOO_LARGE", "Classeur de test trop volumineux (maximum 5 Mo).", 413)
    if not zipfile.is_zipfile(BytesIO(raw)):
        raise ApiError("UNSUPPORTED_FORMAT", "Le fichier sélectionné n'est pas un classeur Excel valide.", 400)
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > 250 or sum(item.file_size for item in entries) > 32 * 1024 * 1024:
            raise ApiError("UNSAFE_ARCHIVE", "Archive Excel trop volumineuse après décompression.", 413)
        if any(item.file_size > 0 and item.file_size / max(item.compress_size, 1) > 150 for item in entries):
            raise ApiError("UNSAFE_ARCHIVE", "Archive Excel anormalement compressée.", 422)
        if any(
            item.filename.startswith("../") or "/../" in item.filename or item.filename.startswith("/")
            for item in entries
        ):
            raise ApiError("UNSAFE_ARCHIVE", "Archive Excel non conforme.", 422)
        if archive.testzip() is not None:
            raise ApiError("INVALID_FILE", "Classeur Excel endommagé.", 422)

    running_id = cache.get(ACTIVE_KEY)
    if running_id:
        active_state = _state(running_id)
        if active_state and active_state.get("state") in ("queued", "running"):
            if not _abandoned(active_state):
                raise ApiError("IMPORT_BUSY", "Un import de tarif est déjà en cours. Attendez sa fin.", 409)
            _put(
                running_id,
                {
                    **active_state,
                    "state": "failed",
                    "message": "Import interrompu par un redémarrage. Consultez les éditions avant de reprendre.",
                },
            )
        cache.delete(ACTIVE_KEY)

    job_id = str(uuid.uuid4())
    if not cache.add(ACTIVE_KEY, job_id, timeout=CACHE_TTL):
        raise ApiError("IMPORT_BUSY", "Un import de tarif est déjà en cours.", 409)
    state = {
        "job_id": job_id,
        "actor_id": str(actor.pk),
        "state": "queued",
        "message": "Fichier reçu. Import planifié…",
        "created_timestamp": time.time(),
        "worker_epoch": WORKER_EPOCH,
        "sha256_prefix": hashlib.sha256(raw).hexdigest()[:12],
    }
    try:
        cache.set(_key(job_id) + ":data", raw, timeout=CACHE_TTL)
        _put(job_id, state)
        transaction.on_commit(lambda: _start_thread(job_id, str(actor.pk), filename, label[:120]))
    except BaseException:
        cache.delete(_key(job_id) + ":data")
        cache.delete(_key(job_id))
        if cache.get(ACTIVE_KEY) == job_id:
            cache.delete(ACTIVE_KEY)
        raise
    return {"job_id": job_id, "state": "queued", "message": "Fichier reçu. Import en arrière-plan."}
