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
    if revision.state != State.VALIDATED:
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
