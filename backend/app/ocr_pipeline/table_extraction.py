from __future__ import annotations

from typing import Any

import numpy as np

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError(
            "OpenCV (cv2) n'est pas installé. Installez opencv-python pour la détection de tableaux."
        )


def detect_tables_by_lines(img: np.ndarray) -> list[dict[str, Any]]:
    """Very simple table detection by finding large rectangular contours.

    Returns a list of table dicts: {"bbox": [x,y,w,h], "rows": List[List[str]]}
    Rows are empty here (placeholder); downstream can populate via OCR/pdf parsing.
    """
    _require_cv2()
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    thr = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 10
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
    morphed = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    tables: list[dict[str, Any]] = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < 5000:
            continue
        aspect = w / max(1, h)
        if aspect < 2.0:  # prefer wide rectangles
            continue
        tables.append({"bbox": [int(x), int(y), int(w), int(h)], "rows": []})
    return tables
