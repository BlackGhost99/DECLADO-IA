"""Services du référentiel : comparaison de sources, résolution d'anomalies, publication, recherche."""

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramSimilarity
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import record_event
from apps.core.exceptions import ApiError

from .codes import normalize_code
from .models import (
    ImportIssue,
    NodeCorrection,
    NodeKind,
    PublicationState,
    TariffEdition,
    TariffNode,
)
from .text import search_normalize

S = ImportIssue.Severity
CORRECTABLE_FIELDS = {"label_clean", "declarable"}


@transaction.atomic
def compare_editions(*, reference: TariffEdition, other: TariffEdition) -> dict:
    """REF-03 : divergences de codes entre deux sources, enregistrées sur l'import le plus récent.

    Aucune source ne « gagne » : chaque écart devient une anomalie à examiner.
    """
    target_run = max(reference.import_run, other.import_run, key=lambda r: r.started_at)

    def lines(edition):
        return dict(TariffNode.objects.filter(edition=edition, kind=NodeKind.TARIFF_LINE).values_list("code", "id"))

    a, b = lines(reference), lines(other)
    issues = []
    for code in sorted(a.keys() - b.keys()):
        issues.append(
            ImportIssue(
                run=target_run,
                node_id=a[code] if target_run == reference.import_run else None,
                category="SOURCE_DIVERGENCE",
                severity=S.REVIEW,
                message=f"Code {code} présent dans « {reference.label} », absent de « {other.label} ».",
                details={"code": code, "present_in": str(reference.id), "absent_from": str(other.id)},
            )
        )
    for code in sorted(b.keys() - a.keys()):
        issues.append(
            ImportIssue(
                run=target_run,
                node_id=b[code] if target_run == other.import_run else None,
                category="SOURCE_DIVERGENCE",
                severity=S.REVIEW,
                message=f"Code {code} présent dans « {other.label} », absent de « {reference.label} ».",
                details={"code": code, "present_in": str(other.id), "absent_from": str(reference.id)},
            )
        )
    ImportIssue.objects.bulk_create(issues, batch_size=1000)
    summary = {
        "common": len(a.keys() & b.keys()),
        "only_reference": len(a.keys() - b.keys()),
        "only_other": len(b.keys() - a.keys()),
    }
    target_run.counts = {
        **target_run.counts,
        "comparison": {**summary, "with": str(other.id if target_run == reference.import_run else reference.id)},
    }
    target_run.save(update_fields=["counts"])
    return summary


def _require_manager(actor):
    if not getattr(actor, "is_reference_manager", False):
        raise ApiError("FORBIDDEN", "Réservé aux gestionnaires du référentiel.", 403)


@transaction.atomic
def resolve_issue(
    *, issue: ImportIssue, actor, resolution: str, reason: str, evidence: str = "", correction: dict | None = None
) -> ImportIssue:
    """Résout une anomalie sans toucher à la source brute (REF-05)."""
    _require_manager(actor)
    if issue.state == ImportIssue.State.RESOLVED:
        raise ApiError("ALREADY_RESOLVED", "Anomalie déjà résolue.", 409)
    if resolution not in ImportIssue.Resolution.values:
        raise ApiError("INVALID_RESOLUTION", "Résolution inconnue.", 400)
    if not reason.strip():
        raise ApiError("REASON_REQUIRED", "Une justification est obligatoire.", 400)
    if resolution == ImportIssue.Resolution.CORRECTED:
        if not correction or not issue.node_id:
            raise ApiError("CORRECTION_REQUIRED", "Une correction sur un nœud identifié est attendue.", 400)
        if not evidence.strip():
            raise ApiError("EVIDENCE_REQUIRED", "Une pièce probante est obligatoire pour corriger.", 400)
        apply_correction(
            node=issue.node,
            actor=actor,
            field=correction.get("field"),
            value=correction.get("value"),
            reason=reason,
            evidence=evidence,
            issue=issue,
        )
    issue.state = ImportIssue.State.RESOLVED
    issue.resolution = resolution
    issue.resolution_reason = reason
    issue.resolution_evidence = evidence
    issue.resolved_by = actor
    issue.resolved_at = timezone.now()
    issue.save()
    record_event(
        organization=None,
        actor=actor,
        event_type="tariff.issue_resolved",
        entity=issue,
        current={"resolution": resolution, "category": issue.category},
    )
    return issue


def apply_correction(
    *, node: TariffNode, actor, field: str, value, reason: str, evidence: str, issue: ImportIssue | None = None
) -> NodeCorrection:
    _require_manager(actor)
    if not node.edition.is_mutable:
        raise ApiError(
            "EDITION_IMMUTABLE", "Édition publiée : toute modification passe par une nouvelle version (REF-06).", 409
        )
    if field not in CORRECTABLE_FIELDS:
        raise ApiError("FIELD_NOT_CORRECTABLE", "Champ non corrigeable.", 400, {"allowed": sorted(CORRECTABLE_FIELDS)})
    previous = getattr(node, field)
    if field == "declarable":
        value = bool(value)
    setattr(node, field, value)
    if field == "label_clean":
        node.label_damaged = False
        node.search_text = search_normalize(value)
        node.full_path_label = (
            node.full_path_label.rsplit(" › ", 1)[0] + f" › {value}" if " › " in (node.full_path_label) else value
        )
    node.save()
    correction = NodeCorrection.objects.create(
        node=node,
        issue=issue,
        field=field,
        previous=str(previous),
        current=str(value),
        reason=reason,
        evidence=evidence,
        actor=actor,
    )
    record_event(
        organization=None,
        actor=actor,
        event_type="tariff.node_corrected",
        entity=node,
        previous={field: str(previous)},
        current={field: str(value)},
    )
    return correction


@transaction.atomic
def publish_edition(*, edition: TariffEdition, actor, mode: str) -> TariffEdition:
    """REF-04 / REF-06 : publication immuable ; l'usage opérationnel exige une applicabilité vérifiée."""
    _require_manager(actor)
    edition = TariffEdition.objects.select_for_update().get(pk=edition.pk)
    if edition.publication_state != PublicationState.DRAFT:
        raise ApiError("ALREADY_PUBLISHED", "Seule une édition en brouillon peut être publiée.", 409)
    if mode == PublicationState.OPERATIONAL:
        missing = []
        if not edition.effective_from:
            missing.append("date d'effet vérifiée")
        if not edition.applicability_verified:
            missing.append("applicabilité vérifiée")
        if edition.import_run.source.is_derived_copy:
            missing.append("source originale (la source est une copie dérivée)")
        missing.append("profil fiscal validé (lot 4)")
        raise ApiError(
            "OPERATIONAL_NOT_ALLOWED",
            "Publication opérationnelle impossible : " + ", ".join(missing) + ".",
            422,
            {"missing": missing},
        )
    if mode != PublicationState.CONSULTATION:
        raise ApiError("INVALID_MODE", "Mode de publication inconnu.", 400)
    edition.publication_state = PublicationState.CONSULTATION
    edition.published_at = timezone.now()
    edition.published_by = actor
    edition.save()
    record_event(
        organization=None, actor=actor, event_type="tariff.edition_published", entity=edition, current={"mode": mode}
    )
    return edition


@transaction.atomic
def withdraw_edition(*, edition: TariffEdition, actor, reason: str) -> TariffEdition:
    _require_manager(actor)
    if not reason.strip():
        raise ApiError("REASON_REQUIRED", "Une justification est obligatoire.", 400)
    if edition.publication_state == PublicationState.WITHDRAWN:
        raise ApiError("ALREADY_WITHDRAWN", "Édition déjà retirée.", 409)
    previous = edition.publication_state
    edition.publication_state = PublicationState.WITHDRAWN
    edition.withdrawn_at = timezone.now()
    edition.save()
    record_event(
        organization=None,
        actor=actor,
        event_type="tariff.edition_withdrawn",
        entity=edition,
        previous={"state": previous},
        current={"state": edition.publication_state, "reason": reason},
    )
    return edition


def visible_editions(user):
    qs = TariffEdition.objects.select_related("import_run__source")
    if getattr(user, "is_reference_manager", False):
        return qs
    # Une édition retirée reste consultable par lien direct (historique), mais sort de la recherche.
    return qs.filter(published_at__isnull=False)


def search(*, user, q: str, edition_id=None, code_prefix: str | None = None, limit: int = 25) -> list[dict]:
    """REC-01 : exact → préfixe → texte intégral → trigrammes, avec la raison de chaque résultat."""
    editions = visible_editions(user).exclude(publication_state=PublicationState.WITHDRAWN)
    if edition_id:
        editions = editions.filter(pk=edition_id)
    base = TariffNode.objects.filter(edition__in=editions).select_related("edition")
    q = (q or "").strip()
    results: list[tuple[TariffNode, str]] = []
    seen = set()

    def push(nodes, reason):
        for node in nodes:
            if node.pk not in seen and len(results) < limit:
                seen.add(node.pk)
                results.append((node, reason))

    prefix = normalize_code(code_prefix) if code_prefix else None
    if prefix:
        base = base.filter(code__startswith=prefix)

    code = normalize_code(q) if q else None
    if code:
        push(base.filter(code=code).order_by("edition__label"), "code exact")
        push(base.filter(code__startswith=code).exclude(code=code).order_by("code", "edition__label"), "préfixe")
    elif q:
        normalized = search_normalize(q)
        query = SearchQuery(normalized, config="french", search_type="plain")
        vector = SearchVector("search_text", config="french")
        push(
            base.annotate(document=vector, rank=SearchRank(vector, query))
            .filter(document=query)
            .order_by("-rank", "code"),
            "texte",
        )
        push(
            base.annotate(sim=TrigramSimilarity("search_text", normalized))
            .filter(Q(sim__gt=0.25))
            .order_by("-sim", "code"),
            "proximité orthographique",
        )
    elif prefix:
        push(base.order_by("code"), "préfixe")
    return [{"node": node, "reason": reason} for node, reason in results]
