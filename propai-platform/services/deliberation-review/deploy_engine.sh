#!/usr/bin/env bash
# PropAI 심의분석 엔진 — 프로덕션 배포/마이그레이션(멱등·재실행 안전).
# 단계: 빌드+기동 → DB healthy 대기 → alembic upgrade head(엔진 컨테이너 내부) → 엔진 기동 → /health 확인.
# 사용: ./deploy_engine.sh           (빌드 포함 전체 배포)
#       SKIP_BUILD=1 ./deploy_engine.sh   (재빌드 없이 마이그레이션+헬스만)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

COMPOSE_FILE="docker-compose.prod.yml"
DB_SVC="deliberation-db"
ENGINE_SVC="deliberation-engine"
HEALTH_URL="http://localhost:8801/health"

# docker compose v2(plugin) 우선, 없으면 docker-compose v1 폴백.
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "[deploy] ✗ docker compose 미설치" >&2; exit 2
fi
DC="$DC -f $COMPOSE_FILE"

# .env.prod 가 있으면 compose 가 자동 참조하도록 안내(compose 는 같은 디렉토리 .env 를 읽음).
if [ -f "$REPO/.env.prod" ] && [ ! -f "$REPO/.env" ]; then
  echo "[deploy] ℹ .env.prod 발견 — compose 변수 주입을 위해 --env-file 사용"
  DC="$DC --env-file .env.prod"
fi

echo "[deploy] 1/5 DB 기동(멱등)"
$DC up -d "$DB_SVC"

echo "[deploy] 2/5 DB healthy 대기"
for i in $(seq 1 60); do
  status="$($DC ps --format '{{.Health}}' "$DB_SVC" 2>/dev/null || true)"
  # 일부 compose 버전은 위 포맷 미지원 → inspect 폴백.
  if [ -z "$status" ]; then
    cid="$($DC ps -q "$DB_SVC" 2>/dev/null || true)"
    [ -n "$cid" ] && status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || true)"
  fi
  if [ "$status" = "healthy" ]; then echo "[deploy]   DB healthy"; break; fi
  if [ "$i" = "60" ]; then echo "[deploy] ✗ DB healthy 대기 타임아웃" >&2; exit 3; fi
  sleep 2
done

echo "[deploy] 3/5 엔진 이미지 빌드+기동(멱등)"
if [ "${SKIP_BUILD:-0}" = "1" ]; then
  $DC up -d "$ENGINE_SVC"
else
  $DC up -d --build "$ENGINE_SVC"
fi

echo "[deploy] 4/5 alembic upgrade head(엔진 컨테이너 내부 · 멱등)"
# ★cwd=/app 강제 + config 명시: alembic.ini 의 script_location=apps/api/alembic·
#   prepend_sys_path=apps/api 는 repo-root(/app) 상대 경로다. 그런데 Dockerfile 최종
#   WORKDIR 은 /app/apps/api 라, exec 가 그 cwd 에서 돌면 apps/api/apps/api/alembic 로
#   어긋나 "Path doesn't exist: apps/api/alembic" 로 실패한다. -w /app 으로 repo-root 에서
#   실행하면 경로가 /app/apps/api/alembic 로 정합. alembic 은 적용분 건너뛰므로 재실행 안전.
$DC exec -T -w /app "$ENGINE_SVC" alembic -c apps/api/alembic.ini upgrade head

echo "[deploy] 5/5 /health 확인"
ok=0
for i in $(seq 1 30); do
  # 호스트에 curl 있으면 사용, 없으면 컨테이너 내부 python 점검.
  if command -v curl >/dev/null 2>&1; then
    code="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)"
    [ "$code" = "200" ] && ok=1 && break
  else
    if $DC exec -T "$ENGINE_SVC" python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8801/health',timeout=3).status==200 else 1)" >/dev/null 2>&1; then
      ok=1; break
    fi
  fi
  sleep 2
done

if [ "$ok" = "1" ]; then
  echo "[deploy] ✓ 엔진 정상 — $HEALTH_URL → 200 {\"status\":\"ok\"}"
  echo "[deploy]   다음(선택): /api/v1/doctor 로 어댑터 live 상태 확인."
else
  echo "[deploy] ✗ /health 200 미확인 — 로그: $DC logs --tail=80 $ENGINE_SVC" >&2
  exit 4
fi
