"""Authentification par session serveur (cookie HttpOnly) et protection CSRF."""

import time

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.accounts.mfa import rate_limit
from apps.accounts.models import TotpDevice
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
        "interface_locale": user.interface_locale,
        "is_reference_manager": user.is_reference_manager,
        "mfa_enabled": TotpDevice.objects.filter(user=user, confirmed_at__isnull=False).exists(),
        "mfa_verified_session": bool(request.session.get("mfa_passed")),
        "mfa_required_for_access": settings.MFA_ENFORCE,
        "memberships": [
            {
                "organization": {
                    "id": str(m.organization_id),
                    "name": m.organization.name,
                    "is_demo": m.organization.is_demo,
                    "timezone": m.organization.timezone,
                    "default_locale": m.organization.default_locale,
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
        identity = data.validated_data["email"].lower()
        rate_limit(request, "password-login", identity, limit=8, seconds=300)
        user = authenticate(
            request, email=data.validated_data["email"].lower(), password=data.validated_data["password"]
        )
        if user is None:
            # Message unique : ne révèle pas si le compte existe ou est désactivé.
            raise ApiError("INVALID_CREDENTIALS", "Identifiants incorrects.", 400)
        if TotpDevice.objects.filter(user=user, confirmed_at__isnull=False).exists():
            # Two-step login: no authenticated session before valid second factor.
            request.session.flush()
            request.session["mfa_pending_uid"] = str(user.pk)
            request.session["mfa_pending_at"] = time.time()
            return Response({"mfa_required": True}, status=202)
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
