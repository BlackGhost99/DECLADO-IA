from rest_framework import serializers
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Role
from apps.organizations.permissions import require_roles

from . import services
from .models import Importer

# Lecture : tout membre actif. Écriture : rôle métier déclarant ou validateur.
CanEditImporters = require_roles(Role.DECLARANT, Role.VALIDATOR, safe_methods_open=True)


class ImporterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Importer
        fields = [
            "id",
            "name",
            "identifiers",
            "contacts",
            "address",
            "notes",
            "ai_refused",
            "ai_refused_at",
            "created_at",
            "updated_at",
            "row_version",
        ]
        read_only_fields = ["id", "ai_refused", "ai_refused_at", "created_at", "updated_at", "row_version"]

    def validate_identifiers(self, value):
        if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
            raise serializers.ValidationError('Les identifiants sont un objet de textes (ex. {"nif": "…"}).')
        return value

    def validate_contacts(self, value):
        if not isinstance(value, list) or not all(isinstance(c, dict) for c in value):
            raise serializers.ValidationError("Les contacts sont une liste d'objets.")
        return value


class DuplicateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Importer
        fields = ["id", "name", "identifiers"]


class ImporterListView(ListCreateAPIView):
    permission_classes = [CanEditImporters]
    serializer_class = ImporterSerializer

    def get_queryset(self):
        qs = Importer.objects.for_organization(self.request.organization)
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(normalized_name__contains=services.normalize_name(q))
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # organization vient de la session, jamais du corps de la requête.
        importer, duplicates = services.create_importer(
            organization=request.organization, actor=request.user, data=serializer.validated_data
        )
        body = ImporterSerializer(importer).data
        body["possible_duplicates"] = DuplicateSerializer(duplicates, many=True).data
        return Response(body, status=201)


class ImporterDetailView(RetrieveUpdateAPIView):
    permission_classes = [CanEditImporters]
    serializer_class = ImporterSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return Importer.objects.for_organization(self.request.organization)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        expected = request.headers.get("If-Match") or request.data.get("row_version")
        try:
            expected = int(str(expected).strip('"')) if expected is not None else None
        except ValueError:
            expected = -1
        importer = services.update_importer(
            organization=request.organization,
            actor=request.user,
            importer_id=instance.pk,
            expected_version=expected,
            data=serializer.validated_data,
        )
        return Response(ImporterSerializer(importer).data)


class AIRefusalInput(serializers.Serializer):
    refused = serializers.BooleanField()


class ImporterAIRefusalView(APIView):
    """Refus du client que ses pièces soient lues par une IA en ligne : tout membre le note, seul un
    administrateur de la société le lève."""

    permission_classes = [require_roles(Role.DECLARANT, Role.VALIDATOR, Role.ORG_ADMIN)]

    def put(self, request, pk):
        serializer = AIRefusalInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        importer = services.set_ai_refusal(
            organization=request.organization,
            actor=request.user,
            importer_id=pk,
            refused=serializer.validated_data["refused"],
            can_lift=request.membership.has_role(Role.ORG_ADMIN),
        )
        return Response(ImporterSerializer(importer).data)
