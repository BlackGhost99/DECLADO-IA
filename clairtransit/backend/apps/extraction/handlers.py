"""Gestionnaire outbox : l'exécution d'une extraction demandée dans une transaction métier."""

from apps.core.outbox import register_handler

from . import services


@register_handler(services.TOPIC)
def run_extraction(event) -> None:
    services.execute(event.payload["run_id"])
