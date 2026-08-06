#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# rollback-web.sh — 158 프론트 롤백. 배포 '성공 후' 결함을 발견했을 때
#   재빌드 없이 propai-web:prev 로 즉시 복귀한다(빌드 22분+ 회피).
#
# safe-deploy.sh 의 rollback_one() 은 배포 '실패' 시에만 도는 내부 함수(지역변수)라
# 외부에서 쓸 수 없다. 그래서 별도 진입점이 필요하다.
#
# ★이 파일이 저장소에 있는 이유 (2026-08-06 실측 사고):
#   종전에는 서버 홈(~/rollback-web.sh)에만 있었다. 홈 사본은 리뷰도 이력도 없이
#   조용히 낡는다. 실제로 홈 ~/safe-deploy.sh 가 저장소 정본과 갈라져 :prev 승계가
#   빠졌고, 그 결과 직전 세대 이미지가 무태그 dangling 으로 남아 **롤백 자산이 한 세대
#   어긋난 채 배포가 "성공"했다**(헬스체크·상태코드·sw 버전 어디에도 안 걸림).
#   배포 도구는 저장소가 정본이어야 한다.
#
# ★종전 홈 사본의 확정 결함 — 락 가드가 공허했다:
#     LOCK=/tmp/propai_deploy.lock ; if [ -f "$LOCK" ]; then ... 중단 ...
#   그런데 safe-deploy.sh 의 락은 **원자적 mkdir 로 만든 디렉터리**다(scripts/safe-deploy.sh
#   "0) 동시배포 방지 락"). 디렉터리에 -f 는 **항상 거짓**이라 이 가드는 한 번도 발동한 적이
#   없다. 실측: 배포가 실제로 도는 중에 -d 는 참, -f 는 거짓이었다.
#   → 빌드/재생성 도중에 롤백이 끼어들어 propai-web:oracle 태그를 서로 덮을 수 있었다.
#   여기서는 **같은 LOCKDIR 을 같은 방식(mkdir)으로 획득**해 배포와 상호배제한다.
#
# 사용법:
#   bash propai-platform/scripts/rollback-web.sh check   # 읽기전용 점검(운영 무변경)
#   bash propai-platform/scripts/rollback-web.sh         # 실제 롤백
# ════════════════════════════════════════════════════════════════
set -uo pipefail

MODE="${1:-run}"
REPO="${REPO:-$HOME/Development_AI}"
COMPOSE_DIR="$REPO/propai-platform"
LOCKDIR="${LOCKDIR:-/tmp/propai_deploy.lock}"   # ★safe-deploy.sh 와 동일해야 상호배제된다
VERIFY_BASE_URL="${VERIFY_BASE_URL:-http://localhost:80}"
VERIFY_BASE_URL="${VERIFY_BASE_URL%/}"
HEALTH_TRIES="${HEALTH_TRIES:-40}"

compose() {
  if command -v docker-compose >/dev/null 2>&1; then docker-compose "$@"; else docker compose "$@"; fi
}
container_name() {
  local n
  for n in "propai-platform_web_1" "propai-platform-web-1"; do
    docker inspect "$n" >/dev/null 2>&1 && { echo "$n"; return 0; }
  done
  echo "propai-platform_web_1"
}
img_id()  { docker image inspect "$1" --format '{{.Id}}' 2>/dev/null || echo ""; }
short()   { printf '%s' "${1#sha256:}" | cut -c1-12; }
# sw 상수는 **따옴표로 뽑는다**. 정규식 propai-v[0-9]*[a-z-]* 로 뽑으면 끝자리 숫자가 잘려
# (propai-v496-modal-rung → 그대로지만, …-ia-p1 → …-ia-p) 멀쩡한 값을 틀리게 읽는다(실측).
sw_const() { curl -s --max-time 10 "$VERIFY_BASE_URL/sw.js" | grep -m1 '^const CACHE_NAME' | cut -d'"' -f2; }

# ── 자산 점검 (check 와 run 이 공유) ──
report_assets() {
  local cur prev
  cur=$(img_id propai-web:oracle); prev=$(img_id propai-web:prev)
  echo "  oracle = $(short "$cur")  ($(docker image inspect propai-web:oracle --format '{{.Created}}' 2>/dev/null | cut -c1-19))"
  echo "  prev   = $(short "$prev")  ($(docker image inspect propai-web:prev   --format '{{.Created}}' 2>/dev/null | cut -c1-19))"
  if [ -z "$prev" ]; then
    echo "  ★prev 없음 — 롤백 불가(직전 배포가 태깅 도입 이전이거나 승계가 빠졌다)"; return 1
  fi
  if [ "$cur" = "$prev" ]; then
    # 같은 커밋 재배포는 레이어 캐시로 동일 ID 가 나온다. 그때 prev==oracle 이면 되돌릴 곳이 없다.
    echo "  ★prev == oracle — 되돌릴 세대가 없다(롤백해도 무변화)"; return 1
  fi
  echo "  판정: 롤백 가능(prev != oracle)"
  return 0
}

echo "== 롤백 자산 =="
if [ "$MODE" = "check" ]; then
  # ★읽기전용. 락도 '보기만' 한다(획득하면 진짜 배포를 막는다).
  if [ -d "$LOCKDIR" ]; then
    echo "  락: 점유중($LOCKDIR) — 지금 롤백하면 배포와 충돌한다"
  else
    echo "  락: 비어있음"
  fi
  report_assets; rc=$?
  echo "  현재 sw: $(sw_const)"
  echo "  (check 모드 — 운영 무변경)"
  exit $rc
fi

# ── 배포와 상호배제 (safe-deploy.sh 와 동일한 원자적 mkdir 락) ──
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "!! 배포/롤백이 진행 중($LOCKDIR) — 중단. 완료 후 재시도."; exit 9
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

cd "$COMPOSE_DIR" || { echo "!! cd 실패: $COMPOSE_DIR"; exit 1; }
report_assets || exit 1

CNAME=$(container_name)
docker image tag propai-web:oracle propai-web:rollback-undo 2>/dev/null || true  # 되돌리기 취소용
docker image tag propai-web:prev propai-web:oracle

docker stop "$CNAME" >/dev/null 2>&1 || true
docker rm   "$CNAME" >/dev/null 2>&1 || true
compose up -d --no-deps --no-build web

ok=0
for _ in $(seq 1 "$HEALTH_TRIES"); do
  c=$(curl -s -o /dev/null -w "%{http_code}" -L "$VERIFY_BASE_URL/" 2>/dev/null)
  [ "$c" = "200" ] && { ok=1; break; }
  sleep 3
done

if [ "$ok" != "1" ]; then
  echo "!! 롤백 후 health 실패 — 원복(rollback-undo)"
  docker image tag propai-web:rollback-undo propai-web:oracle
  docker stop "$CNAME" >/dev/null 2>&1 || true
  docker rm   "$CNAME" >/dev/null 2>&1 || true
  compose up -d --no-deps --no-build web
  exit 1
fi

echo "✅ 프론트 롤백 완료(이미지=prev)"
echo "   sw: $(sw_const)"
# ★이 시점에 prev == oracle 이다. 한 세대만 보관하므로 **연속 롤백은 무변화**다.
#   더 뒤로 가려면 rollback-undo(방금 되돌린 그 이미지)로 앞으로 가거나, 재빌드해야 한다.
echo "   주의: 이제 prev == oracle 이라 재실행해도 더 뒤로 가지 않는다(1세대 보관)."
echo "   앞으로 되돌리려면: docker image tag propai-web:rollback-undo propai-web:oracle 후 재생성"
