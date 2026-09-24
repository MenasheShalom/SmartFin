#!/bin/sh
# Nightly-ish Postgres backups: one when the stack starts, then every 24 hours.
# Keeps BACKUP_KEEP_DAYS days of gzipped dumps in /backups.
set -eu
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
while true; do
  file="/backups/smartfin-$(date +%Y%m%d-%H%M).sql.gz"
  if pg_dump --clean --if-exists --no-owner -h db -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$file.tmp"; then
    mv "$file.tmp" "$file"
    echo "backup: wrote $file"
  else
    rm -f "$file.tmp"
    echo "backup: FAILED" >&2
  fi
  find /backups -name 'smartfin-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
  sleep 86400
done
