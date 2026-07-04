"""하네스 — 아웃박스 발행 + 동기 인프로세스 투영(시행사 집계).

사용자 결정: Redis/Celery 미배포 → 커밋 트랜잭션 내에서 동기로
(1) PII 화이트리스트 적용 아웃박스 기록, (2) sales_site_summary 증분 투영 을 함께 수행.
추후 비동기(Redis Streams) 전환 시 emit_outbox 는 그대로 두고 투영만 분리하면 됨.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.commission_mh_harness import SalesHarnessOutbox
from apps.api.database.models.sales.site_org import SalesSiteSummary

# 상향 허용 필드 화이트리스트(PII 차단): 집계/비식별만 통과
WHITELIST: dict[str, set[str]] = {
    "ContractSigned": {"unit_id", "amount", "stage", "round_id"},
    "ContractCancelled": {"unit_id", "amount"},
    "ApplicationReceived": {"unit_id", "round_id"},
    "UnitStatusChanged": {"unit_id", "from", "to"},
    "UnitInventoryGenerated": {"count"},
    "PricingPublished": {"round_id", "count"},
    "VisitorCheckedIn": {"count", "channel"},
    "CommissionSettled": {"period", "total_net", "total_withholding"},
    "StaffOnboarded": {"node_type", "count_delta"},
}


def _project(event_type: str, payload: dict) -> dict | None:
    """이벤트 → sales_site_summary 증분 컬럼. None 이면 투영 없음."""
    if event_type == "ContractSigned":
        return {"contracts_cnt": 1, "contract_amt": int(payload.get("amount", 0) or 0)}
    if event_type == "ContractCancelled":
        return {"contracts_cnt": -1, "contract_amt": -int(payload.get("amount", 0) or 0)}
    if event_type == "VisitorCheckedIn":
        return {"visitors": int(payload.get("count", 1) or 1)}
    if event_type == "CommissionSettled":
        return {"commission_paid": int(payload.get("total_net", 0) or 0)}
    if event_type == "StaffOnboarded":
        return {"staff_cnt": int(payload.get("count_delta", 0) or 0)}
    return None


async def emit_outbox(db: AsyncSession, site_id: uuid.UUID, event_type: str, payload: dict | None):
    """PII 화이트리스트 적용 후 아웃박스 기록 + 동기 투영 1행 적재."""
    allow = WHITELIST.get(event_type, set())
    clean = {k: v for k, v in (payload or {}).items() if k in allow}
    db.add(SalesHarnessOutbox(
        site_id=site_id, event_type=event_type, payload=clean,
        status="PUBLISHED", published_at=datetime.now(UTC),
    ))
    delta = _project(event_type, payload or {})
    if delta is not None:
        db.add(SalesSiteSummary(
            site_id=site_id, ts=datetime.now(UTC),
            visitors=delta.get("visitors", 0), contracts_cnt=delta.get("contracts_cnt", 0),
            contract_amt=delta.get("contract_amt", 0), staff_cnt=delta.get("staff_cnt", 0),
            commission_paid=delta.get("commission_paid", 0), commission_due=0,
        ))
    await db.flush()
