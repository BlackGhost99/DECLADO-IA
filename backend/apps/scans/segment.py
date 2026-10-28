"""Découpage proposé d'un lot en pièces (NUM-04).

Règles, appliquées dans l'ordre des pages et expliquées à l'agent :
- une page blanche sépare deux pièces et sort du lot ;
- un titre reconnu ouvre une pièce de ce type, sauf s'il prolonge la pièce en cours
  (même type et même numéro, ou mention « page 2/3 ») ;
- la mention « page 1/N » ouvre une pièce, même sans titre reconnu ;
- une page sans titre prolonge la pièce en cours ; sans pièce en cours, elle reste « non classée ».
"""

from dataclasses import dataclass, field

from .titles import OTHER, PageReading


@dataclass
class PageInfo:
    id: object
    number: int  # numéro de la page dans le lot, tel qu'affiché
    blank: bool = False
    reading: PageReading = field(default_factory=PageReading)


@dataclass
class ProposedPiece:
    usage: str
    reason: str
    reference: str = ""
    page_ids: list = field(default_factory=list)


@dataclass
class Proposal:
    pieces: list[ProposedPiece] = field(default_factory=list)
    unclassified: list = field(default_factory=list)
    blank: list = field(default_factory=list)


def _continues(current: ProposedPiece | None, r: PageReading) -> bool:
    if current is None:
        return False
    if r.marker:
        return r.marker[0] > 1
    if not r.usage:
        return True
    return r.usage == current.usage and (not r.reference or not current.reference or r.reference == current.reference)


def propose(pages: list[PageInfo]) -> Proposal:
    out = Proposal()
    current: ProposedPiece | None = None
    for page in pages:
        if page.blank:
            out.blank.append(page.id)
            current = None
            continue
        r = page.reading
        if _continues(current, r):
            current.page_ids.append(page.id)
            if r.reference and not current.reference:
                current.reference = r.reference
            continue
        if r.usage:
            reason = f"titre « {r.label} » reconnu en haut de la page {page.number}"
            if r.reference:
                reason += f", n° {r.reference}"
            current = ProposedPiece(r.usage, reason, r.reference, [page.id])
        elif r.marker:
            mark = f"page {r.marker[0]}/{r.marker[1]}"
            current = ProposedPiece(OTHER, f"mention « {mark} » lue sur la page {page.number}", "", [page.id])
        else:
            out.unclassified.append(page.id)
            continue
        out.pieces.append(current)
    return out
