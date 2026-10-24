"""Contrôle du contenu réel d'un fichier (DOC-01, DOC-05).

Le type est déterminé par les octets, jamais par le nom ou l'en-tête envoyé par le
client : ceux-ci doivent seulement être cohérents avec le contenu. Aucun contenu n'est
exécuté ni interprété au-delà de ces vérifications de structure.
"""

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

PDF = "application/pdf"
PNG = "image/png"
JPEG = "image/jpeg"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TIFF = "image/tiff"

ACCEPTED = {
    PDF: (".pdf",),
    PNG: (".png",),
    JPEG: (".jpg", ".jpeg"),
    XLSX: (".xlsx",),
    TIFF: (".tif", ".tiff"),
}
LABELS = {PDF: "PDF", PNG: "PNG", JPEG: "JPEG", XLSX: "Excel (.xlsx)", TIFF: "TIFF"}
# Plafond de décompression pour inspecter un .xlsx sans risque d'archive piégée.
XLSX_MAX_UNCOMPRESSED = 300 * 1024 * 1024


class Readability:
    OK = "ok"
    PROTECTED = "protected"
    CORRUPTED = "corrupted"


READABILITY_LABELS = {
    Readability.OK: "Lisible",
    Readability.PROTECTED: "Protégé par mot de passe ou chiffré : aperçu impossible",
    Readability.CORRUPTED: "Fichier endommagé ou incomplet : aperçu impossible",
}


class Rejected(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}


@dataclass
class Sniffed:
    mime: str
    readability: str = Readability.OK
    notes: list[str] = field(default_factory=list)


def _detect(head: bytes) -> str | None:
    if head.startswith(b"%PDF-"):
        return PDF
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"PK\x03\x04"):
        return XLSX  # confirmé ou infirmé par l'examen de l'archive
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "ole"  # conteneur Office chiffré ou ancien format .xls
    return None


def sniff(path: Path, *, name: str, declared_mime: str = "", allow_tiff: bool = False) -> Sniffed:
    ext = Path(name).suffix.lower()
    expected = next((m for m, exts in ACCEPTED.items() if ext in exts), None)
    if expected == TIFF and not allow_tiff:
        raise Rejected(
            "UNSUPPORTED_TYPE",
            "Les fichiers TIFF se déposent dans un lot numérisé (« Lot du scanner »).",
            {"accepted": sorted(e for m, exts in ACCEPTED.items() if m != TIFF for e in exts)},
        )
    if expected is None:
        raise Rejected(
            "UNSUPPORTED_TYPE",
            f"Format « {ext or 'sans extension'} » non accepté. Formats acceptés : PDF, PNG, JPEG, XLSX.",
            {"accepted": sorted(e for m, exts in ACCEPTED.items() if m != TIFF or allow_tiff for e in exts)},
        )
    with path.open("rb") as fh:
        head = fh.read(16)
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - 4096))
        tail = fh.read()
    if size == 0:
        raise Rejected("EMPTY_FILE", "Le fichier est vide.")
    detected = _detect(head)

    if detected == "ole" and expected == XLSX:
        return Sniffed(XLSX, Readability.PROTECTED, ["Classeur chiffré (conteneur OLE) : mot de passe nécessaire."])
    if detected != expected:
        raise Rejected(
            "CONTENT_TYPE_MISMATCH",
            f"Le contenu ne correspond pas à l'extension « {ext} ».",
            {"extension": ext, "detected": LABELS.get(detected or "", "inconnu")},
        )
    declared = (declared_mime or "").split(";")[0].strip().lower()
    if (
        declared
        and declared not in ("application/octet-stream", expected)
        and not (expected == JPEG and declared == "image/jpg")
    ):
        raise Rejected(
            "DECLARED_TYPE_MISMATCH",
            "Le type déclaré par le navigateur ne correspond pas au contenu du fichier.",
            {"declared": declared, "detected": expected},
        )

    result = Sniffed(expected)
    if expected == PDF:
        with path.open("rb") as fh:
            data = fh.read()
        if b"%%EOF" not in tail:
            result.readability = Readability.CORRUPTED
            result.notes.append("Marqueur de fin %%EOF absent : PDF tronqué ou endommagé.")
        if b"/Encrypt" in data:
            result.readability = Readability.PROTECTED
            result.notes.append("PDF chiffré (/Encrypt).")
    elif expected == PNG and b"IEND" not in tail:
        result.readability = Readability.CORRUPTED
        result.notes.append("Bloc IEND absent : image tronquée.")
    elif expected == JPEG and b"\xff\xd9" not in tail:
        result.readability = Readability.CORRUPTED
        result.notes.append("Marqueur de fin JPEG absent : image tronquée.")
    elif expected == XLSX:
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                total = sum(i.file_size for i in archive.infolist())
        except zipfile.BadZipFile:
            result.readability = Readability.CORRUPTED
            result.notes.append("Archive .xlsx illisible.")
        else:
            if "xl/workbook.xml" not in names:
                raise Rejected(
                    "CONTENT_TYPE_MISMATCH",
                    "Archive ZIP qui n'est pas un classeur Excel.",
                    {"extension": ext, "detected": "ZIP"},
                )
            if total > XLSX_MAX_UNCOMPRESSED:
                result.readability = Readability.CORRUPTED
                result.notes.append("Contenu décompressé démesuré : aperçu désactivé par prudence.")
            if any(n.startswith("xl/externalLinks/") for n in names):
                result.notes.append("Liaisons externes présentes : conservées, jamais suivies.")
    return result
