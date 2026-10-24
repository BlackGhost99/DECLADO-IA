from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Role
from apps.organizations.permissions import require_roles

from . import intelligence, services
from .models import DocumentRelation

Access = require_roles(Role.DECLARANT, Role.VALIDATOR, safe_methods_open=True)


class RelationInput(serializers.Serializer):
    source_id = serializers.UUIDField()
    target_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=sorted(services.KINDS))
    rationale = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")


class ReviewInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=["confirmed", "rejected"])


class GraphView(APIView):
    permission_classes = [Access]

    def get(self, request, revision_id):
        rev = services._revision(request.organization, revision_id)
        items = (
            DocumentRelation.objects.for_organization(request.organization).filter(revision=rev).order_by("created_at")
        )
        return Response({"revision_id": str(rev.id), "relations": [services.as_dict(item) for item in items]})

    def post(self, request, revision_id):
        data = RelationInput(data=request.data)
        data.is_valid(raise_exception=True)
        relation = services.add_relation(
            org=request.organization, actor=request.user, revision_id=revision_id, **data.validated_data
        )
        return Response(services.as_dict(relation), status=201)


class ReviewView(APIView):
    permission_classes = [Access]

    def post(self, request, relation_id):
        data = ReviewInput(data=request.data)
        data.is_valid(raise_exception=True)
        relation = services.review_relation(
            org=request.organization, actor=request.user, relation_id=relation_id, **data.validated_data
        )
        return Response(services.as_dict(relation))


class SuggestView(APIView):
    permission_classes = [require_roles(Role.DECLARANT, Role.VALIDATOR)]

    def post(self, request, revision_id):
        suggestions = services.suggest_relations(org=request.organization, actor=request.user, revision_id=revision_id)
        return Response({"proposals": suggestions, "count": len(suggestions)})


# Intelligence documentaire : lecture isolée, propositions explicables et revue humaine.

class DocumentIntelligenceView(APIView):
    permission_classes = [Access]

    def get(self, request, revision_id):
        return Response(intelligence.summary(org=request.organization, revision_id=revision_id))

    def post(self, request, revision_id):
        result = intelligence.analyze(
            org=request.organization, actor=request.user, revision_id=revision_id
        )
        return Response({"created": result, **intelligence.summary(org=request.organization, revision_id=revision_id)})


class ManualInvoiceLinkInput(serializers.Serializer):
    document_id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=sorted(intelligence.DocumentInvoiceLink.Kind.values))


class ManualInvoiceLinkView(APIView):
    permission_classes = [require_roles(Role.DECLARANT, Role.VALIDATOR)]

    def post(self, request, revision_id):
        serializer = ManualInvoiceLinkInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = intelligence.create_invoice_link(
            org=request.organization, actor=request.user, revision_id=revision_id,
            **serializer.validated_data,
        )
        return Response(data, status=201)


class ShipmentInput(serializers.Serializer):
    reference = serializers.CharField(max_length=100)


class ShipmentCreateView(APIView):
    permission_classes = [require_roles(Role.DECLARANT, Role.VALIDATOR)]

    def post(self, request, revision_id):
        serializer = ShipmentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = intelligence.create_shipment(
            org=request.organization, actor=request.user,
            revision_id=revision_id, **serializer.validated_data,
        )
        return Response(data, status=201)


class ShipmentLinkInput(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=["document", "invoice"])
    target_id = serializers.UUIDField()


class ShipmentLinkCreateView(APIView):
    permission_classes = [require_roles(Role.DECLARANT, Role.VALIDATOR)]

    def post(self, request, revision_id, shipment_id):
        serializer = ShipmentLinkInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = intelligence.create_shipment_link(
            org=request.organization, actor=request.user, revision_id=revision_id,
            shipment_id=shipment_id, **serializer.validated_data,
        )
        return Response(data, status=201)


class IntelligenceReviewInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=["confirmed", "rejected"])


class IntelligenceReviewView(APIView):
    permission_classes = [require_roles(Role.DECLARANT, Role.VALIDATOR)]

    def post(self, request, model, link_id):
        serializer = IntelligenceReviewInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(intelligence.review(
            org=request.organization, actor=request.user, model=model, link_id=link_id,
            **serializer.validated_data,
        ))


class ShipmentConfirmView(APIView):
    permission_classes = [require_roles(Role.DECLARANT, Role.VALIDATOR)]

    def post(self, request, shipment_id):
        return Response(intelligence.confirm_shipment(
            org=request.organization, actor=request.user, shipment_id=shipment_id,
        ))


class ConflictResolveInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class IntelligenceConflictResolveView(APIView):
    permission_classes = [require_roles(Role.DECLARANT, Role.VALIDATOR)]

    def post(self, request, conflict_id):
        serializer = ConflictResolveInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(intelligence.resolve_conflict(
            org=request.organization, actor=request.user, conflict_id=conflict_id,
            **serializer.validated_data,
        ))
