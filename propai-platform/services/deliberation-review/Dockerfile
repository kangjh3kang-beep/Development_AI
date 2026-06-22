# PropAI 심의분석 엔진 — 프로덕션 이미지(GPU 불요 경량 MVP).
# torch/vllm 없음. FastAPI + SQLAlchemy(asyncpg) + Celery(eager) + structlog 만.
# import 경로 정합: 코드는 전부 절대 import `app.*`(예: `from app.settings import settings`).
#   → 패키지 루트는 apps/api/app 이고, 임포트 루트는 apps/api 이다.
#   ops/run_engine.sh 의 검증된 런타임 계약(PYTHONPATH=apps/api · cwd=apps/api · uvicorn app.main:app)을 그대로 재현.
FROM python:3.12-slim

# 런타임 환경: 출력 버퍼링 해제(로그 즉시), pyc 미생성, pip 캐시 억제.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # ★핵심: 절대 import `app.*` 가 해석되도록 임포트 루트 고정.
    PYTHONPATH=/app/apps/api

WORKDIR /app

# 의존성 설치: pyproject.toml 만 먼저 복사해 레이어 캐시 활용(소스 변경 시 재설치 회피).
# pyproject 에 [build-system]/packages 정의가 없어 `pip install .` 은 패키지를 못 찾으므로,
# 의존성만 설치하고 코드는 작업트리(PYTHONPATH=apps/api)에서 구동한다(ops/run_engine.sh 와 동일 방식).
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        "fastapi>=0.115" \
        "uvicorn" \
        "sqlalchemy[asyncio]>=2.0" \
        "asyncpg" \
        "pydantic>=2" \
        "pydantic-settings>=2" \
        "alembic" \
        "redis" \
        "celery>=5.4" \
        "structlog" \
        "geoalchemy2"

# 소스 트리 복사(apps/, tools/, alembic 등). .dockerignore 가 .venv/__pycache__/.env 제외.
COPY . /app

# FastAPI 포트.
EXPOSE 8801

# alembic 은 apps/api 를 cwd 로 실행해야 script_location(apps/api/alembic)·prepend_sys_path(apps/api) 가 맞음.
WORKDIR /app/apps/api

# 엔진 기동(ops/run_engine.sh 와 동일 타깃). DB 마이그레이션은 deploy_engine.sh 가 컨테이너 안에서 선행 실행.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8801", "--workers", "1"]
