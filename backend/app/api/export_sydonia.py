"""
API endpoints pour l'export des déclarations SYDONIA
"""

import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

router = APIRouter()


class SydoniaDeclaration(BaseModel):
    # Informations générales
    numero_declaration: str
    date_declaration: str
    bureau_douane: str
    regime_douanier: str

    # Importateur
    nom_importateur: str
    adresse_importateur: str
    nif_importateur: str

    # Exportateur
    nom_exportateur: str
    pays_exportation: str

    # Transport
    mode_transport: str
    pays_provenance: str
    pays_origine: str

    # Marchandise
    code_sh: str
    designation: str
    quantite: float
    unite_mesure: str
    poids_net: float
    poids_brut: float

    # Valeur
    valeur_cif: float
    monnaie: str
    taux_change: float

    # Taxes
    droits_douane: float
    tva: float
    tci: float
    cci: float
    oad: float
    total_taxes: float
    valeur_totale: float

    # Documents
    facture_commerciale: str
    connaissement: str
    certificat_origine: str


def format_currency(value: float) -> str:
    """Formate une valeur monétaire"""
    return f"{value:,.2f}".replace(",", " ")


def create_pdf_sydonia(declaration: SydoniaDeclaration) -> io.BytesIO:
    """Génère un PDF de la déclaration SYDONIA"""
    if not REPORTLAB_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="ReportLab n'est pas installé. Installez avec: pip install reportlab",
        )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1 * cm, bottomMargin=1 * cm)

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=colors.HexColor("#1e3c72"),
        spaceAfter=12,
        alignment=1,  # Center
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#2a5298"),
        spaceAfter=6,
        spaceBefore=12,
    )

    # Contenu
    content = []

    # Titre
    content.append(Paragraph("DÉCLARATION EN DOUANE SYDONIA", title_style))
    content.append(Spacer(1, 0.5 * cm))

    # Section 1: Informations générales
    content.append(Paragraph("1. INFORMATIONS GÉNÉRALES", heading_style))
    data1 = [
        [
            "N° Déclaration:",
            declaration.numero_declaration or "N/A",
            "Date:",
            declaration.date_declaration,
        ],
        [
            "Bureau de Douane:",
            declaration.bureau_douane or "N/A",
            "Régime:",
            declaration.regime_douanier,
        ],
    ]
    table1 = Table(data1, colWidths=[4 * cm, 5 * cm, 3 * cm, 4 * cm])
    table1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    content.append(table1)

    # Section 2: Importateur
    content.append(Paragraph("2. IMPORTATEUR", heading_style))
    data2 = [
        ["Nom/Raison Sociale:", declaration.nom_importateur or "N/A"],
        ["Adresse:", declaration.adresse_importateur or "N/A"],
        ["NIF:", declaration.nif_importateur or "N/A"],
    ]
    table2 = Table(data2, colWidths=[4 * cm, 12 * cm])
    table2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    content.append(table2)

    # Section 3: Exportateur & Transport
    content.append(Paragraph("3. EXPORTATEUR & TRANSPORT", heading_style))
    data3 = [
        [
            "Exportateur:",
            declaration.nom_exportateur or "N/A",
            "Pays Export:",
            declaration.pays_exportation or "N/A",
        ],
        [
            "Mode Transport:",
            declaration.mode_transport,
            "Pays Provenance:",
            declaration.pays_provenance or "N/A",
        ],
        ["Pays Origine:", declaration.pays_origine or "N/A", "", ""],
    ]
    table3 = Table(data3, colWidths=[4 * cm, 5 * cm, 3 * cm, 4 * cm])
    table3.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    content.append(table3)

    # Section 4: Marchandise
    content.append(Paragraph("4. DESCRIPTION DE LA MARCHANDISE", heading_style))
    data4 = [
        [
            "Code SH:",
            declaration.code_sh,
            "Quantité:",
            f"{declaration.quantite} {declaration.unite_mesure}",
        ],
        ["Désignation:", declaration.designation, "", ""],
        [
            "Poids Net:",
            f"{declaration.poids_net} kg",
            "Poids Brut:",
            f"{declaration.poids_brut} kg",
        ],
    ]
    table4 = Table(data4, colWidths=[4 * cm, 5 * cm, 3 * cm, 4 * cm])
    table4.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff8e1")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("SPAN", (1, 1), (3, 1)),  # Merge cells for designation
            ]
        )
    )
    content.append(table4)

    # Section 5: Valeur & Taxes
    content.append(Paragraph("5. VALEUR EN DOUANE & LIQUIDATION", heading_style))
    data5 = [
        ["Valeur CIF:", f"{format_currency(declaration.valeur_cif)} {declaration.monnaie}"],
        ["Droits de Douane (DDI):", f"{format_currency(declaration.droits_douane)} XAF"],
        ["TVA:", f"{format_currency(declaration.tva)} XAF"],
        ["TCI (Taxe Communautaire):", f"{format_currency(declaration.tci)} XAF"],
        ["CCI (Contribution Communautaire):", f"{format_currency(declaration.cci)} XAF"],
        ["OAD (Autres Droits):", f"{format_currency(declaration.oad)} XAF"],
    ]
    table5 = Table(data5, colWidths=[8 * cm, 8 * cm])
    table5.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8f5e9")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    content.append(table5)

    # Total
    data_total = [
        ["TOTAL DES TAXES:", f"{format_currency(declaration.total_taxes)} XAF"],
        ["VALEUR TOTALE (CIF + Taxes):", f"{format_currency(declaration.valeur_totale)} XAF"],
    ]
    table_total = Table(data_total, colWidths=[8 * cm, 8 * cm])
    table_total.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ffd54f")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#4caf50")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    content.append(Spacer(1, 0.3 * cm))
    content.append(table_total)

    # Section 6: Documents
    if (
        declaration.facture_commerciale
        or declaration.connaissement
        or declaration.certificat_origine
    ):
        content.append(Paragraph("6. DOCUMENTS JUSTIFICATIFS", heading_style))
        data6 = []
        if declaration.facture_commerciale:
            data6.append(["Facture Commerciale:", declaration.facture_commerciale])
        if declaration.connaissement:
            data6.append(["Connaissement/LTA:", declaration.connaissement])
        if declaration.certificat_origine:
            data6.append(["Certificat d'Origine:", declaration.certificat_origine])

        table6 = Table(data6, colWidths=[6 * cm, 10 * cm])
        table6.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        content.append(table6)

    # Footer
    content.append(Spacer(1, 1 * cm))
    footer_text = f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} - DECLADO-IA"
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey, alignment=1
    )
    content.append(Paragraph(footer_text, footer_style))

    # Générer le PDF
    doc.build(content)
    buffer.seek(0)
    return buffer


@router.post("/api/export/sydonia/pdf")
async def export_sydonia_pdf(declaration: SydoniaDeclaration):
    """
    Génère un PDF de la déclaration SYDONIA
    """
    try:
        pdf_buffer = create_pdf_sydonia(declaration)

        filename = f"SYDONIA_{declaration.code_sh}_{declaration.date_declaration}.pdf"

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de la génération du PDF: {str(e)}"
        )
