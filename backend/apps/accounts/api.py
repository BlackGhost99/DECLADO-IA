"""Authentification par session serveur (cookie HttpOnly) et protection CSRF."""

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.core.exceptions import ApiError
from apps.organizations.context import (
    active_memberships,
    auto_select_single_organization,
    resolve_membership,
    set_active_organization,
)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class ActiveOrganizationSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()


def me_payload(request) -> dict:
    user = request.user
    active = resolve_membership(request)
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "is_reference_manager": user.is_reference_manager,
        "memberships": [
            {
                "organization": {
                    "id": str(m.organization_id),
                    "name": m.organization.name,
                    "is_demo": m.organization.is_demo,
                    "timezone": m.organization.timezone,
                },
                "roles": m.roles,
            }
            for m in active_memberships(user).order_by("organization__name")
        ],
        "active_organization_id": str(active.organization_id) if active else None,
    }


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Pose le cookie CSRF ; le client renvoie sa valeur dans l'en-tête X-CSRFToken."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = authenticate(
            request, email=data.validated_data["email"].lower(), password=data.validated_data["password"]
        )
        if user is None:
            # Message unique : ne révèle pas si le compte existe ou est désactivé.
            raise ApiError("INVALID_CREDENTIALS", "Identifiants incorrects.", 400)
        login(request, user)
        auto_select_single_organization(request)
        record_event(organization=None, actor=user, event_type="auth.login", entity=user)
        return Response(me_payload(request))


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(me_payload(request))


class ActiveOrganizationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = ActiveOrganizationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        membership = set_active_organization(request, data.validated_data["organization_id"])
        if membership is None:
            # 404 plutôt que 403 : ne pas confirmer l'existence d'une autre société.
            raise ApiError("ORGANIZATION_NOT_FOUND", "Société introuvable.", 404)
        return Response(me_payload(request))
