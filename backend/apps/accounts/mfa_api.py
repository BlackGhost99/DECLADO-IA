"""Authenticated MFA enrollment and password-first TOTP challenge."""

import time

from django.contrib.auth import get_user_model, login
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.core.exceptions import ApiError

from .mfa import (
    CHALLENGE_TTL,
    accepted_step,
    consume_second_factor,
    decrypt_secret,
    encrypt_secret,
    issue_recovery_codes,
    new_secret,
    provisioning_uri,
    rate_limit,
)
from .models import TotpDevice

User = get_user_model()


class MFAChallengeInput(serializers.Serializer):
    code = serializers.CharField(max_length=32, trim_whitespace=True)


class MFASetupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if TotpDevice.objects.filter(user=request.user, confirmed_at__isnull=False).exists():
            raise ApiError("MFA_ALREADY_ENABLED", "La double authentification est déjà activée.", 409)
        # Existing pending setup is replaced; unconfirmed secrets cannot authenticate.
        secret = new_secret()
        TotpDevice.objects.update_or_create(
            user=request.user,
            defaults={"encrypted_secret": encrypt_secret(secret), "last_step": -1, "recovery_hashes": []},
        )
        return Response({"secret": secret, "provisioning_uri": provisioning_uri(request.user.email, secret)})


class MFAConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MFAChallengeInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        rate_limit(request, "mfa-enroll", str(request.user.pk), limit=6, seconds=300)
        device = TotpDevice.objects.filter(user=request.user, confirmed_at__isnull=True).first()
        if device is None:
            raise ApiError("MFA_SETUP_REQUIRED", "Initialisez d'abord votre authentificateur.", 409)
        step = accepted_step(decrypt_secret(device.encrypted_secret), serializer.validated_data["code"])
        if step is None:
            raise ApiError("INVALID_MFA_CODE", "Code de vérification incorrect.", 400)
        visible_codes, hashes = issue_recovery_codes()
        device.last_step = step
        device.recovery_hashes = hashes
        device.confirmed_at = timezone.now()
        device.save(update_fields=["last_step", "recovery_hashes", "confirmed_at"])
        request.session["mfa_passed"] = True
        request.session.cycle_key()
        record_event(organization=None, actor=request.user, event_type="auth.mfa_enabled", entity=request.user)
        # Plain recovery codes are shown precisely once; never logged or stored in plaintext.
        return Response({"enabled": True, "recovery_codes": visible_codes})


class MFAVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = MFAChallengeInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        uid = request.session.get("mfa_pending_uid")
        since = request.session.get("mfa_pending_at", 0)
        if not uid or time.time() - since > CHALLENGE_TTL:
            request.session.flush()
            raise ApiError("MFA_CHALLENGE_EXPIRED", "Vérification expirée, reconnectez-vous.", 401)
        rate_limit(request, "mfa-verify", str(uid), limit=6, seconds=300)
        user = User.objects.filter(pk=uid, is_active=True).first()
        if user is None or not consume_second_factor(user, serializer.validated_data["code"]):
            raise ApiError("INVALID_MFA_CODE", "Code de vérification incorrect.", 400)
        request.session.flush()
        login(request, user)
        request.session["mfa_passed"] = True
        from apps.organizations.context import auto_select_single_organization

        auto_select_single_organization(request)
        record_event(organization=None, actor=user, event_type="auth.login_mfa", entity=user)
        from .api import me_payload

        return Response(me_payload(request))


class MFAStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        device = TotpDevice.objects.filter(user=request.user, confirmed_at__isnull=False).first()
        return Response(
            {
                "enabled": device is not None,
                "verified_session": bool(request.session.get("mfa_passed")),
                "recovery_codes_remaining": len(device.recovery_hashes) if device else 0,
            }
        )
