"""Import d'un export CSV d'un classeur tarifaire (copie dérivée de l'Excel).

Chaque ligne est conservée brute avec sa plage A1. Les colonnes autres que code et
libellé deviennent des observations historiques, jamais des règles fiscales. Une cellule
vide reste « inconnue », distincte de zéro. Le CSV ne contient ni formules ni valeurs en
cache : cette perte est signalée.
"""

import csv
import io
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction

from ..codes import hierarchy_prefixes, normalize_code
from ..models import (
    CodeOccurrence,
    ImportIssue,
    ImportRun,
    NodeKind,
    RateObservation,
    RawTariffRecord,
    SourceKind,
    TariffEdition,
    TariffNode,
    ValidationState,
)
from ..text import search_normalize
from .common import IssueCollector, clean_label, finish_run, register_source, source_path

IMPORTER_NAME = "csv_export"
IMPORTER_VERSION = "1.0"
S = ImportIssue.Severity


def _col_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _parse_decimal(raw: str) -> Decimal | None:
    value = raw.strip().replace(" ", "")
    if value.count(",") == 1 and "." not in value:
        value = value.replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _display(code: str) -> str:
    if len(code) == 2:
        return code
    if len(code) == 4:
        return f"{code[:2]}.{code[2:]}"
    if len(code) == 6:
        return f"{code[:4]}.{code[4:]}"
    if len(code) == 8:
        return f"{code[:4]}.{code[4:6]}.{code[6:]}"
    return code


@transaction.atomic
def import_csv(
    path: Path,
    *,
    edition_label: str,
    title: str,
    code_length: int = 8,
    actor=None,
    publisher_claimed: str = "",
    provenance_note: str = "",
    territory: str = "CEMAC",
) -> TariffEdition:
    source = register_source(
        path,
        kind=SourceKind.CSV_EXPORT,
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
    edition = TariffEdition.objects.create(label=edition_label, territory_scope=territory, import_run=run)
    issues = IssueCollector(run)

    data = source_path(source).read_bytes()
    try:
        text = data.decode("utf-8-sig")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
        encoding = "cp1252"
        issues.add("ENCODING_GUESSED", S.REVIEW, "Fichier non UTF-8 : décodé en cp1252, à vérifier.")
    delimiter = csv.Sniffer().sniff(text[:5000], delimiters=";,\t").delimiter
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    header, body = rows[0], rows[1:]
    last_col = _col_letter(len(header) - 1)

    issues.add(
        "FORMULAS_UNAVAILABLE",
        S.INFO,
        "Source CSV : les formules et valeurs en cache de l'Excel d'origine ne sont pas disponibles (REF-02). "
        "Fournir le classeur .xlsx pour les conserver.",
    )

    records = [RawTariffRecord(run=run, ordinal=1, sheet="CSV", cell_range=f"A1:{last_col}1", raw_cells=header)]
    for n, row in enumerate(body, start=2):
        records.append(
            RawTariffRecord(
                run=run, ordinal=n, sheet="CSV", cell_range=f"A{n}:{_col_letter(len(row) - 1)}{n}", raw_cells=row
            )
        )
    RawTariffRecord.objects.bulk_create(records, batch_size=2000)
    by_ordinal = {r.ordinal: r for r in RawTariffRecord.objects.filter(run=run)}

    value_columns = list(range(2, len(header)))
    column_values: dict[int, Counter] = {i: Counter() for i in value_columns}
    nodes: dict[str, TariffNode] = {}
    derived: dict[str, TariffNode] = {}
    occurrences: list[CodeOccurrence] = []
    observations: list[tuple[str, RawTariffRecord, int, str]] = []
    damaged_examples = []
    order = 0

    for n, row in enumerate(body, start=2):
        record = by_ordinal[n]
        if len(row) != len(header):
            issues.add(
                "ROW_SHAPE", S.REVIEW, f"Ligne {n} : {len(row)} colonnes au lieu de {len(header)}.", record=record
            )
        raw_code = row[0] if row else ""
        code = normalize_code(raw_code)
        if code is None or len(code) != code_length:
            issues.add(
                "MALFORMED_CODE",
                S.BLOCKING,
                f"Ligne {n} : code « {raw_code} » mal formé (attendu {code_length} chiffres). Non publié.",
                record=record,
                raw_code=raw_code,
            )
            continue
        if code in nodes:
            occurrences.append(CodeOccurrence(node=nodes[code], source_record=record, raw_code=raw_code))
            issues.add(
                "DUPLICATE_CODE",
                S.REVIEW,
                f"Code {_display(code)} répété ligne {n}.",
                record=record,
                node=nodes[code],
                code=code,
            )
            continue
        label_raw = row[1] if len(row) > 1 else ""
        label_clean, damaged = clean_label(label_raw)
        if damaged and len(damaged_examples) < 10:
            damaged_examples.append({"code": code, "cells": f"B{n}", "label": label_clean})
        order += 1
        node = TariffNode(
            edition=edition,
            code=code,
            code_display=_display(code),
            kind=NodeKind.TARIFF_LINE,
            display_order=order,
            label_raw=label_raw,
            label_clean=label_clean,
            label_damaged=damaged,
            declarable=True,
            validation_state=ValidationState.EXTRACTED,
            source_record=record,
        )
        nodes[code] = node
        for prefix, kind in hierarchy_prefixes(code):
            if prefix not in derived:
                derived[prefix] = TariffNode(
                    edition=edition,
                    code=prefix,
                    code_display=_display(prefix),
                    kind=kind,
                    validation_state=ValidationState.DERIVED,
                    declarable=False,
                )
        for i in value_columns:
            raw = row[i] if i < len(row) else ""
            column_values[i][raw.strip()] += 1
            observations.append((code, record, i, raw))

    # Parents dérivés : présents dans la hiérarchie SH mais sans libellé dans cette source.
    for prefix, node in derived.items():
        ancestors = [derived[p] for p, _ in hierarchy_prefixes(prefix)]
        node.parent = ancestors[-1] if ancestors else None
        node.full_path_label = " › ".join([a.code_display for a in ancestors] + [node.code_display])
    for code, node in nodes.items():
        parents = [derived[p] for p, _ in hierarchy_prefixes(code)]
        node.parent = parents[-1] if parents else None
        path = " › ".join(p.code_display for p in parents)
        node.full_path_label = f"{path} › {node.label_clean}" if path else node.label_clean
        node.search_text = search_normalize(node.label_clean)
    TariffNode.objects.bulk_create(sorted(derived.values(), key=lambda n: len(n.code)), batch_size=2000)
    TariffNode.objects.bulk_create(list(nodes.values()), batch_size=2000)
    CodeOccurrence.objects.bulk_create(occurrences, batch_size=2000)

    quality = Counter()
    rate_rows = []
    for code, record, i, raw in observations:
        value = _parse_decimal(raw) if raw.strip() else None
        if not raw.strip():
            q = RateObservation.Quality.UNKNOWN
        elif value is None:
            q = RateObservation.Quality.UNPARSEABLE
        else:
            q = RateObservation.Quality.KNOWN
        quality[str(q)] += 1
        rate_rows.append(
            RateObservation(
                node=nodes[code],
                source_record=record,
                column=header[i],
                column_index=i,
                raw_value=raw,
                value=value,
                quality=q,
            )
        )
    RateObservation.objects.bulk_create(rate_rows, batch_size=5000)

    for i, values in column_values.items():
        non_empty = {v: c for v, c in values.items() if v}
        numeric = sum(c for v, c in non_empty.items() if _parse_decimal(v) is not None)
        total = sum(non_empty.values())
        if total and numeric / total < 0.5:
            issues.add(
                "COLUMN_CONTENT_MISMATCH",
                S.REVIEW,
                f"Colonne « {header[i]} » : majoritairement non numérique ({total - numeric}/{total}). "
                "Sa signification doit être établie avant tout usage.",
                column=header[i],
                top_values=Counter(non_empty).most_common(8),
            )
        empty = values.get("", 0)
        if empty:
            issues.add(
                "MISSING_VALUES",
                S.INFO,
                f"Colonne « {header[i]} » : {empty} cellule(s) vide(s), conservées comme inconnues (≠ 0).",
                column=header[i],
                empty=empty,
            )
    damaged_count = sum(1 for n in nodes.values() if n.label_damaged)
    if damaged_count:
        issues.add(
            "ENCODING_DAMAGE",
            S.REVIEW,
            f"{damaged_count} libellé(s) contiennent des caractères de contrôle (accents probablement perdus). "
            "Affichés avec « � », sans correction automatique.",
            count=damaged_count,
            examples=damaged_examples,
        )
        for damaged_node in (n for n in nodes.values() if n.label_damaged):
            issues.add(
                "DAMAGED_LABEL",
                S.REVIEW,
                f"Libellé de {damaged_node.code_display} abîmé (caractère de contrôle).",
                record=damaged_node.source_record,
                node=damaged_node,
                code=damaged_node.code,
            )

    counts = {
        "rows": len(body),
        "records": len(records),
        "tariff_lines": len(nodes),
        "derived_parents": len(derived),
        "observations": dict(quality),
        "encoding": encoding,
        "delimiter": delimiter,
        "columns": header,
    }
    coverage = {"rows_without_node": len(body) - len(nodes)}
    finish_run(run, counts=counts, coverage=coverage, issues=issues)
    return edition
