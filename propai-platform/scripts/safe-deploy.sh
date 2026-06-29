#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# safe-deploy.sh — PropAI A1 단독배포자용 "안전 배포" 스크립트
#
# 이번 세션의 장애 원인들을 구조적으로 차단한다:
#   1) 동시배포 충돌      → 배포 락(lock)으로 한 번에 하나만 실행
#   2) docker system prune-af 가 빌드 죽임 → 이 스크립트는 prune 안 함
#   3) compose v1 'ContainerConfig' 버그 → 옛 컨테이너 선제거 후 생성
#   4) api 컨테이너 네트워크 유실 → 재생성 후 네트워크 멤버십 강제 보장
#   5) nginx 가 옛 컨테이너 IP 캐시 → 재생성 후 nginx 재시작
#   6) 새 이미지가 안 뜨는 사고 → 헬스 검증 실패 시 옛 이미지로 자동 롤백
#
# 사용법(A1에서):  bash propai-platform/scripts/safe-deploy.sh [web|api|both] [git-ref]
# 상태는 /tmp/deploy_status.txt, 상세로그는 /tmp/deploy.log 에 기록.
# 권장 실행: setsid bash .../safe-deploy.sh both </dev/null >/dev/null 2>&1 &  (분리 실행)
# ════════════════════════════════════════════════════════════════
set -uo pipefail

TARGET="${1:-web}"                 # web | api | both
DEPLOY_REF="${2:-${DEPLOY_REF:-main}}"
REPO="$HOME/Development_AI"
COMPOSE_DIR="$REPO/propai-platform"
NET_PRIMARY="propai-platform_propai-network"
NET_FALLBACK="propai-platform-propai-network"
LOCKDIR="/tmp/propai_deploy.lock"
STATUS="/tmp/deploy_status.txt"
LOG="/tmp/deploy.log"
HEALTH_TIMEOUT=90                  # 새 컨테이너 헬스 대기 최대 초
VERIFY_BASE_URL="${VERIFY_BASE_URL:-http://localhost:80}"
VERIFY_BASE_URL="${VERIFY_BASE_URL%/}"

ts() { date -u +%H:%M:%S; }
status() { echo "$1 $(ts)" > "$STATUS"; }
log() { echo "[$(ts)] $1" >> "$LOG"; }
compose() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}
container_name() {
  local svc=$1
  local name
  for name in "propai-platform_${svc}_1" "propai-platform-${svc}-1"; do
    if docker inspect "$name" >/dev/null 2>&1; then
      echo "$name"
      return 0
    fi
  done
  echo "propai-platform_${svc}_1"
}
network_name() {
  local name
  for name in "$NET_PRIMARY" "$NET_FALLBACK"; do
    if docker network inspect "$name" >/dev/null 2>&1; then
      echo "$name"
      return 0
    fi
  done
  echo "$NET_PRIMARY"
}

# ── 0) 동시배포 방지 락 (원자적 mkdir) ──
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "ABORT: 다른 배포가 진행중입니다($LOCKDIR). 끝나면 재시도." > "$STATUS"; exit 9
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT
: > "$LOG"

# ── 1) 프리플라이트 ──
status "PREFLIGHT"
# 다른 빌드/prune 동시 진행 차단
if pgrep -f "docker system prune|builder prune" >/dev/null; then
  status "ABORT prune-진행중 — 잠시 후 재시도"; exit 8
fi
# 디스크 여유(85% 미만)
USEPCT=$(df -P / | awk 'NR==2{gsub("%","",$5); print $5}')
if [ "${USEPCT:-0}" -ge 90 ]; then status "ABORT 디스크부족 ${USEPCT}%"; exit 7; fi
# git clean(런타임 qdrant 제외)
cd "$REPO" || { status "FAIL cd-repo"; exit 1; }
if [ -n "$(git status --porcelain | grep -v qdrant_storage)" ]; then
  status "ABORT git-dirty(다른 창 미커밋 보호)"; exit 6
fi

# ── 2) git 동기화 ──
status "SYNC"
git fetch origin "$DEPLOY_REF" >>"$LOG" 2>&1 || { status "FAIL fetch-$DEPLOY_REF"; exit 1; }
git reset --hard FETCH_HEAD >>"$LOG" 2>&1 || { status "FAIL reset"; exit 1; }
HEAD=$(git log --oneline -1)
log "DEPLOY_REF = $DEPLOY_REF"
log "HEAD = $HEAD"

# ── 3) 빌드 (prune 없이, legacy builder로 ContainerConfig 보장) ──
cd "$COMPOSE_DIR" || { status "FAIL cd-compose"; exit 1; }
build_one() {
  local svc=$1
  status "BUILD $svc @ $HEAD"
  DOCKER_BUILDKIT=0 compose build "$svc" >>"$LOG" 2>&1 || { status "FAIL build-$svc"; return 1; }
}
case "$TARGET" in
  web)  build_one web  || exit 1 ;;
  api)  build_one api  || exit 1 ;;
  both) build_one api  || exit 1; build_one web || exit 1 ;;
  *) status "FAIL unknown-target:$TARGET"; exit 1 ;;
esac

# ── 4) 헬스게이트 재생성 + 자동 롤백 ──
# 새 이미지로 컨테이너 교체. 헬스 실패 시 옛 이미지로 롤백.
container_image() { docker inspect "$(container_name "$1")" --format '{{.Image}}' 2>/dev/null; }
ensure_network() {
  local svc=$1 cname net
  cname=$(container_name "$svc")
  net=$(network_name)
  if ! docker inspect "$cname" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null | grep -q "$net"; then
    docker network connect --alias "$svc" "$net" "$cname" >>"$LOG" 2>&1 || true
    log "[$svc] 네트워크 강제 연결 → $net"
  fi
}
wait_running() {
  local cname t=0
  cname=$(container_name "$1")
  while [ $t -lt "$HEALTH_TIMEOUT" ]; do
    local st; st=$(docker inspect "$cname" --format '{{.State.Status}}' 2>/dev/null || echo none)
    local hs; hs=$(docker inspect "$cname" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null || echo none)
    [ "$st" = "running" ] && { [ "$hs" = "healthy" ] || [ "$hs" = "none" ]; } && return 0
    [ "$st" = "exited" ] && return 1
    sleep 4; t=$((t+4))
  done
  return 1
}
rollback_one() {
  local svc=$1 img=$2 cname
  cname=$(container_name "$svc")
  log "[$svc] 롤백 시작 → $img"
  docker stop "$cname" 2>/dev/null; docker rm "$cname" 2>/dev/null
  docker tag "$img" "propai-${svc}:oracle" >>"$LOG" 2>&1
  compose up -d --no-deps --no-build "$svc" >>"$LOG" 2>&1
  ensure_network "$svc"
}
recreate_one() {
  local svc=$1 cname
  cname=$(container_name "$svc")
  local rb; rb=$(container_image "$svc")        # 롤백용 현재 이미지
  log "[$svc] rollback-image=$rb"
  status "RECREATE $svc"
  docker stop "$cname" 2>/dev/null; docker rm "$cname" 2>/dev/null   # 옛 컨테이너 선제거(버그 우회)
  if ! compose up -d --no-deps --no-build "$svc" >>"$LOG" 2>&1; then
    [ -n "$rb" ] && rollback_one "$svc" "$rb"; status "FAIL up-$svc(롤백함)"; return 1
  fi
  ensure_network "$svc"
  if ! wait_running "$svc"; then
    [ -n "$rb" ] && rollback_one "$svc" "$rb"; status "FAIL health-$svc(롤백함)"; return 1
  fi
  log "[$svc] 재생성 OK"
}
case "$TARGET" in
  web)  recreate_one web  || exit 1 ;;
  api)  recreate_one api  || exit 1 ;;
  both) recreate_one api  || exit 1; recreate_one web || exit 1 ;;
esac

# ── 5) 네트워크 전수 보장 + nginx 재시작(새 IP 재인식) ──
status "NGINX-RELOAD"
for s in api web; do ensure_network "$s"; done
docker restart "$(container_name nginx)" >>"$LOG" 2>&1
sleep 8

# ── 6) 공개 검증 ──
status "VERIFY"
WEB=$(curl -s -o /dev/null -w "%{http_code}" "$VERIFY_BASE_URL/ko" --max-time 15)
API=$(curl -s -o /dev/null -w "%{http_code}" "$VERIFY_BASE_URL/health" --max-time 15)
# 검증 실패(502 등)면 nginx 한 번 더 재시작 후 재확인
if [ "$WEB" != "200" ] || [ "$API" != "200" ]; then
  log "1차 검증 실패(web=$WEB api=$API) → nginx 재시작 재시도"
  docker restart "$(container_name nginx)" >>"$LOG" 2>&1; sleep 8
  WEB=$(curl -s -o /dev/null -w "%{http_code}" "$VERIFY_BASE_URL/ko" --max-time 15)
  API=$(curl -s -o /dev/null -w "%{http_code}" "$VERIFY_BASE_URL/health" --max-time 15)
fi
if [ "$WEB" = "200" ] && [ "$API" = "200" ]; then
  status "DONE web=$WEB api=$API @ $HEAD"
else
  status "WARN 검증미흡 web=$WEB api=$API — 수동확인 필요 @ $HEAD"
fi
