"""Calcul des taxes d'un dossier (TAX-02, TAX-06, TAX-07) : valeur en douane puis taxes par article.

Valeur d'un article = valeur des lignes de facture qui lui sont affectées, frais de facture
répartis au prorata, plus le fret et l'assurance des pièces quand l'incoterm ne les comprend
pas (répartis au prorata de la valeur). Tout ce qui manque rend le calcul provisoire ou
inconnu, jamais nul. « Validé » reste une validation interne, pas une liquidation des Douanes.
"""

from datetime import date
from decimal import Decimal

from apps.cases.models import CaseDocument, CaseRevision
from apps.cases.services import current_decision, decision_is_current
from apps.extraction.api import document_fields
from apps.extraction.models import ExtractionRun
from apps.extraction.numbers import parse_amount, parse_currency
from apps.extraction.services import invoice_totals

from . import engine, rules, services
from .models import TaxCode

# Parité fixe du franc CFA (BEAC) : seule conversion faite sans saisie d'un taux de change.
FIXED_RATES = {"XAF": Decimal("1"), "EUR": Decimal("655.957")}
NEEDS_FREIGHT = {"EXW", "FCA", "FAS", "FOB"}
NEEDS_INSURANCE = NEEDS_FREIGHT | {"CFR", "CPT"}
INCLUDES_BOTH = {"CIF", "CIP"}
ZERO = Decimal("0")
WARNING = (
    "Calcul de préparation selon le barème importé : il ne remplace pas la liquidation des Douanes. "
    "« Validé » signifie validé en interne."
)


def to_xaf(amount: Decimal | None, currency: str) -> Decimal | None:
    rate = FIXED_RATES.get((currency or "").upper())
    if amount is None or rate is None:
        return None
    return amount * rate


def _dec(value) -> Decimal | None:
    return Decimal(str(value)) if value not in (None, "") else None


def _fmt(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")).normalize(), "f")


def piece_amount(case_document: CaseDocument, field: str) -> dict:
    """Montant retenu sur une pièce de fret ou d'assurance : saisie de l'agent, sinon lecture."""
    run = (
        ExtractionRun.objects.filter(case_document=case_document, status=ExtractionRun.Status.SUCCEEDED)
        .order_by("-created_at")
        .first()
    )
    fields = {f["field"]: f for f in document_fields(run)} if run else {}

    def retained(name, parser):
        item = fields.get(name)
        if not item:
            return None
        if item["entered"]:
            return parser(item["entered"]["raw"]).value
        return item["parsed"] if item["status"] == "ok" else None

    amount = retained(field, parse_amount)
    currency = retained("currency", parse_currency) or ""
    amount = _dec(amount)
    return {
        "document_id": str(case_document.id),
        "title": case_document.document.original_name if case_document.document_id else "",
        "amount": amount,
        "currency": currency,
        "xaf": to_xaf(amount, currency),
    }


def _pieces(revision: CaseRevision, usage: str, field: str) -> list[dict]:
    docs = revision.documents.filter(usage=usage, replaced_by__isnull=True).select_related("document")
    return [piece_amount(d, field) for d in docs]


def _apportion(total: Decimal, weights: dict, eligible: set) -> dict:
    base = sum((weights[k] for k in eligible), ZERO)
    if not eligible or base == 0:
        return {}
    return {k: total * weights[k] / base for k in eligible}


def case_calculation(case) -> dict:
    revision = case.current_revision
    on = revision.planned_declaration_date or date.today()
    territory = revision.territory
    schedule = services.active_schedule(territory)
    reasons: list[str] = []

    invoices = {inv.id: inv for inv in revision.invoices.prefetch_related("lines")}
    factors: dict = {}
    for inv in invoices.values():
        comp = invoice_totals(inv)["components"]
        goods, fees, discounts = _dec(comp["goods"]), _dec(comp["fees"]), _dec(comp["discounts"])
        if goods and fees is not None and discounts is not None:
            factors[inv.id] = (goods + fees - discounts) / goods
        else:
            factors[inv.id] = Decimal("1")
            if fees is None or discounts is None:
                reasons.append(f"Facture {inv.invoice_number or inv.ordinal} : frais ou remises sans montant lu.")

    goods_lines = list(
        revision.goods_lines.order_by("ordinal").prefetch_related("sources__invoice_line__invoice", "decisions")
    )
    if not goods_lines:
        reasons.append("Aucune marchandise : créer les articles depuis les lignes de facture.")
    base_values: dict = {}
    line_notes: dict = {g.id: [] for g in goods_lines}
    needs_freight, needs_insurance = set(), set()
    for g in goods_lines:
        total = ZERO
        sources = list(g.sources.all())
        if not sources:
            base_values[g.id] = None
            line_notes[g.id].append("Aucune ligne de facture affectée.")
            continue
        for src in sources:
            inv = src.invoice_line.invoice
            xaf = to_xaf(src.assigned_value, inv.currency)
            if xaf is None:
                total = None
                note = (
                    "Valeur affectée inconnue."
                    if src.assigned_value is None
                    else f"Devise « {inv.currency or '?'} » : taux de change à saisir."
                )
                line_notes[g.id].append(note)
                break
            total += xaf * factors[inv.id]
            incoterm = (inv.incoterm or "").upper().split(" ")[0]
            if incoterm in NEEDS_FREIGHT:
                needs_freight.add(g.id)
            if incoterm in NEEDS_INSURANCE:
                needs_insurance.add(g.id)
            if not incoterm:
                line_notes[g.id].append("Incoterm inconnu : fret et assurance non ajoutés.")
            elif incoterm not in NEEDS_INSURANCE | INCLUDES_BOTH:
                line_notes[g.id].append(f"Incoterm {incoterm} : valeur à ajuster (frais après l'arrivée).")
        base_values[g.id] = total

    known_weights = {k: v for k, v in base_values.items() if v is not None}
    extras = {"freight": {}, "insurance": {}}
    pieces = {
        "freight": _pieces(revision, CaseDocument.Usage.FREIGHT, "freight_total"),
        "insurance": _pieces(revision, CaseDocument.Usage.INSURANCE, "premium_total"),
    }
    labels = {"freight": "fret", "insurance": "assurance"}
    for kind, eligible in (("freight", needs_freight), ("insurance", needs_insurance)):
        eligible = eligible & set(known_weights)
        if not eligible:
            continue
        found = pieces[kind]
        if not found:
            reasons.append(f"Pièce de {labels[kind]} absente : valeur provisoire sans {labels[kind]}.")
            continue
        if any(p["xaf"] is None for p in found):
            reasons.append(f"Montant ou devise de {labels[kind]} non lu : valeur provisoire sans {labels[kind]}.")
            continue
        extras[kind] = _apportion(sum((p["xaf"] for p in found), ZERO), known_weights, eligible)

    articles, out_articles = [], []
    for g in goods_lines:
        base = base_values[g.id]
        value = None if base is None else base + extras["freight"].get(g.id, ZERO) + extras["insurance"].get(g.id, ZERO)
        decision = current_decision(g)
        code, code_status = "", "missing"
        if decision and decision_is_current(decision, g):
            code, code_status = decision.selected_code, "confirmed"
        elif decision:
            code_status = "stale"
        resolution = services.rates_for(code, on=on, territory=territory) if code else None
        if resolution:
            rates = {k: r.rate for k, r in resolution.rates.items()}
            why = {k: r.note for k, r in resolution.rates.items() if r.note}
        else:
            rates = {}
            reason = "Code SH à reconfirmer." if code_status == "stale" else "Code SH non confirmé."
            why = {rule.code: reason for rule in rules.ARTICLE_TAXES}
        article = engine.compute_article(value, rates, why)
        articles.append(article)
        out_articles.append(
            {
                "goods_line_id": str(g.id),
                "ordinal": g.ordinal,
                "description": g.description,
                "hs_code": code,
                "code_status": code_status,
                "value": {
                    "xaf": _fmt(value),
                    "invoice": _fmt(base),
                    "freight": _fmt(extras["freight"].get(g.id)),
                    "insurance": _fmt(extras["insurance"].get(g.id)),
                    "notes": line_notes[g.id],
                },
                "cumulative_rate": _fmt(rules.cumulative_rate(rates)) if resolution else None,
                "taxes": [_tax_json(t, resolution) for t in article.amounts],
                "total": _fmt(article.total),
                "known_total": _fmt(article.known_total),
                "unknown": article.unknown,
            }
        )

    values = [base_values[g.id] for g in goods_lines]
    total_value = None
    if goods_lines and all(v is not None for v in values):
        total_value = sum(
            (base_values[g.id] + extras["freight"].get(g.id, ZERO) + extras["insurance"].get(g.id, ZERO))
            for g in goods_lines
        )
    global_resolution = services.rates_for("", on=on, territory=territory)
    global_taxes = engine.compute_global(total_value, {c: global_resolution.rates[c].rate for c in rules.GLOBAL_TAXES})
    totals = engine.declaration_total(articles, global_taxes)
    provisional = bool(reasons) or any(line_notes[g.id] for g in goods_lines)
    return {
        "warning": WARNING,
        "demo": revision.mode == CaseRevision.Mode.DEMO,
        "mode": revision.mode,
        "rules_version": rules.RULES_VERSION,
        "taxes_version": services.version_for(territory, on),
        "schedule": {"label": schedule.label, "source": schedule.source.title} if schedule else None,
        "date": on.isoformat(),
        "date_is_planned": revision.planned_declaration_date is not None,
        "currency_note": "1 EUR = 655,957 XAF (parité fixe). Autres devises : taux de change à saisir.",
        "provisional": provisional,
        "provisional_reasons": reasons,
        "pieces": {k: [_piece_json(p) for p in v] for k, v in pieces.items()},
        "articles": out_articles,
        "total_value": _fmt(total_value),
        "global_taxes": [_tax_json(t, global_resolution) for t in global_taxes],
        "totals": {
            "total": _fmt(totals["total"]),
            "known_total": _fmt(totals["known_total"]),
            "by_tax": {k: _fmt(v) for k, v in totals["by_tax"].items()},
        },
        "notes": {TaxCode.TCI: rules.NOTES[TaxCode.TCI]},
    }


def _tax_json(t: engine.TaxAmount, resolution) -> dict:
    rate = resolution.rates.get(t.code) if resolution else None
    return {
        "code": t.code,
        "base_kind": t.base_kind,
        "base": _fmt(t.base),
        "rate": services.pct(t.rate),
        "amount": _fmt(t.amount),
        "reason": t.reason,
        "rate_status": rate.status if rate else "unknown",
        "source": rate.source if rate else "none",
        "cell": rate.cell if rate else "",
        "amendment": rate.amendment if rate else None,
    }


def _piece_json(p: dict) -> dict:
    return {**p, "amount": _fmt(p["amount"]), "xaf": _fmt(p["xaf"])}
