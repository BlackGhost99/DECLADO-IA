"""Permissions serveur : société active obligatoire, puis rôles éventuels."""

from rest_framework.permissions import BasePermission

from apps.core.exceptions import ApiError

from .context import resolve_membership


class HasActiveOrganization(BasePermission):
    """Exige une affiliation active à la société sélectionnée et l'expose sur la requête."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        membership = resolve_membership(request)
        if membership is None:
            raise ApiError(
                "NO_ACTIVE_ORGANIZATION",
                "Sélectionnez une société active.",
                http_status=403,
            )
        request.membership = membership
        request.organization = membership.organization
        return True


def require_roles(*roles: str, safe_methods_open: bool = False):
    """Fabrique une permission exigeant l'un des rôles donnés dans la société active.

    Avec safe_methods_open=True, la lecture reste ouverte à tout membre actif.
    """

    class _RequireRoles(HasActiveOrganization):
        message = "Rôle insuffisant pour cette action."

        def has_permission(self, request, view):
            if not super().has_permission(request, view):
                return False
            if safe_methods_open and request.method in ("GET", "HEAD", "OPTIONS"):
                return True
            return request.membership.has_role(*roles)

    _RequireRoles.__name__ = "Require_" + "_or_".join(roles)
    return _RequireRoles
