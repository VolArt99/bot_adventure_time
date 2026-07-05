#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "Missing .env"
  exit 1
fi

set -a
source "$ROOT_DIR/.env"
set +a

: "${POSTGRES_USER:=bot}"
: "${POSTGRES_DB:=adventure_time}"
: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}"

OUTPUT="$BACKUP_DIR/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"
CHECKSUM="$OUTPUT.sha256"
LOG_FILE="${BACKUP_LOG_FILE:-$BACKUP_DIR/backup.log}"

{
  echo "[$TIMESTAMP] backup started"
  docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T postgres \
    pg_dump --clean --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUTPUT"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$OUTPUT" > "$CHECKSUM"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$OUTPUT" > "$CHECKSUM"
  fi
  find "$BACKUP_DIR" -name "*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
  find "$BACKUP_DIR" -name "*.sql.gz.sha256" -mtime +"$RETENTION_DAYS" -delete
  echo "[$TIMESTAMP] backup saved to $OUTPUT"
} >>"$LOG_FILE" 2>&1

echo "Backup saved to $OUTPUT"
echo "Log: $LOG_FILE"
