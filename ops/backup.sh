#!/bin/sh
# Daily Postgres backups: one when the stack starts, then whenever the newest is a day old.
# Keeps BACKUP_KEEP_DAYS days of gzipped dumps in /backups.
#
# Checked hourly against the files' age rather than with one "sleep 86400": on a laptop or a
# Windows/macOS Docker host the machine sleeps, and sleep only counts awake time.
set -eu
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

backup() {
  file="/backups/smartfin-$(date +%Y%m%d-%H%M).sql.gz"
  if pg_dump --clean --if-exists --no-owner -h db -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$file.tmp"; then
    mv "$file.tmp" "$file"
    echo "backup: wrote $file"
  else
    rm -f "$file.tmp"
    echo "backup: FAILED" >&2
  fi
  find /backups -name 'smartfin-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
}

backup
while true; do
  sleep 3600
  # Nothing written in the last 24 hours (23h50m, so it doesn't drift later each day)
  if [ -z "$(find /backups -name 'smartfin-*.sql.gz' -mmin -1430)" ]; then
    backup
  fi
done
