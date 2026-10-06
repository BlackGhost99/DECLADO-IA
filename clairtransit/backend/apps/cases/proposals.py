"""Aide au classement justifiée (DEV-018, COD-04 à COD-06, REC-01) sans IA.

Les propositions viennent du référentiel de l'édition contrôlée, avec la raison de leur présence,
le chemin complet, les notes du chapitre et les libellés qui les distinguent. Elles ne sont
produites que si le code est absent, incomplet, introuvable ou ambigu, ou sur demande explicite :
un code présent et retrouvé suit le chemin court de la confirmation (COD-03).
"""

import hashlib
import re

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramSimilarity
from django.db import transaction

from apps.core.exceptions import ApiError
from apps.tariffs.models import LegalNote, PublicationState, TariffNode
from apps.tariffs.text import search_normalize

from . import codecheck
from .models import ClassificationProposal, CodeCheck, GoodsLine, ProposalSet

PRODUCER = "recherche-referentiel 1.0"
MAX_PROPOSALS = 10
S = CodeCheck.State
STOPWORDS = {
    "de", "des", "du", "la", "le", "les", "en", "et", "au", "aux", "pour", "avec", "sans", "sur", "par", "un",
    "une", "the", "of", "for", "and", "with", "fictif", "fictive", "fictifs", "fictives", "fictitious", "lot",
    "piece", "pieces", "article", "articles", "modele", "type", "ref", "divers",
}  # fmt: skip
GENERIC_QUESTIONS = [
    "De quelle matière la marchandise est-elle faite ?",
    "À quoi sert-elle (usage principal) ?",
    "Sous quelle forme est-elle présentée (brute, transformée, neuve, usagée, en pièces) ?",
]


def keywords(text: str) -> list[str]:
    words = re.findall(r"[a-z]+", search_normalize(text))
    seen, result = set(), []
    for word in words:
        if len(word) >= 3 and word not in STOPWORDS and word not in seen:
            seen.add(word)
            result.append(word)
    return result[:8]


def _matched_terms(words: list[str], node: TariffNode) -> list[str]:
    haystack = search_normalize(f"{node.search_text} {node.full_path_label}")
    # Racine de cinq lettres : « reproducteurs » retrouve « reproducteur ».
    return [w for w in words if w in haystack or (len(w) > 5 and w[:5] in haystack)]


def _declarable_under(edition, code: str, limit: int) -> list[TariffNode]:
    return list(
        TariffNode.objects.filter(edition=edition, declarable=True, code__startswith=code)
        .exclude(code=code)
        .order_by("code")[:limit]
    )


def _text_hits(edition, words: list[str], query: str) -> list[tuple[TariffNode, float]]:
    if not words:
        return []
    base = TariffNode.objects.filter(edition=edition)
    vector = SearchVector("search_text", config="french")
    ts_query = SearchQuery(" OR ".join(words), config="french", search_type="websearch")
    hits = list(
        base.annotate(document=vector, rank=SearchRank(vector, ts_query))
        .filter(document=ts_query)
        .order_by("-rank", "code")[:30]
    )
    scored = [(n, float(n.rank)) for n in hits]
    if len(scored) < 3:
        normalized = search_normalize(query)
        seen = {n.pk for n, _ in scored}
        for node in (
            base.annotate(sim=TrigramSimilarity("search_text", normalized)).filter(sim__gt=0.2).order_by("-sim")[:10]
        ):
            if node.pk not in seen:
                scored.append((node, float(node.sim)))
    return scored


def _notes(edition, node: TariffNode) -> list[dict]:
    if not node.code or len(node.code) < 2:
        return []
    notes = LegalNote.objects.filter(edition=edition, scope_type="chapter", scope_ref=node.code[:2])[:5]
    return [
        {
            "id": str(n.id),
            "scope": f"Chapitre {n.scope_ref}",
            "heading": n.heading,
            "excerpt": n.text_raw[:240],
            "mentions_exclusion": bool(re.search(r"ne (comprend|couvre) pas|à l'exclusion|exclu", n.text_raw, re.I)),
        }
        for n in notes
    ]


@transaction.atomic
def propose(*, org, actor, goods: GoodsLine, edition, query: str = "", explicit: bool = False) -> ProposalSet:
    from apps.tariffs import services as tariffs

    visible = tariffs.visible_editions(actor).exclude(publication_state=PublicationState.WITHDRAWN)
    check = goods.code_checks.select_related("observation").first()
    current = (
        check is not None
        and check.target_edition_id == edition.id
        and check.checked_input_hash == codecheck.code_inputs_hash(goods, edition.id)
    )
    if current:
        state, observation, findings = check.state, check.observation, check.findings
    else:
        check = None
        result = codecheck.evaluate(goods, edition, visible)
        state, observation, findings = result["state"], result["observation"], result["findings"]
    if state == S.RECOGNIZED and not explicit:
        raise ApiError(
            "PROPOSALS_NOT_NEEDED",
            "Le code présent est retrouvé dans l'édition : le confirmer. D'autres pistes ne sont proposées "
            "que sur demande explicite.",
            409,
        )
    query = (query or "").strip() or " ".join(
        [goods.description] + [str(v) for v in (goods.attributes or {}).values() if isinstance(v, str | int)]
    )
    words = keywords(query)
    candidates: list[tuple[TariffNode, list[str], float | None]] = []
    seen: set = set()

    def add(node, reasons, score=None):
        if node.pk in seen or not node.declarable or len(candidates) >= MAX_PROPOSALS:
            return
        seen.add(node.pk)
        candidates.append((node, reasons, score))

    code = observation.normalized_code if observation else None
    questions: list[str] = []
    if state == S.INCOMPLETE and code:
        for node in _declarable_under(edition, code, MAX_PROPOSALS):
            add(node, [f"Subdivision du code présent « {observation.raw_code} »."])
        questions.append("Le code présent est incomplet : quelle subdivision correspond à la marchandise ?")
    elif state == S.NOT_FOUND and code:
        prefix = next(
            (
                f["details"]["nearest_existing_prefix"]
                for f in findings
                if f.get("details", {}).get("nearest_existing_prefix")
            ),
            None,
        )
        if prefix:
            for node in _declarable_under(edition, prefix, 5):
                add(node, [f"Même début « {prefix} » que le code présent « {observation.raw_code} », introuvable."])
    elif state == S.EDITION_MISMATCH and code:
        other = TariffNode.objects.filter(edition__in=visible.exclude(pk=edition.pk), code=code).first()
        if other:
            words = keywords(f"{other.label_clean} {query}")
            questions.append(
                f"Le code « {observation.raw_code} » existe dans « {other.edition.label} » seulement : "
                "une correspondance documentée est nécessaire."
            )
    for node, score in _text_hits(edition, words, query):
        terms = _matched_terms(words, node)
        reason = f"Termes communs avec la désignation : {', '.join(terms)}." if terms else "Proximité orthographique."
        if node.declarable:
            add(node, [reason], score)
        elif node.code:
            for child in _declarable_under(edition, node.code, 4):
                add(
                    child,
                    [f"Subdivision de « {node.code_display or node.code} » ({node.label_clean[:60]}).", reason],
                    score,
                )
    if not candidates:
        questions.append(
            f"Aucune ligne de l'édition ne correspond à « {query[:80]} » : préciser la désignation."
            if words
            else "La désignation est trop courte pour chercher : la préciser."
        )
        questions += GENERIC_QUESTIONS
    # Candidats d'une même position (quatre premiers chiffres) : leurs libellés les distinguent.
    by_parent: dict = {}
    for node, _r, _s in candidates:
        by_parent.setdefault(_heading(node), []).append(node)
    for siblings in by_parent.values():
        if len(siblings) > 1:
            labels = " ; ".join(f"« {n.label_clean[:50]} »" for n in siblings[:5])
            questions.append(f"Laquelle de ces caractéristiques s'applique : {labels} ?")
    digest = _digest(goods, edition.id, query)
    proposal_set = ProposalSet.objects.create(
        organization=org,
        goods_line=goods,
        code_check=check,
        edition=edition,
        trigger="explicit" if state == S.RECOGNIZED else state,
        query=query[:1000],
        producer=PRODUCER,
        questions=questions,
        input_hash=digest,
        created_by=actor,
    )
    for rank, (node, reasons, score) in enumerate(candidates, start=1):
        siblings = [n for n in by_parent.get(_heading(node), []) if n.pk != node.pk]
        ClassificationProposal.objects.create(
            organization=org,
            proposal_set=proposal_set,
            node=node,
            code=node.code,
            rank=rank,
            reasons=reasons,
            note_refs=_notes(edition, node),
            distinguishing=[
                {"code": n.code, "code_display": n.code_display, "label": n.label_clean} for n in siblings[:5]
            ],
            retrieval_score=round(score, 4) if score is not None else None,
        )
    return proposal_set


def _heading(node: TariffNode):
    return node.code[:4] if node.code and len(node.code) >= 4 else node.parent_id


def _digest(goods, edition_id, query: str) -> str:
    """Les propositions deviennent périmées dès que la marchandise ou son code changent."""
    return hashlib.sha256(f"{codecheck.code_inputs_hash(goods, edition_id)}|{query}".encode()).hexdigest()


def payload(proposal_set: ProposalSet) -> dict:
    return {
        "id": str(proposal_set.id),
        "goods_line_id": str(proposal_set.goods_line_id),
        "edition_id": str(proposal_set.edition_id),
        "edition_label": proposal_set.edition.label,
        "trigger": proposal_set.trigger,
        "query": proposal_set.query,
        "producer": proposal_set.producer,
        "is_ai": False,
        "questions": proposal_set.questions,
        "is_current": proposal_set.input_hash
        == _digest(proposal_set.goods_line, proposal_set.edition_id, proposal_set.query),
        "created_at": proposal_set.created_at,
        "created_by": proposal_set.created_by.email,
        "proposals": [
            {
                "id": str(p.id),
                "rank": p.rank,
                "node_id": str(p.node_id),
                "code": p.code,
                "code_display": p.node.code_display,
                "label": p.node.label_clean,
                "full_path": p.node.full_path_label,
                "reasons": p.reasons,
                "notes": p.note_refs,
                "distinguishing": p.distinguishing,
                "retrieval_score": p.retrieval_score,
            }
            for p in proposal_set.proposals.select_related("node")
        ],
    }
