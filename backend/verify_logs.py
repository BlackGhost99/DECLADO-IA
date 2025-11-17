#!/usr/bin/env python
"""Standalone HMAC log chain verification script."""

import os
import sys

# Force UTF-8 output on Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from app.security.hmac_logger import verify_log_chain


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_logs.py <log_path>")
        sys.exit(1)

    log_path = sys.argv[1]
    if verify_log_chain(log_path):
        print(f"✅ Log chain verified: {log_path}")
        sys.exit(0)
    else:
        print(f"❌ Log chain INVALID: {log_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
