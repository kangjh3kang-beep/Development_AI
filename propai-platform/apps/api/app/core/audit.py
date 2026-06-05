"""관리자 민감 작업 감사로그 — 책임추적성(accountability).

등급변경·용량상향·시크릿 변경 등 권한/설정 변경을 append-only로 기록.
런타임 idempotent DDL. 실패해도 본 작업은 막지 않음(best-effort).
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DDL = (
    "CREATE TABLE IF NOT EXISTS admin_audit_log ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  actor_id text, actor_role text, tenant_id text,"
    "  action text NOT NULL, target text, detail jsonb,"
    "  created_at timestamptz DEFAULT now())"
)


async def audit_admin_action(
    *, actor_id: str | None, actor_role: str | None, action: str,
    target: str | None = None, tenant_id: str | None = None, detail: dict[str, Any] | None = None,
) -> None:
    try:
        import json as _json
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await db.execute(text(_DDL))
            await db.execute(text(
                "INSERT INTO admin_audit_log(actor_id, actor_role, tenant_id, action, target, detail) "
                "VALUES (:a,:r,:t,:ac,:tg, CAST(:d AS jsonb))"),
                {"a": actor_id, "r": actor_role, "t": tenant_id, "ac": action, "tg": target,
                 "d": _json.dumps(detail or {}, ensure_ascii=False)})
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("감사로그 기록 실패", action=action, err=str(e)[:120])
