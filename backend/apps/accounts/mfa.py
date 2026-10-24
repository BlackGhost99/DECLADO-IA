"""TOTP MFA, encrypted secrets, one-time recovery codes, and replay prevention."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from apps.core.exceptions import ApiError

PERIOD = 30
WINDOW = 1
CHALLENGE_TTL = 300


def _cipher():
    key = settings.MFA_ENCRYPTION_KEY
    if not key:
        # A deployment without a dedicated key must not create readable MFA secrets.
        raise ApiError("MFA_NOT_CONFIGURED", "Chiffrement MFA non configuré.", 503)
    return Fernet(key.encode("ascii"))


def encrypt_secret(secret: str) -> str:
    return _cipher().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(encrypted: str) -> str:
    return _cipher().decrypt(encrypted.encode("ascii")).decode("ascii")


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def provisioning_uri(email: str, secret: str) -> str:
    return (
        f"otpauth://totp/{quote('ClairTransit:' + email, safe='')}?"
        f"secret={secret}&issuer=ClairTransit&algorithm=SHA1&digits=6&period=30"
    )


def _totp(secret: str, counter: int) -> str:
    decoded = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(decoded, struct.pack("!Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    value = struct.unpack("!I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1000000:06d}"


def accepted_step(secret: str, code: str, *, now: float | None = None, after: int = -1) -> int | None:
    if len(code) != 6 or not code.isascii() or not code.isdecimal():
        return None
    tick = int((time.time() if now is None else now) // PERIOD)
    for step in (tick - 1, tick, tick + 1):
        if step > after and step >= 0 and hmac.compare_digest(_totp(secret, step), code):
            return step
    return None


def _recovery_digest(code: str) -> str:
    normalized = code.replace("-", "").replace(" ", "").upper()
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), normalized.encode("ascii", errors="ignore"), hashlib.sha256
    ).hexdigest()


def issue_recovery_codes() -> tuple[list[str], list[str]]:
    codes = [secrets.token_hex(6).upper() for _ in range(10)]
    return codes, [_recovery_digest(code) for code in codes]


@transaction.atomic
def consume_second_factor(user, code: str) -> bool:
    """Atomic compare/update prevents TOTP replay and recovery-code reuse."""
    from .models import TotpDevice

    device = TotpDevice.objects.select_for_update().filter(user=user, confirmed_at__isnull=False).first()
    if device is None:
        return False
    candidate = code.strip().replace("-", "").replace(" ", "").upper()
    digest = _recovery_digest(candidate)
    for existing in device.recovery_hashes:
        if hmac.compare_digest(existing, digest):
            device.recovery_hashes.remove(existing)
            device.save(update_fields=["recovery_hashes"])
            return True
    step = accepted_step(decrypt_secret(device.encrypted_secret), code.strip(), after=device.last_step)
    if step is None:
        return False
    device.last_step = step
    device.save(update_fields=["last_step"])
    return True


def rate_limit(request, bucket: str, identity: str, *, limit: int, seconds: int) -> None:
    """Production uses Redis; any cache outage refuses authentication, not admits it."""
    if not settings.AUTH_RATE_LIMIT_ENABLED:
        return
    raw = f"{bucket}:{identity}:{request.META.get('REMOTE_ADDR', '')}"
    key = "auth:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    try:
        if cache.add(key, 1, timeout=seconds):
            attempts = 1
        else:
            attempts = cache.incr(key)
    except Exception as exc:
        raise ApiError("AUTH_RATE_LIMIT_UNAVAILABLE", "Protection de connexion indisponible.", 503) from exc
    if attempts > limit:
        raise ApiError("AUTH_RATE_LIMIT", "Trop de tentatives, veuillez réessayer plus tard.", 429)
