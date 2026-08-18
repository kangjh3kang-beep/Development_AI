#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# deploy-zero-downtime.sh — 백엔드(168) 무중단(블루-그린) 배포 **정본**.
#
# ★이 파일이 정본인 이유 (2026-08-12):
#   실제로 도는 것은 서버 홈의 `~/deploy.sh` 였고, 저장소의 이 파일은 그보다 한참
#   낡아 있었다 — 동시배포 락도, prev 롤백 승계도, field_audit 게이트도, 워커 정렬도
#   **저장소 사본에는 없었다**. 홈 사본은 리뷰도 이력도 없이 자란다(#583 이 롤백
#   스크립트에서 지적한 것과 같은 문제이며, 여기서는 방향이 반대였다).
#   그래서 서버 실물을 저장소로 끌어올리고, 이후 변경은 여기서만 한다.
#
# 사용법(168에서):  bash ~/Development_AI/propai-platform/infra/deploy-zero-downtime.sh
# ════════════════════════════════════════════════════════════════
# ★pipefail 이 필요하다: 아래 `git pull … | tail -1` 과 `docker build … | tail -2` 는
#   파이프 마지막 명령(tail)의 종료코드를 쓴다 — tail 은 항상 0 이다. set -e 만으로는
#   **빌드가 실패해도 배포가 계속되고** 옛 이미지로 스왑한 뒤 "완료"를 찍는다(은폐).
#   이 저장소가 이미 문서화한 결함이다(_workspace/PLAN_image_generation_inc2-4.md).
#   ★서버 실물에는 pipefail 이 없다 — 정본으로 올리면서 함께 고친다.
set -eo pipefail

# ★서버 역할 가드 — 이 스크립트는 **168(백엔드) 전용**이다(위 사용법 참조).
#   짝인 `scripts/safe-deploy.sh` 에 반대 방향 가드가 있고, 둘이 서로를 배타적으로 잠근다.
#   ★판별 근거(2026-08-17 실측): 백엔드(168)에만 `~/caddy/Caddyfile` 이 있다. 프론트(158)에는
#     없다. 이 스크립트는 Caddyfile 을 읽어 활성 포트를 판정하고 **직접 덮어쓰므로**, 파일이
#     없는 서버에서 돌리면 아래 `CUR` 폴백(8000)으로 엉뚱한 포트에 컨테이너를 띄우고
#     존재하지 않던 Caddyfile 을 새로 만든다 — 조용히 잘못된 상태를 만든다.
if [ ! -f "$HOME/caddy/Caddyfile" ]; then
  echo "!! 여기는 백엔드 서버가 아닙니다(~/caddy/Caddyfile 없음)." >&2
  echo "   deploy-zero-downtime.sh 는 168 전용입니다. 프론트(158)는 아래를 쓰세요:" >&2
  echo "   bash ~/Development_AI/propai-platform/scripts/safe-deploy.sh web main" >&2
  exit 10
fi

# ★동시배포 락 — 두 세션 동시 실행 시 블루그린 포트판정 레이스(2026-07-22 12:31/12:33 중복 실행 실측).
#   락 획득 실패=다른 배포 진행 중 → 즉시 중단(대기 아님: 대개 같은 커밋의 중복 배포라 재시도가 안전).
LOCKFILE=/tmp/propai-deploy.lock
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "!! 다른 배포가 진행 중(락 $LOCKFILE) — 중단. 완료 후 재시도하세요."
  exit 1
fi
cd ~/Development_AI/propai-platform
git pull origin main 2>&1 | tail -1
echo "== build =="
# ★이미지가 **어느 커밋인지** 스스로 말하게 한다 — 프론트 `safe-deploy.sh` 와 같은 형식·같은 이름.
#   seq 는 제로패딩(정렬 가능성) · shortsha 는 커밋 식별.
#   ★이 값이 빠지면 `Dockerfile.oracle` 이 빌드를 죽인다(조용히 "어느 커밋인지 모르는" 이미지가
#     나가지 않는다). 배포 후 실행 컨테이너에서 이 값을 되읽어 대조하는 것이 아래 VERIFY-BUILD 다.
APP_BUILD_ID="propai-v$(printf '%06d' "$(git rev-list --count HEAD)")-$(git rev-parse --short=8 HEAD)"
export APP_BUILD_ID
echo "APP_BUILD_ID = $APP_BUILD_ID"

# ★이 정리는 **위 build-arg 가 만드는 부작용**을 같은 자리에서 봉합한다.
#   `APP_BUILD_ID` 가 커밋마다 달라지므로 **매 배포가 새 이미지 ID** 를 만들고, 직전 세대는
#   태그를 잃으면 dangling 으로 남는다. 158(프론트)은 이미 그 구조라 2026-08-17 에
#   **dangling 89개 · 디스크 90% 로 배포가 죽었다**(`ABORT 디스크부족`). 168 도 같은 축적이 시작된다.
#
#   ★★`-a` 를 절대 붙이지 마라. `-a` 는 **참조되지 않는 태그 이미지까지** 지워
#     `propai-api:prev`(롤백 자산)와 베이스 이미지를 날린다. 그러면 이 스크립트의 자동 롤백이
#     **조용히 무효**가 된다 — 실패한 배포를 되돌릴 수단이 사라진 뒤에야 드러난다.
#     dangling 한정이 안전한 근거: 태그가 붙은 이미지는 dangling 이 아니다(`:latest`·`:prev` 생존).
#     2026-08-17 실측 — 삭제 전 보존대상(실행중 5 + 태그 4)과 dangling 목록의 **교집합 0**.
#   ★과거 `docker system prune -af` 가 빌드를 죽인 사고가 있어 이 스크립트는 prune 을 피해 왔다.
#     그 사고의 원인은 **`-af`(all+force)** 였지 dangling 정리가 아니다.
echo "== dangling 이미지 정리(★-a 금지 — prev 롤백 자산 보호) =="
sudo docker image prune -f 2>&1 | tail -1 || true

# ★롤백 경로 확보(insight-loop 2026-07-29 / 2026-07-30 보정): 빌드 후 이미지 ID를 비교해
#   **내용이 실제로 바뀐 경우에만** 직전 이미지를 prev 로 승계한다.
#   무조건 태깅하면 같은 커밋 재배포 시 캐시로 동일 ID가 나와 prev==latest 가 되어
#   롤백 자산이 조용히 무효화된다(2026-07-30 재배포에서 실측·직전 세대가 태그에서 밀려남).
#   ★★2026-08-17 갱신 — **위 방어는 이제 거의 발동하지 않는다.** `APP_BUILD_ID` 가 커밋마다
#     달라져 이미지 ID 도 항상 달라지므로 `OLD != NEW` 가 사실상 상시 참이 된다.
#     그래도 비교를 **남겨 둔다**: ①`APP_BUILD_ID` 주입이 미래에 빠지면 방어가 되살아나야 하고
#     ②같은 커밋을 재배포하면(`git pull` 이 no-op) 여전히 동일 ID 가 나온다.
#     ※근거가 낡은 채 남으면 다음 사람이 그것을 재사용한다 — 그래서 조건이 바뀐 사실을 여기 적는다.
OLD_IMG_ID=$(sudo docker image inspect propai-api:latest --format {{.Id}} 2>/dev/null || echo "")
# ★빌드가 **캐시를 썼는지** 남긴다 — 안 남기면 느려졌을 때 원인을 못 가린다.
#   2026-08-18 첫 VERIFY-BUILD 배포가 **699초**(기준선 39초의 18배)였는데, 로그가
#   `| tail -2` 라 `Using cache` 줄이 버려져 **사후에 가릴 방법이 없었다**:
#     ①첫 적용 비용(ARG 레이어 신설 + 소스 변경)인지
#     ②위 dangling prune 의 **간접 영향**인지(지운 이미지가 참조하던 레이어가 사라져
#       캐시 재사용이 깨졌을 수 있다 — 빌드 캐시 엔트리가 남아도 레이어가 없으면 못 쓴다)
#   ★`image prune -f` 가 빌드 캐시를 직접 지우는 것은 **아니다**(그건 `builder prune`).
#     배포 후 `docker system df` 에 Build Cache 50개·6.374GB 가 남아 있음을 실측했다.
#   → 원인을 모르는 채 prune 위치를 바꾸는 것은 추측이므로, **먼저 관측을 남기고**
#     다음 배포의 캐시 히트 수로 판별한다.
BUILD_LOG=$(mktemp)
sudo docker build -f Dockerfile.oracle --build-arg "APP_BUILD_ID=$APP_BUILD_ID" -t propai-api:latest . > "$BUILD_LOG" 2>&1
tail -2 "$BUILD_LOG"
# ★`grep -c` 는 매칭 0 이면 exit 1 이라 pipefail+set -e 아래서 배포를 죽인다 → `|| true`.
#   그리고 결과를 **정수로 쓸 때 개행이 섞이면** `[: integer expression expected` 가 난다
#   (2026-08-18 통합자 감시 루프가 그 형태로 10분 헛돌았다) → `tr -d` 로 한 줄로 만든다.
CACHE_HITS=$(grep -cE 'Using cache|^#[0-9]+ CACHED' "$BUILD_LOG" 2>/dev/null | tr -d '[:space:]' || true)
BUILD_STEPS=$(grep -cE '^Step [0-9]+/|^#[0-9]+ \[' "$BUILD_LOG" 2>/dev/null | tr -d '[:space:]' || true)
echo "빌드 캐시 재사용 = ${CACHE_HITS:-0} / 단계 ${BUILD_STEPS:-0}  (로그: $BUILD_LOG)"
NEW_IMG_ID=$(sudo docker image inspect propai-api:latest --format {{.Id}} 2>/dev/null || echo "")
if [ -n "$OLD_IMG_ID" ] && [ "$OLD_IMG_ID" != "$NEW_IMG_ID" ]; then
  sudo docker image tag "$OLD_IMG_ID" propai-api:prev && echo "prev 승계: ${OLD_IMG_ID:0:20}"
else
  echo "prev 유지(이미지 내용 동일 — 같은 커밋 재빌드): $(sudo docker image inspect propai-api:prev --format {{.Id}} 2>/dev/null | cut -c1-20)"
fi
# ★`|| true` 가 필요하다(2026-08-12 리뷰 지적·실측): pipefail 을 켜면 grep 의 '매칭 없음'
#   (exit 1)이 파이프라인 종료코드로 승격되고, set -e 가 **이 대입에서 배포를 죽인다**.
#   그러면 바로 아래 폴백 `CUR=8000` — 정확히 그 경우를 위해 있는 줄 — 이 도달 불가가 된다.
#   실측: Caddyfile 에 localhost:<포트> 가 없을 때 종전은 CUR=8000 도달, pipefail 은 exit 1
#   (메시지 한 줄 없이). 빌드까지 끝낸 뒤 조용히 죽으므로 원인 추적이 어렵다.
#   ★pipefail 은 빌드 실패 은폐를 막으려고 켠 것이다 — 그 목적을 지키면서, '실패해도 되는'
#   이 한 대입만 면제한다(면제를 넓히면 은폐가 돌아온다).
CUR=$(grep -oE 'localhost:[0-9]+' ~/caddy/Caddyfile | grep -oE '[0-9]+' | tail -1) || true
[ -z "$CUR" ] && CUR=8000
NEW=$([ "$CUR" = "8000" ] && echo 8001 || echo 8000)
NAME=propai-api-$NEW
echo "현재 활성 포트=$CUR → 신규 포트=$NEW ($NAME)"
sudo docker rm -f "$NAME" 2>/dev/null || true
sudo docker run -d --name "$NAME" --restart always --env-file .env -p ${NEW}:8000 propai-api:latest >/dev/null
echo "== 신앱 health 대기(8000 내부) =="
ok=0; for i in $(seq 1 60); do if curl -sf -o /dev/null "http://localhost:${NEW}/health"; then ok=1; break; fi; sleep 3; done
if [ "$ok" != "1" ]; then echo "!! 신앱 health 실패 — 배포중단(기존 유지)"; sudo docker rm -f "$NAME"; exit 1; fi
# ★VERIFY-BUILD — **떠 있는 컨테이너가 방금 빌드한 그것인지** 확인한다(Caddy 전환 전).
#   2026-08-17 실사고가 이 자리를 비워 두어 일어났다: 배포 후 확인을 **호스트 파일시스템의
#   소스**로 했는데, 그 경로는 `git reset --hard` 로 늘 최신이라 **무엇을 배포하든 통과**한다.
#   그래서 `#630`·`#653`·`#662` 가 반영된 줄 알았으나 **실서비스 컨테이너 안은 전부 0** 이었다.
#   ★여기서는 **실행 중인 컨테이너에게 직접 묻는다**. 소스도, 저장소 상태도 근거로 쓰지 않는다.
#   ★불일치면 전환하지 않는다 — 잘못된 이미지가 라이브로 올라간 뒤 되돌리는 것보다 싸다.
echo "== VERIFY-BUILD(전환 전 · 실행 컨테이너에 직접 질의) =="
RUNNING_ID=$(sudo docker exec "$NAME" printenv APP_BUILD_ID 2>/dev/null || echo "")
if [ "$RUNNING_ID" != "$APP_BUILD_ID" ]; then
  echo "!! 배포하려는 것과 떠 있는 것이 다르다 — 전환 중단(기존 앱 유지)"
  echo "   빌드한 값 = [$APP_BUILD_ID]"
  echo "   컨테이너  = [$RUNNING_ID]"
  echo "   ※빈 값이면 이미지에 APP_BUILD_ID 가 없다 = **이 빌드의 산출물이 아니다**."
  echo "     정상 빌드는 빈 값을 만들 수 없다(Dockerfile.oracle 이 fail-closed 로 죽인다)."
  echo "     따라서 빈 값은 '옛 propai-api:latest 를 그대로 run 했다'는 뜻이다 — 빌드 로그를 보라."
  sudo docker rm -f "$NAME"
  exit 1
fi
echo "  OK 실행 컨테이너 = $RUNNING_ID"

# ★field_audit 활성 게이트(insight-loop 2026-07-30) — Caddy 전환 전에 신규 컨테이너를 검사한다.
#   #497 진단 엔드포인트로 자가검증 레이어의 무성(silent) 회귀를 배포 시점에 차단(fail-closed).
#   introspect 전용이라 비용·부작용 0. 실패 시 신앱만 제거하고 기존 앱을 유지 → 무중단.
echo "== field_audit 활성 게이트(전환 전 검사) =="
if ! PROPAI_API_BASE="http://localhost:${NEW}" bash scripts/smoke_field_audit.sh; then
  echo "!! field_audit 비활성/등록0 — 배포중단(기존 앱 유지·전환 안 함)"
  sudo docker rm -f "$NAME"
  exit 1
fi

# ★DB 마이그레이션(신 컨테이너 내부 alembic upgrade head) — 트래픽 전환 '전'에 수행.
#  새 코드가 요구하는 스키마(신규 컬럼/테이블)를 트래픽 받기 전에 반영해, 코드-스키마 불일치로
#  로그인 등이 500 나던 사고(2026-07-15 042)를 원천 차단한다. additive 마이그레이션 전제라
#  구 컨테이너는 마이그레이션 중에도 정상 서빙(하위호환). 실패 시 트래픽 전환 없이 배포중단.
#
#  ★★2026-08-12 — 이 블록은 **한 번 사라졌다가 복원됐다**. 저장소 사본을 서버 실물(~/deploy.sh)로
#  덮어쓰며 조용히 지워졌고 리뷰가 잡았다. 서버 사본에는 이게 **원래 없다** — 실측 결과
#  프로덕션 DB 는 `042_member_account_system`, head 는 `043_mypage_coin_orders_ledger` 로
#  **리비전 1건이 미적용**이다(코드가 그 사실을 알고 방어적으로 쓰여 있다:
#  disbursement_ledger_service.py · migrations/versions/043_*.py 의 "deploy.sh가 alembic 미실행이어도").
#  ★그래서 서버 배포 경로를 이 스크립트로 바꾸는 것은 **스키마를 움직이는 행위**다 —
#  배포 배선을 바꾸는 김에 곁다리로 할 일이 아니라, 043 적용을 의도한 시점에 별도로 한다.
echo "== DB 마이그레이션(alembic upgrade head, 신 컨테이너 내부) =="
if ! sudo docker exec "$NAME" sh -c "cd /app/apps/api && PYTHONPATH=/app alembic upgrade head"; then
  echo "!! 마이그레이션 실패 — 배포중단(기존 유지·트래픽 전환 안 함)"; sudo docker rm -f "$NAME"; exit 1
fi

echo "== Caddy 전환(graceful reload) → $NEW =="
printf ":80 {\n  handle /flower* {\n    reverse_proxy localhost:5555\n  }\n  reverse_proxy localhost:%s\n}\n" "$NEW" > ~/caddy/Caddyfile
sudo docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
sleep 2
code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:80/health)
echo "전환 후 80 -> $code"
if [ "$code" != "200" ]; then echo "!! 전환 실패 — 롤백(Caddy를 $CUR로)"; printf ":80 {\n  handle /flower* {\n    reverse_proxy localhost:5555\n  }\n  reverse_proxy localhost:%s\n}\n" "$CUR" > ~/caddy/Caddyfile; sudo docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; sudo docker rm -f "$NAME"; exit 1; fi
echo "== 구앱 제거 =="
for c in $(sudo docker ps -a --format '{{.Names}}' | grep -E '^propai-api'); do [ "$c" = "$NAME" ] || sudo docker rm -f "$c" 2>/dev/null || true; done
# ★백그라운드 워커 이미지 정렬 — 로직은 리포에 있고 여기선 호출만 한다.
#   이 스크립트는 API 컨테이너만 블루-그린으로 교체하므로 워커는 대상이 아니다.
#   컨테이너는 계속 Up 이라 헬스체크로도 안 잡히고, 워커가 조용히 **옛 코드로** 잡을
#   처리한다(무성 회귀). 탐지 수단은 컨테이너 나이가 아니라 이미지 ID 대조뿐이다.
#
#   ★2026-08-12 — 종전에는 여기서 arq **만** 정렬했다. 그래서 celery 3종
#   (worker·beat·flower)이 **2026-07-22 이미지로 3주간** 돌았고, 그 사이 배포된
#   모든 백엔드 수정이 celery 가 실행하는 태스크에는 도달하지 않았다.
#   지금은 "어떤 워커를 정렬할지"를 a1-align-workers.sh 한 곳이 안다 —
#   워커가 늘어도 이 파일은 고치지 않는다(고치는 걸 잊어 누락되는 게 원인이었다).
#
#   ★비치명적: 여기는 이미 트래픽 전환이 끝난 지점이라, 실패해도 배포를 되돌리지 않고
#   경고만 남긴다(운영자가 수동 재실행하면 됨).
if ! bash scripts/a1-align-workers.sh; then
  echo "⚠️ 워커 정렬 실패 — 워커가 구 이미지일 수 있습니다. 수동 확인 필요:"
  echo "   bash ~/Development_AI/propai-platform/scripts/a1-align-workers.sh"
fi

echo "✅ 무중단 배포 완료 (활성=$NEW)"
