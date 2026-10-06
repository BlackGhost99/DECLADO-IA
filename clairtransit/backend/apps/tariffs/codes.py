"""Normalisation des codes tarifaires : séparateurs retirés, zéros conservés, aucune réparation."""

import re

_ALLOWED_SEPARATORS = re.compile(r"[.\s\-]")
_DIGITS = re.compile(r"^\d+$")


def normalize_code(raw: str | None) -> str | None:
    """Retourne les chiffres du code, ou None s'il contient autre chose que chiffres et séparateurs.

    Ne complète jamais par des zéros et ne corrige aucun chiffre.
    """
    if raw is None:
        return None
    stripped = _ALLOWED_SEPARATORS.sub("", raw.strip())
    if not stripped or not _DIGITS.match(stripped):
        return None
    return stripped


def looks_like_code_query(q: str) -> bool:
    return bool(q) and normalize_code(q) is not None


def hierarchy_prefixes(code: str) -> list[tuple[str, str]]:
    """Ancêtres SH implicites d'un code (chapitre 2, position 4, sous-position 6)."""
    levels = [(2, "chapter"), (4, "heading"), (6, "subheading")]
    return [(code[:n], kind) for n, kind in levels if len(code) > n]
