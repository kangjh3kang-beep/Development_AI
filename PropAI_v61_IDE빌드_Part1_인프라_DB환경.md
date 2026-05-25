# PropAI v61.0 -- IDE 빌드 프롬프트 Part 1
# 인프라 + PostgreSQL DB + Docker + 환경설정 + 시드 데이터
# 순서: Part1 -> Part2 -> Part3 -> Part4 순으로 실행
# ASCII 100% | 2026-03-30

================================================================================
[IDE 입력 프롬프트 -- Part 1 시작]
================================================================================

다음 내용을 그대로 IDE(Cursor/Claude Code/VSCode+Copilot)에 입력하세요.

---

## PROMPT:

당신은 PropAI v61.0 풀스택 AI 건설 플랫폼을 구현하는 시니어 개발자입니다.
아래 명세에 따라 프로젝트를 **단계별로 완전히 구현**해 주세요.
각 파일은 실제 동작하는 완성 코드로 작성하고, 누락 없이 모두 생성하세요.

---

## STEP 0: 프로젝트 초기화 + 환경 설정

### 디렉토리 구조 생성

```bash
mkdir -p propai/apps/api/app/{models,services/{cad,bim,cost,design,rates,simulation,gis,esg,ai},api/v1/endpoints,tasks,data,seeds,core}
mkdir -p propai/apps/api/migrations/versions
mkdir -p propai/apps/web/app/\(platform\)/project/\[id\]/{design,cost,analysis,feasibility,billing,esg}
mkdir -p propai/apps/web/components/{cad,cost,design,shared}
mkdir -p propai/data/{ifc_models,cost_templates,drawings,uploads}
mkdir -p propai/kubernetes
cd propai
```

### .env 파일

```bash
# propai/.env
DATABASE_URL=postgresql+asyncpg://propai:propai_dev_2026@localhost:5432/propai_db
DATABASE_URL_SYNC=postgresql://propai:propai_dev_2026@localhost:5432/propai_db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=propai-secret-key-v61-2026-change-in-production-min-32chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
VWORLD_API_KEY=your_vworld_api_key_here
MOLIT_API_KEY=your_molit_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
QDRANT_URL=http://localhost:6333
MLFLOW_TRACKING_URI=http://localhost:5000
BIM_IFC_UPLOAD_PATH=/data/ifc_models
EXCEL_TEMPLATE_PATH=/data/cost_templates
DRAWING_EXPORT_PATH=/data/drawings
UPLOAD_PATH=/data/uploads
ENVIRONMENT=development
LOG_LEVEL=INFO
CODIL_API_BASE=https://www.codil.or.kr
CORS_ORIGINS=["http://localhost:3000","http://localhost:3001"]
```

### requirements.txt

```text
# propai/apps/api/requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.13.3
pydantic==2.9.2
pydantic-settings==2.6.0
structlog==24.4.0
redis==5.1.1
celery==5.4.0
httpx==0.27.2
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.17
aiofiles==24.1.0
geopandas==1.0.1
pyproj==3.7.0
shapely==2.0.6
ifcopenshell==0.7.0
ezdxf==1.3.4
svgwrite==1.4.3
openpyxl==3.1.5
xlrd==2.0.1
pandas==2.2.3
numpy==1.26.4
scipy==1.14.1
trimesh==4.5.3
scikit-learn==1.5.2
xgboost==2.1.3
langchain==0.3.7
langchain-anthropic==0.3.0
langgraph==0.2.42
qdrant-client==1.12.1
anthropic==0.39.0
mlflow==2.17.1
psycopg2-binary==2.9.10
python-dotenv==1.0.1
celery[redis]==5.4.0
```

---

## STEP 1: Docker Compose

```yaml
# propai/docker-compose.yml
version: "3.9"
services:

  postgres:
    image: timescale/timescaledb-ha:pg16-latest
    environment:
      POSTGRES_USER: propai
      POSTGRES_PASSWORD: propai_dev_2026
      POSTGRES_DB: propai_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL","pg_isready -U propai -d propai_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7.4-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD","redis-cli","ping"]
      interval: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  mlflow:
    image: python:3.12-slim
    command: >
      bash -c "pip install mlflow psycopg2-binary -q &&
               mlflow server --host 0.0.0.0 --port 5000
               --backend-store-uri postgresql://propai:propai_dev_2026@postgres:5432/propai_db
               --default-artifact-root /mlflow/artifacts"
    ports:
      - "5000:5000"
    volumes:
      - mlflow_data:/mlflow/artifacts
    depends_on:
      postgres:
        condition: service_healthy

  api:
    build:
      context: ./apps/api
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./apps/api:/app
      - ./data:/data
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://propai:propai_dev_2026@postgres:5432/propai_db
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  celery_worker:
    build:
      context: ./apps/api
      dockerfile: Dockerfile
    volumes:
      - ./apps/api:/app
      - ./data:/data
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://propai:propai_dev_2026@postgres:5432/propai_db
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: celery -A app.tasks.celery_app worker --loglevel=info -Q default,cost,design,rates

  web:
    build:
      context: ./apps/web
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    volumes:
      - ./apps/web:/app
      - /app/node_modules
      - /app/.next
    env_file: .env
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    depends_on:
      - api
    command: npm run dev

volumes:
  postgres_data:
  redis_data:
  qdrant_data:
  mlflow_data:
```

### Dockerfile (API)

```dockerfile
# propai/apps/api/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y \
    gcc libpq-dev libgeos-dev libproj-dev \
    libgdal-dev gdal-bin \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
```

### Dockerfile (Web)

```dockerfile
# propai/apps/web/Dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["npm","run","dev"]
```

---

## STEP 2: 핵심 설정 파일

```python
# propai/apps/api/app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List
import json

class Settings(BaseSettings):
    # DB
    DATABASE_URL: str
    DATABASE_URL_SYNC: str = ""
    # Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    # External API
    VWORLD_API_KEY: str = ""
    MOLIT_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    # Services
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_URL: str = "http://localhost:6333"
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    # File paths
    BIM_IFC_UPLOAD_PATH: str = "/data/ifc_models"
    EXCEL_TEMPLATE_PATH: str = "/data/cost_templates"
    DRAWING_EXPORT_PATH: str = "/data/drawings"
    UPLOAD_PATH: str = "/data/uploads"
    # App
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = '["http://localhost:3000"]'
    CODIL_API_BASE: str = "https://www.codil.or.kr"

    @property
    def cors_origins_list(self) -> List[str]:
        try:
            return json.loads(self.CORS_ORIGINS)
        except Exception:
            return ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

```python
# propai/apps/api/app/core/database.py
from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker
)
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings
import structlog

logger = structlog.get_logger()

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    echo=(settings.ENVIRONMENT == "development"),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")
```

---

## STEP 3: 통합 DB 스키마 (핵심 테이블 -- 전체 시스템 공통)

```python
# propai/apps/api/app/models/base.py
"""PropAI v61.0 통합 DB 모델 -- 전체 시스템 핵심 테이블"""

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, JSON,
    ForeignKey, DateTime, Date, Numeric, BigInteger,
    UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import uuid

# ============================================================
# 1. 조직 / 사용자 / 인증
# ============================================================
class Organization(Base):
    __tablename__ = "organizations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    plan = Column(String(50), default="starter")
    is_active = Column(Boolean, default=True)
    settings = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    email = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(500), nullable=False)
    name = Column(String(100))
    role = Column(String(50), default="member")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# ============================================================
# 2. 프로젝트 마스터
# ============================================================
class Project(Base):
    __tablename__ = "projects"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    name = Column(String(300), nullable=False)
    description = Column(Text)
    status = Column(String(50), default="planning")
    # 위치
    address = Column(String(500))
    pnu_codes = Column(JSONB, default=[])
    latitude = Column(Float)
    longitude = Column(Float)
    # 대지 정보
    site_area = Column(Numeric(12,2))
    zone_type = Column(String(100))
    max_bcr = Column(Numeric(5,2))
    max_far = Column(Numeric(6,2))
    max_height = Column(Numeric(6,1))
    # 건물 계획
    building_type = Column(String(50))
    floor_above = Column(Integer)
    floor_below = Column(Integer, default=2)
    total_floor_area = Column(Numeric(12,2))
    # 메타
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ============================================================
# 3. CAD 설계 도면 -- AI 자동생성 + 인터랙티브 편집
# ============================================================
class DesignStage(Base):
    """설계 단계 관리 (계획->기본->인허가->실시)"""
    __tablename__ = "design_stages"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    stage_no = Column(Integer, nullable=False)       # 1=계획 2=기본 3=인허가 4=실시
    stage_name = Column(String(50), nullable=False)
    stage_status = Column(String(30), default="pending")
    completion_pct = Column(Numeric(5,2), default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    permit_ref = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("project_id","stage_no"),)

class Drawing(Base):
    """도면 마스터 (배치도/평면도/입면도/단면도/조감도 등)"""
    __tablename__ = "drawings"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    stage_id = Column(BigInteger, ForeignKey("design_stages.id"))
    drawing_code = Column(String(20), nullable=False)   # B-01, B-02-STD 등
    drawing_type = Column(String(50), nullable=False)   # 배치도/평면도/입면도
    drawing_name = Column(String(200), nullable=False)
    floor_level = Column(String(20))                    # B3/B1/1F/기준층/RF
    direction = Column(String(10))                      # E/W/S/N
    scale = Column(String(20), default="1:200")
    # 도면 데이터
    vector_data = Column(JSONB)                         # CAD 요소 배열
    svg_content = Column(Text)                          # SVG 렌더링
    dxf_path = Column(Text)                             # DXF 파일 경로
    # AI 생성 정보
    ai_generated = Column(Boolean, default=True)
    ai_model = Column(String(50), default="PropAI-v61")
    generation_params = Column(JSONB, default={})
    # 법규 검토
    compliance_ok = Column(Boolean)
    compliance_issues = Column(JSONB, default=[])
    # 버전
    version = Column(Integer, default=1)
    is_latest = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (Index("idx_drawings_project_code","project_id","drawing_code"),)

class DrawingLayer(Base):
    """CAD 레이어 관리"""
    __tablename__ = "drawing_layers"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    drawing_id = Column(BigInteger, ForeignKey("drawings.id",ondelete="CASCADE"))
    layer_name = Column(String(100), nullable=False)
    layer_color = Column(String(20), default="#000000")
    layer_weight = Column(Numeric(4,1), default=0.25)
    layer_visible = Column(Boolean, default=True)
    layer_locked = Column(Boolean, default=False)
    layer_order = Column(Integer, default=0)
    elements = Column(JSONB, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("idx_layers_drawing","drawing_id"),)

class DrawingEditHistory(Base):
    """CAD 편집 이력 (Undo/Redo 서버 백업)"""
    __tablename__ = "drawing_edit_history"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    drawing_id = Column(BigInteger, ForeignKey("drawings.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    edit_type = Column(String(50), nullable=False)      # ADD/MODIFY/DELETE/MOVE
    element_type = Column(String(50), nullable=False)   # LINE/POLYLINE/TEXT/HATCH
    layer_name = Column(String(100))
    before_data = Column(JSONB)
    after_data = Column(JSONB)
    edit_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("idx_edit_history_drawing","drawing_id"),)

class PermitDocumentSet(Base):
    """인허가 도서 제출 관리"""
    __tablename__ = "permit_document_sets"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    doc_code = Column(String(20), nullable=False)       # A-01, B-01-STD 등
    doc_category = Column(String(10), nullable=False)   # A/B/C/D/E/F/G
    doc_name = Column(String(200), nullable=False)
    drawing_id = Column(BigInteger, ForeignKey("drawings.id"))
    is_required = Column(Boolean, default=True)
    is_completed = Column(Boolean, default=False)
    file_path = Column(Text)
    submission_date = Column(Date)
    review_result = Column(String(50))
    review_comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("project_id","doc_code"),)

class DesignAlternative(Base):
    """설계 대안 (복수 개발방향)"""
    __tablename__ = "design_alternatives"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    alt_no = Column(Integer, nullable=False)
    alt_name = Column(String(100))
    floor_area_ratio = Column(Numeric(6,2))
    building_coverage = Column(Numeric(5,2))
    total_floor_area = Column(Numeric(12,2))
    sellable_area = Column(Numeric(12,2))
    estimated_revenue = Column(Numeric(18,2))
    estimated_cost = Column(Numeric(18,2))
    profit_rate = Column(Numeric(5,2))
    ai_score = Column(Numeric(4,1))
    legal_score = Column(Numeric(4,1))
    profit_score = Column(Numeric(4,1))
    design_score = Column(Numeric(4,1))
    esg_score = Column(Numeric(4,1))
    is_selected = Column(Boolean, default=False)
    selection_reason = Column(Text)
    mc_win_rate = Column(Numeric(5,1))          # 몬테카를로 승률 (%)
    drawings = Column(JSONB, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("project_id","alt_no"),)

# ============================================================
# 4. BIM + 공사비 -- AI 자동산출
# ============================================================
class CostWorkType(Base):
    """공종 마스터 (건축/기계/전기/조경/토목)"""
    __tablename__ = "cost_work_types"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"))
    work_code = Column(String(20), nullable=False)
    work_name = Column(String(200), nullable=False)
    parent_code = Column(String(20))
    work_level = Column(Integer, nullable=False)
    work_category = Column(String(50), nullable=False)  # 건축/기계/전기/조경/토목
    work_division = Column(String(50))
    unit = Column(String(20))
    is_subtotal = Column(Boolean, default=False)
    sort_order = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

class MaterialUnitPrice(Base):
    """자재 단가 마스터 (표준품셈 + 시장단가)"""
    __tablename__ = "material_unit_prices"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    material_code = Column(String(50), nullable=False)
    material_name = Column(String(300), nullable=False)
    spec = Column(String(300))
    unit = Column(String(20), nullable=False)
    material_price = Column(Numeric(18,2), default=0)
    labor_price = Column(Numeric(18,2), default=0)
    expense_price = Column(Numeric(18,2), default=0)
    price_basis_year = Column(Integer, nullable=False, default=2026)
    price_source = Column(String(100), default="표준품셈2025")
    region = Column(String(50), default="경기도")
    valid_from = Column(Date)
    valid_to = Column(Date)
    is_current = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("idx_mat_price_code","material_code"),)

class BimQuantity(Base):
    """IFC BIM 물량 산출 결과"""
    __tablename__ = "bim_quantities"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    ifc_global_id = Column(String(100))
    ifc_object_type = Column(String(100))
    ifc_object_name = Column(String(300))
    work_code = Column(String(20))
    floor_level = Column(String(50))
    zone = Column(String(100))
    quantity = Column(Numeric(18,4), nullable=False, default=0)
    unit = Column(String(20), nullable=False)
    quantity_formula = Column(Text)
    extraction_method = Column(String(50), default="AI_AUTO")
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        Index("idx_bim_qty_project","project_id","work_code"),
        Index("idx_bim_qty_ifc","ifc_global_id"),
    )

class CostDetailItem(Base):
    """공종별 내역서 품목"""
    __tablename__ = "cost_detail_items"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    work_code = Column(String(20), nullable=False)
    item_code = Column(String(100))
    item_name = Column(String(300), nullable=False)
    spec = Column(String(300))
    unit = Column(String(20))
    quantity = Column(Numeric(18,4), default=0)
    material_unit_price = Column(Numeric(18,2), default=0)
    labor_unit_price = Column(Numeric(18,2), default=0)
    expense_unit_price = Column(Numeric(18,2), default=0)
    material_amount = Column(Numeric(18,2), default=0)
    labor_amount = Column(Numeric(18,2), default=0)
    expense_amount = Column(Numeric(18,2), default=0)
    total_amount = Column(Numeric(18,2), default=0)
    bim_qty_id = Column(BigInteger, ForeignKey("bim_quantities.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (Index("idx_cost_items_project","project_id","work_code"),)

class CostCalculationSheet(Base):
    """원가계산서 (5개 분야 통합)"""
    __tablename__ = "cost_calculation_sheets"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    work_category = Column(String(50), nullable=False)
    # 재료비
    direct_material = Column(Numeric(18,2), default=0)
    indirect_material = Column(Numeric(18,2), default=0)
    material_subtotal = Column(Numeric(18,2), default=0)
    # 노무비
    direct_labor = Column(Numeric(18,2), default=0)
    indirect_labor = Column(Numeric(18,2), default=0)
    labor_subtotal = Column(Numeric(18,2), default=0)
    # 경비 (2026년 법정요율 기반)
    machine_cost = Column(Numeric(18,2), default=0)
    industrial_acc_ins = Column(Numeric(18,2), default=0)   # 산재 3.50%
    employment_ins = Column(Numeric(18,2), default=0)        # 고용 0.90%
    health_ins = Column(Numeric(18,2), default=0)            # 건강 3.595%
    pension_ins = Column(Numeric(18,2), default=0)           # 연금 4.75%
    lcare_ins = Column(Numeric(18,2), default=0)             # 장기요양 0.4724%
    retirement_fund = Column(Numeric(18,2), default=0)       # 퇴직공제 2.10%
    safety_health_cost = Column(Numeric(18,2), default=0)    # 안전보건 2.07%
    env_preserve_cost = Column(Numeric(18,2), default=0)     # 환경보전 0.16%
    subcontract_bond = Column(Numeric(18,2), default=0)
    expense_subtotal = Column(Numeric(18,2), default=0)
    # 원가 합계
    pure_construction = Column(Numeric(18,2), default=0)
    general_mgmt_cost = Column(Numeric(18,2), default=0)     # 일반관리비 5.50%
    profit_amount = Column(Numeric(18,2), default=0)          # 이윤 15.00%
    total_construction = Column(Numeric(18,2), default=0)
    vat_amount = Column(Numeric(18,2), default=0)
    total_project_cost = Column(Numeric(18,2), default=0)
    # 적용 법정요율 스냅샷 (변경 추적용)
    applied_rates_snapshot = Column(JSONB, default={})
    rates_applied_date = Column(Date)
    calc_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("project_id","work_category"),)

class ProjectTotalCost(Base):
    """프로젝트 전체 공사비 통합"""
    __tablename__ = "project_total_costs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), unique=True)
    arch_cost = Column(Numeric(18,2), default=0)
    mech_fire_cost = Column(Numeric(18,2), default=0)
    elec_comm_cost = Column(Numeric(18,2), default=0)
    landscape_cost = Column(Numeric(18,2), default=0)
    civil_cost = Column(Numeric(18,2), default=0)
    direct_cost_total = Column(Numeric(18,2), default=0)
    design_cost = Column(Numeric(18,2), default=0)
    supervision_cost = Column(Numeric(18,2), default=0)
    land_cost = Column(Numeric(18,2), default=0)
    acquisition_tax = Column(Numeric(18,2), default=0)
    finance_cost = Column(Numeric(18,2), default=0)
    total_project_cost = Column(Numeric(18,2), default=0)
    expected_revenue = Column(Numeric(18,2), default=0)
    net_profit = Column(Numeric(18,2), default=0)
    profit_rate = Column(Numeric(5,4), default=0)
    irr = Column(Numeric(5,4), default=0)
    npv = Column(Numeric(18,2), default=0)
    bim_model_version = Column(String(50))
    last_bim_sync = Column(DateTime)
    calc_version = Column(Integer, default=1)
    calc_at = Column(DateTime, default=datetime.utcnow)

class ProgressBilling(Base):
    """기성 관리 (감리 연동)"""
    __tablename__ = "progress_billings"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    billing_no = Column(Integer, nullable=False)
    billing_period_from = Column(Date, nullable=False)
    billing_period_to = Column(Date, nullable=False)
    work_code = Column(String(20))
    work_category = Column(String(50))
    planned_qty = Column(Numeric(18,4))
    actual_qty = Column(Numeric(18,4))
    progress_rate = Column(Numeric(5,4))
    planned_amount = Column(Numeric(18,2))
    actual_amount = Column(Numeric(18,2))
    cumulative_amount = Column(Numeric(18,2))
    supervisor_confirm = Column(Boolean, default=False)
    supervisor_name = Column(String(100))
    confirm_date = Column(Date)
    bcws = Column(Numeric(18,2))
    bcwp = Column(Numeric(18,2))
    acwp = Column(Numeric(18,2))
    spi = Column(Numeric(5,4))
    cpi = Column(Numeric(5,4))
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("idx_progress_billing_project","project_id","billing_no"),)

class MonteCarloResult(Base):
    """몬테카를로 시뮬레이션 결과"""
    __tablename__ = "monte_carlo_results"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    sim_type = Column(String(50), nullable=False)   # 공사비/수익률/설계대안
    iterations = Column(Integer, nullable=False, default=10000)
    p10_value = Column(Numeric(18,2))
    p50_value = Column(Numeric(18,2))
    p80_value = Column(Numeric(18,2))
    p90_value = Column(Numeric(18,2))
    mean_value = Column(Numeric(18,2))
    std_dev = Column(Numeric(18,2))
    cv = Column(Numeric(7,4))
    converged = Column(Boolean, default=False)
    risk_contributions = Column(JSONB, default={})
    recommended_value = Column(Numeric(18,2))
    contingency_rate = Column(Numeric(5,2))
    sim_at = Column(DateTime, default=datetime.utcnow)

# ============================================================
# 5. 법정요율 자동갱신
# ============================================================
class LegalRateHistory(Base):
    """법정보험료율 갱신 이력"""
    __tablename__ = "legal_rate_history"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rate_category = Column(String(50), nullable=False)
    rate_value = Column(Numeric(8,6), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    gov_notice_no = Column(String(100))
    gov_notice_url = Column(Text)
    source_api = Column(String(200))
    applied_to = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("idx_legal_rate","rate_category","effective_from"),)

class StandardPriceUpdate(Base):
    """표준품셈 갱신 이력"""
    __tablename__ = "standard_price_updates"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    price_period = Column(String(20), nullable=False)   # 2026H1, 2026H2
    update_type = Column(String(30), nullable=False)     # 품셈/시장단가
    gov_notice_no = Column(String(100))
    effective_from = Column(Date, nullable=False)
    price_count = Column(Integer)
    source_url = Column(Text)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

## STEP 4: Alembic 마이그레이션 설정

```python
# propai/apps/api/alembic.ini (생성)
# propai/apps/api/alembic/env.py
import asyncio
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from app.core.config import settings
from app.models.base import Base
import app.models.base  # 모든 모델 임포트

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = settings.DATABASE_URL
    context.configure(url=url, target_metadata=target_metadata,
                       literal_binds=True, dialect_opts={"paramstyle":"named"})
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    connectable = create_async_engine(settings.DATABASE_URL)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

---

## STEP 5: 시드 데이터 -- 2026년 법정요율 + 표준품셈

```python
# propai/apps/api/app/seeds/run_all_seeds.py
"""전체 시드 데이터 실행 스크립트"""
import asyncio
from app.core.database import AsyncSessionLocal
from app.seeds.legal_rates_2026 import seed_legal_rates
from app.seeds.standard_prices_2026 import seed_standard_prices
from app.seeds.work_type_seed import seed_work_types
from app.seeds.permit_docs_seed import seed_permit_docs
import structlog

logger = structlog.get_logger()

async def run_all():
    async with AsyncSessionLocal() as db:
        await seed_legal_rates(db)
        await seed_standard_prices(db)
        await seed_work_types(db)
        await seed_permit_docs(db)
        await db.commit()
    logger.info("All seeds completed")

if __name__ == "__main__":
    asyncio.run(run_all())
```

```python
# propai/apps/api/app/seeds/legal_rates_2026.py
"""
2026년 법정보험료율 시드 데이터
근거: 고용노동부 고시 + 보건복지부 고시 + 국민연금법 개정
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import LegalRateHistory
from datetime import date

RATES_2026 = [
    # (category, value, notice_no)
    ("산재보험_건설업",   0.035000, "2026-01-01", "고용노동부고시 제2025-XX호"),
    ("고용보험_실업급여", 0.009000, "2026-01-01", "고용보험법시행령"),
    ("건강보험_사업주",   0.035950, "2026-01-01", "건강보험료율7.19% 1/2"),
    ("국민연금_사업주",   0.047500, "2026-01-01", "국민연금법개정(9%->9.5%)"),
    ("장기요양보험료",    0.004724, "2026-01-01", "보건복지부고시(0.9448%)"),
    ("퇴직공제부금비",    0.021000, "2026-01-01", "건설근로자퇴직공제법"),
    ("간접노무비율",      0.144000, "2026-01-01", "예정가격작성기준예규653호"),
    ("일반관리비율",      0.055000, "2026-01-01", "예정가격작성기준"),
    ("이윤상한",          0.150000, "2026-01-01", "예정가격작성기준"),
    ("안전보건관리비",    0.020700, "2026-01-01", "건설기술진흥법시행령"),
    ("환경보전비",        0.001600, "2026-01-01", "환경부고시"),
    ("부가가치세",        0.100000, "2026-01-01", "부가가치세법"),
]

async def seed_legal_rates(db: AsyncSession):
    for cat, val, eff_date, notice in RATES_2026:
        existing = await db.get(LegalRateHistory,
            {"rate_category": cat, "effective_from": date(2026,1,1)})
        if not existing:
            db.add(LegalRateHistory(
                rate_category=cat,
                rate_value=val,
                effective_from=date(2026,1,1),
                gov_notice_no=notice,
                source_api="seed_2026"
            ))
```

```python
# propai/apps/api/app/seeds/standard_prices_2026.py
"""
표준품셈 2025 기준 + 2026년 건설물가 반영 단가
근거: 국토교통부 공고 제2024-1782호 + 시장단가 2025H2
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import MaterialUnitPrice
from datetime import date

# 2026년 1월 시행 단가 (표준품셈2025 기준 + 건설물가지수 반영)
PRICES_2026 = [
    # (code, name, spec, unit, mat, labor, exp, source)
    ("RC-001","철근D10","SD400","TON",940560,184140,0,"표준시장단가2025H2"),
    ("RC-002","철근D13","SD400","TON",930330,179025,0,"표준시장단가2025H2"),
    ("RC-003","철근D16","SD400","TON",919800,173910,0,"표준시장단가2025H2"),
    ("RC-004","철근D19","SD400","TON",914985,171864,0,"표준시장단가2025H2"),
    ("RC-005","레미콘21MPa","25-21-12","M3",97185,18414,3069,"레미콘협동조합2025H2"),
    ("RC-006","레미콘24MPa","25-24-12","M3",104346,18932,3274,"레미콘협동조합2025H2"),
    ("RC-007","레미콘27MPa","25-27-12","M3",112530,19437,3581,"레미콘협동조합2025H2"),
    ("RC-008","거푸집_유로폼","알루미늄유로폼","M2",28644,32736,5115,"표준품셈2025"),
    ("RC-009","거푸집_시스템폼","시스템동바리","M2",35805,28644,4604,"표준품셈2025"),
    ("WP-001","우레탄방수1종","우레탄2액형 도막","M2",25575,18414,2046,"표준품셈2025"),
    ("WP-002","시트방수","개량아스팔트시트","M2",35805,22506,2558,"표준품셈2025"),
    ("WP-003","도막방수","아크릴계","M2",18414,15345,1535,"표준품셈2025"),
    ("WW-001","PVC창호","단열PVC이중창","M2",184140,46035,8189,"표준품셈2025"),
    ("WW-002","AL창호","알루미늄복합창","M2",225060,56265,10230,"표준품셈2025"),
    ("WW-003","시스템창호","고단열시스템창","M2",388740,66495,12276,"표준품셈2025"),
    ("TL-001","내장타일300","300x300 도기질","M2",35805,46035,5115,"표준품셈2025"),
    ("TL-002","외장타일600","600x600 자기질","M2",66495,56265,6138,"표준품셈2025"),
    ("PT-001","수성페인트2회","외부용수성","M2",8184,12276,1023,"표준품셈2025"),
    ("ME-001","냉난방설비_공동","공동주택세대용","세대",3580500,818400,204600,"표준품셈2025"),
    ("ME-002","급배수설비_세대","공동주택세대용","세대",2250600,613800,153450,"표준품셈2025"),
    ("EL-001","전기설비_세대59","59A형","세대",2864400,716100,184140,"표준품셈2025"),
    ("EL-002","전기설비_세대84","84A형","세대",3580500,869850,225060,"표준품셈2025"),
    ("LS-001","느티나무R10","근원직경100mm이상","주",388740,86985,15345,"조달청2025"),
    ("LS-002","잔디_들잔디","들잔디롤잔디","M2",8184,5115,512,"조달청2025"),
    ("LS-003","화강석포장","G1포장(30T)","M2",46035,35805,5115,"조달청2025"),
    ("CV-001","H파일시공","H-300x300","M",86985,46035,15345,"표준품셈2025"),
    ("CV-002","흙막이판시공","라이너플레이트","M2",35805,25575,8184,"표준품셈2025"),
    ("TMP-001","가설사무소_감리","조립식","M2/월",0,0,46050,"표준품셈2025"),
    ("TMP-002","가설사무소_수급","조립식","M2/월",0,0,35810,"표준품셈2025"),
    ("TMP-003","타워크레인기초","기초앙카포함","개소",8695500,3273600,818400,"표준품셈2025"),
]

async def seed_standard_prices(db: AsyncSession):
    for row in PRICES_2026:
        code,name,spec,unit,mat,labor,exp,source = row
        db.add(MaterialUnitPrice(
            material_code=code,
            material_name=name,
            spec=spec,
            unit=unit,
            material_price=mat,
            labor_price=labor,
            expense_price=exp,
            price_basis_year=2026,
            price_source=source,
            region="전국",
            valid_from=date(2026,1,1),
            is_current=True
        ))
```

---

## STEP 6: FastAPI 앱 엔트리포인트

```python
# propai/apps/api/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import structlog
from app.core.config import settings
from app.core.database import init_db

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PropAI v61.0 시작", environment=settings.ENVIRONMENT)
    await init_db()
    # 법정요율 최신 확인 (시작 시)
    try:
        from app.services.rates.legal_rate_updater import LegalRateAutoUpdater
        await LegalRateAutoUpdater().check_and_notify()
    except Exception as e:
        logger.warning("법정요율 체크 실패 (시드 데이터 사용)", error=str(e))
    yield
    logger.info("PropAI v61.0 종료")

app = FastAPI(
    title="PropAI v61.0 -- 부동산 전주기 AI 자동화 플랫폼",
    description="AI CAD 건축설계 + BIM 공사비 자동산출 통합 시스템",
    version="61.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
from app.api.v1.endpoints import (
    auth, projects, gis, design_drawing,
    bim_cost, progress_billing, feasibility,
    permits, esg, rates, notifications
)

ROUTERS = [
    auth.router, projects.router, gis.router,
    design_drawing.router, bim_cost.router,
    progress_billing.router, feasibility.router,
    permits.router, esg.router, rates.router,
    notifications.router,
]
for router in ROUTERS:
    app.include_router(router)

@app.get("/health", tags=["시스템"])
async def health_check():
    return {
        "status": "OK",
        "version": "61.0.0",
        "applied_rates_year": 2026,
        "standard_price_basis": "표준품셈2025+시장단가2025H2",
        "modules": [
            "AI_CAD_설계도면",
            "BIM_공사비_자동산출",
            "법정요율_자동갱신",
            "몬테카를로_시뮬레이션",
            "인허가_도서관리",
        ]
    }
```

---

## STEP 7: 실행 검증

```bash
# Docker 전체 실행
cd propai
docker-compose up -d postgres redis qdrant

# 백엔드 직접 실행 (개발)
cd apps/api
pip install -r requirements.txt
alembic upgrade head
python -m app.seeds.run_all_seeds
uvicorn app.main:app --reload --port 8000

# 프론트엔드
cd apps/web
npm install
npm run dev

# 헬스체크
curl http://localhost:8000/health
# 예상: {"status":"OK","version":"61.0.0",...}

# API 문서
open http://localhost:8000/docs
```

---

## [Part 1 완료 -- Part 2 (AI CAD 설계도면 시스템)로 진행]
================================================================================
