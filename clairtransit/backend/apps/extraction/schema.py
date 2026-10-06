"""Schéma commun produit par tous les adaptateurs (PDF texte, OCR, XLSX).

Chaque valeur garde sa localisation et son statut : une valeur absente ou illisible reste
inconnue (None), jamais remplacée par zéro ou par une supposition non étiquetée.
"""

from dataclasses import dataclass, field
from decimal import Decimal


class Origin:
    READ = "read"  # lu tel quel dans le document
    INFERRED = "inferred"  # déduit (séparateur décimal, pays depuis un nom) : à vérifier
    OCR = "ocr"  # lu par reconnaissance de caractères


class Status:
    OK = "ok"
    MISSING = "missing"  # rien dans le document
    AMBIGUOUS = "ambiguous"  # plusieurs lectures possibles
    UNREADABLE = "unreadable"  # présent mais illisible
    TRUNCATED = "truncated"  # visiblement coupé
    LOW_CONFIDENCE = "low_confidence"  # OCR peu sûr


@dataclass
class Span:
    """Localisation vérifiable. Page physique à partir de 1 ; bbox normalisée 0–1 depuis le coin
    supérieur gauche de la page rendue (x0, y0, x1, y1). Excel : feuille et plage A1, sans page."""

    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    sheet: str = ""
    cell_range: str = ""
    excerpt: str = ""
    page_size: tuple[float, float] | None = None
    rotation: int = 0


@dataclass
class Value:
    raw: str | None
    parsed: object = None  # Decimal, date, str ; None = inconnu
    status: str = Status.OK
    origin: str = Origin.READ
    span: Span | None = None
    confidence: float | None = None
    notes: list[str] = field(default_factory=list)
    label: str = ""  # libellé du champ ou de la colonne source

    @classmethod
    def missing(cls, label: str = "", note: str = "") -> "Value":
        return cls(raw=None, parsed=None, status=Status.MISSING, label=label, notes=[note] if note else [])

    @property
    def needs_review(self) -> bool:
        return self.status != Status.OK or self.origin == Origin.INFERRED


@dataclass
class CodeCandidate:
    """Code présent sur la ligne, avec la nature déduite de son libellé (EXT-04, COD-01)."""

    raw: str
    kind: str  # customs / supplier / ambiguous
    label: str
    claimed_scheme: str = ""
    span: Span | None = None
    origin: str = Origin.READ
    findings: list[str] = field(default_factory=list)


class RowKind:
    GOODS = "goods"
    SUBTOTAL = "subtotal"
    FEE = "fee"
    DISCOUNT = "discount"
    TAX = "tax"
    TOTAL = "total"
    HEADER = "header"
    REPEATED_HEADER = "repeated_header"
    CARRIED = "carried"  # report / à reporter


@dataclass
class ParsedLine:
    fields: dict[str, Value]
    codes: list[CodeCandidate] = field(default_factory=list)
    page: int | None = None
    span: Span | None = None
    warnings: list[dict] = field(default_factory=list)


@dataclass
class Charge:
    """Ligne qui n'est pas une marchandise : frais, remise, taxe, sous-total, total imprimé."""

    kind: str
    label: str
    amount: Value
    span: Span | None = None
    page: int | None = None


@dataclass
class ParsedDocument:
    header: dict[str, Value] = field(default_factory=dict)
    lines: list[ParsedLine] = field(default_factory=list)
    charges: list[Charge] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


HEADER_FIELDS = ("supplier_name", "invoice_number", "invoice_date", "currency", "incoterm", "declared_total")
LINE_FIELDS = ("source_reference", "description_raw", "quantity", "unit", "unit_price", "amount", "origin_country")


def warning(code: str, message: str, **details) -> dict:
    return {"code": code, "message": message, **({"details": details} if details else {})}


def plain(value):
    """Comme jsonable, sans les zéros de remplissage de la précision de stockage (« 3 » et non « 3.00000000 »)."""
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return jsonable(value)


def jsonable(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
