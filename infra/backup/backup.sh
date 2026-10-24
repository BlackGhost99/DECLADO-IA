#!/bin/sh
# Point-in-time PostgreSQL snapshot + immutable documents stored together in an
# encrypted restic snapshot. Always verify restoration separately.
set -eu
umask 077
: "${RESTIC_REPOSITORY:?restic repository required}"
: "${PRIVATE_STORAGE_ROOT:?private files path required}"
: "${PGHOST:?database hostname required}"
if [ -z "${RESTIC_PASSWORD:-}" ] && [ -z "${RESTIC_PASSWORD_FILE:-}" ]; then
  echo "Missing restic repository encryption password" >&2
  exit 2
fi
case "$RESTIC_REPOSITORY" in
  s3:*|sftp:*|rest:*|rclone:*|b2:*|azure:*|gs:*|swift:*) ;;
  *) if [ "${BACKUP_ALLOW_LOCAL:-false}" != "true" ]; then
       echo "Production backup requires an off-site repository" >&2
       exit 2
     fi ;;
esac
if [ ! -d "$PRIVATE_STORAGE_ROOT" ]; then
  echo "Private file volume not mounted" >&2
  exit 2
fi

staging="${BACKUP_STAGING_DIR:-/tmp/clairtransit-backup}"
mkdir -p "$staging"
chmod 0700 "$staging"
if ! mkdir "$staging/.backup-lock" 2>/dev/null; then
  echo "Backup already running" >&2
  exit 3
fi
cleanup() {
  rm -f "$staging/clairtransit.dump"
  rmdir "$staging/.backup-lock" || true
}
trap cleanup EXIT HUP INT TERM

pg_dump --format=custom --file="$staging/clairtransit.dump"
chmod 0600 "$staging/clairtransit.dump"
restic snapshots --json >/dev/null 2>&1 || restic init
restic backup --tag clairtransit --exclude "$PRIVATE_STORAGE_ROOT/quarantine" --one-file-system \
  "$staging/clairtransit.dump" "$PRIVATE_STORAGE_ROOT"
# Deletions require an explicit retention policy and validated off-site storage.
restic forget --tag clairtransit --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
echo "ClairTransit encrypted backup complete"
