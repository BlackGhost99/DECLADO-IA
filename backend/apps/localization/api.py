"""User and tenant locale preferences. Text of official tariffs is never translated in place."""
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.core.exceptions import ApiError
from apps.organizations.models import Role
from apps.organizations.permissions import HasActiveOrganization

LOCALES = ("fr", "en", "es", "ar")

class LocalePayload(serializers.Serializer):
    locale = serializers.ChoiceField(choices=LOCALES)

class UserLocaleView(APIView):
    def get(self, request):
        return Response({"locale": request.user.interface_locale})

    def put(self, request):
        data = LocalePayload(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        current = user.interface_locale
        locale = data.validated_data["locale"]
        if current != locale:
            user.interface_locale = locale
            user.save(update_fields=["interface_locale"])
            record_event(
                organization=None,
                actor=user,
                event_type="user.locale_changed",
                entity=user,
                previous={"locale": current},
                current={"locale": locale},
            )
        return Response({"locale": locale})

class OrganizationLocaleView(APIView):
    permission_classes = [HasActiveOrganization]

    def get(self, request):
        return Response({"locale": request.organization.default_locale})

    def put(self, request):
        if Role.ORG_ADMIN not in request.membership.roles:
            raise ApiError("FORBIDDEN", "Administration de société requise.", 403)
        data = LocalePayload(data=request.data)
        data.is_valid(raise_exception=True)
        org = request.organization
        current = org.default_locale
        locale = data.validated_data["locale"]
        if current != locale:
            org.default_locale = locale
            org.save(update_fields=["default_locale"])
            record_event(
                organization=org,
                actor=request.user,
                event_type="organization.locale_changed",
                entity=org,
                previous={"locale": current},
                current={"locale": locale},
            )
        return Response({"locale": locale})

class CaseSummaryView(APIView):
    permission_classes = [HasActiveOrganization]

    def get(self, request, case_id):
        from apps.cases.models import CustomsCase

        from .reports import SUPPORTED, summary_payload

        locale = request.query_params.get("locale") or request.user.interface_locale
        if locale not in SUPPORTED:
            raise ApiError("INVALID_LOCALE", "Langue non prise en charge.", 400)
        case = (
            CustomsCase.objects.for_organization(request.organization)
            .select_related("current_revision")
            .filter(pk=case_id)
            .first()
        )
        if case is None:
            raise ApiError("NOT_FOUND", "Dossier introuvable.", 404)
        return Response(summary_payload(case=case, locale=locale))
