"""Circuit de validation interne (WF-01 à WF-03) : soumettre, retourner pour correction, valider.

Préparation → à valider : aucun contrôle bloquant ; en mode opérationnel, calcul complet.
À valider → à corriger : validateur ou administrateur, avec un motif.
À valider → validé : validateur ou administrateur ; le calcul doit être celui qui a été soumis.
L'agent qui a soumis peut valider lui-même s'il a le rôle (choix de l'utilisateur du 30/10/2026).
« Validé » signifie validé en interne par la société, jamais accepté par la Douane.
"""

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from apps.core.concurrency import bump, check_version
from apps.core.exceptions import ApiError
from apps.fiscal.calculation import case_calculation
from apps.organizations.models import Role

from . import completeness, services
from .models import CaseRevision, RevisionDecision

State = CaseRevision.State


def _fingerprint(revision: CaseRevision, calc: dict) -> str:
    data = {"revision": str(revision.id), "calculation": calc}
    raw = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _plain(calc: dict) -> dict:
    """Calcul en JSON (Decimal et dates en texte) pour être figé dans la décision."""
    return json.loads(json.dumps(calc, default=str))


def _lock(org, case_id):
    case = services.lock_case(org, case_id)
    revision = CaseRevision.objects.select_for_update().get(pk=case.current_revision.pk)
    return case, revision


def _require_validator(membership):
    if not membership.has_role(Role.VALIDATOR, Role.ORG_ADMIN):
        raise ApiError("FORBIDDEN", "Seul un validateur ou un administrateur de la société valide un dossier.", 403)


def _decide(org, actor, case, revision, kind, state, *, reason="", calc=None, blocking=None):
    calc = _plain(calc if calc is not None else case_calculation(case))
    previous = revision.state
    revision.state = state
    bump(revision)
    revision.save()
    decision = RevisionDecision.objects.create(
        organization=org,
        revision=revision,
        kind=kind,
        actor=actor,
        reason=reason,
        fingerprint=_fingerprint(revision, calc),
        snapshot={"calculation": calc, "blocking": blocking or []},
    )
    services._event(
        org,
        actor,
        f"revision.{kind}",
        revision,
        case,
        {"state": previous},
        {"state": state, **({"reason": reason} if reason else {})},
    )
    return decision


def last_submission(revision: CaseRevision) -> RevisionDecision | None:
    return revision.decisions.filter(kind=RevisionDecision.Kind.SUBMITTED).order_by("-created_at").first()


def validated_decision(revision: CaseRevision) -> RevisionDecision | None:
    """Décision de validation qui fait foi ; un dossier archivé après validation la garde."""
    if revision.state not in (State.VALIDATED, State.ARCHIVED):
        return None
    return revision.decisions.filter(kind=RevisionDecision.Kind.VALIDATED).order_by("-created_at").first()


@transaction.atomic
def submit(*, org, actor, case_id, expected) -> RevisionDecision:
    """WF-01 : soumission seulement quand les contrôles obligatoires passent ; blocages listés sinon."""
    case, revision = _lock(org, case_id)
    check_version(revision, expected)
    if not revision.is_editable:
        raise ApiError("INVALID_TRANSITION", f"Révision « {revision.get_state_display()} » : rien à soumettre.", 409)
    blocking = completeness.evaluate(revision)["blocking"]
    if blocking:
        raise ApiError(
            "SUBMISSION_BLOCKED",
            f"{len(blocking)} point(s) bloquant(s) à régler avant de soumettre.",
            409,
            {"blocking": blocking},
        )
    calc = case_calculation(case)
    if revision.mode == CaseRevision.Mode.OPERATIONAL and calc["totals"]["total"] is None:
        raise ApiError(
            "SUBMISSION_BLOCKED", "Calcul incomplet : une taxe ou une valeur reste inconnue.", 409, {"blocking": []}
        )
    return _decide(org, actor, case, revision, RevisionDecision.Kind.SUBMITTED, State.TO_VALIDATE, calc=calc)


@transaction.atomic
def return_for_correction(*, org, actor, membership, case_id, expected, reason: str) -> RevisionDecision:
    """WF-02 : retour motivé ; la révision redevient modifiable."""
    _require_validator(membership)
    case, revision = _lock(org, case_id)
    check_version(revision, expected)
    if revision.state != State.TO_VALIDATE:
        raise ApiError("INVALID_TRANSITION", "Seul un dossier « À valider » se retourne pour correction.", 409)
    if not reason.strip():
        raise ApiError("VALIDATION_ERROR", "Le motif du retour est obligatoire.", 400)
    return _decide(org, actor, case, revision, RevisionDecision.Kind.RETURNED, State.TO_CORRECT, reason=reason.strip())


@transaction.atomic
def validate(*, org, actor, membership, case_id, expected, reason: str = "") -> RevisionDecision:
    """WF-02, WF-03 : validation interne sur le calcul soumis, figé dans la décision."""
    _require_validator(membership)
    case, revision = _lock(org, case_id)
    check_version(revision, expected)
    if revision.state != State.TO_VALIDATE:
        raise ApiError("INVALID_TRANSITION", "Seul un dossier « À valider » se valide.", 409)
    submission = last_submission(revision)
    calc = _plain(case_calculation(case))
    # La révision n'est plus modifiable depuis la soumission : seul le calcul peut avoir bougé.
    if submission is None or submission.fingerprint != _fingerprint(revision, calc):
        raise ApiError(
            "STALE_SUBMISSION",
            "Le calcul a changé depuis la soumission (taux modifié ou barème activé) : "
            "retourner le dossier pour correction, puis le soumettre de nouveau.",
            409,
        )
    return _decide(
        org, actor, case, revision, RevisionDecision.Kind.VALIDATED, State.VALIDATED, reason=reason.strip(), calc=calc
    )


# --- Fin de vie : dépôt en douane déclaré par l'agent, archivage, sortie des archives ----------


def _record(org, actor, case, revision, kind, *, reason="", snapshot=None, previous=None, current=None):
    validated = revision.decisions.filter(kind=RevisionDecision.Kind.VALIDATED).order_by("-created_at").first()
    bump(revision)
    revision.save()
    decision = RevisionDecision.objects.create(
        organization=org,
        revision=revision,
        kind=kind,
        actor=actor,
        reason=reason,
        fingerprint=validated.fingerprint if validated else "",
        snapshot=snapshot or {},
    )
    services._event(org, actor, f"revision.{kind}", revision, case, previous, current)
    return decision


@transaction.atomic
def lodge(*, org, actor, case_id, expected, number: str, lodged_on, reason: str = "") -> RevisionDecision:
    """Après validation interne : l'agent indique le n° et la date de dépôt dans SYDONIA."""
    from datetime import date

    case, revision = _lock(org, case_id)
    check_version(revision, expected)
    if revision.state != State.VALIDATED:
        raise ApiError("INVALID_TRANSITION", "Seul un dossier validé en interne se déclare déposé en douane.", 409)
    if revision.customs_declaration_number:
        raise ApiError("ALREADY_LODGED", "Le dépôt de cette révision est déjà enregistré.", 409)
    number = " ".join((number or "").split())[:60]
    if not number:
        raise ApiError("VALIDATION_ERROR", "Le n° de déclaration est obligatoire.", 400, {"field": "number"})
    try:
        day = lodged_on if isinstance(lodged_on, date) else date.fromisoformat(str(lodged_on or ""))
    except ValueError:
        raise ApiError(
            "VALIDATION_ERROR", "Date de dépôt invalide (AAAA-MM-JJ).", 400, {"field": "lodged_on"}
        ) from None
    if day > date.today():
        raise ApiError("VALIDATION_ERROR", "La date de dépôt ne peut pas être future.", 400, {"field": "lodged_on"})
    revision.customs_declaration_number = number
    revision.lodged_on = day
    data = {"declaration_number": number, "lodged_on": day.isoformat()}
    return _record(org, actor, case, revision, RevisionDecision.Kind.LODGED, reason=(reason or "").strip()[:2000],
                   snapshot=data, current=data)  # fmt: skip


@transaction.atomic
def archive(*, org, actor, membership, case_id, expected, reason: str = "") -> RevisionDecision:
    """Classe le dossier : lecture seule. Avant validation (abandon), le motif est obligatoire."""
    _require_validator(membership)
    case, revision = _lock(org, case_id)
    check_version(revision, expected)
    previous = revision.state
    if previous not in (State.VALIDATED, *CaseRevision.EDITABLE_STATES):
        raise ApiError(
            "INVALID_TRANSITION", f"Dossier « {revision.get_state_display()} » : à décider avant d'archiver.", 409
        )
    reason = (reason or "").strip()[:2000]
    if previous != State.VALIDATED and not reason:
        raise ApiError("VALIDATION_ERROR", "Motif obligatoire pour archiver un dossier non validé.", 400,
                       {"field": "reason"})  # fmt: skip
    revision.state = State.ARCHIVED
    case.archived_at = timezone.now()
    case.save(update_fields=["archived_at"])
    return _record(org, actor, case, revision, RevisionDecision.Kind.ARCHIVED, reason=reason,
                   snapshot={"previous_state": previous}, previous={"state": previous},
                   current={"state": State.ARCHIVED})  # fmt: skip


@transaction.atomic
def restore(*, org, actor, membership, case_id, expected, reason: str) -> RevisionDecision:
    """Sort un dossier des archives (administrateur de la société), dans l'état qu'il avait."""
    if not membership.has_role(Role.ORG_ADMIN):
        raise ApiError("FORBIDDEN", "Seul un administrateur de la société sort un dossier des archives.", 403)
    case, revision = _lock(org, case_id)
    check_version(revision, expected)
    if revision.state != State.ARCHIVED:
        raise ApiError("INVALID_TRANSITION", "Ce dossier n'est pas archivé.", 409)
    reason = (reason or "").strip()[:2000]
    if not reason:
        raise ApiError("VALIDATION_ERROR", "Le motif est obligatoire.", 400, {"field": "reason"})
    last = revision.decisions.filter(kind=RevisionDecision.Kind.ARCHIVED).order_by("-created_at").first()
    target = (last.snapshot.get("previous_state") if last else None) or State.VALIDATED
    revision.state = target
    case.archived_at = None
    case.save(update_fields=["archived_at"])
    return _record(org, actor, case, revision, RevisionDecision.Kind.RESTORED, reason=reason,
                   previous={"state": State.ARCHIVED}, current={"state": target})  # fmt: skip
