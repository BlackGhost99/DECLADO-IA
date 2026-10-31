"""Fail-closed ClamAV INSTREAM client; no untrusted filesystem path is sent to clamd."""

import socket
import struct
from contextlib import contextmanager

from django.conf import settings


class MalwareDetected(Exception):
    """ClamAV found a malicious signature."""


class ScanUnavailable(Exception):
    """Scanner refused, timed out, returned an invalid reply, or could not be reached."""


class Stream:
    """One INSTREAM session fed chunk by chunk.

    Uploads are streamed to clamd while they are staged, so the verdict never depends on
    reopening the quarantined file: a desktop antivirus (Windows Defender) may lock or delete
    it as soon as it is written.
    """

    def __init__(self, conn: socket.socket):
        self._conn = conn

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        try:
            self._conn.sendall(struct.pack("!I", len(chunk)))
            self._conn.sendall(chunk)
        except (OSError, TimeoutError) as exc:
            raise ScanUnavailable("ClamAV indisponible ou analyse interrompue.") from exc

    def verdict(self) -> None:
        """Require an explicit 'OK' from clamd before treating the bytes as clean."""
        result = bytearray()
        try:
            self._conn.sendall(struct.pack("!I", 0))
            while len(result) < 4096:
                part = self._conn.recv(4096 - len(result))
                if not part:
                    break
                result.extend(part)
                if b"\0" in part:
                    break
        except (OSError, TimeoutError) as exc:
            raise ScanUnavailable("ClamAV indisponible ou analyse interrompue.") from exc

        reply = bytes(result).split(b"\0", 1)[0]
        if reply == b"stream: OK":
            return
        if reply.startswith(b"stream: ") and reply.endswith(b" FOUND"):
            raise MalwareDetected("Signature malveillante détectée.")
        raise ScanUnavailable("ClamAV n'a pas confirmé un résultat sain.")


@contextmanager
def open_stream():
    """Connect before any byte is staged: an unreachable scanner refuses the upload upfront."""
    try:
        conn = socket.create_connection(
            (settings.CLAMAV_HOST, settings.CLAMAV_PORT), timeout=settings.CLAMAV_CONNECT_TIMEOUT
        )
        conn.settimeout(settings.CLAMAV_SCAN_TIMEOUT)
        conn.sendall(b"zINSTREAM\0")
    except (OSError, TimeoutError, ValueError) as exc:
        raise ScanUnavailable("ClamAV indisponible ou analyse interrompue.") from exc
    try:
        yield Stream(conn)
    finally:
        conn.close()


def scan_file(path) -> None:
    """Scan a local file (e.g. a tariff given to the startup script) the same way as an upload."""
    with open_stream() as scanner, open(path, "rb") as source:
        while chunk := source.read(1024 * 1024):
            scanner.feed(chunk)
        scanner.verdict()


def version() -> str:
    """clamd's engine and signature version, e.g. 'ClamAV 1.5.4/27800/Fri Oct 30 08:00:00 2026'."""
    try:
        with socket.create_connection(
            (settings.CLAMAV_HOST, settings.CLAMAV_PORT), timeout=settings.CLAMAV_CONNECT_TIMEOUT
        ) as conn:
            conn.settimeout(settings.CLAMAV_SCAN_TIMEOUT)
            conn.sendall(b"zVERSION\0")
            reply = bytearray()
            while b"\0" not in reply and len(reply) < 1024:
                part = conn.recv(1024)
                if not part:
                    break
                reply.extend(part)
    except (OSError, TimeoutError, ValueError) as exc:
        raise ScanUnavailable("ClamAV indisponible ou analyse interrompue.") from exc
    text = bytes(reply).split(b"\0", 1)[0].decode("ascii", "replace").strip()
    if not text.startswith("ClamAV"):
        raise ScanUnavailable("ClamAV n'a pas donné sa version.")
    return text
