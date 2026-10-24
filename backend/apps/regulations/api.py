"""Lecture documentaire contextualisée par dossier et société active."""

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cases.models import CaseDocument, CaseRevision
from apps.core.exceptions import ApiError
from apps.organizations.models import Role
from apps.organizations.permissions import HasActiveOrganization, require_roles

from .classification import suggest_document_type
from .engine import CaseContext, UnresolvedRegulatoryCondition, evaluate_requirements
from .models import CompanyDocumentPolicy, DocumentClassification, DocumentRequirement, DocumentType, RegulatorySource
from .readiness import legal_coverage_gate

# Seuls ces usages existants identifient un type sans ambiguïté.
# "transport" ne prouve PAS qu'il s'agit d'un B/L ou d'une LTA.
KNOWN_USAGE_TYPES = {
    "invoice": "commercial_invoice",
    "packing_list": "packing_list",
    "origin": "certificate_of_origin",
}
TRANSPORT_MODES = {"sea", "air", "road", "rail", "multimodal"}


class CaseDocumentChecklistView(APIView):
    """GET /api/v1/revisions/<uuid>/document-checklist?operation=import&transport_mode=sea.

    Les paramètres inconnus ne sont pas devinés. Aucun document téléversé
    n'est considéré comme vérifié réglementairement par sa seule présence.
    """

    permission_classes = [HasActiveOrganization]

    def get(self, request, revision_id):
        revision = (
            CaseRevision.objects.for_organization(request.organization)
            .select_related("case")
            .filter(pk=revision_id)
            .first()
        )
        if revision is None:
            raise ApiError("NOT_FOUND", "Révision introuvable.", 404)

        operation = request.query_params.get("operation", "")
        transport = request.query_params.get("transport_mode", "")
        if operation not in {"import", "export"} or transport not in TRANSPORT_MODES:
            raise ApiError(
                "DOCUMENT_CONTEXT_REQUIRED",
                "Précisez operation=import|export et transport_mode=sea|air|road|rail|multimodal.",
                422,
            )
        if not revision.planned_declaration_date or not revision.regime:
            raise ApiError(
                "DOCUMENT_CONTEXT_REQUIRED",
                "La révision doit préciser un régime et une date de déclaration.",
                422,
            )

        flags = {}
        for key in ("has_previous_regime", "has_privileged_regime"):
            raw = request.query_params.get(key)
            if raw is not None and raw not in {"true", "false"}:
                raise ApiError("INVALID_DOCUMENT_FLAG", f"{key} doit valoir true ou false.", 422)
            flags[key] = None if raw is None else raw == "true"

        context = CaseContext(
            country=revision.territory,
            operation=operation,
            regime=revision.regime,
            transport_mode=transport,
            declaration_date=revision.planned_declaration_date,
            **flags,
        )
        rules = DocumentRequirement.objects.filter(published=True, verified=True).select_related(
            "source", "document_type"
        )
        policies = CompanyDocumentPolicy.objects.filter(organization=request.organization, active=True).select_related(
            "document_type"
        )
        try:
            requirements = evaluate_requirements(context, rules, policies)
        except UnresolvedRegulatoryCondition as exc:
            raise ApiError("REGULATORY_REVIEW_REQUIRED", str(exc), 422) from exc

        classifications = {
            row.case_document_id: row.document_type.code
            for row in DocumentClassification.objects.filter(organization=request.organization)
        }
        received_links = list(
            revision.documents.filter(replaced_by__isnull=True).select_related("document").order_by("created_at")
        )
        received = {}
        unclassified = []
        for link in received_links:
            payload = {
                "case_document_id": str(link.pk),
                "filename": link.document.original_name,
                "usage": link.usage,
                "readability": link.document.readability,
                "classification": suggest_document_type(link.document.original_name),
            }
            code = classifications.get(link.pk) or KNOWN_USAGE_TYPES.get(link.usage)
            if code:
                received.setdefault(code, []).append(payload)
            else:
                unclassified.append(payload)

        codes = {entry["document_type"] for entry in requirements}
        labels = dict(DocumentType.objects.filter(code__in=codes).values_list("code", "label_fr"))
        results = [
            {
                **entry,
                "label": labels.get(entry["document_type"], entry["document_type"]),
                "status": "received_unverified" if received.get(entry["document_type"]) else "missing",
                "documents": received.get(entry["document_type"], []),
            }
            for entry in requirements
        ]
        # Aucune règle publiée n'est assimilée à « aucune obligation ».
        return Response(
            {
                "revision_id": str(revision.pk),
                "organization_id": str(request.organization.pk),
                "coverage": "review_required" if not results else "partial_unverified",
                "regulatory_validation": False,
                "requirements": results,
                "unclassified_documents": unclassified,
                "warning": (
                    "Liste indicative : seules les obligations publiées sont évaluées. "
                    "La présence d'une pièce ne constitue pas une validation douanière. "
                    "Les titres de transport doivent être classés précisément."
                ),
            }
        )


class PolicyInput(serializers.Serializer):
    document_type = serializers.SlugField(max_length=60)
    operation = serializers.ChoiceField(choices=["", "import", "export"], required=False, default="")
    regime = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    transport_mode = serializers.ChoiceField(choices=["", *sorted(TRANSPORT_MODES)], required=False, default="")
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class OrganizationDocumentPolicyView(APIView):
    """Tenant-limited additive policy; only organization administrators may create."""

    permission_classes = [require_roles(Role.ORG_ADMIN, safe_methods_open=True)]

    def get(self, request):
        rows = CompanyDocumentPolicy.objects.filter(organization=request.organization).select_related("document_type")
        return Response(
            {
                "results": [
                    {
                        "id": row.pk,
                        "document_type": row.document_type.code,
                        "label": row.document_type.label_fr,
                        "operation": row.operation,
                        "regime": row.regime,
                        "transport_mode": row.transport_mode,
                        "active": row.active,
                        "reason": row.reason,
                    }
                    for row in rows.order_by("pk")
                ]
            }
        )

    def post(self, request):
        data = PolicyInput(data=request.data)
        data.is_valid(raise_exception=True)
        doc = DocumentType.objects.filter(code=data.validated_data["document_type"], active=True).first()
        if doc is None:
            raise ApiError("UNKNOWN_DOCUMENT_TYPE", "Type documentaire inconnu.", 422)
        row = CompanyDocumentPolicy.objects.create(
            organization=request.organization,
            document_type=doc,
            **{k: v for k, v in data.validated_data.items() if k != "document_type"},
        )
        return Response({"id": row.pk, "document_type": doc.code, "active": row.active}, status=201)


class DocumentTypeListView(APIView):
    permission_classes = [HasActiveOrganization]

    def get(self, request):
        return Response(
            {"results": list(DocumentType.objects.filter(active=True).order_by("code").values("code", "label_fr"))}
        )


class DocumentReadinessView(APIView):
    """Conservative V1 gate. Never suggests that legal coverage is complete."""

    permission_classes = [HasActiveOrganization]

    def get(self, request, revision_id):
        revision = CaseRevision.objects.for_organization(request.organization).filter(pk=revision_id).first()
        if revision is None:
            raise ApiError("NOT_FOUND", "Révision introuvable.", 404)
        result = legal_coverage_gate(
            verified_sources=RegulatorySource.objects.filter(verified_on__isnull=False).count(),
            published_rules=DocumentRequirement.objects.filter(published=True, verified=True).count(),
            coverage_certified=False,
        )
        if not revision.planned_declaration_date or not revision.regime:
            result["blocking_reasons"].append("Régime et date de déclaration manquants.")
        if revision.documents.filter(replaced_by__isnull=True).count() == 0:
            result["blocking_reasons"].append("Aucune pièce jointe à cette révision.")
        result["ready"] = False
        result["revision_id"] = str(revision.pk)
        result["regulatory_validation"] = False
        return Response(result)


class ConfirmDocumentTypeInput(serializers.Serializer):
    document_type = serializers.SlugField(max_length=60)
    reason = serializers.CharField(max_length=300, min_length=3)


class ConfirmDocumentTypeView(APIView):
    """Explicit one-time agent confirmation; server resolves organization from membership."""

    permission_classes = [require_roles(Role.DECLARANT, Role.VALIDATOR)]

    def post(self, request, link_id):
        data = ConfirmDocumentTypeInput(data=request.data)
        data.is_valid(raise_exception=True)
        link = (
            CaseDocument.objects.for_organization(request.organization)
            .select_related("revision")
            .filter(pk=link_id, replaced_by__isnull=True)
            .first()
        )
        if link is None:
            raise ApiError("NOT_FOUND", "Pièce active introuvable.", 404)
        if not link.revision.is_editable:
            raise ApiError("REVISION_READ_ONLY", "Cette révision ne peut plus être modifiée.", 409)
        document_type = DocumentType.objects.filter(code=data.validated_data["document_type"], active=True).first()
        if document_type is None:
            raise ApiError("UNKNOWN_DOCUMENT_TYPE", "Type de document inconnu.", 422)
        if DocumentClassification.objects.filter(case_document=link).exists():
            raise ApiError("CLASSIFICATION_EXISTS", "Classification déjà confirmée, historique à préserver.", 409)
        confirmed = DocumentClassification.objects.create(
            organization=request.organization,
            case_document=link,
            document_type=document_type,
            confirmed_by=request.user,
            reason=data.validated_data["reason"],
        )
        return Response(
            {
                "id": confirmed.pk,
                "case_document_id": str(link.pk),
                "document_type": document_type.code,
                "confirmed_at": confirmed.confirmed_at,
                "confirmed_by": str(request.user.pk),
                "regulatory_validation": False,
            },
            status=201,
        )
