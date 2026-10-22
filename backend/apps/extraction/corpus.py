"""Corpus synthétique d'évaluation : pièces des jeux B à E et valeurs attendues."""

import json
from pathlib import Path

from apps.documents.sniff import PDF, PNG, XLSX

from . import synthetic as syn

SIMPLE_HEADER = {
    "supplier_name": "Haras Fictif SARL",
    "invoice_number": "F-2026-001",
    "invoice_date": "2026-09-15",
    "currency": "EUR",
    "incoterm": "FOB Anvers",
    "declared_total": "4205",
}
SIMPLE_LINES = [
    {"source_reference": "12345678", "description_raw": "Chevaux reproducteurs fictifs", "quantity": "2",
     "unit": "U", "unit_price": "1500", "amount": "3000", "origin_country": "FR", "customs_code": "0101.21.00"},
    {"source_reference": "A-77", "description_raw": "Selles en cuir fictives", "quantity": "10", "unit": "U",
     "unit_price": "120.5", "amount": "1205", "origin_country": "IT", "customs_code": "4201.00.00"},
]  # fmt: skip


def build(directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    simple = syn.simple_invoice_pdf()
    entries = {
        "b-simple.pdf": (simple, PDF, False, SIMPLE_HEADER, SIMPLE_LINES),
        "e-scan-net.pdf": (syn.scanned_pdf(simple, dpi=300), PDF, True, SIMPLE_HEADER, SIMPLE_LINES),
        "e-image-nette.png": (syn.render_png(simple, dpi=300), PNG, True, SIMPLE_HEADER, SIMPLE_LINES),
        # Scan très dégradé : la vérité reste celle de la facture ; ce qui n'est pas lu compte comme « manqué ».
        "e-scan-degrade.png": (syn.render_png(simple, dpi=200, degrade=True), PNG, True, SIMPLE_HEADER, SIMPLE_LINES),
        "t08-illisible.pdf": (
            syn.unreadable_values_pdf(),
            PDF,
            False,
            SIMPLE_HEADER | {"declared_total": "750"},
            [
                {
                    "source_reference": "Z-1",
                    "quantity": None,
                    "unit_price": "75",
                    "amount": "750",
                    "origin_country": "DE",
                    "customs_code": "4201.00.00",
                }
            ],  # fmt: skip
        ),
        "d-multipage.pdf": (
            syn.multipage_invoice_pdf(),
            PDF,
            False,
            SIMPLE_HEADER | {"invoice_number": "F-2026-003", "incoterm": "EXW Lyon", "declared_total": "602.5"},
            [
                {"source_reference": "R-1", "quantity": "100", "amount": "200", "customs_code": "9603.29.00"},
                {"source_reference": "R-2", "quantity": "50", "amount": "150", "customs_code": "9603.90.00"},
                {"source_reference": "R-1", "quantity": "100", "amount": "200", "customs_code": "9603.29.00"},
            ],
        ),
        "c-codes.pdf": (
            syn.code_cases_pdf(),
            PDF,
            False,
            {"invoice_number": "F-2026-002", "declared_total": "118"},
            [
                {"source_reference": "87654321", "customs_code": None},  # référence de huit chiffres : pas un code
                {"source_reference": "B-2", "customs_code": "4201.00"},
                {"source_reference": "C-3", "customs_code": None},  # colonne « Code » : nature incertaine
            ],
        ),
        "b-classeur.xlsx": (
            syn.invoice_xlsx(),
            XLSX,
            False,
            {
                "supplier_name": "Sellerie Fictive SA",
                "invoice_number": "X-2026-9",
                "invoice_date": "2026-09-20",
                "currency": "USD",
                "incoterm": None,
                "declared_total": "182",
            },  # fmt: skip
            [
                {
                    "source_reference": "9001",
                    "quantity": "4",
                    "unit_price": "25.5",
                    "amount": "102",
                    "origin_country": "CN",
                    "customs_code": "6307.90.98",
                },
                {
                    "source_reference": "9002",
                    "quantity": "2",
                    "unit_price": "40",
                    "amount": "80",
                    "origin_country": "CN",
                    "customs_code": "4201.00.00",
                },
            ],  # fmt: skip
        ),
    }
    for name, (data, mime, ocr, header, lines) in entries.items():
        (directory / name).write_bytes(data)
        expected = {"file": name, "mime": mime, "ocr": ocr, "header": header, "lines": lines, "synthetic": True}
        (directory / f"{Path(name).stem}.expected.json").write_text(
            json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return sorted(entries)
