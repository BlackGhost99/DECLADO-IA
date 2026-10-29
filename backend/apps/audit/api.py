from rest_framework import serializers
from rest_framework.generics import ListAPIView

from apps.organizations.models import Role
from apps.organizations.permissions import require_roles

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "at",
            "actor_email",
            "event_type",
            "entity_type",
            "entity_id",
            "previous",
            "current",
            "request_id",
        ]


class AuditEventListView(ListAPIView):
    """AUD-02 : historique filtrable, borné à la société active."""

    permission_classes = [require_roles(Role.ORG_ADMIN, Role.VALIDATOR)]
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        # Les annotations internes de la plateforme ne sont pas des événements métier du client.
        qs = (
            AuditEvent.objects.select_related("actor")
            .filter(organization=self.request.organization)
            .exclude(scope="platform")
        )
        params = self.request.query_params
        if params.get("event_type"):
            qs = qs.filter(event_type=params["event_type"])
        if params.get("actor"):
            qs = qs.filter(actor__email=params["actor"].lower())
        if params.get("since"):
            qs = qs.filter(at__gte=params["since"])
        if params.get("until"):
            qs = qs.filter(at__lt=params["until"])
        return qs
