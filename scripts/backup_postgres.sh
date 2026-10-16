#!/usr/bin/env bash
set -euo pipefail

backup_dir="${BACKUP_DIR:-./backups}"
retention_days="${BACKUP_RETENTION_DAYS:-14}"

if [[ ! "$retention_days" =~ ^[0-9]+$ ]] || (( retention_days < 1 )); then
  echo "BACKUP_RETENTION_DAYS must be a positive integer" >&2
  exit 2
fi

mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="$backup_dir/toir-$timestamp.dump"
temporary_file="$(mktemp "$backup_dir/.toir-$timestamp.XXXXXX")"
trap 'rm -f "$temporary_file"' EXIT

docker compose exec -T postgres sh -ec \
  'pg_dump --format=custom --no-owner --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  > "$temporary_file"
mv "$temporary_file" "$backup_file"
find "$backup_dir" -maxdepth 1 -type f -name 'toir-*.dump' \
  -mtime "+$retention_days" -delete
printf 'Created PostgreSQL backup: %s\n' "$backup_file"
