# Localization inventory

Updated: 2026-11-09.

## Current behavior

- The frontend is Russian-only. React components use Russian labels directly; no locale switcher or Uzbek locale tags remain in `app/`, `components/`, or `lib/`.
- `lib/i18n.tsx` retains only the Russian locale and an identity helper for compatibility.
- The former translations admin page and locale helper were removed.
- Reference API responses use Russian names. Translation tables and Russian translation endpoints remain in the backend for canonical reference-name handling.
- Locale selection in the backend resolves to Russian, regardless of the requested locale.

## Database migration

`backend/alembic/versions/0025_russian_only_locales.py` deletes non-Russian rows from the translation tables and constrains those tables to `ru`. This deletion is irreversible after the migration; the migration has not been executed or tested against a database.

`postgres/schema.sql` also describes the Russian-only locale constraint for a fresh schema. Existing databases must use the forward Alembic migration rather than editing applied migrations.

## Not verified

- Database migration upgrade/downgrade and existing Russian translation coverage.
- Backend tests, API E2E, browser behavior, and production deployment.
