"""Services de numérisation : toute écriture passe ici, bornée à la société et journalisée."""

import io
import logging
from collections import Counter
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from PIL import Image

from apps.audit.services import record_event
from apps.cases import services as cases
from apps.cases.models import CaseDocument, CustomsCase
from apps.core.exceptions import ApiError
from apps.core.models import BackgroundJob
from apps.core.outbox import enqueue
from apps.documents import services as documents
from apps.documents.sniff import READABILITY_LABELS, Readability
from apps.documents.storage import get_storage
from apps.extraction import services as extraction
from apps.extraction.adapters import ExtractionFailure

from . import imaging
from .models import ScanBatch, ScanPage, ScanPiece, ScanSource
from .segment import PageInfo, propose
from .titles import PageReading, read_page

logger = logging.getLogger(__name__)

TOPIC = "scans.process"
NOT_FOUND = ("NOT_FOUND", "Élément introuvable.", 404)
EDITABLE_STATES = (ScanBatch.State.OPEN, ScanBatch.State.PROCESSING, ScanBatch.State.TO_SORT)
# Une page lue par OCR avec moins de mots, ou une confiance moyenne plus basse, est « peu lisible ».
MIN_WORDS = 5
MIN_CONFIDENCE = 50.0


def max_pages() -> int:
    return settings.SCAN_BATCH_MAX_PAGES


def _get(qs, pk):
    obj = qs.filter(pk=pk).first() if pk else None
    if obj is None:
        raise ApiError(*NOT_FOUND)
    return obj


def _event(org, actor, event_type, entity, batch, previous=None, current=None):
    record_event(
        organization=org,
        actor=actor,
        event_type=event_type,
        entity=entity,
        previous=previous,
        current=current,
        scope=batch.case.scope,
    )


def _require_editable(batch: ScanBatch):
    if batch.state not in EDITABLE_STATES:
        raise ApiError("BATCH_CLOSED", f"Lot « {batch.get_state_display()} » : il ne peut plus être modifié.", 409)
    cases._require_editable(batch.case.current_revision)


def batches(org):
    return ScanBatch.objects.for_organization(org).select_related("case__current_revision", "job", "created_by")


def batch_for(org, batch_id, *, lock=False) -> ScanBatch:
    qs = batches(org)
    if lock:
        qs = qs.select_for_update(of=("self",))
    return _get(qs, batch_id)


def page_for(org, page_id, *, lock=False) -> ScanPage:
    qs = ScanPage.objects.for_organization(org).select_related("batch__case__current_revision", "piece")
    if lock:
        qs = qs.select_for_update(of=("self",))
    return _get(qs, page_id)


def piece_for(org, piece_id) -> ScanPiece:
    return _get(ScanPiece.objects.for_organization(org).select_related("batch__case__current_revision"), piece_id)


# --- Création et dépôt -------------------------------------------------------------------


@transaction.atomic
def create_batch(*, org, actor, case: CustomsCase, source: str, label: str = "") -> ScanBatch:
    cases._require_editable(case.current_revision)
    if source not in ScanBatch.Source.values:
        raise ApiError("VALIDATION_ERROR", "Source de numérisation inconnue.", 400)
    if not label:
        when = timezone.localtime().strftime("%d/%m %H:%M")
        label = f"Photos du {when}" if source == ScanBatch.Source.CAMERA else f"Lot du {when}"
    batch = ScanBatch.objects.create(
        organization=org,
        case=case,
        revision=case.current_revision,
        source=source,
        label=label[:200],
        created_by=actor,
    )
    _event(org, actor, "scan.batch_created", batch, batch, current={"source": source, "label": batch.label})
    return batch


def _page_total(batch) -> int:
    return batch.pages.exclude(removed=ScanPage.Removal.REPLACED).count()


def _next_position(batch) -> Decimal:
    top = batch.pages.aggregate(m=Max("position"))["m"]
    return (top or Decimal(0)) + 1


def _store(org, actor, batch, upload) -> ScanSource:
    document = documents.store_upload(
        organization=org,
        actor=actor,
        upload=upload,
        declared_mime=getattr(upload, "content_type", "") or "",
        allow_tiff=True,
    )
    if document.mime not in imaging.ACCEPTED_SOURCES:
        raise ApiError("UNSUPPORTED_TYPE", "Un lot numérisé accepte PDF, PNG, JPEG ou TIFF.", 422)
    if document.readability != Readability.OK:
        raise ApiError("DOCUMENT_NOT_READABLE", READABILITY_LABELS[document.readability], 422)
    ordinal = (batch.sources.aggregate(m=Max("ordinal"))["m"] or 0) + 1
    return ScanSource.objects.create(organization=org, batch=batch, document=document, ordinal=ordinal)


def _queue(org, actor, batch) -> None:
    job = BackgroundJob.objects.create(
        organization=org,
        kind="scan",
        input_hash=str(batch.id),
        scope=batch.case.scope,
        created_by=actor,
        progress={"done": 0, "total": 0},
    )
    batch.job = job
    if batch.state == ScanBatch.State.TO_SORT or batch.source == ScanBatch.Source.SCANNER:
        batch.state = ScanBatch.State.PROCESSING
    batch.save(update_fields=["job", "state", "updated_at"])
    enqueue(TOPIC, {"batch_id": str(batch.id), "job_id": str(job.id)}, organization=org)


def add_files(*, org, actor, batch_id, uploads) -> ScanBatch:
    """NUM-02 : un ou plusieurs fichiers du scanner (PDF multipage, images, TIFF), lus en arrière-plan."""
    if not uploads:
        raise ApiError("VALIDATION_ERROR", "Aucun fichier reçu.", 400)
    with transaction.atomic():
        batch = batch_for(org, batch_id, lock=True)
        _require_editable(batch)
        added = []
        for upload in uploads:
            source = _store(org, actor, batch, upload)
            path = get_storage().path_for_reading(source.document.object_key)
            try:
                source.page_count = imaging.page_count(path, source.document.mime)
            except imaging.PageError as exc:
                raise ApiError("DOCUMENT_NOT_READABLE", f"{upload.name} : {exc}", 422) from None
            if _page_total(batch) + sum(s.page_count for s in added) + source.page_count > max_pages():
                raise ApiError(
                    "BATCH_TOO_LARGE",
                    f"Un lot compte au plus {max_pages()} pages : créer un second lot pour la suite.",
                    413,
                    {"max_pages": max_pages()},
                )
            source.save(update_fields=["page_count"])
            added.append(source)
        _event(
            org,
            actor,
            "scan.files_added",
            batch,
            batch,
            current={"files": [s.document.original_name for s in added], "pages": sum(s.page_count for s in added)},
        )
        _queue(org, actor, batch)
    return batch


def add_photo(*, org, actor, batch_id, upload, piece_id=None, usage="") -> ScanPage:
    """NUM-03 : une page prise au téléphone ou à la webcam, rangée dans la pièce en cours de prise de vue."""
    with transaction.atomic():
        batch = batch_for(org, batch_id, lock=True)
        _require_editable(batch)
        if _page_total(batch) + 1 > max_pages():
            raise ApiError("BATCH_TOO_LARGE", f"Un lot compte au plus {max_pages()} pages : créer un second lot.", 413)
        source = _store(org, actor, batch, upload)
        source.page_count, source.split_done = 1, True
        source.save(update_fields=["page_count", "split_done"])
        if piece_id:
            piece = _get(batch.pieces.filter(case_document__isnull=True), piece_id)
        else:
            usage = usage if usage in CaseDocument.Usage.values else CaseDocument.Usage.OTHER
            piece = _new_piece(batch, usage, "choisi à la prise de vue", by_user=True)
        page = ScanPage.objects.create(
            organization=org,
            batch=batch,
            source=source,
            source_page=1,
            position=_next_position(batch),
            piece=piece,
            sorted=True,
        )
        _event(org, actor, "scan.photo_added", page, batch, current={"piece": str(piece.id), "usage": piece.usage})
        _queue(org, actor, batch)
    return page


@transaction.atomic
def finish_capture(*, org, actor, batch_id) -> ScanBatch:
    """Fin de la prise de vue : le lot passe au tri une fois toutes les pages lues."""
    batch = batch_for(org, batch_id, lock=True)
    _require_editable(batch)
    if batch.state == ScanBatch.State.OPEN:
        pending = batch.pages.filter(state=ScanPage.State.PENDING).exists()
        batch.state = ScanBatch.State.PROCESSING if pending else ScanBatch.State.TO_SORT
        batch.save(update_fields=["state", "updated_at"])
        _event(org, actor, "scan.capture_finished", batch, batch, current={"pages": _page_total(batch)})
    return batch


def _new_piece(batch, usage, reason, *, by_user=False) -> ScanPiece:
    ordinal = (batch.pieces.aggregate(m=Max("ordinal"))["m"] or 0) + 1
    return ScanPiece.objects.create(
        organization=batch.organization,
        batch=batch,
        ordinal=ordinal,
        usage=usage,
        reason=reason[:300],
        usage_by_user=by_user,
    )


# --- Lecture des pages (worker) --------------------------------------------------------------


def _progress(job_id, phase, done, total):
    if job_id:
        BackgroundJob.objects.filter(pk=job_id).update(phase=phase, progress={"done": done, "total": total})


def _split_sources(batch) -> None:
    for source in batch.sources.filter(split_done=False).select_related("document"):
        with transaction.atomic():
            position = _next_position(batch)
            ScanPage.objects.bulk_create(
                ScanPage(
                    organization=batch.organization,
                    batch=batch,
                    source=source,
                    source_page=n,
                    position=position + n - 1,
                )
                for n in range(1, (source.page_count or 0) + 1)
            )
            source.split_done = True
            source.save(update_fields=["split_done", "updated_at"])


def _read_one(page: ScanPage) -> None:
    """Prépare et lit une page ; une page en échec est signalée sans arrêter le lot."""
    document = page.source.document
    path = get_storage().path_for_reading(document.object_key)
    notes, words, origin, confidence = [], None, "", None
    try:
        loaded = imaging.load_page(path, document.mime, page.source_page)
    except imaging.PageError as exc:
        ScanPage.objects.filter(pk=page.pk).update(state=ScanPage.State.FAILED, notes=[str(exc)])
        return
    image = loaded.image
    if page.batch.source == ScanBatch.Source.CAMERA:
        image, cropped = imaging.crop_document(image)
        if cropped:
            notes.append("Photo recadrée sur la feuille.")
    blank = imaging.is_blank(image)
    if loaded.words:
        words, origin = loaded.words, "pdf_text"
    elif not blank:
        try:
            result = imaging.ocr_words(image)
        except ExtractionFailure as exc:
            notes.append(exc.message)
        else:
            if result.rotation:
                image = image.rotate(-result.rotation, expand=True)
                notes.append("Page remise à l'endroit.")
            words, origin, confidence = result.words, "ocr", result.confidence
    reading = read_page(words or [])
    hard = not blank and (
        words is None
        or len(words) < MIN_WORDS
        or (origin == "ocr" and confidence is not None and confidence < MIN_CONFIDENCE)
    )
    if hard and words is not None:
        notes.append("Texte peu lisible : reprendre la page si elle compte pour le dossier.")
    data = imaging.jpeg_bytes(image)
    stored = get_storage().put(io.BytesIO(data), prefix=str(page.organization_id))
    ScanPage.objects.filter(pk=page.pk).update(
        image_key=stored.key,
        width=image.width,
        height=image.height,
        state=ScanPage.State.READ if words is not None or blank else ScanPage.State.FAILED,
        text_origin=origin,
        text=" ".join(w.text for w in words or [])[:20000],
        title=reading.label[:120],
        title_usage=reading.usage,
        reference=reading.reference[:80],
        page_marker=f"{reading.marker[0]}/{reading.marker[1]}" if reading.marker else "",
        blank=blank,
        hard_to_read=hard,
        notes=notes,
        updated_at=timezone.now(),
    )


def _display_numbers(batch) -> dict:
    pages = batch.pages.exclude(removed=ScanPage.Removal.REPLACED).order_by("position").values_list("id", flat=True)
    return {pk: n for n, pk in enumerate(pages, start=1)}


def _sort_new_pages(batch, actor) -> None:
    """Découpage proposé des pages pas encore triées ; les choix de l'agent ne sont jamais refaits."""
    new = list(batch.pages.filter(sorted=False, removed="", piece__isnull=True).order_by("position"))
    if not new:
        return
    numbers = _display_numbers(batch)
    infos = []
    for page in new:
        marker = tuple(int(n) for n in page.page_marker.split("/")) if page.page_marker else None
        reading = PageReading(page.title_usage, page.title, page.title, page.reference, marker)
        infos.append(PageInfo(page.id, numbers.get(page.id, 0), page.blank, reading))
    proposal = propose(infos)
    by_id = {p.id: p for p in new}
    for proposed in proposal.pieces:
        piece = _new_piece(batch, proposed.usage, proposed.reason)
        ScanPage.objects.filter(pk__in=proposed.page_ids).update(piece=piece)
    ScanPage.objects.filter(pk__in=proposal.blank).update(removed=ScanPage.Removal.BLANK)
    ScanPage.objects.filter(pk__in=list(by_id)).update(sorted=True)
    record_event(
        organization=batch.organization,
        actor=actor,
        event_type="scan.sorting_proposed",
        entity=batch,
        current={
            "pieces": len(proposal.pieces),
            "unclassified": len(proposal.unclassified),
            "blank_removed": len(proposal.blank),
        },
        scope=batch.case.scope,
    )


def process(batch_id, job_id=None) -> None:
    """Idempotent : découpe les fichiers, lit chaque page encore à lire, puis propose les pièces."""
    batch = ScanBatch.objects.select_related("case", "created_by").filter(pk=batch_id).first()
    if batch is None or batch.state in (ScanBatch.State.ATTACHED, ScanBatch.State.CANCELLED):
        return
    now = timezone.now()
    if job_id:
        BackgroundJob.objects.filter(pk=job_id, state=BackgroundJob.State.QUEUED).update(
            state=BackgroundJob.State.RUNNING, started_at=now, attempts=1, phase="découpage"
        )
    _split_sources(batch)
    total = batch.pages.exclude(removed=ScanPage.Removal.REPLACED).count()
    while True:
        with transaction.atomic():
            page = (
                ScanPage.objects.select_for_update(skip_locked=True)
                .select_related("source__document", "batch")
                .filter(batch=batch, state=ScanPage.State.PENDING)
                .order_by("position")
                .first()
            )
            if page is None:
                break
            try:
                _read_one(page)
            except Exception:
                logger.exception("Lot %s : lecture de la page %s impossible", batch.id, page.id)
                ScanPage.objects.filter(pk=page.pk).update(
                    state=ScanPage.State.FAILED, notes=["Erreur inattendue pendant la lecture : reprendre la page."]
                )
        done = batch.pages.exclude(removed=ScanPage.Removal.REPLACED).exclude(state=ScanPage.State.PENDING).count()
        _progress(job_id, "lecture des pages", done, total)
    with transaction.atomic():
        batch = ScanBatch.objects.select_for_update().select_related("case").get(pk=batch.pk)
        if batch.pages.filter(state=ScanPage.State.PENDING).exists():
            return  # un autre traitement lit encore des pages ; il terminera le tri
        _sort_new_pages(batch, batch.created_by)
        if batch.state == ScanBatch.State.PROCESSING:
            batch.state = ScanBatch.State.TO_SORT
            batch.save(update_fields=["state", "updated_at"])
        if job_id:
            BackgroundJob.objects.filter(pk=job_id).update(
                state=BackgroundJob.State.SUCCEEDED, phase="terminé", finished_at=timezone.now()
            )


# --- Tri par l'agent -----------------------------------------------------------------------


def _drop_empty(batch) -> None:
    ScanPiece.objects.filter(batch=batch, case_document__isnull=True, pages__isnull=True).delete()


@transaction.atomic
def update_page(*, org, actor, page_id, data: dict) -> ScanPage:
    """Pivoter, retirer, remettre, ou ranger une page dans une pièce (ou la laisser non classée)."""
    page = page_for(org, page_id, lock=True)
    batch = page.batch
    _require_editable(batch)
    if page.removed == ScanPage.Removal.REPLACED:
        raise ApiError("PAGE_REPLACED", "Page remplacée par une reprise.", 409)
    before = {"rotation": page.rotation, "removed": page.removed, "piece": str(page.piece_id or "")}
    if "rotation" in data:
        if data["rotation"] not in (0, 90, 180, 270):
            raise ApiError("VALIDATION_ERROR", "Rotation possible : 0, 90, 180 ou 270 degrés.", 400)
        page.rotation = data["rotation"]
    if "removed" in data:
        page.removed = ScanPage.Removal.USER if data["removed"] else ScanPage.Removal.NONE
    if "piece_id" in data:
        target = data["piece_id"]
        if target is None:
            page.piece = None
        elif target == "new":
            usage = data.get("usage") if data.get("usage") in CaseDocument.Usage.values else CaseDocument.Usage.OTHER
            page.piece = _new_piece(batch, usage, "pièce formée par l'agent", by_user=True)
        else:
            page.piece = _get(batch.pieces.filter(case_document__isnull=True), target)
    page.save()
    _drop_empty(batch)
    after = {"rotation": page.rotation, "removed": page.removed, "piece": str(page.piece_id or "")}
    _event(org, actor, "scan.page_updated", page, batch, previous=before, current=after)
    return page


@transaction.atomic
def split_at(*, org, actor, page_id) -> ScanPiece:
    """Couper la pièce : cette page et les suivantes de la même pièce forment une nouvelle pièce."""
    page = page_for(org, page_id, lock=True)
    batch = page.batch
    _require_editable(batch)
    if page.piece is None:
        raise ApiError("NOT_IN_PIECE", "Cette page n'appartient à aucune pièce.", 409)
    old = page.piece
    following = old.pages.filter(position__gte=page.position)
    if following.count() == old.pages.count():
        raise ApiError("ALREADY_FIRST", "La pièce commence déjà à cette page.", 409)
    piece = _new_piece(
        batch, old.usage, f"pièce coupée par l'agent à partir d'une page de la pièce {old.ordinal}", by_user=True
    )
    following.update(piece=piece)
    _event(org, actor, "scan.piece_split", piece, batch, current={"from_piece": str(old.id)})
    return piece


@transaction.atomic
def join_previous(*, org, actor, piece_id) -> ScanPiece:
    """Joindre la pièce à celle qui la précède dans le lot."""
    piece = piece_for(org, piece_id)
    batch = piece.batch
    _require_editable(batch)
    if piece.case_document_id:
        raise ApiError("PIECE_ATTACHED", "Pièce déjà rattachée au dossier.", 409)
    first = piece.pages.order_by("position").first()
    previous = (
        batch.pieces.filter(case_document__isnull=True, pages__position__lt=first.position)
        .exclude(pk=piece.pk)
        .order_by("-pages__position")
        .first()
        if first
        else None
    )
    if previous is None:
        raise ApiError("NO_PREVIOUS", "Aucune pièce avant celle-ci.", 409)
    piece.pages.update(piece=previous)
    _event(org, actor, "scan.piece_joined", previous, batch, current={"joined": str(piece.id)})
    _drop_empty(batch)
    return previous


@transaction.atomic
def update_piece(*, org, actor, piece_id, usage: str) -> ScanPiece:
    piece = piece_for(org, piece_id)
    _require_editable(piece.batch)
    if usage not in CaseDocument.Usage.values:
        raise ApiError("VALIDATION_ERROR", "Type de pièce inconnu.", 400)
    before = piece.usage
    piece.usage, piece.usage_by_user, piece.reason = usage, True, "type choisi par l'agent"
    piece.save(update_fields=["usage", "usage_by_user", "reason", "updated_at"])
    _event(org, actor, "scan.piece_type_set", piece, piece.batch, previous={"usage": before}, current={"usage": usage})
    return piece


@transaction.atomic
def replace_page(*, org, actor, page_id, upload) -> ScanPage:
    """Reprise d'une page (scan ou photo) : elle prend la place et la pièce de l'ancienne, qui reste tracée."""
    old = page_for(org, page_id, lock=True)
    batch = batch_for(org, old.batch_id, lock=True)
    _require_editable(batch)
    if old.removed == ScanPage.Removal.REPLACED:
        raise ApiError("PAGE_REPLACED", "Page déjà remplacée.", 409)
    source = _store(org, actor, batch, upload)
    source.page_count, source.split_done = 1, True
    source.save(update_fields=["page_count", "split_done"])
    page = ScanPage.objects.create(
        organization=org,
        batch=batch,
        source=source,
        source_page=1,
        position=old.position,
        piece=old.piece,
        sorted=True,
    )
    old.removed, old.replaced_by = ScanPage.Removal.REPLACED, page
    old.save(update_fields=["removed", "replaced_by", "updated_at"])
    _event(org, actor, "scan.page_replaced", page, batch, current={"replaces": str(old.id)})
    _queue(org, actor, batch)
    return page


@transaction.atomic
def cancel(*, org, actor, batch_id) -> ScanBatch:
    batch = batch_for(org, batch_id, lock=True)
    _require_editable(batch)
    batch.state = ScanBatch.State.CANCELLED
    batch.save(update_fields=["state", "updated_at"])
    _event(org, actor, "scan.batch_cancelled", batch, batch)
    return batch


# --- Rattachement au dossier ---------------------------------------------------------------


def _page_image(page: ScanPage) -> Image.Image:
    with get_storage().open(page.image_key) as fh:
        image = Image.open(fh)
        image.load()
    return image.rotate(-page.rotation, expand=True) if page.rotation else image


def attach(*, org, actor, batch_id) -> ScanBatch:
    """NUM-06 : chaque pièce devient une pièce PDF du dossier ; les factures sont lues ensuite (OCR)."""
    with transaction.atomic():
        batch = batch_for(org, batch_id, lock=True)
        _require_editable(batch)
        if batch.pages.filter(state=ScanPage.State.PENDING).exists():
            raise ApiError("BATCH_PROCESSING", "Des pages sont encore en lecture : patienter avant de rattacher.", 409)
        revision = batch.case.current_revision
        pieces = [p for p in batch.pieces.filter(case_document__isnull=True).order_by("ordinal")]
        kept = {p.id: list(p.pages.filter(removed="").exclude(image_key="").order_by("position")) for p in pieces}
        pieces = [p for p in pieces if kept[p.id]]
        if not pieces:
            raise ApiError(
                "NOTHING_TO_ATTACH", "Aucune pièce à rattacher : ranger au moins une page dans une pièce.", 409
            )
        labels = dict(CaseDocument.Usage.choices)
        totals = Counter(p.usage for p in pieces)
        seen = Counter()
        attached = []
        for piece in pieces:
            seen[piece.usage] += 1
            name = labels[piece.usage]
            if totals[piece.usage] > 1:
                name += f" ({seen[piece.usage]})"
            filename = f"{batch.case.reference} {name}.pdf".replace("/", "-")
            pdf = imaging.pdf_bytes([_page_image(page) for page in kept[piece.id]])
            upload = SimpleUploadedFile(filename, pdf, content_type="application/pdf")
            document = documents.store_upload(organization=org, actor=actor, upload=upload)
            link = cases.reuse_document(
                org=org, actor=actor, revision=revision, document_id=document.id, usage=piece.usage
            )
            piece.case_document = link
            piece.save(update_fields=["case_document", "updated_at"])
            attached.append((piece, link))
        batch.state, batch.attached_by, batch.attached_at = ScanBatch.State.ATTACHED, actor, timezone.now()
        batch.save(update_fields=["state", "attached_by", "attached_at", "updated_at"])
        _event(
            org,
            actor,
            "scan.batch_attached",
            batch,
            batch,
            current={
                "pieces": [
                    {"piece": str(p.id), "case_document": str(link.id), "usage": p.usage, "pages": len(kept[p.id])}
                    for p, link in attached
                ],
                "unclassified": batch.pages.filter(removed="", piece__isnull=True).count(),
            },
        )
        for piece, link in attached:
            if piece.usage == CaseDocument.Usage.INVOICE:
                try:
                    extraction.request_extraction(org=org, actor=actor, link_id=link.id, ocr=True)
                except ApiError as exc:  # OCR absent : la pièce reste rattachée, la saisie manuelle reste possible
                    logger.info("Lecture de la facture %s non lancée : %s", link.id, exc.detail)
    return batch
