#!/bin/sh
# Nightly PostgreSQL backups, run by the `backup` service of docker-compose.yml (no cron on the host needed).
#   - a verified custom-format dump at BACKUP_HOUR_UTC every day (default 21:00 UTC = 02:00 Tashkent)
#   - one more right at start when the newest automatic dump is older than 20 hours (the host was off)
#   - only its own files (auto-*.dump) are pruned after BACKUP_RETENTION_DAYS; manual dumps are never touched
# Connection comes from the standard PG* variables of the compose file; nothing is printed except file names/sizes.
set -u
umask 077
DIR=/backups
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
HOUR="${BACKUP_HOUR_UTC:-21}"
MIN_FREE_KB=1048576

backup_once() {
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  tmp="$DIR/.auto-$stamp.tmp"
  final="$DIR/auto-$stamp.dump"
  free_kb="$(df -k "$DIR" | awk 'NR==2 {print $4}')"
  if [ "${free_kb:-0}" -lt "$MIN_FREE_KB" ]; then
    echo "backup: SKIPPED, less than 1 GB free in $DIR" >&2
    return 1
  fi
  if ! pg_dump --format=custom --no-owner --file="$tmp"; then
    echo "backup: pg_dump FAILED" >&2
    rm -f "$tmp"
    return 1
  fi
  # a dump that cannot be listed is not a backup
  if ! pg_restore --list "$tmp" > /dev/null 2>&1; then
    echo "backup: verification FAILED, dump removed" >&2
    rm -f "$tmp"
    return 1
  fi
  mv "$tmp" "$final"
  size="$(wc -c < "$final")"
  echo "backup: created $(basename "$final") ($size bytes)"
  printf '%s %s\n' "$stamp" "$size" > "$DIR/.last_auto_backup"
  find "$DIR" -maxdepth 1 -type f -name 'auto-*.dump' -mtime "+$RETENTION_DAYS" -print -delete | sed 's/^/backup: pruned /'
  return 0
}

mkdir -p "$DIR"
case "$HOUR" in ''|*[!0-9]*) echo "BACKUP_HOUR_UTC must be 0-23" >&2; exit 2 ;; esac
case "$RETENTION_DAYS" in ''|*[!0-9]*) echo "BACKUP_RETENTION_DAYS must be a number" >&2; exit 2 ;; esac

# wait for the database, then catch up if the last automatic dump is old
until pg_isready -q; do sleep 3; done
if [ -z "$(find "$DIR" -maxdepth 1 -type f -name 'auto-*.dump' -mmin -1200 2>/dev/null | head -n 1)" ]; then
  echo "backup: no automatic dump in the last 20 hours, taking one now"
  backup_once || true
fi

while true; do
  now="$(date -u +%s)"
  delay=$(( (HOUR * 3600 - now % 86400 + 86400) % 86400 ))
  [ "$delay" -lt 60 ] && delay=60   # never twice within a minute around the target
  echo "backup: next run in $delay seconds"
  sleep "$delay"
  backup_once || true
done
