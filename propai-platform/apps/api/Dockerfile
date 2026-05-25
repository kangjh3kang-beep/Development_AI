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

# 의존성 설치
COPY --chown=propai:propai requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사 및 권한 설정
COPY --chown=propai:propai . .
RUN mkdir -p /app/uploads && chown -R propai:propai /app/uploads

# 보안: 비루트 사용자로 전환
USER propai

# 헬스체크 설정
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
