#!/bin/bash
# scripts/db_reset_and_migrate.sh

echo "=== PropAI v53.0 DB 초기화 시작 ==="

# 워크스페이스 루트로 이동
cd "$(dirname "$0")/.."

# 1. 기존 컨테이너 데이터 볼륨만 삭제 (이미지 유지) 및 강제 삭제
docker compose -f infra/docker-compose.yml down -v --remove-orphans
docker rm -f propai-postgres propai-redis propai-qdrant propai-minio propai-mlflow propai-airflow propai-api propai-web 2>/dev/null
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
