"""Format d'erreur structuré de l'API : {code, message, details, request_id}."""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .middleware import get_request_id


class ApiError(exceptions.APIException):
    """Erreur métier avec un code stable lisible par le client."""

    def __init__(self, code: str, message: str, http_status: int = 400, details: dict | None = None):
        self.status_code = http_status
        self.error_code = code
        self.details = details or {}
        super().__init__(detail=message, code=code)


class RevisionConflict(ApiError):
    def __init__(self, expected: int | None, current: int):
        super().__init__(
            "REVISION_CONFLICT",
            "L'élément a été modifié depuis votre ouverture.",
            status.HTTP_409_CONFLICT,
            {"expected_version": expected, "current_version": current},
        )


_DEFAULT_CODES = {
    400: ("INVALID_REQUEST", "Requête invalide."),
    401: ("NOT_AUTHENTICATED", "Connexion requise."),
    403: ("FORBIDDEN", "Action non autorisée."),
    404: ("NOT_FOUND", "Élément introuvable."),
    405: ("METHOD_NOT_ALLOWED", "Méthode non autorisée."),
    409: ("CONFLICT", "Conflit."),
    413: ("PAYLOAD_TOO_LARGE", "Contenu trop volumineux."),
    429: ("THROTTLED", "Trop de requêtes."),
}


def api_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        _note_failure(context, "SERVER_ERROR", 500, type(exc).__name__)
        return None

    # La session DRF renvoie 403 pour un utilisateur anonyme ; on expose 401.
    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        response.status_code = status.HTTP_401_UNAUTHORIZED

    default_code, default_message = _DEFAULT_CODES.get(response.status_code, ("ERROR", "Erreur."))
    if isinstance(exc, ApiError):
        code, message, details = exc.error_code, str(exc.detail), exc.details
    elif isinstance(exc, exceptions.ValidationError):
        code, message, details = "VALIDATION_ERROR", "Données invalides.", {"fields": response.data}
    else:
        code = default_code
        message = str(getattr(exc, "detail", default_message)) or default_message
        details = {}

    _note_failure(context, code, response.status_code, message)
    return Response(
        {"code": code, "message": message, "details": details, "request_id": get_request_id()},
        status=response.status_code,
        headers={k: v for k, v in response.items()},
    )


# Refus vus par l'utilisateur, notés pour la console de l'exploitant (supervision). Les lectures
# refusées (GET) et les accès non autorisés ne sont pas notés : ce ne sont pas des incidents.
_NOT_NOTED = {401, 403, 404, 405, 429}


def _note_failure(context, code: str, status_code: int, message: str) -> None:
    from apps.supervision import recorder

    request = context.get("request")
    if request is None or recorder.noted(code):
        return
    if status_code < 500 and (request.method in ("GET", "HEAD", "OPTIONS") or status_code in _NOT_NOTED):
        return
    match = getattr(request, "resolver_match", None)
    view = context.get("view")
    recorder.note(
        category="server" if status_code >= 500 else "request",
        level="error" if status_code >= 500 else "warning",
        code=code,
        # Une exception imprévue ne montre que sa classe : son texte peut contenir des données.
        message=message if status_code < 500 or code != "SERVER_ERROR" else f"Exception {message}",
        organization=getattr(request, "organization", None),
        actor=getattr(request, "user", None),
        details={
            "method": request.method,
            "route": getattr(match, "route", "") or "",
            "view": type(view).__name__ if view is not None else "",
            "http_status": status_code,
        },
    )
