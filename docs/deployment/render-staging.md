# DECLADO IA — Render staging mobile (2026-11-08)

This deploy retains the existing Django API and React interface and does
not replace the local Windows installation. Use Dockerfile.render, build
context ".", branch staging/render-mobile-test-20261108.
React and Django share one HTTPS origin; health endpoint: /api/v1/health.

## Required variables on the Render web service
- DJANGO_DEBUG=false
- DJANGO_SECRET_KEY: stable random key
- DJANGO_ALLOWED_HOSTS: web service hostname
- CSRF_TRUSTED_ORIGINS: HTTPS origin of the web service
- DATABASE_URL: separate staging database
- MFA_ENCRYPTION_KEY: stable Fernet encryption key
- MFA_ENFORCE=true
- AUTH_RATE_LIMIT_ENABLED=true
- CACHE_URL: dedicated Redis connection, never Gaboshop/YEM's data
- CELERY_BROKER_URL: dedicated Redis broker
- PRIVATE_STORAGE_ROOT: durable private volume or explicitly implemented
  shared private storage adapter. The current local storage is NOT S3.
- CLAMAV_HOST/CLAMAV_PORT: trustworthy *private* ClamAV daemon; never bypass
  the fail-closed scan and never expose the daemon publicly.
- STAGING_SEED_DEMO=true and DEMO_PASSWORD=unique random staging password
- STAGING_EMBEDDED_WORKER=true ONLY with sufficient memory and shared
  persistent storage. Eager mode on free instances is NOT worker parity.
- AI_PROVIDER=disabled by default; external AI requires an approved provider
  and secret, and only fictional documents should be used for early testing.

## End-to-end validation
Login/MFA; roles and isolation; cases; document upload; ClamAV; OCR in
FR/EN/ES/AR; Celery; invisible extraction and relationship graph; tariff
reference; tax calculations; validation; exports; archive; mobile layouts;
database + private-files backup and restoration.

## Limitations of the free test
Free web services are short-lived, have limited resources and ephemeral
files. ClamAV, Redis, background workers and durable documents cannot
be presumed functional until provisioned and tested. Do not upload any
actual commercial/client documentation in this test environment. Do not
report functional parity unless every relevant check passes.

## Super-administrateur staging
Provisionné par la commande `seed_staging_operator` au démarrage. Configurez
`STAGING_OPERATOR_EMAIL` et `STAGING_OPERATOR_PASSWORD` dans Render (Environment),
jamais dans le dépôt. Il a les droits exploitant et administrateur Django ;
les comptes des deux sociétés de démo utilisent un autre mot de passe,
`DEMO_PASSWORD`. MFA désactivée uniquement pour `APP_ENV=staging`.
