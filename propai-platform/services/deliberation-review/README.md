# propai-review — PropAI 심의분석 엔진

건축 심의도면 자동 심의분석 엔진. **무음 오판 0**을 보증하는 결정론 우선 파이프라인.
하네스 시리즈: Phase0 → R0 → R0.5 → R1.5 → R2 → R3 → L3-B → L4 → L5 → L6 → L3-C (누적 불변식 INV-1..33).

## 환경(현재)
- **Docker 미가용** → 시스템 **PostgreSQL 16 + PostGIS 3.4 + Redis** 사용. DB는 `propai_db`의 **`review` 스키마**로 격리(다른 프로젝트 테이블·alembic과 분리).
- Python 3.12, FastAPI, SQLAlchemy 2.0(asyncpg), pydantic v2, Alembic, Celery, structlog, pytest.
- `docker-compose.yml`은 Docker 가용 시용(spec 보존). 그때는 `propai_review` DB 사용.

## 빠른 시작
```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env            # 필요시 DATABASE_URL 조정
make migrate                    # alembic upgrade head (review 스키마)
make test                       # AT-1..8
```

## Phase 0 수용기준(AT-1..8)
헬스체크 · async db+PostGIS · 공통 믹스인 컬럼 · alembic up/down · input_hash 재현성 ·
static_scan(하드코딩 탐지) · celery 로딩 · 픽스처 로더.

## 구조
- `apps/api/app/` — settings, db(base/session), core(hashing/ids/errors/logging), tasks(celery), contracts, models(probe).
- `apps/api/alembic/` — 마이그레이션(review 스키마).
- `tools/static_scan.py` — 법정/도메인 수치 하드코딩 스캐너(INV-3).
- `tests/` — conftest(async db), fixtures(페이즈별), smoke(AT).
