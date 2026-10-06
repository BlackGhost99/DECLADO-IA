from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BBox:
    x: int
    y: int
    w: int
    h: int

    def to_list(self) -> list[int]:
        return [self.x, self.y, self.w, self.h]


@dataclass
class Word:
    text: str
    bbox: BBox | None = None
    conf: float | None = None


@dataclass
class PageResult:
    page_index: int
    width: int
    height: int
    text: str
    words: list[Word] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)  # rows: List[List[str]], bbox

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_index": self.page_index,
            "width": self.width,
            "height": self.height,
            "text": self.text,
            "words": [
                {"text": w.text, "bbox": (w.bbox.to_list() if w.bbox else None), "conf": w.conf}
                for w in self.words
            ],
            "tables": self.tables,
        }


@dataclass
class NormalizedFields:
    dates: list[str] = field(default_factory=list)  # ISO yyyy-mm-dd
    amounts: list[float] = field(default_factory=list)
    currencies: list[str] = field(default_factory=list)  # ISO codes
    vendor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentResult:
    source: str
    num_pages: int
    pages: list[PageResult]
    normalized: NormalizedFields
    cer: float | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "num_pages": self.num_pages,
            "pages": [p.to_dict() for p in self.pages],
            "normalized": self.normalized.to_dict(),
            "cer": self.cer,
            "warnings": self.warnings,
        }
