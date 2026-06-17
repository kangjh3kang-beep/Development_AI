#!/bin/bash
# 심의분석 엔진 — Celery worker 상시 기동(진짜 비동기). redis broker 필요.
# 운영: systemd 또는 supervisor로 이 스크립트를 상시 실행(docs/OPS_DEPLOYMENT.md 참고).
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO/apps/api"
export CELERY_TASK_ALWAYS_EAGER=false   # 진짜 비동기(eager 폴백 해제)
cd "$REPO/apps/api" || exit 9
exec "$REPO/.venv/bin/celery" -A app.tasks.celery_app worker \
  --loglevel="${CELERY_LOGLEVEL:-info}" --concurrency="${CELERY_CONCURRENCY:-2}"
