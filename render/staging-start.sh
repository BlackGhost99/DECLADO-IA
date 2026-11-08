#!/bin/sh
set -eu
# Never run public staging with Django DEBUG enabled.
if [ "${DJANGO_DEBUG:-false}" = "true" ]; then
  echo "Refusing to run a public server with DJANGO_DEBUG=true" >&2
  exit 1
fi
python manage.py migrate --noinput
python manage.py seed_document_types
if [ "${STAGING_DATABASE_CACHE:-false}" = "true" ]; then
  python manage.py createcachetable clairtransit_staging_cache
fi
if [ "${STAGING_SEED_DEMO:-false}" = "true" ]; then
  if [ -z "${DEMO_PASSWORD:-}" ]; then
    echo "DEMO_PASSWORD must be set before seeding staging accounts" >&2
    exit 1
  fi
  # DEBUG is enabled for the CLI seed command only; public Gunicorn remains secure.
  DJANGO_DEBUG=true python manage.py seed_demo \
    --password "$DEMO_PASSWORD" --no-case --hide-password
fi
if [ "${STAGING_EMBEDDED_WORKER:-false}" = "true" ]; then
  celery -A config worker -B -l info --pool=solo --concurrency=1 &
fi
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-10000}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --timeout 180 \
  --access-logfile - \
  --error-logfile -
