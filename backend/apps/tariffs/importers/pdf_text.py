"""Import d'un texte déjà extrait d'un PDF tarifaire (copie dérivée).

Ce texte ne contient ni coordonnées ni mise en page : les colonnes du tableau y sont
séparées en blocs (codes, puis désignations, puis taux). L'importateur conserve chaque
page brute, repère les sections, chapitres, notes et codes avec leur page, et signale les
anomalies. Il n'associe **aucun** libellé ni taux à un code : sans coordonnées, une
association par simple ordre de lecture serait une supposition (conception §6, point 4).

Convention de pagination (hypothèse à vérifier sur le PDF original) : le texte qui
précède le premier numéro isolé est la page physique 1 (couverture) ; le segment qui suit
le marqueur « N » est la page physique N+1, de numéro imprimé N.
"""

import re
from collections import Counter
from pathlib import Path

from django.db import transaction

from ..models import (
    CodeOccurrence,
    ImportIssue,
    ImportRun,
    LegalNote,
    NodeKind,
    RawTariffRecord,
    SourceKind,
    TariffEdition,
    TariffNode,
    ValidationState,
)
from ..text import search_normalize
from .common import IssueCollector, clean_label, finish_run, register_source, source_path

IMPORTER_NAME = "pdf_text_extract"
IMPORTER_VERSION = "1.0"
S = ImportIssue.Severity

PAGE_MARKER = re.compile(r"\n\n(\d{1,4})\n")
TARIFF_LINE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})\.?$")
HEADING = re.compile(r"^(\d{2})\.(\d{2})$")
CODE_LIKE = re.compile(r"^(?=.*\d.*\.)[\d.]{5,}$")
SECTION = re.compile(r"^Section\s+([IVXLC]+)$")
CHAPTER = re.compile(r"^Chapitre\s*([IVXLC]+|\d{1,2}|premier)$", re.IGNORECASE)
TABLE_HEADER = "NUMERO"
TABLE_START = re.compile(r"TABLEAU\s*\n\s*DES\s*\n\s*DROITS ET TAXES")

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(value: str) -> int:
    total, prev = 0, 0
    for ch in reversed(value.upper()):
        n = ROMAN[ch]
        total = total - n if n < prev else total + n
        prev = max(prev, n)
    return total


def chapter_number(token: str) -> int:
    if token.lower() == "premier":
        return 1
    return int(token) if token.isdigit() else roman_to_int(token)


def split_pages(text: str) -> list[tuple[int, str, str]]:
    """Retourne (page_physique, numéro_imprimé, texte)."""
    parts = PAGE_MARKER.split(text)
    pages = [(1, "", parts[0])]
    for i in range(1, len(parts), 2):
        pages.append((len(pages) + 1, parts[i], parts[i + 1]))
    return pages


def _first_nonempty(lines: list[str], start: int) -> str:
    for line in lines[start : start + 3]:
        if line.strip():
            return line.strip()
    return ""


def _notes_block(lines: list[str], start: int) -> str:
    """Texte de notes depuis `start` jusqu'à l'en-tête de tableau ou au titre suivant."""
    collected = []
    for line in lines[start:]:
        s = line.strip()
        if s == TABLE_HEADER or CHAPTER.match(s) or SECTION.match(s):
            break
        collected.append(line.rstrip())
    return "\n".join(collected).strip()


@transaction.atomic
def import_pdf_text(
    path: Path,
    *,
    edition_label: str,
    title: str,
    actor=None,
    publisher_claimed: str = "",
    provenance_note: str = "",
    hs_version: str = "",
    territory: str = "CEMAC",
) -> TariffEdition:
    source = register_source(
        path,
        kind=SourceKind.PDF_TEXT_EXTRACT,
        title=title,
        is_derived_copy=True,
        actor=actor,
        publisher_claimed=publisher_claimed,
        edition_label_claimed=edition_label,
        provenance_note=provenance_note,
    )
    run = ImportRun.objects.create(
        source=source, importer_name=IMPORTER_NAME, importer_version=IMPORTER_VERSION, created_by=actor
    )
    edition = TariffEdition.objects.create(
        label=edition_label, hs_version=hs_version, territory_scope=territory, import_run=run
    )
    issues = IssueCollector(run)
    text = source_path(source).read_text(encoding="utf-8").replace("\r\n", "\n")
    pages = split_pages(text)

    records = RawTariffRecord.objects.bulk_create(
        [
            RawTariffRecord(run=run, ordinal=idx, page_index=idx, printed_page=printed, raw_text=body)
            for idx, printed, body in pages
        ],
        batch_size=500,
    )
    record_by_page = {r.page_index: r for r in records}

    table_start = next((idx for idx, _, body in pages if TABLE_START.search(body)), 1)

    nodes: dict[str, TariffNode] = {}
    occurrences: list[CodeOccurrence] = []
    notes: list[LegalNote] = []
    sections: list[TariffNode] = []
    sections_by_ref: dict[str, TariffNode] = {}
    current_section = current_chapter = current_heading = None
    order = 0
    page_reasons: Counter[str] = Counter()
    pages_with_codes = 0

    def add_node(code, display, kind, parent, record, label="", validation=ValidationState.REVIEW_REQUIRED):
        nonlocal order
        order += 1
        label_clean, damaged = clean_label(label)
        node = TariffNode(
            edition=edition,
            code=code,
            code_display=display,
            kind=kind,
            parent=parent,
            display_order=order,
            label_raw=label,
            label_clean=label_clean,
            label_damaged=damaged,
            declarable=kind == NodeKind.TARIFF_LINE,
            validation_state=validation,
            source_record=record,
        )
        path = []
        cursor = parent
        while cursor is not None:
            path.insert(0, cursor.code_display or cursor.label_clean)
            cursor = cursor.parent
        node.full_path_label = " › ".join(path + [display or label_clean])
        node.search_text = search_normalize(label_clean)
        if code:
            nodes[code] = node
        return node

    for idx, _printed, body in pages:
        record = record_by_page[idx]
        if idx < table_start:
            page_reasons["avant le tableau des droits (règles, sommaire)"] += 1
            continue
        lines = body.split("\n")
        is_table = any(line.strip() == TABLE_HEADER for line in lines)
        page_codes = 0
        for line_no, line in enumerate(lines, start=1):
            s = line.strip()
            if (m := SECTION.match(s)) and m.group(1) in sections_by_ref:
                current_section = sections_by_ref[m.group(1)]
                continue
            if m := SECTION.match(s):
                current_section = add_node(
                    None,
                    f"Section {m.group(1)}",
                    NodeKind.SECTION,
                    None,
                    record,
                    label=_first_nonempty(lines, line_no),
                    validation=ValidationState.EXTRACTED,
                )
                sections.append(current_section)
                sections_by_ref[m.group(1)] = current_section
                note = _notes_block(lines, line_no + 1)
                if note:
                    notes.append(
                        LegalNote(
                            edition=edition,
                            scope_type="section",
                            scope_ref=m.group(1),
                            heading=current_section.label_clean,
                            text_raw=note,
                            source_record=record,
                        )
                    )
                continue
            if m := CHAPTER.match(s):
                number = chapter_number(m.group(1))
                code = f"{number:02d}"
                if code in nodes:
                    current_chapter = nodes[code]
                    continue
                current_chapter = add_node(
                    code,
                    f"Chapitre {code}",
                    NodeKind.CHAPTER,
                    current_section,
                    record,
                    label=_first_nonempty(lines, line_no),
                    validation=ValidationState.EXTRACTED,
                )
                note = _notes_block(lines, line_no + 1)
                if note:
                    notes.append(
                        LegalNote(
                            edition=edition,
                            scope_type="chapter",
                            scope_ref=code,
                            heading=current_chapter.label_clean,
                            text_raw=note,
                            source_record=record,
                        )
                    )
                continue
            if not is_table:
                continue
            if m := HEADING.match(s):
                code = m.group(1) + m.group(2)
                page_codes += 1
                if code in nodes:
                    occurrences.append(
                        CodeOccurrence(node=nodes[code], source_record=record, raw_code=s, line_no=line_no)
                    )
                    issues.add(
                        "DUPLICATE_CODE",
                        S.REVIEW,
                        f"Position {s} répétée page {idx}.",
                        record=record,
                        node=nodes[code],
                        code=code,
                        line=line_no,
                    )
                    current_heading = nodes[code]
                    continue
                parent = nodes.get(code[:2]) or current_chapter
                if parent is None or parent.code != code[:2]:
                    issues.add(
                        "PARENT_UNKNOWN",
                        S.REVIEW,
                        f"Position {s} page {idx} : chapitre {code[:2]} non repéré.",
                        record=record,
                        code=code,
                        line=line_no,
                    )
                current_heading = add_node(code, s, NodeKind.HEADING, parent, record)
                continue
            if m := TARIFF_LINE.match(s):
                code = "".join(m.groups())
                display = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
                page_codes += 1
                if s.endswith("."):
                    issues.add(
                        "TRAILING_PUNCTUATION",
                        S.INFO,
                        f"Code « {s} » page {idx} : point final ignoré.",
                        record=record,
                        raw_code=s,
                        line=line_no,
                    )
                if code in nodes:
                    occurrences.append(
                        CodeOccurrence(node=nodes[code], source_record=record, raw_code=s, line_no=line_no)
                    )
                    issues.add(
                        "DUPLICATE_CODE",
                        S.REVIEW,
                        f"Code {display} répété page {idx}.",
                        record=record,
                        node=nodes[code],
                        code=code,
                        line=line_no,
                    )
                    continue
                heading = nodes.get(code[:4])
                behind = current_heading is not None and code[:4] < current_heading.code
                if heading is None and not behind:
                    # Position à sous-position unique : souvent non imprimée séparément.
                    chapter = nodes.get(code[:2])
                    if chapter is None:
                        issues.add(
                            "PARENT_UNKNOWN",
                            S.REVIEW,
                            f"Code {display} page {idx} : chapitre {code[:2]} non repéré.",
                            record=record,
                            code=code,
                            line=line_no,
                        )
                    heading = add_node(
                        code[:4],
                        f"{code[:2]}.{code[2:4]}",
                        NodeKind.HEADING,
                        chapter,
                        record,
                        validation=ValidationState.DERIVED,
                    )
                    current_heading = heading
                    mismatch = None
                    mismatch = None
                elif current_heading is not None and (heading is None or heading.code != current_heading.code):
                    mismatch = current_heading
                else:
                    mismatch = None
                line_node = add_node(code, display, NodeKind.TARIFF_LINE, heading or current_heading, record)
                if mismatch is not None:
                    issues.add(
                        "HEADING_MISMATCH",
                        S.REVIEW,
                        f"Code {display} page {idx} lu sous la position {mismatch.code_display} : "
                        "erreur de saisie possible dans la source.",
                        record=record,
                        node=line_node,
                        code=code,
                        line=line_no,
                        read_under=mismatch.code,
                    )
                continue
            if CODE_LIKE.match(s):
                issues.add(
                    "MALFORMED_CODE",
                    S.BLOCKING,
                    f"Chaîne « {s} » page {idx} ressemble à un code mais est mal formée. Non publiée.",
                    record=record,
                    raw_code=s,
                    line=line_no,
                )
        if page_codes:
            pages_with_codes += 1
        elif is_table:
            page_reasons["tableau sans code détecté"] += 1
        else:
            page_reasons["texte sans tableau (notes, titres)"] += 1

    nodes_list = sections + [n for n in nodes.values() if n not in sections]
    TariffNode.objects.bulk_create(nodes_list, batch_size=2000)
    CodeOccurrence.objects.bulk_create(occurrences, batch_size=2000)
    LegalNote.objects.bulk_create(notes, batch_size=500)

    issues.add(
        "LABELS_AND_RATES_NOT_ASSOCIATED",
        S.INFO,
        "Texte extrait sans coordonnées : désignations et taux ne sont pas rattachés aux codes. "
        "Le PDF original est nécessaire pour l'extraction par coordonnées (DEV-007).",
    )
    issues.add(
        "PAGE_MAPPING_HYPOTHESIS",
        S.INFO,
        "Correspondance page physique / numéro imprimé déduite des marqueurs du texte, à vérifier sur le PDF.",
        pages=len(pages),
    )

    kinds = Counter(str(n.kind) for n in nodes_list)
    counts = {"pages": len(pages), "nodes": dict(kinds), "notes": len(notes), "occurrences": len(occurrences)}
    coverage = {
        "pages_total": len(pages),
        "table_starts_at_page": table_start,
        "pages_with_codes": pages_with_codes,
        "pages_without_codes": dict(page_reasons),
    }
    finish_run(run, counts=counts, coverage=coverage, issues=issues)
    return edition
