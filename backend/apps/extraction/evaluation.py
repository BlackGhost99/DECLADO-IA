"""Évaluation des extracteurs sur un corpus annoté (DEV-019, puis DEV-031 sur pièces réelles).

Chaque pièce `<nom>.<ext>` est accompagnée de `<nom>.expected.json` (valeurs attendues ; `null`
quand le document ne permet pas de les connaître). Le rapport compte, par champ : exact, faux,
manqué, inconnu à raison et inventé (valeur produite alors qu'aucune n'était lisible). Un
résultat sur le corpus synthétique ne prouve rien sur des factures réelles.
"""

import json
from decimal import Decimal
from pathlib import Path

from apps.tariffs.codes import normalize_code

from . import adapters
from .schema import HEADER_FIELDS, LINE_FIELDS, jsonable

OUTCOMES = ("exact", "wrong", "missed", "unknown_ok", "invented")


def _norm(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    text = str(value).strip()
    try:
        return format(Decimal(text).normalize(), "f")
    except Exception:
        return text


def _outcome(expected, got) -> str:
    expected, got = _norm(expected), _norm(got)
    if expected is None:
        return "unknown_ok" if got is None else "invented"
    if got is None:
        return "missed"
    return "exact" if expected == got else "wrong"


def evaluate_file(path: Path, expected: dict) -> dict:
    doc = adapters.run(expected["mime"], path, ocr=expected.get("ocr", False), progress=lambda *a: None)
    fields: dict[str, dict] = {}

    def count(name, outcome):
        fields.setdefault(name, dict.fromkeys(OUTCOMES, 0))[outcome] += 1

    for name in HEADER_FIELDS:
        if name in expected.get("header", {}):
            count(f"facture.{name}", _outcome(expected["header"][name], jsonable(doc.header[name].parsed)))
    for i, exp_line in enumerate(expected.get("lines", [])):
        got = doc.lines[i] if i < len(doc.lines) else None
        for name in LINE_FIELDS:
            if name in exp_line:
                count(f"ligne.{name}", _outcome(exp_line[name], jsonable(got.fields[name].parsed) if got else None))
        if "customs_code" in exp_line:
            customs = [c.raw for c in (got.codes if got else []) if c.kind == "customs"]
            got_code = normalize_code(customs[0]) if customs else None
            count("ligne.code_douanier", _outcome(normalize_code(exp_line["customs_code"] or "") or None, got_code))
    return {
        "file": path.name,
        "expected_lines": len(expected.get("lines", [])),
        "extracted_lines": len(doc.lines),
        "warnings": [w["code"] for w in doc.warnings],
        "fields": fields,
    }


def evaluate_corpus(directory: Path) -> dict:
    results = []
    for expected_path in sorted(directory.glob("*.expected.json")):
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        document = directory / expected["file"]
        try:
            results.append(evaluate_file(document, expected))
        except adapters.ExtractionFailure as exc:
            results.append({"file": document.name, "failure": exc.code, "fields": {}})
    totals: dict[str, dict] = {}
    for result in results:
        for name, counts in result["fields"].items():
            bucket = totals.setdefault(name, dict.fromkeys(OUTCOMES, 0))
            for k, v in counts.items():
                bucket[k] += v
    invented = sum(c["invented"] for c in totals.values())
    return {"documents": results, "fields": totals, "invented_values": invented}


def markdown(report: dict) -> str:
    lines = ["| Champ | Exact | Faux | Manqué | Inconnu à raison | Inventé |", "|---|---|---|---|---|---|"]
    for name, c in sorted(report["fields"].items()):
        lines.append(f"| {name} | {c['exact']} | {c['wrong']} | {c['missed']} | {c['unknown_ok']} | {c['invented']} |")
    lines.append("")
    lines.append(f"Valeurs inventées (attendu inconnu, valeur produite) : {report['invented_values']}.")
    return "\n".join(lines)
