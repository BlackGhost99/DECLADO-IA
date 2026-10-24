"""Moteur déterministe de sélection documentaire ; aucune règle juridique inventée."""

from dataclasses import dataclass
from datetime import date

SUPPORTED_FLAGS = {"requires_previous_regime", "requires_privileged_regime"}


@dataclass(frozen=True)
class CaseContext:
    country: str
    operation: str
    regime: str
    transport_mode: str
    declaration_date: date
    has_previous_regime: bool | None = None
    has_privileged_regime: bool | None = None


class UnresolvedRegulatoryCondition(Exception):
    """Contexte réglementaire insuffisant : impossible d'annoncer une conformité."""


def _matches(rule, context: CaseContext):
    if context.country not in {"GA", "CM", "CG", "TD", "CF", "GQ"}:
        raise UnresolvedRegulatoryCondition("Pays CEMAC manquant ou non pris en charge")
    if not context.declaration_date or not context.regime or not context.operation:
        raise UnresolvedRegulatoryCondition("Contexte douanier incomplet")
    if not rule.published or not rule.verified:
        return False
    source = rule.source
    if source.scope == "NATIONAL" and source.country_code != context.country:
        return False
    if source.scope not in {"CEMAC", "NATIONAL"}:
        raise UnresolvedRegulatoryCondition("Portée réglementaire inconnue")
    if not rule.valid_from or context.declaration_date < rule.valid_from:
        return False
    if rule.valid_until and context.declaration_date >= rule.valid_until:
        return False
    for attr in ("operation", "regime", "transport_mode"):
        wanted = getattr(rule, attr)
        actual = getattr(context, attr)
        if wanted and not actual:
            raise UnresolvedRegulatoryCondition(f"Critère obligatoire manquant : {attr}")
        if wanted and wanted != actual:
            return False
    conditions = rule.conditions or {}
    if set(conditions) - SUPPORTED_FLAGS:
        unknown = set(conditions) - SUPPORTED_FLAGS
        raise UnresolvedRegulatoryCondition(f"Conditions non prises en charge : {unknown}")
    checks = {
        "requires_previous_regime": context.has_previous_regime,
        "requires_privileged_regime": context.has_privileged_regime,
    }
    for key, expected in conditions.items():
        if checks[key] is None:
            raise UnresolvedRegulatoryCondition(f"Condition non renseignée : {key}")
        if checks[key] != expected:
            return False
    return True


def evaluate_requirements(context: CaseContext, regulatory_rules, company_policies=()):
    """Union additive des exigences légales et des politiques internes, sans effacement possible."""
    if (
        context.country not in {"GA", "CM", "CG", "TD", "CF", "GQ"}
        or not context.declaration_date
        or not context.regime
        or not context.operation
    ):
        raise UnresolvedRegulatoryCondition("Contexte douanier incomplet")
    by_code = {}
    for rule in regulatory_rules:
        if _matches(rule, context):
            key = rule.document_type.code
            entry = by_code.setdefault(key, {"document_type": key, "reasons": [], "stages": []})
            entry["reasons"].append(
                {
                    "kind": "regulation",
                    "source": rule.source.reference,
                    "article": rule.article,
                    "rule_id": str(rule.pk),
                }
            )
            if rule.stage not in entry["stages"]:
                entry["stages"].append(rule.stage)
    for policy in company_policies:
        if not policy.active:
            continue
        for field in ("operation", "regime", "transport_mode"):
            wanted = getattr(policy, field)
            actual = getattr(context, field)
            if wanted and not actual:
                raise UnresolvedRegulatoryCondition(f"Critère de politique manquant : {field}")
            if wanted and wanted != actual:
                break
        else:
            key = policy.document_type.code
            entry = by_code.setdefault(key, {"document_type": key, "reasons": [], "stages": []})
            entry["reasons"].append({"kind": "company", "policy_id": str(policy.pk)})
    return sorted(by_code.values(), key=lambda d: d["document_type"])
