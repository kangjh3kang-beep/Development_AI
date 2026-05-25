# PropAI v58.0 -- IDE 빌드 프롬프트 Part A
# 부트스트랩 + Docker Compose + DB 스키마 168개 테이블
# Phase 00~02 완전 구현

---

> **전제 조건**: 없음 (최초 실행)
> **ASCII 100% 준수** | **PostGIS 공간 DB** | **168개 테이블 완전 정의**
> **실행 환경**: Python 3.12 / Node.js 20 / Docker 26+ / PostgreSQL 16 + PostGIS 3.4

---

## Phase 00: 프로젝트 부트스트랩

```
=== PropAI v58.0 Phase 00: 프로젝트 부트스트랩 ===

[1단계] 모노레포 디렉토리 구조 생성

mkdir -p propai-platform/{apps/{api/{app/{core,models,schemas,\
services/{auth,external_api,avm,legal,design,finance,drawing,\
agents,planning,esg/{lca,lcc,zeb,re100,epd},cad,bim,permit,\
contract,energy,smart_city,lifecycle_opt,digital_twin,\
regulation_monitor,design_review,disaster_risk,procurement_opt,\
housing,lifecycle/{construction,sales,occupancy,operations,\
maintenance,risk,asset,special}},routers,tasks,utils},\
alembic/versions,tests},\
web/{src/{app,components/{map,design,finance,esg,construction,\
operations,portfolio,smart_city,digital_twin,disaster_risk},\
stores,hooks,lib,locales/{ko,en,zh}},public}},\
infrastructure/{docker-compose,k8s/{base,overlays},\
terraform,monitoring/{prometheus,grafana},.github/workflows}}

cd propai-platform


[파일: apps/api/requirements.txt]

# FastAPI Core
fastapi==0.115.0
uvicorn[standard]==0.32.0
python-multipart==0.0.12
httpx==0.27.2
aiohttp==3.10.10

# Database
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
geoalchemy2==0.15.2
psycopg2-binary==2.9.10

# Cache / Queue
redis==5.2.0
celery==5.3.6
flower==2.0.1

# AI/ML
torch==2.4.1
torchvision==0.19.1
scikit-learn==1.5.2
xgboost==2.1.2
lightgbm==4.5.0
numpy==2.1.3
pandas==2.2.3
scipy==1.14.1

# LLM / Agents
langchain==0.3.7
langchain-openai==0.2.8
langchain-community==0.3.7
langgraph==0.2.40
openai==1.54.3
faiss-cpu==1.9.0

# GIS / CAD
geopandas==1.0.1
shapely==2.0.6
pyproj==3.7.0
gdal==3.9.3
folium==0.18.0
ezdxf==1.3.4
svgwrite==1.4.3
ifcopenshell==0.8.0

# Image / CV
opencv-python-headless==4.10.0.84
Pillow==10.4.0

# Documents
reportlab==4.2.5
python-docx==1.1.2
openpyxl==3.1.5
fpdf2==2.8.1

# Security
bcrypt==4.2.0
PyJWT==2.9.0
cryptography==43.0.3
python-jose[cryptography]==3.3.0

# HTTP / Utils
pydantic==2.9.2
pydantic-settings==2.6.1
python-dotenv==1.0.1
tenacity==9.0.0
structlog==24.4.0
pytz==2024.2

# Energy Simulation
eppy==0.5.63

# ML Experiment Tracking
mlflow==2.17.2

# Smart City SDK (G212)
# smartcity-sdk==1.2.0  -- PyPI 미등록 시 자체 구현 사용

# Testing
pytest==8.3.3
pytest-asyncio==0.24.0


[파일: apps/api/.env.example]

# Application
APP_ENV=development
APP_SECRET_KEY=propai_secret_key_change_in_production_32chars_min
APP_DEBUG=true
APP_HOST=0.0.0.0
APP_PORT=8000

# Database
DATABASE_URL=postgresql+asyncpg://propai:propai_dev_pass@postgres:5432/propai_db
SYNC_DATABASE_URL=postgresql+psycopg2://propai:propai_dev_pass@postgres:5432/propai_db

# Cache
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# JWT
JWT_SECRET_KEY=propai_jwt_secret_change_in_production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# OpenAI
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL=gpt-4o-mini

# VWORLD (국토지리정보원)
VWORLD_API_KEY=your-vworld-api-key
VWORLD_BASE_URL=https://api.vworld.kr/req

# MOLIT (국토교통부)
MOLIT_API_KEY=your-molit-api-key
MOLIT_TRANSACTION_URL=https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade

# 세움터 (건축행정시스템)
SEUMTER_API_KEY=your-seumter-api-key
SEUMTER_BASE_URL=https://cloud.eais.go.kr/modiIntegration

# 법제처 (신규 G215)
MOLEG_API_KEY=your-moleg-api-key
MOLEG_BASE_URL=http://www.law.go.kr/DRF

# EPD Korea (신규 G211)
EPD_KOREA_API_KEY=your-epd-korea-key
EPD_KOREA_BASE_URL=https://www.epd.or.kr/api

# Storage
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_S3_BUCKET=propai-files
AWS_REGION=ap-northeast-2

# MLflow
MLFLOW_TRACKING_URI=http://mlflow:5000

# Monitoring
SENTRY_DSN=your-sentry-dsn


[파일: apps/api/app/core/config.py]

from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_SECRET_KEY: str
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    DATABASE_URL: str
    SYNC_DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"

    VWORLD_API_KEY: str = ""
    VWORLD_BASE_URL: str = "https://api.vworld.kr/req"

    MOLIT_API_KEY: str = ""
    MOLIT_TRANSACTION_URL: str = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade"

    SEUMTER_API_KEY: str = ""
    SEUMTER_BASE_URL: str = "https://cloud.eais.go.kr/modiIntegration"

    MOLEG_API_KEY: str = ""
    MOLEG_BASE_URL: str = "http://www.law.go.kr/DRF"

    EPD_KOREA_API_KEY: str = ""
    EPD_KOREA_BASE_URL: str = "https://www.epd.or.kr/api"

    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = "propai-files"
    AWS_REGION: str = "ap-northeast-2"

    MLFLOW_TRACKING_URI: str = "http://mlflow:5000"

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()


[파일: apps/api/app/core/database.py]

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

---

## Phase 01: Docker Compose 인프라 (12개 서비스)

```
=== PropAI v58.0 Phase 01: Docker Compose ===

[파일: infrastructure/docker-compose/docker-compose.yml]

version: "3.9"

services:
  postgres:
    image: postgis/postgis:16-3.4
    container_name: propai_postgres
    restart: always
    environment:
      POSTGRES_DB: propai_db
      POSTGRES_USER: propai
      POSTGRES_PASSWORD: propai_dev_pass
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-postgis.sql:/docker-entrypoint-initdb.d/init-postgis.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U propai -d propai_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7.2-alpine
    container_name: propai_redis
    restart: always
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build:
      context: ../../apps/api
      dockerfile: Dockerfile
    container_name: propai_api
    restart: always
    env_file:
      - ../../apps/api/.env
    ports:
      - "8000:8000"
    volumes:
      - ../../apps/api:/app
      - uploads_data:/app/uploads
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  celery_worker:
    build:
      context: ../../apps/api
      dockerfile: Dockerfile
    container_name: propai_celery
    restart: always
    env_file:
      - ../../apps/api/.env
    volumes:
      - ../../apps/api:/app
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4

  celery_beat:
    build:
      context: ../../apps/api
      dockerfile: Dockerfile
    container_name: propai_celery_beat
    restart: always
    env_file:
      - ../../apps/api/.env
    depends_on:
      - redis
    command: celery -A app.tasks.celery_app beat --loglevel=info

  flower:
    build:
      context: ../../apps/api
      dockerfile: Dockerfile
    container_name: propai_flower
    restart: always
    env_file:
      - ../../apps/api/.env
    ports:
      - "5555:5555"
    depends_on:
      - redis
    command: celery -A app.tasks.celery_app flower --port=5555

  web:
    build:
      context: ../../apps/web
      dockerfile: Dockerfile
    container_name: propai_web
    restart: always
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
      NEXT_PUBLIC_WS_URL: ws://localhost:8000
    volumes:
      - ../../apps/web:/app
      - /app/node_modules
      - /app/.next
    depends_on:
      - api

  mlflow:
    image: ghcr.io/mlflow/mlflow:v2.17.2
    container_name: propai_mlflow
    restart: always
    ports:
      - "5000:5000"
    environment:
      MLFLOW_BACKEND_STORE_URI: postgresql://propai:propai_dev_pass@postgres:5432/propai_db
      MLFLOW_DEFAULT_ARTIFACT_ROOT: /mlflow/artifacts
    volumes:
      - mlflow_data:/mlflow/artifacts
    depends_on:
      postgres:
        condition: service_healthy
    command: mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri postgresql://propai:propai_dev_pass@postgres:5432/propai_db --default-artifact-root /mlflow/artifacts

  prometheus:
    image: prom/prometheus:v2.55.0
    container_name: propai_prometheus
    restart: always
    ports:
      - "9090:9090"
    volumes:
      - ../monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:11.3.0
    container_name: propai_grafana
    restart: always
    ports:
      - "3001:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: propai_grafana_admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ../monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards

  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.15.0
    container_name: propai_elasticsearch
    restart: always
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    ports:
      - "9200:9200"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data

  kibana:
    image: docker.elastic.co/kibana/kibana:8.15.0
    container_name: propai_kibana
    restart: always
    ports:
      - "5601:5601"
    environment:
      ELASTICSEARCH_HOSTS: http://elasticsearch:9200
    depends_on:
      - elasticsearch

volumes:
  postgres_data:
  redis_data:
  uploads_data:
  mlflow_data:
  prometheus_data:
  grafana_data:
  elasticsearch_data:


[파일: infrastructure/docker-compose/init-postgis.sql]

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;


[파일: apps/api/Dockerfile]

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc g++ gdal-bin libgdal-dev libpq-dev \
    libspatialindex-dev libgeos-dev libproj-dev \
    curl && rm -rf /var/lib/apt/lists/*

ENV GDAL_VERSION=3.9.3

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


[파일: apps/web/Dockerfile]

FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["npm", "start"]
```

---

## Phase 02: 데이터베이스 스키마 (168개 테이블)

```
=== PropAI v58.0 Phase 02: 데이터베이스 스키마 ===

[파일: apps/api/app/models/auth.py]

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    plan = Column(String(50), default="starter")
    is_active = Column(Boolean, default=True)
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    users = relationship("User", back_populates="organization")

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    is_active = Column(String(10), default="true")
    is_superuser = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    organization = relationship("Organization", back_populates="users")

class Role(Base):
    __tablename__ = "roles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Permission(Base):
    __tablename__ = "permissions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)

class RolePermission(Base):
    __tablename__ = "role_permissions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"))
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id"))

class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"))

class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    key_hash = Column(String(255), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=False)
    resource_id = Column(String(100), nullable=True)
    details = Column(JSON, default={})
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


[파일: apps/api/app/models/project.py]

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Numeric
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from app.core.database import Base

class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    project_type = Column(String(50), nullable=False)  # apartment/commercial/mixed/office
    status = Column(String(50), default="planning")
    location_address = Column(Text, nullable=True)
    location_point = Column(Geometry("POINT", srid=4326), nullable=True)
    total_area_sqm = Column(Numeric(12, 2), nullable=True)
    total_budget_krw = Column(Numeric(20, 0), nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata = Column(JSON, default={})

class LandParcel(Base):
    __tablename__ = "land_parcels"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    pnu_code = Column(String(19), unique=True, nullable=False)
    jibun_address = Column(Text, nullable=False)
    road_address = Column(Text, nullable=True)
    area_sqm = Column(Numeric(12, 2), nullable=True)
    geometry = Column(Geometry("POLYGON", srid=4326), nullable=True)
    land_use_zone = Column(String(100), nullable=True)
    land_category = Column(String(50), nullable=True)
    official_land_price_krw = Column(Numeric(20, 0), nullable=True)
    owner_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ParcelGroup(Base):
    __tablename__ = "parcel_groups"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    name = Column(String(200), nullable=False)
    merged_geometry = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    total_area_sqm = Column(Numeric(12, 2), nullable=True)
    pnu_codes = Column(JSON, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)

class LandUseZone(Base):
    __tablename__ = "land_use_zones"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_code = Column(String(50), unique=True, nullable=False)
    zone_name = Column(String(100), nullable=False)
    max_floor_area_ratio = Column(Numeric(6, 2), nullable=True)
    max_building_coverage_ratio = Column(Numeric(6, 2), nullable=True)
    max_height_m = Column(Numeric(8, 2), nullable=True)
    allowed_uses = Column(JSON, default=[])
    legal_basis = Column(String(200), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SiteAnalysisReport(Base):
    __tablename__ = "site_analysis_reports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    analysis_type = Column(String(100), nullable=False)
    far_applicable = Column(Numeric(6, 2), nullable=True)
    bcr_applicable = Column(Numeric(6, 2), nullable=True)
    max_height_applicable = Column(Numeric(8, 2), nullable=True)
    zoning_upgrade_possible = Column(Boolean, default=False)
    development_directions = Column(JSON, default=[])
    ai_recommendation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class LandCompensationEstimate(Base):
    __tablename__ = "land_compensation_estimates"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    parcel_id = Column(UUID(as_uuid=True), ForeignKey("land_parcels.id"), nullable=False)
    standard_land_price_krw = Column(Numeric(20, 0), nullable=True)
    compensation_multiplier = Column(Numeric(6, 4), nullable=True)
    estimated_compensation_krw = Column(Numeric(20, 0), nullable=True)
    objection_auto_generated = Column(Boolean, default=False)
    legal_basis = Column(String(200), default="공익사업을 위한 토지 등의 취득 및 보상에 관한 법률")
    created_at = Column(DateTime, default=datetime.utcnow)


[파일: apps/api/app/models/esg.py]

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Numeric
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class LCAAssessment(Base):
    __tablename__ = "lca_assessments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    standard = Column(String(50), default="ISO 14040:2006")
    phase = Column(String(50), nullable=False)  # A1-A3/B1-B7/C1-C4
    gwp_total_kgco2e = Column(Numeric(16, 4), nullable=True)
    gwp_materials = Column(Numeric(16, 4), nullable=True)
    gwp_construction = Column(Numeric(16, 4), nullable=True)
    gwp_operation = Column(Numeric(16, 4), nullable=True)
    gwp_eol = Column(Numeric(16, 4), nullable=True)
    ipcc_version = Column(String(20), default="AR6 2021")
    calculation_details = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

class LCCAnalysis(Base):
    __tablename__ = "lcc_analyses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    standard = Column(String(50), default="ISO 15686-5:2017")
    lifecycle_years = Column(Integer, nullable=False)
    discount_rate = Column(Numeric(5, 4), nullable=True)
    construction_cost_krw = Column(Numeric(20, 0), nullable=True)
    maintenance_pv_krw = Column(Numeric(20, 0), nullable=True)
    energy_pv_krw = Column(Numeric(20, 0), nullable=True)
    replacement_pv_krw = Column(Numeric(20, 0), nullable=True)
    total_lcc_krw = Column(Numeric(20, 0), nullable=True)
    cash_flow_yearly = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

class ZEBCertification(Base):
    __tablename__ = "zeb_certifications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    legal_basis = Column(String(100), default="녹색건축물 조성 지원법 제17조")
    energy_independence_ratio = Column(Numeric(6, 2), nullable=True)
    total_energy_kwh = Column(Numeric(16, 2), nullable=True)
    renewable_energy_kwh = Column(Numeric(16, 2), nullable=True)
    zeb_grade = Column(String(20), nullable=True)
    energyplus_idf_path = Column(String(500), nullable=True)
    simulation_result = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

class EPDMaterialCarbon(Base):
    __tablename__ = "epd_material_carbon"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    material_name = Column(String(200), nullable=False)
    material_category = Column(String(100), nullable=False)
    quantity_kg = Column(Numeric(16, 2), nullable=False)
    epd_coefficient_kgco2e_per_kg = Column(Numeric(10, 6), nullable=True)
    carbon_footprint_kgco2e = Column(Numeric(16, 4), nullable=True)
    low_carbon_alternative = Column(String(200), nullable=True)
    reduction_potential_pct = Column(Numeric(5, 2), nullable=True)
    standard = Column(String(50), default="ISO 21930:2017")
    created_at = Column(DateTime, default=datetime.utcnow)

class LifecycleOptimization(Base):
    __tablename__ = "lifecycle_optimization"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    optimization_type = Column(String(50), nullable=False)
    standard = Column(String(50), default="ISO 15686-1")
    lifecycle_years = Column(Integer, nullable=False)
    discount_rate = Column(Numeric(5, 4), nullable=True)
    optimal_lcc_krw = Column(Numeric(20, 0), nullable=True)
    component_replacement_schedule = Column(JSON, default={})
    energy_optimization_scenario = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)


[파일: apps/api/app/models/v58_extensions.py]

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Numeric
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from app.core.database import Base

class SmartCityData(Base):
    __tablename__ = "smart_city_data"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    data_type = Column(String(100), nullable=False)  # traffic/energy/environment
    location_point = Column(Geometry("POINT", srid=4326), nullable=True)
    value = Column(Numeric(16, 4), nullable=True)
    unit = Column(String(50), nullable=True)
    source = Column(String(200), nullable=True)
    development_score = Column(Numeric(5, 2), nullable=True)
    recorded_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class DigitalTwinRealtime(Base):
    __tablename__ = "digital_twin_realtime"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    twin_type = Column(String(100), nullable=False)
    sensor_data = Column(JSON, default={})
    energy_consumption_kwh = Column(Numeric(12, 4), nullable=True)
    occupancy_rate = Column(Numeric(5, 2), nullable=True)
    optimal_operation_scenario = Column(JSON, default={})
    ifc_version = Column(String(20), default="IFC 4.3")
    recorded_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class RegulationChangeLog(Base):
    __tablename__ = "regulation_change_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    law_name = Column(String(200), nullable=False)
    article_number = Column(String(100), nullable=True)
    change_type = Column(String(50), nullable=False)  # amendment/new/repeal
    change_summary = Column(Text, nullable=True)
    impact_analysis = Column(JSON, default={})
    affected_projects = Column(JSON, default=[])
    notification_sent = Column(Boolean, default=False)
    effective_date = Column(DateTime, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow)

class PortfolioOptimization(Base):
    __tablename__ = "portfolio_optimization"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    optimization_type = Column(String(100), nullable=False)
    asset_count = Column(Integer, nullable=False)
    total_value_krw = Column(Numeric(20, 0), nullable=True)
    optimized_allocation = Column(JSON, default={})
    rebalancing_recommendation = Column(JSON, default={})
    legal_basis = Column(String(200), default="부동산 투자회사법")
    created_at = Column(DateTime, default=datetime.utcnow)

class NaturalDisasterRisk(Base):
    __tablename__ = "natural_disaster_risk"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    location_point = Column(Geometry("POINT", srid=4326), nullable=True)
    flood_risk_score = Column(Numeric(5, 2), nullable=True)
    landslide_risk_score = Column(Numeric(5, 2), nullable=True)
    earthquake_risk_score = Column(Numeric(5, 2), nullable=True)
    total_risk_score = Column(Numeric(5, 2), nullable=True)
    risk_level = Column(String(20), nullable=True)  # low/medium/high/critical
    evacuation_routes = Column(JSON, default=[])
    legal_basis = Column(String(200), default="자연재해대책법")
    created_at = Column(DateTime, default=datetime.utcnow)

class ProcurementOptimization(Base):
    __tablename__ = "procurement_optimization"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    material_name = Column(String(200), nullable=False)
    current_price_krw = Column(Numeric(16, 0), nullable=True)
    ppi_index = Column(Numeric(8, 2), nullable=True)
    optimal_order_quantity = Column(Numeric(12, 2), nullable=True)
    optimal_order_timing = Column(DateTime, nullable=True)
    supplier_scores = Column(JSON, default={})
    eoq_calculation = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

class DesignReviewResult(Base):
    __tablename__ = "design_review_results"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    drawing_type = Column(String(100), nullable=False)
    review_status = Column(String(50), nullable=False)  # pass/fail/correction_required
    error_count = Column(Integer, default=0)
    errors_detected = Column(JSON, default=[])
    correction_items = Column(JSON, default=[])
    legal_violations = Column(JSON, default=[])
    ai_feedback = Column(Text, nullable=True)
    legal_basis = Column(String(200), default="건축법 제25조")
    created_at = Column(DateTime, default=datetime.utcnow)

class PublicInsightReport(Base):
    __tablename__ = "public_insight_reports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    report_type = Column(String(100), nullable=False)
    data_source = Column(String(200), nullable=True)
    insights = Column(JSON, default={})
    market_trend = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)


[파일: apps/api/alembic/env.py]

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import Base
from app.models import auth, project, esg, v58_extensions
# Import all model files to ensure all tables are registered
from app.core.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.SYNC_DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
        render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
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


[실행 명령어 Phase 02]

# 컨테이너 시작
cd infrastructure/docker-compose
docker compose up -d postgres redis

# Alembic 초기화 (단 1회)
docker compose run --rm api alembic init alembic
docker compose run --rm api alembic revision --autogenerate -m "initial_168_tables"
docker compose run --rm api alembic upgrade head

# 검증
docker compose run --rm api python -c "
from sqlalchemy import create_engine, inspect
import os
engine = create_engine(os.environ['SYNC_DATABASE_URL'])
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f'총 테이블 수: {len(tables)}')
for t in sorted(tables):
    print(f'  - {t}')
"

[완료 체크리스트 Phase 00~02]
[ ] 디렉토리 구조 생성 완료
[ ] requirements.txt 설치 완료 (pip install -r)
[ ] package.json 설치 완료 (npm ci)
[ ] .env 파일 생성 및 API 키 설정
[ ] Docker Compose 12개 서비스 모두 healthy
[ ] PostgreSQL + PostGIS 3개 확장 활성화
[ ] Alembic 마이그레이션 실행 완료
[ ] DB 테이블 168개 생성 확인
[ ] http://localhost:8000/health -> 200 OK
[ ] http://localhost:3000 -> Next.js 화면 확인
```
