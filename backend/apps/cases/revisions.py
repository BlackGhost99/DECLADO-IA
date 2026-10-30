"""Nouvelle révision d'un dossier validé (WF-04).

La révision validée reste telle quelle : décisions, calcul figé et exports restent consultables.
La nouvelle révision repart en brouillon avec une copie des pièces rattachées (mêmes originaux),
des factures, lignes, codes relevés et marchandises. Un code validé sur des données identiques
est repris avec son auteur et son motif, et la reprise est tracée dans ses preuves ; tout le
reste (contrôles, propositions, soumission, validation) se refait sur la nouvelle révision.
"""

from django.db import transaction
from django.db.models import Max

from apps.core.exceptions import ApiError
from apps.regulations.models import DocumentClassification

from . import codecheck, services
from .models import (
    CaseRevision,
    ClassificationDecision,
    CodeObservation,
    GoodsLine,
    GoodsLineSource,
    InvoiceLine,
)

SKIP = {"id", "created_at", "updated_at", "row_version"}


def _clone(obj, **overrides):
    data = {f.attname: getattr(obj, f.attname) for f in obj._meta.concrete_fields if f.name not in SKIP}
    data.update(overrides)
    return type(obj).objects.create(**data)


@transaction.atomic
def create_revision(*, org, actor, case_id, reason: str) -> CaseRevision:
    case = services.lock_case(org, case_id)
    old = CaseRevision.objects.select_for_update().get(pk=case.current_revision_id)
    if old.state != CaseRevision.State.VALIDATED:
        raise ApiError(
            "REVISION_NOT_VALIDATED",
            "Une nouvelle révision se crée après validation interne ; la révision courante reste modifiable.",
            409,
            {"current_state": old.state},
        )
    reason = (reason or "").strip()
    if not reason:
        raise ApiError("VALIDATION_ERROR", "Le motif de la nouvelle révision est obligatoire.", 400)

    number = (case.revisions.aggregate(n=Max("revision_no"))["n"] or 0) + 1
    new = _clone(
        old,
        revision_no=number,
        parent_revision_id=old.id,
        state=CaseRevision.State.DRAFT,
        reason=reason[:2000],
        created_by_id=actor.id,
    )

    links = {}
    for link in old.documents.filter(replaced_by__isnull=True):
        links[link.id] = _clone(
            link, revision_id=new.id, replaced_by_id=None, idempotency_key="", copied_from_id=link.id
        ).id
        # Le type de pièce confirmé par un agent suit la pièce : il ne se reconfirme pas.
        confirmed = DocumentClassification.objects.filter(case_document=link).first()
        if confirmed is not None:
            _clone(confirmed, case_document_id=links[link.id])
    invoices, lines, observations = {}, {}, {}
    for inv in old.invoices.all():
        invoices[inv.id] = _clone(
            inv, revision_id=new.id, document_id=links.get(inv.document_id), copied_from_id=inv.id
        ).id
    for line in InvoiceLine.objects.filter(invoice__revision=old):
        lines[line.id] = _clone(
            line,
            invoice_id=invoices[line.invoice_id],
            evidence_document_id=links.get(line.evidence_document_id),
            copied_from_id=line.id,
        ).id
    for obs in CodeObservation.objects.filter(invoice_line__invoice__revision=old, superseded_at__isnull=True):
        observations[obs.id] = _clone(
            obs,
            invoice_line_id=lines[obs.invoice_line_id],
            evidence_document_id=links.get(obs.evidence_document_id),
            superseded_by_id=None,
            superseded_at=None,
        ).id

    carried = 0
    for goods in old.goods_lines.all():
        copy = _clone(goods, revision_id=new.id)
        for src in GoodsLineSource.objects.filter(goods_line=goods):
            _clone(src, goods_line_id=copy.id, invoice_line_id=lines[src.invoice_line_id])
        decision = services.current_decision(goods)
        if decision is None or not services.decision_is_current(decision, goods):
            continue
        refs = [*decision.evidence_refs, {"kind": "carried_from", "decision_id": str(decision.id),
                                          "revision_no": old.revision_no}]  # fmt: skip
        ClassificationDecision.objects.create(
            organization=org,
            goods_line=copy,
            original_observation_id=observations.get(decision.original_observation_id),
            selected_node_id=decision.selected_node_id,
            selected_code=decision.selected_code,
            edition_id=decision.edition_id,
            action=decision.action,
            reason=decision.reason,
            evidence_refs=refs,
            actor_id=decision.actor_id,
            goods_line_version=copy.row_version,
            input_hash=codecheck.code_inputs_hash(GoodsLine.objects.get(pk=copy.pk), decision.edition_id),
        )
        carried += 1

    case.current_revision = new
    case.save(update_fields=["current_revision"])
    services._event(
        org,
        actor,
        "revision.created",
        new,
        case,
        {"revision_no": old.revision_no, "state": old.state},
        {"revision_no": new.revision_no, "reason": new.reason, "documents": len(links), "codes_carried": carried},
    )
    return new
