"""Barème actif, taux applicables à une date et modifications de taux (TAX-01, TAX-04, TAX-05)."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from apps.audit.services import record_event
from apps.core.exceptions import ApiError

from . import rules
from .models import ScheduleLine, ScheduleRate, TaxAmendment, TaxCode, TaxSchedule

MAX_RATE = Decimal("100")


def pct(value: Decimal | None) -> str | None:
    """Taux affiché sans zéros de stockage : « 20 » et non « 20.0000 »."""
    return format(value.normalize(), "f") if value is not None else None


def active_schedule(territory: str = "GA") -> TaxSchedule | None:
    return TaxSchedule.objects.filter(territory=territory, is_active=True).select_related("source", "edition").first()


@transaction.atomic
def activate_schedule(*, schedule: TaxSchedule, actor=None) -> TaxSchedule:
    previous = TaxSchedule.objects.select_for_update().filter(territory=schedule.territory, is_active=True).first()
    if previous and previous.pk == schedule.pk:
        return schedule
    if previous:
        previous.is_active = False
        previous.save(update_fields=["is_active"])
    schedule.is_active = True
    schedule.save(update_fields=["is_active"])
    record_event(
        organization=None,
        actor=actor,
        event_type="fiscal.schedule_activated",
        entity=schedule,
        previous={"schedule": str(previous.pk)} if previous else None,
        current={"schedule": str(schedule.pk), "label": schedule.label, "counts": schedule.counts},
    )
    return schedule


def version_for(territory: str, on: date | None = None) -> int:
    """Version des taxes : 1 pour le barème importé, +1 par modification (applicable à la date)."""
    qs = TaxAmendment.objects.filter(territory=territory)
    if on is not None:
        qs = qs.filter(effective_from__lte=on)
    return 1 + qs.count()


@dataclass
class Rate:
    tax: str
    rate: Decimal | None
    status: str  # known, unknown, none (pas de taxe), export_only
    source: str = "schedule"  # schedule, amendment, none
    raw: str = ""
    cell: str = ""
    amendment: dict | None = None
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "tax": self.tax,
            "rate": pct(self.rate),
            "status": self.status,
            "source": self.source,
            "raw": self.raw,
            "cell": self.cell,
            "amendment": self.amendment,
            "note": self.note,
        }


@dataclass
class Resolution:
    hs_code: str
    national_code: str
    line: ScheduleLine | None
    lines: list[ScheduleLine]
    rates: dict[str, Rate]
    version: int
    notes: list[str] = field(default_factory=list)


def _amendment_dict(a: TaxAmendment) -> dict:
    return {
        "sequence": a.sequence,
        "effective_from": a.effective_from.isoformat(),
        "source_kind": a.source_kind,
        "source_reference": a.source_reference,
        "scope": "code" if a.hs_code else "all",
    }


def applicable_amendments(territory: str, hs_code: str, national: str, on: date) -> dict[str, TaxAmendment]:
    """Dernière modification en vigueur à la date, par taxe (propre au code ou pour tous les codes)."""
    qs = TaxAmendment.objects.filter(territory=territory, effective_from__lte=on).filter(
        Q(hs_code="") | Q(hs_code=hs_code, national_code="") | Q(hs_code=hs_code, national_code=national)
    )
    latest: dict[str, TaxAmendment] = {}
    for a in qs.order_by("sequence"):
        latest[a.tax] = a
    return latest


def rates_for(hs_code: str, *, national: str = "", on: date | None = None, territory: str = "GA") -> Resolution:
    on = on or date.today()
    schedule = active_schedule(territory)
    lines = (
        list(ScheduleLine.objects.filter(schedule=schedule, hs_code=hs_code).prefetch_related("rates"))
        if schedule
        else []
    )
    notes = []
    line = None
    if national:
        line = next((ln for ln in lines if ln.national_code == national), None)
    elif lines:
        line = next((ln for ln in lines if ln.national_code == "000"), None)
    schedule_rates: dict[str, ScheduleRate | None] = {}
    if line:
        schedule_rates = {r.tax: r for r in line.rates.all()}
    elif lines:
        # Pas de ligne « 000 » : un taux identique sur toutes les sous-positions vaut pour le code.
        by_tax: dict[str, list[ScheduleRate]] = {}
        for ln in lines:
            for r in ln.rates.all():
                by_tax.setdefault(r.tax, []).append(r)
        for tax, values in by_tax.items():
            distinct = {(v.rate, v.raw_value == "") for v in values}
            schedule_rates[tax] = values[0] if len(distinct) == 1 else None
        if any(v is None for v in schedule_rates.values()):
            notes.append("Sous-position nationale à préciser : les taux diffèrent selon la sous-position.")
    elif schedule:
        notes.append("Code absent du barème des taxes.")
    else:
        notes.append("Aucun barème des taxes n'est importé.")

    amendments = applicable_amendments(territory, hs_code, national or (line.national_code if line else ""), on)
    rates: dict[str, Rate] = {}
    for rule in rules.ARTICLE_TAXES:
        amendment = amendments.get(rule.code)
        cell = schedule_rates.get(rule.code)
        if amendment:
            rates[rule.code] = Rate(
                rule.code,
                amendment.rate,
                "known",
                "amendment",
                raw=cell.raw_value if cell else "",
                cell=cell.cell if cell else "",
                amendment=_amendment_dict(amendment),
            )
        elif cell is None:
            rates[rule.code] = Rate(rule.code, None, "unknown", "none", note=notes[0] if notes else "")
        elif cell.rate is None and rule.empty_means_none and not cell.raw_value:
            rates[rule.code] = Rate(rule.code, Decimal("0"), "none", cell=cell.cell, note="Pas de droit d'accise.")
        elif cell.rate is None:
            note = "Cellule vide : taux inconnu (≠ 0)." if not cell.raw_value else "Taux illisible."
            rates[rule.code] = Rate(rule.code, None, "unknown", raw=cell.raw_value, cell=cell.cell, note=note)
        else:
            rates[rule.code] = Rate(rule.code, cell.rate, "known", raw=cell.raw_value, cell=cell.cell)
    for code in rules.GLOBAL_TAXES:
        amendment = amendments.get(code)
        if amendment:
            rates[code] = Rate(code, amendment.rate, "known", "amendment", amendment=_amendment_dict(amendment))
        else:
            rates[code] = Rate(code, None, "unknown", "none", note=rules.NOTES[code])
    dso = schedule_rates.get(TaxCode.DSO)
    rates[TaxCode.DSO] = Rate(
        TaxCode.DSO,
        dso.rate if dso else None,
        "export_only",
        raw=dso.raw_value if dso else "",
        cell=dso.cell if dso else "",
        note=rules.NOTES[TaxCode.DSO],
    )
    return Resolution(hs_code, national, line, lines, rates, version_for(territory, on), notes)


def schedule_summary(schedule: TaxSchedule) -> dict[str, dict]:
    """Taux le plus courant de chaque taxe et nombre de valeurs distinctes (vue d'ensemble)."""
    out = {}
    counts: dict[str, Counter] = {}
    for tax, rate in ScheduleRate.objects.filter(line__schedule=schedule).values_list("tax", "rate"):
        counts.setdefault(tax, Counter())[format(rate.normalize(), "f") if rate is not None else ""] += 1
    for tax, counter in counts.items():
        filled = {k: v for k, v in counter.items() if k}
        common = max(filled.items(), key=lambda kv: kv[1])[0] if filled else None
        out[tax] = {
            "common_rate": common,
            "distinct": len(filled),
            "empty": counter.get("", 0),
            "values": sorted(filled.items(), key=lambda kv: -kv[1])[:6],
        }
    return out


@transaction.atomic
def create_amendment(*, actor, data: dict, territory: str = "GA") -> TaxAmendment:
    """TAX-04 : réservé à l'admin ClairTransit ; motivé, daté, sourcé ; le barème importé reste intact."""
    if not getattr(actor, "is_reference_manager", False):
        raise ApiError("FORBIDDEN", "Seul l'admin ClairTransit peut modifier un taux.", 403)
    tax = (data.get("tax") or "").strip().upper()
    if tax not in TaxCode.values or tax in rules.EXPORT_ONLY:
        raise ApiError("VALIDATION_ERROR", "Taxe inconnue.", 400, {"field": "tax"})
    if tax in rules.SYDONIA_TAXES:
        raise ApiError("VALIDATION_ERROR", "Taxe calculée par SYDONIA : aucun taux à saisir.", 400, {"field": "tax"})
    scope = data.get("scope") or "code"
    hs_code = "".join(ch for ch in (data.get("hs_code") or "") if ch.isdigit())
    national = (data.get("national_code") or "").strip()
    if tax in rules.GLOBAL_TAXES:
        scope = "all"
    if scope == "all":
        hs_code, national = "", ""
    elif len(hs_code) != 8:
        raise ApiError("VALIDATION_ERROR", "Code SH à 8 chiffres attendu.", 400, {"field": "hs_code"})
    if national and (len(national) != 3 or not national.isdigit()):
        raise ApiError("VALIDATION_ERROR", "Sous-position nationale à 3 chiffres.", 400, {"field": "national_code"})
    try:
        rate = Decimal(str(data.get("rate", "")).strip().replace(",", "."))
    except ArithmeticError:
        raise ApiError("VALIDATION_ERROR", "Taux invalide.", 400, {"field": "rate"}) from None
    if not rate.is_finite() or rate < 0 or rate > MAX_RATE or rate != rate.quantize(Decimal("0.0001")):
        raise ApiError("VALIDATION_ERROR", "Taux entre 0 et 100 %, 4 décimales au plus.", 400, {"field": "rate"})
    try:
        effective_from = date.fromisoformat(str(data.get("effective_from") or ""))
    except ValueError:
        raise ApiError("VALIDATION_ERROR", "Date d'effet invalide.", 400, {"field": "effective_from"}) from None
    source_kind = data.get("source_kind") or ""
    if source_kind not in TaxAmendment.SourceKind.values:
        raise ApiError("VALIDATION_ERROR", "Type de texte inconnu.", 400, {"field": "source_kind"})
    reference = (data.get("source_reference") or "").strip()
    if source_kind != TaxAmendment.SourceKind.OPERATOR and not reference:
        raise ApiError("VALIDATION_ERROR", "Référence du texte obligatoire.", 400, {"field": "source_reference"})
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise ApiError("REASON_REQUIRED", "Une justification est obligatoire.", 400, {"field": "reason"})
    if scope == "code":
        schedule = active_schedule(territory)
        lines = ScheduleLine.objects.filter(schedule=schedule, hs_code=hs_code) if schedule else None
        if not lines or not lines.exists():
            raise ApiError("UNKNOWN_CODE", "Code absent du barème des taxes.", 400, {"field": "hs_code"})
        if national and not lines.filter(national_code=national).exists():
            raise ApiError("UNKNOWN_CODE", "Sous-position absente du barème.", 400, {"field": "national_code"})

    previous = rates_for(hs_code, national=national, on=effective_from, territory=territory).rates.get(tax)
    # Verrou sur les modifications existantes ; la contrainte d'unicité couvre la toute première.
    last = max(
        TaxAmendment.objects.select_for_update().filter(territory=territory).values_list("sequence", flat=True),
        default=0,
    )
    amendment = TaxAmendment.objects.create(
        territory=territory,
        sequence=last + 1,
        tax=tax,
        hs_code=hs_code,
        national_code=national,
        rate=rate,
        previous_rate=previous.rate if previous and scope == "code" else None,
        effective_from=effective_from,
        source_kind=source_kind,
        source_reference=reference[:300],
        reason=reason,
        created_by=actor,
    )
    record_event(
        organization=None,
        actor=actor,
        event_type="fiscal.rate_amended",
        entity=amendment,
        previous={"rate": pct(amendment.previous_rate)},
        current={
            "tax": tax,
            "hs_code": hs_code,
            "national_code": national,
            "rate": pct(rate),
            "effective_from": effective_from.isoformat(),
            "source_kind": source_kind,
            "source_reference": reference,
            "reason": reason,
            "version": version_for(territory),
        },
    )
    return amendment
