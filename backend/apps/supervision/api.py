"""Console ClairTransit > Supervision : réservée à l'exploitant de la plateforme."""

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ApiError
from apps.onboarding.api import IsPlatformOperator

from . import services


class SupervisionView(APIView):
    permission_classes = [IsPlatformOperator]

    def get(self, request):
        try:
            days = int(request.query_params.get("days", "7"))
        except ValueError:
            days = 0
        if days not in services.PERIODS:
            raise ApiError("VALIDATION_ERROR", "Période : 1, 7 ou 30 jours.", 400)
        return Response(services.dashboard(days))


class AntivirusSelfTestView(APIView):
    permission_classes = [IsPlatformOperator]

    def post(self, request):
        return Response(services.self_test(request.user))
