"""MFA must remain server-enforced; authentication challenge is not a logged-in session."""

import pytest
from cryptography.fernet import Fernet
from django.core.cache import cache

from apps.accounts import mfa
from apps.accounts.models import TotpDevice
from tests.conftest import PASSWORD


@pytest.fixture(autouse=True)
def mfa_settings(settings):
    settings.MFA_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
    settings.MFA_ENFORCE = True
    settings.AUTH_RATE_LIMIT_ENABLED = True
    cache.clear()


def test_production_gate_prevents_access_until_enrolled(world, session):
    s = session("declarant@a.test")
    assert s.get("/api/v1/me").status_code == 200
    blocked = s.get("/api/v1/importers")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "MFA_REQUIRED"
    info = s.post("/api/v1/auth/mfa/setup")
    assert info.status_code == 200
    assert info.json()["provisioning_uri"].startswith("otpauth://totp/")
    secret = info.json()["secret"]
    step = int(mfa.time.time() // mfa.PERIOD)
    done = s.post("/api/v1/auth/mfa/confirm", {"code": mfa._totp(secret, step)})
    assert done.status_code == 200, done.content
    codes = done.json()["recovery_codes"]
    assert len(codes) == len(set(codes)) == 10
    assert s.get("/api/v1/importers").status_code == 200
    assert TotpDevice.objects.get(user=world["users"]["a_declarant"]).encrypted_secret != secret


def test_two_step_login_and_recovery_code_single_use(world, session):
    s = session("declarant@a.test")
    secret = s.post("/api/v1/auth/mfa/setup").json()["secret"]
    code = mfa._totp(secret, int(mfa.time.time() // mfa.PERIOD))
    recover = s.post("/api/v1/auth/mfa/confirm", {"code": code}).json()["recovery_codes"][0]
    assert s.post("/api/v1/auth/logout").status_code == 204
    challenge = s.login("declarant@a.test", PASSWORD)
    assert challenge.status_code == 202
    assert challenge.json() == {"mfa_required": True}
    assert s.get("/api/v1/me").status_code == 401
    assert s.get("/api/v1/importers").status_code == 401
    assert s.post("/api/v1/auth/mfa/verify", {"code": "not-valid"}).status_code == 400
    complete = s.post("/api/v1/auth/mfa/verify", {"code": recover})
    assert complete.status_code == 200, complete.content
    assert complete.json()["mfa_verified_session"] is True
    assert s.get("/api/v1/importers").status_code == 200
    s.post("/api/v1/auth/logout")
    assert s.login("declarant@a.test").status_code == 202
    assert s.post("/api/v1/auth/mfa/verify", {"code": recover}).status_code == 400


def test_login_password_throttled(world, session):
    s = session()
    for _ in range(8):
        assert s.login("declarant@a.test", "incorrect").status_code == 400
    assert s.login("declarant@a.test", "incorrect").status_code == 429


def test_pending_verification_requires_csrf(world, session):
    s = session("declarant@a.test")
    secret = s.post("/api/v1/auth/mfa/setup").json()["secret"]
    s.post("/api/v1/auth/mfa/confirm", {"code": mfa._totp(secret, int(mfa.time.time() // 30))})
    s.post("/api/v1/auth/logout")
    assert s.login("declarant@a.test").status_code == 202
    response = s.client.post("/api/v1/auth/mfa/verify", {"code": "123456"}, format="json")
    assert response.status_code == 403


def test_totp_replay_is_rejected_even_with_valid_code():
    secret = mfa.new_secret()
    now = 1775000000
    code = mfa._totp(secret, int(now // 30))
    step = mfa.accepted_step(secret, code, now=now)
    assert step is not None
    assert mfa.accepted_step(secret, code, now=now, after=step) is None
