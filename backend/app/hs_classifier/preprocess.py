import re
from typing import Iterable, List


def clean_text(text: str) -> str:
    """Basic cleaning: lower, remove non-word (keep spaces), collapse whitespace."""
    if not text:
        return ""
    text = text.lower()
    # remove punctuation except + and - which may appear in codes
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def prepare_corpus(texts: Iterable[str]) -> List[str]:
    return [clean_text(t) for t in texts]
