#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Create .env from .env.example first."
  exit 1
fi

docker compose pull postgres || true
docker compose build bot
docker compose up -d

echo "Deployment started. Check logs with: docker compose logs -f bot"
