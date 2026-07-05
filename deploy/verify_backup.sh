#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <path-to-backup.sql.gz>"
  exit 1
fi

BACKUP_FILE="$1"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "FAIL: backup missing"
  exit 1
fi

if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
  echo "FAIL: gzip integrity check failed"
  exit 1
fi

if [[ -f "$CHECKSUM_FILE" ]]; then
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c "$CHECKSUM_FILE"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -c "$CHECKSUM_FILE"
  else
    echo "WARN: checksum file present but sha256sum/shasum not found"
  fi
else
  echo "WARN: checksum file missing, only gzip test performed"
fi

echo "OK: backup looks valid"
