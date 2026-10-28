"""API de l'extraction : demande (202 + travail), suivi, détail localisé, divergences."""

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cases.models import CaseDocument
from apps.core.exceptions import ApiError
from apps.core.models import BackgroundJob
from apps.organizations.models import Role
from apps.organizations.permissions import HasActiveOrganization, require_roles

from . import ai, ai_completion, readers, services
from .models import Divergence, ExtractionRun, FieldCorrection, FieldObservation

CanEdit = require_roles(Role.DECLARANT, Role.VALIDATOR, safe_methods_open=True)
ERROR_HINTS = {
    "OCR_UNAVAILABLE": "Saisir les lignes manuellement, ou demander l'installation de l'OCR.",
    "OCR_REQUIRED": "Relancer avec l'OCR, ou saisir les lignes manuellement.",
    "DOCUMENT_PROTECTED": "Déposer une version sans mot de passe.",
    "DOCUMENT_UNREADABLE": "Déposer une version lisible, ou saisir les lignes manuellement.",
    "PAGE_LIMIT": "Découper la pièce, ou saisir les lignes manuellement.",
    "REVISION_NOT_EDITABLE": "Créer une nouvelle révision pour extraire à nouveau.",
    "INTERNAL_ERROR": "Relancer ; si l'échec persiste, saisir les lignes manuellement.",
}


def job_payload(job: BackgroundJob) -> dict:
    return {
        "id": str(job.id),
        "kind": job.kind,
        "state": job.state,
        "state_label": job.get_state_display(),
        "phase": job.phase,
        "progress": job.progress,
        "attempts": job.attempts,
        "error_code": job.error_code or None,
        "error_message": job.error_message or None,
        "hint": ERROR_HINTS.get(job.error_code),
        "result_ref": job.result_ref or None,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "note": "Un travail terminé ne valide rien : chaque valeur reste à revoir.",
    }


def run_summary(run: ExtractionRun) -> dict:
    return {
        "id": str(run.id),
        "case_document_id": str(run.case_document_id),
        "document_id": str(run.document_id),
        "attempt": run.attempt,
        "parser": run.parser,
        "parser_version": run.parser_version,
        "schema_version": run.schema_version,
        "provider": run.provider,
        "model": run.model,
        "options": run.options,
        "status": run.status,
        "status_label": run.get_status_display(),
        "error_code": run.error_code or None,
        "error_message": run.error_message or None,
        "hint": ERROR_HINTS.get(run.error_code),
        "warnings": run.warnings,
        "invoice_id": str(run.invoice_id) if run.invoice_id else None,
        "reader": run.options.get("reader", readers.INVOICE),
        "type_detection": run.stats.get("type_detection"),
        "fields": document_fields(run),
        "ai": ai_state(run),
        "previous_run_id": str(run.previous_run_id) if run.previous_run_id else None,
        "merge_report": run.merge_report,
        "created_by": run.created_by.email,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "job": job_payload(run.job),
    }


def _proposal(obs) -> dict:
    return {
        "raw": obs.raw_value,
        "parsed": obs.parsed_value,
        "status": obs.status,
        "notes": obs.notes,
        "excerpt": obs.source_span.excerpt if obs.source_span_id else "",
        "span": obs.source_span.as_dict() if obs.source_span_id else None,
        "created_at": obs.created_at,
    }


def _entered(correction) -> dict:
    return {
        "raw": (correction.current or {}).get("raw"),
        "from_ai": bool((correction.current or {}).get("from_ai")),
        "by": correction.actor.full_name or correction.actor.email,
        "at": correction.created_at,
    }


def document_fields(run: ExtractionRun) -> list[dict]:
    """Informations lues sur une pièce autre qu'une facture, dans l'ordre de leur type, avec la
    proposition de l'IA en ligne et la valeur retenue par l'agent quand elles existent."""
    reader = run.options.get("reader", readers.INVOICE)
    if reader == readers.INVOICE or run.status != ExtractionRun.Status.SUCCEEDED:
        return []
    order = {spec.name: n for n, spec in enumerate(readers.SPECS.get(reader, ()))}
    observations = list(run.observations.filter(entity_key="document").select_related("source_span"))
    proposals = {o.field_name: o for o in observations if o.origin_type == FieldObservation.Origin.AI}
    entered = {
        c.field_name: c
        for c in FieldCorrection.objects.filter(observation__run=run, observation__entity_key="document")
        .select_related("actor")
        .order_by("created_at")
    }
    read = [o for o in observations if o.origin_type != FieldObservation.Origin.AI]
    return [
        {
            "field": obs.field_name,
            "label": obs.label,
            "raw": obs.raw_value,
            "parsed": obs.parsed_value,
            "status": obs.status,
            "origin": obs.origin_type,
            "notes": obs.notes,
            "span": obs.source_span.as_dict() if obs.source_span_id else None,
            "proposal": _proposal(proposals[obs.field_name]) if obs.field_name in proposals else None,
            "entered": _entered(entered[obs.field_name]) if obs.field_name in entered else None,
        }
        for obs in sorted(read, key=lambda o: order.get(o.field_name, 99))
    ]


def invoice_proposals(run: ExtractionRun) -> list[dict]:
    """Propositions de l'IA pour l'en-tête d'une facture, tant que le champ de la facture reste vide."""
    if run.options.get("reader", readers.INVOICE) != readers.INVOICE or run.invoice_id is None:
        return []
    invoice = run.invoice
    out = []
    for obs in run.observations.filter(entity_key="invoice", origin_type=FieldObservation.Origin.AI).select_related(
        "source_span"
    ):
        if getattr(invoice, obs.field_name, None) in (None, ""):
            out.append({"field": obs.field_name, "label": obs.label} | _proposal(obs))
    return out


def ai_state(run: ExtractionRun) -> dict:
    """Ce que l'écran de la pièce montre de l'IA en ligne : dernier complément et bouton « Compléter »."""
    config = ai_completion.settings_for(run.organization)
    usable = ai.is_enabled() and config.enabled and run.status == ExtractionRun.Status.SUCCEEDED
    refused = ai_completion.client_refuses(run.case_document)
    missing = ai_completion.missing_fields(run) if usable and not refused else []
    return {
        "last": ai_completion.summary(run),
        "client_refused": refused,
        "can_complete": bool(missing),
        "missing": [f.name for f in missing],
        "proposals": invoice_proposals(run),
    }


def run_detail(run: ExtractionRun) -> dict:
    groups: dict[str, list] = {}
    for obs in run.observations.select_related("source_span").order_by("entity_key", "field_name"):
        groups.setdefault(obs.entity_key, []).append(
            {
                "field": obs.field_name,
                "label": obs.label,
                "raw": obs.raw_value,
                "parsed": obs.parsed_value,
                "status": obs.status,
                "origin": obs.origin_type,
                "confidence": obs.confidence,
                "notes": obs.notes,
                "span": obs.source_span.as_dict() if obs.source_span_id else None,
                "invoice_line_id": str(obs.invoice_line_id) if obs.invoice_line_id else None,
            }
        )
    return run_summary(run) | {
        "stats": run.stats,
        "charges": run.charges,
        "observations": groups,
        "comparison": services.compare_runs(run),
    }


class ExtractionInput(serializers.Serializer):
    ocr = serializers.BooleanField(required=False, default=False)
    retry = serializers.BooleanField(required=False, default=False)


class CaseDocumentExtractionsView(APIView):
    permission_classes = [CanEdit]

    def get(self, request, link_id):
        link = CaseDocument.objects.for_organization(request.organization).filter(pk=link_id).first()
        if link is None:
            raise ApiError(*services.NOT_FOUND)
        runs = link.extraction_runs.select_related("job", "created_by")
        return Response({"results": [run_summary(r) for r in runs]})

    def post(self, request, link_id):
        serializer = ExtractionInput(data=request.data)
        if not serializer.is_valid():
            raise ApiError("INVALID_REQUEST", "Requête invalide.", 400, serializer.errors)
        run, created = services.request_extraction(
            org=request.organization, actor=request.user, link_id=link_id, **serializer.validated_data
        )
        return Response(run_summary(run), status=202 if created else 200)


class ExtractionRunView(APIView):
    permission_classes = [HasActiveOrganization]

    def get(self, request, run_id):
        run = (
            ExtractionRun.objects.for_organization(request.organization)
            .select_related("job", "created_by")
            .filter(pk=run_id)
            .first()
        )
        if run is None:
            raise ApiError(*services.NOT_FOUND)
        return Response(run_detail(run))


class JobView(APIView):
    permission_classes = [HasActiveOrganization]

    def get(self, request, job_id):
        job = BackgroundJob.objects.for_organization(request.organization).filter(pk=job_id).first()
        if job is None:
            raise ApiError(*services.NOT_FOUND)
        return Response(job_payload(job))


class ResolveInput(serializers.Serializer):
    resolution = serializers.ChoiceField(choices=["keep", "accept"])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class DivergenceResolveView(APIView):
    permission_classes = [CanEdit]

    def post(self, request, divergence_id):
        serializer = ResolveInput(data=request.data)
        if not serializer.is_valid():
            raise ApiError("INVALID_REQUEST", "Requête invalide.", 400, serializer.errors)
        divergence = services.resolve_divergence(
            org=request.organization, actor=request.user, divergence_id=divergence_id, **serializer.validated_data
        )
        divergence = Divergence.objects.select_related("invoice_line", "resolved_by", "observation__source_span").get(
            pk=divergence.pk
        )
        from apps.cases.api import divergence_payload

        return Response(divergence_payload(divergence))


class CaseDocumentAICompletionView(APIView):
    """Complément par l'IA en ligne demandé par l'agent (mode « sur demande », ou relance)."""

    permission_classes = [CanEdit]

    def post(self, request, link_id):
        record = ai_completion.complete_on_demand(org=request.organization, actor=request.user, link_id=link_id)
        run = ExtractionRun.objects.select_related("job", "created_by").get(pk=record.run_id)
        return Response(run_summary(run))


class FieldDecisionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["accept", "set"])
    value = serializers.CharField(required=False, allow_blank=True, max_length=500)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ExtractionFieldDecisionView(APIView):
    """L'agent retient la proposition de l'IA, ou saisit la valeur d'une information non trouvée."""

    permission_classes = [CanEdit]

    def post(self, request, run_id, field_name):
        serializer = FieldDecisionInput(data=request.data)
        if not serializer.is_valid():
            raise ApiError("INVALID_REQUEST", "Requête invalide.", 400, serializer.errors)
        ai_completion.decide(
            org=request.organization,
            actor=request.user,
            run_id=run_id,
            field_name=field_name,
            **serializer.validated_data,
        )
        run = ExtractionRun.objects.select_related("job", "created_by").get(pk=run_id)
        return Response(run_summary(run))
