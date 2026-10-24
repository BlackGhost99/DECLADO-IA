"""Fail-closed ClamAV INSTREAM client; no untrusted filesystem path is sent to clamd."""

import socket
import struct
from pathlib import Path

from django.conf import settings


class MalwareDetected(Exception):
    """ClamAV found a malicious signature."""


class ScanUnavailable(Exception):
    """Scanner refused, timed out, returned an invalid reply, or could not be reached."""


def scan_file(path: Path) -> None:
    """Require an explicit 'OK' from clamd before treating a file as clean."""
    host = settings.CLAMAV_HOST
    port = settings.CLAMAV_PORT
    try:
        with socket.create_connection((host, port), timeout=settings.CLAMAV_CONNECT_TIMEOUT) as conn:
            conn.settimeout(settings.CLAMAV_SCAN_TIMEOUT)
            conn.sendall(b"zINSTREAM\0")
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    conn.sendall(struct.pack("!I", len(chunk)))
                    conn.sendall(chunk)
            conn.sendall(struct.pack("!I", 0))
            result = bytearray()
            while len(result) < 4096:
                part = conn.recv(4096 - len(result))
                if not part:
                    break
                result.extend(part)
                if b"\0" in part:
                    break
    except (OSError, TimeoutError, ValueError) as exc:
        raise ScanUnavailable("ClamAV indisponible ou analyse interrompue.") from exc

    reply = bytes(result).split(b"\0", 1)[0]
    if reply == b"stream: OK":
        return
    if reply.startswith(b"stream: ") and reply.endswith(b" FOUND"):
        raise MalwareDetected("Signature malveillante détectée.")
    raise ScanUnavailable("ClamAV n'a pas confirmé un résultat sain.")
