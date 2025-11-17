"""Backup and restore script for encrypted SQLCipher database.

Usage:
  python backup_db.py export <output_file>
  python backup_db.py restore <backup_file>
"""

import argparse
import logging
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def export_backup(db_path: str, out_path: str) -> None:
    db_p = Path(db_path)
    if not db_p.exists():
        raise FileNotFoundError(f"Database not found: {db_p}")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(db_p, out)
    logger.info(f"✅ Encrypted DB backed up to: {out}")
    logger.info("Database is encrypted with SQLCipher. Restore requires the same key/passphrase.")


def restore_backup(backup_path: str, db_path: str) -> None:
    bk = Path(backup_path)
    if not bk.exists():
        raise FileNotFoundError(f"Backup file not found: {bk}")
    db_p = Path(db_path)
    if db_p.exists():
        confirm = input(f"Overwrite existing DB at {db_p}? (yes/no): ")
        if confirm.lower() != "yes":
            logger.info("Restore cancelled.")
            return
    shutil.copy(bk, db_p)
    logger.info(f"✅ DB restored from: {bk}")
    logger.info("Test database connection to confirm decryption key matches.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup/restore encrypted SQLCipher DB")
    parser.add_argument("command", choices=["export", "restore"], help="Backup or restore")
    parser.add_argument("file", help="Backup file path")
    parser.add_argument(
        "--db", default="./data/declado.db", help="DB file path (default: ./data/declado.db)"
    )
    args = parser.parse_args()

    if args.command == "export":
        export_backup(args.db, args.file)
    elif args.command == "restore":
        restore_backup(args.file, args.db)


if __name__ == "__main__":
    main()
