#!/usr/bin/env bash
# Wrapper docker compose — charge .env depuis la racine
# Usage: ./dc.sh up -d | ./dc.sh logs lm_celery -f | ./dc.sh ps
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec docker compose --env-file "$DIR/.env" -f "$DIR/docker/docker-compose.dev.yml" "$@"
