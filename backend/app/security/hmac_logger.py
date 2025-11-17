from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path

from app.core.config import settings


class HMACFileHandler(logging.Handler):
    """Append-only JSONL log with chained HMAC for tamper evidence.

    Each entry includes prev_hmac, and hmac = HMAC(key, prev_hmac || ts || level || name || msg || model_version || user).
    """

    def __init__(self, filename: str | os.PathLike, key: str | None = None) -> None:
        super().__init__()
        self.path = Path(filename)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.key = (key or settings.LOG_HMAC_KEY or settings.SECRET_KEY).encode("utf-8")
        self.prev_hmac = self._last_hmac()
        self.model_version = settings.APP_VERSION
        self.user = os.getenv("DECLADO_USER") or getpass.getuser()

    def _last_hmac(self) -> str:
        if not self.path.exists():
            return "GENESIS"
        try:
            with self.path.open("rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                # Read last ~4KB for final line
                f.seek(max(0, size - 4096))
                tail = f.read().decode("utf-8", errors="ignore")
            lines = [ln for ln in tail.splitlines() if ln.strip()]
            if not lines:
                return "GENESIS"
            last = json.loads(lines[-1])
            return last.get("hmac", "GENESIS")
        except Exception:
            return "GENESIS"

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            payload = {
                "ts": ts,
                "level": record.levelname,
                "name": record.name,
                "msg": self.format(record),
                "model_version": self.model_version,
                "user": self.user,
                "prev_hmac": self.prev_hmac,
            }
            mac = hmac.new(self.key, digestmod=hashlib.sha256)
            mac.update(payload["prev_hmac"].encode("utf-8"))
            mac.update(ts.encode("utf-8"))
            mac.update(record.levelname.encode("utf-8"))
            mac.update(record.name.encode("utf-8"))
            mac.update(str(payload["msg"]).encode("utf-8"))
            mac.update(self.model_version.encode("utf-8"))
            mac.update(self.user.encode("utf-8"))
            payload["hmac"] = mac.hexdigest()
            line = json.dumps(payload, ensure_ascii=False)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self.prev_hmac = payload["hmac"]
        except Exception:
            self.handleError(record)


def configure_hmac_logging() -> None:
    handler = HMACFileHandler(Path("./logs/declado-audit.log"))
    handler.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    # Minimal formatter - message is included in JSON payload; avoid duplicating metadata
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)


def verify_log_chain(path: str, key: str | None = None) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    key_bytes = (key or settings.LOG_HMAC_KEY or settings.SECRET_KEY).encode("utf-8")
    prev = "GENESIS"
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            obj = json.loads(ln)
            expected_mac = hmac.new(key_bytes, digestmod=hashlib.sha256)
            expected_mac.update(prev.encode("utf-8"))
            expected_mac.update(obj["ts"].encode("utf-8"))
            expected_mac.update(obj["level"].encode("utf-8"))
            expected_mac.update(obj["name"].encode("utf-8"))
            expected_mac.update(str(obj["msg"]).encode("utf-8"))
            expected_mac.update(str(obj.get("model_version", "")).encode("utf-8"))
            expected_mac.update(str(obj.get("user", "")).encode("utf-8"))
            if not hmac.compare_digest(expected_mac.hexdigest(), obj["hmac"]):
                return False
            prev = obj["hmac"]
        return True
    except Exception:
        return False
