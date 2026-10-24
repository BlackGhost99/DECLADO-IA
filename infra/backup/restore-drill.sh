#!/bin/sh
# Always run in isolated infrastructure; never overwrite live files or database.
set -eu
umask 077
: "${RESTIC_REPOSITORY:?restic repository required}"
work="$(mktemp -d)"
cleanup() { rm -rf "$work"; }
trap cleanup EXIT HUP INT TERM
restic check
restic restore latest --tag clairtransit --target "$work"
dump="$(find "$work" -name clairtransit.dump -type f -print -quit)"
if [ -z "$dump" ]; then
  echo "No database dump found in the restored snapshot" >&2
  exit 4
fi
pg_restore --list "$dump" >/dev/null
if [ "${BACKUP_DRILL_RESTORE_DATABASE:-false}" = "true" ]; then
  : "${PGHOST:?restore database host required}"
  database="clairtransit_restore_drill_$$"
  # Never run this in a live production database cluster.
  createdb "$database"
  trap 'dropdb --if-exists "$database"; cleanup' EXIT
  pg_restore --exit-on-error --no-owner --no-acl --dbname="$database" "$dump"
  psql --dbname="$database" -Atc "SELECT count(*) FROM django_migrations" | grep -Eq '^[1-9][0-9]*$'
fi
echo "Encrypted restore drill complete; repository integrity and database archive verified"
