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

# Phase 3(L0/L1) — 임계값 일시조정·피처플래그 저장소(마이그레이션 v62_6 가 정본).
_PLATFORM_SETTINGS_DDL = """
CREATE TABLE IF NOT EXISTS platform_settings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key text NOT NULL,
    value jsonb,
    scope text NOT NULL DEFAULT 'global',
    ttl_expires_at timestamptz,
    updated_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
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
    # platform_settings (Phase 3): (key, scope) upsert 키 + TTL 인덱스.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_ps_key_scope ON platform_settings (key, scope)",
    "CREATE INDEX IF NOT EXISTS idx_ps_ttl ON platform_settings (ttl_expires_at)",
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
        await db.execute(text(_PLATFORM_SETTINGS_DDL))
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


# ════════════════════════════════════════════════════════════════════════════
# platform_settings 헬퍼 (Phase 3 — TTL 만료 자동원복, L0/L1 설정 읽기/쓰기)
# ════════════════════════════════════════════════════════════════════════════
# 임계값 일시상향(threshold_relax)·피처플래그 등 자동조치가 기록하는 설정의
# 단일 접근점. TTL 만료 시 get_setting 은 None(논리 만료 — 별도 prune 없이도
# 만료 즉시 원래값으로 폴백). 모든 함수 best-effort: 실패해도 호출경로 불변.

import json as _json  # noqa: E402


async def get_setting(db, key: str, scope: str = "global"):
    """key/scope 설정값(jsonb)을 반환. 미존재 또는 TTL 만료 시 None.

    ttl_expires_at 이 과거면 만료로 간주(자동원복 = None 반환). prune 은 별도.
    """
    try:
        row = (await db.execute(text(
            "SELECT value, ttl_expires_at FROM platform_settings "
            "WHERE key = :k AND scope = :s"
        ), {"k": key, "s": scope})).fetchone()
        if row is None:
            return None
        value, ttl = row[0], row[1]
        if ttl is not None:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            # ttl 이 naive 면 UTC 로 가정해 비교(드라이버별 tz 처리 방어).
            if ttl.tzinfo is None:
                ttl = ttl.replace(tzinfo=timezone.utc)
            if ttl <= now:
                return None  # 만료 → 논리적 원복.
        if isinstance(value, str):
            try:
                return _json.loads(value)
            except Exception:  # noqa: BLE001
                return value
        return value
    except Exception as e:  # noqa: BLE001
        logger.debug("get_setting 실패(%s): %s", key, str(e)[:120])
        return None


async def set_setting(db, key: str, value, *, scope: str = "global",
                      ttl_expires_at=None, updated_by: str | None = None) -> bool:
    """key/scope 설정을 upsert. ttl_expires_at(UTC datetime) 지정 시 만료 자동원복.

    (key, scope) UNIQUE 기준 ON CONFLICT 갱신. 성공 시 True.
    """
    try:
        await db.execute(text(
            "INSERT INTO platform_settings (key, value, scope, ttl_expires_at, updated_by) "
            "VALUES (:k, CAST(:v AS jsonb), :s, :ttl, :ub) "
            "ON CONFLICT (key, scope) DO UPDATE SET "
            "  value = EXCLUDED.value, ttl_expires_at = EXCLUDED.ttl_expires_at, "
            "  updated_by = EXCLUDED.updated_by, updated_at = now()"
        ), {
            "k": key, "s": scope, "ttl": ttl_expires_at, "ub": updated_by,
            "v": _json.dumps(value, ensure_ascii=False, default=str),
        })
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("set_setting 실패(%s): %s", key, str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


async def clear_setting(db, key: str, scope: str = "global") -> bool:
    """key/scope 설정을 즉시 삭제(롤백 = 원래값으로 즉시 원복). 성공 시 True."""
    try:
        await db.execute(text(
            "DELETE FROM platform_settings WHERE key = :k AND scope = :s"
        ), {"k": key, "s": scope})
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("clear_setting 실패(%s): %s", key, str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
