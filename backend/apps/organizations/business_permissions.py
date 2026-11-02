"""Capacités d'une société : métier principal, activités secondaires et habilitations (MET-01 à MET-06).

Les capacités sont une barrière supplémentaire, jamais un substitut aux rôles et aux contrôles
d'objet. La préparation d'une déclaration (`declaration`) est réservée :
- au métier transitaire / commissionnaire, principal ou secondaire ; il exerce sous agrément
  (CD CEMAC art. 148 à 151), dont la référence est enregistrée dans la console ;
- à toute autre société seulement si une habilitation vérifiée, en vigueur et du pays de la
  société le permet (agrément, autorisation provisoire, déclaration pour compte propre).
Un conseil ou un expert agréé ne reçoit jamais `declaration` par son métier.
"""

from django.utils import timezone

from .business_models import BusinessProfile, CustomsHabilitation
from .context import active_memberships

PROFILE_FEATURES = {
    BusinessProfile.TRANSIT: frozenset({"cases", "documents", "tariff", "taxes", "declaration"}),
    BusinessProfile.IMPORTER: frozenset({"cases", "documents", "tariff", "taxes", "estimates"}),
    BusinessProfile.LOGISTICS: frozenset({"cases", "documents", "tariff", "taxes", "agencies", "transport"}),
    BusinessProfile.EXPERT: frozenset({"cases", "documents", "tariff", "taxes", "audit", "advisory"}),
}
KNOWN_FEATURES = frozenset().union(*PROFILE_FEATURES.values())

# Habilitations qui ouvrent la préparation d'une déclaration à une société qui n'est pas transitaire.
DECLARING_KINDS = frozenset(
    {
        CustomsHabilitation.Kind.CUSTOMS_BROKER,
        CustomsHabilitation.Kind.TEMPORARY_AUTHORIZATION,
        CustomsHabilitation.Kind.OWN_ACCOUNT,
    }
)


def organization_profiles(organization) -> list[str]:
    profile = getattr(organization, "business_profile", None)
    if profile is None:
        # Sociétés antérieures au choix du métier : transitaires.
        return [BusinessProfile.TRANSIT]
    return profile.profiles


def declaring_habilitations(organization, day=None):
    day = day or timezone.localdate()
    rows = CustomsHabilitation.objects.for_organization(organization).filter(
        kind__in=DECLARING_KINDS,
        status=CustomsHabilitation.Status.VERIFIED,
        country_code=organization.country_code,
    )
    return [h for h in rows if h.in_force(day)]


def declaration_basis(organization, day=None) -> str | None:
    """Pourquoi la société peut préparer une déclaration : son métier, une habilitation, ou rien."""
    if BusinessProfile.TRANSIT in organization_profiles(organization):
        return "profile"
    if declaring_habilitations(organization, day):
        return "habilitation"
    return None


def organization_capabilities(organization, day=None) -> frozenset[str]:
    profiles = organization_profiles(organization)
    features = set().union(*(PROFILE_FEATURES.get(p, frozenset()) for p in profiles))
    profile = getattr(organization, "business_profile", None)
    if profile is not None:
        features |= {f for f in profile.features if f in KNOWN_FEATURES}
    features.discard("declaration")
    if declaration_basis(organization, day):
        features.add("declaration")
    return frozenset(features)


def has_feature(user, organization, feature):
    if feature not in KNOWN_FEATURES or not organization or not organization.active:
        return False
    if not active_memberships(user).filter(organization=organization).exists():
        return False
    return feature in organization_capabilities(organization)


def require_capability(organization, feature: str) -> None:
    """Refuse côté serveur une action que les capacités de la société n'ouvrent pas."""
    from apps.core.exceptions import ApiError

    if feature not in organization_capabilities(organization):
        raise ApiError(
            "CAPABILITY_REQUIRED",
            "Cette action demande une habilitation que la société n'a pas.",
            403,
            {"capability": feature},
        )
