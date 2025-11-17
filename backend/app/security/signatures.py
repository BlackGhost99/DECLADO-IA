from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Iterable
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def _iter_files(base: Path) -> Iterable[Path]:
    for p in sorted(base.rglob("*")):
        if p.is_file():
            # exclude signature files
            if p.name.endswith(".sig"):
                continue
            yield p


def compute_dir_digest(base: Path) -> str:
    sha = hashlib.sha256()
    base = base.resolve()
    for p in _iter_files(base):
        rel = p.relative_to(base).as_posix().encode("utf-8")
        sha.update(rel)
        data = p.read_bytes()
        sha.update(data)
    return sha.hexdigest()


def verify_signature(base: Path) -> bool:
    sig_file = base.with_suffix(base.suffix + ".sig") if base.is_file() else (base / ".sig")
    if not sig_file.exists():
        logger.info(f"No signature file for {base}")
        return True
    try:
        obj = json.loads(sig_file.read_text(encoding="utf-8"))
        algo = obj.get("algo", "HMAC-SHA256")
        digest_hex = obj["digest"]
        sig_hex = obj["hmac"]
    except Exception as e:
        logger.error(f"Invalid signature file {sig_file}: {e}")
        return False
    if algo != "HMAC-SHA256":
        logger.error(f"Unsupported signature algo: {algo}")
        return False
    key = (settings.LOG_HMAC_KEY or settings.SECRET_KEY).encode("utf-8")
    # Compute digest of directory or file
    if base.is_dir():
        digest = compute_dir_digest(base)
    else:
        sha = hashlib.sha256()
        sha.update(base.read_bytes())
        digest = sha.hexdigest()
    if digest != digest_hex:
        logger.error(f"Digest mismatch for {base}")
        return False
    mac = hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, sig_hex):
        logger.error(f"HMAC verification failed for {base}")
        return False
    logger.info(f"Signature OK for {base}")
    return True
