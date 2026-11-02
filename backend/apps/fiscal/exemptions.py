"""Exonérations (TAX-04, T23) : déclarées par l'admin ClairTransit, demandées et prouvées dans le dossier.

Une exonération n'est jamais appliquée sur la seule demande de l'agent :
- le justificatif doit être joint au dossier et validé par un validateur ou un administrateur ;
- le champ d'application (code SH, régime douanier, période) est vérifié article par article.
Tant qu'une demande attend, le calcul reste provisoire et la soumission est bloquée. Hors champ,
l'exonération n'est pas appliquée et la raison est affichée. Rien n'est deviné ni inventé.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_event
from apps.core.exceptions import ApiError
from apps.organizations.models import Role

from . import rules
from .models import ExemptionClaim, ExemptionRegime, TaxAmendment

MAX_RATE = Decimal("100")
# Taxes qu'une exonération peut viser : celles calculées par article (pas la RI, calculée par SYDONIA).
EXEMPTABLE = tuple(r.code for r in rules.ARTICLE_TAXES)
OPEN = ExemptionClaim.Status.REQUESTED
NOT_FOUND = ("NOT_FOUND", "Demande d'exonération introuvable.", 404)


def _norm_regime(value: str) -> str:
    return "".join((value or "").upper().split())


def _require_manager(actor):
    if not getattr(actor, "is_reference_manager", False):
        raise ApiError("FORBIDDEN", "Seul l'admin ClairTransit déclare ou désactive une exonération.", 403)


def _rate(raw, tax: str) -> Decimal:
    try:
        rate = Decimal(str(raw).strip().replace(",", "."))
    except ArithmeticError:
        raise ApiError("VALIDATION_ERROR", f"Taux invalide pour {tax}.", 400, {"field": "taxes"}) from None
    if not rate.is_finite() or rate < 0 or rate > MAX_RATE or rate != rate.quantize(Decimal("0.0001")):
        raise ApiError("VALIDATION_ERROR", f"{tax} : taux entre 0 et 100 %, 4 décimales au plus.", 400,
                       {"field": "taxes"})  # fmt: skip
    return rate


def _date(raw, name: str, required: bool) -> date | None:
    if raw in (None, ""):
        if required:
            raise ApiError("VALIDATION_ERROR", "Date de début obligatoire.", 400, {"field": name})
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise ApiError("VALIDATION_ERROR", "Date invalide (AAAA-MM-JJ).", 400, {"field": name}) from None


def _text_list(raw, name: str) -> list[str]:
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        raw = raw.replace(";", "\n").replace(",", "\n").splitlines()
    if not isinstance(raw, list):
        raise ApiError("VALIDATION_ERROR", "Liste attendue.", 400, {"field": name})
    out = []
    for item in raw:
        text = str(item).strip()
        if text and text not in out:
            out.append(text[:200])
    return out


def regime_json(r: ExemptionRegime) -> dict:
    return {
        "id": str(r.id),
        "territory": r.territory,
        "code": r.code,
        "label": r.label,
        "conditions": r.conditions,
        "taxes": r.taxes,
        "hs_prefixes": r.hs_prefixes,
        "customs_regimes": r.customs_regimes,
        "required_documents": r.required_documents,
        "valid_from": r.valid_from.isoformat(),
        "valid_to": r.valid_to.isoformat() if r.valid_to else None,
        "source_kind": r.source_kind,
        "source_reference": r.source_reference,
        "official": r.source_kind != TaxAmendment.SourceKind.OPERATOR,
        "reason": r.reason,
        "is_active": r.is_active,
        "deactivated_at": r.deactivated_at,
        "deactivation_reason": r.deactivation_reason,
        "created_by": r.created_by.full_name or r.created_by.email,
        "created_at": r.created_at,
    }


@transaction.atomic
def create_regime(*, actor, data: dict, territory: str = "GA") -> ExemptionRegime:
    _require_manager(actor)
    code = (data.get("code") or "").strip()[:40]
    label = (data.get("label") or "").strip()[:200]
    if not code:
        raise ApiError("VALIDATION_ERROR", "Référence de l'exonération obligatoire.", 400, {"field": "code"})
    if not label:
        raise ApiError("VALIDATION_ERROR", "Libellé obligatoire.", 400, {"field": "label"})
    raw_taxes = data.get("taxes") or {}
    if not isinstance(raw_taxes, dict) or not raw_taxes:
        raise ApiError("VALIDATION_ERROR", "Indiquer au moins une taxe exonérée.", 400, {"field": "taxes"})
    taxes = {}
    for tax, raw in raw_taxes.items():
        tax = str(tax).strip().upper()
        if tax not in EXEMPTABLE:
            raise ApiError("VALIDATION_ERROR", f"Taxe « {tax} » non exonérable ici.", 400, {"field": "taxes"})
        taxes[tax] = format(_rate(raw, tax).normalize(), "f")
    prefixes = _text_list(data.get("hs_prefixes"), "hs_prefixes")
    for p in prefixes:
        if not p.isdigit() or not 2 <= len(p) <= 8:
            raise ApiError("VALIDATION_ERROR", f"Préfixe de code « {p} » : 2 à 8 chiffres.", 400,
                           {"field": "hs_prefixes"})  # fmt: skip
    regimes = [_norm_regime(r) for r in _text_list(data.get("customs_regimes"), "customs_regimes")]
    documents = _text_list(data.get("required_documents"), "required_documents")
    if not documents:
        raise ApiError("VALIDATION_ERROR", "Indiquer au moins un justificatif exigé.", 400,
                       {"field": "required_documents"})  # fmt: skip
    valid_from = _date(data.get("valid_from"), "valid_from", True)
    valid_to = _date(data.get("valid_to"), "valid_to", False)
    if valid_to and valid_to < valid_from:
        raise ApiError("VALIDATION_ERROR", "La fin précède le début.", 400, {"field": "valid_to"})
    source_kind = data.get("source_kind") or ""
    if source_kind not in TaxAmendment.SourceKind.values:
        raise ApiError("VALIDATION_ERROR", "Type de texte inconnu.", 400, {"field": "source_kind"})
    reference = (data.get("source_reference") or "").strip()[:300]
    if source_kind != TaxAmendment.SourceKind.OPERATOR and not reference:
        raise ApiError("VALIDATION_ERROR", "Référence du texte obligatoire.", 400, {"field": "source_reference"})
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise ApiError("REASON_REQUIRED", "Une justification est obligatoire.", 400, {"field": "reason"})
    if ExemptionRegime.objects.select_for_update().filter(territory=territory, code=code, is_active=True).exists():
        raise ApiError("DUPLICATE", "Une exonération active porte déjà cette référence : la désactiver d'abord.",
                       409, {"field": "code"})  # fmt: skip
    regime = ExemptionRegime.objects.create(
        territory=territory,
        code=code,
        label=label,
        conditions=(data.get("conditions") or "").strip(),
        taxes=taxes,
        hs_prefixes=prefixes,
        customs_regimes=regimes,
        required_documents=documents,
        valid_from=valid_from,
        valid_to=valid_to,
        source_kind=source_kind,
        source_reference=reference,
        reason=reason,
        created_by=actor,
    )
    record_event(
        organization=None,
        actor=actor,
        event_type="fiscal.exemption_created",
        entity=regime,
        current={k: v for k, v in regime_json(regime).items() if k not in {"created_at", "deactivated_at"}},
    )
    return regime


@transaction.atomic
def deactivate_regime(*, actor, regime_id, reason: str) -> ExemptionRegime:
    _require_manager(actor)
    regime = ExemptionRegime.objects.select_for_update().filter(pk=regime_id).first()
    if regime is None:
        raise ApiError("NOT_FOUND", "Exonération introuvable.", 404)
    if not regime.is_active:
        raise ApiError("INVALID_TRANSITION", "Exonération déjà désactivée.", 409)
    reason = (reason or "").strip()
    if not reason:
        raise ApiError("REASON_REQUIRED", "Le motif de la désactivation est obligatoire.", 400, {"field": "reason"})
    regime.is_active = False
    regime.deactivated_at = timezone.now()
    regime.deactivated_by = actor
    regime.deactivation_reason = reason
    regime.save(update_fields=["is_active", "deactivated_at", "deactivated_by", "deactivation_reason"])
    record_event(
        organization=None,
        actor=actor,
        event_type="fiscal.exemption_deactivated",
        entity=regime,
        previous={"is_active": True},
        current={"is_active": False, "reason": reason},
    )
    return regime


# --- Champ d'application et effet sur le calcul --------------------------------------------


def out_of_scope(regime: ExemptionRegime, *, hs_code: str, customs_regime: str, on: date) -> str:
    """Raison pour laquelle l'exonération ne s'applique pas à cet article ; vide si elle s'applique."""
    if on < regime.valid_from or (regime.valid_to and on > regime.valid_to):
        return f"Date du calcul ({on.isoformat()}) hors de la période de l'exonération."
    if regime.hs_prefixes:
        if not hs_code:
            return "Code SH non confirmé : champ d'application non vérifiable."
        if not any(hs_code.startswith(p) for p in regime.hs_prefixes):
            return f"Code {hs_code} hors des codes couverts ({', '.join(regime.hs_prefixes)})."
    if regime.customs_regimes:
        current = _norm_regime(customs_regime)
        if not current:
            return "Régime douanier non renseigné : champ d'application non vérifiable."
        if not any(current.startswith(r) for r in regime.customs_regimes):
            return f"Régime « {customs_regime} » non couvert ({', '.join(regime.customs_regimes)})."
    return ""


@dataclass
class ArticleExemption:
    rates: dict[str, Decimal] = field(default_factory=dict)
    applied: dict[str, dict] = field(default_factory=dict)  # taxe → exonération appliquée
    notes: list[str] = field(default_factory=list)
    pending: bool = False


def claims_for(revision) -> list[ExemptionClaim]:
    return list(
        revision.exemption_claims.exclude(status__in=[ExemptionClaim.Status.WITHDRAWN, ExemptionClaim.Status.REJECTED])
        .select_related("regime")
        .prefetch_related("goods_lines")
        .order_by("created_at")
    )


def for_article(claims: list[ExemptionClaim], goods_line, *, hs_code: str, customs_regime: str, on: date):
    out = ArticleExemption()
    for claim in claims:
        targets = {g.id for g in claim.goods_lines.all()}
        if targets and goods_line.id not in targets:
            continue
        regime = claim.regime
        name = f"{regime.code} ({regime.label})"
        if claim.status == OPEN:
            out.pending = True
            out.notes.append(f"Exonération {name} demandée : justificatif à valider, non appliquée.")
            continue
        why = out_of_scope(regime, hs_code=hs_code, customs_regime=customs_regime, on=on)
        if why:
            out.notes.append(f"Exonération {name} non appliquée : {why}")
            continue
        for tax, raw in regime.taxes.items():
            rate = Decimal(raw)
            if tax in out.rates and out.rates[tax] <= rate:
                continue  # deux exonérations : le taux le plus bas, celle qui l'emporte est affichée
            out.rates[tax] = rate
            out.applied[tax] = {
                "claim_id": str(claim.id),
                "code": regime.code,
                "label": regime.label,
                "rate": raw,
                "source_kind": regime.source_kind,
                "source_reference": regime.source_reference,
                "proof_reference": claim.proof_reference,
            }
    return out


def blocking_items(revision) -> list[dict]:
    """Demandes en attente : la soumission attend la validation du justificatif ou le retrait."""
    return [
        {
            "scope": "exemption",
            "id": str(c.id),
            "label": f"Exonération {c.regime.code}",
            "field": "proof",
            "message": "Exonération demandée : justificatif à valider par un validateur, ou demande à retirer.",
        }
        for c in revision.exemption_claims.filter(status=OPEN).select_related("regime")
    ]


# --- Demandes dans un dossier ---------------------------------------------------------------


def claim_json(c: ExemptionClaim) -> dict:
    return {
        "id": str(c.id),
        "regime": regime_json(c.regime),
        "status": c.status,
        "goods_line_ids": sorted(str(g.id) for g in c.goods_lines.all()),
        "proof_ids": sorted(str(d.id) for d in c.proofs.all()),
        "proof_reference": c.proof_reference,
        "note": c.note,
        "requested_by": c.requested_by.full_name or c.requested_by.email,
        "decided_by": (c.decided_by.full_name or c.decided_by.email) if c.decided_by else None,
        "decided_at": c.decided_at,
        "decision_reason": c.decision_reason,
        "created_at": c.created_at,
        "row_version": c.row_version,
    }


def _editable_revision(case_services, org, case_id):
    case = case_services.lock_case(org, case_id)
    revision = case.current_revision
    if not revision.is_editable:
        raise ApiError("REVISION_LOCKED", f"Révision « {revision.get_state_display()} » : non modifiable.", 409)
    return case, revision


def _targets(revision, data: dict):
    from apps.cases.models import CaseDocument, GoodsLine

    goods_ids = data.get("goods_line_ids") or []
    proof_ids = data.get("proof_ids") or []
    if not isinstance(goods_ids, list) or not isinstance(proof_ids, list):
        raise ApiError("VALIDATION_ERROR", "Listes d'identifiants attendues.", 400)
    goods = list(GoodsLine.objects.filter(revision=revision, pk__in=goods_ids)) if goods_ids else []
    if len(goods) != len(set(map(str, goods_ids))):
        raise ApiError("VALIDATION_ERROR", "Article absent de ce dossier.", 400, {"field": "goods_line_ids"})
    proofs = (
        list(CaseDocument.objects.filter(revision=revision, replaced_by__isnull=True, pk__in=proof_ids))
        if proof_ids
        else []
    )
    if len(proofs) != len(set(map(str, proof_ids))):
        raise ApiError("VALIDATION_ERROR", "Pièce absente de ce dossier.", 400, {"field": "proof_ids"})
    return goods, proofs


def _event(org, actor, kind, claim, case, previous=None, current=None):
    record_event(
        organization=org,
        actor=actor,
        event_type=f"exemption.{kind}",
        entity=claim,
        previous=previous,
        current=current,
        scope=case.scope,
    )


@transaction.atomic
def request_claim(*, org, actor, case_id, data: dict) -> ExemptionClaim:
    from apps.cases import services as case_services

    case, revision = _editable_revision(case_services, org, case_id)
    regime = ExemptionRegime.objects.filter(pk=data.get("regime_id"), is_active=True).first()
    if regime is None or regime.territory != revision.territory:
        raise ApiError("VALIDATION_ERROR", "Exonération inconnue ou désactivée.", 400, {"field": "regime_id"})
    if (
        revision.exemption_claims.filter(regime=regime)
        .exclude(status__in=[ExemptionClaim.Status.WITHDRAWN, ExemptionClaim.Status.REJECTED])
        .exists()
    ):
        raise ApiError("DUPLICATE", "Cette exonération est déjà demandée dans le dossier.", 409)
    goods, proofs = _targets(revision, data)
    claim = ExemptionClaim.objects.create(
        organization=org,
        revision=revision,
        regime=regime,
        proof_reference=(data.get("proof_reference") or "").strip()[:120],
        note=(data.get("note") or "").strip()[:2000],
        requested_by=actor,
    )
    claim.goods_lines.set(goods)
    claim.proofs.set(proofs)
    _event(org, actor, "requested", claim, case, None,
           {"regime": regime.code, "goods": len(goods), "proofs": len(proofs)})  # fmt: skip
    return claim


def _lock_claim(org, case_id, claim_id):
    from apps.cases import services as case_services

    case, revision = _editable_revision(case_services, org, case_id)
    claim = (
        ExemptionClaim.objects.for_organization(org).select_for_update().filter(pk=claim_id, revision=revision).first()
    )
    if claim is None:
        raise ApiError(*NOT_FOUND)
    return case, revision, claim


@transaction.atomic
def update_claim(*, org, actor, case_id, claim_id, expected, data: dict) -> ExemptionClaim:
    from apps.core.concurrency import bump, check_version

    case, revision, claim = _lock_claim(org, case_id, claim_id)
    check_version(claim, expected)
    if claim.status != OPEN:
        raise ApiError("INVALID_TRANSITION", "Seule une demande en attente se modifie.", 409)
    goods, proofs = _targets(revision, data)
    before = {"goods": claim.goods_lines.count(), "proofs": claim.proofs.count(), "reference": claim.proof_reference}
    claim.goods_lines.set(goods)
    claim.proofs.set(proofs)
    if "proof_reference" in data:
        claim.proof_reference = (data.get("proof_reference") or "").strip()[:120]
    if "note" in data:
        claim.note = (data.get("note") or "").strip()[:2000]
    bump(claim)
    claim.save()
    _event(org, actor, "updated", claim, case, before,
           {"goods": len(goods), "proofs": len(proofs), "reference": claim.proof_reference})  # fmt: skip
    return claim


@transaction.atomic
def decide_claim(*, org, actor, membership, case_id, claim_id, expected, decision: str, reason: str):
    from apps.core.concurrency import bump, check_version

    case, revision, claim = _lock_claim(org, case_id, claim_id)
    check_version(claim, expected)
    reason = (reason or "").strip()[:2000]
    if decision == "withdraw":
        if claim.status != OPEN:
            raise ApiError("INVALID_TRANSITION", "Seule une demande en attente se retire.", 409)
        status = ExemptionClaim.Status.WITHDRAWN
    else:
        if not membership.has_role(Role.VALIDATOR, Role.ORG_ADMIN):
            raise ApiError("FORBIDDEN", "Seul un validateur ou un administrateur de la société décide.", 403)
        if claim.status != OPEN:
            raise ApiError("INVALID_TRANSITION", "Cette demande est déjà décidée.", 409)
        if decision == "validate":
            if not claim.proofs.exists():
                raise ApiError("PROOF_REQUIRED", "Joindre le justificatif au dossier avant de le valider.", 409,
                               {"required_documents": claim.regime.required_documents})  # fmt: skip
            status = ExemptionClaim.Status.VALIDATED
        elif decision == "reject":
            if not reason:
                raise ApiError("REASON_REQUIRED", "Le motif du refus est obligatoire.", 400, {"field": "reason"})
            status = ExemptionClaim.Status.REJECTED
        else:
            raise ApiError("VALIDATION_ERROR", "Décision inconnue.", 400)
    claim.status = status
    claim.decided_by = actor
    claim.decided_at = timezone.now()
    claim.decision_reason = reason
    bump(claim)
    claim.save()
    _event(org, actor, status, claim, case, {"status": OPEN},
           {"status": status, "regime": claim.regime.code, **({"reason": reason} if reason else {})})  # fmt: skip
    return claim


def copy_claims(*, old_revision, new_revision, documents: dict, goods: dict) -> int:
    """Nouvelle révision (WF-04) : les demandes suivent, avec leurs pièces et articles copiés."""
    copied = 0
    for claim in old_revision.exemption_claims.exclude(status=ExemptionClaim.Status.WITHDRAWN):
        new = ExemptionClaim.objects.create(
            organization_id=claim.organization_id,
            revision=new_revision,
            regime_id=claim.regime_id,
            proof_reference=claim.proof_reference,
            note=claim.note,
            status=claim.status,
            requested_by_id=claim.requested_by_id,
            decided_by_id=claim.decided_by_id,
            decided_at=claim.decided_at,
            decision_reason=claim.decision_reason,
            copied_from=claim,
        )
        new.goods_lines.set([goods[g] for g in claim.goods_lines.values_list("id", flat=True) if g in goods])
        new.proofs.set([documents[d] for d in claim.proofs.values_list("id", flat=True) if d in documents])
        copied += 1
    return copied
