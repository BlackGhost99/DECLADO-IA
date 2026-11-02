"""Notes de fonctionnement mises de côté pendant une requête, écrites après sa réponse.

Une pièce refusée lève une erreur : la transaction de la requête est annulée, et une note écrite
dedans disparaîtrait avec elle. La note attend donc la fin de la requête (middleware). Hors requête
(tâche de fond, commande), elle est écrite tout de suite.
"""

import logging
from contextvars import ContextVar

from apps.core.middleware import get_request_id

logger = logging.getLogger(__name__)

_pending: ContextVar[list | None] = ContextVar("supervision_pending", default=None)


def note(*, category, level, code, message="", organization=None, actor=None, details=None) -> None:
    item = {
        "category": category,
        "level": level,
        "code": (code or "")[:60],
        "message": (message or "")[:300],
        "organization_id": getattr(organization, "id", None),
        "actor_id": getattr(actor, "id", None) if getattr(actor, "is_authenticated", False) else None,
        "request_id": get_request_id() if get_request_id() != "-" else "",
        "details": details or {},
    }
    pending = _pending.get()
    if pending is None:
        _write([item])
    else:
        pending.append(item)


def noted(code: str) -> bool:
    """Une note de ce code attend déjà : l'erreur générique de la requête ne la répète pas."""
    return any(item["code"] == code for item in _pending.get() or [])


def _write(items: list[dict]) -> None:
    from .models import OperationalEvent

    for item in items:
        try:
            OperationalEvent.objects.create(**item)
        except Exception:  # une note ne doit jamais casser la réponse
            logger.exception("Note de fonctionnement non écrite : %s", item["code"])


class SupervisionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _pending.set([])
        try:
            response = self.get_response(request)
        finally:
            pending = _pending.get() or []
            _pending.reset(token)
            # Hors de la transaction de la vue : la note survit à l'annulation de la requête.
            _write(pending)
        return response
