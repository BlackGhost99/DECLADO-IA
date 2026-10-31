"""Projet de déclaration au modèle du Document administratif unique (DAU), prérempli par ClairTransit.

Les cases reprennent la numérotation du formulaire fourni par l'exploitant. Elles sont remplies
avec les données du dossier, et rien n'est inventé : une case sans donnée prouvée reste vide
(colis, masses, opérateurs). Les cases réservées à la Douane (n° de déclaration, enregistrement,
contrôle, approbation) restent toujours vides.

Ce document sert à saisir la déclaration dans SYDONIA. Il ne vaut pas déclaration. Le calcul
des impositions est celui de la préparation ClairTransit et la liquidation reste celle de la
Douane. Un brouillon porte la mention BROUILLON, et une révision validée porte seulement la
mention de validation interne.
"""

import io
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from apps.extraction import readers
from apps.extraction.api import document_fields
from apps.extraction.models import ExtractionRun
from apps.extraction.services import invoice_totals
from apps.fiscal import rules

from . import services
from .models import CaseDocument, CaseExport

# Incoterms dont le prix comprend déjà le fret, et ceux qui comprennent aussi l'assurance.
FREIGHT_IN_PRICE = {"CFR", "CPT", "CIF", "CIP", "DAP", "DPU", "DDP"}
INSURANCE_IN_PRICE = {"CIF", "CIP"}
# Tableau imbriqué collé à son cadre : aucune marge intérieure.
FLAT = [(f"{side}PADDING", (0, 0), (-1, -1), 0) for side in ("LEFT", "RIGHT", "TOP", "BOTTOM")]
LOGO = Path(__file__).parent / "assets" / "logo-clairtransit.jpg"

TEXT = {
    "country": "RÉPUBLIQUE GABONAISE",
    "administration": "DIRECTION GÉNÉRALE DES DOUANES\nET DROITS INDIRECTS",
    "title": "DÉCLARATION EN DOUANE\nIMPORTATION",
    "subtitle": "(Document Administratif Unique)",
    "project": (
        "Projet préparé avec ClairTransit, à saisir dans SYDONIA : ce document ne vaut pas déclaration "
        "et n'est pas accepté par la Douane."
    ),
    "footer": "Projet ClairTransit : ne vaut pas déclaration.",
    "taxes_note": "Préparation ClairTransit : la liquidation reste celle de la Douane.",
    "draft": "BROUILLON",
    "page": "Page {n}",
    "many": "plusieurs",
    "included": "compris ({inc})",
    "sydonia": "SYDONIA",
    "by_line": "variable",
    "account2": "c. 2",
    "total": "TOTAL",
}


def _amount(value) -> str:
    if value in (None, ""):
        return ""
    number = Decimal(str(value)).quantize(Decimal("1"))
    return f"{number:,}".replace(",", " ")


def _money(value) -> str:
    """Montant en devise avec ses décimales : 16 124,00."""
    if value in (None, ""):
        return ""
    number = Decimal(str(value)).quantize(Decimal("0.01"))
    whole, _, cents = f"{number:,}".partition(".")
    return f"{whole.replace(',', chr(0xA0))},{cents}"


def _code(code: str | None) -> str:
    if code and len(code) == 8 and code.isdigit():
        return f"{code[:4]}.{code[4:6]}.{code[6:]}"
    return code or ""


def _retained(fields: list[dict], name: str) -> str:
    for f in fields:
        if f["field"] == name:
            entered = f.get("entered") or {}
            return str(entered.get("raw") or f.get("raw") or "")
    return ""


def _latest_run(link):
    return (
        ExtractionRun.objects.filter(case_document=link, status=ExtractionRun.Status.SUCCEEDED)
        .order_by("-created_at")
        .first()
    )


def _invoice_reference(run, name: str) -> str:
    if run is None:
        return ""
    obs = run.observations.filter(entity_key="document", field_name=name).exclude(raw_value=None).first()
    return obs.raw_value if obs is not None and obs.raw_value else ""


def data(case, revision, calc) -> dict:
    """Valeurs des cases, en texte ; une case inconnue reste une chaîne vide (inconnu ≠ 0)."""
    invoices = list(revision.invoices.prefetch_related("lines").order_by("ordinal"))
    links = list(revision.documents.filter(replaced_by__isnull=True).select_related("document").order_by("created_at"))
    suppliers = sorted({inv.supplier_name for inv in invoices if inv.supplier_name})
    currencies = sorted({inv.currency.upper() for inv in invoices if inv.currency})
    incoterms = sorted({inv.incoterm for inv in invoices if inv.incoterm})
    totals = [inv.declared_total for inv in invoices]
    invoice_total = sum(totals, Decimal("0")) if totals and None not in totals and len(currencies) == 1 else None

    containers, transport = [], []
    for link in links:
        run = _latest_run(link)
        if link.usage == CaseDocument.Usage.INVOICE:
            container = _invoice_reference(run, "container")
            if container and container not in containers:
                containers.append(container)
            bl = _invoice_reference(run, "related_bl")
            if bl and not any(t["reference"] == bl for t in transport):
                transport.append({"type": "B/L", "reference": bl, "date": ""})
        elif link.usage == CaseDocument.Usage.TRANSPORT and run is not None:
            fields = document_fields(run) if run.options.get("reader") == readers.TRANSPORT else []
            number = _retained(fields, "transport_number")
            if number and any(t["reference"] == number for t in transport):
                continue
            transport.append(
                {
                    "type": link.document.original_name if not number else "B/L",
                    "reference": number,
                    "date": _retained(fields, "issue_date"),
                }
            )

    articles = {a["goods_line_id"]: a for a in calc.get("articles") or []}
    goods = []
    for g in revision.goods_lines.order_by("ordinal").prefetch_related("sources__invoice_line", "decisions"):
        sources = list(g.sources.all())
        lines = [s.invoice_line for s in sources]
        quantities = [ln.quantity for ln in lines]
        units = sorted({ln.unit for ln in lines if ln.unit})
        values = [s.assigned_value for s in sources]
        decision = services.current_decision(g)
        code = decision.selected_code if decision is not None and services.decision_is_current(decision, g) else ""
        goods.append(
            {
                "no": str(g.ordinal),
                "description": g.description,
                "code": _code(code),
                "origin": g.origin_country,
                "quantity": format(sum(quantities, Decimal("0")).normalize(), "f")
                if quantities and None not in quantities
                else "",
                "unit": ", ".join(units),
                "value": _money(sum(values, Decimal("0"))) if values and None not in values else "",
                "regime": revision.regime,
                "customs_value": _amount((articles.get(str(g.id)) or {}).get("value", {}).get("xaf")),
            }
        )

    origins = sorted({g["origin"] for g in goods if g["origin"]})
    freight = [(a.get("value") or {}).get("freight") for a in articles.values()]
    insurance = [(a.get("value") or {}).get("insurance") for a in articles.values()]

    def added(values):
        known = [Decimal(str(v)) for v in values if v not in (None, "")]
        return _amount(sum(known, Decimal("0"))) if known else ""

    incoterm = incoterms[0].split(" ")[0].upper() if len(incoterms) == 1 else ""
    fees = Decimal("0")
    fee_currency = currencies[0] if len(currencies) == 1 else ""
    for inv in invoices:
        comp = invoice_totals(inv)["components"]
        if comp.get("fees") not in (None, ""):
            fees += Decimal(str(comp["fees"]))

    documents = []
    labels = dict(CaseDocument.Usage.choices)
    for link in links:
        documents.append(
            {
                "code": labels.get(link.usage, link.usage),
                "reference": link.document.original_name,
                "date": link.created_at.strftime("%d/%m/%Y"),
            }
        )

    importer = case.importer
    nif = ""
    if importer is not None:
        nif = " ".join(str(v) for v in (importer.identifiers or {}).values() if v)

    return {
        "model": "IM",
        "regime": revision.regime,
        "office": revision.entry_office,
        "exporter": "\n".join(suppliers),
        "references": " · ".join(x for x in (case.reference, revision.client_reference) if x),
        "destination": revision.territory,
        "consignee": "\n".join(x for x in (importer.name, importer.address) if x) if importer else "",
        "consignee_id": nif,
        "export_country": revision.provenance_country,
        "origin": origins[0] if len(origins) == 1 else (TEXT["many"] if origins else ""),
        "provenance": revision.provenance_country,
        "transport_mode": revision.get_transport_mode_display() if revision.transport_mode else "",
        "declarant": case.organization.name,
        "incoterm": incoterm,
        "incoterm_place": incoterms[0][len(incoterm) :].strip(" ,") if len(incoterms) == 1 else "",
        "currency": ", ".join(currencies),
        "invoice_total": _money(invoice_total),
        "articles": str(len(goods)),
        "freight": added(freight) or (TEXT["included"].format(inc=incoterm) if incoterm in FREIGHT_IN_PRICE else ""),
        "insurance": added(insurance)
        or (TEXT["included"].format(inc=incoterm) if incoterm in INSURANCE_IN_PRICE else ""),
        "other_fees": f"{_money(fees)} {fee_currency}".strip() if fees else "",
        "cif": _amount(calc.get("total_value")),
        "containers": containers,
        "transport": transport,
        "goods": goods,
        "documents": documents,
        "taxes": taxes(calc),
        "total_taxes": _amount((calc.get("totals") or {}).get("total")),
    }


def taxes(calc) -> list[dict]:
    """Case 46 : une ligne par taxe, assiette et montant additionnés sur les articles."""
    rows: dict[str, dict] = {}
    rates: dict[str, set] = defaultdict(set)
    order = [r.code for r in rules.ARTICLE_TAXES]
    for article in calc.get("articles") or []:
        for t in article.get("taxes") or []:
            row = rows.setdefault(t["code"], {"code": t["code"], "base": Decimal("0"), "amount": Decimal("0")})
            for key in ("base", "amount"):
                if row[key] is not None:
                    row[key] = None if t.get(key) in (None, "") else row[key] + Decimal(str(t[key]))
            rates[t["code"]].add(t.get("rate"))
    out = []
    for code, row in sorted(rows.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99):
        if code in rules.SYDONIA_TAXES:
            out.append({"code": code, "base": "", "rate": "", "amount": TEXT["sydonia"]})
            continue
        found = rates[code]
        rate = next(iter(found)) if len(found) == 1 else None
        out.append(
            {
                "code": code + (f" ({TEXT['account2']})" if code == "TCI" else ""),
                "base": _amount(row["base"]),
                "rate": f"{Decimal(str(rate)).normalize():f} %" if rate not in (None, "") else TEXT["by_line"],
                "amount": _amount(row["amount"]),
            }
        )
    for g in calc.get("global_taxes") or []:
        if g["code"] in rules.SYDONIA_TAXES and not any(r["code"] == g["code"] for r in out):
            out.append({"code": g["code"], "base": "", "rate": "", "amount": TEXT["sydonia"]})
    return out


# --- Rendu ------------------------------------------------------------------------------


def build(ctx) -> bytes:
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

    d = ctx["dau"]
    ink = colors.HexColor("#1d2b24")
    band = colors.HexColor("#e3f1e7")
    line = colors.HexColor("#5d6b63")
    value_style = ParagraphStyle("v", fontName="Vera", fontSize=7.6, leading=9.4, textColor=ink)
    label_style = ParagraphStyle("l", fontName="Vera-Bold", fontSize=6.6, leading=8, textColor=ink, backColor=band)
    head_style = ParagraphStyle("h", fontName="Vera-Bold", fontSize=6.4, leading=7.8, textColor=ink, alignment=1)
    title_style = ParagraphStyle("t", fontName="Vera-Bold", fontSize=10.5, leading=13, alignment=1, textColor=ink)
    small = ParagraphStyle("s", fontName="Vera", fontSize=6.6, leading=8, textColor=ink, alignment=1)
    num_style = ParagraphStyle("n", parent=value_style, alignment=2)

    def p(text, style=value_style):
        return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)

    def box(number, label, value="", style=value_style):
        title = f"{number}  {label}" if number else label
        return [p(title, label_style), p(value, style)]

    def frame(rows, widths, spans=(), extra=()):
        table = Table(rows, colWidths=[w * mm for w in widths], hAlign="LEFT")
        style = [
            ("BOX", (0, 0), (-1, -1), 0.9, line),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        style += [("SPAN", a, b) for a, b in spans]
        table.setStyle(TableStyle(style + list(extra)))
        return table

    def grid(title, header, rows, widths, numeric=(), min_rows=0, total=None):
        body = [[p(h, head_style) for h in header]]
        for r in rows:
            body.append([p(v, num_style if i in numeric else value_style) for i, v in enumerate(r)])
        for _ in range(max(0, min_rows - len(rows))):
            body.append([""] * len(header))
        if total is not None:
            body.append(total)
        inner_table = Table(body, colWidths=[w * mm for w in widths], repeatRows=1, hAlign="LEFT")
        table = Table([[p(title, label_style)], [inner_table]], colWidths=[sum(widths) * mm], hAlign="LEFT")
        inner_table.setStyle(
            TableStyle(
                [
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, line),
                    ("LINEABOVE", (0, 0), (-1, 0), 0.4, line),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONT", (0, 0), (-1, -1), "Vera", 7.4),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white]),
                ]
            )
        )
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.9, line),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return table

    story = []

    # En-tête : administration, titre, cases 1 à 4.
    header = frame(
        [
            [
                [p(TEXT["country"], ParagraphStyle("c", parent=value_style, fontName="Vera-Bold", fontSize=8.4)),
                 p(TEXT["administration"])],
                [p(TEXT["title"], title_style), p(TEXT["subtitle"], small)],
                box("1", "TYPE DE DÉCLARATION", ""),
                box("2", "N° DE DÉCLARATION", "GA/____/____/________"),
            ],
            ["", "", frame([[box("1.1", "Modèle", d["model"]), box("1.2", "Régime", d["regime"]),
                             box("1.3", "Formulaire", "1")]], [12, 20, 18]),
             frame([[box("3", "Bureau de dédouanement", d["office"]), box("4", "Page")]], [36, 14])],
        ],
        [45, 35, 50, 50],
        spans=[((0, 0), (0, 1)), ((1, 0), (1, 1))],
        extra=[("LEFTPADDING", (2, 1), (3, 1), 0), ("RIGHTPADDING", (2, 1), (3, 1), 0),
               ("TOPPADDING", (2, 1), (3, 1), 0), ("BOTTOMPADDING", (2, 1), (3, 1), 0)],
    )  # fmt: skip
    story += [header, Spacer(1, 2.5 * mm)]

    parties = frame(
        [
            [box("5", "Exportateur (nom et adresse complète)", d["exporter"]), box("6", "N° d'opérateur"),
             box("7", "Références du déclarant", d["references"]), box("8", "Date d'enregistrement")],
            ["", "", box("9", "Bureau d'entrée (et pays)", d["office"]),
             box("10", "Pays de destination finale", d["destination"])],
            [box("11", "Destinataire (nom et adresse complète)", d["consignee"]),
             box("12", "N° d'opérateur", d["consignee_id"]),
             frame([[box("13", "Pays d'exportation", d["export_country"]), box("14", "Pays d'origine", d["origin"]),
                     box("15", "Pays de destination", d["destination"])]], [33, 33, 34]), ""],
            ["", "", frame([[box("16", "Pays de provenance", d["provenance"]),
                             box("17", "Code mode transport", d["transport_mode"]),
                             box("18", "Identité du moyen de transport à l'arrivée")]], [33, 33, 34]), ""],
            [box("19", "Représentant en douane / Déclarant (nom et adresse)", d["declarant"]),
             box("20", "N° d'opérateur"),
             frame([[box("21", "Conditions de livraison (Incoterm)", ""), ""],
                    [box("", "Code", d["incoterm"]), box("", "Lieu", d["incoterm_place"])]], [25, 25],
                   spans=[((0, 0), (1, 0))]),
             frame([[box("22", "Devise et montant total facture", ""), ""],
                    [box("", "Devise", d["currency"]), box("", "Montant", d["invoice_total"], num_style)]], [18, 32],
                   spans=[((0, 0), (1, 0))])],
        ],
        [55, 25, 50, 50],
        spans=[((0, 0), (0, 1)), ((1, 0), (1, 1)), ((0, 2), (0, 3)), ((1, 2), (1, 3)),
               ((2, 2), (3, 2)), ((2, 3), (3, 3))],
        extra=[("LEFTPADDING", (2, 2), (3, 4), 0), ("RIGHTPADDING", (2, 2), (3, 4), 0),
               ("TOPPADDING", (2, 2), (3, 4), 0), ("BOTTOMPADDING", (2, 2), (3, 4), 0)],
    )  # fmt: skip
    story += [parties, Spacer(1, 2.5 * mm)]

    story.append(
        frame(
            [[box("23", "Nombre total de colis"), box("24", "Nature des colis"), box("25", "Masse brute totale (kg)"),
              box("26", "Masse nette totale (kg)"), box("27", "Nombre d'articles", d["articles"])]],
            [34, 34, 38, 38, 36],
        )
    )  # fmt: skip
    story.append(
        frame(
            [[box("28", "Informations financières (FCFA)"), "", "", box("29", "Valeur totale FOB"),
              box("30", "Valeur totale CIF (FCFA)", d["cif"], num_style)],
             [box("28.1", "Fret international", d["freight"]), box("28.2", "Assurance", d["insurance"]),
              box("28.3", "Autres frais", d["other_fees"]), "", ""]],
            [36, 36, 36, 36, 36],
            spans=[((0, 0), (2, 0)), ((3, 0), (3, 1)), ((4, 0), (4, 1))],
        )
    )  # fmt: skip
    story.append(Spacer(1, 2.5 * mm))

    containers = [[c, "", "", ""] for c in d["containers"]]
    transport = [[t["type"], t["reference"], t["date"]] for t in d["transport"]]
    side = Table(
        [
            [grid("32  Documents de transport", ["Type", "Référence", "Date"], transport, [26, 42, 22], min_rows=2)],
            [frame([[box("33", "Mention spéciale", TEXT["project"])]], [90])],
        ],
        hAlign="LEFT",
        colWidths=[90 * mm],
    )
    side.setStyle(TableStyle(FLAT))
    pair = Table(
        [[grid("31  Colis et conteneurs", ["N° conteneur", "Type", "Nombre", "Nombs (n°)"], containers,
               [30, 18, 18, 24], min_rows=2), side]],
        hAlign="LEFT",
        colWidths=[90 * mm, 90 * mm],
    )  # fmt: skip
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), *FLAT]))
    story += [pair, Spacer(1, 2.5 * mm)]

    header = ["N°", "35 Marques, nombre et nature des colis", "36 Désignation des marchandises",
              "37 Code SH", "38 Origine", "39 Masse brute (kg)", "40 Masse nette (kg)",
              "41 Quantité\n42 Unité", f"43 Valeur en devises ({d['currency'] or '?'})", "44 Régime"]  # fmt: skip
    rows = [
        [g["no"], "", g["description"], g["code"], g["origin"], "", "",
         f"{g['quantity']} {g['unit']}".strip(), g["value"], g["regime"]]
        for g in d["goods"]
    ]  # fmt: skip
    story.append(
        grid("34  Articles et marchandises", header, rows, [8, 18, 42, 21, 13, 13, 13, 15, 21, 16],
             numeric=(7, 8), min_rows=3)
    )  # fmt: skip
    story.append(Spacer(1, 2.5 * mm))

    docs = [[x["code"], x["reference"], x["date"], "", ""] for x in d["documents"]]
    tax_rows = [[t["code"], t["base"], t["rate"], t["amount"]] for t in d["taxes"]]
    total = [p(TEXT["total"], label_style), "", "", p(d["total_taxes"], num_style)]
    bottom = Table(
        [[grid("45  Documents produits, certificats et autorisations",
               ["Code", "Référence", "Date", "Autorité émettrice", "Description"], docs, [17, 23, 20, 20, 20],
               min_rows=3),
          grid("46  Calcul des impositions (préparation)", ["Type", "Assiette", "Taux", "Montant"], tax_rows,
               [17, 22, 17, 24], numeric=(1, 3), min_rows=4, total=total)]],
        hAlign="LEFT",
        colWidths=[100 * mm, 80 * mm],
    )  # fmt: skip
    bottom.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), *FLAT]))
    story += [bottom, p(TEXT["taxes_note"], ParagraphStyle("tn", parent=value_style, fontSize=6.4, alignment=2))]

    customs = frame(
        [[box("47", "Contrôle par la douane", "[  ] Voie verte   [  ] Voie jaune\n[  ] Voie rouge   [  ] Autre :"),
          box("48", "Approbation de la déclaration",
              "Déclaration acceptée le :\nAgent et matricule :\nSignature :"),
          box("49", "Observations"), ],
         ["", "", box("50", "Bon à enlever", "Date, bureau et signature :")]],
        [50, 70, 60],
        spans=[((0, 0), (0, 1)), ((1, 0), (1, 1))],
    )  # fmt: skip
    story.append(customs)

    draft = ctx["marking"] == CaseExport.Marking.DRAFT
    reference = ctx["identification"][0][1]

    def decorate(canvas, doc):
        canvas.saveState()
        if LOGO.exists():
            # Logo de l'application en filigrane, comme sur le modèle fourni.
            canvas.setFillAlpha(0.07)
            size = 150 * mm
            canvas.drawImage(str(LOGO), (A4[0] - size) / 2, A4[1] / 2 - size / 3, width=size,
                             height=size * 2 / 3, mask="auto")  # fmt: skip
        canvas.restoreState()
        canvas.saveState()
        if draft:
            canvas.setFont("Vera-Bold", 80)
            canvas.setFillColor(colors.Color(0.85, 0.2, 0.15, alpha=0.12))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, TEXT["draft"])
        canvas.restoreState()
        canvas.saveState()
        canvas.setFont("Vera", 6.5)
        canvas.setFillColor(colors.HexColor("#5d6b63"))
        footer = f"{reference} · {CaseExport.Marking(ctx['marking']).label} · {TEXT['footer']}"
        canvas.drawString(15 * mm, 7 * mm, footer)
        canvas.drawRightString(A4[0] - 15 * mm, 7 * mm, TEXT["page"].format(n=doc.page))
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        # Le cadre de page ajoute 6 points de chaque côté : la largeur utile reste de 180 mm.
        leftMargin=15 * mm - 6,
        rightMargin=15 * mm - 6,
        topMargin=10 * mm,
        bottomMargin=13 * mm,
        title=f"Projet de déclaration {reference}",
        author=ctx["identification"][2][1],
        invariant=1,
    )
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()
