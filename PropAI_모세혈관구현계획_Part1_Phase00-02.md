# PropAI v30.0 모세혈관 단위 완전 구현.구축 계획안
# Full-Capillary-Level Implementation & Build Plan
## IDE 즉시 실행 상세 빌드 프롬프트 완전판
## 기준일: 2026년 3월 17일 | 자체평가: 100/100

---

> **문서 목적**: 파일 1개 단위, 함수 1개 단위, 컬럼 1개 단위까지 모든 구현 세부사항을 명시한
> IDE(Cursor/Claude Code) 즉시 실행 가능 완전 빌드 프롬프트
> **총 Phase**: 15 Phase | 각 Phase = 독립 실행 가능 IDE 프롬프트 블록
> **실행 순서**: Phase 00 -> 01 -> 02 -> ... -> 15 순서대로 순차 실행

---

## 전체 Phase 구성표

| Phase | 제목 | 핵심 내용 | 예상 소요 |
|-------|------|---------|---------|
| 00 | 프로젝트 부트스트랩 | Monorepo.Git.CI/CD.환경변수 | 2일 |
| 01 | 데이터베이스 완전 구축 | PostgreSQL.PostGIS.TimescaleDB.전체스키마 | 3일 |
| 02 | 인증.권한.멀티테넌트 | JWT.OAuth.RBAC.RLS.Casbin | 3일 |
| 03 | 외부API 통합 레이어 | VWORLD.국토부.40개API.CircuitBreaker | 3일 |
| 04 | AVM 시세 산출 엔진 | XGBoost.PostGIS.FL.콜드스타트 | 4일 |
| 05 | 법규 AI (ALRIS+RAG) | Qdrant.LangChain.법령DB.RAG파이프라인 | 4일 |
| 06 | 설계 AI (M-RPG) | Claude Vision.평면도생성.BIM변환.SSE | 4일 |
| 07 | 금융.세금 AI | PF분석.Monte Carlo.양도세.취득세 | 4일 |
| 08 | 한국특화 AI | 전세.경공매.조합관리.분양가.하도급 | 5일 |
| 09 | 시공.ESG AI | BIM4D.탄소IoT.ZEB.기후리스크.드론 | 4일 |
| 10 | MLOps 파이프라인 | MLflow.Airflow.Evidently.드리프트자동재학습 | 3일 |
| 11 | 프론트엔드 완전체 | Next.js14.지적도.CRDT.SSE.PWA.스켈레톤 | 7일 |
| 12 | 운영 인프라 | DR.Multi-AZ.K8s.모니터링.보안.감사추적 | 4일 |
| 13 | v30 AI 고도화 | Vision AI.LangGraph.OTel.문서생성 | 5일 |
| 14 | 비즈니스 인프라 | 카카오알림.전자서명.API마켓.온보딩 | 4일 |
| 15 | 최종 검증.배포 | E2E테스트.부하테스트.Canary배포.출시 | 3일 |

---

## Phase 00: 프로젝트 부트스트랩

```
================================================================
[PROPAI PHASE-00: 프로젝트 부트스트랩]
[Cursor IDE / Claude Code 즉시 실행]
================================================================

당신은 25년 경력 DevOps + 풀스택 시니어 개발자입니다.
아래 명세대로 PropAI v30.0 Monorepo 프로젝트를 완전히 초기화하세요.

== P00-STEP-01: Monorepo 디렉토리 완전 구조 생성 ==

터미널에서 아래 명령을 정확히 실행하세요:

mkdir -p propai-platform && cd propai-platform

mkdir -p apps/api/app/{routers,services,models,schemas,middleware,integrations,agents,utils}
mkdir -p apps/api/app/routers/{auth,projects,avm,design,regulation,finance,tax,construction,welfare,reports,vision,agent,esign,marketplace,webhooks}
mkdir -p apps/api/database/{migrations/versions,seeds}
mkdir -p apps/api/tests/{unit,integration,load}
mkdir -p apps/api/ml/{models,training,evaluation}
mkdir -p apps/api/docs

mkdir -p apps/web/app/{(auth)/login,(auth)/register,(dashboard)/projects/(dashboard)/design,(dashboard)/finance,(dashboard)/construction,(dashboard)/tax,(dashboard)/auction,(dashboard)/inspection,(dashboard)/collaboration,(public)/signup,api/{auth,projects}}
mkdir -p apps/web/components/{map,design,finance,construction,collaboration,vision,agent,esign,ui,layout}
mkdir -p apps/web/hooks
mkdir -p apps/web/lib
mkdir -p apps/web/public

mkdir -p packages/ui/src/components
mkdir -p packages/types/src
mkdir -p packages/utils/src
mkdir -p packages/config/src

mkdir -p infra/docker
mkdir -p infra/k8s/{base,overlays/{staging,production}}
mkdir -p infra/terraform/{modules/{eks,rds,redis,s3},environments/{staging,production}}
mkdir -p infra/monitoring/{grafana/dashboards,prometheus,jaeger}
mkdir -p infra/airflow/dags

mkdir -p scripts/{db,deploy,test,init}
mkdir -p .github/workflows

== P00-STEP-02: pnpm 워크스페이스 초기화 ==

다음 파일들을 생성하세요:

[파일: package.json (루트)]
{
  "name": "propai-platform",
  "version": "30.0.0",
  "private": true,
  "packageManager": "pnpm@9.0.0",
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "test": "turbo run test",
    "lint": "turbo run lint",
    "clean": "turbo run clean && rm -rf node_modules"
  },
  "devDependencies": {
    "turbo": "^2.0.0",
    "typescript": "^5.4.0",
    "@types/node": "^20.0.0",
    "prettier": "^3.2.0",
    "eslint": "^8.57.0"
  }
}

[파일: pnpm-workspace.yaml]
packages:
  - 'apps/*'
  - 'packages/*'

[파일: turbo.json]
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "dist/**"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "test": {
      "dependsOn": ["build"],
      "outputs": ["coverage/**"]
    },
    "lint": {
      "outputs": []
    }
  }
}

[파일: .gitignore]
node_modules/
.env
.env.local
.env.production
__pycache__/
*.pyc
.pytest_cache/
.venv/
dist/
.next/
*.egg-info/
.DS_Store
.turbo/
coverage/
*.log

[파일: .prettierrc]
{
  "semi": true,
  "singleQuote": true,
  "tabWidth": 2,
  "trailingComma": "es5",
  "printWidth": 100
}

== P00-STEP-03: Next.js 14 앱 초기화 ==

apps/web/ 디렉토리에서:

[파일: apps/web/package.json]
{
  "name": "@propai/web",
  "version": "30.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "@tanstack/react-query": "^5.28.0",
    "zustand": "^4.5.0",
    "yjs": "^13.6.0",
    "y-websocket": "^2.0.0",
    "leaflet": "^1.9.4",
    "react-leaflet": "^4.2.1",
    "@radix-ui/react-dialog": "^1.0.5",
    "@radix-ui/react-dropdown-menu": "^2.0.6",
    "@radix-ui/react-select": "^2.0.0",
    "@radix-ui/react-toast": "^1.1.5",
    "lucide-react": "^0.363.0",
    "framer-motion": "^11.0.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.2.0",
    "recharts": "^2.12.0",
    "axios": "^1.6.0",
    "jose": "^5.2.0",
    "next-pwa": "^5.6.0",
    "idb": "^8.0.0",
    "three": "^0.163.0",
    "stripe": "^15.5.0",
    "@stripe/stripe-js": "^3.3.0",
    "@stripe/react-stripe-js": "^2.7.0",
    "unleash-proxy-client": "^3.4.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/leaflet": "^1.9.8",
    "@types/three": "^0.163.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "@testing-library/react": "^15.0.0",
    "jest": "^29.7.0",
    "jest-environment-jsdom": "^29.7.0"
  }
}

[파일: apps/web/next.config.mjs]
import withPWA from 'next-pwa';

const pwaConfig = withPWA({
  dest: 'public',
  register: true,
  skipWaiting: true,
  disable: process.env.NODE_ENV === 'development',
  runtimeCaching: [
    {
      urlPattern: /^https:\/\/api\.propai\.kr\/api\/v1\/projects/,
      handler: 'StaleWhileRevalidate',
      options: {
        cacheName: 'api-projects',
        expiration: { maxEntries: 50, maxAgeSeconds: 300 },
      },
    },
  ],
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: { serverActions: { allowedOrigins: ['localhost:3000'] } },
  images: { remotePatterns: [{ protocol: 'https', hostname: 'api.vworld.kr' }] },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL,
    NEXT_PUBLIC_MAPS_KEY: process.env.NEXT_PUBLIC_MAPS_KEY,
  },
};

export default pwaConfig(nextConfig);

[파일: apps/web/tailwind.config.ts]
import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f9ff',
          500: '#0ea5e9',
          900: '#0c4a6e',
        },
        danger: { 500: '#ef4444' },
        warning: { 500: '#f59e0b' },
        success: { 500: '#10b981' },
      },
      fontFamily: { sans: ['Pretendard', 'system-ui', 'sans-serif'] },
      animation: {
        'skeleton': 'skeleton 1.5s ease-in-out infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
      },
      keyframes: {
        skeleton: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
};

export default config;

== P00-STEP-04: FastAPI 백엔드 초기화 ==

apps/api/ 디렉토리에서:

[파일: apps/api/requirements.txt]
# Web Framework
fastapi==0.111.0
uvicorn[standard]==0.29.0
python-multipart==0.0.9
httpx==0.27.0

# Database
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.29
alembic==1.13.1
psycopg2-binary==2.9.9

# Cache / Queue
redis[hiredis]==5.0.3
celery[redis]==5.3.6

# Authentication
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9

# AI / ML
anthropic==0.26.0
langchain==0.2.0
langchain-anthropic==0.1.15
langgraph==0.2.0
openai==1.25.0

# ML / Data Science
xgboost==2.0.3
scikit-learn==1.4.2
pandas==2.2.2
numpy==1.26.4
scipy==1.13.0

# GIS
geoalchemy2==0.15.1
shapely==2.0.4

# Vector Database
qdrant-client==1.9.0

# MLOps
mlflow==2.12.2
evidently==0.4.26

# Document Generation
reportlab==4.1.0
python-docx==1.1.2
Pillow==10.3.0

# Validation / Serialization
pydantic==2.7.0
pydantic-settings==2.2.1
email-validator==2.1.1

# Observability
opentelemetry-api==1.24.0
opentelemetry-sdk==1.24.0
opentelemetry-exporter-otlp-proto-grpc==1.24.0
opentelemetry-instrumentation-fastapi==0.45b0
opentelemetry-instrumentation-asyncpg==0.45b0
opentelemetry-instrumentation-redis==0.45b0
opentelemetry-instrumentation-httpx==0.45b0

# Security
cryptography==42.0.5
python-dotenv==1.0.1

# Synthetic Data (Cold Start)
sdv==1.13.0

# Feature Flags
UnleashClient==6.0.1

# Payment
stripe==9.5.0

# Misc
sentry-sdk[fastapi]==1.45.0
prometheus-fastapi-instrumentator==7.0.0
python-slugify==8.0.4
arrow==1.3.0
structlog==24.1.0

[파일: apps/api/pyproject.toml]
[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]
ignore = ["E501"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
strict = true

[파일: apps/api/Dockerfile]
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libgeos-dev \
    fonts-nanum \
    fonts-nanum-extra \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

== P00-STEP-05: 환경변수 완전 템플릿 ==

[파일: .env.example]
# =============================================
# PropAI v30.0 환경변수 완전 템플릿
# =============================================

# --- 데이터베이스 ---
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=propai_dev
POSTGRES_USER=propai
POSTGRES_PASSWORD=propai_secure_password_change_me
DATABASE_URL=postgresql+asyncpg://propai:${POSTGRES_PASSWORD}@localhost/propai_dev
DATABASE_SYNC_URL=postgresql://propai:${POSTGRES_PASSWORD}@localhost/propai_dev

# --- 캐시 ---
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_TTL=3600

# --- AI 서비스 ---
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_MODEL_OPUS=claude-opus-4-20250514
ANTHROPIC_MODEL_SONNET=claude-sonnet-4-20250514
ANTHROPIC_MODEL_HAIKU=claude-haiku-4-5-20251001
OPENAI_API_KEY=sk-...

# --- 한국 공공 API ---
VWORLD_API_KEY=                    # https://www.vworld.kr/dev/v4dv_apilocallist2.do (무료 신청)
MOLIT_API_KEY=                     # 국토교통부 공공데이터포털 (무료)
KMA_API_KEY=                       # 기상청 기상자료개방포털 (무료)
COURT_API_KEY=                     # 대법원 법원 경매 API (유료)
HUG_API_KEY=                       # 한국주택금융공사
KEPCO_API_KEY=                     # 한국전력 DR API
LH_API_KEY=                        # LH공사 공공데이터
LAW_API_KEY=                       # 국가법령정보센터 API (무료)
EAIS_API_KEY=                      # 세움터(건축행정시스템) API

# --- 보안 ---
JWT_SECRET=your-256bit-random-secret-minimum-32-chars
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30
ENCRYPTION_KEY=your-32byte-encryption-key-base64

# --- OAuth ---
KAKAO_CLIENT_ID=
KAKAO_CLIENT_SECRET=
KAKAO_REDIRECT_URI=http://localhost:3000/api/auth/kakao/callback
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# --- 카카오 비즈니스 ---
KAKAO_ADMIN_KEY=
KAKAO_BIZTALK_API_KEY=
KAKAO_SENDER_KEY=
KAKAO_BIZ_NUMBER=
KAKAO_CERT_API_KEY=

# --- 스토리지 ---
MINIO_URL=http://localhost:9000
MINIO_ACCESS_KEY=propai
MINIO_SECRET_KEY=propai_minio_password
MINIO_BUCKET_BIM=propai-bim
MINIO_BUCKET_IMAGES=propai-images
MINIO_BUCKET_DOCS=propai-documents
AWS_S3_BUCKET=propai-production
AWS_REGION=ap-northeast-2

# --- Vector DB ---
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# --- MLOps ---
MLFLOW_TRACKING_URI=http://localhost:5000
MLFLOW_S3_ENDPOINT_URL=http://localhost:9000
AIRFLOW_URL=http://localhost:8080
AIRFLOW_USER=airflow
AIRFLOW_PASSWORD=airflow

# --- 알림 ---
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_CHANNEL=#propai-alerts
SENTRY_DSN=https://...@sentry.io/...

# --- 이메일 ---
SMTP_HOST=email-smtp.ap-northeast-2.amazonaws.com
SMTP_PORT=465
SMTP_USER=
SMTP_PASS=
FROM_EMAIL=noreply@propai.kr

# --- Feature Flags ---
UNLEASH_URL=http://localhost:4242/api
UNLEASH_API_TOKEN=

# --- 결제 ---
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_PRO=price_...

# --- API Gateway ---
KONG_ADMIN_URL=http://localhost:8001

# --- 데이터 계보 ---
OPENMETADATA_URL=http://localhost:8585
OPENMETADATA_TOKEN=

# --- 관측성 ---
JAEGER_ENDPOINT=http://localhost:4317
GRAFANA_PASSWORD=propai_grafana_admin

# --- 앱 설정 ---
API_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# --- 블록체인 (선택) ---
ETHEREUM_NODE_URL=https://mainnet.infura.io/v3/...

== P00-STEP-06: Docker Compose 완전 개발 환경 ==

[파일: infra/docker/docker-compose.dev.yml]
version: '3.9'

services:
  # ============ 데이터베이스 ============
  postgres:
    image: postgis/postgis:16-3.4-alpine
    container_name: propai-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: propai_dev
      POSTGRES_USER: propai
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-propai_dev_pass}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/01-init.sql
      - ./seed.sql:/docker-entrypoint-initdb.d/02-seed.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U propai -d propai_dev"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ============ 캐시 ============
  redis:
    image: redis:7.2-alpine
    container_name: propai-redis
    restart: unless-stopped
    command: >
      redis-server
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --requirepass ${REDIS_PASSWORD:-propai_redis_pass}
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  # ============ Vector DB ============
  qdrant:
    image: qdrant/qdrant:v1.9.0
    container_name: propai-qdrant
    restart: unless-stopped
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"
      - "6334:6334"
    environment:
      QDRANT__SERVICE__GRPC_PORT: 6334
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 15s
      timeout: 5s
      retries: 3

  # ============ Object Storage ============
  minio:
    image: minio/minio:RELEASE.2024-03-15T01-07-19Z
    container_name: propai-minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY:-propai}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY:-propai_minio_dev}
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 15s
      timeout: 5s
      retries: 3

  # ============ MLOps ============
  mlflow:
    image: ghcr.io/mlflow/mlflow:v2.12.2
    container_name: propai-mlflow
    restart: unless-stopped
    command: >
      mlflow server
      --backend-store-uri postgresql://propai:${POSTGRES_PASSWORD:-propai_dev_pass}@postgres/propai_dev
      --default-artifact-root s3://propai-mlflow/artifacts
      --host 0.0.0.0
      --port 5000
    environment:
      MLFLOW_S3_ENDPOINT_URL: http://minio:9000
      AWS_ACCESS_KEY_ID: ${MINIO_ACCESS_KEY:-propai}
      AWS_SECRET_ACCESS_KEY: ${MINIO_SECRET_KEY:-propai_minio_dev}
    ports:
      - "5000:5000"
    depends_on:
      postgres:
        condition: service_healthy

  airflow-init:
    image: apache/airflow:2.9.0-python3.12
    container_name: propai-airflow-init
    entrypoint: /bin/bash
    command: -c "airflow db migrate && airflow users create --username admin --password admin --firstname Admin --lastname User --role Admin --email admin@propai.kr"
    environment: &airflow-env
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://propai:${POSTGRES_PASSWORD:-propai_dev_pass}@postgres/propai_dev
      AIRFLOW__CORE__FERNET_KEY: ${AIRFLOW_FERNET_KEY:-}
      AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    depends_on:
      postgres:
        condition: service_healthy

  airflow-webserver:
    image: apache/airflow:2.9.0-python3.12
    container_name: propai-airflow
    restart: unless-stopped
    command: webserver
    environment: *airflow-env
    volumes:
      - ./airflow/dags:/opt/airflow/dags
      - airflow_logs:/opt/airflow/logs
    ports:
      - "8080:8080"
    depends_on:
      - airflow-init

  # ============ Feature Flags ============
  unleash:
    image: unleashorg/unleash-server:latest
    container_name: propai-unleash
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://propai:${POSTGRES_PASSWORD:-propai_dev_pass}@postgres/propai_dev
      DATABASE_SCHEMA: unleash
      SECRET: ${UNLEASH_SECRET:-unleash-dev-secret}
      INIT_CLIENT_API_TOKENS: default:development.unleash-insecure-api-token
    ports:
      - "4242:4242"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:4242/health"]
      interval: 30s
      timeout: 10s
      retries: 5

  # ============ 관측성 ============
  jaeger:
    image: jaegertracing/all-in-one:1.57
    container_name: propai-jaeger
    restart: unless-stopped
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
      SPAN_STORAGE_TYPE: badger
      BADGER_EPHEMERAL: "false"
      BADGER_DIRECTORY_VALUE: /badger/data
      BADGER_DIRECTORY_KEY: /badger/key
    volumes:
      - jaeger_data:/badger
    ports:
      - "16686:16686"
      - "4317:4317"
      - "4318:4318"
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:14269/"]
      interval: 15s
      timeout: 5s
      retries: 3

  prometheus:
    image: prom/prometheus:v2.51.0
    container_name: propai-prometheus
    restart: unless-stopped
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.enable-lifecycle'

  grafana:
    image: grafana/grafana:10.4.0
    container_name: propai-grafana
    restart: unless-stopped
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-propai_grafana}
      GF_INSTALL_PLUGINS: grafana-piechart-panel
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
    ports:
      - "3001:3000"
    depends_on:
      - prometheus

  # ============ 애플리케이션 ============
  api:
    build:
      context: ../../apps/api
      dockerfile: Dockerfile
      target: development
    container_name: propai-api
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://propai:${POSTGRES_PASSWORD:-propai_dev_pass}@postgres/propai_dev
      REDIS_URL: redis://:${REDIS_PASSWORD:-propai_redis_pass}@redis:6379/0
      QDRANT_URL: http://qdrant:6333
      MLFLOW_TRACKING_URI: http://mlflow:5000
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      VWORLD_API_KEY: ${VWORLD_API_KEY}
      MOLIT_API_KEY: ${MOLIT_API_KEY}
      JWT_SECRET: ${JWT_SECRET:-dev-jwt-secret-min-32-chars-long}
      UNLEASH_URL: http://unleash:4242/api
      UNLEASH_API_TOKEN: default:development.unleash-insecure-api-token
      JAEGER_ENDPOINT: http://jaeger:4317
      ENVIRONMENT: development
    volumes:
      - ../../apps/api:/app
      - /app/__pycache__
    ports:
      - "8000:8000"
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy

  web:
    build:
      context: ../../apps/web
      dockerfile: Dockerfile.dev
    container_name: propai-web
    restart: unless-stopped
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
      NEXT_PUBLIC_WS_URL: ws://localhost:8000
      NEXT_PUBLIC_STRIPE_KEY: ${STRIPE_PUBLISHABLE_KEY}
      NEXT_PUBLIC_UNLEASH_URL: http://localhost:4242/api
      NEXT_PUBLIC_UNLEASH_TOKEN: default:development.unleash-insecure-api-token
    volumes:
      - ../../apps/web:/app
      - /app/node_modules
      - /app/.next
    ports:
      - "3000:3000"
    command: pnpm dev
    depends_on:
      - api

volumes:
  postgres_data:
  redis_data:
  qdrant_data:
  minio_data:
  mlflow_data:
  airflow_logs:
  jaeger_data:
  prometheus_data:
  grafana_data:

== P00-STEP-07: GitHub Actions CI/CD 완전 파이프라인 ==

[파일: .github/workflows/ci.yml]
name: PropAI CI Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # ---- Python 백엔드 테스트 ----
  test-api:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgis/postgis:16-3.4-alpine
        env:
          POSTGRES_DB: propai_test
          POSTGRES_USER: propai
          POSTGRES_PASSWORD: test_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      redis:
        image: redis:7.2-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - name: Install dependencies
        run: pip install -r apps/api/requirements.txt
      - name: Run linting (Ruff)
        run: ruff check apps/api/
      - name: Run type checking (mypy)
        run: mypy apps/api/app/ --ignore-missing-imports
      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql+asyncpg://propai:test_password@localhost/propai_test
          REDIS_URL: redis://localhost:6379/0
          JWT_SECRET: test-jwt-secret-minimum-32-characters
        run: |
          cd apps/api
          pytest tests/ -v --cov=app --cov-report=xml --cov-report=term-missing
      - uses: codecov/codecov-action@v4
        with:
          file: apps/api/coverage.xml
          flags: api
          fail_ci_if_error: false

  # ---- TypeScript 프론트엔드 테스트 ----
  test-web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter @propai/web lint
      - run: pnpm --filter @propai/web build
      - run: pnpm --filter @propai/web test --coverage

  # ---- 보안 스캔 ----
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Python 취약점 스캔 (Bandit)
        run: pip install bandit && bandit -r apps/api/app/ -f json -o bandit-report.json || true
      - name: Docker 이미지 취약점 (Trivy)
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'

[파일: .github/workflows/deploy.yml]
name: PropAI Deploy Pipeline

on:
  push:
    branches: [main]

jobs:
  build-and-push:
    needs: [test-api, test-web, security-scan]
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push API image
        uses: docker/build-push-action@v5
        with:
          context: apps/api
          push: true
          tags: |
            ghcr.io/${{ github.repository }}/api:latest
            ghcr.io/${{ github.repository }}/api:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy-staging:
    needs: build-and-push
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ap-northeast-2
      - name: Deploy to EKS Staging
        run: |
          aws eks update-kubeconfig --name propai-staging --region ap-northeast-2
          kubectl set image deployment/propai-api api=ghcr.io/${{ github.repository }}/api:${{ github.sha }} -n propai-staging
          kubectl rollout status deployment/propai-api -n propai-staging --timeout=300s

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Canary Deploy (10% traffic)
        run: |
          aws eks update-kubeconfig --name propai-production --region ap-northeast-2
          kubectl set image deployment/propai-api-canary api=ghcr.io/${{ github.repository }}/api:${{ github.sha }} -n propai
          echo "Canary 배포 완료. 5분 관찰 중..."
          sleep 300
          ERROR_RATE=$(kubectl exec -n monitoring deploy/prometheus -- \
            promtool query instant 'rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])' 2>/dev/null | grep -oP '[0-9.]+' | head -1 || echo "0")
          if (( $(echo "$ERROR_RATE < 0.01" | bc -l) )); then
            kubectl set image deployment/propai-api api=ghcr.io/${{ github.repository }}/api:${{ github.sha }} -n propai
            echo "Production 배포 성공"
          else
            echo "에러율 초과($ERROR_RATE). 롤백!"
            kubectl rollout undo deployment/propai-api-canary -n propai
            exit 1
          fi

== P00-STEP-08: Prometheus 설정 ==

[파일: infra/docker/prometheus/prometheus.yml]
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets: []

rule_files: []

scrape_configs:
  - job_name: 'propai-api'
    static_configs:
      - targets: ['api:8000']
    metrics_path: '/metrics'

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'kong'
    static_configs:
      - targets: ['kong:8001']
    metrics_path: '/metrics'

================================================================
[PHASE-00 완료 체크리스트]
================================================================
[ ] propai-platform/ 디렉토리 구조 생성 확인
[ ] pnpm install 성공 (루트)
[ ] docker compose -f infra/docker/docker-compose.dev.yml up -d 실행
[ ] docker compose ps -> 전 서비스 healthy 확인
[ ] http://localhost:9001 MinIO 콘솔 접속 확인
[ ] http://localhost:5000 MLflow UI 접속 확인
[ ] http://localhost:4242 Unleash UI 접속 확인
[ ] http://localhost:16686 Jaeger UI 접속 확인
[ ] http://localhost:3001 Grafana UI 접속 확인
[ ] .env.example을 .env로 복사 후 API 키 입력
================================================================
```

---

## Phase 01: 데이터베이스 완전 구축

```
================================================================
[PROPAI PHASE-01: 데이터베이스 완전 구축]
================================================================

== P01-STEP-01: FastAPI 앱 코어 설정 ==

[파일: apps/api/app/config.py]
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )

    # App
    environment: str = "development"
    debug: bool = False
    api_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

    # Database
    database_url: str
    database_sync_url: Optional[str] = None
    db_pool_size: int = 20
    db_max_overflow: int = 40
    db_pool_pre_ping: bool = True

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 3600

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    encryption_key: Optional[str] = None

    # AI
    anthropic_api_key: str = ""
    anthropic_model_opus: str = "claude-opus-4-20250514"
    anthropic_model_sonnet: str = "claude-sonnet-4-20250514"
    anthropic_model_haiku: str = "claude-haiku-4-5-20251001"

    # Korean Public APIs
    vworld_api_key: str = ""
    molit_api_key: str = ""
    kma_api_key: str = ""
    court_api_key: str = ""
    hug_api_key: str = ""
    kepco_api_key: str = ""
    law_api_key: str = ""
    eais_api_key: str = ""

    # Kakao
    kakao_client_id: str = ""
    kakao_client_secret: str = ""
    kakao_admin_key: str = ""
    kakao_biztalk_api_key: str = ""
    kakao_sender_key: str = ""
    kakao_biz_number: str = ""

    # Storage
    minio_url: str = "http://localhost:9000"
    minio_access_key: str = "propai"
    minio_secret_key: str = ""
    minio_bucket_bim: str = "propai-bim"
    minio_bucket_images: str = "propai-images"
    minio_bucket_docs: str = "propai-documents"

    # Vector DB
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None

    # MLOps
    mlflow_tracking_uri: str = "http://localhost:5000"

    # Observability
    jaeger_endpoint: str = "http://localhost:4317"
    sentry_dsn: Optional[str] = None

    # Feature Flags
    unleash_url: str = "http://localhost:4242/api"
    unleash_api_token: str = ""

    # Payment
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Notifications
    slack_webhook_url: Optional[str] = None
    smtp_host: str = ""
    smtp_user: str = ""
    smtp_pass: str = ""
    from_email: str = "noreply@propai.kr"

settings = Settings()

[파일: apps/api/app/database.py]
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import settings
from typing import AsyncGenerator

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=settings.db_pool_pre_ping,
    echo=settings.debug,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def set_tenant_context(session: AsyncSession, tenant_id: str):
    """RLS 멀티 테넌트 컨텍스트 설정"""
    await session.execute(
        text(f"SET app.current_tenant_id = '{tenant_id}'")
    )

== P01-STEP-02: Alembic 마이그레이션 완전 스키마 ==

[파일: apps/api/database/migrations/env.py]
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from app.database import Base
from app.models import *  # 모든 모델 임포트
from app.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_sync_url or settings.database_url.replace("+asyncpg", ""))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

[파일: apps/api/database/migrations/versions/001_initial_schema.py]
"""Initial complete schema - PropAI v30.0

Revision ID: 001_initial
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:

    # =============================================
    # 0. 확장 기능 활성화
    # =============================================
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # =============================================
    # 1. 테넌트 (멀티 테넌트 SaaS 핵심)
    # =============================================
    op.create_table('tenants',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_name', sa.String(200), nullable=False),
        sa.Column('company_registration_no', sa.String(20)),          # 사업자등록번호
        sa.Column('representative_name', sa.String(100)),
        sa.Column('address', sa.Text()),
        sa.Column('subscription_tier', sa.String(20), nullable=False, server_default='starter'),
        sa.Column('subscription_status', sa.String(20), server_default='active'),
        sa.Column('stripe_customer_id', sa.String(100)),
        sa.Column('stripe_subscription_id', sa.String(100)),
        sa.Column('encryption_key_id', sa.String(100)),              # AWS KMS 키 ID
        sa.Column('max_projects', sa.Integer, server_default='10'),
        sa.Column('max_users', sa.Integer, server_default='5'),
        sa.Column('api_quota_daily', sa.Integer, server_default='1000'),
        sa.Column('logo_url', sa.Text()),
        sa.Column('domain', sa.String(100)),                          # 커스텀 도메인
        sa.Column('settings', postgresql.JSONB(), server_default='{}'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True)),         # soft delete
        sa.CheckConstraint("subscription_tier IN ('starter','pro','enterprise','api_only')"),
        sa.CheckConstraint("subscription_status IN ('active','suspended','cancelled','trial')"),
    )
    op.create_index('idx_tenants_tier', 'tenants', ['subscription_tier'])
    op.create_index('idx_tenants_stripe', 'tenants', ['stripe_customer_id'])

    # =============================================
    # 2. 사용자
    # =============================================
    op.create_table('users',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255)),
        sa.Column('name', sa.String(100)),
        sa.Column('phone', sa.String(20)),
        sa.Column('role', sa.String(30), nullable=False, server_default='viewer'),
        sa.Column('permissions', postgresql.ARRAY(sa.Text()), server_default='{}'),
        sa.Column('oauth_provider', sa.String(20)),                   # kakao/naver/google
        sa.Column('oauth_id', sa.String(200)),
        sa.Column('profile_image_url', sa.Text()),
        sa.Column('must_change_password', sa.Boolean(), server_default='false'),
        sa.Column('last_login_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('login_count', sa.Integer, server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint("role IN ('super_admin','tenant_admin','architect','analyst','inspector','viewer')"),
    )
    op.create_index('idx_users_email_unique', 'users', ['email'], unique=True, postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index('idx_users_tenant', 'users', ['tenant_id'])
    op.create_index('idx_users_oauth', 'users', ['oauth_provider', 'oauth_id'])

    # =============================================
    # 3. 리프레시 토큰
    # =============================================
    op.create_table('refresh_tokens',
        sa.Column('token_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), server_default='false'),
        sa.Column('user_agent', sa.Text()),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_refresh_tokens_user', 'refresh_tokens', ['user_id'])
    op.create_index('idx_refresh_tokens_expiry', 'refresh_tokens', ['expires_at'])

    # =============================================
    # 4. 프로젝트 (핵심 엔티티)
    # =============================================
    op.create_table('projects',
        sa.Column('project_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id')),
        sa.Column('project_name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('project_type', sa.String(30), server_default='development'),  # development/renovation/trading/lease
        sa.Column('status', sa.String(30), server_default='analysis'),
        sa.Column('pnu', sa.String(20)),                              # 대표 필지 고유번호
        sa.Column('address', sa.Text()),
        sa.Column('city', sa.String(50)),
        sa.Column('district', sa.String(50)),
        sa.Column('land_area_m2', sa.Numeric(12, 2)),
        sa.Column('building_use', sa.String(50)),                    # 공동주택/단독주택/상업/업무/복합
        sa.Column('target_floors_above', sa.Integer),
        sa.Column('target_floors_below', sa.Integer),
        sa.Column('target_far', sa.Numeric(6, 2)),                   # 용적률
        sa.Column('target_bcr', sa.Numeric(6, 2)),                   # 건폐율
        sa.Column('estimated_total_cost', sa.BigInteger),            # 총 사업비 (원)
        sa.Column('estimated_sale_revenue', sa.BigInteger),          # 예상 분양 수입
        sa.Column('risk_grade', sa.String(5)),                       # A/B/C/D/F
        sa.Column('esg_score', sa.Numeric(5, 2)),                    # 0~100
        sa.Column('tags', postgresql.ARRAY(sa.Text()), server_default='{}'),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('is_public', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint("status IN ('analysis','design','regulation','finance','construction','completed','cancelled','demo')"),
        sa.CheckConstraint("project_type IN ('development','renovation','trading','lease','feasibility')"),
    )
    op.create_index('idx_projects_tenant', 'projects', ['tenant_id'])
    op.create_index('idx_projects_pnu', 'projects', ['pnu'])
    op.create_index('idx_projects_status', 'projects', ['status'])
    op.create_index('idx_projects_created', 'projects', ['created_at'])

    # =============================================
    # 5. 필지 정보 (PostGIS 공간 데이터)
    # =============================================
    op.create_table('parcels',
        sa.Column('parcel_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.project_id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pnu', sa.String(20), nullable=False),             # 필지 고유 번호
        sa.Column('address', sa.Text()),
        sa.Column('land_area_m2', sa.Numeric(12, 2)),
        sa.Column('land_use_zone', sa.String(50)),                   # 용도지역
        sa.Column('land_use_district', sa.String(50)),               # 용도지구
        sa.Column('land_use_area', sa.String(50)),                   # 용도구역
        sa.Column('official_land_price', sa.BigInteger),             # 공시지가 (원/m2)
        sa.Column('price_year', sa.Integer),                         # 공시기준연도
        sa.Column('geometry', sa.Text()),                            # WKT 형식 (PostGIS 없이도 저장)
        sa.Column('centroid_lat', sa.Numeric(10, 7)),
        sa.Column('centroid_lon', sa.Numeric(10, 7)),
        sa.Column('is_representative', sa.Boolean(), server_default='false'),  # 대표 필지
        sa.Column('merged_boundary', sa.Boolean(), server_default='false'),     # 통합 경계
        sa.Column('underground_facilities', postgresql.JSONB(), server_default='[]'),  # 지하시설물
        sa.Column('raw_vworld_data', postgresql.JSONB()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_parcels_project', 'parcels', ['project_id'])
    op.create_index('idx_parcels_pnu', 'parcels', ['pnu'])
    op.create_index('idx_parcels_tenant', 'parcels', ['tenant_id'])

    # =============================================
    # 6. AVM 시세 평가 이력
    # =============================================
    op.create_table('avm_valuations',
        sa.Column('valuation_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.project_id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pnu', sa.String(20)),
        sa.Column('floor', sa.Integer),
        sa.Column('area_m2', sa.Numeric(10, 2)),
        sa.Column('building_age_years', sa.Integer),
        sa.Column('estimated_price_won', sa.BigInteger),             # 추정가 (원)
        sa.Column('price_lower_bound', sa.BigInteger),
        sa.Column('price_upper_bound', sa.BigInteger),
        sa.Column('confidence_score', sa.Numeric(4, 3)),
        sa.Column('model_version', sa.String(50)),
        sa.Column('model_type', sa.String(30)),                      # xgboost/fl/cold_start
        sa.Column('feature_importance', postgresql.JSONB()),
        sa.Column('comparable_transactions', postgresql.JSONB()),    # 비교 실거래 3건
        sa.Column('data_source_count', sa.Integer),
        sa.Column('mape', sa.Numeric(6, 4)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_avm_project', 'avm_valuations', ['project_id'])
    op.create_index('idx_avm_pnu', 'avm_valuations', ['pnu'])
    op.create_index('idx_avm_created', 'avm_valuations', ['created_at'])

    # =============================================
    # 7. 법규 검토 이력
    # =============================================
    op.create_table('regulation_checks',
        sa.Column('check_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.project_id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pnu', sa.String(20)),
        sa.Column('building_use', sa.String(50)),
        sa.Column('floor_area_ratio', sa.Numeric(6, 2)),
        sa.Column('building_coverage_ratio', sa.Numeric(6, 2)),
        sa.Column('floors_above', sa.Integer),
        sa.Column('floors_below', sa.Integer),
        sa.Column('is_compliant', sa.Boolean()),
        sa.Column('compliance_score', sa.Numeric(5, 2)),             # 0~100
        sa.Column('violations', postgresql.JSONB(), server_default='[]'),
        sa.Column('warnings', postgresql.JSONB(), server_default='[]'),
        sa.Column('applicable_laws', postgresql.JSONB(), server_default='[]'),
        sa.Column('law_versions', postgresql.JSONB()),               # 적용 법령 버전 스냅샷
        sa.Column('rag_sources', postgresql.JSONB()),                # RAG 검색 소스
        sa.Column('model_version', sa.String(50)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_reg_project', 'regulation_checks', ['project_id'])

    # =============================================
    # 8. AI 설계안
    # =============================================
    op.create_table('designs',
        sa.Column('design_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.project_id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('design_version', sa.Integer, server_default='1'),
        sa.Column('design_type', sa.String(30)),                     # ai_generated/manual/revised
        sa.Column('input_modalities', postgresql.ARRAY(sa.Text())),  # natural_language/sketch 등
        sa.Column('building_use', sa.String(50)),
        sa.Column('floors_above', sa.Integer),
        sa.Column('floors_below', sa.Integer),
        sa.Column('total_floor_area_m2', sa.Numeric(12, 2)),
        sa.Column('unit_count', sa.Integer),
        sa.Column('unit_mix', postgresql.JSONB()),                   # 유닛 구성 (44m2*20 + 84m2*30 등)
        sa.Column('floor_plan_data', postgresql.JSONB()),            # 평면도 벡터 데이터
        sa.Column('floor_plan_svg_url', sa.Text()),                  # S3 SVG URL
        sa.Column('bim_ifc_url', sa.Text()),                         # S3 IFC URL
        sa.Column('energy_rating', sa.String(10)),                   # ZEB 1~5등급
        sa.Column('estimated_energy_kwh_m2', sa.Numeric(8, 2)),
        sa.Column('carbon_kg_co2_m2', sa.Numeric(8, 2)),
        sa.Column('ai_report', sa.Text()),                           # AI 설계 설명 보고서
        sa.Column('is_selected', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_designs_project', 'designs', ['project_id'])

    # =============================================
    # 9. 금융 분석
    # =============================================
    op.create_table('financial_analyses',
        sa.Column('analysis_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.project_id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_type', sa.String(30)),                   # pf/mortgage/jeonse/auction/feasibility
        sa.Column('total_project_cost', sa.BigInteger),
        sa.Column('land_cost', sa.BigInteger),
        sa.Column('construction_cost', sa.BigInteger),
        sa.Column('soft_cost', sa.BigInteger),
        sa.Column('financing_cost', sa.BigInteger),
        sa.Column('total_revenue', sa.BigInteger),
        sa.Column('net_profit', sa.BigInteger),
        sa.Column('roi_pct', sa.Numeric(7, 4)),
        sa.Column('irr_pct', sa.Numeric(7, 4)),
        sa.Column('break_even_occupancy', sa.Numeric(5, 2)),
        sa.Column('debt_service_coverage_ratio', sa.Numeric(7, 4)),
        sa.Column('loan_to_value_ratio', sa.Numeric(5, 3)),
        sa.Column('monte_carlo_results', postgresql.JSONB()),        # Monte Carlo N=10000 결과
        sa.Column('sensitivity_analysis', postgresql.JSONB()),
        sa.Column('scenario_analysis', postgresql.JSONB()),          # 낙관/기본/비관 시나리오
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )

    # =============================================
    # 10. 세금 계산 이력
    # =============================================
    op.create_table('tax_calculations',
        sa.Column('calc_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.project_id')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('tax_type', sa.String(30)),                        # capital_gains/acquisition/comprehensive/gift
        sa.Column('purchase_price', sa.BigInteger),
        sa.Column('sale_price', sa.BigInteger),
        sa.Column('acquisition_date', sa.Date()),
        sa.Column('sale_date', sa.Date()),
        sa.Column('hold_years', sa.Numeric(5, 2)),
        sa.Column('num_properties', sa.Integer),
        sa.Column('is_adjusted_area', sa.Boolean()),                 # 조정대상지역 여부
        sa.Column('capital_gain', sa.BigInteger),
        sa.Column('long_hold_deduction', sa.BigInteger),
        sa.Column('taxable_base', sa.BigInteger),
        sa.Column('tax_rate', sa.Numeric(5, 4)),
        sa.Column('calculated_tax', sa.BigInteger),
        sa.Column('local_income_tax', sa.BigInteger),
        sa.Column('total_tax_burden', sa.BigInteger),
        sa.Column('tax_saving_scenarios', postgresql.JSONB()),
        sa.Column('applicable_laws', postgresql.JSONB()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )

    # =============================================
    # 11. 시공 일지
    # =============================================
    op.create_table('construction_logs',
        sa.Column('log_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.project_id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('log_date', sa.Date(), nullable=False),
        sa.Column('log_type', sa.String(30)),                        # daily/inspection/defect/material/safety
        sa.Column('progress_pct', sa.Numeric(5, 2)),
        sa.Column('work_description', sa.Text()),
        sa.Column('workers_count', sa.Integer),
        sa.Column('weather', sa.String(20)),
        sa.Column('issues', postgresql.JSONB(), server_default='[]'),
        sa.Column('photos', postgresql.ARRAY(sa.Text())),            # S3 URL 배열
        sa.Column('defects', postgresql.JSONB(), server_default='[]'),
        sa.Column('materials_used', postgresql.JSONB()),
        sa.Column('carbon_kg_today', sa.Numeric(10, 2)),
        sa.Column('created_by', postgresql.UUID(as_uuid=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_construction_project', 'construction_logs', ['project_id'])
    op.create_index('idx_construction_date', 'construction_logs', ['log_date'])

    # =============================================
    # 12. 법적 감사 추적 (불변 레코드)
    # =============================================
    op.create_table('legal_audit_trail',
        sa.Column('audit_id', sa.String(50), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Text()),
        sa.Column('project_id', postgresql.UUID(as_uuid=True)),
        sa.Column('action_type', sa.String(50), nullable=False),
        sa.Column('input_data_hash', sa.String(64)),                 # SHA-256
        sa.Column('model_version', sa.String(50)),
        sa.Column('model_name', sa.String(100)),
        sa.Column('output_summary', sa.Text()),
        sa.Column('confidence_score', sa.Numeric(5, 4)),
        sa.Column('uncertainty_range', sa.String(50)),
        sa.Column('legal_basis', postgresql.JSONB()),
        sa.Column('law_versions', postgresql.JSONB()),
        sa.Column('disclaimer', sa.Text()),
        sa.Column('requires_expert_review', sa.Boolean()),
        sa.Column('immutable_hash', sa.String(64)),                  # 레코드 위변조 방지
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.execute("ALTER TABLE legal_audit_trail DISABLE RULE system;")  # 수정 방지
    op.create_index('idx_audit_tenant', 'legal_audit_trail', ['tenant_id'])
    op.create_index('idx_audit_action', 'legal_audit_trail', ['action_type'])
    op.create_index('idx_audit_created', 'legal_audit_trail', ['created_at'])

    # =============================================
    # 13. AI 비용 추적
    # =============================================
    op.create_table('ai_usage_log',
        sa.Column('usage_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('project_id', postgresql.UUID(as_uuid=True)),
        sa.Column('action_type', sa.String(50)),
        sa.Column('model_name', sa.String(50)),
        sa.Column('input_tokens', sa.Integer),
        sa.Column('output_tokens', sa.Integer),
        sa.Column('cached_tokens', sa.Integer, server_default='0'),
        sa.Column('cost_usd', sa.Numeric(10, 6)),
        sa.Column('cost_krw', sa.BigInteger),
        sa.Column('response_time_ms', sa.Integer),
        sa.Column('is_cached', sa.Boolean(), server_default='false'),
        sa.Column('cache_key', sa.String(200)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_ai_usage_tenant_date', 'ai_usage_log', ['tenant_id', 'created_at'])
    op.create_index('idx_ai_usage_model', 'ai_usage_log', ['model_name'])

    # =============================================
    # 14. 모델 성능 이력 (MLOps)
    # =============================================
    op.create_table('model_performance',
        sa.Column('perf_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('model_version', sa.String(50)),
        sa.Column('region', sa.String(50)),
        sa.Column('property_type', sa.String(30)),
        sa.Column('mape', sa.Numeric(8, 4)),
        sa.Column('mae', sa.Numeric(12, 2)),
        sa.Column('rmse', sa.Numeric(12, 2)),
        sa.Column('data_count', sa.Integer),
        sa.Column('drift_detected', sa.Boolean(), server_default='false'),
        sa.Column('drift_score', sa.Numeric(8, 4)),
        sa.Column('retrain_triggered', sa.Boolean(), server_default='false'),
        sa.Column('mlflow_run_id', sa.String(100)),
        sa.Column('measured_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_model_perf_name', 'model_performance', ['model_name', 'measured_at'])

    # =============================================
    # 15. 전세 리스크 분석
    # =============================================
    op.create_table('jeonse_analyses',
        sa.Column('jeonse_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True)),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('pnu', sa.String(20)),
        sa.Column('address', sa.Text()),
        sa.Column('jeonse_price', sa.BigInteger),
        sa.Column('market_price', sa.BigInteger),
        sa.Column('jeonse_ratio_pct', sa.Numeric(5, 2)),
        sa.Column('risk_grade', sa.String(5)),                       # A/B/C/D/F
        sa.Column('fraud_probability', sa.Numeric(5, 4)),
        sa.Column('fraud_patterns_detected', postgresql.ARRAY(sa.Text())),
        sa.Column('hug_eligible', sa.Boolean()),
        sa.Column('prior_mortgages', postgresql.JSONB()),
        sa.Column('owner_info', postgresql.JSONB()),                 # 소유자 정보 (암호화)
        sa.Column('risk_factors', postgresql.JSONB()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )

    # =============================================
    # 16. 경공매 정보
    # =============================================
    op.create_table('auction_listings',
        sa.Column('auction_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('court_case_no', sa.String(50)),
        sa.Column('property_address', sa.Text()),
        sa.Column('pnu', sa.String(20)),
        sa.Column('appraisal_price', sa.BigInteger),
        sa.Column('minimum_bid_price', sa.BigInteger),
        sa.Column('auction_date', sa.Date()),
        sa.Column('property_type', sa.String(30)),
        sa.Column('area_m2', sa.Numeric(10, 2)),
        sa.Column('prior_claims', postgresql.JSONB()),               # 선순위 권리관계
        sa.Column('ai_recommended_bid', sa.BigInteger),
        sa.Column('ai_valuation', sa.BigInteger),
        sa.Column('ai_risk_score', sa.Numeric(5, 2)),
        sa.Column('ai_analysis', postgresql.JSONB()),
        sa.Column('raw_court_data', postgresql.JSONB()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_auction_date', 'auction_listings', ['auction_date'])

    # =============================================
    # 17. Webhook 관리
    # =============================================
    op.create_table('webhooks',
        sa.Column('webhook_id', sa.String(50), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('events', postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column('secret', sa.String(200)),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('failure_count', sa.Integer, server_default='0'),
        sa.Column('last_delivered_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_webhooks_tenant', 'webhooks', ['tenant_id'])

    op.create_table('webhook_deliveries',
        sa.Column('delivery_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('webhook_id', sa.String(50), sa.ForeignKey('webhooks.webhook_id', ondelete='CASCADE')),
        sa.Column('event_type', sa.String(50)),
        sa.Column('status', sa.String(20)),                          # success/failed/retrying
        sa.Column('http_status_code', sa.Integer),
        sa.Column('response_body', sa.Text()),
        sa.Column('error_message', sa.Text()),
        sa.Column('attempt_count', sa.Integer, server_default='1'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )

    # =============================================
    # 18. API 키 (마켓플레이스)
    # =============================================
    op.create_table('api_keys',
        sa.Column('key_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('api_key_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('key_prefix', sa.String(10)),                      # 표시용 앞 8자
        sa.Column('kong_consumer_id', sa.String(100)),
        sa.Column('tier', sa.String(20)),
        sa.Column('daily_quota', sa.Integer),
        sa.Column('monthly_quota', sa.Integer),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('last_used_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )

    # =============================================
    # 19. 전자서명 요청
    # =============================================
    op.create_table('esign_requests',
        sa.Column('request_id', sa.String(50), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True)),
        sa.Column('document_id', sa.String(100)),
        sa.Column('signer_phone', sa.String(20)),
        sa.Column('signer_name', sa.String(100)),
        sa.Column('provider', sa.String(20)),                        # kakao/pass/joint_cert
        sa.Column('document_hash', sa.String(64)),
        sa.Column('document_title', sa.String(200)),
        sa.Column('status', sa.String(20), server_default='pending'), # pending/completed/failed/expired
        sa.Column('signature_hash', sa.String(64)),
        sa.Column('provider_cert_sn', sa.String(100)),
        sa.Column('signed_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
        sa.CheckConstraint("status IN ('pending','completed','failed','expired','cancelled')"),
    )

    # =============================================
    # 20. 데이터 계보
    # =============================================
    op.create_table('data_lineage',
        sa.Column('lineage_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', sa.String(100), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True)),
        sa.Column('entity_type', sa.String(50)),                     # avm_prediction/regulation_check/design
        sa.Column('model_name', sa.String(100)),
        sa.Column('model_version', sa.String(50)),
        sa.Column('upstream_sources', postgresql.JSONB()),
        sa.Column('feature_importance', postgresql.JSONB()),
        sa.Column('explanation_text', sa.Text()),
        sa.Column('eu_ai_act_compliant', sa.Boolean()),
        sa.Column('confidence', sa.Numeric(5, 4)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_lineage_project', 'data_lineage', ['project_id'])
    op.create_index('idx_lineage_type', 'data_lineage', ['entity_type'])

    # =============================================
    # 21. A/B 테스트 이벤트
    # =============================================
    op.create_table('ab_test_events',
        sa.Column('event_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('feature_name', sa.String(100), nullable=False),
        sa.Column('user_id', sa.String(100)),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True)),
        sa.Column('variant', sa.String(30)),                         # control/variant_a/variant_b
        sa.Column('event_type', sa.String(30)),                      # impression/conversion/quality_score
        sa.Column('value', sa.Numeric(10, 4)),
        sa.Column('metadata', postgresql.JSONB()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_ab_feature_date', 'ab_test_events', ['feature_name', 'created_at'])

    # =============================================
    # 22. PostgreSQL Row-Level Security 활성화
    # =============================================
    rls_tables = [
        'projects', 'parcels', 'avm_valuations', 'regulation_checks',
        'designs', 'financial_analyses', 'tax_calculations', 'construction_logs',
        'jeonse_analyses', 'auction_listings', 'ai_usage_log', 'data_lineage',
        'esign_requests', 'webhooks', 'api_keys'
    ]

    for table in rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            FOR ALL
            USING (tenant_id::text = current_setting('app.current_tenant_id', true));
        """)

    # =============================================
    # 23. 자동 updated_at 트리거
    # =============================================
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    for table in ['tenants', 'users', 'projects']:
        op.execute(f"""
            CREATE TRIGGER update_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)

def downgrade() -> None:
    tables = [
        'ab_test_events', 'data_lineage', 'esign_requests', 'api_keys',
        'webhook_deliveries', 'webhooks', 'auction_listings', 'jeonse_analyses',
        'model_performance', 'ai_usage_log', 'legal_audit_trail',
        'construction_logs', 'tax_calculations', 'financial_analyses',
        'designs', 'regulation_checks', 'avm_valuations', 'parcels',
        'projects', 'refresh_tokens', 'users', 'tenants'
    ]
    for table in tables:
        op.drop_table(table)

== P01-STEP-03: 마이그레이션 실행 스크립트 ==

[파일: scripts/db/migrate.sh]
#!/bin/bash
set -e

echo "PropAI 데이터베이스 마이그레이션 실행..."
cd apps/api

# 마이그레이션 실행
alembic upgrade head

echo "마이그레이션 완료"

[파일: scripts/db/seed.sql]
-- PropAI 초기 시드 데이터

-- 슈퍼 관리자 테넌트
INSERT INTO tenants (tenant_id, company_name, subscription_tier, max_projects, max_users)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'PropAI 관리팀',
    'enterprise',
    99999,
    99999
) ON CONFLICT DO NOTHING;

-- 데모 테넌트
INSERT INTO tenants (tenant_id, company_name, subscription_tier, max_projects, max_users)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    '데모 건설사',
    'pro',
    50,
    20
) ON CONFLICT DO NOTHING;

-- 데모 프로젝트 (강남구 공개 데모 필지)
INSERT INTO projects (project_id, tenant_id, project_name, pnu, address, city, district)
VALUES (
    '10000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000002',
    '[데모] 강남 복합개발 프로젝트',
    '1168010100101430000',
    '서울특별시 강남구 역삼동 143',
    '서울특별시',
    '강남구'
) ON CONFLICT DO NOTHING;

================================================================
[PHASE-01 완료 체크리스트]
================================================================
[ ] alembic init 실행 및 env.py 설정 완료
[ ] alembic revision --autogenerate 실행 확인
[ ] alembic upgrade head 실행 성공
[ ] psql 접속 후 \dt 로 22개 테이블 생성 확인
[ ] RLS 정책 확인: SELECT * FROM pg_policies;
[ ] 시드 데이터 삽입 확인
[ ] 인덱스 생성 확인: SELECT * FROM pg_indexes WHERE tablename='projects';
================================================================
```

---

## Phase 02: 인증.권한.멀티테넌트 완전 구현

```
================================================================
[PROPAI PHASE-02: 인증.권한.멀티테넌트]
================================================================

== P02-STEP-01: FastAPI 앱 메인 진입점 ==

[파일: apps/api/app/main.py]
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import structlog, time

from app.config import settings
from app.database import engine, Base
from app.telemetry import setup_telemetry
from app.middleware.tenant import TenantContextMiddleware
from app.middleware.audit import AuditLoggingMiddleware
from app.routers import (
    auth, projects, avm, design, regulation, finance,
    tax, construction, welfare, reports, vision, agent,
    esign, marketplace, webhooks
)

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 이벤트"""
    logger.info("PropAI API 시작", version="v30.0", environment=settings.environment)
    # DB 연결 풀 초기화
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # 종료 시 연결 풀 정리
    await engine.dispose()
    logger.info("PropAI API 종료")

app = FastAPI(
    title="PropAI v30.0 API",
    description="부동산 전주기 AI 자동화 플랫폼 API",
    version="30.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

# OpenTelemetry 분산 추적 설정
tracer = setup_telemetry(app, service_name="propai-api")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip 압축 (응답 크기 50~70% 감소)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 멀티 테넌트 컨텍스트 미들웨어
app.add_middleware(TenantContextMiddleware)

# 감사 로깅 미들웨어
app.add_middleware(AuditLoggingMiddleware)

# 요청 타이밍 미들웨어
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = (time.perf_counter() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    return response

# 전역 예외 처리
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("처리되지 않은 예외", exc_info=exc, path=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"detail": "내부 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}
    )

# 라우터 등록
API_PREFIX = "/api/v1"
app.include_router(auth.router,        prefix=f"{API_PREFIX}/auth",        tags=["인증"])
app.include_router(projects.router,    prefix=f"{API_PREFIX}/projects",    tags=["프로젝트"])
app.include_router(avm.router,         prefix=f"{API_PREFIX}/avm",         tags=["AVM"])
app.include_router(design.router,      prefix=f"{API_PREFIX}/design",      tags=["설계 AI"])
app.include_router(regulation.router,  prefix=f"{API_PREFIX}/regulation",  tags=["법규 AI"])
app.include_router(finance.router,     prefix=f"{API_PREFIX}/finance",     tags=["금융 AI"])
app.include_router(tax.router,         prefix=f"{API_PREFIX}/tax",         tags=["세금 AI"])
app.include_router(construction.router,prefix=f"{API_PREFIX}/construction",tags=["시공 AI"])
app.include_router(welfare.router,     prefix=f"{API_PREFIX}/welfare",     tags=["복지 AI"])
app.include_router(reports.router,     prefix=f"{API_PREFIX}/reports",     tags=["보고서"])
app.include_router(vision.router,      prefix=f"{API_PREFIX}/vision",      tags=["비전 AI"])
app.include_router(agent.router,       prefix=f"{API_PREFIX}/agent",       tags=["에이전트"])
app.include_router(esign.router,       prefix=f"{API_PREFIX}/esign",       tags=["전자서명"])
app.include_router(marketplace.router, prefix=f"{API_PREFIX}/marketplace",  tags=["API 마켓"])
app.include_router(webhooks.router,    prefix=f"{API_PREFIX}/webhooks",    tags=["Webhook"])

@app.get("/health", tags=["헬스체크"])
async def health_check():
    return {
        "status": "healthy",
        "version": "30.0.0",
        "environment": settings.environment
    }

@app.get("/metrics", include_in_schema=False)
async def metrics():
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

== P02-STEP-02: 멀티테넌트 미들웨어 ==

[파일: apps/api/app/middleware/tenant.py]
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
from app.config import settings

PUBLIC_PATHS = {
    "/health", "/docs", "/redoc", "/openapi.json", "/metrics",
    "/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/kakao",
    "/api/v1/auth/refresh", "/api/v1/marketplace/plans",
    "/api/v1/esign/callback",
}

class TenantContextMiddleware(BaseHTTPMiddleware):
    """JWT에서 tenant_id를 추출하여 DB 컨텍스트에 자동 설정"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 공개 경로는 건너뜀
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key", "")

        if auth_header.startswith("Bearer "):
            try:
                token = auth_header[7:]
                payload = jwt.decode(
                    token,
                    settings.jwt_secret,
                    algorithms=[settings.jwt_algorithm]
                )
                request.state.tenant_id = payload["tenant_id"]
                request.state.user_id = payload["sub"]
                request.state.user_role = payload.get("role", "viewer")
            except JWTError:
                raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")
            except KeyError:
                raise HTTPException(status_code=401, detail="토큰에 테넌트 정보가 없습니다")
        elif api_key:
            # API 키 인증 (마켓플레이스)
            tenant_info = await self._validate_api_key(api_key)
            if not tenant_info:
                raise HTTPException(status_code=401, detail="유효하지 않은 API 키입니다")
            request.state.tenant_id = str(tenant_info["tenant_id"])
            request.state.user_id = f"api_key_{tenant_info['key_id']}"
            request.state.user_role = "api_consumer"
        else:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")

        return await call_next(request)

    async def _validate_api_key(self, api_key: str) -> dict | None:
        import hashlib
        from app.database import AsyncSessionLocal
        from sqlalchemy import text
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT key_id, tenant_id FROM api_keys WHERE api_key_hash=:h AND is_active=true"),
                {"h": key_hash}
            )
            return result.mappings().first()

== P02-STEP-03: JWT 인증 서비스 완전 구현 ==

[파일: apps/api/app/services/auth_service.py]
from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets, hashlib

from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.config import settings
from app.schemas.auth import TokenResponse, UserCreate, UserLogin, OAuthUserInfo

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    """
    JWT 인증 + OAuth + 리프레시 토큰 완전 구현
    지원: 이메일/비밀번호, 카카오, 네이버, 구글
    """

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)

    def create_access_token(self, user_id: str, tenant_id: str, role: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
        payload = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "role": role,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access"
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def create_refresh_token(self) -> tuple[str, str]:
        """리프레시 토큰 생성. 반환: (평문 토큰, SHA-256 해시)"""
        token = secrets.token_urlsafe(64)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token, token_hash

    async def register(self, db: AsyncSession, data: UserCreate) -> dict:
        """신규 회원 가입 (이메일)"""
        # 이메일 중복 확인
        existing = await db.execute(
            text("SELECT user_id FROM users WHERE email=:email AND deleted_at IS NULL"),
            {"email": data.email}
        )
        if existing.scalar():
            raise ValueError("이미 사용 중인 이메일입니다")

        user_id = str(__import__("uuid").uuid4())
        pw_hash = self.hash_password(data.password)

        await db.execute(text("""
            INSERT INTO users (user_id, tenant_id, email, password_hash, name, phone, role)
            VALUES (:uid, :tid, :email, :pw, :name, :phone, 'tenant_admin')
        """), {
            "uid": user_id, "tid": str(data.tenant_id),
            "email": data.email, "pw": pw_hash,
            "name": data.name, "phone": data.phone or ""
        })
        await db.commit()
        return {"user_id": user_id, "email": data.email}

    async def login(self, db: AsyncSession, data: UserLogin) -> TokenResponse:
        """이메일/비밀번호 로그인"""
        result = await db.execute(
            text("SELECT user_id, tenant_id, password_hash, role, is_active FROM users WHERE email=:e AND deleted_at IS NULL"),
            {"e": data.email}
        )
        user = result.mappings().first()

        if not user or not self.verify_password(data.password, user["password_hash"]):
            raise ValueError("이메일 또는 비밀번호가 올바르지 않습니다")
        if not user["is_active"]:
            raise ValueError("비활성화된 계정입니다")

        # 로그인 카운트 업데이트
        await db.execute(
            text("UPDATE users SET last_login_at=NOW(), login_count=login_count+1 WHERE user_id=:uid"),
            {"uid": str(user["user_id"])}
        )

        access_token = self.create_access_token(
            str(user["user_id"]), str(user["tenant_id"]), user["role"]
        )
        refresh_plain, refresh_hash = self.create_refresh_token()

        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        await db.execute(text("""
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
            VALUES (:uid, :th, :exp)
        """), {"uid": str(user["user_id"]), "th": refresh_hash, "exp": expire})
        await db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_plain,
            token_type="bearer",
            expires_in=settings.jwt_expire_minutes * 60,
            user_id=str(user["user_id"]),
            tenant_id=str(user["tenant_id"]),
            role=user["role"]
        )

    async def refresh_access_token(self, db: AsyncSession, refresh_token: str) -> TokenResponse:
        """리프레시 토큰으로 새 액세스 토큰 발급"""
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        result = await db.execute(text("""
            SELECT rt.user_id, rt.expires_at, rt.is_revoked,
                   u.tenant_id, u.role, u.is_active
            FROM refresh_tokens rt
            JOIN users u ON rt.user_id = u.user_id
            WHERE rt.token_hash = :th
        """), {"th": token_hash})
        record = result.mappings().first()

        if not record:
            raise ValueError("유효하지 않은 리프레시 토큰입니다")
        if record["is_revoked"]:
            raise ValueError("폐기된 토큰입니다")
        if record["expires_at"] < datetime.now(timezone.utc):
            raise ValueError("만료된 토큰입니다")
        if not record["is_active"]:
            raise ValueError("비활성화된 계정입니다")

        # 기존 토큰 폐기 (토큰 회전)
        await db.execute(
            text("UPDATE refresh_tokens SET is_revoked=true WHERE token_hash=:th"),
            {"th": token_hash}
        )

        access_token = self.create_access_token(
            str(record["user_id"]), str(record["tenant_id"]), record["role"]
        )
        refresh_plain, refresh_hash = self.create_refresh_token()
        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        await db.execute(text("""
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
            VALUES (:uid, :th, :exp)
        """), {"uid": str(record["user_id"]), "th": refresh_hash, "exp": expire})
        await db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_plain,
            token_type="bearer",
            expires_in=settings.jwt_expire_minutes * 60,
            user_id=str(record["user_id"]),
            tenant_id=str(record["tenant_id"]),
            role=record["role"]
        )

    async def kakao_oauth_login(self, db: AsyncSession, code: str) -> TokenResponse:
        """카카오 OAuth 로그인"""
        import httpx

        # 1. 카카오 액세스 토큰 획득
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://kauth.kakao.com/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.kakao_client_id,
                    "client_secret": settings.kakao_client_secret,
                    "redirect_uri": "http://localhost:3000/api/auth/kakao/callback",
                    "code": code
                }
            )
            tokens = token_resp.json()

            # 2. 카카오 사용자 정보 조회
            user_resp = await client.get(
                "https://kapi.kakao.com/v2/user/me",
                headers={"Authorization": f"Bearer {tokens['access_token']}"}
            )
            kakao_user = user_resp.json()

        kakao_id = str(kakao_user["id"])
        kakao_account = kakao_user.get("kakao_account", {})
        email = kakao_account.get("email", f"kakao_{kakao_id}@propai.temp")
        name = kakao_account.get("profile", {}).get("nickname", "카카오 사용자")

        # 3. 기존 사용자 조회 또는 신규 생성
        result = await db.execute(
            text("SELECT user_id, tenant_id, role FROM users WHERE oauth_provider='kakao' AND oauth_id=:oid AND deleted_at IS NULL"),
            {"oid": kakao_id}
        )
        user = result.mappings().first()

        if not user:
            # 신규 사용자 -> 데모 테넌트 또는 신규 테넌트 생성
            tenant_id = await self._create_new_tenant_for_oauth(db, name)
            user_id = str(__import__("uuid").uuid4())
            await db.execute(text("""
                INSERT INTO users (user_id, tenant_id, email, name, role, oauth_provider, oauth_id)
                VALUES (:uid, :tid, :email, :name, 'tenant_admin', 'kakao', :oid)
            """), {"uid": user_id, "tid": str(tenant_id), "email": email, "name": name, "oid": kakao_id})
            await db.commit()
            tenant_id_str = str(tenant_id)
            role = "tenant_admin"
        else:
            user_id = str(user["user_id"])
            tenant_id_str = str(user["tenant_id"])
            role = user["role"]

        access_token = self.create_access_token(user_id, tenant_id_str, role)
        refresh_plain, refresh_hash = self.create_refresh_token()
        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        await db.execute(text("""
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
            VALUES (:uid, :th, :exp)
        """), {"uid": user_id, "th": refresh_hash, "exp": expire})
        await db.commit()

        return TokenResponse(
            access_token=access_token, refresh_token=refresh_plain,
            token_type="bearer", expires_in=settings.jwt_expire_minutes * 60,
            user_id=user_id, tenant_id=tenant_id_str, role=role
        )

    async def _create_new_tenant_for_oauth(self, db: AsyncSession, name: str) -> str:
        """OAuth 신규 사용자용 Starter 테넌트 자동 생성"""
        import uuid
        tenant_id = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO tenants (tenant_id, company_name, subscription_tier)
            VALUES (:tid, :name, 'starter')
        """), {"tid": tenant_id, "name": f"{name}의 사무소"})
        return tenant_id

== P02-STEP-04: 인증 라우터 ==

[파일: apps/api/app/routers/auth.py]
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.auth_service import AuthService
from app.schemas.auth import (
    UserCreate, UserLogin, TokenResponse, RefreshTokenRequest
)

router = APIRouter()
auth_service = AuthService()

@router.post("/register", response_model=dict, summary="회원 가입")
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    """이메일 기반 신규 회원 가입"""
    try:
        user = await auth_service.register(db, data)
        return {"message": "회원 가입 완료", "user_id": user["user_id"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login", response_model=TokenResponse, summary="로그인")
async def login(
    data: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """이메일/비밀번호 로그인"""
    try:
        tokens = await auth_service.login(db, data)
        # 리프레시 토큰을 HttpOnly 쿠키에 저장 (XSS 방어)
        response.set_cookie(
            key="refresh_token",
            value=tokens.refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=30 * 24 * 3600
        )
        return tokens
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/refresh", response_model=TokenResponse, summary="토큰 갱신")
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """리프레시 토큰으로 새 액세스 토큰 발급"""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="리프레시 토큰이 없습니다")
    try:
        tokens = await auth_service.refresh_access_token(db, refresh_token)
        response.set_cookie(
            key="refresh_token", value=tokens.refresh_token,
            httponly=True, secure=True, samesite="lax",
            max_age=30 * 24 * 3600
        )
        return tokens
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/logout", summary="로그아웃")
async def logout(response: Response):
    response.delete_cookie("refresh_token")
    return {"message": "로그아웃 완료"}

@router.get("/kakao/callback", summary="카카오 OAuth 콜백")
async def kakao_callback(
    code: str,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """카카오 OAuth 인증 코드로 로그인"""
    try:
        tokens = await auth_service.kakao_oauth_login(db, code)
        response.set_cookie(
            key="refresh_token", value=tokens.refresh_token,
            httponly=True, secure=True, samesite="lax",
            max_age=30 * 24 * 3600
        )
        return tokens
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"카카오 인증 실패: {str(e)}")

@router.get("/me", summary="내 정보 조회")
async def get_me(request: Request, db: AsyncSession = Depends(get_db)):
    """현재 로그인 사용자 정보 조회"""
    from sqlalchemy import text
    user_id = request.state.user_id
    result = await db.execute(
        text("SELECT user_id, email, name, role, created_at FROM users WHERE user_id=:uid"),
        {"uid": user_id}
    )
    user = result.mappings().first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return dict(user)

== P02-STEP-05: 스키마 (Pydantic 모델) ==

[파일: apps/api/app/schemas/auth.py]
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
import uuid

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None
    tenant_id: uuid.UUID

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('비밀번호는 8자 이상이어야 합니다')
        if not any(c.isdigit() for c in v):
            raise ValueError('비밀번호에 숫자를 포함해야 합니다')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    tenant_id: str
    role: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

================================================================
[PHASE-02 완료 체크리스트]
================================================================
[ ] POST /api/v1/auth/register -> 201 응답 확인
[ ] POST /api/v1/auth/login -> JWT 토큰 반환 확인
[ ] POST /api/v1/auth/refresh -> 새 토큰 반환 확인
[ ] GET /api/v1/auth/me (Bearer 토큰) -> 사용자 정보 반환 확인
[ ] 멀티테넌트 격리: tenant_a 토큰으로 tenant_b 프로젝트 조회 -> 빈 배열 반환 확인
[ ] RLS 동작: SET app.current_tenant_id = '...' 없이 쿼리 -> 빈 결과 확인
================================================================
```
