from __future__ import annotations

import logging
import os

import numpy as np
import pytesseract

from .types import BBox, Word

# Configuration Windows: détecter automatiquement Tesseract
# Chemins courants d'installation sur Windows
TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\Public\Tesseract-OCR\tesseract.exe",
]

logger = logging.getLogger(__name__)

# Tesseract parallélise par OpenMP ; sur une petite page, l'attente active des fils
# coûte plus qu'elle ne rapporte (lenteur constatée sur Windows). Réglable par l'environnement.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

for tess_path in TESSERACT_PATHS:
    if os.path.exists(tess_path):
        pytesseract.pytesseract.tesseract_cmd = tess_path
        # Try to set TESSDATA_PREFIX automatically (sibling tessdata folder)
        tessdata = os.path.join(os.path.dirname(tess_path), "tessdata")
        if os.path.exists(tessdata):
            os.environ.setdefault("TESSDATA_PREFIX", tessdata)
        logger.info(f"Tesseract detected at: {tess_path}")
        if os.environ.get("TESSDATA_PREFIX"):
            logger.info(f"TESSDATA_PREFIX={os.environ['TESSDATA_PREFIX']}")
        break


def _parse_tesseract_data(data: str) -> tuple[str, list[Word]]:
    lines = data.strip().splitlines()
    if not lines:
        return "", []
    header = lines[0].split("\t")
    idx_map = {name: i for i, name in enumerate(header)}
    words: list[Word] = []
    texts: list[str] = []
    for ln in lines[1:]:
        parts = ln.split("\t")
        if len(parts) != len(header):
            continue
        text = parts[idx_map.get("text", -1)].strip()
        if not text:
            continue
        try:
            x = int(float(parts[idx_map["left"]]))
            y = int(float(parts[idx_map["top"]]))
            w = int(float(parts[idx_map["width"]]))
            h = int(float(parts[idx_map["height"]]))
            conf = float(parts[idx_map["conf"]]) if parts[idx_map["conf"]] != "-1" else None
        except Exception:
            x = y = w = h = 0
            conf = None
        words.append(Word(text=text, bbox=BBox(x, y, w, h), conf=conf))
        texts.append(text)
    return " ".join(texts), words


def ocr_image(img: np.ndarray, lang: str = "eng+fra") -> tuple[str, list[Word]]:
    """Effectue l'OCR sur une image. Retourne le texte et les mots avec leurs positions."""
    try:
        config = "--oem 1 --psm 6"
        data = pytesseract.image_to_data(
            img, lang=lang, config=config, output_type=pytesseract.Output.STRING
        )
        return _parse_tesseract_data(data)
    except pytesseract.TesseractNotFoundError:
        # Tesseract n'est pas installé - retourner un message d'erreur explicite
        error_msg = (
            "Tesseract OCR n'est pas installé. "
            "Téléchargez-le depuis: https://github.com/UB-Mannheim/tesseract/wiki "
            "Puis installez-le dans C:\\Program Files\\Tesseract-OCR\\"
        )
        return error_msg, []
    except Exception as e:
        # Autre erreur Tesseract
        return f"Erreur OCR: {str(e)}", []
