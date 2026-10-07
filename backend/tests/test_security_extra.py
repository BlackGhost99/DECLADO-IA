"""Extra coverage for app.security: antivirus, HMAC audit log, signatures, key manager.

Everything runs offline and deterministically: no real antivirus, no DPAPI, no
writes outside ``tmp_path``. OS commands, ``shutil.which`` and Windows APIs are
monkeypatched.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import hashlib
import hmac
import importlib.util
import json
import logging
import subprocess
import sys
import types
from pathlib import Path

import pytest

from app.core.config import settings
from app.security import antivirus, hmac_logger, key_manager, signatures

TEST_KEY = "unit-test-hmac-key"


# ============================================================================
# Antivirus
# ============================================================================


@pytest.fixture
def av_enabled(monkeypatch):
    monkeypatch.setattr(settings, "AV_SCAN_ENABLED", True)
    monkeypatch.setattr(settings, "AV_DEFENDER_PATH", None)
    monkeypatch.setattr(settings, "AV_CLAMSCAN_PATH", None)


@pytest.fixture
def sample_file(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    return f


def _fake_run(stdout: str = "", returncode: int = 0, exc: Exception | None = None):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout)

    run.calls = calls
    return run


def _redirect_av_paths(monkeypatch, mapping: dict[str, Path]):
    """Redirect hard-coded Windows install paths of antivirus.py into tmp_path."""
    real_path = Path

    def fake_path(*args):
        if len(args) == 1 and str(args[0]) in mapping:
            return mapping[str(args[0])]
        return real_path(*args)

    monkeypatch.setattr(antivirus, "Path", fake_path)


def test_which_found_and_missing(monkeypatch):
    monkeypatch.setattr(antivirus.shutil, "which", lambda exe: "/usr/bin/" + exe)
    assert antivirus._which("clamscan") == Path("/usr/bin/clamscan")
    monkeypatch.setattr(antivirus.shutil, "which", lambda exe: None)
    assert antivirus._which("clamscan") is None


def test_detect_defender_explicit_setting(monkeypatch, tmp_path):
    exe = tmp_path / "MpCmdRun.exe"
    exe.write_text("x")
    monkeypatch.setattr(settings, "AV_DEFENDER_PATH", exe)
    assert antivirus.detect_defender() == exe


def test_detect_defender_on_path(monkeypatch, av_enabled):
    monkeypatch.setattr(antivirus, "_which", lambda exe: Path("/opt/av/MpCmdRun.exe"))
    assert antivirus.detect_defender() == Path("/opt/av/MpCmdRun.exe")


def test_detect_defender_platform_dir(monkeypatch, tmp_path, av_enabled):
    platform_dir = tmp_path / "Platform"
    (platform_dir / "4.18.1").mkdir(parents=True)
    newest = platform_dir / "4.18.2"
    newest.mkdir()
    (newest / "MpCmdRun.exe").write_text("x")
    (platform_dir / "4.18.0").mkdir()
    (platform_dir / "4.18.0" / "MpCmdRun.exe").write_text("x")
    (platform_dir / "not-a-dir.txt").write_text("x")
    _redirect_av_paths(
        monkeypatch, {"C:/ProgramData/Microsoft/Windows Defender/Platform": platform_dir}
    )
    monkeypatch.setattr(antivirus, "_which", lambda exe: None)
    assert antivirus.detect_defender() == newest / "MpCmdRun.exe"


def test_detect_defender_platform_dir_without_exe(monkeypatch, tmp_path, av_enabled):
    platform_dir = tmp_path / "Platform"
    (platform_dir / "4.18.1").mkdir(parents=True)
    _redirect_av_paths(
        monkeypatch, {"C:/ProgramData/Microsoft/Windows Defender/Platform": platform_dir}
    )
    monkeypatch.setattr(antivirus, "_which", lambda exe: None)
    assert antivirus.detect_defender() is None


def test_detect_defender_none(monkeypatch, tmp_path, av_enabled):
    _redirect_av_paths(
        monkeypatch,
        {"C:/ProgramData/Microsoft/Windows Defender/Platform": tmp_path / "missing"},
    )
    monkeypatch.setattr(antivirus, "_which", lambda exe: None)
    assert antivirus.detect_defender() is None


def test_detect_clamav_variants(monkeypatch, tmp_path, av_enabled):
    exe = tmp_path / "clamscan.exe"
    exe.write_text("x")
    monkeypatch.setattr(settings, "AV_CLAMSCAN_PATH", exe)
    assert antivirus.detect_clamav() == exe

    monkeypatch.setattr(settings, "AV_CLAMSCAN_PATH", None)
    monkeypatch.setattr(antivirus, "_which", lambda name: Path("/usr/bin/clamscan"))
    assert antivirus.detect_clamav() == Path("/usr/bin/clamscan")

    monkeypatch.setattr(antivirus, "_which", lambda name: None)
    _redirect_av_paths(monkeypatch, {"C:/Program Files/ClamAV/clamscan.exe": exe})
    assert antivirus.detect_clamav() == exe

    _redirect_av_paths(
        monkeypatch, {"C:/Program Files/ClamAV/clamscan.exe": tmp_path / "absent.exe"}
    )
    assert antivirus.detect_clamav() is None


def test_scan_disabled(monkeypatch, sample_file):
    monkeypatch.setattr(settings, "AV_SCAN_ENABLED", False)
    assert antivirus.scan_file(str(sample_file)) == (True, "AV scan disabled")


def test_scan_missing_file(av_enabled, tmp_path):
    ok, msg = antivirus.scan_file(str(tmp_path / "nope.pdf"))
    assert ok is False
    assert "not found" in msg


@pytest.mark.parametrize(
    "stdout, rc, expected",
    [
        ("Scan finished. No threats found.", 0, (True, "Windows Defender: clean")),
        ("found 0 threats", 2, (True, "Windows Defender: clean")),
        ("Threat Trojan:Win32 detected", 0, (False, "Windows Defender: threat found")),
        ("Scan completed", 0, (True, "Windows Defender: clean")),
        ("error", 2, (False, "Windows Defender: scan failed or threat found")),
    ],
)
def test_scan_with_defender(monkeypatch, av_enabled, sample_file, stdout, rc, expected):
    monkeypatch.setattr(antivirus, "detect_defender", lambda: Path("MpCmdRun.exe"))
    monkeypatch.setattr(antivirus, "detect_clamav", lambda: None)
    fake = _fake_run(stdout, rc)
    monkeypatch.setattr(antivirus.subprocess, "run", fake)
    assert antivirus.scan_file(str(sample_file)) == expected
    assert fake.calls[0][:2] == ["MpCmdRun.exe", "-Scan"]


@pytest.mark.parametrize(
    "stdout, rc, expected",
    [
        ("doc.pdf: OK", 0, (True, "ClamAV: clean")),
        ("doc.pdf: Eicar-Test-Signature FOUND", 1, (False, "ClamAV: threat found")),
        ("weird output", 0, (True, "ClamAV: scan finished")),
        ("weird output", 2, (False, "ClamAV: scan finished")),
    ],
)
def test_scan_with_clamav(monkeypatch, av_enabled, sample_file, stdout, rc, expected):
    monkeypatch.setattr(antivirus, "detect_defender", lambda: None)
    monkeypatch.setattr(antivirus, "detect_clamav", lambda: Path("clamscan"))
    monkeypatch.setattr(antivirus.subprocess, "run", _fake_run(stdout, rc))
    assert antivirus.scan_file(str(sample_file)) == expected


def test_scan_defender_error_falls_back_to_clamav(monkeypatch, av_enabled, sample_file):
    monkeypatch.setattr(antivirus, "detect_defender", lambda: Path("MpCmdRun.exe"))
    monkeypatch.setattr(antivirus, "detect_clamav", lambda: Path("clamscan"))

    def run(cmd, **kwargs):
        if cmd[0] == "MpCmdRun.exe":
            raise subprocess.TimeoutExpired(cmd, 120)
        return subprocess.CompletedProcess(cmd, 0, stdout="doc.pdf: OK")

    monkeypatch.setattr(antivirus.subprocess, "run", run)
    assert antivirus.scan_file(str(sample_file)) == (True, "ClamAV: clean")


def test_scan_all_tools_fail_or_absent(monkeypatch, av_enabled, sample_file):
    monkeypatch.setattr(antivirus, "detect_defender", lambda: None)
    monkeypatch.setattr(antivirus, "detect_clamav", lambda: Path("clamscan"))
    monkeypatch.setattr(antivirus.subprocess, "run", _fake_run(exc=OSError("boom")))
    assert antivirus.scan_file(str(sample_file)) == (True, "No antivirus available; skipped")

    monkeypatch.setattr(antivirus, "detect_clamav", lambda: None)
    assert antivirus.scan_file(str(sample_file)) == (True, "No antivirus available; skipped")


# ============================================================================
# HMAC audit logger
# ============================================================================


@pytest.fixture
def hmac_settings(monkeypatch):
    monkeypatch.setattr(settings, "LOG_HMAC_KEY", TEST_KEY)
    monkeypatch.setenv("DECLADO_USER", "pytest-user")


def _record(msg: str, level: int = logging.INFO, name: str = "audit") -> logging.LogRecord:
    return logging.LogRecord(name, level, __file__, 1, msg, None, None)


def _make_handler(path: Path, key: str | None = None) -> hmac_logger.HMACFileHandler:
    handler = hmac_logger.HMACFileHandler(path, key=key)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def test_hmac_chain_roundtrip_and_resume(tmp_path, hmac_settings):
    log = tmp_path / "nested" / "audit.log"
    handler = _make_handler(log)
    assert handler.prev_hmac == "GENESIS"
    assert handler.user == "pytest-user"
    handler.emit(_record("first"))
    handler.emit(_record("second", logging.WARNING))
    handler.close()

    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(ln) for ln in lines)
    assert first["prev_hmac"] == "GENESIS"
    assert second["prev_hmac"] == first["hmac"]
    assert hmac_logger.verify_log_chain(str(log)) is True
    assert hmac_logger.verify_log_chain(str(log), key="wrong-key") is False

    # A new handler resumes the chain from the last entry
    resumed = _make_handler(log)
    assert resumed.prev_hmac == second["hmac"]
    resumed.emit(_record("third"))
    resumed.close()
    # blank lines are ignored by the verifier
    with log.open("a", encoding="utf-8") as f:
        f.write("\n")
    assert hmac_logger.verify_log_chain(str(log)) is True


def test_hmac_explicit_key(tmp_path, hmac_settings):
    log = tmp_path / "audit.log"
    handler = _make_handler(log, key="explicit")
    handler.emit(_record("hello"))
    handler.close()
    assert hmac_logger.verify_log_chain(str(log), key="explicit") is True
    assert hmac_logger.verify_log_chain(str(log)) is False


def test_hmac_tampered_and_invalid_logs(tmp_path, hmac_settings):
    log = tmp_path / "audit.log"
    handler = _make_handler(log)
    handler.emit(_record("original"))
    handler.close()

    entry = json.loads(log.read_text(encoding="utf-8"))
    entry["msg"] = "tampered"
    log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    assert hmac_logger.verify_log_chain(str(log)) is False

    log.write_text("not json\n", encoding="utf-8")
    assert hmac_logger.verify_log_chain(str(log)) is False
    assert hmac_logger.verify_log_chain(str(tmp_path / "missing.log")) is False


def test_hmac_last_hmac_edge_cases(tmp_path, hmac_settings):
    empty = tmp_path / "empty.log"
    empty.write_text("\n\n", encoding="utf-8")
    assert _make_handler(empty).prev_hmac == "GENESIS"

    garbage = tmp_path / "garbage.log"
    garbage.write_text("{broken\n", encoding="utf-8")
    assert _make_handler(garbage).prev_hmac == "GENESIS"

    no_mac = tmp_path / "nomac.log"
    no_mac.write_text(json.dumps({"msg": "x"}) + "\n", encoding="utf-8")
    assert _make_handler(no_mac).prev_hmac == "GENESIS"


def test_hmac_emit_error_is_handled(tmp_path, hmac_settings, monkeypatch):
    handler = _make_handler(tmp_path / "audit.log")
    errors = []
    monkeypatch.setattr(handler, "handleError", lambda record: errors.append(record))
    handler.path = tmp_path  # a directory: opening it for append fails
    rec = _record("boom")
    handler.emit(rec)
    assert errors == [rec]
    assert handler.prev_hmac == "GENESIS"


def test_configure_hmac_logging(tmp_path, hmac_settings, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "LOG_LEVEL", "WARNING")
    root = logging.getLogger()
    before = list(root.handlers)
    hmac_logger.configure_hmac_logging()
    added = [h for h in root.handlers if h not in before]
    try:
        assert len(added) == 1
        handler = added[0]
        assert isinstance(handler, hmac_logger.HMACFileHandler)
        assert handler.level == logging.WARNING
        assert (tmp_path / "logs").is_dir()
    finally:
        for h in added:
            root.removeHandler(h)
            h.close()


# ============================================================================
# Signatures
# ============================================================================


def _sign(digest: str, key: str = TEST_KEY) -> str:
    return hmac.new(key.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()


@pytest.fixture
def signed_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOG_HMAC_KEY", TEST_KEY)
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    (repo / "a.txt").write_bytes(b"alpha")
    (repo / "sub" / "b.bin").write_bytes(b"\x00\x01")
    (repo / "sub" / "ignored.sig").write_text("not hashed")
    digest = signatures.compute_dir_digest(repo)
    (repo / ".sig").write_text(
        json.dumps({"algo": "HMAC-SHA256", "digest": digest, "hmac": _sign(digest)}),
        encoding="utf-8",
    )
    return repo


def test_iter_files_and_dir_digest(signed_dir):
    names = [p.name for p in signatures._iter_files(signed_dir)]
    assert names == ["a.txt", "b.bin"]

    expected = hashlib.sha256()
    for rel, data in (("a.txt", b"alpha"), ("sub/b.bin", b"\x00\x01")):
        expected.update(rel.encode("utf-8"))
        expected.update(data)
    assert signatures.compute_dir_digest(signed_dir) == expected.hexdigest()


def test_verify_signature_dir_ok_and_tampered(signed_dir):
    assert signatures.verify_signature(signed_dir) is True
    (signed_dir / "a.txt").write_bytes(b"changed")
    assert signatures.verify_signature(signed_dir) is False


def test_verify_signature_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOG_HMAC_KEY", TEST_KEY)
    model = tmp_path / "model.onnx"
    model.write_bytes(b"weights")
    digest = hashlib.sha256(b"weights").hexdigest()
    sig = tmp_path / "model.onnx.sig"
    sig.write_text(json.dumps({"digest": digest, "hmac": _sign(digest)}), encoding="utf-8")
    assert signatures.verify_signature(model) is True

    sig.write_text(json.dumps({"digest": digest, "hmac": _sign(digest, "other")}))
    assert signatures.verify_signature(model) is False


def test_verify_signature_missing_sig_file(tmp_path):
    (tmp_path / "plain").mkdir()
    assert signatures.verify_signature(tmp_path / "plain") is True


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps({"algo": "HMAC-SHA256", "hmac": "x"}),  # missing digest
        json.dumps({"algo": "ED25519", "digest": "x", "hmac": "y"}),  # unsupported
    ],
)
def test_verify_signature_invalid_sig_files(signed_dir, content):
    (signed_dir / ".sig").write_text(content, encoding="utf-8")
    assert signatures.verify_signature(signed_dir) is False


# ============================================================================
# Key manager
# ============================================================================


@pytest.fixture
def key_paths(tmp_path, monkeypatch):
    keystore = tmp_path / "keys" / "db_key.bin"
    salt = tmp_path / "keys" / "db_key.salt"
    monkeypatch.setattr(settings, "DB_KEYSTORE_PATH", keystore)
    monkeypatch.setattr(settings, "DB_SALT_PATH", salt)
    monkeypatch.setattr(settings, "DB_PBKDF2_ITERATIONS", 1000)
    monkeypatch.setattr(settings, "DB_PASSPHRASE", "throwaway-passphrase")
    return keystore, salt


def test_pbkdf2_and_hex_key():
    key = key_manager._pbkdf2_derive("pw", b"\x00" * 16, iterations=10)
    assert key == hashlib.pbkdf2_hmac("sha256", b"pw", b"\x00" * 16, 10, dklen=32)
    assert key_manager.sqlcipher_hex_key(b"\x01\xff") == "x'01ff'"
    assert key_manager._is_windows() is sys.platform.startswith("win")


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_load_key_non_windows(monkeypatch, key_paths):
    keystore, salt_path = key_paths
    monkeypatch.setattr(key_manager, "_is_windows", lambda: False)
    k1 = key_manager.load_or_create_db_key()
    assert salt_path.exists() and len(salt_path.read_bytes()) == 16
    assert len(k1.key_bytes) == 32 and k1.iterations == 1000
    assert not keystore.exists()  # never persisted off Windows

    k2 = key_manager.load_or_create_db_key()
    assert k2.key_bytes == k1.key_bytes and k2.salt == k1.salt

    monkeypatch.setattr(settings, "DB_PASSPHRASE", None)
    capture = _ListHandler()
    key_manager.logger.addHandler(capture)
    try:
        k3 = key_manager.load_or_create_db_key()
    finally:
        key_manager.logger.removeHandler(capture)
    assert k3.key_bytes != k1.key_bytes
    assert any("DB_PASSPHRASE not set" in m for m in capture.messages)


def _fake_dpapi(monkeypatch, module):
    monkeypatch.setattr(module, "_dpapi_protect", lambda data: b"PROT" + data[::-1])

    def unprotect(blob: bytes) -> bytes:
        if not blob.startswith(b"PROT"):
            raise OSError("CryptUnprotectData failed")
        return blob[4:][::-1]

    monkeypatch.setattr(module, "_dpapi_unprotect", unprotect)


def test_load_key_windows_flow(monkeypatch, key_paths):
    keystore, _ = key_paths
    monkeypatch.setattr(key_manager, "_is_windows", lambda: True)
    _fake_dpapi(monkeypatch, key_manager)

    created = key_manager.load_or_create_db_key()
    assert keystore.exists() and keystore.read_bytes().startswith(b"PROT")

    loaded = key_manager.load_or_create_db_key()
    assert loaded.key_bytes == created.key_bytes

    # Wrong key length in keystore -> regenerated
    keystore.write_bytes(b"PROT" + b"short")
    regenerated = key_manager.load_or_create_db_key()
    assert regenerated.key_bytes == created.key_bytes
    assert len(key_manager._dpapi_unprotect(keystore.read_bytes())) == 32

    # Unreadable keystore -> regenerated
    keystore.write_bytes(b"garbage")
    assert key_manager.load_or_create_db_key().key_bytes == created.key_bytes


@pytest.mark.skipif(sys.platform.startswith("win"), reason="stubs exist only off Windows")
def test_dpapi_stubs_raise_off_windows():
    with pytest.raises(NotImplementedError):
        key_manager._dpapi_protect(b"x")
    with pytest.raises(NotImplementedError):
        key_manager._dpapi_unprotect(b"x")


def _load_key_manager_as_windows(monkeypatch, succeed: bool = True):
    """Execute a private copy of key_manager.py with a fake Windows DPAPI.

    The real module is untouched; the copy runs its Windows-only branch against
    fake ``crypt32``/``kernel32`` functions so it works on any OS.
    """
    keep_alive = []
    freed = []

    def _transform(in_ref, out_ref, fn):
        if not succeed:
            return 0
        in_blob = in_ref._obj
        data = fn(ctypes.string_at(in_blob.pbData, in_blob.cbData))
        buf = ctypes.create_string_buffer(data, len(data))
        keep_alive.append(buf)
        out_blob = out_ref._obj
        out_blob.cbData = len(data)
        out_blob.pbData = ctypes.cast(buf, wt.LPBYTE)
        return 1

    def crypt_protect(in_ref, desc, entropy, reserved, prompt, flags, out_ref):
        return _transform(in_ref, out_ref, lambda d: b"DP" + d)

    def crypt_unprotect(in_ref, desc, entropy, reserved, prompt, flags, out_ref):
        return _transform(in_ref, out_ref, lambda d: d[2:])

    fake_windll = types.SimpleNamespace(
        crypt32=types.SimpleNamespace(
            CryptProtectData=crypt_protect, CryptUnprotectData=crypt_unprotect
        ),
        kernel32=types.SimpleNamespace(LocalFree=lambda ptr: freed.append(ptr)),
    )
    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)

    spec = importlib.util.spec_from_file_location("key_manager_windows_copy", key_manager.__file__)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve the defining module through sys.modules
    monkeypatch.setitem(sys.modules, spec.name, module)
    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "win32")
        spec.loader.exec_module(module)
    return module, freed


def test_dpapi_windows_branch_with_fake_crypt32(monkeypatch, key_paths):
    module, freed = _load_key_manager_as_windows(monkeypatch)
    blob = module._dpapi_protect(b"secret-bytes")
    assert blob == b"DPsecret-bytes"
    assert module._dpapi_unprotect(blob) == b"secret-bytes"
    assert len(freed) == 2

    keystore, _ = key_paths
    monkeypatch.setattr(module, "_is_windows", lambda: True)
    key = module.load_or_create_db_key()
    assert keystore.read_bytes() == b"DP" + key.key_bytes
    assert module.load_or_create_db_key().key_bytes == key.key_bytes


def test_dpapi_windows_branch_failures(monkeypatch):
    module, _ = _load_key_manager_as_windows(monkeypatch, succeed=False)
    with pytest.raises(OSError, match="CryptProtectData failed"):
        module._dpapi_protect(b"x")
    with pytest.raises(OSError, match="CryptUnprotectData failed"):
        module._dpapi_unprotect(b"x")
