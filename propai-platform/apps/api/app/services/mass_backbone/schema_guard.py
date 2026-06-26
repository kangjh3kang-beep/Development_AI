"""매스 백본 — 부팅 시 mass_templates 테이블 멱등 보장(growth/memory schema_guard 선례).

이 플랫폼은 alembic CLI 비번 interpolation 이슈로 신규 테이블을 부팅 schema_guard로 보장하는 게 표준.
CREATE TABLE/INDEX IF NOT EXISTS만 사용(파괴적 변경 없음)·best-effort(실패해도 호출경로 불변).

⚠️ 컬럼은 app/models/mass_template.py(MassTemplate ORM)와 정합 유지(float·jsonb·timestamptz).
★현재 미배선(휴면) — main.py lifespan 부팅 훅 연결은 D1.5(영속) 단계에서. 집계 서비스(순수)는 이 테이블
불요. 표준 mass_templates 영속이 필요할 때 ensure_mass_schema를 부팅 1회 호출(growth schema_guard 인접).
"""

from __future__ import annotations

import contextlib
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_MASS_SCHEMA_READY = False

_MASS_TEMPLATES_DDL = """
CREATE TABLE IF NOT EXISTS mass_templates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    region varchar(120) NOT NULL,
    zone_code varchar(60),
    building_type varchar(60) NOT NULL,
    sample_count integer NOT NULL DEFAULT 0,
    median_bcr_pct double precision,
    median_far_pct double precision,
    median_floors double precision,
    median_total_area_sqm double precision,
    source varchar(60) NOT NULL DEFAULT 'building_registry',
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_mt_region ON mass_templates (region)",
    "CREATE INDEX IF NOT EXISTS idx_mt_type ON mass_templates (building_type)",
    "CREATE INDEX IF NOT EXISTS idx_mt_zone ON mass_templates (zone_code)",
]


async def ensure_mass_schema(db: AsyncSession, force: bool = False) -> bool:
    """mass_templates 테이블·인덱스를 멱등 보장한다. 성공 시 True.

    부팅 1회 호출(growth schema_guard 인접). 실패는 graceful(rollback 후 False)."""
    global _MASS_SCHEMA_READY
    if _MASS_SCHEMA_READY and not force:
        return True
    try:
        await db.execute(text(_MASS_TEMPLATES_DDL))
        for ddl in _INDEXES:
            await db.execute(text(ddl))
        await db.commit()
        _MASS_SCHEMA_READY = True
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("mass_templates schema_guard 실패: %s", str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False
