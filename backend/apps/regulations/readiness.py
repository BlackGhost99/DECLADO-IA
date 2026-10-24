"""Fail-closed assessment: unknown legal scope cannot pass validation."""


def legal_coverage_gate(*, verified_sources: int, published_rules: int, coverage_certified: bool) -> dict:
    reasons = []
    if not verified_sources:
        reasons.append("Aucune source juridique vérifiée.")
    if not published_rules:
        reasons.append("Aucune obligation réglementaire publiée.")
    if not coverage_certified:
        reasons.append("Couverture des régimes et exceptions non certifiée.")
    return {"ready": not reasons, "blocking_reasons": reasons}
