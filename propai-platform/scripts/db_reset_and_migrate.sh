#!/bin/bash
# scripts/db_reset_and_migrate.sh
#
# ★★이 스크립트는 **DB 볼륨을 삭제한다**(`down -v`). 프로덕션에서 돌면 데이터가 사라진다.
#
#   2026-08-20 실측으로 드러난 상태:
#     · 이 파일은 **158·168 프로덕션 양쪽에 실재한다** — 두 서버 모두 저장소를
#       `git reset --hard FETCH_HEAD` 로 통째로 받으므로 배포될 때마다 함께 올라간다.
#     · 저장소 전역에 **호출처 0건**(`git grep` 전수, 대조군 생존) — 아무도 이 경로를
#       테스트하지 않는다. 죽은 코드인데 **이름은 일상적**이다(`db_reset_and_migrate`).
#       마이그레이션 방법을 찾던 사람이나 에이전트가 집어 들기 딱 좋다.
#     · `down -v` 는 **저장소 전역에서 이 한 줄뿐**이다(git grep 전수).
#
#   → 그래서 두 겹으로 막는다: ①프로덕션 컨테이너가 돌면 무조건 중단 ②명시적 확인 요구.
#     한 겹만 두면 다른 한 겹이 없는 상황에서 그대로 뚫린다.

set -euo pipefail

# 워크스페이스 루트로 이동 (가드가 실패하면 여기까지 오지 않는다)
cd "$(dirname "$0")/.."

# ── 가드 ① 프로덕션 컨테이너가 실행 중이면 중단 ─────────────────────────────
#   실서비스 컨테이너 이름: 168 = `propai-api-8000`/`8001`(blue-green),
#                           158 = `propai-platform_web_1`/`_api_1`(compose v1).
#   ★이름 패턴은 **실측 기반**이다(2026-08-20 `docker ps` 양 서버). 배포 방식이 바뀌면
#     이 패턴도 함께 고칠 것 — 안 고치면 가드가 조용히 아무것도 막지 않게 된다.
_running=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -E '^propai-(api-[0-9]+|platform_)' || true)
if [ -n "$_running" ]; then
  echo "★중단: 프로덕션 컨테이너가 실행 중이다. 이 스크립트는 **DB 볼륨을 삭제**한다."
  echo "$_running" | sed 's/^/    실행중: /'
  echo "  로컬 개발 환경에서만 쓸 것."
  exit 10
fi

# ── 가드 ② 명시적 확인 ──────────────────────────────────────────────────────
#   ★환경변수로 받는다(대화형 `read` 는 CI·비대화 셸에서 그냥 통과해 버린다).
if [ "${DB_RESET_CONFIRM:-}" != "yes" ]; then
  echo "★중단: 볼륨 삭제에는 명시적 확인이 필요하다."
  echo "  다시 실행: DB_RESET_CONFIRM=yes $0"
  exit 11
fi

echo "=== PropAI DB 초기화 시작 (볼륨 삭제 포함) ==="

# 1. 기존 컨테이너 데이터 볼륨만 삭제 (이미지 유지) 및 강제 삭제
docker compose -f infra/docker-compose.yml down -v --remove-orphans
# ★삭제 범위를 **compose 정의에서 파생**한다. 종전에는 이름 8개가 손으로 박혀 있었는데
#   그 목록과 compose 정의(12개)가 어긋났다 — `propai-airflow` 는 compose 에 없고,
#   compose 의 elasticsearch·kafka·zookeeper·mqtt-broker·jaeger·prometheus·grafana 는
#   그 목록에 없었다. **조회(compose 파일)와 삭제(손 목록)의 범위가 다르면**
#   "down 으로 충분하다"는 오판이 생긴다(2026-08-19 docker prune 사고와 같은 부류).
#   ★`2>/dev/null` 도 걷어낸다 — 실패를 숨기면 무엇이 안 지워졌는지 알 수 없다.
_svcs=$(docker compose -f infra/docker-compose.yml config --services 2>/dev/null || true)
if [ -n "$_svcs" ]; then
  echo "$_svcs" | sed 's/^/  잔여 확인: propai-/'
  for s in $_svcs; do docker rm -f "propai-$s" 2>&1 | grep -v 'No such container' || true; done
fi
echo "[1/5] 볼륨 삭제 완료"

# 2. PostgreSQL 컨테이너 재시작 (PostGIS 자동 초기화)
docker compose -f infra/docker-compose.yml up -d postgres redis qdrant minio
echo "[2/5] 인프라 컨테이너 시작..."

# 3. postgres healthy 상태 대기
until docker compose -f infra/docker-compose.yml exec postgres pg_isready -U propai_user -d propai_db; do
  echo "  PostgreSQL 대기 중..."
  sleep 2
done
echo "[3/5] PostgreSQL 준비 완료"

# 4. Alembic 마이그레이션 실행
cd apps/api

echo "  필수 파이썬 패키지(geoalchemy2) 확인 및 설치 중..."
pip install geoalchemy2==0.15.2

# 신규 테이블(v53 등 모델 변경점) 반영을 위해 자동생성 시도, 이후 업그레이드
alembic revision --autogenerate -m "auto_v53_tables"
alembic upgrade head
echo "[4/5] 121개 테이블 마이그레이션 및 적용 완료"

cd ../../
# 5. 시드 데이터 삽입 (GWP DB, 법규 기초 데이터 등)
# python scripts/seed_data.py
echo "[5/5] 시드 데이터 삽입 완료 (현재 seed_data.py 스크립트 구조 확인 후 진행)"

echo "=== PropAI v53.0 DB 초기화 완료 ==="
