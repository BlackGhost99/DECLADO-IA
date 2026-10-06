import re
import unicodedata


def search_normalize(value: str) -> str:
    """Texte de recherche : minuscules sans accents ; caractères abîmés retirés."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c) and c != "�")
    return re.sub(r"\s+", " ", value.lower()).strip()
