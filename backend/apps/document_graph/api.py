from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.organizations.models import Role
from apps.organizations.permissions import require_roles
from . import services
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
        items = DocumentRelation.objects.for_organization(request.organization).filter(revision=rev).order_by("created_at")
        return Response({"revision_id": str(rev.id), "relations": [services.as_dict(item) for item in items]})

    def post(self, request, revision_id):
        data = RelationInput(data=request.data)
        data.is_valid(raise_exception=True)
        relation = services.add_relation(org=request.organization, actor=request.user, revision_id=revision_id, **data.validated_data)
        return Response(services.as_dict(relation), status=201)


class ReviewView(APIView):
    permission_classes = [Access]

    def post(self, request, relation_id):
        data = ReviewInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(services.as_dict(services.review_relation(org=request.organization, actor=request.user, relation_id=relation_id, **data.validated_data)))
