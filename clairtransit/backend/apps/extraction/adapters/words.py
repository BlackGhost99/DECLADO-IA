"""Mots positionnés (PDF texte ou OCR) regroupés en rangées pour la structuration."""

from ..layout import Item, Page, Row
from ..schema import Span


def rows_from_words(words: list[dict], *, page_number: int, width: float, height: float, rotation: int = 0) -> Page:
    """words : dicts text/x0/x1/top/bottom (unités de la page) et confidence facultative."""
    ordered = sorted(words, key=lambda w: (w["top"], w["x0"]))
    bands: list[list[dict]] = []
    for word in ordered:
        center = (word["top"] + word["bottom"]) / 2
        if bands:
            top = min(w["top"] for w in bands[-1])
            bottom = max(w["bottom"] for w in bands[-1])
            if top <= center <= bottom:
                bands[-1].append(word)
                continue
        bands.append([word])
    rows = []
    heights = []
    for index, band in enumerate(bands):
        items = []
        for w in sorted(band, key=lambda w: w["x0"]):
            bbox = (
                round(w["x0"] / width, 5),
                round(w["top"] / height, 5),
                round(w["x1"] / width, 5),
                round(w["bottom"] / height, 5),
            )
            span = Span(page=page_number, bbox=bbox, page_size=(round(width, 2), round(height, 2)), rotation=rotation)
            items.append(Item(text=w["text"], x0=w["x0"], x1=w["x1"], span=span, confidence=w.get("confidence")))
            heights.append(w["bottom"] - w["top"])
        rows.append(Row(items=items, page=page_number, index=index))
    typical = sorted(heights)[len(heights) // 2] if heights else 10.0
    # Deux mots d'un même titre sont séparés d'une espace ; deux colonnes, d'un vide plus large.
    return Page(number=page_number, rows=rows, merge_gap=0.8 * typical)
