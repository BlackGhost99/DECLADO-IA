"""Stockage privé des pièces (DOC-02).

Interface minimale derrière laquelle un adaptateur compatible S3 viendra se placer
(ADR-009). L'implémentation locale écrit hors de toute racine servie par le web, sous
une clé aléatoire non devinable ; seuls les contrôles applicatifs donnent accès aux octets.
"""

import hashlib
import os
import secrets
from pathlib import Path
from typing import BinaryIO, Protocol

from django.conf import settings


class StoredObject:
    def __init__(self, key: str, sha256: str, size: int):
        self.key, self.sha256, self.size = key, sha256, size


class PrivateStorage(Protocol):
    def put(self, fileobj: BinaryIO, *, prefix: str) -> StoredObject: ...

    def open(self, key: str) -> BinaryIO: ...

    def path_for_reading(self, key: str) -> Path: ...

    def discard(self, key: str) -> None: ...


class LocalPrivateStorage:
    """Fichiers sous PRIVATE_STORAGE_ROOT/documents/<préfixe>/<clé aléatoire>, mode 0600."""

    def __init__(self, root: Path):
        self.root = Path(root) / "documents"

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Clé de stockage invalide.")
        return path

    def put(self, fileobj: BinaryIO, *, prefix: str) -> StoredObject:
        key = f"{prefix}/{secrets.token_hex(16)}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        digest, size = hashlib.sha256(), 0
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            for chunk in iter(lambda: fileobj.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
        os.replace(tmp, path)
        return StoredObject(key, digest.hexdigest(), size)

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def path_for_reading(self, key: str) -> Path:
        return self._path(key)

    def discard(self, key: str) -> None:
        """Supprime un dépôt refusé avant tout enregistrement ; jamais un original accepté."""
        self._path(key).unlink(missing_ok=True)


def get_storage() -> PrivateStorage:
    return LocalPrivateStorage(settings.PRIVATE_STORAGE_ROOT)
