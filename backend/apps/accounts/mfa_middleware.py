"""Fail-closed API restriction while MFA enrollment or verification is required."""

from django.conf import settings
from django.http import JsonResponse

from apps.accounts.models import TotpDevice


class MFAEnforcementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        user = getattr(request, "user", None)
        if (
            settings.MFA_ENFORCE
            and path.startswith("/api/v1/")
            and not (
                path.startswith("/api/v1/auth/")
                or path in ("/api/v1/me", "/api/v1/health")
            )
            and user is not None
            and user.is_authenticated
        ):
            enrolled = TotpDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()
            if not enrolled or not request.session.get("mfa_passed"):
                return JsonResponse(
                    {
                        "code": "MFA_REQUIRED",
                        "message": "Activez ou validez la double authentification avant de continuer.",
                        "details": {},
                        "request_id": getattr(request, "request_id", ""),
                    },
                    status=403,
                )
        return self.get_response(request)
