"""Lecture documentaire contextualisée par dossier et société active."""
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cases.models import CaseRevision
from apps.core.exceptions import ApiError
from apps.organizations.permissions import HasActiveOrganization

from .engine import CaseContext, UnresolvedRegulatoryCondition, evaluate_requirements
from .models import CompanyDocumentPolicy, DocumentRequirement, DocumentType


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
        policies = CompanyDocumentPolicy.objects.filter(
            organization=request.organization, active=True
        ).select_related("document_type")
        try:
            requirements = evaluate_requirements(context, rules, policies)
        except UnresolvedRegulatoryCondition as exc:
            raise ApiError("REGULATORY_REVIEW_REQUIRED", str(exc), 422) from exc

        received_links = list(
            revision.documents.filter(replaced_by__isnull=True)
            .select_related("document")
            .order_by("created_at")
        )
        received = {}
        unclassified = []
        for link in received_links:
            payload = {
                "case_document_id": str(link.pk),
                "filename": link.document.original_name,
                "usage": link.usage,
                "readability": link.document.readability,
            }
            code = KNOWN_USAGE_TYPES.get(link.usage)
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
