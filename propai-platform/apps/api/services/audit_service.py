"""법적 감사 추적 서비스.

INSERT-ONLY 패턴: 규제 준수를 위해 삭제/수정 불가.
모든 쓰기 작업(create/update/delete) 시 호출한다.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.legal_audit_trail import LegalAuditTrail


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
    return trail
