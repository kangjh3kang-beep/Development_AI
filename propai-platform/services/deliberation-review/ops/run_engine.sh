#!/bin/bash
# 심의분석 엔진 — FastAPI(uvicorn) 상시 기동. .env + .env.secrets(export_scoped_secrets) 자동 로드.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO/apps/api"
cd "$REPO/apps/api" || exit 9
exec "$REPO/.venv/bin/python" -m uvicorn app.main:app \
  --host "${ENGINE_HOST:-127.0.0.1}" --port "${ENGINE_PORT:-8801}" --workers "${ENGINE_WORKERS:-1}"
