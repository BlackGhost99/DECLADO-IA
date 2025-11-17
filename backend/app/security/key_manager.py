from __future__ import annotations

import hashlib
import logging
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class DBKey:
    key_bytes: bytes  # 32 bytes
    salt: bytes  # 16 bytes
    iterations: int


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _pbkdf2_derive(
    passphrase: str, salt: bytes, iterations: int = 200_000, length: int = 32
) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=length)


def _is_windows() -> bool:
    return sys.platform.startswith("win")


# Minimal DPAPI via ctypes (no external deps)
if _is_windows():
    import ctypes
    import ctypes.wintypes as wt

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", wt.LPBYTE)]

    CryptProtectData = ctypes.windll.crypt32.CryptProtectData
    CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wt.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        wt.LPVOID,
        wt.LPVOID,
        wt.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    CryptProtectData.restype = wt.BOOL

    CryptUnprotectData = ctypes.windll.crypt32.CryptUnprotectData
    CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(wt.LPWSTR),
        ctypes.POINTER(DATA_BLOB),
        wt.LPVOID,
        wt.LPVOID,
        wt.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    CryptUnprotectData.restype = wt.BOOL

    def _dpapi_protect(data: bytes) -> bytes:
        in_blob = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), wt.LPBYTE))
        out_blob = DATA_BLOB()
        if not CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            raise OSError("CryptProtectData failed")
        try:
            buf = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return buf
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    def _dpapi_unprotect(blob: bytes) -> bytes:
        in_blob = DATA_BLOB(len(blob), ctypes.cast(ctypes.create_string_buffer(blob), wt.LPBYTE))
        out_blob = DATA_BLOB()
        if not CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            raise OSError("CryptUnprotectData failed")
        try:
            buf = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return buf
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)

else:

    def _dpapi_protect(data: bytes) -> bytes:  # type: ignore
        raise NotImplementedError

    def _dpapi_unprotect(blob: bytes) -> bytes:  # type: ignore
        raise NotImplementedError


def load_or_create_db_key() -> DBKey:
    """Load DB key from DPAPI-protected keystore (Windows). If not present, derive and store.

    On non-Windows: derive from passphrase and salt; do not store the key by default.
    """
    keystore = Path(settings.DB_KEYSTORE_PATH)
    salt_path = Path(settings.DB_SALT_PATH)
    iterations = settings.DB_PBKDF2_ITERATIONS

    # Choose passphrase source
    passphrase = settings.DB_PASSPHRASE or settings.SECRET_KEY

    # Ensure salt exists (consistent derivation)
    if salt_path.exists():
        salt = salt_path.read_bytes()
    else:
        salt = secrets.token_bytes(16)
        _ensure_parent(salt_path)
        salt_path.write_bytes(salt)

    if _is_windows():
        if keystore.exists():
            try:
                blob = keystore.read_bytes()
                key_bytes = _dpapi_unprotect(blob)
                if len(key_bytes) != 32:
                    raise ValueError("Invalid key length in keystore")
                return DBKey(key_bytes=key_bytes, salt=salt, iterations=iterations)
            except Exception as e:
                logger.warning(f"Failed to read DPAPI keystore, regenerating: {e}")
        # Derive and store
        key_bytes = _pbkdf2_derive(passphrase, salt, iterations, 32)
        blob = _dpapi_protect(key_bytes)
        _ensure_parent(keystore)
        keystore.write_bytes(blob)
        return DBKey(key_bytes=key_bytes, salt=salt, iterations=iterations)
    else:
        # Non-Windows: derive key at runtime; do not persist key to disk
        if not settings.DB_PASSPHRASE:
            logger.warning(
                "DB_PASSPHRASE not set; deriving key from SECRET_KEY (less secure). Set DB_PASSPHRASE in .env for better security."
            )
        key_bytes = _pbkdf2_derive(passphrase, salt, iterations, 32)
        return DBKey(key_bytes=key_bytes, salt=salt, iterations=iterations)


def sqlcipher_hex_key(key_bytes: bytes) -> str:
    """Return SQLCipher-compatible hex key string: x'HEX'"""
    return "x'" + key_bytes.hex() + "'"
