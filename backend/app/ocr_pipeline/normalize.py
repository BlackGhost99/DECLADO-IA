from __future__ import annotations

import re
from datetime import datetime

DATE_PATTERNS = [
    r"\b(\d{2})[\./-](\d{2})[\./-](\d{4})\b",  # dd/mm/yyyy
    r"\b(\d{4})[\./-](\d{2})[\./-](\d{2})\b",  # yyyy-mm-dd
]

AMOUNT_PATTERN = r"(?<!\w)(\d{1,3}(?:[\s,]\d{3})*(?:[\.,]\d{2})?|\d+(?:[\.,]\d{2}))(?!\w)"
CURRENCY_PATTERN = r"\b(USD|EUR|XAF|XOF|FCFA|CFA)\b|[€$]"

CEMAC_CURRENCIES = {
    "XAF": "XAF",
    "FCFA": "XAF",
    "CFA": "XAF",
    "XOF": "XOF",
    "USD": "USD",
    "EUR": "EUR",
}


def normalize_date(text: str) -> list[str]:
    dates: list[str] = []
    for pat in DATE_PATTERNS:
        for m in re.finditer(pat, text):
            try:
                if len(m.groups()) == 3 and len(m.group(1)) == 2:  # dd/mm/yyyy
                    d, mth, y = m.group(1), m.group(2), m.group(3)
                    dt = datetime(int(y), int(mth), int(d))
                else:  # yyyy-mm-dd
                    y, mth, d = m.group(1), m.group(2), m.group(3)
                    dt = datetime(int(y), int(mth), int(d))
                dates.append(dt.date().isoformat())
            except Exception:
                continue
    return sorted(set(dates))


def _to_float(num_str: str) -> float | None:
    s = num_str.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def normalize_amounts(text: str) -> list[float]:
    amts: list[float] = []
    for m in re.finditer(AMOUNT_PATTERN, text):
        v = _to_float(m.group(1))
        if v is not None:
            amts.append(v)
    # keep unique while preserving order (rounded to cents)
    seen = set()
    uniq: list[float] = []
    for v in amts:
        key = round(v, 2)
        if key not in seen:
            seen.add(key)
            uniq.append(v)
    return uniq


def normalize_currencies(text: str) -> list[str]:
    currs: list[str] = []
    for m in re.finditer(CURRENCY_PATTERN, text, flags=re.IGNORECASE):
        val = m.group(0).upper()
        if val in ("€",):
            val = "EUR"
        if val in ("$"):
            val = "USD"
        currs.append(CEMAC_CURRENCIES.get(val, val))
    # unique order-preserving
    out: list[str] = []
    for c in currs:
        if c not in out:
            out.append(c)
    return out
