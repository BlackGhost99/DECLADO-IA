"""Lecture des nombres, dates, devises et pays tels qu'imprimés.

Règles : aucun nombre n'est inventé ; un séparateur ambigu (« 1,500 ») n'est tranché que par
le reste du document et la valeur est alors étiquetée « déduite » ; sinon elle reste inconnue.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from .schema import Origin, Status

COMMA, DOT = ",", "."
_SPACES = "    '’"
_NUMBER = re.compile(r"^\(?[-−+]?\d[\d" + re.escape(_SPACES) + r".,]*\)?-?$")
_CURRENCY_NOISE = re.compile(r"(€|\$|£|¥|FCFA|F\s?CFA|XAF|EUR|USD|CNY|GBP|JPY)", re.IGNORECASE)


@dataclass
class Reading:
    value: object
    status: str = Status.OK
    origin: str = Origin.READ
    note: str = ""


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def norm(text: str) -> str:
    """Forme de comparaison : minuscules, sans accents, espaces simples."""
    return re.sub(r"\s+", " ", strip_accents(text or "").lower()).strip()


def looks_numeric(text: str) -> bool:
    cleaned = _CURRENCY_NOISE.sub("", text or "").strip()
    return bool(cleaned) and bool(_NUMBER.match(cleaned))


def decimal_style(token: str) -> str | None:
    """Séparateur décimal certain d'un nombre isolé, ou None si le nombre n'en dit rien."""
    t = _CURRENCY_NOISE.sub("", token).strip().strip("()-−+")
    for ch in _SPACES:
        t = t.replace(ch, "")
    if "," in t and "." in t:
        return COMMA if t.rfind(",") > t.rfind(".") else DOT
    for sep in (COMMA, DOT):
        if t.count(sep) == 1:
            decimals = len(t.split(sep)[1])
            if decimals in (1, 2):
                return sep
    return None


def document_decimal_hint(tokens) -> str | None:
    """Séparateur décimal du document si tous les nombres sans ambiguïté s'accordent."""
    styles = {s for s in (decimal_style(t) for t in tokens if looks_numeric(t)) if s}
    return styles.pop() if len(styles) == 1 else None


def parse_amount(text: str | None, hint: str | None = None) -> Reading:
    if text is None or not text.strip():
        return Reading(None, Status.MISSING)
    raw = text.strip()
    t = _CURRENCY_NOISE.sub("", raw).strip()
    if not t or not _NUMBER.match(t):
        return Reading(None, Status.UNREADABLE, note=f"« {raw} » n'est pas un nombre lisible.")
    negative = t.startswith(("-", "−", "(")) or t.endswith("-")
    t = t.strip("()-−+")
    for ch in _SPACES:
        t = t.replace(ch, "")
    origin, note = Origin.READ, ""
    if "," in t and "." in t:
        decimal = COMMA if t.rfind(",") > t.rfind(".") else DOT
    elif t.count(",") > 1 or t.count(".") > 1:
        decimal = None  # 1.234.567 ou 1,234,567 : séparateurs de milliers seulement
        sep = "," if "," in t else "."
        if not all(len(g) == 3 for g in t.split(sep)[1:]):
            return Reading(None, Status.UNREADABLE, note=f"Groupement de chiffres incohérent dans « {raw} ».")
        t = t.replace(sep, "")
    elif "," in t or "." in t:
        sep = "," if "," in t else "."
        decimals = len(t.split(sep)[1])
        if decimals == 3:
            if hint is None:
                return Reading(
                    None,
                    Status.AMBIGUOUS,
                    note=f"« {raw} » : séparateur de milliers ou décimal ? Le document ne permet pas de trancher.",
                )
            decimal = sep if hint == sep else None
            origin, note = Origin.INFERRED, "Séparateur interprété d'après les autres nombres du document."
            if decimal is None:
                t = t.replace(sep, "")
        else:
            decimal = sep
    else:
        decimal = None
    if decimal:
        thousands = DOT if decimal == COMMA else COMMA
        t = t.replace(thousands, "").replace(decimal, ".")
    try:
        value = Decimal(t)
    except InvalidOperation:
        return Reading(None, Status.UNREADABLE, note=f"« {raw} » n'est pas un nombre lisible.")
    return Reading(-value if negative else value, Status.OK, origin, note)


_DATE_DMY = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})$")
_DATE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "january": 1, "february": 2,
    "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}  # fmt: skip
_DATE_WORDS = re.compile(r"^(\d{1,2})\s+([a-z]+)\s+(\d{4})$")


def parse_date(text: str | None, *, english: bool = False) -> Reading:
    """Jour/mois/année par défaut (usage francophone) ; un document en anglais rend 03/04 ambigu."""
    if text is None or not text.strip():
        return Reading(None, Status.MISSING)
    raw = text.strip()
    try:
        if m := _DATE_ISO.match(raw):
            return Reading(date(int(m[1]), int(m[2]), int(m[3])))
        if m := _DATE_DMY.match(raw):
            day, month, year = int(m[1]), int(m[2]), int(m[3])
            if year < 100:
                return Reading(None, Status.AMBIGUOUS, note=f"Année sur deux chiffres dans « {raw} ».")
            if english and day <= 12 and month <= 12 and day != month:
                return Reading(
                    None, Status.AMBIGUOUS, note=f"« {raw} » : jour/mois ou mois/jour ? Facture rédigée en anglais."
                )
            return Reading(date(year, month, day))
        if m := _DATE_WORDS.match(norm(raw)):
            month = _MONTHS.get(m[2])
            if month:
                return Reading(date(int(m[3]), month, int(m[1])))
    except ValueError:
        return Reading(None, Status.UNREADABLE, note=f"Date impossible : « {raw} ».")
    return Reading(None, Status.UNREADABLE, note=f"Date illisible : « {raw} ».")


ISO_CURRENCIES = {"XAF", "XOF", "EUR", "USD", "CNY", "GBP", "JPY", "CHF", "CAD", "AED", "INR", "TRY", "ZAR", "NGN"}
_CURRENCY_SIGNS = {
    "€": "EUR",
    "£": "GBP",
    "fcfa": "XAF",
    "f cfa": "XAF",
    "franc cfa": "XAF",
    "euro": "EUR",
    "euros": "EUR",
}


def parse_currency(text: str | None) -> Reading:
    if text is None or not text.strip():
        return Reading(None, Status.MISSING)
    raw = text.strip()
    up = raw.upper().strip(" .:()")
    if up in ISO_CURRENCIES:
        return Reading(up)
    key = norm(raw).strip(" .:()")
    if key in _CURRENCY_SIGNS:
        return Reading(_CURRENCY_SIGNS[key], origin=Origin.INFERRED, note=f"Devise déduite de « {raw} ».")
    if key in ("$", "dollar", "dollars"):
        return Reading(None, Status.AMBIGUOUS, note="« $ » ne précise pas le dollar (USD, CAD…).")
    return Reading(None, Status.UNREADABLE, note=f"Devise non reconnue : « {raw} ».")


# Noms usuels → ISO 3166-1 alpha-2 ; une correspondance est une déduction à vérifier.
_COUNTRIES = {
    "france": "FR", "chine": "CN", "china": "CN", "allemagne": "DE", "germany": "DE", "italie": "IT",
    "italy": "IT", "espagne": "ES", "spain": "ES", "belgique": "BE", "belgium": "BE", "pays-bas": "NL",
    "netherlands": "NL", "royaume-uni": "GB", "united kingdom": "GB", "etats-unis": "US", "usa": "US",
    "united states": "US", "japon": "JP", "japan": "JP", "inde": "IN", "india": "IN", "turquie": "TR",
    "turkey": "TR", "cameroun": "CM", "cameroon": "CM", "gabon": "GA", "congo": "CG", "nigeria": "NG",
    "afrique du sud": "ZA", "south africa": "ZA", "maroc": "MA", "morocco": "MA", "bresil": "BR",
    "brazil": "BR", "coree du sud": "KR", "south korea": "KR", "portugal": "PT", "suisse": "CH",
}  # fmt: skip


def parse_country(text: str | None) -> Reading:
    if text is None or not text.strip():
        return Reading(None, Status.MISSING)
    raw = text.strip()
    if re.fullmatch(r"[A-Za-z]{2}", raw):
        return Reading(raw.upper())
    code = _COUNTRIES.get(norm(raw).removeprefix("made in ").strip())
    if code:
        return Reading(code, origin=Origin.INFERRED, note=f"Pays « {raw} » converti en code {code}.")
    return Reading(None, Status.UNREADABLE, note=f"Pays non reconnu : « {raw} ».")


def split_quantity_unit(text: str) -> tuple[str, str]:
    """« 12 kg » → (« 12 », « kg ») ; l'unité n'est séparée que si elle suit un nombre."""
    m = re.match(r"^\s*([\d" + re.escape(_SPACES) + r".,]+)\s*([A-Za-zµ²³]{1,8}\.?)\s*$", text or "")
    return (m[1].strip(), m[2]) if m else (text, "")
