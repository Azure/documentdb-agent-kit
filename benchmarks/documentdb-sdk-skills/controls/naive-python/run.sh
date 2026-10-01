#!/usr/bin/env bash
set -euo pipefail
cd /app
exec uvicorn app:app --host 0.0.0.0 --port "${APP_PORT:-9080}"
