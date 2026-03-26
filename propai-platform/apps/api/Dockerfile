FROM python:3.12-slim AS base

# 보안: non-root 사용자
RUN groupadd -r propai && useradd -r -g propai -u 1001 propai

WORKDIR /app

# 의존성 설치
COPY apps/api/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사 (모노레포 루트 기준)
COPY --chown=propai:propai . .

# 불필요한 도구 제거
RUN apt-get purge -y curl wget 2>/dev/null; apt-get autoremove -y 2>/dev/null; rm -rf /var/lib/apt/lists/*

USER propai

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]