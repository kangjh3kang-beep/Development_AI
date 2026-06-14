"""자가성장 엔진 — 부팅 시 스키마 멱등 보장(billing_service._ensure_* 선례).

마이그레이션(v62_5_self_growth_tables)이 정본이지만, 미적용 환경(개발/신규배포)
에서도 부팅 시 텔레메트리 3 테이블·인덱스를 자동 보장한다.
CREATE TABLE/INDEX IF NOT EXISTS 만 사용(파괴적 변경 없음). best-effort.

⚠️ 컬럼/인덱스는 database/models/platform_event.py ORM 과 정합 유지.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 최초 1회만 실행하기 위한 프로세스 로컬 가드(billing_service._SCHEMA_READY 선례).
_SCHEMA_READY = False

_PLATFORM_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS platform_events (
    id bigserial PRIMARY KEY,
    event_id uuid,
    tenant_id uuid,
    user_hash text,
    session_id text,
    event_type text NOT NULL,
    surface text,
    route text,
    status_code integer,
    latency_ms integer,
    severity text,
    service text,
    payload jsonb,
    app_version text,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""

_PLATFORM_INSIGHTS_DDL = """
CREATE TABLE IF NOT EXISTS platform_insights (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid,
    insight_type text NOT NULL,
    window_start timestamptz,
    window_end timestamptz,
    metrics_json jsonb,
    severity text,
    narrative text,
    recommended_action text,
    status varchar(20) NOT NULL DEFAULT 'open',
    created_at timestamptz NOT NULL DEFAULT now()
)
"""

_AI_FEEDBACK_DDL = """
CREATE TABLE IF NOT EXISTS ai_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid,
    user_hash text,
    target_type text NOT NULL,
    service text,
    analysis_type text,
    content_hash text,
    verdict text,
    correction text,
    rating integer,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""

_INDEXES = [
    # platform_events
    "CREATE INDEX IF NOT EXISTS idx_pe_type_created ON platform_events (event_type, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_pe_tenant_created ON platform_events (tenant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_pe_route_status ON platform_events (route, status_code)",
    "CREATE INDEX IF NOT EXISTS idx_pe_service_created ON platform_events (service, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_pe_created ON platform_events (created_at)",
    # event_id 멱등(중복전송 차단). NULL 은 UNIQUE 에서 충돌하지 않음.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_pe_event_id ON platform_events (event_id)",
    # platform_insights
    "CREATE INDEX IF NOT EXISTS idx_pi_type_created ON platform_insights (insight_type, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_pi_severity_status ON platform_insights (severity, status)",
    "CREATE INDEX IF NOT EXISTS idx_pi_created ON platform_insights (created_at)",
    # ai_feedback
    "CREATE INDEX IF NOT EXISTS idx_af_tenant ON ai_feedback (tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_af_service_verdict_created ON ai_feedback (service, verdict, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_af_analysis_hash ON ai_feedback (analysis_type, content_hash)",
]


async def ensure_schema(db: AsyncSession, force: bool = False) -> bool:
    """텔레메트리 3 테이블·인덱스를 멱등 보장한다. 성공 시 True.

    부팅 시 1회 호출(load_into_env 인접). 실패는 graceful(rollback 후 False).
    """
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return True
    try:
        await db.execute(text(_PLATFORM_EVENTS_DDL))
        await db.execute(text(_PLATFORM_INSIGHTS_DDL))
        await db.execute(text(_AI_FEEDBACK_DDL))
        for ddl in _INDEXES:
            await db.execute(text(ddl))
        await db.commit()
        _SCHEMA_READY = True
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("growth schema_guard 실패: %s", str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
