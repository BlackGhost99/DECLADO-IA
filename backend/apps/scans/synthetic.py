"""Lots numérisés fictifs pour les tests et la démonstration (aucun document client)."""

import io

from apps.extraction.synthetic import pdf_from_pages


def page(title: str = "", *lines: str, top: float = 60) -> list[tuple[float, float, str]]:
    """Une page : un titre en haut, puis des lignes de texte."""
    items = [(50, top, title)] if title else []
    items += [(50, top + 30 + 18 * i, text) for i, text in enumerate(lines)]
    return items


def text_pdf(pages: list[list[tuple[float, float, str]]], *, size: int = 14) -> bytes:
    return pdf_from_pages(pages, size=size)


def images_of(pdf: bytes, *, dpi: int = 200, rotate: dict[int, int] | None = None) -> list:
    """Rendu de chaque page (scan simulé) ; rotate = {numéro de page: degrés} pour une feuille mal posée."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf)
    try:
        images = [doc[i].render(scale=dpi / 72).to_pil().convert("L") for i in range(len(doc))]
    finally:
        doc.close()
    for number, degrees in (rotate or {}).items():
        images[number - 1] = images[number - 1].rotate(degrees, expand=True, fillcolor=255)
    return images


def scanned_pdf(pdf: bytes, *, dpi: int = 200, rotate: dict[int, int] | None = None) -> bytes:
    """PDF multipage sans couche texte, comme la sortie d'un scanner à chargeur."""
    images = images_of(pdf, dpi=dpi, rotate=rotate)
    out = io.BytesIO()
    images[0].save(out, "PDF", save_all=True, append_images=images[1:], resolution=dpi)
    return out.getvalue()


def tiff(pdf: bytes, *, dpi: int = 150) -> bytes:
    images = images_of(pdf, dpi=dpi)
    out = io.BytesIO()
    images[0].save(out, "TIFF", save_all=True, append_images=images[1:], compression="tiff_deflate")
    return out.getvalue()


def photo(pdf: bytes, *, dpi: int = 120, background: int = 70) -> bytes:
    """Photo d'une feuille posée sur une table sombre (JPEG), pour le recadrage."""
    from PIL import Image

    sheet = images_of(pdf, dpi=dpi)[0].convert("RGB")
    canvas = Image.new("RGB", (int(sheet.width * 1.4), int(sheet.height * 1.3)), (background,) * 3)
    canvas.paste(sheet, ((canvas.width - sheet.width) // 2, (canvas.height - sheet.height) // 2))
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=90)
    return out.getvalue()


def demo_batch() -> bytes:
    """Lot fictif : facture de deux pages, page blanche, connaissement, colisage, page sans titre."""
    return text_pdf(
        [
            page("FACTURE N° FE-2026-0417", "Fournisseur : Fictive Energie GmbH", "Page 1/2"),
            page("FACTURE N° FE-2026-0417", "Suite des lignes", "Page 2/2"),
            [],
            page("CONNAISSEMENT (BILL OF LADING)", "B/L N° FIC-2026-0456", "Navire : MV Fictif"),
            page("LISTE DE COLISAGE", "Référence facture : FE-2026-0417", "5 caisses 9 500 kg"),
            page("", "Annexe sans titre", "Observations diverses du transitaire"),
        ]
    )
