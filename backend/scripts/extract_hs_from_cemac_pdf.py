"""
Extraction des codes HS et descriptions depuis le PDF du Tarif des Douanes CEMAC.

Entrée: chemin du PDF
Sortie: CSV backend/data/hs_cemac.csv avec colonnes: text,hs_code

Notes:
- On détecte les codes au début de ligne: 4 chiffres (position), 6 chiffres, ou format 12.34.56
- On normalise les codes en 4 chiffres (en prenant les 4 premiers)
- On concatène les lignes suivantes comme description jusqu'au prochain code
- L'extraction texte PDF peut être bruitée (colonnes); ce script crée un dataset initial à affiner
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import pdfplumber

# Assurer que le dossier backend est dans le PYTHONPATH pour importer 'app.*' depuis scripts/
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

try:
    # Utiliser les helpers existants pour trouver Poppler et convertir les pages
    from app.ocr_pipeline.pdf_utils import iter_pdf_pages_as_images  # type: ignore
except Exception:
    iter_pdf_pages_as_images = None  # type: ignore

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

# pdfminer.six (fallback texte pur)
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text  # type: ignore
except Exception:  # pragma: no cover
    pdfminer_extract_text = None  # type: ignore

# PIL helpers pour un pré-traitement OCR simple
try:
    from PIL import ImageFilter, ImageOps  # type: ignore
except Exception:  # pragma: no cover
    ImageOps = None  # type: ignore
    ImageFilter = None  # type: ignore

# Regex pour codes en début de ligne
RE_CODE = re.compile(r"^\s*(?P<raw>(\d{2}\.\d{2}\.\d{2}|\d{6}|\d{4}))\b[\s\-:]*", re.UNICODE)
# Recherche non ancrée (utilisée côté OCR)
RE_CODE_ANY = re.compile(r"(?P<raw>(\d{2}\.\d{2}\.\d{2}|\d{6}|\b\d{4}\b))", re.UNICODE)


def normalize_code(raw: str) -> str | None:
    raw2 = raw.replace(".", "").replace(" ", "")
    if not raw2.isdigit():
        return None
    if len(raw2) >= 4:
        return raw2[:4]
    return None


def iter_lines(pdf_path: Path):
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            try:
                text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            except Exception:
                text = page.extract_text() or ""
            for line in text.splitlines():
                yield line.strip()


def extract_pairs(pdf_path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    cur_code: str | None = None
    cur_desc_parts: list[str] = []

    def flush():
        nonlocal cur_code, cur_desc_parts
        if cur_code and cur_desc_parts:
            desc = " ".join(p.strip("-• ") for p in cur_desc_parts)
            # Nettoyage description
            desc = re.sub(r"\s+", " ", desc).strip()
            if len(desc) >= 5:
                rows.append((desc, cur_code))
        cur_code = None
        cur_desc_parts = []

    for line in iter_lines(pdf_path):
        m = RE_CODE.match(line)
        if m:
            # Nouvelle entrée
            raw = m.group("raw")
            code4 = normalize_code(raw)
            rest = line[m.end() :].strip()
            if code4:
                flush()
                cur_code = code4
                if rest:
                    cur_desc_parts.append(rest)
            else:
                # ligne non exploitable, on l'ajoute à la desc si on est dans une entrée
                if cur_code:
                    cur_desc_parts.append(line)
        else:
            # continuation de description
            if cur_code:
                cur_desc_parts.append(line)

    flush()
    return rows


def extract_pairs_ocr(pdf_path: Path, max_pages: int | None = 20) -> list[tuple[str, str]]:
    """Fallback OCR: rasterise les pages et utilise Tesseract pour extraire le texte.

    max_pages: limite le nombre de pages à traiter (pour un premier dataset). Mettre None pour tout le PDF.
    """
    if pytesseract is None or iter_pdf_pages_as_images is None:
        return []

    rows: list[tuple[str, str]] = []
    cur_code: str | None = None
    cur_desc_parts: list[str] = []

    def flush():
        nonlocal cur_code, cur_desc_parts
        if cur_code and cur_desc_parts:
            desc = " ".join(p.strip("-• ") for p in cur_desc_parts)
            desc = re.sub(r"\s+", " ", desc).strip()
            if len(desc) >= 5:
                rows.append((desc, cur_code))
        cur_code = None
        cur_desc_parts = []

    def _preprocess(img):
        # Convertit en niveaux de gris, améliore le contraste et applique un seuillage léger
        try:
            if ImageOps is None:
                return img
            g = img.convert("L")
            g = ImageOps.autocontrast(g)
            if ImageFilter is not None:
                g = g.filter(ImageFilter.MedianFilter(size=3))
            # Seuil simple
            g = g.point(lambda x: 255 if x > 180 else 0)
            return g
        except Exception:
            return img

    try:
        count = 0
        for _idx, img in iter_pdf_pages_as_images(str(pdf_path), dpi=300):
            pimg = _preprocess(img)
            text = pytesseract.image_to_string(pimg, lang="fra+eng") or ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Chercher un code où qu'il soit dans la ligne (plus permissif)
                m = RE_CODE_ANY.search(line)
                if m:
                    raw = m.group("raw")
                    code4 = normalize_code(raw)
                    # Enlever le code trouvé de la ligne pour ne garder que la description
                    rest = (line[: m.start()] + " " + line[m.end() :]).strip()
                    if code4:
                        flush()
                        cur_code = code4
                        if rest:
                            cur_desc_parts.append(rest)
                else:
                    if cur_code:
                        cur_desc_parts.append(line)

            count += 1
            if max_pages is not None and count >= max_pages:
                break

        flush()
    except Exception:
        # Retourne ce qui a pu être récupéré
        pass

    return rows


def write_csv(rows: list[tuple[str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["text", "hs_code"])
        for text, code in rows:
            w.writerow([text, code])


def extract_pairs_pymupdf(pdf_path: Path) -> list[tuple[str, str]]:
    """Fallback extraction using PyMuPDF text blocks."""
    if fitz is None:
        return []
    rows: list[tuple[str, str]] = []
    cur_code: str | None = None
    cur_desc_parts: list[str] = []

    def flush():
        nonlocal cur_code, cur_desc_parts
        if cur_code and cur_desc_parts:
            desc = " ".join(p.strip("-• ") for p in cur_desc_parts)
            desc = re.sub(r"\s+", " ", desc).strip()
            if len(desc) >= 5:
                rows.append((desc, cur_code))
        cur_code = None
        cur_desc_parts = []

    try:
        doc = fitz.open(str(pdf_path))
        for page in doc:
            text = page.get_text("text") or ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                m = RE_CODE.match(line)
                if m:
                    raw = m.group("raw")
                    code4 = normalize_code(raw)
                    rest = line[m.end() :].strip()
                    if code4:
                        flush()
                        cur_code = code4
                        if rest:
                            cur_desc_parts.append(rest)
                else:
                    if cur_code:
                        cur_desc_parts.append(line)
        flush()
    except Exception:
        pass
    return rows


def extract_pairs_pdfminer(pdf_path: Path) -> list[tuple[str, str]]:
    """Fallback extraction using pdfminer.six (texte brut)."""
    if pdfminer_extract_text is None:
        return []

    rows: list[tuple[str, str]] = []
    cur_code: str | None = None
    cur_desc_parts: list[str] = []

    def flush():
        nonlocal cur_code, cur_desc_parts
        if cur_code and cur_desc_parts:
            desc = " ".join(p.strip("-• ") for p in cur_desc_parts)
            desc = re.sub(r"\s+", " ", desc).strip()
            if len(desc) >= 5:
                rows.append((desc, cur_code))
        cur_code = None
        cur_desc_parts = []

    try:
        text = pdfminer_extract_text(str(pdf_path)) or ""
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = RE_CODE.match(line)
            if m:
                raw = m.group("raw")
                code4 = normalize_code(raw)
                rest = line[m.end() :].strip()
                if code4:
                    flush()
                    cur_code = code4
                    if rest:
                        cur_desc_parts.append(rest)
            else:
                if cur_code:
                    cur_desc_parts.append(line)
        flush()
    except Exception:
        pass

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract HS pairs from CEMAC PDF")
    parser.add_argument(
        "--pdf",
        type=str,
        default=str(
            Path(__file__).parents[2]
            / "datasets"
            / "tarif-des-douanes-de-la-cemac-version-originale-pdf-210608020644.pdf"
        ),
        help="Chemin du PDF CEMAC",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path(__file__).parents[1] / "data" / "hs_cemac.csv"),
        help="Chemin du CSV de sortie",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_path = Path(args.out)

    if not pdf_path.exists():
        print(f"❌ PDF introuvable: {pdf_path}")
        return 1

    print("📄 Extraction depuis:", pdf_path)
    pairs = extract_pairs(pdf_path)
    print(f"➡️  Paires extraites (pdfplumber): {len(pairs)}")

    if len(pairs) < 50:
        print("⚠️  Peu de paires extraites — tentative pdfminer...")
        pm_pairs = extract_pairs_pdfminer(pdf_path)
        print(f"➡️  Paires extraites (pdfminer): {len(pm_pairs)}")
        if len(pm_pairs) > len(pairs):
            pairs = pm_pairs

    if len(pairs) < 50:
        print("⚠️  Peu de paires extraites — tentative PyMuPDF...")
        mu_pairs = extract_pairs_pymupdf(pdf_path)
        print(f"➡️  Paires extraites (PyMuPDF): {len(mu_pairs)}")
        if len(mu_pairs) > len(pairs):
            pairs = mu_pairs

    if len(pairs) < 50:
        print("⚠️  Peu de paires extraites — tentative OCR de secours (jusqu'à 20 pages)...")
        ocr_pairs = extract_pairs_ocr(pdf_path, max_pages=20)
        print(f"➡️  Paires extraites (OCR): {len(ocr_pairs)}")
        if len(ocr_pairs) > len(pairs):
            pairs = ocr_pairs

    write_csv(pairs, out_path)
    print("✅ CSV écrit:", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
