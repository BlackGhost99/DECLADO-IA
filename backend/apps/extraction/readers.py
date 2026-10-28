"""Lecture d'une pièce selon son type : facture commerciale, titre de transport, assurance, fret.

La facture commerciale garde sa lecture complète (layout.structure). Les autres pièces ne donnent
que leurs informations utiles au dossier (références, parties, voyage, montants), lues à côté de
leur libellé (fields.py) et jamais devinées : un champ absent reste « non trouvé » (LEC-08, LEC-09).
Le type détecté d'après le titre accompagne chaque lecture ; il reste une proposition (LEC-07).
"""

import re
from dataclasses import dataclass

from .fields import KNOWN_LABELS, header_rows, labelled_values, letterhead_company
from .layout import (
    Page,
    _loose_total,
    _phrases,
    _Reader,
    _resolve_day_month,
    structure,
)
from .numbers import document_decimal_hint, looks_numeric, norm
from .schema import Origin, ParsedDocument, Status, Value, warning

INVOICE, TRANSPORT, INSURANCE, FREIGHT = "invoice", "transport", "insurance", "freight"
READERS = (INVOICE, TRANSPORT, INSURANCE, FREIGHT)


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str  # libellé français enregistré avec la valeur ; l'interface traduit d'après le nom
    kind: str = "text"  # text, date, currency, amount
    labels: tuple[str, ...] = ()


def _k(name: str, *extra: str) -> tuple[str, ...]:
    return KNOWN_LABELS.get(name, ()) + extra


DOCUMENT_NUMBER = _k("invoice_number", "n° attestation", "attestation no", "certificat no", "note de debit n°")
ISSUE_DATE = ("issue date", "date of issue", "date d'emission", "date d emission", "date", "invoice date",
              "date de facture", "shipped on board", "on board date", "date d'embarquement")  # fmt: skip

SPECS: dict[str, tuple[FieldSpec, ...]] = {
    TRANSPORT: (
        FieldSpec("transport_number", "N° du titre de transport", labels=_k("transport_number")),
        FieldSpec("issue_date", "Date d'émission", "date", ISSUE_DATE),
        FieldSpec("shipper", "Chargeur", labels=_k("shipper", "exporter", "exportateur")),
        FieldSpec(
            "consignee", "Destinataire", labels=("consignee", "destinataire", "receptionnaire", "réceptionnaire")
        ),
        FieldSpec("notify", "Partie à notifier", labels=_k("notify")),
        FieldSpec("vessel", "Navire", labels=_k("vessel", "vessel name", "flight", "vol")),
        FieldSpec("voyage", "Voyage", labels=_k("voyage")),
        FieldSpec("port_of_loading", "Port de chargement", labels=_k("port_of_loading", "airport of departure")),
        FieldSpec(
            "port_of_discharge", "Port de déchargement", labels=_k("port_of_discharge", "airport of destination")
        ),
        FieldSpec("place_of_delivery", "Lieu de livraison", labels=_k("place_of_delivery")),
        FieldSpec("related_invoice", "Facture citée", labels=_k("related_invoice")),
        FieldSpec("container", "Conteneur", labels=_k("container")),
        FieldSpec("packages", "Colis", labels=_k("packages")),
        FieldSpec("gross_weight", "Poids brut", labels=_k("gross_weight")),
        FieldSpec("measurement", "Volume", labels=_k("measurement")),
        FieldSpec("freight_terms", "Conditions de fret", labels=_k("freight_terms")),
    ),
    INSURANCE: (
        FieldSpec("issuer", "Assureur"),
        FieldSpec("document_number", "N° de la pièce", labels=DOCUMENT_NUMBER),
        FieldSpec("issue_date", "Date", "date", ISSUE_DATE),
        FieldSpec("currency", "Devise", "currency", _k("currency")),
        FieldSpec("policy_number", "N° de police", labels=_k("policy_number")),
        FieldSpec("insured", "Assuré", labels=("assure", "assuré", "insured", "beneficiaire", "bénéficiaire")),
        FieldSpec("related_bl", "Titre de transport cité", labels=_k("related_bl")),
        FieldSpec("related_invoice", "Facture citée", labels=_k("related_invoice")),
        FieldSpec("vessel", "Navire", labels=_k("vessel")),
        FieldSpec("voyage", "Voyage", labels=_k("voyage")),
        FieldSpec("container", "Conteneur", labels=_k("container")),
        FieldSpec("insured_value", "Valeur assurée", "amount", _k("insured_value")),
        FieldSpec("premium_total", "Prime totale", "amount"),
    ),
    FREIGHT: (
        FieldSpec("issuer", "Transporteur ou transitaire"),
        FieldSpec("document_number", "N° de la pièce", labels=DOCUMENT_NUMBER),
        FieldSpec("issue_date", "Date", "date", ISSUE_DATE),
        FieldSpec("currency", "Devise", "currency", _k("currency")),
        FieldSpec("related_bl", "Titre de transport cité", labels=_k("related_bl")),
        FieldSpec("related_invoice", "Facture citée", labels=_k("related_invoice")),
        FieldSpec("vessel", "Navire", labels=_k("vessel")),
        FieldSpec("port_of_loading", "Port de chargement", labels=_k("port_of_loading")),
        FieldSpec("port_of_discharge", "Port de déchargement", labels=_k("port_of_discharge")),
        FieldSpec("freight_total", "Montant du fret", "amount"),
    ),
}
# Champ « total » de chaque lecture : le dernier total imprimé de la pièce.
TOTAL_FIELD = {INSURANCE: "premium_total", FREIGHT: "freight_total"}
REFERENCE_FIELDS = {"transport_number", "document_number", "policy_number", "related_bl", "related_invoice"}
MEASURE_FIELDS = {"packages", "gross_weight", "measurement"}
# Numéro de conteneur (ISO 6346) : quatre lettres puis six ou sept chiffres, « MSCU 771205-4 ».
CONTAINER = re.compile(r"\b[A-Z]{4}\s?\d{6}(?:\s?-?\s?\d)?(?!\d)")


def _has_digit(text: str) -> bool:
    return any(c.isdigit() for c in text)


_SHAPES = {"amount": lambda text: any(looks_numeric(w) for w in text.split()), "date": _has_digit}

# --- Type de pièce d'après son titre -------------------------------------------------------

# (code de la taxonomie, motif sur le texte normalisé) : du plus précis au plus général.
TITLES: tuple[tuple[str, str], ...] = (
    ("insurance_invoice", r"\bfacture d ?assurance\b|\binsurance invoice\b|\bavis de prime\b|\bnote de prime\b"),
    ("insurance_certificate", r"\b(?:attestation|certificat) d ?assurance\b|\binsurance certificate\b"
                              r"|\bcertificate of insurance\b"),
    ("insurance_policy", r"\bpolice d ?assurance\b|\binsurance policy\b"),
    ("freight_invoice", r"\bfacture de (?:fret|transport)\b|\bfreight invoice\b|\bfreight note\b"),
    ("sea_waybill", r"\bsea ?way ?bill\b|\blettre de transport maritime\b"),
    ("bill_of_lading", r"\bbill of lading\b|\bconnaissement\b"),
    ("air_waybill", r"\bair ?way ?bill\b|\blettre de transport aerien\b"),
    ("road_consignment_note", r"\blettre de voiture\b|\bconsignment note\b|\bcmr\b"),
    ("packing_list", r"\bpacking ?list\b|\bliste de colisage\b"),
    ("certificate_of_origin", r"\bcertificat d ?origine\b|\bcertificate of origin\b"),
    ("proforma_invoice", r"\bpro ?forma\b"),
    ("commercial_invoice", r"\bcommercial invoice\b|\bfacture commerciale\b|\bfactura comercial\b|\binvoice\b"
                           r"|\bfacture\b|\bfactura\b"),
)  # fmt: skip
READER_FOR_TYPE = {
    "commercial_invoice": INVOICE,
    "proforma_invoice": INVOICE,
    "bill_of_lading": TRANSPORT,
    "sea_waybill": TRANSPORT,
    "air_waybill": TRANSPORT,
    "road_consignment_note": TRANSPORT,
    "rail_consignment_note": TRANSPORT,
    "insurance_invoice": INSURANCE,
    "insurance_certificate": INSURANCE,
    "insurance_policy": INSURANCE,
    "freight_invoice": FREIGHT,
    "freight_receipt": FREIGHT,
}
READER_FOR_USAGE = {"invoice": INVOICE, "transport": TRANSPORT, "insurance": INSURANCE, "freight": FREIGHT}


def _columns(page: Page) -> list[str]:
    """Texte de l'en-tête colonne par colonne : un titre aligné à droite sur deux lignes
    (« FACTURE » / « D'ASSURANCE ») se relit d'un seul tenant, sans l'adresse voisine."""
    columns: list[list] = []
    for row in header_rows(page):
        for phrase in _phrases(row.items, page.merge_gap):
            x0, x1 = phrase[0].x0, phrase[-1].x1
            for column in columns:
                if x0 <= column[1] and x1 >= column[0]:
                    column[0], column[1] = min(column[0], x0), max(column[1], x1)
                    column[2].append(" ".join(i.text for i in phrase))
                    break
            else:
                columns.append([x0, x1, [" ".join(i.text for i in phrase)]])
    return [" ".join(column[2]) for column in columns]


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", norm(text).replace("'", " ")).strip()


def detect_type(pages: list[Page]) -> dict | None:
    """Type proposé d'après le titre de la première page, avec le texte qui le justifie."""
    if not pages:
        return None
    zones = _columns(pages[0]) or [" ".join(r.text for r in pages[0].rows[:8])]
    for code, pattern in TITLES:
        for zone in zones:
            m = re.search(pattern, re.sub(r"\s+", " ", _plain(zone)))
            if m:
                return {"code": code, "method": "title", "excerpt": m.group(0).upper()[:80], "page": pages[0].number}
    return None


# --- Lecture des champs ----------------------------------------------------------------------


def _reader(pages: list[Page], origin: str) -> _Reader:
    tokens = [i.text for p in pages for r in p.rows for i in r.items if looks_numeric(i.text)]
    joined = norm(" ".join(i.text for p in pages for r in p.rows for i in r.items)[:4000])
    english = any(w in joined for w in ("bill of lading", "invoice", "shipper", "consignee", "insured")) and not any(
        w in joined for w in ("facture", "connaissement", "assure", "destinataire")
    )
    return _Reader(document_decimal_hint(tokens), english, origin)


def read_fields(pages: list[Page], reader_name: str, *, origin: str = Origin.READ) -> ParsedDocument:
    doc = ParsedDocument()
    reader = _reader(pages, origin)
    specs = SPECS[reader_name]
    labels = {s.name: s.labels for s in specs if s.labels}
    accept = {s.name: _SHAPES[s.kind] for s in specs if s.kind in _SHAPES}
    accept |= {name: _has_digit for name in REFERENCE_FIELDS | MEASURE_FIELDS}
    accept["container"] = lambda text: bool(CONTAINER.search(text.upper()))
    found = labelled_values(pages, labels, accept=accept)
    for spec in specs:
        hit = found.get(spec.name)
        if hit is None:
            continue
        text = hit.text
        if spec.name == "container":
            text = CONTAINER.search(text.upper()).group(0)
        value = reader.value(hit.items, spec.kind, spec.label, text=text)
        value.notes.append(f"Lu à côté du libellé « {hit.label} ».")
        doc.header[spec.name] = value
    if any(s.name == "issuer" for s in specs) and (company := letterhead_company(pages)):
        value = reader.value(company.items, "text", "", text=company.text)
        value.notes.append("Raison sociale lue en tête de la pièce.")
        doc.header["issuer"] = value
    if total_name := TOTAL_FIELD.get(reader_name):
        if charge := _loose_total(pages, reader):
            charge.amount.notes.append(f"Total imprimé « {charge.label} ».")
            doc.header[total_name] = charge.amount
    if "issue_date" in doc.header:
        _resolve_day_month(doc.header, pages, reader, field="issue_date")
    for spec in specs:
        value = doc.header.setdefault(spec.name, Value.missing(spec.label, "Non trouvé dans la pièce."))
        value.label = spec.label
    if not any(v.status == Status.OK for v in doc.header.values()):
        doc.warnings.append(warning("NOTHING_READ", "Aucune information lue : saisir ou vérifier depuis la pièce."))
    doc.stats["language"] = "en" if reader.english else "fr"
    return doc


def read(pages: list[Page], reader_name: str = INVOICE, *, origin: str = Origin.READ) -> ParsedDocument:
    doc = structure(pages, origin=origin) if reader_name == INVOICE else read_fields(pages, reader_name, origin=origin)
    doc.stats["reader"] = reader_name
    if detection := detect_type(pages):
        doc.stats["type_detection"] = detection
    return doc
