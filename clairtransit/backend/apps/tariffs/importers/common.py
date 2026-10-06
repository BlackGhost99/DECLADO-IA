"""Outils partagés des importateurs : enregistrement de la source, anomalies, comptages."""

import hashlib
import re
import shutil
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from ..models import ImportIssue, ImportRun, SourceDocument

CONTROL_CHARS = {chr(c) for c in range(32) if chr(c) not in "\t\n\r"}
REPLACEMENT = "�"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_source(path: Path, *, kind: str, title: str, is_derived_copy: bool, actor=None, **meta) -> SourceDocument:
    """Copie l'original dans le stockage privé (sans le modifier) et l'identifie par son empreinte.

    Un fichier identique déjà enregistré est réutilisé : une nouvelle importation crée un
    nouveau ImportRun, l'ancien reste consultable.
    """
    path = Path(path)
    digest = sha256_file(path)
    existing = SourceDocument.objects.filter(sha256=digest).first()
    if existing:
        return existing
    target_dir = Path(settings.PRIVATE_STORAGE_ROOT) / "sources"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / digest
    if not target.exists():
        shutil.copyfile(path, target)
    return SourceDocument.objects.create(
        title=title,
        original_name=path.name,
        kind=kind,
        is_derived_copy=is_derived_copy,
        sha256=digest,
        bytes=path.stat().st_size,
        storage_path=str(target.relative_to(settings.PRIVATE_STORAGE_ROOT)),
        uploaded_by=actor,
        **meta,
    )


def source_path(source: SourceDocument) -> Path:
    return Path(settings.PRIVATE_STORAGE_ROOT) / source.storage_path


OOXML_ESCAPE = re.compile(r"_x([0-9A-Fa-f]{4})_")


def clean_label(raw: str) -> tuple[str, bool]:
    """Libellé affichable : espaces normalisés, caractères de contrôle signalés (non devinés).

    Les échappements OOXML (« _x0002_ ») sont décodés avant contrôle : Excel les utilise pour
    stocker des caractères de contrôle.
    """
    raw = OOXML_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), raw)
    damaged = any(c in CONTROL_CHARS for c in raw)
    text = "".join(REPLACEMENT if c in CONTROL_CHARS else c for c in raw)
    return " ".join(text.split()), damaged


class IssueCollector:
    def __init__(self, run: ImportRun):
        self.run = run
        self.pending: list[ImportIssue] = []
        self.counter: Counter[str] = Counter()

    def add(self, category, severity, message, *, record=None, node=None, **details):
        self.counter[category] += 1
        self.pending.append(
            ImportIssue(
                run=self.run,
                record=record,
                node=node,
                category=category,
                severity=severity,
                message=message[:500],
                details=details,
            )
        )

    def flush(self):
        ImportIssue.objects.bulk_create(self.pending, batch_size=1000)
        self.pending = []


def finish_run(run: ImportRun, *, counts: dict, coverage: dict, issues: IssueCollector) -> ImportRun:
    issues.flush()
    run.counts = {**counts, "issues": dict(issues.counter)}
    run.coverage = coverage
    run.status = ImportRun.Status.COMPLETED_WITH_ISSUES if issues.counter else ImportRun.Status.COMPLETED
    run.finished_at = timezone.now()
    run.save()
    return run
