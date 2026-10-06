"""Outbox : événement enregistré avec la donnée, traitement idempotent et borné."""

from django.db import transaction

from apps.core import outbox
from apps.core.models import OutboxEvent


def test_dispatch_is_idempotent(db):
    with transaction.atomic():
        event = outbox.enqueue("system.ping", {"n": 1})
    assert outbox.dispatch_pending() == 1
    assert outbox.dispatch_pending() == 0
    event.refresh_from_db()
    assert event.dispatched_at is not None and event.attempts == 1


def test_rolled_back_transaction_leaves_no_event(db):
    try:
        with transaction.atomic():
            outbox.enqueue("system.ping", {})
            raise RuntimeError
    except RuntimeError:
        pass
    assert not OutboxEvent.objects.exists()


def test_failures_are_visible_and_bounded(db):
    calls = []

    @outbox.register_handler("test.boom")
    def boom(event):
        calls.append(event.id)
        raise ValueError("boom")

    event = outbox.enqueue("test.boom", {})
    outbox.dispatch_pending()
    outbox.dispatch_pending()
    assert len(calls) == 1  # nouvelle tentative différée, pas immédiate
    event.refresh_from_db()
    assert event.available_at > event.created_at
    for _ in range(outbox.MAX_ATTEMPTS + 3):
        OutboxEvent.objects.update(available_at=None)  # le délai est écoulé
        outbox.dispatch_pending()
    event.refresh_from_db()
    assert len(calls) == outbox.MAX_ATTEMPTS
    assert event.dispatched_at is None and event.last_error == "ValueError"


def test_claimed_event_is_not_given_twice(db):
    calls = []

    @outbox.register_handler("test.reentrant")
    def reentrant(event):
        calls.append(event.id)
        # Un second worker qui interroge pendant le traitement ne reçoit pas le même événement.
        assert outbox.dispatch_pending() == 0

    outbox.enqueue("test.reentrant", {})
    assert outbox.dispatch_pending() == 1
    assert len(calls) == 1
