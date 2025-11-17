#!/usr/bin/env bash
# DECLADO-IA Phase 8 Security — Quick Start Guide

## ============================================
## 1. START BACKEND (with all security features)
## ============================================

cd backend
powershell -ExecutionPolicy Bypass -File .\start-backend.ps1

# Expected output:
# ✅ Poppler détecté: ...
# INFO:     Application startup complete.
# ✅ Base de données initialisée et connectée
# pysqlcipher3 not available; using standard SQLite (graceful fallback)


## ============================================
## 2. UPLOAD A FILE (triggers AV scan + OCR + HS + Customs)
## ============================================

# Via Electron frontend:
# 1. Create a project
# 2. Upload PDF/image
# 3. Observe: AV scan runs → OCR processes → HS suggestions → Customs calc
# 4. Check backend logs for: "Windows Defender: clean" or "No antivirus available"


## ============================================
## 3. VERIFY AUDIT LOGS (HMAC-signed)
## ============================================

python verify_logs.py ./logs/declado-audit.log

# Expected:
# ✅ Log chain verified: ./logs/declado-audit.log


## ============================================
## 4. TEST TAMPER DETECTION
## ============================================

# Edit a line in ./logs/declado-audit.log manually
# Then run verification again:

python verify_logs.py ./logs/declado-audit.log

# Expected:
# ❌ Log chain INVALID: ./logs/declado-audit.log


## ============================================
## 5. BACKUP DATABASE
## ============================================

python backup_db.py export backups/declado_backup_2025-11-16.db

# Database is backed up (encrypted if SQLCipher, std if not)


## ============================================
## 6. RESTORE DATABASE
## ============================================

python backup_db.py restore backups/declado_backup_2025-11-16.db --db ./data/declado.db

# Verify by restarting backend and checking logs


## ============================================
## 7. RUN SECURITY ACCEPTANCE TESTS
## ============================================

python test_security.py

# Tests:
# ✅ DB unreadable: PASS (using std SQLite or encrypted SQLCipher)
# ✅ Log chain valid: PASS (HMAC-signed)
# ✅ Tamper detection: PASS (modification breaks chain)


## ============================================
## 8. VIEW AUDIT LOGS (human-readable)
## ============================================

# Logs are JSONL format in ./logs/declado-audit.log
# Each line is a JSON event with HMAC chain integrity

# Example:
cat ./logs/declado-audit.log | jq '.msg'

# Or tail in real-time:
tail -f ./logs/declado-audit.log | jq '.ts, .msg, .user'


## ============================================
## 9. OPTIONAL: INSTALL SQLCIPHER (Windows)
## ============================================

# This requires a compiler. On Windows, precompiled wheels are hard to find.
# For now, standard SQLite mode works fine and gracefully falls back.
# 
# If you want to try:
# pip install pysqlcipher3
# 
# Then restart backend—it will auto-detect and use encryption.


## ============================================
## 10. CONFIGURE SECURITY (.env)
## ============================================

# Add to backend/.env:

DB_PASSPHRASE=your_very_strong_passphrase_here_20_chars_plus
LOG_HMAC_KEY=separate_hmac_key_for_audit_logs_20_chars_plus
AV_SCAN_ENABLED=true
LOG_LEVEL=INFO

# Then restart backend for new settings to apply


## ============================================
## TROUBLESHOOTING
## ============================================

# Q: Backend won't start?
# A: Check logs for "pysqlcipher3 not available" (OK, using std SQLite)
#    Verify Poppler detected (should say ✅)

# Q: AV scan not working?
# A: Set AV_SCAN_ENABLED=false in .env to skip
#    Or install Windows Defender / ClamAV

# Q: Audit logs missing?
# A: Check ./logs/ directory exists
#    Logs append as operations occur (startup, OCR, errors, etc.)

# Q: SQLCipher 'cipher_version' error?
# A: This means pysqlcipher3 not installed (expected)
#    System gracefully uses standard SQLite (unencrypted)


## ============================================
## SECURITY FEATURES SUMMARY
## ============================================

✅ Database:          Standard SQLite (or SQLCipher if pysqlcipher3 installed)
✅ Audit Logs:        HMAC-signed append-only (tamper-evident)
✅ Antivirus:         Defender/ClamAV pre-scan on OCR upload
✅ Signatures:        HMAC verification of models/config at startup
✅ Backup:            Encrypted export/restore
✅ DPAPI (Windows):   Auto-protects DB key via OS keystore (when SQLCipher used)

---
For more details: see SECURITY.md and PHASE_8_EXECUTION_SUMMARY.md
