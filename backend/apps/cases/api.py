import re
from decimal import Decimal

from django.conf import settings
from django.db.models import Prefetch, Q
from django.http import FileResponse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.core.concurrency import expected_version
from apps.core.exceptions import ApiError
from apps.documents import services as documents
from apps.documents.models import Document
from apps.documents.sniff import JPEG, PDF, PNG, XLSX
from apps.documents.storage import get_storage
from apps.extraction import services as extraction
from apps.extraction.codes import FINDING_MESSAGES
from apps.extraction.models import FieldObservation
from apps.fiscal.calculation import FIXED_RATES
from apps.organizations.models import Role
from apps.organizations.permissions import HasActiveOrganization, require_roles
from apps.regulations.doc_types import mismatch_of, type_of
from apps.tariffs.api import HISTORICAL_WARNING

from . import completeness, proposals, services
from .models import (
    CaseDocument,
    CaseRevision,
    CodeObservation,
    CustomsCase,
    GoodsLine,
    Invoice,
    InvoiceLine,
)

# Lecture : tout membre actif. Écriture : déclarant ou validateur.
CanEdit = require_roles(Role.DECLARANT, Role.VALIDATOR, safe_methods_open=True)


def dec(value):
    """Décimal transmis en chaîne, sans zéros de remplissage du stockage (100.00000000 → "100")."""
    return None if value is None else format(value.normalize(), "f")


def user_brief(user):
    return None if user is None else {"id": str(user.id), "email": user.email, "full_name": user.full_name}


# --- Représentations ------------------------------------------------------------------


def document_payload(doc: Document) -> dict:
    return {
        "id": str(doc.id),
        "original_name": doc.original_name,
        "mime": doc.mime,
        "type_label": doc.type_label,
        "bytes": doc.bytes,
        "sha256": doc.sha256,
        "version": doc.version,
        "supersedes_id": str(doc.supersedes_id) if doc.supersedes_id else None,
        "readability": doc.readability,
        "readability_label": doc.get_readability_display(),
        "inspection_notes": doc.inspection_notes,
        "detected_locale": doc.detected_locale,
        "language_detection": doc.language_detection,
        "previewable": doc.previewable,
        "uploaded_by": user_brief(doc.uploaded_by),
        "created_at": doc.created_at,
    }


def case_document_payload(link: CaseDocument) -> dict:
    return {
        "id": str(link.id),
        "usage": link.usage,
        "usage_label": link.get_usage_display(),
        "added_by": user_brief(link.added_by),
        "created_at": link.created_at,
        "replaced_by_id": str(link.replaced_by_id) if link.replaced_by_id else None,
        "row_version": link.row_version,
        "document": document_payload(link.document),
        "document_type": type_of(link),
        "type_mismatch": mismatch_of(link),
        "latest_extraction": _latest_extraction(link),
    }


def _latest_extraction(link: CaseDocument) -> dict | None:
    from apps.extraction.api import run_summary

    run = link.extraction_runs.select_related("job", "created_by").order_by("-created_at").first()
    return run_summary(run) if run else None


def observation_payload(obs: CodeObservation) -> dict:
    return {
        "id": str(obs.id),
        "field_label": obs.field_label,
        "raw_code": obs.raw_code,
        "normalized_code": obs.normalized_code,
        "code_kind": obs.code_kind,
        "code_kind_label": obs.get_code_kind_display(),
        "entry_origin": obs.entry_origin,
        "evidence_document_id": str(obs.evidence_document_id) if obs.evidence_document_id else None,
        "evidence_page": obs.evidence_page,
        "source_span": obs.source_span.as_dict() if obs.source_span_id else None,
        "findings": [{"code": f, "message": FINDING_MESSAGES.get(f, f)} for f in obs.findings],
        "created_by": obs.created_by.email,
        "created_at": obs.created_at,
        "superseded_at": obs.superseded_at,
    }


def line_payload(line: InvoiceLine) -> dict:
    observations = list(line.code_observations.all())
    sources = list(line.goods_sources.all())
    return {
        "id": str(line.id),
        "ordinal": line.ordinal,
        "source_reference": line.source_reference,
        "description_raw": line.description_raw,
        "quantity": dec(line.quantity),
        "unit": line.unit,
        "unit_price": dec(line.unit_price),
        "amount": dec(line.amount),
        "origin_country": line.origin_country,
        "entry_origin": line.entry_origin,
        "entry_origin_label": line.get_entry_origin_display(),
        "evidence_document_id": str(line.evidence_document_id) if line.evidence_document_id else None,
        "evidence_page": line.evidence_page,
        "evidence_note": line.evidence_note,
        "row_version": line.row_version,
        "codes": [observation_payload(o) for o in observations if o.superseded_at is None],
        "code_history": [observation_payload(o) for o in observations if o.superseded_at is not None],
        "goods_line_ids": [str(s.goods_line_id) for s in sources],
        "extraction_key": line.extraction_key or None,
        "field_origins": line.field_origins,
        "review_flags": line.review_flags,
        "field_sources": extraction.field_sources(
            FieldObservation.objects.filter(invoice_line_id__in=extraction.lineage(line)).select_related("source_span")
            if line.extraction_key
            else []
        ),
        "corrections": [correction_payload(c) for c in line.corrections.select_related("actor")],
    }


def correction_payload(c) -> dict:
    return {
        "id": str(c.id),
        "field": c.field_name,
        "previous": c.previous,
        "current": c.current,
        "reason": c.reason,
        "actor": c.actor.email,
        "at": c.created_at,
    }


def divergence_payload(d) -> dict:
    return {
        "id": str(d.id),
        "kind": d.kind,
        "kind_label": d.get_kind_display(),
        "invoice_line_id": str(d.invoice_line_id) if d.invoice_line_id else None,
        "line_ordinal": d.invoice_line.ordinal if d.invoice_line_id else None,
        "field": d.field_name,
        "current_value": d.current_value,
        "extracted_value": d.extracted_value,
        "run_id": str(d.run_id),
        "state": d.state,
        "state_label": d.get_state_display(),
        "resolved_by": d.resolved_by.email if d.resolved_by_id else None,
        "resolved_at": d.resolved_at,
        "resolution_reason": d.resolution_reason,
        "span": d.observation.source_span.as_dict() if d.observation_id and d.observation.source_span_id else None,
    }


def invoice_payload(inv: Invoice) -> dict:
    return {
        "id": str(inv.id),
        "ordinal": inv.ordinal,
        "supplier_name": inv.supplier_name,
        "buyer_name": inv.buyer_name,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "currency": inv.currency,
        "incoterm": inv.incoterm,
        "declared_total": dec(inv.declared_total),
        "document_id": str(inv.document_id) if inv.document_id else None,
        "row_version": inv.row_version,
        "lines": [line_payload(ln) for ln in inv.lines.all()],
        "field_origins": inv.field_origins,
        "review_flags": inv.review_flags,
        "field_sources": extraction.field_sources(
            FieldObservation.objects.filter(
                invoice_id__in=extraction.lineage(inv), invoice_line__isnull=True
            ).select_related("source_span")
        ),
        "divergences": [
            divergence_payload(d)
            for d in inv.divergences.select_related("invoice_line", "resolved_by", "observation__source_span")
        ],
        "totals_check": extraction.invoice_totals(inv),
        "latest_extraction_id": str(run.id) if (run := extraction.latest_run_for_invoice(inv)) else None,
    }


def decision_payload(decision, goods) -> dict | None:
    if decision is None:
        return None
    return {
        "id": str(decision.id),
        "action": decision.action,
        "action_label": decision.get_action_display(),
        "selected_code": decision.selected_code,
        "selected_code_display": decision.selected_node.code_display,
        "label": decision.selected_node.label_clean,
        "edition": {"id": str(decision.edition_id), "label": decision.edition.label},
        "reason": decision.reason,
        "evidence_refs": decision.evidence_refs,
        "actor": user_brief(decision.actor),
        "at": decision.created_at,
        "is_current": services.decision_is_current(decision, goods),
        "note": "Décision interne de préparation : ni validation du dossier, ni acceptation douanière.",
    }


def goods_payload(goods: GoodsLine) -> dict:
    check = services.latest_check(goods)
    return {
        "id": str(goods.id),
        "ordinal": goods.ordinal,
        "description": goods.description,
        "attributes": goods.attributes,
        "origin_country": goods.origin_country,
        "regime": goods.regime,
        "valuation_status": goods.valuation_status,
        "row_version": goods.row_version,
        "sources": [
            {
                "invoice_line_id": str(s.invoice_line_id),
                "invoice_ordinal": s.invoice_line.invoice.ordinal,
                "line_ordinal": s.invoice_line.ordinal,
                "assigned_quantity": dec(s.assigned_quantity),
                "assigned_value": dec(s.assigned_value),
            }
            for s in goods.sources.select_related("invoice_line__invoice")
        ],
        "latest_check": services.check_payload(check, goods, goods.revision) if check else None,
        "decision": decision_payload(services.current_decision(goods), goods),
        "decision_count": goods.decisions.count(),
    }


def revision_payload(revision: CaseRevision) -> dict:
    edition = revision.target_edition
    invoices = revision.invoices.prefetch_related(
        Prefetch(
            "lines",
            queryset=InvoiceLine.objects.prefetch_related(
                Prefetch("code_observations", queryset=CodeObservation.objects.select_related("created_by")),
                "goods_sources",
            ),
        )
    )
    return {
        "id": str(revision.id),
        "revision_no": revision.revision_no,
        "state": revision.state,
        "state_label": revision.get_state_display(),
        "mode": revision.mode,
        "mode_label": revision.get_mode_display(),
        "territory": revision.territory,
        "planned_declaration_date": revision.planned_declaration_date,
        "regime": revision.regime,
        "client_reference": revision.client_reference,
        "transport_mode": revision.transport_mode,
        "transport_mode_label": revision.get_transport_mode_display() if revision.transport_mode else "",
        "entry_office": revision.entry_office,
        "origin_country": revision.origin_country,
        "provenance_country": revision.provenance_country,
        "prefilled": revision.prefilled,
        "exchange_rates": revision.exchange_rates,
        "priority": revision.priority,
        "priority_label": revision.get_priority_display(),
        "is_editable": revision.is_editable,
        "decisions": [
            {
                "kind": d.kind,
                "kind_label": d.get_kind_display(),
                "actor": user_brief(d.actor),
                "reason": d.reason,
                "created_at": d.created_at,
                "calculated": ((d.snapshot.get("calculation") or {}).get("totals") or {}).get("total") is not None,
            }
            for d in revision.decisions.select_related("actor")
        ],
        "export_count": revision.exports.count(),
        "row_version": revision.row_version,
        "target_edition": None
        if edition is None
        else {
            "id": str(edition.id),
            "label": edition.label,
            "publication_state": edition.publication_state,
            "warning": None if edition.publication_state == "operational" else HISTORICAL_WARNING,
        },
        "documents": [
            case_document_payload(link)
            for link in revision.documents.select_related("document__uploaded_by", "added_by").order_by("created_at")
        ],
        "invoices": [invoice_payload(inv) for inv in invoices],
        "goods_lines": [goods_payload(g) for g in revision.goods_lines.select_related("revision")],
        "completeness": completeness.evaluate(revision),
        "status_note": "« Validé en interne » ne vaudra jamais acceptation par la douane.",
    }


def case_payload(case: CustomsCase, *, detail=False) -> dict:
    revision = case.current_revision
    body = {
        "id": str(case.id),
        "reference": case.reference,
        "title": case.title,
        "importer": None if case.importer is None else {"id": str(case.importer.id), "name": case.importer.name},
        "assigned_to": user_brief(case.assigned_to),
        "created_by": user_brief(case.created_by),
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "row_version": case.row_version,
        "state": revision.state,
        "state_label": revision.get_state_display(),
        "mode": revision.mode,
        "revision_no": revision.revision_no,
    }
    if detail:
        body["revision"] = revision_payload(revision)
        body["revisions"] = [
            {"revision_no": r.revision_no, "state": r.state, "created_at": r.created_at} for r in case.revisions.all()
        ]
    return body


# --- Entrées --------------------------------------------------------------------------

AMOUNT = {"max_digits": 24, "decimal_places": 8, "allow_null": True, "required": False}


class CaseInput(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, max_length=200)
    importer_id = serializers.UUIDField(required=False, allow_null=True)
    assigned_to_id = serializers.UUIDField(required=False, allow_null=True)
    planned_declaration_date = serializers.DateField(required=False, allow_null=True)
    regime = serializers.CharField(required=False, allow_blank=True, max_length=60)
    territory = serializers.CharField(required=False, max_length=10)
    target_edition_id = serializers.UUIDField(required=False, allow_null=True)
    client_reference = serializers.CharField(required=False, allow_blank=True, max_length=60)
    transport_mode = serializers.ChoiceField(
        choices=CaseRevision.TransportMode.choices, required=False, allow_blank=True
    )
    entry_office = serializers.CharField(required=False, allow_blank=True, max_length=120)
    origin_country = serializers.RegexField(r"^[A-Za-z]{2}$|^$", required=False, allow_blank=True)
    provenance_country = serializers.RegexField(r"^[A-Za-z]{2}$|^$", required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=CaseRevision.Priority.choices, required=False)


class ExchangeRateInput(serializers.Serializer):
    rate = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0.000001"))
    source = serializers.CharField(required=False, allow_blank=True, max_length=200)


class RevisionInput(serializers.Serializer):
    planned_declaration_date = serializers.DateField(required=False, allow_null=True)
    regime = serializers.CharField(required=False, allow_blank=True, max_length=60)
    territory = serializers.CharField(required=False, max_length=10)
    target_edition_id = serializers.UUIDField(required=False, allow_null=True)
    client_reference = serializers.CharField(required=False, allow_blank=True, max_length=60)
    transport_mode = serializers.ChoiceField(
        choices=CaseRevision.TransportMode.choices, required=False, allow_blank=True
    )
    entry_office = serializers.CharField(required=False, allow_blank=True, max_length=120)
    origin_country = serializers.RegexField(r"^[A-Za-z]{2}$|^$", required=False, allow_blank=True)
    provenance_country = serializers.RegexField(r"^[A-Za-z]{2}$|^$", required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=CaseRevision.Priority.choices, required=False)
    # Devise → taux saisi ; une devise absente du dictionnaire envoyé est retirée.
    exchange_rates = serializers.DictField(child=ExchangeRateInput(), required=False)

    def validate_exchange_rates(self, value):
        for currency in value:
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise serializers.ValidationError(f"Devise « {currency} » : code ISO à trois lettres majuscules.")
            if currency in FIXED_RATES:
                raise serializers.ValidationError(f"{currency} : parité fixe, aucun taux à saisir.")
        return value


class InvoiceInput(serializers.Serializer):
    supplier_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    buyer_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    invoice_number = serializers.CharField(required=False, allow_blank=True, max_length=100)
    invoice_date = serializers.DateField(required=False, allow_null=True)
    currency = serializers.RegexField(r"^[A-Za-z]{3}$|^$", required=False, allow_blank=True)
    incoterm = serializers.CharField(required=False, allow_blank=True, max_length=20)
    declared_total = serializers.DecimalField(**AMOUNT)
    document_id = serializers.UUIDField(required=False, allow_null=True)
    correction_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class LineInput(serializers.Serializer):
    source_reference = serializers.CharField(required=False, allow_blank=True, max_length=100)
    description_raw = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.DecimalField(**AMOUNT)
    unit = serializers.CharField(required=False, allow_blank=True, max_length=20)
    unit_price = serializers.DecimalField(**AMOUNT)
    amount = serializers.DecimalField(**AMOUNT)
    origin_country = serializers.RegexField(r"^[A-Za-z]{2}$|^$", required=False, allow_blank=True)
    evidence_document_id = serializers.UUIDField(required=False, allow_null=True)
    evidence_page = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    evidence_note = serializers.CharField(required=False, allow_blank=True, max_length=300)
    # Codes : texte, jamais nombre ; le libellé du champ source est conservé (EXT-04).
    customs_code = serializers.CharField(required=False, allow_blank=True, max_length=60, trim_whitespace=True)
    customs_code_label = serializers.CharField(required=False, allow_blank=True, max_length=100)
    claimed_scheme = serializers.CharField(required=False, allow_blank=True, max_length=60)
    uncertain_code = serializers.CharField(required=False, allow_blank=True, max_length=60)
    uncertain_code_label = serializers.CharField(required=False, allow_blank=True, max_length=100)
    correction_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def to_internal_value(self, data):
        for key in ("customs_code", "uncertain_code", "source_reference"):
            if key in data and not isinstance(data[key], str) and data[key] is not None:
                raise serializers.ValidationError({key: "Saisir le code en texte (les zéros initiaux comptent)."})
        return super().to_internal_value(data)


class GoodsInput(serializers.Serializer):
    invoice_line_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    attributes = serializers.DictField(required=False)
    origin_country = serializers.RegexField(r"^[A-Za-z]{2}$|^$", required=False, allow_blank=True)
    regime = serializers.CharField(required=False, allow_blank=True, max_length=60)


class DecisionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["confirm", "complete", "replace", "classify"])
    code_check_id = serializers.UUIDField()
    node_id = serializers.UUIDField(required=False, allow_null=True)
    proposal_id = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField()
    evidence_refs = serializers.ListField(required=False)
    goods_line_version = serializers.IntegerField()


class CaseFilter(serializers.Serializer):
    state = serializers.ChoiceField(choices=CaseRevision.State.choices, required=False)
    assigned_to = serializers.RegexField(r"^(none|[0-9a-fA-F-]{36})$", required=False)
    importer = serializers.UUIDField(required=False)
    created_from = serializers.DateField(required=False)
    created_to = serializers.DateField(required=False)
    q = serializers.CharField(required=False, max_length=100)


def valid_query(serializer_class, request):
    s = serializer_class(data=request.query_params)
    if not s.is_valid():
        raise ApiError("INVALID_FILTER", "Filtre invalide.", 400, s.errors)
    return s.validated_data


def valid(serializer_class, request, partial=False):
    s = serializer_class(data=request.data, partial=partial)
    s.is_valid(raise_exception=True)
    return s.validated_data


# --- Vues -----------------------------------------------------------------------------


def cases_qs(request):
    return CustomsCase.objects.for_organization(request.organization).select_related(
        "importer", "assigned_to", "created_by", "current_revision__target_edition"
    )


def get_case(request, case_id) -> CustomsCase:
    case = cases_qs(request).filter(pk=case_id).first()
    if case is None:
        raise ApiError(*services.NOT_FOUND)
    return case


class CaseListView(APIView):
    permission_classes = [CanEdit]

    def get(self, request):
        p = valid_query(CaseFilter, request)
        qs = cases_qs(request)
        if p.get("state"):
            qs = qs.filter(current_revision__state=p["state"])
        if p.get("assigned_to"):
            qs = (
                qs.filter(assigned_to=None)
                if p["assigned_to"] == "none"
                else qs.filter(assigned_to_id=p["assigned_to"])
            )
        if p.get("importer"):
            qs = qs.filter(importer_id=p["importer"])
        if p.get("created_from"):
            qs = qs.filter(created_at__date__gte=p["created_from"])
        if p.get("created_to"):
            qs = qs.filter(created_at__date__lte=p["created_to"])
        if p.get("q"):
            qs = qs.filter(Q(reference__icontains=p["q"]) | Q(title__icontains=p["q"]))
        results = [case_payload(c) for c in qs.order_by("-created_at")[:200]]
        return Response({"results": results, "states": CaseRevision.State.choices})

    def post(self, request):
        case = services.create_case(org=request.organization, actor=request.user, data=valid(CaseInput, request))
        return Response(case_payload(get_case(request, case.id), detail=True), status=201)


class CaseDetailView(APIView):
    permission_classes = [CanEdit]

    def get(self, request, case_id):
        return Response(case_payload(get_case(request, case_id), detail=True))

    def patch(self, request, case_id):
        data = valid(CaseInput, request, partial=True)
        data = {k: v for k, v in data.items() if k in ("title", "importer_id")}
        services.update_case(
            org=request.organization, actor=request.user, case_id=case_id, expected=expected_version(request), data=data
        )
        return Response(case_payload(get_case(request, case_id), detail=True))


class CaseAssignView(APIView):
    permission_classes = [CanEdit]

    def post(self, request, case_id):
        assignee = request.data.get("assignee_id")
        services.assign_case(
            org=request.organization,
            actor=request.user,
            membership=request.membership,
            case_id=case_id,
            expected=expected_version(request),
            assignee_id=assignee,
        )
        return Response(case_payload(get_case(request, case_id)))


CanDecide = require_roles(Role.DECLARANT, Role.VALIDATOR, Role.ORG_ADMIN)


class CaseWorkflowView(APIView):
    """WF-01 à WF-03 : soumettre, retourner pour correction (motif) ou valider en interne."""

    permission_classes = [CanDecide]

    def post(self, request, case_id, action):
        from . import workflow

        get_case(request, case_id)  # 404 hors de la société, avant tout verrou
        common = {"org": request.organization, "actor": request.user, "case_id": case_id,
                  "expected": expected_version(request)}  # fmt: skip
        reason = str(request.data.get("reason", ""))[:2000]
        if action == "submit":
            workflow.submit(**common)
        elif action == "return":
            workflow.return_for_correction(**common, membership=request.membership, reason=reason)
        elif action == "validate":
            workflow.validate(**common, membership=request.membership, reason=reason)
        else:
            raise ApiError(*services.NOT_FOUND)
        return Response(case_payload(get_case(request, case_id), detail=True))


CanExport = require_roles(Role.DECLARANT, Role.VALIDATOR, Role.ORG_ADMIN, safe_methods_open=True)


class CaseExportsView(APIView):
    """EXP-01 à EXP-03 : exports de toutes les révisions du dossier ; POST génère celui de la courante."""

    permission_classes = [CanExport]

    def get(self, request, case_id):
        from . import exports
        from .models import CaseExport

        case = get_case(request, case_id)
        rows = (
            CaseExport.objects.for_organization(request.organization)
            .filter(revision__case=case)
            .select_related("revision", "created_by")
        )
        return Response({"results": [exports.export_payload(e) for e in rows]})

    def post(self, request, case_id):
        from . import exports

        get_case(request, case_id)
        export = exports.create_export(
            org=request.organization, actor=request.user, case_id=case_id, fmt=str(request.data.get("format", ""))
        )
        return Response(exports.export_payload(export), status=201)


class CaseExportFileView(APIView):
    """Octets d'un export conservé, bornés à la société."""

    permission_classes = [CanExport]

    def get(self, request, case_id, export_id):
        from .models import CaseExport

        case = get_case(request, case_id)
        export = (
            CaseExport.objects.for_organization(request.organization).filter(pk=export_id, revision__case=case).first()
        )
        if export is None:
            raise ApiError(*services.NOT_FOUND)
        mime = XLSX if export.format == CaseExport.Format.XLSX else "application/pdf"
        response = FileResponse(
            get_storage().open(export.object_key), content_type=mime, as_attachment=True, filename=export.filename
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class CaseRevisionsView(APIView):
    """WF-04 : nouvelle révision d'un dossier validé, avec un motif ; l'ancienne reste consultable."""

    permission_classes = [CanDecide]

    def post(self, request, case_id):
        get_case(request, case_id)  # 404 hors de la société, avant tout verrou
        services.create_revision(
            org=request.organization,
            actor=request.user,
            case_id=case_id,
            reason=str(request.data.get("reason", ""))[:2000],
        )
        return Response(case_payload(get_case(request, case_id), detail=True), status=201)


def get_revision(request, revision_id) -> CaseRevision:
    revision = (
        CaseRevision.objects.for_organization(request.organization)
        .select_related("case", "target_edition")
        .filter(pk=revision_id)
        .first()
    )
    if revision is None:
        raise ApiError(*services.NOT_FOUND)
    return revision


class RevisionDetailView(APIView):
    permission_classes = [CanEdit]

    def get(self, request, revision_id):
        return Response(revision_payload(get_revision(request, revision_id)))

    def patch(self, request, revision_id):
        services.update_revision(
            org=request.organization,
            actor=request.user,
            revision_id=revision_id,
            expected=expected_version(request),
            data=valid(RevisionInput, request, partial=True),
        )
        return Response(revision_payload(get_revision(request, revision_id)))


def _upload_from(request):
    length = int(request.META.get("CONTENT_LENGTH") or 0)
    if length > settings.DOCUMENT_MAX_BYTES + 1024 * 1024:
        raise ApiError(
            "FILE_TOO_LARGE",
            f"Fichier trop volumineux (limite {settings.DOCUMENT_MAX_BYTES} octets).",
            413,
            {"max_bytes": settings.DOCUMENT_MAX_BYTES},
        )
    upload = request.FILES.get("file")
    if upload is None:
        raise ApiError("FILE_REQUIRED", "Joindre un fichier.", 400, documents.limits())
    return upload


def _usage(request):
    """usage : « auto » (type lu sur le titre) ou un usage connu ; document_type : code de la taxonomie."""
    if request.data.get("document_type"):
        return "auto"
    usage = request.data.get("usage") or CaseDocument.Usage.OTHER
    if usage not in [*CaseDocument.Usage.values, services.AUTO]:
        raise ApiError("INVALID_USAGE", "Usage de pièce inconnu.", 400, {"allowed": CaseDocument.Usage.values})
    return usage


class CaseDocumentsView(APIView):
    """POST multipart : file, usage, duplicate_action (keep_both). En-tête Idempotency-Key facultatif."""

    permission_classes = [CanEdit]
    parser_classes = [MultiPartParser]

    def get(self, request, case_id):
        case = get_case(request, case_id)
        links = case.current_revision.documents.select_related("document__uploaded_by", "added_by")
        return Response({"results": [case_document_payload(lk) for lk in links], "limits": documents.limits()})

    def post(self, request, case_id):
        case = get_case(request, case_id)
        upload = _upload_from(request)
        link, created = services.attach_upload(
            org=request.organization,
            actor=request.user,
            revision=case.current_revision,
            upload=upload,
            usage=_usage(request),
            declared_mime=getattr(upload, "content_type", "") or "",
            duplicate_action=request.data.get("duplicate_action", ""),
            idempotency_key=(request.headers.get("Idempotency-Key") or "")[:100],
            document_type=(request.data.get("document_type") or "")[:60],
        )
        link = CaseDocument.objects.select_related("document__uploaded_by", "added_by").get(pk=link.pk)
        return Response(case_document_payload(link), status=201 if created else 200)


class CaseDocumentReuseView(APIView):
    permission_classes = [CanEdit]

    def post(self, request, case_id):
        case = get_case(request, case_id)
        link = services.reuse_document(
            org=request.organization,
            actor=request.user,
            revision=case.current_revision,
            document_id=request.data.get("document_id"),
            usage=_usage(request),
            document_type=(request.data.get("document_type") or "")[:60],
        )
        return Response(case_document_payload(link), status=201)


class CaseDocumentReplaceView(APIView):
    permission_classes = [CanEdit]
    parser_classes = [MultiPartParser]

    def post(self, request, link_id):
        upload = _upload_from(request)
        link = services.replace_document(
            org=request.organization,
            actor=request.user,
            link_id=link_id,
            upload=upload,
            declared_mime=getattr(upload, "content_type", "") or "",
        )
        return Response(case_document_payload(link), status=201)


def get_document(request, document_id) -> Document:
    doc = (
        Document.objects.for_organization(request.organization)
        .select_related("uploaded_by")
        .filter(pk=document_id)
        .first()
    )
    if doc is None:
        raise ApiError(*services.NOT_FOUND)
    return doc


class DocumentLimitsView(APIView):
    permission_classes = [HasActiveOrganization]

    def get(self, request):
        return Response(documents.limits())


class DocumentDetailView(APIView):
    permission_classes = [HasActiveOrganization]

    def get(self, request, document_id):
        doc = get_document(request, document_id)
        versions, cursor = [], doc
        while cursor.supersedes_id:
            cursor = cursor.supersedes
            versions.append(document_payload(cursor))
        return Response({**document_payload(doc), "previous_versions": versions})


class DocumentDownloadView(APIView):
    """DOC-04 : lien temporaire émis après contrôle des droits ; les octets ne sont jamais publics."""

    permission_classes = [HasActiveOrganization]

    def get(self, request, document_id):
        doc = get_document(request, document_id)
        disposition = "inline" if request.query_params.get("disposition") == "inline" else "attachment"
        if disposition == "inline" and (doc.mime not in (PDF, PNG, JPEG) or not doc.previewable):
            raise ApiError("PREVIEW_UNAVAILABLE", "Aperçu intégré impossible pour ce fichier ; le télécharger.", 422)
        return Response(documents.issue_access(document=doc, user=request.user, disposition=disposition))


class DocumentPreviewView(APIView):
    permission_classes = [HasActiveOrganization]

    def get(self, request, document_id):
        doc = get_document(request, document_id)
        if not doc.previewable:
            return Response(
                {"kind": "unavailable", "message": doc.get_readability_display(), "notes": doc.inspection_notes}
            )
        if doc.mime == XLSX:
            return Response({"kind": "sheet", **documents.xlsx_preview(doc)})
        link = documents.issue_access(document=doc, user=request.user, disposition="inline")
        return Response({"kind": "pdf" if doc.mime == PDF else "image", **link})


class FileView(APIView):
    """Lecture des octets par jeton : même utilisateur, affiliation active, durée courte."""

    permission_classes = [IsAuthenticated]

    @classmethod
    def as_view(cls, **kwargs):
        return xframe_options_sameorigin(super().as_view(**kwargs))

    def get(self, request, token, name=None):
        doc, disposition = documents.resolve_access(token, request.user)
        response = FileResponse(
            get_storage().open(doc.object_key),
            content_type=doc.mime,
            as_attachment=disposition == "attachment",
            filename=doc.original_name,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        if doc.mime != PDF:
            # Le lecteur PDF intégré du navigateur ne s'affiche pas sous une politique aussi stricte.
            response["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
        return response


class InvoiceCreateView(APIView):
    permission_classes = [CanEdit]

    def post(self, request, revision_id):
        get_revision(request, revision_id)
        inv = services.add_invoice(
            org=request.organization, actor=request.user, revision_id=revision_id, data=valid(InvoiceInput, request)
        )
        return Response(invoice_payload(inv), status=201)


class InvoiceDetailView(APIView):
    permission_classes = [CanEdit]

    def patch(self, request, invoice_id):
        inv = services.update_invoice(
            org=request.organization,
            actor=request.user,
            invoice_id=invoice_id,
            expected=expected_version(request),
            data=valid(InvoiceInput, request, partial=True),
        )
        return Response(invoice_payload(inv))


class InvoiceFieldConfirmView(APIView):
    permission_classes = [CanEdit]

    def post(self, request, invoice_id, field):
        inv = services.confirm_invoice_field(
            org=request.organization,
            actor=request.user,
            invoice_id=invoice_id,
            expected=expected_version(request),
            field=field,
        )
        return Response(invoice_payload(inv))


class InvoiceLineCreateView(APIView):
    permission_classes = [CanEdit]

    def post(self, request, invoice_id):
        line = services.add_invoice_line(
            org=request.organization, actor=request.user, invoice_id=invoice_id, data=valid(LineInput, request)
        )
        return Response(line_payload(line), status=201)


class InvoiceLineDetailView(APIView):
    permission_classes = [CanEdit]

    def patch(self, request, line_id):
        line = services.update_invoice_line(
            org=request.organization,
            actor=request.user,
            line_id=line_id,
            expected=expected_version(request),
            data=valid(LineInput, request, partial=True),
        )
        return Response(line_payload(line))


def get_goods(request, goods_id) -> GoodsLine:
    goods = (
        GoodsLine.objects.for_organization(request.organization).select_related("revision").filter(pk=goods_id).first()
    )
    if goods is None:
        raise ApiError(*services.NOT_FOUND)
    return goods


class GoodsLineCreateView(APIView):
    permission_classes = [CanEdit]

    def post(self, request, revision_id):
        goods = services.create_goods_line(
            org=request.organization, actor=request.user, revision_id=revision_id, data=valid(GoodsInput, request)
        )
        return Response(goods_payload(goods), status=201)


class GoodsLineDetailView(APIView):
    permission_classes = [CanEdit]

    def get(self, request, goods_id):
        return Response(goods_payload(get_goods(request, goods_id)))

    def patch(self, request, goods_id):
        data = valid(GoodsInput, request, partial=True)
        data.pop("invoice_line_ids", None)
        services.update_goods_line(
            org=request.organization,
            actor=request.user,
            goods_id=goods_id,
            expected=expected_version(request),
            data=data,
        )
        return Response(goods_payload(get_goods(request, goods_id)))


class CodeCheckView(APIView):
    permission_classes = [CanEdit]

    def post(self, request, goods_id):
        check = services.run_code_check(
            org=request.organization, actor=request.user, goods_id=goods_id, edition_id=request.data.get("edition_id")
        )
        goods = get_goods(request, goods_id)
        return Response(services.check_payload(check, goods, goods.revision), status=201)


class DecisionView(APIView):
    permission_classes = [CanEdit]

    def get(self, request, goods_id):
        goods = get_goods(request, goods_id)
        return Response(
            {
                "results": [
                    decision_payload(d, goods)
                    for d in goods.decisions.select_related("selected_node", "edition", "actor")
                ]
            }
        )

    def post(self, request, goods_id):
        services.record_decision(
            org=request.organization, actor=request.user, goods_id=goods_id, data=valid(DecisionInput, request)
        )
        return Response(goods_payload(get_goods(request, goods_id)), status=201)


class CaseAuditView(APIView):
    """AUD-01/AUD-02 : historique d'un dossier, borné à la société."""

    permission_classes = [CanEdit]

    def get(self, request, case_id):
        case = get_case(request, case_id)
        events = AuditEvent.objects.filter(organization=request.organization, scope=case.scope).select_related("actor")
        return Response(
            {
                "results": [
                    {
                        "id": str(e.id),
                        "at": e.at,
                        "actor": e.actor.email if e.actor else None,
                        "event_type": e.event_type,
                        "entity_type": e.entity_type,
                        "entity_id": e.entity_id,
                        "previous": e.previous,
                        "current": e.current,
                    }
                    for e in events.order_by("-at")[:500]
                ]
            }
        )


class InvoiceGoodsLinesView(APIView):
    """Une marchandise par ligne facturée libre de la facture (chemin court après extraction)."""

    permission_classes = [CanEdit]

    def post(self, request, invoice_id):
        created = services.goods_lines_from_invoice(org=request.organization, actor=request.user, invoice_id=invoice_id)
        return Response({"results": [goods_payload(get_goods(request, g.id)) for g in created]}, status=201)


class ProposalInput(serializers.Serializer):
    edition_id = serializers.UUIDField(required=False, allow_null=True)
    query = serializers.CharField(required=False, allow_blank=True, max_length=500)
    explicit = serializers.BooleanField(required=False, default=False)


class ProposalView(APIView):
    """COD-04 à COD-06 : aide au classement, seulement si nécessaire ou explicitement demandée."""

    permission_classes = [CanEdit]

    def get(self, request, goods_id):
        goods = get_goods(request, goods_id)
        sets = goods.proposal_sets.select_related("edition", "created_by", "goods_line")[:10]
        return Response({"results": [proposals.payload(ps) for ps in sets]})

    def post(self, request, goods_id):
        data = valid(ProposalInput, request)
        goods = get_goods(request, goods_id)
        edition_id = data.get("edition_id") or goods.revision.target_edition_id
        if not edition_id:
            raise ApiError("EDITION_REQUIRED", "Choisir l'édition du référentiel dans laquelle chercher.", 422)
        edition = services.edition_for(request.user, edition_id)
        proposal_set = proposals.propose(
            org=request.organization,
            actor=request.user,
            goods=goods,
            edition=edition,
            query=data.get("query", ""),
            explicit=data.get("explicit", False),
        )
        return Response(proposals.payload(proposal_set), status=201)


class AIChoiceView(APIView):
    """CLA-IA : l'IA choisit parmi les propositions, sur demande de l'agent ; jamais une décision."""

    permission_classes = [CanEdit]

    def post(self, request, goods_id):
        from . import ai_choice

        goods = get_goods(request, goods_id)
        choice = ai_choice.choose(org=request.organization, actor=request.user, goods_id=goods.id)
        if choice is None:
            raise ApiError("NO_CANDIDATES", "Aucune ligne du tarif à départager : préciser la désignation.", 422)
        return Response(proposals.payload(choice.proposal_set), status=201)
