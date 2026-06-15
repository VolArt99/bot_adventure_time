#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
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

docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUTPUT"

find "$BACKUP_DIR" -name "*.sql.gz" -mtime +14 -delete
echo "Backup saved to $OUTPUT"
