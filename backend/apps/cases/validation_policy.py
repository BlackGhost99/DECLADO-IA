"""Règles de validation interne : le mode agent unique exige une activation explicite.

Aucune validation interne ne constitue une acceptation par la Douane.
"""
from apps.core.exceptions import ApiError
from apps.organizations.models import Role

MODES = frozenset({"single_agent", "dual_control", "conditional"})


def policy_for(organization):
    raw = organization.validation_policy or {}
    mode = raw.get("mode")
    if mode not in MODES:
        # Politique historique : séparation obligatoire (fail closed).
        mode = "dual_control"
    return {"mode": mode, "version": raw.get("version", 1)}


def can_validate(*, organization, membership, actor, revision, assessment):
    mode = policy_for(organization)["mode"]
    if not assessment["complete"] or assessment["blocking"]:
        raise ApiError("DOSSIER_INCOMPLETE", "Le dossier contient des contrôles bloquants.", 409)
    if revision.mode != "operational":
        raise ApiError("NOT_OPERATIONAL", "Seul un dossier opérationnel peut être validé en interne.", 409)

    validator = membership.has_role(Role.VALIDATOR, Role.ORG_ADMIN)
    declarant = membership.has_role(Role.DECLARANT)
    assigned = revision.case.assigned_to_id == actor.pk
    creator = revision.case.created_by_id == actor.pk

    # Les avertissements déclenchent la validation à deux en mode conditionnel.
    effective_dual = mode == "dual_control" or (mode == "conditional" and bool(assessment["warnings"]))
    if effective_dual:
        if not validator:
            raise ApiError("SECOND_VALIDATOR_REQUIRED", "Un validateur habilité est requis.", 403)
        if creator or assigned:
            raise ApiError("SEPARATION_OF_DUTIES", "La validation doit être effectuée par une autre personne.", 403)
    elif not (validator or (declarant and (assigned or creator))):
        raise ApiError("VALIDATION_DENIED", "Vous ne pouvez pas valider ce dossier.", 403)
    return {"mode": mode, "dual_control_applied": effective_dual}
