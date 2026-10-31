"""Choix du code par l'IA parmi les propositions du référentiel (CLA-IA).

La recherche dans le tarif (proposals.py) trouve les lignes candidates, sans IA. L'IA en ligne,
quand la société l'a activée, lit la désignation et choisit l'une de ces lignes en citant le
passage qui la distingue, ou répond « information insuffisante ». Contrôles, quel que soit le
fournisseur : la ligne choisie doit être l'une des candidates, avec le même code, et le passage
cité doit se retrouver dans la désignation ; sinon le choix est écarté, jamais réparé.

Ne partent que la désignation de la marchandise et les libellés du tarif : ni pièce, ni client,
ni montant. Le refus du client et le plafond mensuel de la société s'appliquent comme pour le
complément des pièces. Le choix reste une proposition : seul un agent décide le code, et sa
décision garde la trace du choix de l'IA qu'il a retenu.
"""

import logging
import time
from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction

from apps.core.exceptions import ApiError
from apps.extraction import ai
from apps.extraction.ai_completion import sent_this_month, settings_for
from apps.extraction.models import OrganizationAISettings

from . import codecheck, proposals, services
from .models import AIClassification, CodeCheck, GoodsLine, ProposalSet

logger = logging.getLogger(__name__)

NEEDS_CODE = (CodeCheck.State.INCOMPLETE, CodeCheck.State.MISSING, CodeCheck.State.NOT_FOUND, CodeCheck.State.AMBIGUOUS)
MAX_DESCRIPTION = 1000
MAX_REASON = 500


def available(org, *, auto: bool = False) -> bool:
    """Un fournisseur est raccordé sur le serveur et la société a activé l'IA en ligne."""
    conf = settings_for(org)
    if not (ai.is_enabled() and conf.enabled):
        return False
    return not auto or conf.mode == OrganizationAISettings.Mode.AUTO


def _flat(text: str) -> str:
    return " ".join((text or "").lower().split())


def description_of(goods: GoodsLine) -> str:
    extra = [str(v) for v in (goods.attributes or {}).values() if isinstance(v, str | int)]
    return " ".join([goods.description, *extra]).strip()[:MAX_DESCRIPTION]


@dataclass
class Outcome:
    status: str
    chosen: object = None  # ClassificationProposal
    reason: str = ""
    evidence: str = ""
    rejected: list[dict] = field(default_factory=list)
    completion: ai.Completion | None = None
    sent_chars: int = 0
    latency_ms: int | None = None
    error_code: str = ""
    error_message: str = ""


def validate(item, by_id: dict, description: str) -> tuple[object, str, str, list[dict]]:
    """(proposition retenue ou None, raison, passage cité, rejets)."""
    if not isinstance(item, dict):
        return None, "", "", [{"reason": "Format inattendu."}]
    reason = str(item.get("reason") or "").strip()[:MAX_REASON]
    if not item.get("found"):
        return None, reason, "", []
    proposal = by_id.get(str(item.get("node_id") or ""))
    if proposal is None:
        return None, "", "", [{"reason": "Ligne absente des candidats fournis : code inventé rejeté."}]
    code = "".join(ch for ch in str(item.get("code") or "") if ch.isdigit())
    if code != proposal.code:
        return None, "", "", [{"reason": "Code différent de celui de la ligne choisie."}]
    evidence = str(item.get("evidence") or "").strip()
    if not evidence or _flat(evidence) not in _flat(description):
        return None, "", "", [{"reason": "Passage cité introuvable dans la désignation : choix écarté."}]
    return proposal, reason, evidence[:200], []


def ask(goods: GoodsLine, proposal_set: ProposalSet) -> Outcome:
    """Contrôles d'envoi, appel et vérification ; n'écrit rien (appelé hors transaction)."""
    importer = goods.revision.case.importer
    if importer is not None and importer.ai_refused:
        return Outcome(AIClassification.Status.CLIENT_REFUSED)
    if sent_this_month(goods.organization) >= settings_for(goods.organization).monthly_cap:
        return Outcome(AIClassification.Status.CAP_REACHED)
    candidates = list(proposal_set.proposals.select_related("node"))
    by_id = {str(p.node_id): p for p in candidates}
    sent = [
        {
            "node_id": str(p.node_id),
            "code": p.node.code_display or p.code,
            "path": p.node.full_path_label or p.node.label_clean,
        }
        for p in candidates
    ]
    description = description_of(goods)
    sent_chars = len(description) + sum(len(c["path"]) + len(c["code"]) for c in sent)
    start = time.monotonic()
    try:
        completion = ai.get_provider().choose_code(description=description, candidates=sent)
    except ai.AIUnavailable as exc:
        return Outcome(
            AIClassification.Status.FAILED,
            sent_chars=sent_chars,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_code=getattr(exc, "code", "AI_DISABLED"),
            error_message=getattr(exc, "message", str(exc))[:300],
        )
    item = completion.items[0] if completion.items else None
    chosen, reason, evidence, rejected = validate(item, by_id, description)
    return Outcome(
        AIClassification.Status.SENT,
        chosen,
        reason,
        evidence,
        rejected,
        completion,
        sent_chars=sent_chars,
        latency_ms=int((time.monotonic() - start) * 1000),
    )


def _current_set(goods: GoodsLine, edition_id) -> ProposalSet | None:
    found = goods.proposal_sets.filter(edition_id=edition_id).first()
    if found is not None and found.input_hash == proposals._digest(goods, edition_id, found.query):
        return found
    return None


def choose(*, org, actor, goods_id, trigger: str = "on_demand") -> AIClassification | None:
    """Prépare les propositions si besoin, demande le choix à l'IA et l'enregistre."""
    if not available(org, auto=trigger == "auto"):
        if trigger == "auto":
            return None
        raise ApiError(
            "AI_NOT_ENABLED",
            "IA en ligne non activée : un administrateur l'active dans Administration, IA en ligne.",
            409,
        )
    with transaction.atomic():
        goods = services._get(
            GoodsLine.objects.for_organization(org).select_related("revision__case__importer"), goods_id
        )
        services._require_editable(goods.revision)
        check = services.latest_check(goods)
        if check is None or check.checked_input_hash != codecheck.code_inputs_hash(goods, check.target_edition_id):
            raise ApiError("CODE_CHECK_STALE", "Contrôler d'abord le code de la marchandise.", 409)
        if check.state == CodeCheck.State.RECOGNIZED:
            raise ApiError("PROPOSALS_NOT_NEEDED", "Le code présent est retrouvé : le confirmer.", 409)
        proposal_set = _current_set(goods, check.target_edition_id) or proposals.propose(
            org=org, actor=actor, goods=goods, edition=check.target_edition
        )
    if not proposal_set.proposals.exists():
        return None  # rien à départager : les questions de la recherche suffisent
    outcome = ask(goods, proposal_set)
    completion = outcome.completion
    return AIClassification.objects.create(
        organization=org,
        proposal_set=proposal_set,
        goods_line=goods,
        status=outcome.status,
        trigger=trigger,
        provider=ai.provider_name() if outcome.status in ("sent", "failed") else "",
        model=(completion.model if completion else ai.model_name()) if outcome.status in ("sent", "failed") else "",
        free_tier=bool(settings.AI_FREE_TIER),
        chosen=outcome.chosen,
        reason=outcome.reason,
        evidence=outcome.evidence,
        rejected=outcome.rejected,
        sent_chars=outcome.sent_chars,
        input_tokens=completion.input_tokens if completion else None,
        output_tokens=completion.output_tokens if completion else None,
        cost_estimate=ai.estimate_cost(completion.input_tokens, completion.output_tokens) if completion else None,
        latency_ms=outcome.latency_ms,
        error_code=outcome.error_code,
        error_message=outcome.error_message,
        created_by=actor,
    )


def payload(choice: AIClassification | None) -> dict | None:
    if choice is None:
        return None
    chosen = choice.chosen
    return {
        "id": str(choice.id),
        "status": choice.status,
        "status_label": choice.get_status_display(),
        "proposal_id": str(chosen.id) if chosen else None,
        "node_id": str(chosen.node_id) if chosen else None,
        "code": chosen.code if chosen else None,
        "code_display": chosen.node.code_display if chosen else None,
        "label": chosen.node.label_clean if chosen else None,
        "insufficient": choice.status == AIClassification.Status.SENT and chosen is None and not choice.rejected,
        "reason": choice.reason,
        "evidence": choice.evidence,
        "rejected": choice.rejected,
        "model": choice.model,
        "free_tier": choice.free_tier,
        "error_message": choice.error_message,
        "created_at": choice.created_at,
    }
