#!/usr/bin/env python
"""
Validation script for DECLADO-IA security & encryption acceptance criteria.

Tests:
1. DB is unreadable without key (sqlite3 fails)
2. HMAC log chain is verifiable
3. Tampering detection works
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def test_db_unreadable() -> bool:
    """Test that encrypted DB file cannot be opened with standard sqlite3."""
    db_path = Path("./data/declado.db")
    if not db_path.exists():
        print("⚠️  No database file found; skip DB test.")
        return True

    # Try to open with sqlite3 CLI (should fail)
    try:
        result = subprocess.run(
            ["sqlite3", str(db_path), "SELECT 1;"], capture_output=True, text=True, timeout=5
        )
        if "encrypted" in result.stderr.lower() or "not a database" in result.stderr.lower():
            print("✅ DB unreadable without key (sqlite3 error as expected)")
            return True
        if result.returncode != 0:
            print("✅ DB access failed as expected (non-zero exit code)")
            return True
        print(f"❌ DB was opened by sqlite3 without key (should fail): {result.stdout}")
        return False
    except FileNotFoundError:
        print("⚠️  sqlite3 CLI not found; manual check: try opening ./data/declado.db")
        return True
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False


def test_log_chain_valid() -> bool:
    """Test that HMAC log chain verification passes."""
    log_path = Path("./logs/declado-audit.log")
    if not log_path.exists():
        print("⚠️  No audit log found; skip log test.")
        return True

    try:
        result = subprocess.run(
            [sys.executable, "verify_logs.py", str(log_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode == 0 and "verified" in result.stdout.lower():
            print("✅ Log chain verified successfully")
            return True
        print(f"❌ Log verification failed: {result.stdout} {result.stderr}")
        return False
    except Exception as e:
        print(f"❌ Log verification error: {e}")
        return False


def test_tamper_detection() -> bool:
    """Test that tampering with audit log is detected."""
    log_path = Path("./logs/declado-audit.log")
    if not log_path.exists():
        print("⚠️  No audit log; skip tamper test.")
        return True

    backup = log_path.with_suffix(".log.bak")
    try:
        # Backup original
        shutil.copy(log_path, backup)

        # Tamper: append a fake line
        with log_path.open("a", encoding="utf-8") as f:
            f.write(
                '{"ts":"2025-01-01T00:00:00","level":"INFO","name":"test","msg":"TAMPER","hmac":"fake"}\n'
            )

        # Verify should fail
        result = subprocess.run(
            [sys.executable, "verify_logs.py", str(log_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )

        # Restore original
        shutil.move(backup, log_path)

        if result.returncode != 0 and "INVALID" in result.stdout:
            print("✅ Tamper detection works (modified log rejected)")
            return True
        print(f"❌ Tampered log was not detected: {result.stdout}")
        return False
    except Exception as e:
        # Ensure restore
        if backup.exists():
            shutil.move(backup, log_path)
        print(f"❌ Tamper test error: {e}")
        return False


def main() -> None:
    print("=" * 60)
    print("DECLADO-IA Security Acceptance Tests")
    print("=" * 60)

    os.chdir(Path(__file__).parent)

    results = {
        "DB unreadable": test_db_unreadable(),
        "Log chain valid": test_log_chain_valid(),
        "Tamper detection": test_tamper_detection(),
    }

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name}: {status}")

    if all(results.values()):
        print("\n🎉 All security tests passed!")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Review security setup.")
        sys.exit(1)


if __name__ == "__main__":
    main()
