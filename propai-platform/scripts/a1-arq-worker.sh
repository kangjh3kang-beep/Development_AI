#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# a1-arq-worker.sh — arq 워커를 현재 propai-api 이미지에 정렬한다(멱등).
#
# ★왜 필요한가: 백엔드 배포(~/deploy.sh)는 API 컨테이너만 블루-그린으로 교체하고
#   arq 워커(propai-arq-worker)는 건드리지 않는다. 구앱 제거 루프도 '^propai-api'
#   패턴이라 arq 는 대상이 아니다. 그래서 배포할 때마다 워커만 **구 이미지에 남는다**.
#
#   이게 위험한 이유: 컨테이너는 계속 Up 이라 헬스체크로 잡히지 않는다. 워커가 조용히
#   옛 코드로 잡을 처리하고, 배포한 수정이 백그라운드 경로에만 반영되지 않는 상태가
#   된다(무성 회귀). 2026-08-01~02 배포에서 4회 연속 재현됐고 매번 수동 재생성했다.
#   ★탐지 수단은 컨테이너 나이가 아니라 **이미지 ID 대조**뿐이다.
#
# 사용법: bash scripts/a1-arq-worker.sh
#   환경변수: PROPAI_API_IMAGE(기본 propai-api:latest) · ARQ_WORKER_NAME · ARQ_WORKER_CMD
#            REPO_DIR · DOCKER_BIN · ARQ_HEALTH_WAIT(초)
#
# 종료코드: 0=정렬됨(재생성했거나 이미 최신) · 1=실패(이미지 없음/기동 실패/ID 불일치)
# ════════════════════════════════════════════════════════════════
set -uo pipefail

REPO_DIR="${REPO_DIR:-$HOME/Development_AI/propai-platform}"
IMAGE="${PROPAI_API_IMAGE:-propai-api:latest}"
DOCKER_BIN="${DOCKER_BIN:-docker}"
ARQ_NAME="${ARQ_WORKER_NAME:-propai-arq-worker}"
ARQ_SETTINGS="${ARQ_WORKER_SETTINGS:-apps.worker.main.WorkerSettings}"
ARQ_CMD="${ARQ_WORKER_CMD:-arq $ARQ_SETTINGS}"
ARQ_RESTART="${ARQ_RESTART_POLICY:-unless-stopped}"
HEALTH_WAIT="${ARQ_HEALTH_WAIT:-40}"
# ★워커에 맞는 헬스체크로 덮어쓴다 (2026-08-12).
#   워커는 API 이미지(propai-api)로 뜨는데 그 이미지의 HEALTHCHECK 는
#   `curl -f http://localhost:8000/health` 다. 워커는 HTTP 서버가 아니라 **영원히 실패**한다.
#   실제로 3일 내내 unhealthy 였고(로그의 cron 은 정상 실행 중이었다), 그래서
#   **진짜 워커 장애가 나도 같은 화면**이 된다 — 감시가 마비된 상태였다.
#   `arq --check` 는 워커가 Redis 에 쓴 health 키를 읽으므로 실제 대상을 태운다.
#   ★단, 이 신호가 유효하려면 WorkerSettings.health_check_interval 이 **적당해야** 한다
#     (키 TTL = interval + 1). 경계는 **양방향**이다:
#       · 너무 길면(기본 3600) 죽은 워커가 1시간 초록이다.
#       · 너무 짧으면(60) 루프를 막는 정상 작업(모델 재학습·대용량 IFC) 중에
#         **일하는 워커가 빨개진다** — 위양성의 형태만 바뀐다.
#     그래서 300 으로 뒀다(main.py 에 근거 상세). 탐지까지는 TTL 301초 + 연속
#     실패 3회(60초 간격) ⇒ 최선 약 7분 · 최악 약 8분이다.
ARQ_HEALTH_CMD="${ARQ_HEALTH_CMD:-arq --check $ARQ_SETTINGS}"
ARQ_HEALTH_INTERVAL="${ARQ_HEALTH_INTERVAL:-60s}"
ARQ_HEALTH_TIMEOUT="${ARQ_HEALTH_TIMEOUT:-15s}"
ARQ_HEALTH_RETRIES="${ARQ_HEALTH_RETRIES:-3}"
# 기동 직후 health 키가 아직 없을 수 있다 — 실측상 기동 1초 뒤 기록되지만 여유를 둔다.
ARQ_HEALTH_START="${ARQ_HEALTH_START:-90s}"
ENV_FILE="$REPO_DIR/.env"

log() { echo "[arq] $1"; }

# 이미지 ID를 짧게 — 로그 대조용(전체 sha256 은 길어 눈으로 못 본다).
short() { printf '%s' "${1#sha256:}" | cut -c1-12; }

if [ ! -f "$ENV_FILE" ]; then
  log "ERROR: .env 없음 — $ENV_FILE"; exit 1
fi

LATEST_ID=$("$DOCKER_BIN" image inspect "$IMAGE" --format '{{.Id}}' 2>/dev/null || true)
if [ -z "$LATEST_ID" ]; then
  log "ERROR: 이미지 없음 — $IMAGE"; exit 1
fi

# 컨테이너가 없으면 CUR_ID 는 빈 값 → 아래 비교에서 자동으로 '재생성' 분기를 탄다.
CUR_ID=$("$DOCKER_BIN" inspect "$ARQ_NAME" --format '{{.Image}}' 2>/dev/null || true)

if [ -n "$CUR_ID" ] && [ "$CUR_ID" = "$LATEST_ID" ]; then
  log "이미 최신 — 재생성 불요 (image=$(short "$LATEST_ID"))"
  exit 0
fi

if [ -z "$CUR_ID" ]; then
  log "워커 컨테이너 없음 → 신규 기동 (image=$(short "$LATEST_ID"))"
else
  log "이미지 드리프트 감지: 워커=$(short "$CUR_ID") vs 최신=$(short "$LATEST_ID") → 재생성"
fi

"$DOCKER_BIN" rm -f "$ARQ_NAME" >/dev/null 2>&1 || true

# shellcheck disable=SC2086  # ARQ_CMD 는 의도적으로 분리(명령+인자)
if ! "$DOCKER_BIN" run -d \
      --name "$ARQ_NAME" \
      --restart "$ARQ_RESTART" \
      --env-file "$ENV_FILE" \
      --health-cmd "$ARQ_HEALTH_CMD" \
      --health-interval "$ARQ_HEALTH_INTERVAL" \
      --health-timeout "$ARQ_HEALTH_TIMEOUT" \
      --health-retries "$ARQ_HEALTH_RETRIES" \
      --health-start-period "$ARQ_HEALTH_START" \
      "$IMAGE" $ARQ_CMD >/dev/null; then
  log "ERROR: 워커 기동 실패"; exit 1
fi

# 기동 확인: 컨테이너가 살아있고 워커가 함수 등록을 마쳤는지 로그로 본다.
#   (컨테이너 Up 만으로는 부족 — 이 결함 자체가 'Up 인데 옛 코드'였다.)
ready=0
for _ in $(seq 1 "$HEALTH_WAIT"); do
  state=$("$DOCKER_BIN" inspect "$ARQ_NAME" --format '{{.State.Running}}' 2>/dev/null || echo false)
  if [ "$state" = "true" ] && "$DOCKER_BIN" logs "$ARQ_NAME" 2>&1 | grep -q "Starting worker for"; then
    ready=1; break
  fi
  sleep 1
done

NEW_ID=$("$DOCKER_BIN" inspect "$ARQ_NAME" --format '{{.Image}}' 2>/dev/null || true)
if [ "$NEW_ID" != "$LATEST_ID" ]; then
  log "ERROR: 재생성 후에도 이미지 불일치 — 워커=$(short "$NEW_ID") 최신=$(short "$LATEST_ID")"; exit 1
fi

if [ "$ready" != "1" ]; then
  log "ERROR: ${HEALTH_WAIT}초 내 워커 기동 확인 실패(함수 등록 로그 없음)"
  "$DOCKER_BIN" logs "$ARQ_NAME" 2>&1 | tail -5
  exit 1
fi

FUNCS=$("$DOCKER_BIN" logs "$ARQ_NAME" 2>&1 | grep -oE "Starting worker for [0-9]+ functions" | tail -1)
log "재생성 완료 — image=$(short "$LATEST_ID") · ${FUNCS:-기동 확인됨}"
exit 0
