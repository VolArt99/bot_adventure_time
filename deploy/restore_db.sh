#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <path-to-backup.sql.gz>"
  echo "Example: $0 ./backups/adventure_time_20260705_120000.sql.gz"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_FILE="$1"

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Backup file not found: $BACKUP_FILE"
  exit 1
fi

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

read -r -p "Restore $POSTGRES_DB from $BACKUP_FILE? This overwrites current data. [y/N] " confirm
if [[ "${confirm,,}" != "y" ]]; then
  echo "Cancelled"
  exit 0
fi

echo "Stopping bot container..."
docker compose -f "$ROOT_DIR/docker-compose.yml" stop bot

echo "Restoring database..."
gunzip -c "$BACKUP_FILE" | docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1

echo "Starting bot container..."
docker compose -f "$ROOT_DIR/docker-compose.yml" start bot

echo "Restore completed"
