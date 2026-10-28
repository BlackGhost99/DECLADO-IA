"""Mots d'une page PDF sans le filigrane : « DOCUMENT FICTIF », « COPIE », « SPECIMEN »…

Un filigrane est écrit en biais, ou en très grands caractères pâles. Ses lettres tombent au milieu
du texte (« SubtRotal », « CTOTAL A PAYER ») et cassent la lecture : elles sont retirées avant le
regroupement en mots. Un titre en gras ou un en-tête blanc sur fond foncé restent lus.
"""

LARGE = 2.5  # fois la taille médiane des caractères de la page
TILT = 0.1  # rotation au-delà de laquelle un caractère n'est ni horizontal ni vertical


def _pale(color) -> bool:
    if color is None:
        return False
    values = tuple(color) if isinstance(color, list | tuple) else (color,)
    if not all(isinstance(v, int | float) for v in values):
        return False  # motif ou couleur nommée : on ne devine pas
    if len(values) in (1, 3):  # gris ou RGB
        return min(values) >= 0.8
    if len(values) == 4:  # CMJN
        return max(values) <= 0.2
    return False


def _tilted(char) -> bool:
    a, b, c, d = (float(v) for v in char.get("matrix", (1, 0, 0, 1))[:4])
    return abs(b) > TILT * abs(a) and abs(a) > TILT * abs(b) or abs(c) > TILT * abs(d) and abs(d) > TILT * abs(c)


def watermark_filter(page):
    """Page sans les caractères du filigrane (en biais, ou grands et pâles)."""
    sizes = sorted(float(c["size"]) for c in page.chars)
    if not sizes:
        return page
    large = LARGE * sizes[len(sizes) // 2]

    def keep(obj) -> bool:
        if obj.get("object_type") != "char":
            return True
        return not (_tilted(obj) or (float(obj["size"]) >= large and _pale(obj.get("non_stroking_color"))))

    return page.filter(keep)


def page_words(page) -> list[dict]:
    return watermark_filter(page).extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=2)
