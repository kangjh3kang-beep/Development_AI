"""하네스 — 아웃박스 발행 + 동기 인프로세스 투영(시행사 집계).

사용자 결정: Redis/Celery 미배포 → 커밋 트랜잭션 내에서 동기로
(1) PII 화이트리스트 적용 아웃박스 기록, (2) sales_site_summary 증분 투영 을 함께 수행.
추후 비동기(Redis Streams) 전환 시 emit_outbox 는 그대로 두고 투영만 분리하면 됨.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.commission_mh_harness import SalesHarnessOutbox
from apps.api.database.models.sales.site_org import SalesSiteSummary

# 상향 허용 필드 화이트리스트(PII 차단): 집계/비식별만 통과
logger = logging.getLogger(__name__)

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
    # ★추첨 공약 공개 — 전부 해시·숫자라 **개인정보가 아니다**(사후 감사자가 `GET …/commitment`
    #   의 공개값과 대조하는 데 쓴다). 이 줄이 없으면 아래 `allow` 가 **빈 집합**이라
    #   payload 가 **통째로 버려지고**, 원장에는 빈 행만 남는다(R2 리뷰 MAJOR-1 실측).
    "DrawCommitmentRevealed": {"announcement_id", "commit_hash", "beacon_round", "beacon",
                               "participants_hash", "pool_hash"},
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
    # ★★**모르는 이벤트는 조용히 빈 행이 된다** — 그게 이 함수의 가장 위험한 성질이다.
    #   실측(R2 리뷰 MAJOR-1): 화이트리스트에 없는 이벤트를 내보냈더니 payload 가 `{}` 가 됐고,
    #   호출부 주석은 *"원장에 남긴다"* 라고 말하고 있었다. ***침묵하는 손실은 손실보다 나쁘다.***
    #   ⇒ **적어도 시끄럽게** 만든다(차단은 하지 않는다 — 기존 이벤트를 깨지 않기 위해).
    #   그리고 `tests/test_outbox_whitelist_covers_every_emitter.py` 가 **호출부를 AST 로 파생**해
    #   누락을 CI 에서 막는다(주석만으로는 다음 사람이 또 밟는다).
    if event_type not in WHITELIST:
        logger.warning(
            "emit_outbox: 화이트리스트에 없는 이벤트 %r — payload %d개 키가 **버려진다**. "
            "WHITELIST 에 추가하지 않으면 원장에 빈 행만 남는다.",
            event_type, len(payload or {}))
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
