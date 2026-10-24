"""Gestionnaire outbox : lecture d'un lot numérisé demandée dans une transaction métier."""

from apps.core.outbox import register_handler

from . import services


@register_handler(services.TOPIC)
def process_batch(event) -> None:
    services.process(event.payload["batch_id"], event.payload.get("job_id"))
