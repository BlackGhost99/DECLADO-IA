"""Valeurs placées à côté ou sous leur libellé (cellule « Invoice No. » puis « IIC-2026-7784 »).

Une pièce (facture, B/L, facture d'assurance) range souvent ses informations dans une grille :
un libellé, puis sa valeur dans la cellule de droite ou dans la rangée du dessous. Ce module
retrouve ces couples sans rien deviner : un libellé sans valeur lisible reste sans valeur (LEC-03).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from .layout import Item, Page, Row, _phrases
from .numbers import norm

# Forme juridique en fin de raison sociale : « Iberica Industrial Components S.L. » (LEC-01).
LEGAL_FORM = re.compile(
    r"\b(s\.?\s?l\.?|s\.?\s?a\.?\s?r\.?\s?l\.?|s\.?\s?a\.?\s?s\.?|s\.?\s?a\.?|e\.?u\.?r\.?l\.?|ltd\.?|limited|gmbh|"
    r"inc\.?|llc|b\.?v\.?|n\.?v\.?|s\.?p\.?a\.?|s\.?r\.?l\.?|plc|ag|co\.?,?\s?ltd\.?|corp\.?|corporation|"
    r"company|sarlu|sasu|sa\s+\w+)$"
)


@dataclass
class Found:
    items: list[Item]
    text: str
    label: str
    page: int | None


def _key(text: str) -> str:
    return norm(text).strip(" :.#-").replace(" .", ".")


def _label_index(labels: dict[str, tuple[str, ...]]) -> dict[str, str]:
    index = {}
    for field, names in labels.items():
        for name in names:
            index.setdefault(_key(name), field)
    return index


def _split_label(phrase: list[Item], index: dict[str, str]) -> tuple[str, int] | None:
    """Plus long préfixe de la phrase qui est un libellé connu : (champ, nombre de mots du libellé)."""
    for n in range(len(phrase), 0, -1):
        key = _key(" ".join(i.text for i in phrase[:n]))
        if key in index:
            return index[key], n
    return None


def _is_label(phrase: list[Item], index: dict[str, str]) -> bool:
    found = _split_label(phrase, index)
    return found is not None and found[1] == len(phrase)


def _text(items: list[Item]) -> str:
    return " ".join(i.text for i in items).strip(" :")


def _close_below(upper: Row, lower: Row) -> bool:
    a = [i.span.bbox for i in upper.items if i.span.bbox]
    b = [i.span.bbox for i in lower.items if i.span.bbox]
    if not a or not b:
        return lower.index == upper.index + 1
    height = max(box[3] - box[1] for box in a + b)
    # Une rangée de titres en petits caractères peut être séparée de ses valeurs par une marge de cellule.
    return min(box[1] for box in b) - max(box[3] for box in a) <= 2.5 * height


def _wrapped_labels(page: Page, index: dict[str, str]) -> tuple[dict[tuple[int, float], str], dict[int, Row]]:
    """Libellé de colonne coupé sur deux lignes (« MEASUREMEN » puis « T ») : texte complet par
    (rangée, début de cellule), et rangée de ces fins de libellé sous chaque rangée de libellés."""
    whole, tails = {}, {}
    for upper, lower in zip(page.rows, page.rows[1:], strict=False):
        if not _close_below(upper, lower):
            continue
        starts = {round(p[0].x0, 0): p for p in _phrases(upper.items, page.merge_gap)}
        merged = {}
        for tail in _phrases(lower.items, page.merge_gap):
            head = starts.get(round(tail[0].x0, 0))
            if head is None or any(ch.isdigit() for ch in _text(tail)):
                break
            text = next(
                (t for t in (_text(head) + _text(tail), f"{_text(head)} {_text(tail)}") if _key(t) in index), None
            )
            if text is None:
                break
            merged[(id(upper), head[0].x0)] = text
        else:
            if merged:
                whole.update(merged)
                tails[id(upper)] = lower
    return whole, tails


def labelled_values(
    pages: list[Page],
    labels: dict[str, tuple[str, ...]],
    *,
    skip: set[int] | None = None,
    accept: dict[str, Callable[[str], bool]] | None = None,
):
    """{champ: Found} : première valeur trouvée pour chaque libellé, dans l'ordre de lecture.

    accept : contrôle de forme par champ (un montant contient un nombre) ; une cellule voisine qui
    n'a pas la forme attendue (« TAUX ») n'est pas une valeur, on regarde alors sous le libellé."""
    accept = accept or {}
    index = _label_index(labels)
    known = _label_index(KNOWN_LABELS)
    # Un libellé courant d'un seul mot (« Origin », « Mode ») peut aussi être une valeur : il ne
    # borne une cellule que s'il fait partie des libellés demandés.
    all_labels = {k: v for k, v in _label_index(KNOWN_LABELS).items() if " " in k or "/" in k} | index
    found: dict[str, Found] = {}
    for page in pages:
        whole, tails = _wrapped_labels(page, all_labels)
        tail_ids = {id(t) for t in tails.values()}
        rows = [row for row in page.rows if id(row) not in tail_ids]
        for r, row in enumerate(rows):
            if skip and id(row) in skip:
                continue
            phrases = _phrases(row.items, page.merge_gap)
            for p, phrase in enumerate(phrases):
                wrapped = whole.get((id(row), phrase[0].x0))
                if wrapped is not None:
                    if _key(wrapped) not in index or index[_key(wrapped)] in found:
                        continue
                    field, size, label = index[_key(wrapped)], len(phrase), wrapped
                else:
                    if _key(_text(phrase)) in known and _key(_text(phrase)) not in index:
                        continue  # « Container type » est un autre libellé, pas « Container » suivi de « type »
                    split = _split_label(phrase, index)
                    if split is None:
                        continue
                    field, size = split
                    if field in found:
                        continue
                    label = _text(phrase[:size])
                ok = accept.get(field, bool)
                inline = phrase[size:]
                if inline and ok(_text(inline)):
                    found[field] = Found(inline, _text(inline), label, page.number)
                    continue
                # Valeur dans la cellule suivante de la même rangée, sauf si c'est déjà un autre libellé.
                following = phrases[p + 1 : p + 2]
                if following and not _is_label(following[0], all_labels) and ok(_text(following[0])):
                    found[field] = Found(following[0], _text(following[0]), label, page.number)
                    continue
                # Sinon, sous le libellé : dans la rangée suivante, entre les cellules voisines du libellé.
                left = phrases[p - 1][-1].x1 if p > 0 else float("-inf")
                right = phrases[p + 1][0].x0 if p + 1 < len(phrases) else float("inf")
                if r + 1 >= len(rows) or not _close_below(tails.get(id(row), row), rows[r + 1]):
                    continue
                below = _phrases(rows[r + 1].items, page.merge_gap)
                if any(_is_label(o, all_labels) and o[0].x0 <= phrase[-1].x1 for o in below):
                    continue  # nouvelle rangée de libellés : la cellule est vide
                cell = [o for o in below if left <= (o[0].x0 + o[-1].x1) / 2 < right and not _is_label(o, all_labels)]
                # D'abord ce qui est exactement sous le libellé, sinon la cellule la plus proche à sa
                # droite : une grille « libellé | valeur » dont les valeurs tombent une ligne plus bas.
                under = [o for o in cell if o[0].x0 <= phrase[-1].x1 and o[-1].x1 >= phrase[0].x0]
                beside = [o for o in cell if o[0].x0 >= phrase[0].x0 - page.merge_gap]
                pick = under[:1] or sorted(beside, key=lambda o: o[0].x0)[:1]
                if pick and ok(_text(pick[0])):
                    found[field] = Found(pick[0], _text(pick[0]), label, page.number)
    return found


# Libellés qui sont aussi des titres de pièce (« COMMERCIAL INVOICE ») : ils ne marquent pas le début de la grille.
TITLE_LIKE = {"related_invoice", "related_bl", "goods_description"}


def grid_labels() -> dict[str, str]:
    return {k: v for k, v in _label_index(KNOWN_LABELS).items() if v not in TITLE_LIKE}


def header_rows(page: Page, *, limit: int = 12) -> list[Row]:
    """Rangées de l'en-tête de la page, avant la première rangée qui porte un libellé de grille."""
    index = grid_labels()
    rows = []
    for row in page.rows[:limit]:
        if any(_split_label(p, index) for p in _phrases(row.items, page.merge_gap)):
            break
        rows.append(row)
    return rows


def letterhead_company(pages: list[Page]) -> Found | None:
    """Raison sociale en tête de la première page (forme juridique), avant la première grille."""
    if not pages:
        return None
    page = pages[0]
    for row in header_rows(page):
        phrases = _phrases(row.items, page.merge_gap)
        for phrase in phrases:
            text = _text(phrase)
            if LEGAL_FORM.search(norm(text)) and any(c.isalpha() for c in text):
                return Found(phrase, text, "En-tête", page.number)
    return None


# Libellés courants de toutes les pièces : ils bornent une valeur même s'ils ne sont pas demandés.
# Comparés sans accents ni majuscules (norm).
KNOWN_LABELS: dict[str, tuple[str, ...]] = {
    "invoice_number": ("invoice no.", "invoice no", "invoice number", "invoice #", "invoice n°", "facture no.",
                       "facture no", "facture n°", "n° facture", "n° de facture", "numero de facture", "factura no",
                       "factura n°", "certificate no.", "certificate no", "certificat n°", "attestation n°"),
    "invoice_date": ("invoice date", "date de facture", "date facture", "date", "fecha", "issue date", "date of issue",
                     "date d'emission", "date d emission"),
    "currency": ("currency", "devise", "monnaie", "moneda"),
    "supplier_name": ("supplier", "seller", "vendor", "exporter", "fournisseur", "vendeur", "exportateur",
                      "proveedor"),
    "buyer_name": ("bill to", "sold to", "buyer", "consignee", "importer", "importateur", "customer", "client",
                   "destinataire", "acheteur", "comprador", "assure", "insured"),
    "incoterm": ("incoterm", "incoterms", "terms of delivery", "conditions de livraison"),
    "purchase_order": ("purchase order", "p/o", "po no", "bon de commande", "pedido"),
    "country_of_origin": ("country of origin", "pays d'origine", "origin", "origine"),
    "payment_terms": ("payment terms", "conditions de paiement"),
    "destination": ("destination",),
    "related_bl": ("related b/l", "b/l de reference", "b/l ref", "bill of lading", "b/l"),
    "transport_number": ("b/l no.", "b/l no", "b/l number", "bl no", "bill of lading no", "n° b/l", "n° connaissement",
                         "connaissement n°", "awb no", "awb no.", "awb number", "lta n°", "cmr no",
                         "lettre de voiture n°"),
    "related_invoice": ("related invoice", "invoice ref", "facture commerciale", "commercial invoice", "facture liee",
                        "invoice"),
    "shipper": ("shipper", "chargeur", "expediteur"),
    "notify": ("notify party", "notify", "partie a notifier"),
    "vessel": ("vessel", "ocean vessel", "navire"),
    "voyage": ("voyage", "voyage no", "voyage no.", "voyage n°"),
    "port_of_loading": ("port of loading", "port de chargement", "pol"),
    "port_of_discharge": ("port of discharge", "port de dechargement", "pod"),
    "place_of_delivery": ("place of delivery", "lieu de livraison"),
    "container": ("container", "container no", "container no.", "conteneur", "container number"),
    "packages": ("packages", "no. of packages", "number of packages", "colis", "nombre de colis"),
    "gross_weight": ("gross weight", "poids brut", "gross weight (kg)"),
    "measurement": ("measurement", "volume", "cubage"),
    "freight_terms": ("freight terms", "freight payable at", "conditions de fret"),
    "policy_number": ("police / policy", "police", "policy", "policy no", "policy no.", "police n°", "n° de police"),
    "insured_value": ("base assuree", "valeur assuree", "sum insured", "insured value", "capital assure"),
    "goods_description": ("marchandises", "description of goods", "goods", "nature des marchandises"),
    "marks": ("marks & numbers", "marks and numbers", "marques et numeros"),
    "net_gross_weight": ("net/gross weight",),
    "customer_tax_ref": ("customer tax ref.", "customer tax ref", "tax id", "nif"),
    "no_of_originals": ("no. of originals", "number of originals"),
    "container_type": ("container type",),
    "shipment_type": ("shipment type",),
    "declared_cargo_value": ("declared cargo value",),
    "customs_reference": ("customs reference",),
    "mode": ("mode",),
    "risk_start": ("debut du risque",),
    "risk_end": ("fin du risque",),
    "status_note": ("statut",),
    "document_note": ("document",),
    "purpose": ("purpose",),
}  # fmt: skip
