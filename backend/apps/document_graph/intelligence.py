"""Conservative documentary intelligence. No AI provider and no tax computation.

Only exact references from successful extraction observations create *proposed*
associations. All cross-document decisions remain attributed to human reviewers.
"""

import re
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_event
from apps.cases.models import CaseDocument, Invoice
from apps.core.exceptions import ApiError
from apps.extraction.models import ExtractionRun, FieldObservation

from .matcher import references
from .models import DocumentConflict, DocumentInvoiceLink, Shipment, ShipmentDocument, ShipmentInvoice
from .services import _document, _revision

ENGINE_VERSION = "document-graph-exact-v1"
REF_CHARS = re.compile(r"^[A-Z0-9][A-Z0-9/-]{2,99}$")
NOT_FOUND = ("NOT_FOUND", "Élément introuvable.", 404)


def _normalize(value):
    result = str(value or "").upper().strip().strip("/-")
    return result if REF_CHARS.fullmatch(result) and any(char.isdigit() for char in result) else ""


def _invoice(org, revision, invoice_id):
    invoice = Invoice.objects.for_organization(org).filter(pk=invoice_id, revision=revision).first()
    if invoice is None:
        raise ApiError(*NOT_FOUND)
    return invoice


def _event(org, actor, obj, name, rev, current=None):
    record_event(
        organization=org,
        actor=actor,
        event_type="document_graph." + name,
        entity=obj,
        current=current or {"id": str(obj.id)},
        scope=rev.case.scope,
    )


def _observations(org, links):
    """Use only the latest completed extraction per *active* case document."""
    link_ids = [link.pk for link in links]
    runs = (
        ExtractionRun.objects.for_organization(org)
        .filter(case_document_id__in=link_ids, status=ExtractionRun.Status.SUCCEEDED)
        .order_by("case_document_id", "-created_at", "-attempt")
    )
    latest = {}
    for run in runs:
        latest.setdefault(run.case_document_id, run.id)
    rows = (
        FieldObservation.objects.for_organization(org)
        .filter(run_id__in=latest.values())
        .values("run__case_document_id", "field_name", "label", "raw_value", "status")
    )
    return list(rows)


def _reference_index(org, links):
    """References with document-specific evidence, not unverified LLM output."""
    index = defaultdict(dict)
    explicit_invoice_numbers = defaultdict(set)
    for row in _observations(org, links):
        doc_id = str(row["run__case_document_id"])
        raw = str(row["raw_value"] or "")[:300]
        if not raw or row["status"] not in {"ok", "low_confidence"}:
            continue
        label = str(row["label"] or "")[:100]
        detected = references(label + ": " + raw)
        if row["field_name"] == "invoice_number" and row["status"] == "ok":
            value = _normalize(raw)
            if value:
                explicit_invoice_numbers[doc_id].add(value)
                detected.append({"kind": "invoice", "value": value, "excerpt": label[:100]})
        for ref in detected:
            value = _normalize(ref["value"])
            if value:
                key = (ref["kind"], value)
                index[key][doc_id] = {"kind": key[0], "value": key[1], "method": ENGINE_VERSION}
    return index, explicit_invoice_numbers


def _suggest(model, org, actor, rev, lookup, evidence, key):
    """Preserve rejection/confirmation across reanalysis; never force a human decision."""
    obj, created = model.objects.get_or_create(
        **lookup,
        defaults={
            "organization": org,
            "created_by": actor,
            "status": "proposed",
            "evidence": evidence[:10],
        },
    )
    if created:
        _event(org, actor, obj, "link_suggested", rev, {"type": key, "id": str(obj.pk)})
    return created


@transaction.atomic
def analyze(*, org, actor, revision_id):
    """Idempotent proposal pass over available extracted fields; leaves unknowns unknown."""
    rev = _revision(org, revision_id)
    if not rev.is_editable:
        raise ApiError("REVISION_NOT_EDITABLE", "Révision non modifiable.", 409)
    links = list(
        CaseDocument.objects.for_organization(org).filter(
            revision=rev, replaced_by__isnull=True, document__readability="ok"
        )
    )
    index, observed_invoice_numbers = _reference_index(org, links)
    invoices = list(Invoice.objects.for_organization(org).filter(revision=rev))
    invoice_by_number = defaultdict(list)
    for invoice in invoices:
        if value := _normalize(invoice.invoice_number):
            invoice_by_number[value].append(invoice)

    counts = {"document_invoices": 0, "shipments": 0, "shipment_documents": 0, "shipment_invoices": 0,
              "conflicts": 0}
    # Exact invoice references may be shared by packing lists, insurance or freight.
    for (kind, value), docs in index.items():
        if kind != "invoice":
            continue
        matches = invoice_by_number.get(value, [])
        if len(matches) != 1:
            continue  # duplicate invoice numbers: never pick a random invoice
        invoice = matches[0]
        for doc_id, evidence in docs.items():
            if str(invoice.document_id or "") == doc_id:
                continue
            if _suggest(
                DocumentInvoiceLink, org, actor, rev,
                {"revision": rev, "document_id": doc_id, "invoice": invoice,
                 "kind": DocumentInvoiceLink.Kind.INVOICE_REFERENCE},
                [evidence], "document_invoice",
            ):
                counts["document_invoices"] += 1

    # A shared explicit transport reference is evidence for a shipment, not proof of its composition.
    for (kind, value), docs in index.items():
        if kind != "transport" or len(docs) < 2:
            continue
        shipment, created = Shipment.objects.get_or_create(
            revision=rev, reference=value,
            defaults={"organization": org, "created_by": actor, "method": ENGINE_VERSION},
        )
        if created:
            counts["shipments"] += 1
            _event(org, actor, shipment, "shipment_suggested", rev, {"reference": value})
        for doc_id, evidence in docs.items():
            if _suggest(
                ShipmentDocument, org, actor, rev, {"shipment": shipment, "document_id": doc_id},
                [evidence], "shipment_document",
            ):
                counts["shipment_documents"] += 1
        for invoice in invoices:
            if str(invoice.document_id or "") in docs:
                if _suggest(
                    ShipmentInvoice, org, actor, rev, {"shipment": shipment, "invoice": invoice},
                    [{"kind": "transport", "value": value, "method": ENGINE_VERSION}], "shipment_invoice",
                ):
                    counts["shipment_invoices"] += 1

    # Compare a *single* explicit extraction header to the current editable invoice.
    # Never replace the invoice or manufacture a zero amount.
    for invoice in invoices:
        if not invoice.document_id or not invoice.invoice_number:
            continue
        observed = observed_invoice_numbers.get(str(invoice.document_id), set())
        expected = _normalize(invoice.invoice_number)
        if len(observed) != 1 or not expected or expected in observed:
            continue
        key = f"{invoice.id}:invoice_number"
        conflict, created = DocumentConflict.objects.get_or_create(
            revision=rev, kind="invoice_reference_mismatch", key=key,
            defaults={
                "organization": org,
                "document_id": invoice.document_id,
                "invoice": invoice,
                "detail": {"current": expected, "observed": next(iter(observed)),
                           "method": ENGINE_VERSION},
                "created_by": actor,
            },
        )
        if created:
            counts["conflicts"] += 1
            _event(org, actor, conflict, "conflict_detected", rev, {"kind": conflict.kind})
    return counts


def _serialize_link(obj):
    data = {
        "id": str(obj.pk),
        "status": obj.status,
        "evidence": obj.evidence,
        "reviewed_at": obj.reviewed_at.isoformat() if obj.reviewed_at else None,
    }
    for field in ("shipment_id", "document_id", "invoice_id", "revision_id", "kind"):
        if hasattr(obj, field):
            value = getattr(obj, field)
            data[field] = str(value) if field.endswith("_id") else value
    return data


def summary(*, org, revision_id):
    rev = _revision(org, revision_id)
    shipments = list(Shipment.objects.for_organization(org).filter(revision=rev).order_by("reference"))
    ds = list(DocumentInvoiceLink.objects.for_organization(org).filter(revision=rev).order_by("created_at"))
    sh_ids = [s.id for s in shipments]
    sh_docs = list(ShipmentDocument.objects.for_organization(org).filter(shipment_id__in=sh_ids))
    sh_invoices = list(ShipmentInvoice.objects.for_organization(org).filter(shipment_id__in=sh_ids))
    conflicts = list(DocumentConflict.objects.for_organization(org).filter(revision=rev))
    return {
        "revision_id": str(rev.pk),
        "engine": ENGINE_VERSION,
        "ai_provider": "disabled",
        "shipments": [
            {
                "id": str(s.id), "reference": s.reference, "status": s.status, "method": s.method,
                "documents": [_serialize_link(link) for link in sh_docs if link.shipment_id == s.id],
                "invoices": [_serialize_link(link) for link in sh_invoices if link.shipment_id == s.id],
            }
            for s in shipments
        ],
        "document_invoices": [_serialize_link(link) for link in ds],
        "conflicts": [
            {"id": str(c.id), "kind": c.kind, "document_id": str(c.document_id) if c.document_id else None,
             "invoice_id": str(c.invoice_id) if c.invoice_id else None,
             "status": c.status, "detail": c.detail, "resolution": c.resolution}
            for c in conflicts
        ],
        "pending_count": (
            sum(link.status == "proposed" for link in ds + sh_docs + sh_invoices)
            + sum(c.status == "open" for c in conflicts)
            + sum(s.status == "proposed" for s in shipments)
        ),
    }


@transaction.atomic
def create_invoice_link(*, org, actor, revision_id, document_id, invoice_id, kind):
    rev = _revision(org, revision_id)
    if not rev.is_editable:
        raise ApiError("REVISION_NOT_EDITABLE", "Révision non modifiable.", 409)
    doc = _document(org, rev, document_id)
    invoice = _invoice(org, rev, invoice_id)
    if kind not in DocumentInvoiceLink.Kind.values:
        raise ApiError("INVALID_RELATION", "Type de lien invalide.", 400)
    if DocumentInvoiceLink.objects.for_organization(org).filter(
        revision=rev, document=doc, invoice=invoice, kind=kind
    ).exists():
        raise ApiError("RELATION_EXISTS", "Lien déjà enregistré.", 409)
    obj = DocumentInvoiceLink.objects.create(
        organization=org, revision=rev, document=doc, invoice=invoice, kind=kind,
        status="confirmed", created_by=actor, reviewed_by=actor, reviewed_at=timezone.now(),
        evidence=[{"method": "manual"}],
    )
    _event(org, actor, obj, "invoice_link_created", rev)
    return _serialize_link(obj)


@transaction.atomic
def create_shipment(*, org, actor, revision_id, reference):
    rev = _revision(org, revision_id)
    if not rev.is_editable:
        raise ApiError("REVISION_NOT_EDITABLE", "Révision non modifiable.", 409)
    value = _normalize(reference)
    if not value:
        raise ApiError("INVALID_REFERENCE", "Référence de transport invalide.", 400)
    if Shipment.objects.for_organization(org).filter(revision=rev, reference=value).exists():
        raise ApiError("SHIPMENT_EXISTS", "Expédition déjà présente.", 409)
    obj = Shipment.objects.create(
        organization=org, revision=rev, reference=value, status="confirmed", method="manual",
        created_by=actor, confirmed_by=actor,
    )
    _event(org, actor, obj, "shipment_created", rev)
    return {"id": str(obj.pk), "reference": obj.reference, "status": obj.status}


@transaction.atomic
def create_shipment_link(*, org, actor, revision_id, shipment_id, target_id, target_type):
    rev = _revision(org, revision_id)
    if not rev.is_editable:
        raise ApiError("REVISION_NOT_EDITABLE", "Révision non modifiable.", 409)
    shipment = Shipment.objects.for_organization(org).filter(pk=shipment_id, revision=rev).first()
    if shipment is None:
        raise ApiError(*NOT_FOUND)
    if target_type == "document":
        target = _document(org, rev, target_id)
        model, field = ShipmentDocument, "document"
    elif target_type == "invoice":
        target = _invoice(org, rev, target_id)
        model, field = ShipmentInvoice, "invoice"
    else:
        raise ApiError("INVALID_RELATION", "Cible invalide.", 400)
    if model.objects.for_organization(org).filter(shipment=shipment, **{field: target}).exists():
        raise ApiError("RELATION_EXISTS", "Lien déjà enregistré.", 409)
    obj = model.objects.create(
        organization=org, shipment=shipment, **{field: target},
        status="confirmed", evidence=[{"method": "manual"}],
        created_by=actor, reviewed_by=actor, reviewed_at=timezone.now(),
    )
    _event(org, actor, obj, "shipment_link_created", rev)
    return _serialize_link(obj)


@transaction.atomic
def review(*, org, actor, model, link_id, status):
    if status not in ("confirmed", "rejected"):
        raise ApiError("INVALID_STATUS", "Décision invalide.", 400)
    models = {
        "document_invoice": DocumentInvoiceLink,
        "shipment_document": ShipmentDocument,
        "shipment_invoice": ShipmentInvoice,
    }
    if model not in models:
        raise ApiError("INVALID_RELATION", "Type de lien invalide.", 400)
    obj = models[model].objects.for_organization(org).select_for_update().filter(pk=link_id).first()
    if obj is None:
        raise ApiError(*NOT_FOUND)
    rev = obj.revision if model == "document_invoice" else obj.shipment.revision
    if not rev.is_editable:
        raise ApiError("REVISION_NOT_EDITABLE", "Révision non modifiable.", 409)
    if obj.status != "proposed":
        raise ApiError("ALREADY_REVIEWED", "Décision déjà prise.", 409)
    obj.status = status
    obj.reviewed_by = actor
    obj.reviewed_at = timezone.now()
    obj.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    _event(org, actor, obj, "link_reviewed", rev, {"status": status, "link_type": model})
    return _serialize_link(obj)


@transaction.atomic
def confirm_shipment(*, org, actor, shipment_id):
    shipment = Shipment.objects.for_organization(org).select_for_update().filter(pk=shipment_id).first()
    if shipment is None:
        raise ApiError(*NOT_FOUND)
    if not shipment.revision.is_editable:
        raise ApiError("REVISION_NOT_EDITABLE", "Révision non modifiable.", 409)
    if shipment.status != "proposed":
        raise ApiError("ALREADY_REVIEWED", "Expédition déjà confirmée.", 409)
    if not ShipmentDocument.objects.for_organization(org).filter(shipment=shipment, status="confirmed").exists():
        raise ApiError("MISSING_EVIDENCE", "Confirmer une pièce avant l'expédition.", 409)
    shipment.status = "confirmed"
    shipment.confirmed_by = actor
    shipment.save(update_fields=["status", "confirmed_by", "updated_at"])
    _event(org, actor, shipment, "shipment_confirmed", shipment.revision)
    return {"id": str(shipment.pk), "reference": shipment.reference, "status": shipment.status}


@transaction.atomic
def resolve_conflict(*, org, actor, conflict_id, reason):
    conflict = DocumentConflict.objects.for_organization(org).select_for_update().filter(pk=conflict_id).first()
    if conflict is None:
        raise ApiError(*NOT_FOUND)
    if not conflict.revision.is_editable:
        raise ApiError("REVISION_NOT_EDITABLE", "Révision non modifiable.", 409)
    if conflict.status != "open":
        raise ApiError("ALREADY_REVIEWED", "Conflit déjà résolu.", 409)
    if not reason.strip():
        raise ApiError("REASON_REQUIRED", "Motif obligatoire.", 400)
    conflict.status = "resolved"
    conflict.resolution = reason.strip()[:500]
    conflict.resolved_by = actor
    conflict.resolved_at = timezone.now()
    conflict.save(update_fields=["status", "resolution", "resolved_by", "resolved_at", "updated_at"])
    _event(org, actor, conflict, "conflict_resolved", conflict.revision, {"status": "resolved"})
    return {"id": str(conflict.pk), "status": conflict.status, "resolution": conflict.resolution}
