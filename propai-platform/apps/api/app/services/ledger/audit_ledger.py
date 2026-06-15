"""감사 이벤트 → 분석원장(analysis_ledger) 단일 SSOT 흡수.

무결성 단일화(Phase 0 unit b): in-memory AuditTrailService의 별도 SHA256 해시체인을 폐기하고,
모든 감사 이벤트를 원장에 analysis_type='audit'로 누적한다(단일 체인·단일 verify_chain).

체인 키: 합성 주소 '__audit__/<tenant>'(비-NULL·안정 — 원장의 빈-주소 NULL 키 함정 회피).
각 이벤트는 event_id/event_ts로 유일 → 원장의 멱등 dedup에 삼켜지지 않음.
정직·best-effort: append 실패가 본 작업을 막지 않음(호출부는 반환 dict의 ok만 확인).
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from app.services.ledger import analysis_ledger_service as ledger

AUDIT_ANALYSIS_TYPE = "audit"


def audit_stream_address(tenant_id: str | None) -> str:
    """테넌트별 감사 체인 키(합성 주소, 비-NULL·안정)."""
    return f"__audit__/{tenant_id or 'global'}"


def build_audit_payload(
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    user_id: str | None,
    event_id: str,
    event_ts: float,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """감사 1건의 결정적 원장 payload. event_id/event_ts는 호출부 주입(테스트 결정성)."""
    return {
        "kind": "audit",
        "schema_version": "audit/v1",
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "user_id": user_id,
        "event_id": event_id,
        "event_ts": event_ts,
        "changes": changes or {},
        "metadata": metadata or {},
    }


async def append_audit(
    *,
    action: str,
    user_id: str | None,
    resource_type: str,
    resource_id: str,
    tenant_id: str | None = None,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """감사 이벤트 1건을 원장에 append(analysis_type='audit'). best-effort."""
    payload = build_audit_payload(
        action=action, resource_type=resource_type, resource_id=resource_id,
        user_id=user_id, event_id=uuid.uuid4().hex, event_ts=time.time(),
        changes=changes, metadata=metadata,
    )
    return await ledger.append_analysis(
        analysis_type=AUDIT_ANALYSIS_TYPE, payload=payload,
        tenant_id=tenant_id, address=audit_stream_address(tenant_id),
        source="audit", created_by=user_id,
    )


async def verify_audit_chain(*, tenant_id: str | None = None) -> dict[str, Any]:
    """테넌트 감사 체인 무결성 검증(원장 verify_chain 위임)."""
    return await ledger.verify_chain(
        analysis_type=AUDIT_ANALYSIS_TYPE, tenant_id=tenant_id,
        address=audit_stream_address(tenant_id),
    )
