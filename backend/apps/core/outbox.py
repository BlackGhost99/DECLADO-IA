"""Table outbox : enregistrement transactionnel des événements et distribution idempotente."""

import logging
from collections.abc import Callable
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import OutboxEvent

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
# Durée pendant laquelle un événement pris en charge n'est pas redonné à un autre worker.
LEASE = timedelta(minutes=30)
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


def _backoff(attempts: int) -> timedelta:
    """Temporisation progressive entre deux tentatives : 30 s, 1 min, 2 min, 4 min…"""
    return timedelta(seconds=30 * 2 ** max(attempts - 1, 0))


def _claim(now) -> OutboxEvent | None:
    with transaction.atomic():
        event = (
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(dispatched_at__isnull=True, attempts__lt=MAX_ATTEMPTS)
            .filter(Q(available_at__isnull=True) | Q(available_at__lte=now))
            .order_by("created_at")
            .first()
        )
        if event is None:
            return None
        event.attempts += 1
        event.available_at = now + LEASE
        event.save(update_fields=["attempts", "available_at"])
        return event


def dispatch_pending(limit: int = 100) -> int:
    """Traite les événements en attente. Retourne le nombre d'événements terminés.

    Chaque événement est pris sous bail dans une courte transaction, puis traité hors de
    celle-ci : un traitement long (extraction, OCR) publie son avancement au fil de l'eau.
    Le gestionnaire est donc responsable de ses propres transactions et doit être idempotent.
    """
    done = 0
    for _ in range(limit):
        now = timezone.now()
        event = _claim(now)
        if event is None:
            break
        handler = _handlers.get(event.topic)
        if handler is None:
            OutboxEvent.objects.filter(pk=event.pk).update(
                last_error="NO_HANDLER", available_at=now + _backoff(event.attempts)
            )
            continue
        try:
            handler(event)
        except Exception as exc:  # erreur récupérable, visible, bornée et espacée
            OutboxEvent.objects.filter(pk=event.pk).update(
                last_error=type(exc).__name__[:200], available_at=timezone.now() + _backoff(event.attempts)
            )
            logger.exception("Échec du traitement de l'événement %s", event.id)
            continue
        OutboxEvent.objects.filter(pk=event.pk).update(dispatched_at=timezone.now(), last_error="", available_at=None)
        done += 1
    return done


@register_handler("system.ping")
def _ping(event: OutboxEvent) -> None:
    """Événement de vérification de la chaîne outbox → worker."""
    logger.info("system.ping reçu (%s)", event.id)
