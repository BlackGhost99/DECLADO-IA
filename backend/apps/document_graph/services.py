"""Graph mutations: enforce tenant, revision, and immutable review history."""

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_event
from apps.cases.models import CaseDocument, CaseRevision
from apps.core.exceptions import ApiError

from .models import DocumentRelation

KINDS = {"same_shipment", "supports_invoice", "shared_insurance", "shared_transport", "other"}


def _revision(org, revision_id):
    rev = CaseRevision.objects.for_organization(org).filter(pk=revision_id).first()
    if rev is None:
        raise ApiError("NOT_FOUND", "Révision introuvable.", 404)
    return rev


def _document(org, rev, pk):
    link = CaseDocument.objects.for_organization(org).filter(pk=pk, revision=rev, replaced_by__isnull=True).first()
    if link is None:
        raise ApiError("NOT_FOUND", "Pièce introuvable dans cette révision.", 404)
    return link


def as_dict(link):
    return {
        "id": str(link.pk),
        "revision_id": str(link.revision_id),
        "source_id": str(link.source_id),
        "target_id": str(link.target_id),
        "kind": link.kind,
        "status": link.status,
        "provenance": link.provenance,
        "rationale": link.rationale,
        "reviewed_at": link.reviewed_at,
    }


@transaction.atomic
def add_relation(*, org, actor, revision_id, source_id, target_id, kind, rationale=""):
    rev = _revision(org, revision_id)
    if not rev.is_editable:
        raise ApiError("REVISION_NOT_EDITABLE", "Révision non modifiable.", 409)
    if kind not in KINDS or str(source_id) == str(target_id):
        raise ApiError("INVALID_RELATION", "Relation invalide.", 400)
    source = _document(org, rev, source_id)
    target = _document(org, rev, target_id)
    if (
        DocumentRelation.objects.for_organization(org)
        .filter(revision=rev, source=source, target=target, kind=kind)
        .exists()
    ):
        raise ApiError("RELATION_EXISTS", "Relation déjà enregistrée.", 409)
    relation = DocumentRelation.objects.create(
        organization=org,
        revision=rev,
        source=source,
        target=target,
        kind=kind,
        provenance="manual",
        rationale=rationale[:500],
        created_by=actor,
        status=DocumentRelation.Status.CONFIRMED,
        reviewed_by=actor,
        reviewed_at=timezone.now(),
    )
    record_event(
        organization=org,
        actor=actor,
        event_type="document_graph.relation_created",
        entity=relation,
        current=as_dict(relation),
        scope=rev.case.scope,
    )
    return relation


@transaction.atomic
def review_relation(*, org, actor, relation_id, status):
    relation = (
        DocumentRelation.objects.for_organization(org)
        .select_for_update()
        .select_related("revision__case")
        .filter(pk=relation_id)
        .first()
    )
    if relation is None:
        raise ApiError("NOT_FOUND", "Relation introuvable.", 404)
    if not relation.revision.is_editable:
        raise ApiError("REVISION_NOT_EDITABLE", "Révision non modifiable.", 409)
    if status not in (DocumentRelation.Status.CONFIRMED, DocumentRelation.Status.REJECTED):
        raise ApiError("INVALID_STATUS", "Décision invalide.", 400)
    if relation.status != DocumentRelation.Status.PROPOSED:
        raise ApiError("ALREADY_REVIEWED", "Relation déjà examinée.", 409)
    before = as_dict(relation)
    relation.status = status
    relation.reviewed_by = actor
    relation.reviewed_at = timezone.now()
    relation.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    record_event(
        organization=org,
        actor=actor,
        event_type="document_graph.relation_reviewed",
        entity=relation,
        previous=before,
        current=as_dict(relation),
        scope=relation.revision.case.scope,
    )
    return relation


@transaction.atomic
def suggest_relations(*, org, actor, revision_id):
    """Create human-reviewable suggestions from extracted field observations only."""
    from apps.extraction.models import FieldObservation

    from .matcher import propose_links

    rev = _revision(org, revision_id)
    if not rev.is_editable:
        raise ApiError("REVISION_NOT_EDITABLE", "Révision non modifiable.", 409)
    links = list(
        CaseDocument.objects.for_organization(org)
        .filter(revision=rev, replaced_by__isnull=True)
        .values_list("id", flat=True)
    )
    texts = {str(pk): [] for pk in links}
    observations = (
        FieldObservation.objects.for_organization(org)
        .filter(run__case_document_id__in=links, run__status="succeeded")
        .values_list("run__case_document_id", "raw_value")
    )
    for pk, raw in observations.iterator():
        if raw:
            texts[str(pk)].append(str(raw)[:500])
    candidates = propose_links([{"id": pk, "text": "\n".join(values)} for pk, values in texts.items()])
    saved = []
    for suggestion in candidates:
        source = suggestion["source_id"]
        target = suggestion["target_id"]
        if (
            DocumentRelation.objects.for_organization(org)
            .filter(revision=rev, source_id=source, target_id=target)
            .exists()
        ):
            continue
        relation = DocumentRelation.objects.create(
            organization=org,
            revision=rev,
            source_id=source,
            target_id=target,
            kind="same_shipment",
            provenance="suggested",
            status=DocumentRelation.Status.PROPOSED,
            rationale="Référence commune détectée ; vérifier avant confirmation.",
            created_by=actor,
        )
        record_event(
            organization=org,
            actor=actor,
            event_type="document_graph.relation_suggested",
            entity=relation,
            current={"references": suggestion["evidence"], "relation": as_dict(relation)},
            scope=rev.case.scope,
        )
        saved.append({"relation": as_dict(relation), "evidence": suggestion["evidence"]})
    return saved
