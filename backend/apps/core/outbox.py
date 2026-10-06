"""Table outbox : enregistrement transactionnel des événements et distribution idempotente."""

import logging
from collections.abc import Callable

from django.db import transaction
from django.utils import timezone

from .models import OutboxEvent

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
_handlers: dict[str, Callable[[OutboxEvent], None]] = {}


def register_handler(topic: str):
    def decorator(func):
        _handlers[topic] = func
        return func

    return decorator


def enqueue(topic: str, payload: dict, organization=None) -> OutboxEvent:
    """À appeler dans la transaction qui modifie la donnée métier."""
    event = OutboxEvent.objects.create(topic=topic, payload=payload, organization=organization)

    def _kick():
        from .tasks import dispatch_outbox

        try:
            dispatch_outbox.delay()
        except Exception:  # courtier indisponible : l'événement reste en attente
            logger.warning("Courtier indisponible, événement %s en attente", event.id)

    transaction.on_commit(_kick)
    return event


def dispatch_pending(limit: int = 100) -> int:
    """Traite les événements en attente. Retourne le nombre d'événements terminés."""
    done = 0
    with transaction.atomic():
        pending = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(dispatched_at__isnull=True, attempts__lt=MAX_ATTEMPTS)
            .order_by("created_at")[:limit]
        )
        for event in pending:
            handler = _handlers.get(event.topic)
            event.attempts += 1
            if handler is None:
                event.last_error = "NO_HANDLER"
                event.save(update_fields=["attempts", "last_error"])
                continue
            try:
                with transaction.atomic():
                    handler(event)
            except Exception as exc:  # erreur récupérable, visible et bornée
                event.last_error = type(exc).__name__[:200]
                event.save(update_fields=["attempts", "last_error"])
                logger.exception("Échec du traitement de l'événement %s", event.id)
                continue
            event.dispatched_at = timezone.now()
            event.last_error = ""
            event.save(update_fields=["attempts", "dispatched_at", "last_error"])
            done += 1
    return done


@register_handler("system.ping")
def _ping(event: OutboxEvent) -> None:
    """Événement de vérification de la chaîne outbox → worker."""
    logger.info("system.ping reçu (%s)", event.id)
