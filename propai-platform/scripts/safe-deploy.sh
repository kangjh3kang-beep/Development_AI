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

# ── 0-A) ★서버 역할 가드 — 이 스크립트는 **158(A1 프론트) 전용**이다 ──
#   ★2026-08-17 실사고. 이걸 168(백엔드)에서 돌리면 **트래픽을 받지 않는 compose 스택**만
#     갱신하고 "성공"을 찍는다. 그날 #630·#653·#662 가 배포된 줄 알았으나 실서비스
#     (caddy → propai-api-800x) 컨테이너 안은 **전부 0** 이었다.
#   ★왜 검증도 못 잡았나: 이 스크립트의 검증은 `$VERIFY_BASE_URL/ko` 를 보는데 백엔드
#     서버엔 프론트가 없어 **web=404** 가 난다. 그것을 `WARN 검증미흡 — 수동확인 필요`
#     로만 찍고 넘어갔고, 사람이 "백엔드 전용이라 당연"이라고 해석해 배경이 됐다.
#     → 그래서 **검증이 아니라 시작 지점**에서 막는다(16분을 태우기 전에).
#   ★판별 근거(2026-08-17 실측): 백엔드(168)에만 `~/caddy/Caddyfile` 과 caddy 컨테이너가
#     있고 프론트(158)에는 **둘 다 없다**. 백엔드가 caddy 를 버리는 날 이 가드도 함께 고쳐야
#     한다 — 그때는 이 스크립트가 백엔드에서 조용히 다시 통과하게 되므로.
if [ -f "$HOME/caddy/Caddyfile" ]; then
  echo "ABORT: 여기는 **백엔드 서버**입니다(~/caddy/Caddyfile 존재)." >&2
  echo "       safe-deploy.sh 는 158(프론트) 전용이라 여기서는 트래픽 없는 스택만 갱신합니다." >&2
  echo "       백엔드 정본을 쓰세요: bash ~/Development_AI/propai-platform/infra/deploy-zero-downtime.sh" >&2
  exit 10
fi

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

# ★앱 버전을 여기서 한 번 만든다 — sw 캐시명과 텔레메트리가 **같은 값**에서 갈라진다.
#   seq 는 제로패딩(정렬 가능성) · shortsha 는 커밋 식별. 손으로 올리던 범프를 대체한다.
#   ★이 export 가 빠지면 Dockerfile.web 이 빌드를 죽인다(조용히 옛 캐시명이 나가지 않는다).
APP_BUILD_ID="propai-v$(printf '%06d' "$(git rev-list --count HEAD)")-$(git rev-parse --short=8 HEAD)"
export APP_BUILD_ID
log "APP_BUILD_ID = $APP_BUILD_ID"
log "DEPLOY_REF = $DEPLOY_REF"
log "HEAD = $HEAD"

# ── 3) 빌드 (prune 없이, legacy builder로 ContainerConfig 보장) ──
cd "$COMPOSE_DIR" || { status "FAIL cd-compose"; exit 1; }
build_one() {
  local svc=$1
  status "BUILD $svc @ $HEAD"
  # ★롤백 경로 확보 — 새 빌드가 :oracle 을 덮기 전 세대를 :prev 로 승계한다.
  #   rollback_one() 은 배포 '실패' 시에만 동작하는 내부 함수(지역변수 rb)라, 배포가 성공한 뒤
  #   결함을 발견했을 때 되돌릴 이미지가 없었다. :prev 는 태그가 있으므로 dangling prune 에도 생존한다.
  #   ★빌드 '후' ID 비교가 핵심 — 빌드 '전' 무조건 태깅하면 같은 커밋 재배포 시 레이어 캐시로
  #   동일 ID 가 나와 prev==oracle 이 되고 롤백 자산이 조용히 무효화된다(168 에서 실측·2026-07-30).
  local old_img_id new_img_id
  old_img_id=$(docker image inspect "propai-${svc}:oracle" --format '{{.Id}}' 2>/dev/null || echo "")
  DOCKER_BUILDKIT=0 compose build "$svc" >>"$LOG" 2>&1 || { status "FAIL build-$svc"; return 1; }
  new_img_id=$(docker image inspect "propai-${svc}:oracle" --format '{{.Id}}' 2>/dev/null || echo "")
  if [ -n "$old_img_id" ] && [ "$old_img_id" != "$new_img_id" ]; then
    if docker image tag "$old_img_id" "propai-${svc}:prev" >>"$LOG" 2>&1; then
      log "[$svc] prev 승계: ${old_img_id:0:20} (rollback 가능)"
    else
      log "[$svc] prev 태깅 실패 — 배포는 계속(롤백 자산만 미갱신)"
    fi
  else
    log "[$svc] prev 유지(이미지 내용 동일 또는 최초 빌드)"
  fi
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
ensure_dependency_services() {
  # 새 API가 Redis/Qdrant를 실제로 보도록 dependency 서비스를 먼저 보장한다.
  # 이미 떠 있으면 no-op, 없으면 image pull 후 생성한다.
  status "DEPENDENCIES"
  compose up -d --no-build redis qdrant >>"$LOG" 2>&1 || { status "FAIL deps"; return 1; }
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
  api|both) ensure_dependency_services || exit 1 ;;
esac
case "$TARGET" in
  web)  recreate_one web  || exit 1 ;;
  api)  recreate_one api  || exit 1 ;;
  both) recreate_one api  || exit 1; recreate_one web || exit 1 ;;
esac

# ── 5) 네트워크 전수 보장 + nginx 재시작(새 IP 재인식) ──
status "NGINX-RELOAD"
for s in redis qdrant api web; do ensure_network "$s"; done
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
