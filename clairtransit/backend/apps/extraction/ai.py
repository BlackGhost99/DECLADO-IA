"""Interface d'IA remplaçable (ADR-008, § 12 de la conception) : aucun fournisseur n'est raccordé.

DEV-019 demande d'évaluer l'IA sur un corpus puis de raccorder le fournisseur retenu seulement
après le choix du prestataire, de la localisation, de la conservation des données et des secrets.
Rien de cela n'est décidé : le seul adaptateur est « disabled », qui refuse explicitement. Il ne
doit jamais être présenté comme une IA opérationnelle. Le parcours fonctionne sans lui.

Le contrôle des sorties est en place dès maintenant : un futur adaptateur ne pourra proposer que
des lignes du référentiel fournies en entrée, avec des citations retrouvables.
"""

from dataclasses import dataclass
from typing import Protocol

from django.conf import settings


class AIUnavailable(Exception):
    code = "AI_DISABLED"
    message = "Aucun fournisseur d'IA n'est raccordé : extraction classique et saisie manuelle uniquement."


class AIProvider(Protocol):
    name: str

    def extract_document(self, *, text: str, schema: dict) -> dict: ...

    def enrich_goods_description(self, *, description: str) -> dict: ...

    def rank_candidates(self, *, description: str, candidates: list[dict]) -> list[dict]: ...

    def explain_candidate(self, *, description: str, candidate: dict) -> dict: ...


class DisabledProvider:
    name = "disabled"

    def _refuse(self, **_kwargs):
        raise AIUnavailable()

    extract_document = enrich_goods_description = rank_candidates = explain_candidate = _refuse


def get_provider() -> AIProvider:
    if settings.AI_PROVIDER == "disabled":
        return DisabledProvider()
    raise AIUnavailable()  # aucun autre adaptateur n'existe : pas de repli silencieux


def is_enabled() -> bool:
    return settings.AI_PROVIDER != "disabled"


@dataclass
class Rejection:
    index: int
    reason: str


def validate_ranking(output: list[dict], *, allowed: dict[str, str], sources: set[str]) -> tuple[list[dict], list]:
    """Contrôle de sortie : chaque candidat doit être un nœud fourni (identifiant et code concordants)
    et chaque citation une source réellement transmise. Le reste est rejeté, jamais réparé."""
    accepted, rejected = [], []
    for index, item in enumerate(output if isinstance(output, list) else []):
        if not isinstance(item, dict):
            rejected.append(Rejection(index, "Format inattendu."))
            continue
        node_id, code = str(item.get("node_id", "")), str(item.get("code", ""))
        if node_id not in allowed:
            rejected.append(Rejection(index, "Ligne absente des candidats fournis : code inventé rejeté."))
            continue
        if allowed[node_id] != code:
            rejected.append(Rejection(index, "Code différent de celui de la ligne citée."))
            continue
        citations = item.get("citations") or []
        if not citations or any(str(c) not in sources for c in citations):
            rejected.append(Rejection(index, "Preuve introuvable : proposition invalidée."))
            continue
        accepted.append({"node_id": node_id, "code": code, "citations": [str(c) for c in citations]})
    return accepted, rejected
