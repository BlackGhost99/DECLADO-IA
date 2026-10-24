"""Services des dossiers : toute écriture passe ici, bornée à la société et journalisée."""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.audit.services import record_event
from apps.clients.models import Importer
from apps.core.concurrency import bump, check_version
from apps.core.exceptions import ApiError
from apps.documents import services as documents
from apps.documents.models import Document
from apps.extraction import services as extraction
from apps.organizations.models import Membership, Role
from apps.regulations.taxonomy import require_type
from apps.tariffs import services as tariffs
from apps.tariffs.codes import normalize_code
from apps.tariffs.models import PublicationState, TariffNode

from . import codecheck
from .models import (
    CaseDocument,
    CaseRevision,
    CaseSequence,
    ClassificationDecision,
    ClassificationProposal,
    CodeCheck,
    CodeObservation,
    CustomsCase,
    EntryOrigin,
    GoodsLine,
    GoodsLineSource,
    Invoice,
    InvoiceLine,
)

NOT_FOUND = ("NOT_FOUND", "Élément introuvable.", 404)


def _get(qs, pk):
    obj = qs.filter(pk=pk).first() if pk else None
    if obj is None:
        raise ApiError(*NOT_FOUND)
    return obj


def _event(org, actor, event_type, entity, case, previous=None, current=None):
    record_event(
        organization=org,
        actor=actor,
        event_type=event_type,
        entity=entity,
        previous=previous,
        current=current,
        scope=case.scope,
    )


def _diff(before: dict, after: dict) -> tuple[dict, dict]:
    changed = [k for k in after if before.get(k) != after[k]]
    return {k: before.get(k) for k in changed}, {k: after[k] for k in changed}


def _jsonable(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "pk"):
        return str(value.pk)
    return value


def _require_editable(revision: CaseRevision):
    if not revision.is_editable:
        raise ApiError(
            "REVISION_NOT_EDITABLE",
            f"Révision « {revision.get_state_display()} » : modification impossible. Créer une nouvelle révision.",
            409,
        )


# --- Résolutions bornées à la société -------------------------------------------------


def importer_for(org, importer_id):
    return _get(Importer.objects.for_organization(org), importer_id)


def assignee_for(org, user_id):
    membership = (
        Membership.objects.select_related("user")
        .filter(organization=org, user_id=user_id, active=True, user__is_active=True)
        .first()
    )
    if membership is None or not membership.has_role(Role.DECLARANT, Role.VALIDATOR):
        raise ApiError(
            "INVALID_ASSIGNEE", "La personne doit être membre actif de la société, déclarant ou validateur.", 422
        )
    return membership.user


def edition_for(actor, edition_id):
    edition = (
        tariffs.visible_editions(actor)
        .exclude(publication_state=PublicationState.WITHDRAWN)
        .filter(pk=edition_id)
        .first()
    )
    if edition is None:
        raise ApiError("INVALID_EDITION", "Édition inconnue, non publiée ou retirée.", 422)
    return edition


def case_document_for(revision, case_document_id):
    if not case_document_id:
        return None
    link = (
        CaseDocument.objects.for_organization(revision.organization)
        .filter(pk=case_document_id, revision=revision)
        .first()
    )
    if link is None:
        raise ApiError("INVALID_DOCUMENT", "La pièce doit appartenir à ce dossier.", 422)
    return link


# --- Dossiers et révisions -----------------------------------------------------------


def next_reference(org) -> str:
    """DOS-01 : référence unique par société, verrouillée par compteur annuel."""
    from zoneinfo import ZoneInfo

    year = timezone.now().astimezone(ZoneInfo(org.timezone)).year
    CaseSequence.objects.get_or_create(organization=org, year=year)
    seq = CaseSequence.objects.select_for_update().get(organization=org, year=year)
    seq.last_value += 1
    seq.save(update_fields=["last_value"])
    return f"DOS-{year}-{seq.last_value:04d}"


@transaction.atomic
def create_case(*, org, actor, data: dict) -> CustomsCase:
    importer = importer_for(org, data["importer_id"]) if data.get("importer_id") else None
    assignee = assignee_for(org, data["assigned_to_id"]) if data.get("assigned_to_id") else None
    edition = edition_for(actor, data["target_edition_id"]) if data.get("target_edition_id") else None
    case = CustomsCase.objects.create(
        organization=org,
        reference=next_reference(org),
        title=data.get("title", ""),
        importer=importer,
        assigned_to=assignee,
        created_by=actor,
    )
    revision = CaseRevision.objects.create(
        organization=org,
        case=case,
        revision_no=1,
        mode=CaseRevision.Mode.DEMO if org.is_demo else CaseRevision.Mode.HISTORICAL,
        territory=data.get("territory") or "GA",
        planned_declaration_date=data.get("planned_declaration_date"),
        regime=data.get("regime", ""),
        target_edition=edition,
        created_by=actor,
    )
    case.current_revision = revision
    case.save(update_fields=["current_revision"])
    _event(
        org,
        actor,
        "case.created",
        case,
        case,
        current={
            "reference": case.reference,
            "importer": str(importer.id) if importer else None,
            "mode": revision.mode,
        },
    )
    return case


def lock_case(org, case_id) -> CustomsCase:
    return _get(CustomsCase.objects.for_organization(org).select_for_update(of=("self",)), case_id)


@transaction.atomic
def update_case(*, org, actor, case_id, expected: int | None, data: dict) -> CustomsCase:
    case = lock_case(org, case_id)
    check_version(case, expected)
    _require_editable(case.current_revision)
    before = {"title": case.title, "importer": str(case.importer_id) if case.importer_id else None}
    if "title" in data:
        case.title = data["title"]
    if "importer_id" in data:
        case.importer = importer_for(org, data["importer_id"]) if data["importer_id"] else None
    after = {"title": case.title, "importer": str(case.importer_id) if case.importer_id else None}
    bump(case)
    case.save()
    previous, current = _diff(before, after)
    _event(org, actor, "case.updated", case, case, previous, current)
    return case


@transaction.atomic
def assign_case(*, org, actor, membership, case_id, expected: int | None, assignee_id) -> CustomsCase:
    """Validateur/administrateur : affecte à quiconque. Déclarant : prend un dossier libre pour lui-même."""
    case = lock_case(org, case_id)
    check_version(case, expected)
    supervisor = membership.has_role(Role.VALIDATOR, Role.ORG_ADMIN)
    self_take = str(assignee_id) == str(actor.id) and case.assigned_to_id is None
    if not supervisor and not self_take:
        raise ApiError("FORBIDDEN", "Seul un validateur ou un administrateur peut réaffecter ce dossier.", 403)
    previous = str(case.assigned_to_id) if case.assigned_to_id else None
    case.assigned_to = assignee_for(org, assignee_id) if assignee_id else None
    bump(case)
    case.save()
    _event(
        org,
        actor,
        "case.assigned",
        case,
        case,
        {"assigned_to": previous},
        {"assigned_to": str(case.assigned_to_id) if case.assigned_to_id else None},
    )
    return case


REVISION_FIELDS = ("planned_declaration_date", "regime", "territory", "target_edition")


@transaction.atomic
def update_revision(*, org, actor, revision_id, expected: int | None, data: dict) -> CaseRevision:
    revision = _get(CaseRevision.objects.for_organization(org).select_for_update(of=("self",)), revision_id)
    check_version(revision, expected)
    _require_editable(revision)
    before = {f: _jsonable(getattr(revision, f)) for f in REVISION_FIELDS}
    for field in ("planned_declaration_date", "regime", "territory"):
        if field in data:
            setattr(
                revision,
                field,
                data[field] if data[field] is not None else ("" if field != "planned_declaration_date" else None),
            )
    if "target_edition_id" in data:
        revision.target_edition = edition_for(actor, data["target_edition_id"]) if data["target_edition_id"] else None
    after = {f: _jsonable(getattr(revision, f)) for f in REVISION_FIELDS}
    bump(revision)
    revision.save()
    previous, current = _diff(before, after)
    _event(org, actor, "revision.updated", revision, revision.case, previous, current)
    return revision


def create_revision(*, org, actor, case_id, reason: str):
    """WF-04 : une nouvelle révision part d'une révision validée. La validation arrive au lot 5."""
    case = lock_case(org, case_id)
    if case.current_revision.state != CaseRevision.State.VALIDATED:
        raise ApiError(
            "REVISION_NOT_VALIDATED",
            "Une nouvelle révision se crée après validation interne ; la révision courante reste modifiable.",
            409,
            {"current_state": case.current_revision.state},
        )
    raise ApiError("NOT_IMPLEMENTED", "Création de révision après validation : prévue au lot 5.", 501)


# --- Pièces ----------------------------------------------------------------------------


def _link_document(org, actor, revision, document, usage, idempotency_key="", document_type_code="") -> CaseDocument:
    link = CaseDocument.objects.create(
        organization=org,
        revision=revision,
        document=document,
        usage=usage,
        document_type_code=document_type_code,
        added_by=actor,
        idempotency_key=idempotency_key,
    )
    _event(
        org,
        actor,
        "case.document_attached",
        link,
        revision.case,
        current={
            "document": str(document.id),
            "sha256": document.sha256,
            "usage": usage,
            "document_type_code": document_type_code,
            "name": document.original_name,
        },
    )
    return link


def attach_upload(
    *,
    org,
    actor,
    revision,
    upload,
    usage,
    declared_mime="",
    duplicate_action="",
    idempotency_key="",
    document_type_code="",
):
    """DOC-01/02/03 : dépôt contrôlé. Un fichier identique déjà présent est signalé ; l'utilisateur décide."""
    if idempotency_key:
        existing = CaseDocument.objects.for_organization(org).filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            if existing.revision_id != revision.id:
                raise ApiError("IDEMPOTENCY_KEY_REUSED", "Clé d'idempotence déjà utilisée pour un autre dossier.", 409)
            return existing, False
    _require_editable(revision)
    with transaction.atomic():
        document = documents.store_upload(organization=org, actor=actor, upload=upload, declared_mime=declared_mime)
        duplicates = documents.find_duplicates(org, document.sha256, exclude_id=document.id)
        if duplicates and duplicate_action != "keep_both":
            # Rien n'est enregistré : l'exception annule le Document, le fichier est retiré.
            documents.get_storage().discard(document.object_key)
            raise ApiError(
                "DUPLICATE_DOCUMENT",
                "Un fichier identique existe déjà dans la société : réutiliser la pièce ou conserver les deux.",
                409,
                {
                    "sha256": document.sha256,
                    "existing": [
                        {
                            "id": str(d.id),
                            "original_name": d.original_name,
                            "created_at": d.created_at.isoformat(),
                            "cases": sorted(
                                {link.revision.case.reference for link in d.case_links.select_related("revision__case")}
                            ),
                        }
                        for d in duplicates
                    ],
                },
            )
        try:
            with transaction.atomic():
                link = _link_document(org, actor, revision, document, usage, idempotency_key, document_type_code)
        except IntegrityError:
            raise ApiError("IDEMPOTENCY_KEY_REUSED", "Requête déjà en cours de traitement.", 409) from None
    return link, True


@transaction.atomic
def reuse_document(*, org, actor, revision, document_id, usage, document_type_code="") -> CaseDocument:
    _require_editable(revision)
    document = _get(Document.objects.for_organization(org), document_id)
    return _link_document(org, actor, revision, document, usage, document_type_code=document_type_code)


@transaction.atomic
def replace_document(*, org, actor, link_id, upload, declared_mime="") -> CaseDocument:
    """DOC-02 : nouvelle version ; l'original et son rattachement restent consultables."""
    old = _get(
        CaseDocument.objects.for_organization(org)
        .select_for_update(of=("self",))
        .select_related("revision__case", "document"),
        link_id,
    )
    _require_editable(old.revision)
    if old.replaced_by_id:
        raise ApiError("ALREADY_REPLACED", "Cette pièce a déjà été remplacée : remplacer la dernière version.", 409)
    head = old.document
    if hasattr(head, "superseded_by"):
        raise ApiError("ALREADY_REPLACED", "Ce fichier a déjà une version plus récente.", 409)
    document = documents.store_upload(
        organization=org, actor=actor, upload=upload, declared_mime=declared_mime, supersedes=head
    )
    new = CaseDocument.objects.create(
        organization=org, revision=old.revision, document=document, usage=old.usage,
        document_type_code=old.document_type_code, added_by=actor
    )
    old.replaced_by = new
    bump(old)
    old.save()
    _event(
        org,
        actor,
        "case.document_replaced",
        new,
        old.revision.case,
        {"document": str(head.id), "sha256": head.sha256},
        {"document": str(document.id), "sha256": document.sha256, "version": document.version},
    )
    return new


@transaction.atomic
def classify_case_document(*, org, actor, link_id, document_type_code: str) -> CaseDocument:
    """Human classification of an attached scan or legacy document; always audited."""
    spec = require_type(document_type_code)
    link = _get(
        CaseDocument.objects.for_organization(org)
        .select_for_update(of=("self",))
        .select_related("revision__case"),
        link_id,
    )
    _require_editable(link.revision)
    if link.replaced_by_id:
        raise ApiError("ALREADY_REPLACED", "Classer la dernière version de la pièce.", 409)
    previous = {"document_type_code": link.document_type_code, "usage": link.usage}
    link.document_type_code = document_type_code
    link.usage = spec.usage
    bump(link)
    link.save(update_fields=["document_type_code", "usage", "row_version", "updated_at"])
    _event(
        org, actor, "case.document_classified", link, link.revision.case,
        previous, {"document_type_code": link.document_type_code, "usage": link.usage},
    )
    return link


# --- Factures et lignes --------------------------------------------------------------

INVOICE_FIELDS = ("supplier_name", "invoice_number", "invoice_date", "currency", "incoterm", "declared_total")
EXTRACTED_LINE_FIELDS = (
    "source_reference",
    "description_raw",
    "quantity",
    "unit",
    "unit_price",
    "amount",
    "origin_country",
)
LINE_FIELDS = (
    "source_reference",
    "description_raw",
    "quantity",
    "unit",
    "unit_price",
    "amount",
    "origin_country",
    "evidence_page",
    "evidence_note",
)


def _values(obj, fields):
    return {f: getattr(obj, f) for f in fields}


def _snapshot(obj, fields):
    return {f: _jsonable(getattr(obj, f)) for f in fields}


def _apply(obj, data, fields):
    for f in fields:
        if f in data:
            value = data[f]
            field = obj._meta.get_field(f)
            if value is None and not field.null:
                value = ""
            setattr(obj, f, value)


def _next_ordinal(qs) -> int:
    return (qs.aggregate(m=Max("ordinal"))["m"] or 0) + 1


@transaction.atomic
def add_invoice(*, org, actor, revision_id, data) -> Invoice:
    revision = _get(CaseRevision.objects.for_organization(org).select_for_update(of=("self",)), revision_id)
    _require_editable(revision)
    invoice = Invoice(organization=org, revision=revision, ordinal=_next_ordinal(revision.invoices.all()))
    _apply(invoice, data, INVOICE_FIELDS)
    invoice.currency = (invoice.currency or "").upper()
    invoice.document = case_document_for(revision, data.get("document_id"))
    invoice.save()
    _event(org, actor, "invoice.created", invoice, revision.case, current=_snapshot(invoice, INVOICE_FIELDS))
    return invoice


@transaction.atomic
def update_invoice(*, org, actor, invoice_id, expected, data) -> Invoice:
    invoice = _get(
        Invoice.objects.for_organization(org).select_for_update(of=("self",)).select_related("revision__case"),
        invoice_id,
    )
    check_version(invoice, expected)
    _require_editable(invoice.revision)
    raw_before = _values(invoice, INVOICE_FIELDS)
    before = _snapshot(invoice, INVOICE_FIELDS) | {
        "document": str(invoice.document_id) if invoice.document_id else None
    }
    _apply(invoice, data, INVOICE_FIELDS)
    invoice.currency = (invoice.currency or "").upper()
    if "document_id" in data:
        invoice.document = case_document_for(invoice.revision, data["document_id"])
    extraction.record_corrections(
        actor=actor,
        entity=invoice,
        before=raw_before,
        after=_values(invoice, INVOICE_FIELDS),
        reason=data.get("correction_reason", ""),
    )
    bump(invoice)
    invoice.save()
    after = _snapshot(invoice, INVOICE_FIELDS) | {"document": str(invoice.document_id) if invoice.document_id else None}
    _event(org, actor, "invoice.updated", invoice, invoice.revision.case, *_diff(before, after))
    return invoice


def _observe(
    org,
    actor,
    line,
    *,
    raw_code,
    kind,
    field_label,
    claimed_scheme="",
    evidence=None,
    page=None,
    entry_origin=EntryOrigin.MANUAL,
    source_span=None,
    findings=None,
):
    """COD-01 : l'observation précédente du même type est remplacée, jamais modifiée."""
    raw_code = (raw_code or "").strip()
    previous = line.code_observations.filter(code_kind=kind, superseded_at__isnull=True).first()
    if (
        previous
        and previous.raw_code == raw_code
        and previous.field_label == field_label
        and previous.entry_origin == entry_origin
    ):
        return previous
    new = None
    if raw_code:
        new = CodeObservation.objects.create(
            organization=org,
            invoice_line=line,
            field_label=field_label,
            raw_code=raw_code,
            normalized_code=normalize_code(raw_code),
            code_kind=kind,
            claimed_scheme=claimed_scheme,
            entry_origin=entry_origin,
            evidence_document=evidence,
            evidence_page=page,
            source_span=source_span,
            findings=findings or [],
            created_by=actor,
        )
    if previous:
        previous.superseded_at = timezone.now()
        previous.superseded_by = new
        previous.save(update_fields=["superseded_at", "superseded_by", "updated_at"])
    _event(
        org,
        actor,
        "invoice_line.code_observed",
        line,
        line.invoice.revision.case,
        {"raw_code": previous.raw_code, "kind": kind} if previous else None,
        {
            "raw_code": raw_code,
            "normalized": new.normalized_code if new else None,
            "kind": kind,
            "field_label": field_label,
            "origin": entry_origin,
        },
    )
    return new


def _observe_from(org, actor, line, data):
    evidence, page = line.evidence_document, line.evidence_page
    if "customs_code" in data:
        _observe(
            org,
            actor,
            line,
            raw_code=data["customs_code"],
            kind=CodeObservation.Kind.CUSTOMS,
            field_label=(data.get("customs_code_label") or "Code douanier (saisi)").strip(),
            claimed_scheme=data.get("claimed_scheme", ""),
            evidence=evidence,
            page=page,
        )
    if "uncertain_code" in data:
        _observe(
            org,
            actor,
            line,
            raw_code=data["uncertain_code"],
            kind=CodeObservation.Kind.AMBIGUOUS,
            field_label=(data.get("uncertain_code_label") or "Code de nature incertaine").strip(),
            evidence=evidence,
            page=page,
        )


@transaction.atomic
def add_invoice_line(*, org, actor, invoice_id, data) -> InvoiceLine:
    invoice = _get(
        Invoice.objects.for_organization(org).select_for_update(of=("self",)).select_related("revision__case"),
        invoice_id,
    )
    _require_editable(invoice.revision)
    line = InvoiceLine(organization=org, invoice=invoice, ordinal=_next_ordinal(invoice.lines.all()))
    _apply(line, data, LINE_FIELDS)
    line.origin_country = (line.origin_country or "").upper()
    line.evidence_document = case_document_for(invoice.revision, data.get("evidence_document_id"))
    line.save()
    _event(
        org,
        actor,
        "invoice_line.created",
        line,
        invoice.revision.case,
        current={"ordinal": line.ordinal, "invoice": str(invoice.id)},
    )
    _observe_from(org, actor, line, data)
    return line


@transaction.atomic
def update_invoice_line(*, org, actor, line_id, expected, data) -> InvoiceLine:
    line = _get(
        InvoiceLine.objects.for_organization(org)
        .select_for_update(of=("self",))
        .select_related("invoice__revision__case"),
        line_id,
    )
    check_version(line, expected)
    _require_editable(line.invoice.revision)
    before = _snapshot(line, LINE_FIELDS)
    raw_before = _values(line, LINE_FIELDS)
    _apply(line, data, LINE_FIELDS)
    line.origin_country = (line.origin_country or "").upper()
    if "evidence_document_id" in data:
        line.evidence_document = case_document_for(line.invoice.revision, data["evidence_document_id"])
    extraction.record_corrections(
        actor=actor,
        entity=line,
        before={f: raw_before[f] for f in EXTRACTED_LINE_FIELDS},
        after={f: getattr(line, f) for f in EXTRACTED_LINE_FIELDS},
        reason=data.get("correction_reason", ""),
    )
    customs_before = _active_code(line, CodeObservation.Kind.CUSTOMS)
    bump(line)
    line.save()
    previous, current = _diff(before, _snapshot(line, LINE_FIELDS))
    if current:
        # Les textes de facture ne sont pas recopiés dans le journal : seuls les noms de champs le sont.
        _event(org, actor, "invoice_line.updated", line, line.invoice.revision.case, None, {"fields": sorted(current)})
    _observe_from(org, actor, line, data)
    customs_after = _active_code(line, CodeObservation.Kind.CUSTOMS)
    if line.extraction_key and customs_before != customs_after:
        extraction.record_corrections(
            actor=actor,
            entity=line,
            before={"code:customs": customs_before},
            after={"code:customs": customs_after},
            reason=data.get("correction_reason", ""),
        )
        line.save(update_fields=["field_origins", "review_flags", "updated_at"])
    return line


def _active_code(line, kind):
    obs = line.code_observations.filter(code_kind=kind, superseded_at__isnull=True).first()
    return obs.raw_code if obs else None


# --- Marchandises ---------------------------------------------------------------------

GOODS_FIELDS = ("description", "attributes", "origin_country", "regime")


@transaction.atomic
def create_goods_line(*, org, actor, revision_id, data) -> GoodsLine:
    """Une marchandise issue d'une ou plusieurs lignes facturées, liens et quantités conservés."""
    revision = _get(CaseRevision.objects.for_organization(org).select_for_update(of=("self",)), revision_id)
    _require_editable(revision)
    lines = list(
        InvoiceLine.objects.for_organization(org)
        .filter(pk__in=data.get("invoice_line_ids") or [], invoice__revision=revision)
        .order_by("invoice__ordinal", "ordinal")
    )
    if not lines or len(lines) != len(set(data.get("invoice_line_ids") or [])):
        raise ApiError("INVALID_INVOICE_LINES", "Choisir une ou plusieurs lignes facturées de ce dossier.", 422)
    already = GoodsLineSource.objects.filter(invoice_line__in=lines).select_related("goods_line").first()
    if already:
        raise ApiError(
            "INVOICE_LINE_ALREADY_USED",
            f"La ligne facturée est déjà rattachée à la marchandise n° {already.goods_line.ordinal}.",
            409,
        )
    first = lines[0]
    goods = GoodsLine(
        organization=org,
        revision=revision,
        ordinal=_next_ordinal(revision.goods_lines.all()),
        description=data.get("description") or first.description_raw,
        attributes=data.get("attributes") or {},
        origin_country=(
            data.get("origin_country")
            or (first.origin_country if len({ln.origin_country for ln in lines}) == 1 else "")
        ).upper(),
        regime=data.get("regime", ""),
    )
    goods.save()
    for line in lines:
        GoodsLineSource.objects.create(
            organization=org,
            goods_line=goods,
            invoice_line=line,
            assigned_quantity=line.quantity,
            assigned_value=line.amount,
        )
    _event(
        org,
        actor,
        "goods_line.created",
        goods,
        revision.case,
        current={"ordinal": goods.ordinal, "invoice_lines": [str(ln.id) for ln in lines]},
    )
    return goods


@transaction.atomic
def goods_lines_from_invoice(*, org, actor, invoice_id) -> list[GoodsLine]:
    """Chemin court : une marchandise par ligne facturée encore libre, liens et quantités conservés."""
    invoice = _get(Invoice.objects.for_organization(org).select_related("revision"), invoice_id)
    free = invoice.lines.filter(goods_sources__isnull=True).order_by("ordinal")
    return [
        create_goods_line(org=org, actor=actor, revision_id=invoice.revision_id, data={"invoice_line_ids": [line.id]})
        for line in free
    ]


@transaction.atomic
def update_goods_line(*, org, actor, goods_id, expected, data) -> GoodsLine:
    goods = _get(
        GoodsLine.objects.for_organization(org).select_for_update(of=("self",)).select_related("revision__case"),
        goods_id,
    )
    check_version(goods, expected)
    _require_editable(goods.revision)
    before = _snapshot(goods, GOODS_FIELDS)
    _apply(goods, data, GOODS_FIELDS)
    goods.origin_country = (goods.origin_country or "").upper()
    bump(goods)
    goods.save()
    _previous, current = _diff(before, _snapshot(goods, GOODS_FIELDS))
    if current:
        _event(org, actor, "goods_line.updated", goods, goods.revision.case, None, {"fields": sorted(current)})
    return goods


# --- Contrôle et décision de code ----------------------------------------------------


def check_payload(check: CodeCheck, goods: GoodsLine, revision) -> dict:
    current_hash = codecheck.code_inputs_hash(goods, check.target_edition_id)
    decision = current_decision(goods)
    _applicable, applicability_findings = codecheck.applicability(check.target_edition, revision)
    obs = check.observation
    return {
        "id": str(check.id),
        "goods_line_id": str(goods.id),
        "observed_code": obs.raw_code if obs else None,
        "observed_field": obs.field_label if obs else None,
        "normalized_code": obs.normalized_code if obs else None,
        "target_edition_id": str(check.target_edition_id),
        "target_edition_label": check.target_edition.label,
        "recognition_status": check.state,
        "recognition_label": check.get_state_display(),
        "node": None
        if check.node is None
        else {
            "id": str(check.node.id),
            "code": check.node.code,
            "code_display": check.node.code_display,
            "label": check.node.label_clean,
            "full_path": check.node.full_path_label,
            "declarable": check.node.declarable,
        },
        "is_current": check.checked_input_hash == current_hash,
        "human_confirmation": "stale"
        if check.checked_input_hash != current_hash
        else ("confirmed" if decision and decision.code_check_id == check.id else "pending"),
        "operational_applicability": "unverified" if applicability_findings else "verified",
        "findings": check.findings,
        "source_refs": [{"case_document_id": str(obs.evidence_document_id), "page": obs.evidence_page}]
        if obs and obs.evidence_document_id
        else [],
        "checked_at": check.created_at,
        "checked_by": check.created_by.email,
    }


@transaction.atomic
def run_code_check(*, org, actor, goods_id, edition_id=None) -> CodeCheck:
    goods = _get(
        GoodsLine.objects.for_organization(org).select_related("revision__case", "revision__target_edition"), goods_id
    )
    revision = goods.revision
    edition_id = edition_id or revision.target_edition_id
    if not edition_id:
        raise ApiError("EDITION_REQUIRED", "Choisir l'édition du référentiel contre laquelle contrôler le code.", 422)
    edition = edition_for(actor, edition_id)
    visible = tariffs.visible_editions(actor).exclude(publication_state=PublicationState.WITHDRAWN)
    result = codecheck.evaluate(goods, edition, visible)
    _applicable, applicability_findings = codecheck.applicability(edition, revision)
    check = CodeCheck.objects.create(
        organization=org,
        goods_line=goods,
        observation=result["observation"],
        target_edition=edition,
        node=result["node"],
        state=result["state"],
        findings=applicability_findings + result["findings"],
        checked_input_hash=codecheck.code_inputs_hash(goods, edition.id),
        created_by=actor,
    )
    _event(
        org,
        actor,
        "goods_line.code_checked",
        check,
        revision.case,
        current={
            "state": check.state,
            "edition": str(edition.id),
            "node": str(check.node_id) if check.node_id else None,
        },
    )
    return check


def latest_check(goods: GoodsLine) -> CodeCheck | None:
    return goods.code_checks.select_related("target_edition", "node", "observation", "created_by").first()


def current_decision(goods: GoodsLine) -> ClassificationDecision | None:
    return goods.decisions.select_related("selected_node", "edition", "actor").first()


def decision_is_current(decision: ClassificationDecision, goods: GoodsLine) -> bool:
    return decision.input_hash == codecheck.code_inputs_hash(goods, decision.edition_id)


@transaction.atomic
def record_decision(*, org, actor, goods_id, data) -> ClassificationDecision:
    """COD-03/COD-07 : confirmation (ou complément/remplacement) attribuée, motivée et liée au contrôle courant."""
    goods = _get(
        GoodsLine.objects.for_organization(org).select_for_update(of=("self",)).select_related("revision__case"),
        goods_id,
    )
    check_version(goods, data.get("goods_line_version"))
    _require_editable(goods.revision)
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise ApiError("REASON_REQUIRED", "Une justification est obligatoire.", 400)
    check = latest_check(goods)
    if check is None or str(check.id) != str(data.get("code_check_id")):
        raise ApiError("CODE_CHECK_STALE", "Un contrôle plus récent existe : relire le résultat avant de décider.", 409)
    if check.checked_input_hash != codecheck.code_inputs_hash(goods, check.target_edition_id):
        raise ApiError("CODE_CHECK_STALE", "Les données ont changé depuis le contrôle : relancer le contrôle.", 409)
    action = data.get("action")
    evidence = [e for e in (data.get("evidence_refs") or []) if isinstance(e, (str, dict))]
    obs = check.observation
    proposal = None
    if data.get("proposal_id"):
        proposal = (
            ClassificationProposal.objects.for_organization(org)
            .filter(pk=data["proposal_id"], proposal_set__goods_line=goods, proposal_set__edition=check.target_edition)
            .first()
        )
        if proposal is None or str(proposal.node_id) != str(data.get("node_id")):
            raise ApiError(
                "INVALID_PROPOSAL", "La proposition ne correspond pas à cette marchandise et à ce code.", 422
            )
        evidence.append({"proposal_id": str(proposal.id), "producer": proposal.proposal_set.producer})
    if action == ClassificationDecision.Action.CONFIRM:
        if check.state != CodeCheck.State.RECOGNIZED:
            raise ApiError(
                "CANNOT_CONFIRM",
                f"Contrôle « {check.get_state_display()} » : seul un code retrouvé et déclarable se confirme.",
                422,
            )
        node = check.node
    elif action == ClassificationDecision.Action.CLASSIFY:
        if check.state not in (CodeCheck.State.MISSING, CodeCheck.State.AMBIGUOUS):
            raise ApiError(
                "CANNOT_CLASSIFY",
                "Un code douanier est présent : le confirmer, le compléter ou le remplacer avec une source.",
                422,
            )
        node = TariffNode.objects.filter(pk=data.get("node_id"), edition=check.target_edition).first()
        if node is None or not node.declarable:
            raise ApiError("INVALID_NODE", "Choisir une ligne déclarable existante de l'édition contrôlée.", 422)
    elif action in (ClassificationDecision.Action.COMPLETE, ClassificationDecision.Action.REPLACE):
        node = TariffNode.objects.filter(pk=data.get("node_id"), edition=check.target_edition).first()
        if node is None or not node.declarable:
            raise ApiError("INVALID_NODE", "Choisir une ligne déclarable existante de l'édition contrôlée.", 422)
        if action == ClassificationDecision.Action.COMPLETE:
            if check.state != CodeCheck.State.INCOMPLETE or not (
                obs and obs.normalized_code and node.code.startswith(obs.normalized_code)
            ):
                raise ApiError("INVALID_COMPLETION", "Le complément doit être une subdivision du code observé.", 422)
        elif obs is None:
            raise ApiError(
                "NOTHING_TO_REPLACE",
                "Aucun code présent à remplacer : classer la marchandise depuis la recherche ou les propositions.",
                422,
            )
        elif not evidence:
            raise ApiError("EVIDENCE_REQUIRED", "Un remplacement exige une source (pièce, note, avis).", 400)
    else:
        raise ApiError("INVALID_ACTION", "Action inconnue.", 400)
    goods.row_version += 1
    goods.save(update_fields=["row_version", "updated_at"])
    decision = ClassificationDecision.objects.create(
        organization=org,
        goods_line=goods,
        original_observation=obs,
        code_check=check,
        selected_node=node,
        selected_code=node.code,
        proposal=proposal,
        edition=check.target_edition,
        action=action,
        reason=reason,
        evidence_refs=evidence,
        actor=actor,
        goods_line_version=goods.row_version,
        input_hash=check.checked_input_hash,
    )
    _event(
        org,
        actor,
        "goods_line.code_decided",
        decision,
        goods.revision.case,
        {"observed": obs.raw_code if obs else None},
        {"action": action, "code": node.code, "edition": str(check.target_edition_id)},
    )
    return decision
