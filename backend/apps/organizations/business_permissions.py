"""Capabilities are an additional gate, never a substitute for role/object permissions."""
from .business_models import BusinessProfile
from .context import active_memberships

PROFILE_FEATURES = {
    BusinessProfile.TRANSIT: frozenset({"cases", "documents", "tariff", "taxes", "declaration"}),
    BusinessProfile.IMPORTER: frozenset({"cases", "documents", "tariff", "taxes", "estimates"}),
    BusinessProfile.LOGISTICS: frozenset({"cases", "documents", "tariff", "taxes", "declaration", "agencies", "transport"}),
    BusinessProfile.EXPERT: frozenset({"cases", "documents", "tariff", "taxes", "audit"}),
}
KNOWN_FEATURES = frozenset().union(*PROFILE_FEATURES.values())


def has_feature(user, organization, feature):
    if feature not in KNOWN_FEATURES or not organization or not organization.active:
        return False
    if not active_memberships(user).filter(organization=organization).exists():
        return False
    profile = getattr(organization, "business_profile", None)
    if profile is None:
        # Existing organizations default to transit until they are migrated.
        return feature in PROFILE_FEATURES[BusinessProfile.TRANSIT]
    return (
        feature in PROFILE_FEATURES.get(profile.primary_profile, frozenset())
        or feature in profile.features
    )
