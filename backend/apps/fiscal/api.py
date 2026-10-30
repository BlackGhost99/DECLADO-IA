"""API « Taxes et règles » : barème, taux d'un code, modifications (admin ClairTransit) et calcul d'un dossier."""

from datetime import date

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cases import workflow
from apps.cases.api import CanEdit, get_case
from apps.core.exceptions import ApiError

from . import calculation, rules, services
from .models import ScheduleLine, TaxAmendment, TaxCode

TAX_ORDER = [r.code for r in rules.ARTICLE_TAXES] + list(rules.GLOBAL_TAXES) + list(rules.EXPORT_ONLY)
REVIEW_KINDS = ("tec_difference", "empty_tax", "national_subposition", "duplicate", "not_in_reference")
FORMULA = (
    "DDI, TCI, CCI, OAD et CAF sur la valeur en douane ; DA sur valeur + DDI ; TVA et CSS sur valeur + DDI + DA. "
    "Chaque taxe est arrondie au franc supérieur."
)
PAGE = 200


def _date_param(request) -> date:
    raw = request.query_params.get("date")
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ApiError("VALIDATION_ERROR", "Date invalide (AAAA-MM-JJ).", 400) from None


def amendment_json(a: TaxAmendment) -> dict:
    return {
        "sequence": a.sequence,
        "tax": a.tax,
        "hs_code": a.hs_code,
        "national_code": a.national_code,
        "scope": "code" if a.hs_code else "all",
        "rate": services.pct(a.rate),
        "previous_rate": services.pct(a.previous_rate),
        "effective_from": a.effective_from,
        "source_kind": a.source_kind,
        "source_reference": a.source_reference,
        "reason": a.reason,
        "created_by": a.created_by.full_name or a.created_by.email,
        "created_at": a.created_at,
        "version": a.sequence + 1,
    }


def _schedule_json(schedule) -> dict | None:
    if schedule is None:
        return None
    return {
        "id": str(schedule.id),
        "label": schedule.label,
        "territory": schedule.territory,
        "source": schedule.source.title,
        "sheet": schedule.sheet,
        "reference_sheet": schedule.reference_sheet,
        "edition_id": str(schedule.edition_id) if schedule.edition_id else None,
        "imported_at": schedule.created_at,
        "counts": schedule.counts,
    }


class TaxesOverviewView(APIView):
    """TAX-01 : taxes, bases, taux du barème actif et historique des modifications."""

    def get(self, request):
        territory = "GA"
        schedule = services.active_schedule(territory)
        summary = services.schedule_summary(schedule) if schedule else {}
        general = services.applicable_amendments(territory, "", "", date.today())
        taxes = []
        for code in TAX_ORDER:
            rule = rules.RULES.get(code)
            stats = summary.get(code, {})
            amendment = general.get(code)
            if code in rules.EXPORT_ONLY:
                status = "export_only"
            elif code in rules.GLOBAL_TAXES:
                status = "set" if amendment else "to_confirm"
            else:
                status = "verified" if rule.verified else "from_schedule"
            taxes.append(
                {
                    "code": code,
                    "label": TaxCode(code).label,
                    "base_kind": rule.base if rule else rules.VALUE,
                    "scope": "declaration" if code in rules.GLOBAL_TAXES else "article",
                    "common_rate": services.pct(amendment.rate) if amendment else stats.get("common_rate"),
                    "distinct": stats.get("distinct", 0),
                    "empty": stats.get("empty", 0),
                    "values": stats.get("values", []),
                    "empty_means_none": bool(rule and rule.empty_means_none),
                    "status": status,
                    "amendment": amendment_json(amendment) if amendment else None,
                    "note": rules.NOTES.get(code, ""),
                }
            )
        history = TaxAmendment.objects.filter(territory=territory).select_related("created_by").order_by("-sequence")
        return Response(
            {
                "schedule": _schedule_json(schedule),
                "version": services.version_for(territory),
                "rules_version": rules.RULES_VERSION,
                "can_edit": bool(getattr(request.user, "is_reference_manager", False)),
                "formula": FORMULA,
                "taxes": taxes,
                "history": [amendment_json(a) for a in history[:50]],
                "review": (schedule.counts.get("review", {}) if schedule else {}),
            }
        )


def _line_json(line: ScheduleLine) -> dict:
    return {
        "hs_code": line.hs_code,
        "national_code": line.national_code,
        "label": line.label,
        "unit": line.unit,
        "row_number": line.row_number,
        "review": line.review,
        "reference": line.reference,
        "rates": {r.tax: r.raw_value for r in line.rates.all()},
    }


class ReviewListView(APIView):
    """Lignes du barème à revoir : écarts avec la feuille TEC, taxes vides, sous-positions nationales."""

    def get(self, request, kind):
        if kind not in REVIEW_KINDS:
            raise ApiError("NOT_FOUND", "Liste inconnue.", 404)
        schedule = services.active_schedule("GA")
        if schedule is None:
            return Response({"count": 0, "results": []})
        qs = ScheduleLine.objects.filter(schedule=schedule, review__contains=[kind]).prefetch_related("rates")
        try:
            page = max(1, int(request.query_params.get("page", "1")))
        except ValueError:
            page = 1
        lines = qs[(page - 1) * PAGE : page * PAGE]
        return Response({"count": qs.count(), "page": page, "results": [_line_json(ln) for ln in lines]})


class CodeRatesView(APIView):
    """TAX-01 / TAX-05 : taux applicables à un code à une date, preuve et historique."""

    def get(self, request):
        code = "".join(ch for ch in request.query_params.get("code", "") if ch.isdigit())
        if len(code) != 8:
            raise ApiError("VALIDATION_ERROR", "Code SH à 8 chiffres attendu.", 400, {"field": "code"})
        national = request.query_params.get("national", "").strip()
        on = _date_param(request)
        resolution = services.rates_for(code, national=national, on=on)
        rates = {k: r.rate for k, r in resolution.rates.items()}
        line = resolution.line or (resolution.lines[0] if resolution.lines else None)
        history = (
            TaxAmendment.objects.filter(territory="GA", hs_code__in=["", code])
            .select_related("created_by")
            .order_by("-sequence")
        )
        return Response(
            {
                "hs_code": code,
                "national_code": resolution.line.national_code if resolution.line else national,
                "label": line.label if line else "",
                "unit": line.unit if line else "",
                "row_number": resolution.line.row_number if resolution.line else None,
                "date": on,
                "version": resolution.version,
                "notes": resolution.notes,
                "rates": [resolution.rates[c].as_dict() for c in TAX_ORDER],
                "cumulative_rate": services.pct(rules.cumulative_rate(rates)),
                "review": resolution.line.review if resolution.line else [],
                "reference": resolution.line.reference if resolution.line else {},
                "subpositions": [
                    {
                        "national_code": ln.national_code,
                        "label": ln.label,
                        "row_number": ln.row_number,
                        "review": ln.review,
                    }
                    for ln in resolution.lines
                ],
                "history": [amendment_json(a) for a in history[:50]],
                "can_edit": bool(getattr(request.user, "is_reference_manager", False)),
            }
        )


class AmendmentListView(APIView):
    """TAX-04 : modifications de taux ; seule l'admin ClairTransit en enregistre."""

    def get(self, request):
        qs = TaxAmendment.objects.filter(territory="GA").select_related("created_by").order_by("-sequence")
        return Response({"results": [amendment_json(a) for a in qs[:200]]})

    def post(self, request):
        amendment = services.create_amendment(actor=request.user, data=request.data)
        return Response(amendment_json(amendment), status=201)


class CaseCalculationView(APIView):
    """TAX-02 / TAX-06 : calcul des taxes du dossier, borné à la société."""

    permission_classes = [CanEdit]

    def get(self, request, case_id):
        case = get_case(request, case_id)
        # Dossier validé : le calcul figé à la validation fait foi (WF-03), même si un taux change ensuite.
        decision = workflow.validated_decision(case.current_revision)
        if decision is not None:
            return Response({**decision.snapshot["calculation"], "frozen": True, "frozen_at": decision.created_at})
        return Response(calculation.case_calculation(case))
