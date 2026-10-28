"""Demande, exécution et fusion des extractions ; corrections et divergences (DEV-014 à DEV-018).

Règles de fusion (EXT-01, EXT-07) :
- une valeur saisie ou corrigée par une personne n'est jamais écrasée par une relecture ;
  si la relecture la contredit, une divergence est ouverte et l'utilisateur tranche ;
- une valeur que la relecture ne retrouve pas est conservée (rien n'est effacé) ;
- une ligne que la relecture ne retrouve pas est conservée et signalée ;
- les lignes saisies à la main ne sont jamais touchées.
"""

import hashlib
import json
import logging
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.audit.services import record_event
from apps.cases.models import CaseDocument, CaseRevision, CodeObservation, EntryOrigin, Invoice, InvoiceLine
from apps.core.exceptions import ApiError
from apps.core.models import BackgroundJob
from apps.core.outbox import enqueue
from apps.documents.sniff import JPEG, PNG, READABILITY_LABELS, Readability
from apps.documents.storage import get_storage
from apps.tariffs.codes import normalize_code

from . import adapters, readers
from . import codes as codemod
from .detection import detect_document_type
from .layout import totals_check
from .models import Divergence, ExtractionRun, FieldCorrection, FieldObservation, SourceSpan
from .schema import HEADER_FIELDS, LINE_FIELDS, Origin, ParsedDocument, RowKind, Span, Status, Value, jsonable, plain

logger = logging.getLogger(__name__)

TOPIC = "extraction.run"
NOT_FOUND = ("NOT_FOUND", "Élément introuvable.", 404)
MAX_LENGTH = {
    "supplier_name": 200,
    "buyer_name": 200,
    "invoice_number": 100,
    "currency": 3,
    "incoterm": 20,
    "source_reference": 100,
    "unit": 20,
    "origin_country": 2,
}
STATUS_MESSAGES = {
    Status.MISSING: "Absent du document : à renseigner.",
    Status.AMBIGUOUS: "Lecture ambiguë : à vérifier.",
    Status.UNREADABLE: "Illisible : valeur laissée inconnue.",
    Status.TRUNCATED: "Texte coupé : compléter depuis la pièce.",
    Status.LOW_CONFIDENCE: "Lecture peu sûre : à vérifier.",
}
CODE_FIELD = "code:"


def _event(org, actor, event_type, entity, revision, previous=None, current=None):
    record_event(
        organization=org,
        actor=actor,
        event_type=event_type,
        entity=entity,
        previous=previous,
        current=current,
        scope=revision.case.scope,
    )


def _require_editable(revision: CaseRevision):
    if not revision.is_editable:
        raise ApiError(
            "REVISION_NOT_EDITABLE",
            f"Révision « {revision.get_state_display()} » : modification impossible. Créer une nouvelle révision.",
            409,
        )


# --- Demande -----------------------------------------------------------------------------


def options_hash(document, parser: str, options: dict) -> str:
    """Idempotence : même pièce + même version de lecteur + mêmes options = même travail."""
    payload = json.dumps(
        {"sha256": document.sha256, "parser": parser, "version": adapters.PARSER_VERSION, "options": options},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@transaction.atomic
def request_extraction(*, org, actor, link_id, ocr: bool = False, retry: bool = False) -> tuple[ExtractionRun, bool]:
    """Retourne (exécution, créée). Une demande identique en cours ou déjà faite est réutilisée,
    sauf relance explicite (retry), qui crée une nouvelle tentative comparée à la précédente."""
    link = (
        CaseDocument.objects.for_organization(org)
        .select_for_update(of=("self",))
        .select_related("revision__case", "document")
        .filter(pk=link_id)
        .first()
    )
    if link is None:
        raise ApiError(*NOT_FOUND)
    _require_editable(link.revision)
    if link.replaced_by_id:
        raise ApiError("DOCUMENT_REPLACED", "Pièce remplacée : extraire la nouvelle version.", 409)
    document = link.document
    if document.readability != Readability.OK:
        raise ApiError(
            "DOCUMENT_NOT_READABLE",
            f"{READABILITY_LABELS[document.readability]} Déposer une version lisible ou saisir les lignes.",
            422,
        )
    try:
        parser = adapters.parser_for(document.mime, ocr=ocr)
    except adapters.ExtractionFailure as exc:
        raise ApiError(exc.code, exc.message, 422) from exc
    if not link.detected_type and not link.type_detection:
        # Pièce déposée avant la détection du type : son titre est lu maintenant (LEC-07).
        if detection := detect_document_type(document):
            link.detected_type, link.type_detection = detection["code"], detection
            link.save(update_fields=["detected_type", "type_detection", "updated_at"])
    reader = reader_for(link)
    if reader is None:
        raise ApiError(
            "NO_READER_FOR_TYPE",
            "Pas de lecture automatique pour ce type de pièce : elle est conservée telle quelle.",
            422,
        )
    if document.mime in (PNG, JPEG) and not ocr:
        raise ApiError("OCR_REQUIRED", "Image : la lecture demande l'OCR (ocr=true), ou saisir les lignes.", 422)
    options = {"ocr": bool(ocr), "reader": reader}
    digest = options_hash(document, parser, options)
    runs = ExtractionRun.objects.for_organization(org).filter(case_document=link)
    active = runs.filter(options_hash=digest, status__in=[ExtractionRun.Status.QUEUED, ExtractionRun.Status.RUNNING])
    if active.exists():
        return active.first(), False
    if not retry:
        done = runs.filter(options_hash=digest, status=ExtractionRun.Status.SUCCEEDED).first()
        if done:
            return done, False
    previous = runs.filter(status=ExtractionRun.Status.SUCCEEDED).first()
    job = BackgroundJob.objects.create(
        organization=org,
        kind="extraction",
        input_hash=digest,
        scope=link.revision.case.scope,
        created_by=actor,
        progress={"done": 0, "total": 0},
    )
    run = ExtractionRun.objects.create(
        organization=org,
        case_document=link,
        document=document,
        job=job,
        parser=parser,
        parser_version=adapters.PARSER_VERSION,
        schema_version=adapters.SCHEMA_VERSION,
        options=options,
        options_hash=digest,
        attempt=(runs.aggregate(m=Max("attempt"))["m"] or 0) + 1,
        previous_run=previous,
        created_by=actor,
    )
    job.result_ref = str(run.id)
    job.save(update_fields=["result_ref"])
    enqueue(TOPIC, {"run_id": str(run.id)}, organization=org)
    _event(
        org,
        actor,
        "document.extraction_requested",
        run,
        link.revision,
        current={"parser": parser, "attempt": run.attempt, "ocr": bool(ocr), "document": str(document.id)},
    )
    return run, True


# --- Exécution (worker) -------------------------------------------------------------------


def execute(run_id) -> None:
    """Idempotent : une exécution déjà prise ou terminée n'est pas refaite."""
    with transaction.atomic():
        run = (
            ExtractionRun.objects.select_for_update(of=("self",))
            .select_related("job", "document", "case_document__revision__case")
            .filter(pk=run_id)
            .first()
        )
        if run is None or run.status != ExtractionRun.Status.QUEUED:
            return
        now = timezone.now()
        run.status = ExtractionRun.Status.RUNNING
        run.save(update_fields=["status", "updated_at"])
        job = run.job
        job.state, job.started_at, job.attempts, job.phase = BackgroundJob.State.RUNNING, now, job.attempts + 1, "début"
        job.save(update_fields=["state", "started_at", "attempts", "phase", "updated_at"])

    def progress(phase: str, done: int, total: int) -> None:
        BackgroundJob.objects.filter(pk=run.job_id).update(phase=phase, progress={"done": done, "total": total})

    try:
        path = get_storage().path_for_reading(run.document.object_key)
        parsed = adapters.run(
            run.document.mime,
            path,
            ocr=run.options.get("ocr", False),
            progress=progress,
            reader=run.options.get("reader", readers.INVOICE),
        )
    except adapters.ExtractionFailure as exc:
        _fail(run, exc.code, exc.message, exc.details)
        return
    except Exception:
        logger.exception("Extraction %s : erreur inattendue", run.id)
        _fail(run, "INTERNAL_ERROR", "Erreur inattendue pendant l'extraction : relancer, ou saisir les lignes.")
        return
    try:
        with transaction.atomic():
            if parsed.stats.get("reader", readers.INVOICE) == readers.INVOICE:
                merge(run, parsed)
            else:
                merge_fields(run, parsed)
            detection = parsed.stats.get("language_detection", {})
            if detection:
                # Store hints separately from immutable uploads and original extracted values.
                document = run.document
                document.detected_locale = detection.get("locale", "")
                document.language_detection = detection
                document.save(update_fields=["detected_locale", "language_detection", "updated_at"])
    except ApiError as exc:
        _fail(run, exc.error_code, str(exc.detail))
    except Exception:
        logger.exception("Extraction %s : échec de l'enregistrement", run.id)
        _fail(run, "INTERNAL_ERROR", "Erreur inattendue pendant l'enregistrement : relancer.")


def _fail(run: ExtractionRun, code: str, message: str, details: dict | None = None) -> None:
    with transaction.atomic():
        now = timezone.now()
        ExtractionRun.objects.filter(pk=run.pk).update(
            status=ExtractionRun.Status.FAILED,
            error_code=code,
            error_message=message[:500],
            stats=details or {},
            finished_at=now,
            updated_at=now,
        )
        BackgroundJob.objects.filter(pk=run.job_id).update(
            state=BackgroundJob.State.FAILED,
            error_code=code,
            error_message=message[:500],
            phase="échec",
            finished_at=now,
            updated_at=now,
        )
        revision = run.case_document.revision
        record_event(
            organization=run.organization,
            actor=run.created_by,
            event_type="document.extraction_failed",
            entity=run,
            current={"error_code": code},
            scope=revision.case.scope,
        )


# --- Fusion -------------------------------------------------------------------------------


def _span(run: ExtractionRun, span: Span | None) -> SourceSpan | None:
    if span is None:
        return None
    return SourceSpan.objects.create(
        organization=run.organization,
        document=run.document,
        page_index=span.page,
        bbox=list(span.bbox) if span.bbox else None,
        page_size=list(span.page_size) if span.page_size else None,
        rotation=span.rotation,
        sheet=span.sheet,
        cell_range=span.cell_range,
        excerpt=(span.excerpt or "")[:200],
    )


def _observation(run, entity_key, field_name, value: Value, *, invoice=None, line=None) -> FieldObservation:
    return FieldObservation.objects.create(
        organization=run.organization,
        run=run,
        entity_key=entity_key,
        field_name=field_name,
        label=(value.label or "")[:120],
        raw_value=value.raw,
        parsed_value=jsonable(value.parsed),
        status=value.status,
        origin_type=value.origin,
        confidence=value.confidence,
        notes=value.notes,
        source_span=_span(run, value.span),
        invoice=invoice,
        invoice_line=line,
    )


def _model_value(field: str, parsed):
    if parsed is None:
        return None
    if isinstance(parsed, Decimal | date):
        return parsed
    text = str(parsed).strip()
    if field == "currency":
        text = text.upper()
    if field == "origin_country":
        return text.upper() if len(text) == 2 else None
    limit = MAX_LENGTH.get(field)
    return text[:limit] if limit else text


def _empty(value) -> bool:
    return value is None or value == ""


def _same(a, b) -> bool:
    if isinstance(a, Decimal) and isinstance(b, Decimal):
        return a == b
    return str(a if a is not None else "").strip() == str(b if b is not None else "").strip()


def _origin_label(value: Value) -> str:
    return "inferred" if value.origin == Origin.INFERRED else "extracted"


def _is_human(entity, field: str, created: bool) -> bool:
    origin = entity.field_origins.get(field)
    if origin == "manual":
        return True
    # Valeur présente sans provenance d'extraction : saisie avant la lecture, donc humaine.
    return origin is None and not created and not _empty(getattr(entity, field))


def _open_divergence(run, invoice, line, field, current, extracted, obs, report) -> None:
    existing = Divergence.objects.filter(
        invoice=invoice,
        invoice_line=line,
        field_name=field,
        kind=Divergence.Kind.VALUE,
        state__in=[Divergence.State.OPEN, Divergence.State.KEPT],
        extracted_value=jsonable(extracted),
    )
    if existing.exists():
        return  # déjà présentée (ou déjà tranchée pour cette même valeur)
    Divergence.objects.create(
        organization=run.organization,
        run=run,
        invoice=invoice,
        invoice_line=line,
        field_name=field,
        current_value=plain(current),
        extracted_value=plain(extracted),
        observation=obs,
    )
    report["divergences"] += 1


def _merge_field(run, entity, field, value: Value, obs, report, *, invoice, line, created) -> bool:
    new = _model_value(field, value.parsed)
    current = getattr(entity, field)
    if _is_human(entity, field, created):
        if new is not None and not _same(current, new):
            _open_divergence(run, invoice, line, field, current, new, obs, report)
        else:
            report["corrections_kept"] += 1
        return False
    if new is None:
        if not _empty(current):
            report["values_not_reread"] += 1
        return False
    entity.field_origins[field] = _origin_label(value)
    if _same(current, new):
        return False
    setattr(entity, field, new)
    return True


def _flags(fields: dict[str, Value], entity, extra: list[dict]) -> list[dict]:
    flags = []
    for name, value in fields.items():
        if entity.field_origins.get(name) == "manual":
            continue
        if value.status != Status.OK:
            message = " ".join(value.notes) or STATUS_MESSAGES.get(value.status, "À vérifier.")
            flags.append({"field": name, "code": value.status.upper(), "message": message})
        elif value.origin == Origin.INFERRED:
            flags.append({"field": name, "code": "INFERRED", "message": " ".join(value.notes) or "Valeur déduite."})
    return flags + extra


def _merge_code(run, actor, line, cand, link, page, span, report) -> None:
    from apps.cases import services as cases

    kind = cand.kind
    active = line.code_observations.filter(code_kind=kind, superseded_at__isnull=True).first()
    if active and active.entry_origin == EntryOrigin.MANUAL:
        if (normalize_code(active.raw_code) or active.raw_code) != (normalize_code(cand.raw) or cand.raw):
            _open_divergence(run, line.invoice, line, f"{CODE_FIELD}{kind}", active.raw_code, cand.raw, None, report)
        return
    created = cases._observe(
        run.organization,
        actor,
        line,
        raw_code=cand.raw,
        kind=kind,
        field_label=cand.label[:100],
        claimed_scheme=cand.claimed_scheme,
        evidence=link,
        page=page,
        entry_origin=EntryOrigin.EXTRACTED,
        source_span=span,
        findings=cand.findings,
    )
    if created is not None and created is not active:
        report["codes_observed"] += 1


def reader_for(link: CaseDocument) -> str | None:
    """Lecture d'après le type confirmé, sinon détecté, sinon l'usage choisi au dépôt."""
    from apps.regulations.doc_types import type_of

    found = type_of(link)
    if found and (reader := readers.READER_FOR_TYPE.get(found["code"])):
        return reader
    if found and found["source"] == "confirmed":
        return None  # type confirmé sans lecture (certificat, liste de colisage…) : rien n'est deviné
    return readers.READER_FOR_USAGE.get(link.usage)


def merge_fields(run: ExtractionRun, parsed: ParsedDocument) -> None:
    """Pièce autre qu'une facture commerciale : ses informations sont enregistrées comme observations
    sourcées, sans créer de facture ni de ligne de marchandise (LEC-08, LEC-09)."""
    revision = (
        CaseRevision.objects.select_for_update(of=("self",))
        .select_related("case")
        .get(pk=run.case_document.revision_id)
    )
    _require_editable(revision)
    read = 0
    for name, value in parsed.header.items():
        _observation(run, "document", name, value)
        read += value.status == Status.OK
    now = timezone.now()
    run.stats = parsed.stats
    run.warnings = parsed.warnings
    run.merge_report = {"fields_read": read, "fields_total": len(parsed.header)}
    run.status, run.finished_at = ExtractionRun.Status.SUCCEEDED, now
    run.save()
    BackgroundJob.objects.filter(pk=run.job_id).update(
        state=BackgroundJob.State.SUCCEEDED, phase="terminé", finished_at=now, updated_at=now
    )
    _event(
        run.organization,
        run.created_by,
        "document.read",
        run,
        revision,
        current={"run": str(run.id), "reader": parsed.stats.get("reader"), "fields_read": read},
    )


def merge(run: ExtractionRun, parsed: ParsedDocument) -> None:
    org, actor, link = run.organization, run.created_by, run.case_document
    revision = CaseRevision.objects.select_for_update(of=("self",)).select_related("case").get(pk=link.revision_id)
    _require_editable(revision)
    report = {
        "invoice_created": False,
        "lines_created": 0,
        "lines_updated": 0,
        "lines_not_reread": 0,
        "values_set": 0,
        "values_not_reread": 0,
        "corrections_kept": 0,
        "divergences": 0,
        "codes_observed": 0,
    }
    invoice = (
        Invoice.objects.for_organization(org)
        .select_for_update(of=("self",))
        .filter(revision=revision, document=link)
        .order_by("ordinal")
        .first()
    )
    created = invoice is None
    if created:
        invoice = Invoice.objects.create(
            organization=org,
            revision=revision,
            document=link,
            ordinal=(revision.invoices.aggregate(m=Max("ordinal"))["m"] or 0) + 1,
        )
        report["invoice_created"] = True
    changed = False
    for name in HEADER_FIELDS:
        value = parsed.header[name]
        obs = _observation(run, "invoice", name, value, invoice=invoice)
        if _merge_field(run, invoice, name, value, obs, report, invoice=invoice, line=None, created=created):
            changed = True
            report["values_set"] += 1
    for name, value in parsed.header.items():
        if name not in HEADER_FIELDS:
            # Référence d'une autre pièce (B/L, bon de commande) : observation pour le rapprochement.
            _observation(run, "document", name, value, invoice=invoice)
    invoice.review_flags = _flags({k: v for k, v in parsed.header.items() if k in HEADER_FIELDS}, invoice, [])
    if changed and not created:
        invoice.row_version += 1
    invoice.save()

    existing = {
        ln.extraction_key: ln
        for ln in InvoiceLine.objects.select_for_update(of=("self",))
        .filter(invoice=invoice, organization=org)
        .exclude(extraction_key="")
    }
    next_ordinal = (invoice.lines.aggregate(m=Max("ordinal"))["m"] or 0) + 1
    goods_amounts = []
    for n, parsed_line in enumerate(parsed.lines, start=1):
        key = f"item-{n}"
        line = existing.pop(key, None)
        line_created = line is None
        if line_created:
            line = InvoiceLine.objects.create(
                organization=org,
                invoice=invoice,
                ordinal=next_ordinal,
                entry_origin=EntryOrigin.EXTRACTED,
                extraction_key=key,
                evidence_document=link,
                evidence_page=parsed_line.page,
            )
            next_ordinal += 1
            report["lines_created"] += 1
        line_changed = False
        for name in LINE_FIELDS:
            value = parsed_line.fields[name]
            obs = _observation(run, key, name, value, invoice=invoice, line=line)
            if _merge_field(run, line, name, value, obs, report, invoice=invoice, line=line, created=line_created):
                line_changed = True
                report["values_set"] += 1
        candidates = _resolve_conflicts(parsed_line.codes)
        extra_flags = [{"field": "", **w} for w in parsed_line.warnings]
        for cand in candidates:
            notes = [codemod.FINDING_MESSAGES.get(f, f) for f in cand.findings]
            value = Value(
                raw=cand.raw,
                parsed=normalize_code(cand.raw),
                label=cand.label,
                span=cand.span,
                origin=cand.origin,
                notes=notes,
            )
            obs = _observation(run, key, f"{CODE_FIELD}{cand.kind}", value, invoice=invoice, line=line)
            _merge_code(run, actor, line, cand, link, parsed_line.page, obs.source_span, report)
            extra_flags += [
                {"field": f"{CODE_FIELD}{cand.kind}", "code": f, "message": codemod.FINDING_MESSAGES.get(f, f)}
                for f in cand.findings
            ]
        line.review_flags = _flags(parsed_line.fields, line, extra_flags)
        if line_changed and not line_created:
            line.row_version += 1
            report["lines_updated"] += 1
        line.save()
        goods_amounts.append(line.amount)

    for line in existing.values():
        report["lines_not_reread"] += 1
        if not Divergence.objects.filter(
            invoice_line=line, kind=Divergence.Kind.LINE_NOT_REREAD, state=Divergence.State.OPEN
        ).exists():
            Divergence.objects.create(
                organization=org, run=run, invoice=invoice, invoice_line=line, kind=Divergence.Kind.LINE_NOT_REREAD
            )
            report["divergences"] += 1

    charges = []
    for charge in parsed.charges:
        span = _span(run, charge.span)
        charges.append(
            {
                "kind": charge.kind,
                "label": charge.label,
                "amount": jsonable(charge.amount.parsed),
                "raw": charge.amount.raw,
                "status": charge.amount.status,
                "page": charge.page,
                "span": span.as_dict() if span else None,
            }
        )
    now = timezone.now()
    run.charges = charges
    run.stats = parsed.stats | {"totals": _totals_json(goods_amounts, charges, invoice.declared_total)}
    run.warnings = parsed.warnings
    run.invoice = invoice
    run.merge_report = report
    run.status, run.finished_at = ExtractionRun.Status.SUCCEEDED, now
    run.save()
    BackgroundJob.objects.filter(pk=run.job_id).update(
        state=BackgroundJob.State.SUCCEEDED, phase="terminé", finished_at=now, updated_at=now
    )
    _event(
        org,
        actor,
        "invoice.extracted",
        invoice,
        revision,
        current={"run": str(run.id), "attempt": run.attempt} | {k: v for k, v in report.items() if v},
    )


def _resolve_conflicts(candidates):
    """Deux codes douaniers différents sur une ligne : une seule observation « incertaine »
    qui les cite tous, pour que le contrôle demande à trancher (aucun choix automatique)."""
    customs = [c for c in candidates if c.kind == codemod.CUSTOMS]
    if len({normalize_code(c.raw) or c.raw for c in customs}) <= 1:
        return candidates
    first = customs[0]
    first.kind = codemod.AMBIGUOUS
    first.label = f"Codes contradictoires : {' ; '.join(f'{c.label} {c.raw}' for c in customs)}"[:100]
    if "CODE_CONFLICT" not in first.findings:
        first.findings.append("CODE_CONFLICT")
    return [c for c in candidates if c.kind != codemod.CUSTOMS] + [first]


def _totals_json(goods_amounts, charges, printed) -> dict:
    parsed_charges = [
        {
            "kind": c["kind"],
            "label": c["label"],
            "amount": Decimal(c["amount"]) if c["amount"] is not None else None,
            "page": c.get("page"),
        }
        for c in charges
        if c["kind"] != RowKind.TOTAL
    ]
    result = totals_check(goods_amounts, parsed_charges, printed)
    # Montants sans zéros de remplissage : « 4205 » et non « 4205.00000000 » (précision de stockage).
    return json.loads(
        json.dumps(result, default=lambda v: format(v.normalize(), "f") if isinstance(v, Decimal) else jsonable(v))
    )


def invoice_totals(invoice: Invoice) -> dict:
    """Contrôle EXT-06 sur les valeurs courantes (corrections comprises) et les frais lus."""
    run = latest_run_for_invoice(invoice)
    charges = run.charges if run else []
    return _totals_json([ln.amount for ln in invoice.lines.all()], charges, invoice.declared_total)


def latest_run_for_invoice(invoice: Invoice) -> ExtractionRun | None:
    return (
        ExtractionRun.objects.filter(invoice=invoice, status=ExtractionRun.Status.SUCCEEDED)
        .order_by("-created_at")
        .first()
    )


# --- Corrections et divergences -----------------------------------------------------------


def record_corrections(*, actor, entity, before: dict, after: dict, reason: str = "") -> None:
    """À appeler avant l'enregistrement d'une modification humaine : les valeurs deviennent
    « saisies » (protégées des relectures) et, pour une valeur extraite, la correction est tracée."""
    is_line = isinstance(entity, InvoiceLine)
    extracted = bool(entity.extraction_key) if is_line else ExtractionRun.objects.filter(invoice=entity).exists()
    for field, current in after.items():
        if _same(before.get(field), current):
            continue
        previous_origin = entity.field_origins.get(field)
        entity.field_origins[field] = "manual"
        entity.review_flags = [f for f in entity.review_flags if f.get("field") != field]
        if not extracted:
            continue
        observation = (
            FieldObservation.objects.filter(
                organization=entity.organization,
                field_name=field,
                **({"invoice_line": entity} if is_line else {"invoice": entity, "invoice_line__isnull": True}),
            )
            .order_by("-created_at")
            .first()
        )
        FieldCorrection.objects.create(
            organization=entity.organization,
            invoice=None if is_line else entity,
            invoice_line=entity if is_line else None,
            field_name=field,
            previous={"value": jsonable(before.get(field)), "origin": previous_origin},
            current={"value": jsonable(current)},
            observation=observation,
            reason=(reason or "")[:500],
            actor=actor,
        )


@transaction.atomic
def resolve_divergence(*, org, actor, divergence_id, resolution: str, reason: str = "") -> Divergence:
    from apps.cases import services as cases

    divergence = (
        Divergence.objects.for_organization(org)
        .select_for_update(of=("self",))
        .select_related("invoice__revision__case", "invoice_line", "observation")
        .filter(pk=divergence_id)
        .first()
    )
    if divergence is None:
        raise ApiError(*NOT_FOUND)
    revision = divergence.invoice.revision
    _require_editable(revision)
    if divergence.state != Divergence.State.OPEN:
        raise ApiError("DIVERGENCE_RESOLVED", "Cette divergence a déjà été tranchée.", 409)
    if resolution not in ("keep", "accept"):
        raise ApiError("INVALID_RESOLUTION", "Choisir « keep » (garder) ou « accept » (retenir la relecture).", 400)
    if resolution == "accept":
        if divergence.kind == Divergence.Kind.LINE_NOT_REREAD:
            raise ApiError(
                "NOTHING_TO_ACCEPT", "Ligne absente de la relecture : elle est conservée ; aucune suppression.", 422
            )
        field = divergence.field_name
        line = divergence.invoice_line
        target = (
            InvoiceLine.objects.select_for_update(of=("self",)).get(pk=line.pk)
            if line
            else Invoice.objects.select_for_update(of=("self",)).get(pk=divergence.invoice_id)
        )
        if field.startswith(CODE_FIELD):
            kind = field.removeprefix(CODE_FIELD)
            active = target.code_observations.filter(code_kind=kind, superseded_at__isnull=True).first()
            cases._observe(
                org,
                actor,
                target,
                raw_code=divergence.extracted_value,
                kind=kind,
                field_label="Relecture retenue",
                evidence=target.evidence_document,
                page=target.evidence_page,
                entry_origin=EntryOrigin.EXTRACTED,
            )
            previous = active.raw_code if active else None
        else:
            previous = getattr(target, field)
            parsed = divergence.extracted_value
            model_field = target._meta.get_field(field)
            if model_field.get_internal_type() == "DecimalField" and parsed is not None:
                parsed = Decimal(parsed)
            elif model_field.get_internal_type() == "DateField" and parsed is not None:
                parsed = date.fromisoformat(parsed)
            setattr(target, field, parsed)
            target.field_origins[field] = "extracted"
            target.row_version += 1
            target.save()
        FieldCorrection.objects.create(
            organization=org,
            invoice=None if line else target,
            invoice_line=target if line else None,
            field_name=field,
            previous={"value": jsonable(previous), "origin": "manual"},
            current={"value": divergence.extracted_value, "origin": "extracted"},
            observation=divergence.observation,
            reason=(reason or "Nouvelle lecture retenue après divergence.")[:500],
            actor=actor,
        )
    divergence.state = Divergence.State.ACCEPTED if resolution == "accept" else Divergence.State.KEPT
    divergence.resolved_by, divergence.resolved_at = actor, timezone.now()
    divergence.resolution_reason = (reason or "")[:500]
    divergence.save()
    _event(
        org,
        actor,
        "extraction.divergence_resolved",
        divergence,
        revision,
        current={"resolution": divergence.state, "field": divergence.field_name, "kind": divergence.kind},
    )
    return divergence


# --- Lecture -------------------------------------------------------------------------------


def compare_runs(run: ExtractionRun) -> dict | None:
    """EXT-07 : nouvelle tentative comparée à l'ancienne, champ par champ."""
    previous = run.previous_run
    if previous is None:
        return None

    def index(r):
        return {(o.entity_key, o.field_name): o for o in r.observations.all()}

    before, after = index(previous), index(run)
    rows, counts = [], {"same": 0, "changed": 0, "new": 0, "not_reread": 0}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        old_value = old.parsed_value if old else None
        new_value = new.parsed_value if new else None
        if old_value is None and new_value is None:
            continue
        if old_value == new_value:
            status = "same"
        elif old_value is None:
            status = "new"
        elif new_value is None:
            status = "not_reread"
        else:
            status = "changed"
        counts[status] += 1
        if status != "same":
            rows.append(
                {
                    "entity_key": key[0],
                    "field": key[1],
                    "label": (new or old).label,
                    "previous": old_value,
                    "current": new_value,
                    "status": status,
                }
            )
    return {"previous_run_id": str(previous.id), "previous_attempt": previous.attempt, "counts": counts, "rows": rows}


def field_sources(observations) -> dict:
    """Dernière observation de chaque champ : provenance, statut et localisation."""
    result = {}
    for obs in sorted(observations, key=lambda o: o.created_at):
        result[obs.field_name] = {
            "observation_id": str(obs.id),
            "run_id": str(obs.run_id),
            "label": obs.label,
            "raw": obs.raw_value,
            "status": obs.status,
            "origin": obs.origin_type,
            "confidence": obs.confidence,
            "notes": obs.notes,
            "span": obs.source_span.as_dict() if obs.source_span else None,
        }
    return result


def is_code_field(name: str) -> bool:
    return name.startswith(CODE_FIELD)


def code_kind_label(kind: str) -> str:
    return dict(CodeObservation.Kind.choices).get(kind, kind)
