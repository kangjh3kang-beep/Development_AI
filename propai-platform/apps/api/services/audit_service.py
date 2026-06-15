"""법적 감사 추적 서비스.

INSERT-ONLY 패턴: 규제 준수를 위해 삭제/수정 불가.
모든 쓰기 작업(create/update/delete) 시 호출한다.
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.legal_audit_trail import LegalAuditTrail

logger = structlog.get_logger(__name__)


async def record_audit(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    entity_type: str,
    entity_id: UUID,
    action: str,
    actor_id: UUID,
    before_state: dict | None = None,
    after_state: dict | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
) -> LegalAuditTrail:
    """감사 추적 레코드를 생성한다 (INSERT-ONLY)."""
    trail = LegalAuditTrail(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        before_state=before_state,
        after_state=after_state,
        reason=reason,
        ip_address=ip_address,
    )
    db.add(trail)
    await db.flush()

    # Phase 0 unit b2: legal 감사 이벤트를 원장 단일 SSOT에도 흡수(best-effort).
    try:
        from app.services.ledger.audit_ledger import append_audit
        await append_audit(
            action=action, user_id=str(actor_id), resource_type=entity_type,
            resource_id=str(entity_id), tenant_id=str(tenant_id),
            changes={"before": before_state, "after": after_state},
            metadata={"reason": reason, "ip_address": ip_address},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("감사 원장 흡수 실패", err=str(e)[:120])

    return trail
