"""Récapitulatif PDF d'un calcul (reportlab)."""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.rules_engine import CalculationResult

META_LABELS = {
    "declaration_number": "N° de déclaration",
    "declaration_date": "Date",
    "declarant_name": "Déclarant",
    "exporter_name": "Exportateur",
    "importer_name": "Importateur",
    "customs_office": "Bureau de douane",
    "country": "Pays",
}


def _table(rows: list[list[str]]) -> Table:
    table = Table(rows, colWidths=[200, 290])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def build_calculation_pdf(result: CalculationResult, extra_meta: dict | None = None) -> bytes:
    data = result.to_dict()
    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Calcul {data['calculation_id']}")
    story = [
        Paragraph("Récapitulatif du calcul douanier", styles["Title"]),
        Paragraph(f"Calcul {data['calculation_id']}", styles["Normal"]),
        Spacer(1, 12),
    ]
    meta = [[META_LABELS.get(k, k), str(v)] for k, v in (extra_meta or {}).items() if v]
    if meta:
        story += [_table(meta), Spacer(1, 12)]

    goods = data["input"]
    story += [
        Paragraph("Marchandise", styles["Heading2"]),
        _table(
            [
                ["Facture", goods["invoice_number"]],
                ["Code SH", goods["hs_code"]],
                ["Désignation", goods["description"]],
                [
                    "Quantité × prix",
                    f"{goods['quantity']} × {goods['unit_price']} {goods['currency']}",
                ],
                ["Incoterm", goods["incoterm"]],
                ["Origine", goods["origin_country"]],
                ["Valeur CAF", data["incoterms_conversion"]["cif_value"]],
                ["Base imposable", data["taxable_base"]],
            ]
        ),
        Spacer(1, 12),
    ]
    taxes = data["tax_breakdown"]
    rows = [
        ["Droit de douane", f"{taxes['customs_duty_amount']} ({taxes['customs_duty_rate']} %)"],
        ["TVA", f"{taxes['vat_amount']} ({taxes['vat_rate']} % sur {taxes['vat_base']})"],
    ]
    rows += [[name, amount] for name, amount in taxes["other_taxes"].items()]
    rows += [["Total des taxes", taxes["total_taxes"]], ["Montant total", taxes["total_amount"]]]
    story += [Paragraph("Taxes", styles["Heading2"]), _table(rows), Spacer(1, 12)]

    if result.required_documents:
        story.append(Paragraph("Documents requis", styles["Heading2"]))
        story += [Paragraph(f"• {d}", styles["Normal"]) for d in result.required_documents]
    if result.warnings:
        story.append(Paragraph("Avertissements", styles["Heading2"]))
        story += [Paragraph(f"• {w}", styles["Normal"]) for w in result.warnings]

    doc.build(story)
    return buffer.getvalue()
