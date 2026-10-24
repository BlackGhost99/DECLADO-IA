"""Read-only view of the selected organization's business capabilities."""
from rest_framework.response import Response
from rest_framework.views import APIView

from .business_models import BusinessProfile
from .business_permissions import PROFILE_FEATURES
from .permissions import HasActiveOrganization


class BusinessProfileView(APIView):
    permission_classes = [HasActiveOrganization]

    def get(self, request):
        profile = getattr(request.organization, "business_profile", None)
        kind = profile.primary_profile if profile else BusinessProfile.TRANSIT
        features = sorted(PROFILE_FEATURES.get(kind, frozenset()) | (set(profile.features) if profile else set()))
        return Response({
            "organization_id": str(request.organization.id),
            "primary_profile": kind,
            "features": features,
            "agencies_enabled": "agencies" in features,
        })
