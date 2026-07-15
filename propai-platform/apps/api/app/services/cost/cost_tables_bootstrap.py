"""v61 공사비 테이블 멱등 부트스트랩 — Alembic 불사용(런타임 CREATE TABLE IF NOT EXISTS).

프로덕션 DB에 alembic_version 테이블이 없어(런타임 생성 패턴), analysis_ledger_service._ensure
패턴을 그대로 따른다:
 - CREATE TABLE IF NOT EXISTS 로 v61_cost.py ORM 대응 테이블(MVP 필요분)을 멱등 생성.
 - 표준단가 시드 42개를 INSERT ... ON CONFLICT DO NOTHING 으로 멱등 적재.
 - 라우터 첫 사용 시 lazy 호출 → 배포되면 자동 생성, 수동 마이그레이션 불필요.

기존 데이터 무영향(IF NOT EXISTS·ON CONFLICT). 프로덕션 DB는 배포 후 자동 실행 전제.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# ── DDL: v61_cost.py ORM 대응(MVP 필요분) ──
# material_code 에 UNIQUE 제약 부여(시드 ON CONFLICT 대상 — SSOT 조회 키).
_DDL_MATERIAL_UNIT_PRICES = (
    "CREATE TABLE IF NOT EXISTS material_unit_prices ("
    "  id bigserial PRIMARY KEY,"
    "  material_code varchar(50) NOT NULL,"
    "  material_name varchar(300) NOT NULL,"
    "  spec varchar(300),"
    "  unit varchar(20) NOT NULL,"
    "  material_price numeric(18,2) DEFAULT 0,"
    "  labor_price numeric(18,2) DEFAULT 0,"
    "  expense_price numeric(18,2) DEFAULT 0,"
    "  price_basis_year int DEFAULT 2026,"
    "  price_source varchar(100) DEFAULT '표준품셈2025',"
    "  region varchar(50) DEFAULT '경기도',"
    "  valid_from date,"
    "  valid_to date,"
    "  is_current boolean DEFAULT true,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
# material_code UNIQUE(부분 인덱스 아님 — 시드 멱등 ON CONFLICT 대상)
_DDL_MATERIAL_UQ = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_material_unit_prices_code "
    "ON material_unit_prices(material_code)"
)
# P1 단가 4계층 리졸버(T1 공공고시) — 기존 배포 테이블에도 멱등 보강(신규 컬럼, 기존 데이터 무영향).
_DDL_MATERIAL_SOURCE_URL = (
    "ALTER TABLE material_unit_prices ADD COLUMN IF NOT EXISTS source_url varchar(500)"
)

_DDL_COST_WORK_TYPES = (
    "CREATE TABLE IF NOT EXISTS cost_work_types ("
    "  id bigserial PRIMARY KEY,"
    "  project_id uuid,"
    "  work_code varchar(20) NOT NULL,"
    "  work_name varchar(200) NOT NULL,"
    "  parent_code varchar(20),"
    "  work_level int DEFAULT 1,"
    "  work_category varchar(50) NOT NULL,"
    "  work_division varchar(50),"
    "  unit varchar(20),"
    "  is_subtotal boolean DEFAULT false,"
    "  sort_order int DEFAULT 0,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_DDL_WORK_TYPE_UQ = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cost_work_types_code "
    "ON cost_work_types(work_code)"
)

_DDL_BIM_QUANTITIES = (
    "CREATE TABLE IF NOT EXISTS bim_quantities ("
    "  id bigserial PRIMARY KEY,"
    "  project_id uuid NOT NULL,"
    "  tenant_id uuid,"  # PR#315 H2: 정본 ORM(TenantMixin)과 물리스키마 정합 — nullable(백필 금지)
    "  ifc_global_id varchar(100),"
    "  ifc_object_type varchar(100),"
    "  ifc_object_name varchar(300),"
    "  work_code varchar(20),"
    "  floor_level varchar(50),"
    "  zone varchar(100),"
    "  quantity numeric(18,4) DEFAULT 0,"
    "  unit varchar(20),"
    "  quantity_formula text,"
    "  extraction_method varchar(50) DEFAULT 'AI_AUTO',"
    "  verified boolean DEFAULT false,"
    "  created_at timestamptz DEFAULT now(),"
    "  updated_at timestamptz DEFAULT now()"
    ")"
)
# PR#315 H2: 기존 배포 테이블(CREATE IF NOT EXISTS 로 스킵되는 경우)에도 멱등 보강.
# nullable 추가 — NOT NULL 백필은 운영 리스크라 금지(기존 행 무영향, 신규 행부터 채움).
_DDL_BIM_QUANTITIES_TENANT = (
    "ALTER TABLE bim_quantities ADD COLUMN IF NOT EXISTS tenant_id uuid"
)

_DDL_PROGRESS_BILLINGS = (
    "CREATE TABLE IF NOT EXISTS progress_billings ("
    "  id bigserial PRIMARY KEY,"
    "  project_id uuid NOT NULL,"
    "  billing_no int NOT NULL,"
    "  period_from date,"
    "  period_to date,"
    "  work_entries jsonb DEFAULT '[]'::jsonb,"
    "  planned_value numeric(18,2) DEFAULT 0,"
    "  earned_value numeric(18,2) DEFAULT 0,"
    "  actual_cost numeric(18,2) DEFAULT 0,"
    "  evm_spi double precision,"
    "  evm_cpi double precision,"
    "  notes text,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)

# BOQ 헤더(원가계산서) — cost_estimate
_DDL_COST_ESTIMATE = (
    "CREATE TABLE IF NOT EXISTS cost_estimate ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  project_id text,"
    "  tenant_id text,"
    "  building_type varchar(50),"
    "  structure_type varchar(50),"
    "  total_gfa_sqm numeric(18,2),"
    "  direct_won numeric(20,2) DEFAULT 0,"
    "  indirect_won numeric(20,2) DEFAULT 0,"
    "  total_won numeric(20,2) DEFAULT 0,"
    "  confidence_grade varchar(20),"
    "  qto_source varchar(20),"
    "  summary jsonb DEFAULT '{}'::jsonb,"
    "  badges jsonb DEFAULT '{}'::jsonb,"
    "  created_by text,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_DDL_COST_ESTIMATE_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_cost_estimate_project "
    "ON cost_estimate(project_id, created_at DESC)"
)

# BOQ 항목 — cost_estimate_item
_DDL_COST_ESTIMATE_ITEM = (
    "CREATE TABLE IF NOT EXISTS cost_estimate_item ("
    "  id bigserial PRIMARY KEY,"
    "  estimate_id uuid NOT NULL,"
    "  code varchar(50),"
    "  name varchar(300),"
    "  work_type varchar(100),"
    "  quantity numeric(18,4) DEFAULT 0,"
    "  unit varchar(20),"
    "  unit_price numeric(18,2) DEFAULT 0,"
    "  amount numeric(20,2) DEFAULT 0,"
    "  price_source varchar(50),"
    "  price_basis_year int,"
    "  qto_source varchar(20),"
    "  market_unit_price numeric(18,2),"
    "  actual_unit_price numeric(18,2),"
    "  sort_order int DEFAULT 0"
    ")"
)
_DDL_COST_ESTIMATE_ITEM_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_cost_estimate_item_estimate "
    "ON cost_estimate_item(estimate_id, sort_order)"
)

_ALL_DDL = (
    _DDL_MATERIAL_UNIT_PRICES, _DDL_MATERIAL_UQ, _DDL_MATERIAL_SOURCE_URL,
    _DDL_COST_WORK_TYPES, _DDL_WORK_TYPE_UQ,
    _DDL_BIM_QUANTITIES, _DDL_BIM_QUANTITIES_TENANT,
    _DDL_PROGRESS_BILLINGS,
    _DDL_COST_ESTIMATE, _DDL_COST_ESTIMATE_IDX,
    _DDL_COST_ESTIMATE_ITEM, _DDL_COST_ESTIMATE_ITEM_IDX,
)

_ENSURED = False  # 프로세스 내 1회 보장(중복 DDL 방지 — 멱등하지만 호출 절감)


async def _ensure_cost_tables(db) -> None:
    """v61 공사비 테이블을 멱등 생성하고 표준단가·공종 시드를 멱등 적재한다.

    analysis_ledger_service._ensure 와 동일 패턴(CREATE IF NOT EXISTS). 기존 데이터 무영향.
    프로세스 내 1회만 실제 실행(이후 no-op).
    """
    global _ENSURED
    if _ENSURED:
        return
    from sqlalchemy import text

    for ddl in _ALL_DDL:
        await db.execute(text(ddl))
    await _seed_unit_prices(db)
    await _seed_work_types(db)
    await db.commit()
    _ENSURED = True


async def _seed_unit_prices(db) -> None:
    """표준단가 42개 멱등 적재(INSERT ... ON CONFLICT (material_code) DO NOTHING)."""
    from sqlalchemy import text

    from app.services.seed.v61_seed_data import seed_standard_prices_2026

    rows = seed_standard_prices_2026()
    sql = text(
        "INSERT INTO material_unit_prices"
        "(material_code, material_name, spec, unit, material_price, labor_price, expense_price,"
        " price_basis_year, price_source, region, is_current)"
        " VALUES (:material_code,:material_name,:spec,:unit,:material_price,:labor_price,:expense_price,"
        " :price_basis_year,:price_source,:region, true)"
        " ON CONFLICT (material_code) DO NOTHING"
    )
    for r in rows:
        await db.execute(sql, {
            "material_code": r["material_code"],
            "material_name": r["material_name"],
            "spec": r.get("spec"),
            "unit": r["unit"],
            "material_price": r.get("material_price", 0),
            "labor_price": r.get("labor_price", 0),
            "expense_price": r.get("expense_price", 0),
            "price_basis_year": r.get("price_basis_year", 2026),
            "price_source": r.get("price_source", "표준품셈2025"),
            "region": r.get("region", "경기도"),
        })


async def _seed_work_types(db) -> None:
    """공종 분류 멱등 적재(INSERT ... ON CONFLICT (work_code) DO NOTHING)."""
    from sqlalchemy import text

    from app.services.seed.v61_seed_data import seed_work_types

    rows = seed_work_types()
    sql = text(
        "INSERT INTO cost_work_types"
        "(work_code, work_name, parent_code, work_level, work_category, sort_order)"
        " VALUES (:work_code,:work_name,:parent_code,:work_level,:work_category,:sort_order)"
        " ON CONFLICT (work_code) DO NOTHING"
    )
    for r in rows:
        await db.execute(sql, {
            "work_code": r["work_code"],
            "work_name": r["work_name"],
            "parent_code": r.get("parent_code"),
            "work_level": r.get("work_level", 1),
            "work_category": r["work_category"],
            "sort_order": r.get("sort_order", 0),
        })
