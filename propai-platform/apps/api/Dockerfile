# Final Production Stage
FROM python:3.12-slim

# 보안: 비루트 사용자 생성
RUN groupadd -g 1001 propai && \
    useradd -m -u 1001 -g propai propai

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    gcc g++ gdal-bin libgdal-dev libpq-dev \
    libspatialindex-dev libgeos-dev libproj-dev \
    curl && rm -rf /var/lib/apt/lists/*

ENV GDAL_VERSION=3.9.3
ENV PYTHONUNBUFFERED=1

# 의존성 설치 (캐싱 최적화)
COPY --chown=propai:propai apps/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 전체 소스 복사 (packages 포함 — 모노레포 의존성)
COPY --chown=propai:propai packages/ ./packages/
COPY --chown=propai:propai apps/__init__.py ./apps/__init__.py
COPY --chown=propai:propai apps/api/ ./apps/api/

# 업로드 디렉토리 설정
RUN mkdir -p /app/uploads && chown -R propai:propai /app

# 보안: 비루트 사용자로 전환
USER propai

# 헬스체크 설정
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
