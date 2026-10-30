"""Exports du dossier (EXP-01 à EXP-03) : récapitulatif PDF et détail Excel d'une révision.

Le contenu vient du calcul de préparation : celui figé à la validation quand la révision est
validée, le calcul du moment sinon. Un brouillon porte un marquage visible sur chaque page et
chaque feuille ; seule une révision validée porte la mention de validation interne, jamais une
acceptation par la Douane. Les exports sont produits en français (langue de la déclaration)
et conservés tels que générés, avec leur empreinte.
"""

import io
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.fiscal import rules
from apps.fiscal.calculation import case_calculation
from apps.fiscal.models import TaxCode

from . import services, workflow
from .models import CaseExport, CaseRevision

State = CaseRevision.State

# Libellés de sortie regroupés ici : une autre langue de sortie s'ajoutera sans toucher au rendu.
TEXT = {
    "title": "Récapitulatif de préparation douanière",
    "draft_mark": "BROUILLON",
    "draft_banner": "Brouillon : non validé en interne. Ne pas transmettre comme dossier définitif.",
    "validated_banner": (
        "Validé en interne par {org} le {date} par {actor}. "
        "Validation interne de la société : ce n'est pas une acceptation par la Douane."
    ),
    "demo_banner": "Données fictives de démonstration.",
    "historical_banner": "Simulation sur référence historique : calcul non opérationnel.",
    "identification": "Identification",
    "reference": "Dossier",
    "revision": "Révision",
    "company": "Société",
    "importer": "Importateur",
    "state": "État",
    "regime": "Régime",
    "territory": "Territoire",
    "office": "Bureau d'entrée",
    "date": "Date de calcul",
    "goods": "Marchandises et codes",
    "line": "Ligne",
    "code": "Code SH",
    "description": "Désignation",
    "value": "Valeur en douane (FCFA)",
    "total": "Total (FCFA)",
    "taxes": "Droits et taxes",
    "tax": "Taxe",
    "label": "Libellé",
    "rate": "Taux",
    "amount": "Montant (FCFA)",
    "customs_value": "Valeur en douane totale",
    "total_taxes": "Total des droits et taxes (compte 1)",
    "tci": "TCI, compte 2 (hors total)",
    "ri": "Redevance informatique : calculée par SYDONIA",
    "unknown": "inconnu",
    "provisional": "Calcul provisoire",
    "sources": "Sources",
    "rules_version": "Règles de calcul",
    "taxes_version": "Version des taux",
    "schedule": "Barème",
    "decisions": "Décisions",
    "generated": "Généré le {date} par {actor}",
    "fingerprint": "Empreinte du calcul",
    "code_status": "État du code",
    "status": {"confirmed": "confirmé", "stale": "à reconfirmer", "missing": "non confirmé"},
    "meta": "Métadonnées",
    "field": "Champ",
    "content": "Valeur",
    "marking": "Marquage",
}

# Une cellule dont le texte commence ainsi pourrait être lue comme une formule par un tableur.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _calculation(case, revision):
    """Calcul exporté et son empreinte : le calcul figé fait foi pour une révision validée."""
    decision = workflow.validated_decision(revision)
    if decision is not None:
        return decision.snapshot["calculation"], decision.fingerprint, decision
    calc = workflow._plain(case_calculation(case))
    return calc, workflow._fingerprint(revision, calc), None


def _amount(value) -> str:
    if value in (None, ""):
        return TEXT["unknown"]
    number = Decimal(str(value))
    whole = f"{number.quantize(Decimal('1')):,}".replace(",", "\u00a0")
    return whole


def _code(code: str | None) -> str:
    """Code SH lisible (8502.11.00) ; le texte d'origine est gardé tel quel s'il n'a pas 8 chiffres."""
    if code and len(code) == 8 and code.isdigit():
        return f"{code[:4]}.{code[4:6]}.{code[6:]}"
    return code or ""


def _tax_label(code: str) -> str:
    try:
        return str(TaxCode(code).label)
    except ValueError:
        return code


def _when(value) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")


def _context(case, revision, actor):
    calc, fingerprint, validated = _calculation(case, revision)
    decisions = [
        {
            "label": d.get_kind_display(),
            "actor": d.actor.full_name or d.actor.email,
            "at": _when(d.created_at),
            "reason": d.reason,
        }
        for d in revision.decisions.select_related("actor")
    ]
    marking = CaseExport.Marking.VALIDATED if validated else CaseExport.Marking.DRAFT
    banners = []
    if validated:
        banners.append(
            TEXT["validated_banner"].format(
                org=case.organization.name,
                date=_when(validated.created_at),
                actor=validated.actor.full_name or validated.actor.email,
            )
        )
    else:
        banners.append(TEXT["draft_banner"])
    if revision.mode == CaseRevision.Mode.DEMO:
        banners.append(TEXT["demo_banner"])
    elif revision.mode == CaseRevision.Mode.HISTORICAL:
        banners.append(TEXT["historical_banner"])
    if calc.get("provisional"):
        banners.append(f"{TEXT['provisional']} : " + " ".join(calc.get("provisional_reasons") or []))
    identification = [
        (TEXT["reference"], case.reference),
        (TEXT["revision"], str(revision.revision_no)),
        (TEXT["company"], case.organization.name),
        (TEXT["importer"], case.importer.name if case.importer else TEXT["unknown"]),
        (TEXT["state"], revision.get_state_display()),
        (TEXT["regime"], revision.regime or TEXT["unknown"]),
        (TEXT["territory"], revision.territory),
        (TEXT["office"], revision.entry_office or TEXT["unknown"]),
        (TEXT["date"], calc.get("date") or ""),
    ]
    sources = [
        (TEXT["rules_version"], calc.get("rules_version") or ""),
        (TEXT["taxes_version"], str(calc.get("taxes_version") or "")),
        (TEXT["schedule"], (calc.get("schedule") or {}).get("label") or TEXT["unknown"]),
        (TEXT["fingerprint"], fingerprint),
    ]
    return {
        "calc": calc,
        "fingerprint": fingerprint,
        "marking": marking,
        "banners": banners,
        "identification": identification,
        "sources": sources,
        "decisions": decisions,
        "generated": TEXT["generated"].format(date=_when(timezone.now()), actor=actor.full_name or actor.email),
    }


def _tax_totals(calc) -> list[tuple[str, str, str]]:
    """Total par taxe sur l'ensemble des articles, TCI comprise (affichée à part)."""
    rows = []
    by_tax = (calc.get("totals") or {}).get("by_tax") or {}
    order = [r.code for r in rules.ARTICLE_TAXES]
    for code, amount in sorted(by_tax.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99):
        if code in rules.SYDONIA_TAXES:
            continue  # calculée par SYDONIA : mentionnée à part, jamais un montant de ClairTransit
        rows.append((code, _tax_label(code), _amount(amount)))
    return rows


# --- PDF -------------------------------------------------------------------------------


def build_pdf(ctx) -> bytes:
    from xml.sax.saxutils import escape

    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    fonts = Path(reportlab.__file__).parent / "fonts"
    if "Vera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Vera", str(fonts / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("Vera-Bold", str(fonts / "VeraBd.ttf")))

    green = colors.HexColor("#0b5d3b")
    base = ParagraphStyle("base", fontName="Vera", fontSize=8.5, leading=11)
    small = ParagraphStyle("small", parent=base, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#4a5860"))
    h1 = ParagraphStyle("h1", parent=base, fontName="Vera-Bold", fontSize=15, leading=19, textColor=green)
    h2 = ParagraphStyle("h2", parent=base, fontName="Vera-Bold", fontSize=10.5, leading=14, spaceBefore=8)
    banner = ParagraphStyle(
        "banner", parent=base, fontName="Vera-Bold", backColor=colors.HexColor("#fff4e0"), borderPadding=5
    )
    if ctx["marking"] == CaseExport.Marking.VALIDATED:
        banner.backColor = colors.HexColor("#e6f4ec")

    def p(text, style=base):
        return Paragraph(escape(str(text)), style)

    def grid(rows, widths, header=True, numeric=()):
        table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        style = [
            ("FONT", (0, 0), (-1, -1), "Vera", 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d9e0e4")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            style += [
                ("FONT", (0, 0), (-1, 0), "Vera-Bold", 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f4f6")),
            ]
        for col in numeric:
            style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
        table.setStyle(TableStyle(style))
        return table

    calc = ctx["calc"]
    story = [p(TEXT["title"], h1), Spacer(1, 4)]
    for line in ctx["banners"]:
        story += [p(line, banner), Spacer(1, 6)]
    story.append(p(TEXT["identification"], h2))
    story.append(grid([[p(k), p(v)] for k, v in ctx["identification"]], [45 * mm, 125 * mm], header=False))

    story.append(p(TEXT["goods"], h2))
    rows = [[TEXT["line"], TEXT["code"], TEXT["description"], TEXT["value"], TEXT["total"]]]
    for a in calc.get("articles") or []:
        code = _code(a.get("hs_code")) or "—"
        status = TEXT["status"].get(a.get("code_status"), "")
        rows.append(
            [
                str(a.get("ordinal")),
                p(f"{code}\n{status}" if status != TEXT["status"]["confirmed"] else code),
                p(a.get("description") or ""),
                _amount((a.get("value") or {}).get("xaf")),
                _amount(a.get("total")),
            ]
        )
    story.append(grid(rows, [12 * mm, 24 * mm, 84 * mm, 28 * mm, 22 * mm], numeric=(3, 4)))

    story.append(p(TEXT["taxes"], h2))
    rows = [[TEXT["tax"], TEXT["label"], TEXT["amount"]]]
    for code, label, amount in _tax_totals(calc):
        rows.append([code, p(label), amount])
    story.append(grid(rows, [20 * mm, 110 * mm, 40 * mm], numeric=(2,)))
    totals = calc.get("totals") or {}
    summary = [
        [p(TEXT["customs_value"]), _amount(calc.get("total_value"))],
        [p(TEXT["total_taxes"]), _amount(totals.get("total"))],
    ]
    tci = (totals.get("other_accounts") or {}).get("TCI")
    if "TCI" in (totals.get("other_accounts") or {}):
        summary.append([p(TEXT["tci"]), _amount(tci)])
    summary.append([p(TEXT["ri"]), "—"])
    table = grid(summary, [130 * mm, 40 * mm], header=False, numeric=(1,))
    table.setStyle(TableStyle([("FONT", (1, 1), (1, 1), "Vera-Bold", 9)]))
    story += [Spacer(1, 4), table]

    story.append(p(TEXT["sources"], h2))
    story.append(grid([[p(k), p(v)] for k, v in ctx["sources"]], [45 * mm, 125 * mm], header=False))
    story.append(Spacer(1, 3))
    story.append(p(calc.get("warning") or "", small))

    story.append(p(TEXT["decisions"], h2))
    if ctx["decisions"]:
        for d in ctx["decisions"]:
            reason = f" : « {d['reason']} »" if d["reason"] else ""
            story.append(p(f"{d['label']} par {d['actor']}, le {d['at']}{reason}", base))
    else:
        story.append(p("—", base))
    story += [Spacer(1, 8), p(ctx["generated"], small)]

    draft = ctx["marking"] == CaseExport.Marking.DRAFT

    def decorate(canvas, doc):
        canvas.saveState()
        if draft:
            canvas.setFont("Vera-Bold", 80)
            canvas.setFillColor(colors.Color(0.85, 0.2, 0.15, alpha=0.12))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, TEXT["draft_mark"])
            canvas.restoreState()
            canvas.saveState()
        canvas.setFont("Vera", 7)
        canvas.setFillColor(colors.HexColor("#6b7780"))
        footer = f"{ctx['identification'][0][1]} · {TEXT['revision']} {ctx['identification'][1][1]}"
        footer += f" · {CaseExport.Marking(ctx['marking']).label} · {doc.page}"
        canvas.drawString(20 * mm, 10 * mm, footer)
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"{TEXT['title']} {ctx['identification'][0][1]}",
        author=ctx["identification"][2][1],
        invariant=1,
    )
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()


# --- XLSX ------------------------------------------------------------------------------


def safe_text(value):
    """Texte gardé comme texte : jamais converti en nombre ni lu comme une formule (EXP-02)."""
    return "" if value is None else str(value)


def build_xlsx(ctx) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    bold = Font(bold=True)
    wb = Workbook()

    def put(ws, row, col, value, *, number=False):
        cell = ws.cell(row=row, column=col)
        if number and value not in (None, ""):
            cell.value = Decimal(str(value))
            cell.number_format = "#,##0"
        else:
            cell.value = safe_text(value)
            # Forcé en texte : un code « 01011010 » garde son zéro, « =… » reste un texte.
            cell.data_type = "s"
            if cell.value.startswith(FORMULA_PREFIXES):
                cell.quotePrefix = True
        return cell

    calc = ctx["calc"]
    ws = wb.active
    ws.title = "Marchandises"
    row = 1
    for line in ctx["banners"]:
        cell = put(ws, row, 1, line)
        cell.font = bold
        fill = "E6F4EC" if ctx["marking"] == CaseExport.Marking.VALIDATED else "FFF4E0"
        cell.fill = PatternFill("solid", fgColor=fill)
        row += 1
    row += 1
    tax_codes = []
    for a in calc.get("articles") or []:
        for t in a.get("taxes") or []:
            if t["code"] not in tax_codes:
                tax_codes.append(t["code"])
    headers = [TEXT["line"], TEXT["code"], TEXT["code_status"], TEXT["description"], TEXT["value"]]
    headers += [f"{c} (FCFA)" for c in tax_codes] + [TEXT["total"]]
    for col, h in enumerate(headers, 1):
        put(ws, row, col, h).font = bold
    header_row = row
    for a in calc.get("articles") or []:
        row += 1
        put(ws, row, 1, a.get("ordinal"), number=True).number_format = "0"
        put(ws, row, 2, a.get("hs_code") or "")
        put(ws, row, 3, TEXT["status"].get(a.get("code_status"), a.get("code_status")))
        put(ws, row, 4, a.get("description") or "").alignment = Alignment(wrap_text=True)
        put(ws, row, 5, (a.get("value") or {}).get("xaf"), number=True)
        amounts = {t["code"]: t.get("amount") for t in a.get("taxes") or []}
        for i, code in enumerate(tax_codes):
            put(ws, row, 6 + i, amounts.get(code), number=True)
        put(ws, row, 6 + len(tax_codes), a.get("total"), number=True)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    for letter, width in zip("ABCDE", (7, 14, 16, 48, 20), strict=True):
        ws.column_dimensions[letter].width = width

    taxes = wb.create_sheet("Taxes")
    for col, h in enumerate((TEXT["tax"], TEXT["label"], TEXT["amount"]), 1):
        put(taxes, 1, col, h).font = bold
    r = 1
    for code, label, _ in _tax_totals(calc):
        amount = ((calc.get("totals") or {}).get("by_tax") or {}).get(code)
        r += 1
        put(taxes, r, 1, code)
        put(taxes, r, 2, label)
        put(taxes, r, 3, amount, number=True)
    totals = calc.get("totals") or {}
    r += 2
    put(taxes, r, 2, TEXT["customs_value"]).font = bold
    put(taxes, r, 3, calc.get("total_value"), number=True)
    r += 1
    put(taxes, r, 2, TEXT["total_taxes"]).font = bold
    put(taxes, r, 3, totals.get("total"), number=True)
    if "TCI" in (totals.get("other_accounts") or {}):
        r += 1
        put(taxes, r, 2, TEXT["tci"])
        put(taxes, r, 3, totals["other_accounts"]["TCI"], number=True)
    r += 1
    put(taxes, r, 2, TEXT["ri"])
    taxes.column_dimensions["B"].width = 48
    taxes.column_dimensions["C"].width = 18

    meta = wb.create_sheet(TEXT["meta"])
    put(meta, 1, 1, TEXT["field"]).font = bold
    put(meta, 1, 2, TEXT["content"]).font = bold
    rows = [*ctx["identification"], (TEXT["marking"], CaseExport.Marking(ctx["marking"]).label), *ctx["sources"]]
    rows += [
        (d["label"], f"{d['actor']}, {d['at']}" + (f" : {d['reason']}" if d["reason"] else ""))
        for d in ctx["decisions"]
    ]
    rows += [("", calc.get("warning") or ""), ("", ctx["generated"])]
    for i, (k, v) in enumerate(rows, 2):
        put(meta, i, 1, k)
        put(meta, i, 2, v)
    meta.column_dimensions["A"].width = 26
    meta.column_dimensions["B"].width = 90

    wb.properties.creator = "ClairTransit"
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


BUILDERS = {CaseExport.Format.PDF: build_pdf, CaseExport.Format.XLSX: build_xlsx}


@transaction.atomic
def create_export(*, org, actor, case_id, fmt: str) -> CaseExport:
    """Génère, conserve et journalise un export de la révision courante."""
    from apps.core.exceptions import ApiError
    from apps.documents.storage import get_storage

    if fmt not in BUILDERS:
        raise ApiError("VALIDATION_ERROR", "Format d'export inconnu : pdf ou xlsx.", 400)
    case = services.lock_case(org, case_id)
    revision = case.current_revision
    ctx = _context(case, revision, actor)
    content = BUILDERS[fmt](ctx)
    stored = get_storage().put(io.BytesIO(content), prefix=f"exports/{org.id}")
    suffix = "" if ctx["marking"] == CaseExport.Marking.VALIDATED else "_brouillon"
    export = CaseExport.objects.create(
        organization=org,
        revision=revision,
        format=fmt,
        marking=ctx["marking"],
        filename=f"{case.reference}_r{revision.revision_no}{suffix}.{fmt}",
        object_key=stored.key,
        sha256=stored.sha256,
        bytes=stored.size,
        calculation_fingerprint=ctx["fingerprint"],
        created_by=actor,
    )
    services._event(
        org,
        actor,
        "revision.exported",
        revision,
        case,
        None,
        {"format": fmt, "marking": export.marking, "sha256": export.sha256},
    )
    return export


def export_payload(e: CaseExport) -> dict:
    return {
        "id": str(e.id),
        "revision_no": e.revision.revision_no,
        "format": e.format,
        "format_label": e.get_format_display(),
        "marking": e.marking,
        "marking_label": e.get_marking_display(),
        "filename": e.filename,
        "bytes": e.bytes,
        "sha256": e.sha256,
        "created_at": e.created_at,
        "created_by": e.created_by.full_name or e.created_by.email,
    }
