from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class BBox:
    x: int
    y: int
    w: int
    h: int

    def to_list(self) -> List[int]:
        return [self.x, self.y, self.w, self.h]


@dataclass
class Word:
    text: str
    bbox: Optional[BBox] = None
    conf: Optional[float] = None


@dataclass
class PageResult:
    page_index: int
    width: int
    height: int
    text: str
    words: List[Word] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)  # rows: List[List[str]], bbox

    def to_dict(self) -> Dict[str, Any]:
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
    dates: List[str] = field(default_factory=list)  # ISO yyyy-mm-dd
    amounts: List[float] = field(default_factory=list)
    currencies: List[str] = field(default_factory=list)  # ISO codes
    vendor: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentResult:
    source: str
    num_pages: int
    pages: List[PageResult]
    normalized: NormalizedFields
    cer: Optional[float] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "num_pages": self.num_pages,
            "pages": [p.to_dict() for p in self.pages],
            "normalized": self.normalized.to_dict(),
            "cer": self.cer,
            "warnings": self.warnings,
        }
