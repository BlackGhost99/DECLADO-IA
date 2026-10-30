"""Structuration commune : lignes de texte localisées → en-tête de facture, lignes, frais, totaux.

Les adaptateurs (PDF texte, OCR, XLSX) fournissent des rangées d'éléments positionnés. Ce module
repère la ligne de titres du tableau, rattache chaque élément à sa colonne, classe les rangées
(marchandise, sous-total, frais, remise, taxe, total, en-tête répété) et lit les valeurs sans
jamais inventer une valeur absente (EXT-01 à EXT-08).
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from apps.tariffs.codes import normalize_code

from . import codes as codemod
from .numbers import (
    document_decimal_hint,
    looks_numeric,
    norm,
    parse_amount,
    parse_country,
    parse_currency,
    parse_date,
    split_quantity_unit,
)
from .schema import (
    Charge,
    CodeCandidate,
    Origin,
    ParsedDocument,
    ParsedLine,
    RowKind,
    Span,
    Status,
    Value,
    warning,
)

OCR_MIN_CONFIDENCE = 60.0


@dataclass
class Item:
    """Mot (PDF, OCR) ou cellule (XLSX). x0/x1 : abscisses (colonne pour Excel)."""

    text: str
    x0: float
    x1: float
    span: Span
    confidence: float | None = None
    typed: object = None  # valeur native d'une cellule Excel (Decimal, date)
    notes: list[str] = field(default_factory=list)


@dataclass
class Row:
    items: list[Item]
    page: int | None
    index: int  # ordre dans la page ou la feuille

    @property
    def text(self) -> str:
        return " ".join(i.text for i in self.items)


@dataclass
class Page:
    number: int | None  # page physique (PDF) ; None pour une feuille Excel
    rows: list[Row]
    merge_gap: float  # écart maximal entre deux mots d'un même titre de colonne
    sheet: str = ""
    exact_columns: bool = False  # Excel : une cellule n'appartient qu'à la colonne de son titre
    origin: str = Origin.READ


@dataclass
class Column:
    role: str
    label: str
    x0: float
    x1: float


ROLE_LABELS = {
    "description": ("designation", "description", "libelle", "produit", "marchandise", "goods", "description of goods",
                    "nature des marchandises", "articles"),
    "quantity": ("qte", "qte.", "quantite", "qty", "qty.", "quantity", "nombre", "nb"),
    "unit": ("unite", "unit", "u", "uom", "um"),
    "unit_price": ("prix unitaire", "p.u.", "pu", "p.u", "unit price", "prix u.", "prix", "price", "prix unit.",
                   "unit cost"),
    "amount": ("montant", "total", "amount", "montant ht", "total ht", "value", "valeur", "line total", "prix total",
               "total line"),
    "origin": ("origine", "origin", "pays d'origine", "country of origin", "coo", "pays"),
}  # fmt: skip
CODE_ROLE = {codemod.CUSTOMS: "customs_code", codemod.SUPPLIER: "reference", codemod.AMBIGUOUS: "uncertain_code"}

_CARRIED = re.compile(r"\b(a reporter|report|reporte|carried forward|brought forward)\b")
_SUBTOTAL = re.compile(r"\b(sous-total|sous total|subtotal|sub-total|total page|total partiel)\b")
_TAX = re.compile(r"^(tva|vat|taxe|tax)\b")
_DISCOUNT = re.compile(r"^(remise|rabais|escompte|ristourne|discount)\b")
# « Ocean freight », « Frais de port » ; « Port de déchargement » est un lieu, pas un frais (LEC-04).
_FEE = re.compile(
    r"^(?:(?:ocean|sea|air|road|inland|international|maritime)\s+)?"
    r"(frais|fret|freight|transport|assurance|insurance|emballage|packing|packaging|handling|shipping"
    r"|port(?!\s+(?:de|d'|du|des|of|a|à)\b))\b"
)
_FOOTER = re.compile(r"^(page \d+|\d+ ?/ ?\d+$)")
_TOTAL = re.compile(r"\b(total|net a payer|montant du|amount due|grand total)\b")

_HEADER_PATTERNS = {
    "invoice_number": re.compile(
        r"\b(?:facture|invoice|proforma)\s*(?:n\s*[°o]|no\.?|num(?:ero)?\.?|number|#)\s*[:.]?\s*([A-Za-z0-9][\w/\-.]*)",
        re.IGNORECASE,
    ),
    "invoice_date": re.compile(
        r"\b(?:date(?: de (?:la )?facture| facture)?|invoice date|dated?)\s*[:.]?\s*"
        r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-zéû]+\s+\d{4})",
        re.IGNORECASE,
    ),
    "currency": re.compile(r"\b(?:devise|currency|monnaie)\s*[:.]?\s*([A-Za-z€$£]{1,6}(?:\s?CFA)?)", re.IGNORECASE),
    "supplier_name": re.compile(
        r"\b(?:fournisseur|vendeur|exportateur|exp[ée]diteur|supplier|seller|exporter|shipper|vendor)\s*[:.]\s*(.+)$",
        re.IGNORECASE,
    ),
    "incoterm": re.compile(r"\b((?:EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)(?:\s+[A-Za-zÀ-ÿ\-]+)?)\b"),
}
HEADER_LABELS = {
    "supplier_name": "Fournisseur",
    "buyer_name": "Acheteur ou destinataire",
    "invoice_number": "N° de facture",
    "invoice_date": "Date de facture",
    "currency": "Devise",
    "incoterm": "Incoterm",
    "declared_total": "Total imprimé",
}


def _union(spans: list[Span]) -> Span | None:
    spans = [s for s in spans if s is not None]
    if not spans:
        return None
    first = spans[0]
    if first.sheet:
        cells = [s.cell_range for s in spans]
        return Span(sheet=first.sheet, cell_range=cells[0] if len(cells) == 1 else f"{cells[0]}:{cells[-1]}")
    boxes = [s.bbox for s in spans if s.bbox]
    bbox = (
        (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        if boxes
        else None
    )
    return Span(page=first.page, bbox=bbox, page_size=first.page_size, rotation=first.rotation)


def _with_excerpt(span: Span | None, text: str) -> Span | None:
    if span is not None:
        span.excerpt = (text or "")[:200]
    return span


def _adjacent(previous: Row | None, row: Row) -> bool:
    """Rangée immédiatement sous la précédente (ligne suivante d'une même désignation)."""
    if previous is None or previous.page != row.page:
        return False
    a, b = previous.items[0].span, row.items[0].span
    if a.sheet or b.sheet:
        return a.sheet == b.sheet and row.index == previous.index + 1
    if not (a.bbox and b.bbox):
        return False
    height = max(item.span.bbox[3] - item.span.bbox[1] for item in previous.items if item.span.bbox)
    bottom = max(item.span.bbox[3] for item in previous.items if item.span.bbox)
    top = min(item.span.bbox[1] for item in row.items if item.span.bbox)
    return top - bottom <= 0.9 * height


def _phrases(items: list[Item], gap: float) -> list[list[Item]]:
    groups: list[list[Item]] = []
    for item in sorted(items, key=lambda i: i.x0):
        if groups and item.x0 - groups[-1][-1].x1 <= gap:
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def _role_of(label: str) -> str | None:
    key = norm(label).strip(" :#")
    kind = codemod.classify_label(label)
    if kind:
        return CODE_ROLE[kind]
    for role, labels in ROLE_LABELS.items():
        if key in labels:
            return role
    return None


def _match_columns(items: list[Item], gap: float) -> list[Column]:
    """Titres de colonnes reconnus : plus longue suite de mots d'un groupe qui forme un libellé connu."""
    columns: list[Column] = []
    for group in _phrases(items, gap):
        i = 0
        while i < len(group):
            for j in range(len(group), i, -1):
                label = " ".join(it.text for it in group[i:j])
                role = _role_of(label)
                if role:
                    columns.append(Column(role, label, group[i].x0, group[j - 1].x1))
                    i = j
                    break
            else:
                i += 1
    return columns


def _is_header(columns: list[Column]) -> bool:
    roles = {c.role for c in columns}
    return len(roles) >= 3 and bool(roles & {"description", "amount"})


def _assign(row: Row, columns: list[Column], gap: float, exact: bool = False) -> dict[str, list[Item]]:
    """Chaque groupe de mots contigus va entier dans la colonne qui contient son centre : une
    désignation qui déborde sur la colonne voisine reste une désignation."""
    cells: dict[str, list[Item]] = {}
    if exact:
        by_column = {c.x0: c.role for c in columns}
        for item in row.items:
            if item.x0 in by_column:
                cells.setdefault(by_column[item.x0], []).append(item)
        return cells
    ordered = sorted(columns, key=lambda c: c.x0)
    bounds = [(ordered[k - 1].x1 + ordered[k].x0) / 2 for k in range(1, len(ordered))]
    for group in _phrases(row.items, gap):
        center = (group[0].x0 + group[-1].x1) / 2
        k = sum(1 for b in bounds if center > b)
        cells.setdefault(ordered[k].role, []).extend(group)
    return cells


NUMERIC_ROLES = ("quantity", "unit_price", "amount")


def _numeric_tokens(pages: list[Page]) -> list[str]:
    """Nombres des colonnes chiffrées seulement : les codes (0101.21.00) ne renseignent pas le séparateur."""
    tokens, columns = [], None
    for page in pages:
        for row in page.rows:
            candidate = _match_columns(row.items, page.merge_gap)
            if _is_header(candidate):
                columns = candidate
                continue
            if columns:
                cells = _assign(row, columns, page.merge_gap, page.exact_columns)
                tokens += [_cell_text(cells[r]) for r in NUMERIC_ROLES if cells.get(r)]
    return tokens


def _cell_text(items: list[Item]) -> str:
    return " ".join(i.text for i in sorted(items, key=lambda i: i.x0)).strip()


def _confidence(items: list[Item]) -> float | None:
    values = [i.confidence for i in items if i.confidence is not None]
    return min(values) if values else None


class _Reader:
    """Lecture des valeurs d'un document avec son contexte (séparateur décimal, langue)."""

    def __init__(self, hint, english, origin):
        self.hint, self.english, self.origin = hint, english, origin

    def value(self, items: list[Item] | None, kind: str, label: str, text: str | None = None) -> Value:
        if not items:
            return Value.missing(label)
        raw = _cell_text(items) if text is None else text
        span = _with_excerpt(_union([i.span for i in items]), raw)
        conf = _confidence(items)
        notes = [n for i in items for n in i.notes]
        typed = items[0].typed if len(items) == 1 else None
        low = conf is not None and conf < OCR_MIN_CONFIDENCE
        origin = Origin.OCR if conf is not None else self.origin
        if kind == "amount":
            if isinstance(typed, Decimal):
                reading_value, status, rorigin, note = typed, Status.OK, Origin.READ, ""
            else:
                r = parse_amount(raw, self.hint)
                reading_value, status, rorigin, note = r.value, r.status, r.origin, r.note
            if low and status == Status.OK:
                # Chiffres lus avec peu de confiance : valeur inconnue, jamais devinée (EXT-05, T08).
                reading_value, status, note = None, Status.LOW_CONFIDENCE, f"Lecture peu sûre ({conf:.0f} %)."
            return Value(
                raw, reading_value, status, rorigin if rorigin == Origin.INFERRED else origin, span, conf,
                notes + ([note] if note else []), label,
            )  # fmt: skip
        if kind == "date":
            r = parse_date(raw, english=self.english) if not hasattr(typed, "year") else None
            parsed = typed if r is None else r.value
            status = Status.OK if r is None else r.status
            return Value(raw, parsed, status, origin, span, conf, notes + ([r.note] if r and r.note else []), label)
        if kind == "currency":
            r = parse_currency(raw)
            return Value(raw, r.value, r.status, r.origin if r.origin == Origin.INFERRED else origin, span, conf,
                         notes + ([r.note] if r.note else []), label)  # fmt: skip
        if kind == "country":
            r = parse_country(raw)
            return Value(raw, r.value, r.status, r.origin if r.origin == Origin.INFERRED else origin, span, conf,
                         notes + ([r.note] if r.note else []), label)  # fmt: skip
        status = Status.OK
        if raw.endswith(("…", "...")):
            status = Status.TRUNCATED
            notes.append("Texte visiblement coupé : compléter depuis la pièce.")
        elif low:
            status = Status.LOW_CONFIDENCE
            notes.append(f"Lecture peu sûre ({conf:.0f} %).")
        return Value(raw, raw, status, origin, span, conf, notes, label)


def _classify(row_text: str, cells: dict[str, list[Item]], header_like: bool) -> str:
    key = norm(row_text)
    first = norm(_cell_text(cells.get("description", []))) or key
    if header_like:
        return RowKind.REPEATED_HEADER
    if _CARRIED.search(key):
        return RowKind.CARRIED
    if _SUBTOTAL.search(key):
        return RowKind.SUBTOTAL
    if _TAX.match(first) or _TAX.match(key):
        return RowKind.TAX
    if _DISCOUNT.match(first) or _DISCOUNT.match(key):
        return RowKind.DISCOUNT
    if _FEE.match(first) and not cells.get("quantity"):
        return RowKind.FEE
    if _TOTAL.search(key) and not cells.get("quantity"):
        return RowKind.TOTAL
    return RowKind.GOODS


def _row_amount(row: Row, cells: dict[str, list[Item]], reader: _Reader, label: str) -> Value:
    items = cells.get("amount")
    if items:
        # « TOTAL 18 554.00 EUR » dans une seule cellule : le libellé n'est pas le montant (LEC-05).
        start = next((k for k, i in enumerate(items) if looks_numeric(i.text) or isinstance(i.typed, Decimal)), None)
        items = items[start:] if start is not None else items
    else:
        numeric = [i for i in row.items if looks_numeric(i.text) or isinstance(i.typed, Decimal)]
        items = numeric[-1:] if numeric else None
    value = reader.value(items, "amount", label)
    value.label = label
    return value


# Les numéros et références contiennent au moins un chiffre : « Invoice » n'est pas un numéro.
_HAS_DIGIT = re.compile(r"\d")
# Pays où une date 03/10/2026 se lit d'usage mois/jour, ou dont l'usage est mêlé : rien n'est déduit.
MONTH_FIRST_OR_MIXED = {"US", "CA", "PH", "CN", "JP", "KR", "ZA"}
INVOICE_LABEL_FIELDS = ("supplier_name", "buyer_name", "invoice_number", "invoice_date", "currency", "incoterm")


def _labelled_header(pages: list[Page], table_rows: set[int], reader: _Reader) -> dict[str, Value]:
    from .fields import KNOWN_LABELS, labelled_values, letterhead_company

    found: dict[str, Value] = {}
    labels = {name: KNOWN_LABELS[name] for name in INVOICE_LABEL_FIELDS}
    for name, hit in labelled_values(pages, labels, skip=table_rows).items():
        raw = hit.text
        if name == "invoice_number" and not _HAS_DIGIT.search(raw):
            continue
        if name == "incoterm":
            m = _HEADER_PATTERNS["incoterm"].search(raw)
            if not m:
                continue
            raw = m[1]
        kind = {"invoice_date": "date", "currency": "currency"}.get(name, "text")
        value = reader.value(hit.items, kind, HEADER_LABELS[name], text=raw)
        if name == "incoterm":
            value.parsed = raw[:20]
        value.notes.append(f"Lu à côté du libellé « {hit.label} ».")
        found[name] = value
    if "supplier_name" not in found:
        company = letterhead_company(pages)
        if company:
            value = reader.value(company.items, "text", HEADER_LABELS["supplier_name"], text=company.text)
            value.origin = Origin.INFERRED
            value.notes.append("Émetteur lu en tête de la facture (raison sociale) : à vérifier.")
            found["supplier_name"] = value
    return found


def _issuer_country(pages: list[Page]) -> tuple[str, str] | None:
    """Pays écrit dans l'adresse en tête de la première page, avant la grille des libellés."""
    from .fields import header_rows

    if not pages:
        return None
    for row in header_rows(pages[0]):
        phrases = [" ".join(i.text for i in p) for p in _phrases(row.items, pages[0].merge_gap)]
        for part in [part for phrase in phrases for part in reversed(re.split(r"[,;]", phrase))]:
            words = norm(part).split()
            for n in range(min(3, len(words)), 0, -1):
                name = " ".join(words[-n:])
                reading = parse_country(name)
                if reading.value and len(name) > 2:
                    return reading.value, " ".join(part.strip().split()[-n:])
    return None


def _resolve_day_month(header: dict[str, Value], pages: list[Page], reader: _Reader, field="invoice_date") -> None:
    """LEC-06 : 03/10/2026 sur une facture en anglais se lit jour/mois si l'émetteur est établi dans
    un pays où c'est l'usage ; la valeur est alors marquée « déduite », jamais présentée comme lue."""
    value = header.get(field)
    if value is None or value.status != Status.AMBIGUOUS or not value.raw:
        return
    issuer = _issuer_country(pages)
    if not issuer or issuer[0] in MONTH_FIRST_OR_MIXED:
        return
    country, written = issuer
    reading = parse_date(value.raw, english=False)
    if reading.value is None:
        return
    value.parsed, value.status, value.origin = reading.value, Status.OK, Origin.INFERRED
    value.notes = [
        f"« {value.raw} » lu jour/mois : l'adresse de l'émetteur indique « {written} » ({country}), "
        "où c'est l'usage. À vérifier."
    ]


def _header_fields(pages: list[Page], table_rows: set[int], reader: _Reader) -> tuple[dict[str, Value], list[dict]]:
    found: dict[str, Value] = _labelled_header(pages, table_rows, reader)
    warnings: list[dict] = []
    for page in pages:
        for row in page.rows:
            if id(row) in table_rows:
                continue
            text = row.text
            for name, pattern in _HEADER_PATTERNS.items():
                if name in found:
                    continue
                m = pattern.search(text)
                if not m:
                    continue
                if name == "invoice_number" and not _HAS_DIGIT.search(m[1]):
                    continue
                start, end = m.span(1)
                items, pos = [], 0
                for item in row.items:
                    item_start, item_end = pos, pos + len(item.text)
                    if item_end > start and item_start < end:
                        items.append(item)
                    pos = item_end + 1
                raw = m[1].strip()
                kind = {"invoice_date": "date", "currency": "currency"}.get(name, "text")
                value = reader.value(items or row.items, kind, HEADER_LABELS[name], text=raw)
                if name == "incoterm":
                    value.parsed = raw[:20]
                found[name] = value
    _resolve_day_month(found, pages, reader)
    return found, warnings


# Références d'autres pièces imprimées sur la facture : elles servent au rapprochement (LEC-10).
INVOICE_REFERENCES = {"related_bl": "Titre de transport cité", "purchase_order": "Bon de commande",
                      "container": "Conteneur"}  # fmt: skip


def _invoice_references(pages: list[Page], table_rows: set[int], reader: _Reader) -> dict[str, Value]:
    from .fields import KNOWN_LABELS, labelled_values

    labels = {name: KNOWN_LABELS[name] for name in INVOICE_REFERENCES}
    accept = dict.fromkeys(INVOICE_REFERENCES, _HAS_DIGIT.search)
    found = {}
    for name, hit in labelled_values(pages, labels, skip=table_rows, accept=accept).items():
        value = reader.value(hit.items, "text", INVOICE_REFERENCES[name], text=hit.text)
        value.notes.append(f"Lu à côté du libellé « {hit.label} ».")
        found[name] = value
    return found


def _loose_total(pages: list[Page], reader: _Reader) -> Charge | None:
    """Total imprimé hors tableau reconnu : « TOTAL A PAYER 111.93 EUR » (LEC-05)."""
    hit = None
    for page in pages:
        for row in page.rows:
            key = norm(row.text)
            if not _TOTAL.search(key) or _SUBTOTAL.search(key):
                continue
            numeric = [i for i in row.items if looks_numeric(i.text)]
            if not numeric:
                continue
            first = row.items.index(numeric[0])
            amount_items = row.items[first:]
            if any(not looks_numeric(i.text) and not parse_currency(i.text).value for i in amount_items):
                # « Total : 3 articles, voir annexe » : pas un montant sûr.
                amount_items = [numeric[-1]]
            label = " ".join(i.text for i in row.items[:first])[:80] or row.text[:80]
            value = reader.value(amount_items, "amount", label)
            hit = Charge(kind=RowKind.TOTAL, label=label, amount=value, span=value.span, page=page.number)
    return hit


def structure(pages: list[Page], *, origin: str = Origin.READ) -> ParsedDocument:
    doc = ParsedDocument()
    all_tokens = [i.text for p in pages for r in p.rows for i in r.items]
    hint = document_decimal_hint(_numeric_tokens(pages))
    joined = norm(" ".join(all_tokens[:400]))
    english = ("invoice" in joined or "description of goods" in joined) and "facture" not in joined
    reader = _Reader(hint, english, origin)
    doc.stats.update({"decimal_separator": hint, "language": "en" if english else "fr"})

    table_rows: set[int] = set()
    columns: list[Column] | None = None
    seen_header = False
    rows_by_kind: dict[str, int] = {}
    current: ParsedLine | None = None
    totals: list[Charge] = []

    for page in pages:
        page_columns = None
        ended = False
        previous_row = None
        for row in page.rows:
            candidate = _match_columns(row.items, page.merge_gap)
            if _is_header(candidate):
                kind = RowKind.REPEATED_HEADER if seen_header else RowKind.HEADER
                seen_header = True
                page_columns = columns = candidate
                table_rows.add(id(row))
                rows_by_kind[kind] = rows_by_kind.get(kind, 0) + 1
                current = None
                continue
            active = page_columns or columns
            if not active:
                continue
            cells = _assign(row, active, page.merge_gap, page.exact_columns)
            kind = _classify(row.text, cells, False)
            if kind != RowKind.GOODS:
                table_rows.add(id(row))
                rows_by_kind[kind] = rows_by_kind.get(kind, 0) + 1
                label = row.text if len(row.text) <= 80 else row.text[:80]
                amount = _row_amount(row, cells, reader, label)
                charge = Charge(kind=kind, label=label, amount=amount, span=amount.span, page=page.number)
                (totals if kind == RowKind.TOTAL else doc.charges).append(charge)
                current = None
                if kind == RowKind.TOTAL:
                    ended = True
                continue
            if ended or _FOOTER.match(norm(row.text)):
                # Après le total, les rangées (conditions, mentions) ne sont pas des marchandises.
                continue
            numeric_cells = [r for r in ("quantity", "unit_price", "amount") if cells.get(r)]
            if not numeric_cells and not cells.get("reference") and not cells.get("customs_code"):
                if (
                    current is not None
                    and cells.get("description")
                    and set(cells) <= {"description", "unit"}
                    and _adjacent(previous_row, row)
                ):
                    # Désignation sur plusieurs lignes : rattachée à la marchandise précédente.
                    extra = _cell_text(cells["description"])
                    desc = current.fields["description_raw"]
                    desc.raw = f"{desc.raw} {extra}" if desc.raw else extra
                    desc.parsed = desc.raw
                    desc.span = _union([desc.span, *[i.span for i in cells["description"]]])
                    desc.span = _with_excerpt(desc.span, desc.raw)
                    desc.notes.append("Désignation sur plusieurs lignes.")
                    if desc.raw.endswith(("…", "...")):
                        desc.status = Status.TRUNCATED
                    table_rows.add(id(row))
                    previous_row = row
                continue
            table_rows.add(id(row))
            rows_by_kind[RowKind.GOODS] = rows_by_kind.get(RowKind.GOODS, 0) + 1
            current = _goods_line(row, cells, active, reader, page)
            previous_row = row
            doc.lines.append(current)

    doc.header, header_warnings = _header_fields(pages, table_rows, reader)
    doc.header.update(_invoice_references(pages, table_rows, reader))
    doc.warnings.extend(header_warnings)
    if not totals and (loose := _loose_total(pages, reader)):
        totals.append(loose)
    if totals:
        final = totals[-1]
        doc.header["declared_total"] = Value(
            final.amount.raw, final.amount.parsed, final.amount.status, final.amount.origin, final.amount.span,
            final.amount.confidence, final.amount.notes, f"Total imprimé (« {final.label} »)",
        )  # fmt: skip
        doc.charges.extend(totals)
    for name, label in HEADER_LABELS.items():
        doc.header.setdefault(name, Value.missing(label, "Non trouvé dans le document."))
    if not seen_header:
        doc.warnings.append(
            warning("NO_TABLE_FOUND", "Aucun tableau de marchandises reconnu : saisir les lignes manuellement.")
        )
    _line_checks(doc)
    doc.stats["rows"] = rows_by_kind
    return doc


def _goods_line(row: Row, cells: dict[str, list[Item]], columns: list[Column], reader: _Reader, page: Page):
    labels = {c.role: c.label for c in columns}
    qty_items, unit_items = cells.get("quantity"), cells.get("unit")
    fields = {
        "source_reference": reader.value(cells.get("reference"), "text", labels.get("reference", "Référence")),
        "description_raw": reader.value(cells.get("description"), "text", labels.get("description", "Désignation")),
        "quantity": reader.value(qty_items, "amount", labels.get("quantity", "Quantité")),
        "unit": reader.value(unit_items, "text", labels.get("unit", "Unité")),
        "unit_price": reader.value(cells.get("unit_price"), "amount", labels.get("unit_price", "Prix unitaire")),
        "amount": reader.value(cells.get("amount"), "amount", labels.get("amount", "Montant")),
        "origin_country": reader.value(cells.get("origin"), "country", labels.get("origin", "Origine")),
    }
    qty = fields["quantity"]
    if qty.status == Status.UNREADABLE and qty.raw and not unit_items:
        number, unit = split_quantity_unit(qty.raw)
        if unit:
            r = parse_amount(number, reader.hint)
            if r.value is not None:
                qty.parsed, qty.status, qty.notes = r.value, Status.OK, [f"Unité « {unit} » lue avec la quantité."]
                fields["unit"] = Value(unit, unit, Status.OK, qty.origin, qty.span, qty.confidence, [], qty.label)
    unit_value = fields["unit"]
    if not qty_items and unit_value.raw:
        # « 40 pcs » rangé sous l'unité (colonne décalée, filigrane retiré) : la quantité est le nombre.
        number, unit = split_quantity_unit(unit_value.raw)
        r = parse_amount(number, reader.hint) if unit else None
        if r is not None and r.value is not None:
            fields["quantity"] = Value(number, r.value, Status.OK, unit_value.origin, unit_value.span,
                                       unit_value.confidence, [f"Quantité lue avec l'unité « {unit_value.raw} »."],
                                       labels.get("quantity", "Quantité"))  # fmt: skip
            unit_value.raw = unit_value.parsed = unit
    line = ParsedLine(fields=fields, page=page.number, span=_union([i.span for i in row.items]))
    for role, kind in (("customs_code", codemod.CUSTOMS), ("uncertain_code", codemod.AMBIGUOUS)):
        items = cells.get(role)
        if items:
            raw = _cell_text(items)
            cand = CodeCandidate(
                raw=raw,
                kind=kind,
                label=labels.get(role, "Code"),
                claimed_scheme=codemod.claimed_scheme(labels.get(role, "")),
                span=_with_excerpt(_union([i.span for i in items]), raw),
                origin=Origin.OCR if _confidence(items) is not None else reader.origin,
                findings=codemod.code_findings(raw),
            )
            if isinstance(items[0].typed, Decimal):
                # Cellule Excel numérique : les zéros initiaux ont pu être perdus ; rien n'est ajouté.
                cand.findings.append("CODE_NUMERIC_CELL")
            line.codes.append(cand)
    desc = fields["description_raw"]
    for label, raw, _s, _e in codemod.inline_codes(desc.raw or ""):
        line.codes.append(
            CodeCandidate(
                raw=raw,
                kind=codemod.CUSTOMS,
                label=label,
                claimed_scheme=codemod.claimed_scheme(label),
                span=desc.span,
                origin=desc.origin,
                findings=codemod.code_findings(raw),
            )
        )
    return line


def _line_checks(doc: ParsedDocument) -> None:
    seen: dict[tuple, int] = {}
    for n, line in enumerate(doc.lines, start=1):
        f = line.fields
        customs = [c for c in line.codes if c.kind == codemod.CUSTOMS]
        if len({normalize_code(c.raw) or c.raw for c in customs}) > 1:
            for c in customs:
                c.findings.append("CODE_CONFLICT")
        if not customs and not any(c.kind == codemod.AMBIGUOUS for c in line.codes):
            line.warnings.append(warning("CODE_ABSENT", codemod.FINDING_MESSAGES["CODE_ABSENT"]))
        q, p, a = f["quantity"].parsed, f["unit_price"].parsed, f["amount"].parsed
        if all(isinstance(v, Decimal) for v in (q, p, a)) and abs(q * p - a) > Decimal("0.01"):
            line.warnings.append(
                warning(
                    "AMOUNT_MISMATCH",
                    f"Quantité × prix = {q * p} ; montant imprimé {a}.",
                    computed=format(q * p, "f"),
                    printed=format(a, "f"),
                )
            )
        if isinstance(a, Decimal) and a < 0:
            line.warnings.append(warning("CREDIT_LINE", "Montant négatif : avoir ou retour à traiter explicitement."))
        key = (norm(f["description_raw"].raw or ""), f["unit_price"].parsed, f["quantity"].parsed)
        if key[0] and key in seen:
            line.warnings.append(
                warning(
                    "DUPLICATE_SUSPECTED",
                    f"Même désignation, prix et quantité que la ligne {seen[key]} : conservée, à vérifier.",
                )
            )
        else:
            seen.setdefault(key, n)


def totals_check(goods_amounts: list[Decimal | None], charges: list[dict], printed_total: Decimal | None) -> dict:
    """EXT-06 : comparaison du total imprimé et du total recalculé, composantes et écart affichés."""
    known = [a for a in goods_amounts if a is not None]
    unknown = len(goods_amounts) - len(known)
    goods_sum = sum(known, Decimal("0")) if unknown == 0 else None

    def total(kind):
        values = [c["amount"] for c in charges if c["kind"] == kind]
        if any(v is None for v in values):
            return None
        return sum((abs(v) if kind == RowKind.DISCOUNT else v for v in values), Decimal("0"))

    fees, discounts, taxes = total(RowKind.FEE), total(RowKind.DISCOUNT), total(RowKind.TAX)
    components = {"goods": goods_sum, "fees": fees, "discounts": discounts, "taxes": taxes}
    if any(v is None for v in components.values()):
        computed, status = None, "incomplete"
    else:
        computed = goods_sum + fees - discounts + taxes
        status = "no_printed_total" if printed_total is None else ("match" if computed == printed_total else "gap")
    gap = printed_total - computed if computed is not None and printed_total is not None else None
    explanations = []
    if gap:
        for kind_label, value in (("frais", fees), ("remises", discounts), ("taxes", taxes)):
            if value and abs(gap) == value:
                explanations.append(f"L'écart est égal au total des {kind_label} : vérifier leur prise en compte.")
    subtotals = [
        {"label": c["label"], "amount": c["amount"], "page": c.get("page")}
        for c in charges
        if c["kind"] in (RowKind.SUBTOTAL, RowKind.CARRIED)
    ]
    return {
        "status": status,
        "goods_lines": len(goods_amounts),
        "goods_lines_without_amount": unknown,
        "components": components,
        "computed_total": computed,
        "printed_total": printed_total,
        "gap": gap,
        "explanations": explanations,
        "subtotals_not_added": subtotals,
    }
