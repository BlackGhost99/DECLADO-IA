"""Untrusted uploads are staged under a separate private directory, never a document key."""

import hashlib
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from apps.core.exceptions import ApiError


@dataclass(frozen=True)
class Quarantined:
    path: Path
    size: int
    sha256: str


def stage(upload, max_bytes: int, on_chunk: Callable[[bytes], None] | None = None) -> Quarantined:
    """Copy an upload into quarantine; on_chunk sees each chunk before it touches the disk."""
    root = Path(settings.PRIVATE_STORAGE_ROOT) / "quarantine"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / secrets.token_hex(24)
    size, digest = 0, hashlib.sha256()
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as destination:
            while chunk := upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise ApiError(
                        "FILE_TOO_LARGE",
                        "Fichier trop volumineux.",
                        413,
                        {"max_bytes": max_bytes},
                    )
                digest.update(chunk)
                if on_chunk:
                    on_chunk(chunk)
                destination.write(chunk)
        return Quarantined(path, size, digest.hexdigest())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
