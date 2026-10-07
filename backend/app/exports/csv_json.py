"""Exports texte (CSV une ligne par calcul, JSON complet)."""

from __future__ import annotations

import csv
import io
import json

from app.rules_engine import CalculationResult

CSV_COLUMNS = [
    "calculation_id",
    "invoice_number",
    "hs_code",
    "description",
    "quantity",
    "unit_price",
    "currency",
    "incoterm",
    "origin_country",
    "cif_value",
    "taxable_base",
    "customs_duty_rate",
    "customs_duty_amount",
    "vat_rate",
    "vat_amount",
    "total_taxes",
    "total_amount",
]


def calculation_to_csv(result: CalculationResult) -> str:
    data = result.to_dict()
    taxes = data["tax_breakdown"]
    row = {
        "calculation_id": data["calculation_id"],
        **{k: data["input"][k] for k in ("invoice_number", "hs_code", "description", "quantity")},
        **{k: data["input"][k] for k in ("unit_price", "currency", "incoterm", "origin_country")},
        "cif_value": data["incoterms_conversion"]["cif_value"],
        "taxable_base": data["taxable_base"],
        **{
            k: taxes[k]
            for k in ("customs_duty_rate", "customs_duty_amount", "vat_rate", "vat_amount")
        },
        "total_taxes": taxes["total_taxes"],
        "total_amount": taxes["total_amount"],
    }
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(row)
    return out.getvalue()


def calculation_to_json(result: CalculationResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
