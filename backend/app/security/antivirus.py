from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def _which(exe: str) -> Path | None:
    p = shutil.which(exe)
    return Path(p) if p else None


def detect_defender() -> Path | None:
    # Explicit setting overrides
    if settings.AV_DEFENDER_PATH and settings.AV_DEFENDER_PATH.exists():
        return settings.AV_DEFENDER_PATH
    # Try PATH
    p = _which("MpCmdRun.exe")
    if p:
        return p
    # Common Windows Defender platform path
    base = Path("C:/ProgramData/Microsoft/Windows Defender/Platform")
    if base.exists():
        versions = sorted([d for d in base.iterdir() if d.is_dir()], reverse=True)
        for v in versions:
            cand = v / "MpCmdRun.exe"
            if cand.exists():
                return cand
    return None


def detect_clamav() -> Path | None:
    if settings.AV_CLAMSCAN_PATH and settings.AV_CLAMSCAN_PATH.exists():
        return settings.AV_CLAMSCAN_PATH
    p = _which("clamscan")
    if p:
        return p
    # Windows default install
    cand = Path("C:/Program Files/ClamAV/clamscan.exe")
    return cand if cand.exists() else None


def scan_file(path: str) -> tuple[bool, str]:
    """Scan file with available AV tool.

    Returns (is_clean, message). If AV disabled or not found, returns (True, reason).
    """
    if not settings.AV_SCAN_ENABLED:
        return True, "AV scan disabled"

    p = Path(path)
    if not p.exists():
        return False, "File not found for scan"

    defender = detect_defender()
    if defender:
        try:
            # 3 = Custom scan, single file
            result = subprocess.run(
                [str(defender), "-Scan", "-ScanType", "3", "-File", str(p)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
            )
            out = result.stdout
            if "No threats" in out or "0 threats" in out:
                return True, "Windows Defender: clean"
            if result.returncode == 0:
                # Defender sometimes exits 0 even when threats are found; check keywords
                if "threat" in out.lower():
                    return False, "Windows Defender: threat found"
                return True, "Windows Defender: clean"
            return False, "Windows Defender: scan failed or threat found"
        except Exception as e:
            logger.warning(f"Defender scan failed: {e}")
    clam = detect_clamav()
    if clam:
        try:
            result = subprocess.run(
                [str(clam), str(p)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
            )
            out = result.stdout
            if "OK" in out and "FOUND" not in out:
                return True, "ClamAV: clean"
            if "FOUND" in out:
                return False, "ClamAV: threat found"
            return result.returncode == 0, "ClamAV: scan finished"
        except Exception as e:
            logger.warning(f"ClamAV scan failed: {e}")
    return True, "No antivirus available; skipped"
