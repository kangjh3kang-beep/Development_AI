"""수수료 분할지급/유보 — 마일스톤 스케줄(합계≤1) + 유보 차감 + 도래분 지급(원천징수). 취소시 환수 연계."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.commission.engine import payout_net
from apps.api.database.models.sales.commission_ext import SalesCommissionHoldback, SalesCommissionPayoutSchedule
from apps.api.database.models.sales.commission_mh_harness import (
    SalesCommissionEvent,
    SalesCommissionPayout,
    SalesCommissionSplit,
)

# ── 지급 테이블 부가컬럼(tax_type/vat) 멱등 보장 — 정본은 Alembic 033 ─────────────
# ★기존엔 run_due_payouts 의 지급 루프 '매 건' ALTER TABLE ADD COLUMN IF NOT EXISTS 가
#   실행돼 런타임 DDL race + 직렬화 비용이 있었다. 정본을 033 마이그레이션으로 이관하고,
#   런타임 ALTER 는 advisory-lock + 프로세스 1회 게이트로 강등해 race 와 반복 DDL 을 제거한다.
_LOCK_PAYOUT_COLS = 880421102
_PAYOUT_COLS_READY = False
_payout_cols_lock = asyncio.Lock()


async def _ensure_payout_columns(db: AsyncSession | None = None) -> None:
    """sales_commission_payouts 의 tax_type/vat 컬럼 멱등 보장(부팅 안전망) — 프로세스 1회.

    정본은 Alembic 033. 마이그레이션 미적용 환경 대비 ADD COLUMN IF NOT EXISTS 만 수행한다
    (파괴적 변경 없음). 최초 1회 성공 후엔 즉시 반환(no-op) — 지급 루프 매 건 ALTER/직렬화 제거.
    동시 부팅 race 는 advisory-lock(트랜잭션 종료 시 자동해제), 코루틴 경합은 asyncio.Lock 으로 막는다.

    ★[부분커밋 차단] DDL+commit 을 '호출자 세션(db)'에서 하면, run_due_payouts 가 같은 세션에서
      쌓던 지급(Payout) 행이 이 commit 에 휩쓸려 조기 부분커밋된다(이후 오류 시 일부만 남는 위험).
      그래서 DDL 은 항상 '별도 단명 세션'(async_session_factory)에서 수행해 호출자 트랜잭션 경계를
      건드리지 않는다(append_analysis 패턴). 인자 db 는 하위호환 위해 받지만 사용하지 않는다.
    """
    global _PAYOUT_COLS_READY
    if _PAYOUT_COLS_READY:
        return
    async with _payout_cols_lock:
        if _PAYOUT_COLS_READY:
            return
        # ★별도 단명 세션 — 호출자(run_due_payouts) 세션의 미커밋 지급행을 휩쓸지 않도록 격리.
        from app.core.database import async_session_factory
        async with async_session_factory() as ddl_db:
            await ddl_db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_PAYOUT_COLS})
            await ddl_db.execute(text(
                "ALTER TABLE sales_commission_payouts ADD COLUMN IF NOT EXISTS "
                "tax_type varchar(16) DEFAULT 'WITHHOLDING'"))
            await ddl_db.execute(text(
                "ALTER TABLE sales_commission_payouts ADD COLUMN IF NOT EXISTS "
                "vat numeric(16,0) DEFAULT 0"))
            await ddl_db.commit()
        _PAYOUT_COLS_READY = True


async def create_schedule(db: AsyncSession, split_id, milestones: list[dict]):
    total = sum(Decimal(str(m["ratio"])) for m in milestones)
    if total > Decimal("1"):
        raise ValueError("마일스톤 비율 합계가 1을 초과")
    for m in milestones:
        db.add(SalesCommissionPayoutSchedule(split_id=split_id, milestone=m["milestone"],
               ratio=Decimal(str(m["ratio"])), planned_at=m.get("planned_at")))
    await db.flush()


async def set_holdback(db: AsyncSession, split_id, reason, amount, release_condition=None):
    db.add(SalesCommissionHoldback(split_id=split_id, reason=reason, amount=amount,
           release_condition=release_condition))
    await db.flush()


async def release_holdback(db: AsyncSession, holdback_id):
    h = (await db.execute(select(SalesCommissionHoldback).where(
        SalesCommissionHoldback.id == holdback_id))).scalar_one()
    h.released_at = datetime.now(UTC)
    await db.flush()
    return h


async def run_due_payouts(db: AsyncSession, site_id, as_of: date, wh_rate=Decimal("0.033")) -> int:
    # ★[현장 격리·머니패스] 도래분 지급 스케줄은 '이 현장(site_id)' 것만 선택한다.
    #   schedule → split → event 경로로 event.site_id 를 조인해 본 현장 due 만 지급한다.
    #   (격리 없이 status/planned_at 만 필터하면 한 현장 운영자가 정산 실행 시 전 현장 due 가
    #    일괄 지급돼 교차현장 과처리·원천징수 오산이 발생한다 — 머니패스 격리 마감.)
    rows = list((await db.execute(
        select(SalesCommissionPayoutSchedule)
        .join(SalesCommissionSplit, SalesCommissionSplit.id == SalesCommissionPayoutSchedule.split_id)
        .join(SalesCommissionEvent, SalesCommissionEvent.id == SalesCommissionSplit.event_id)
        .where(
            SalesCommissionPayoutSchedule.status == "PLANNED",
            SalesCommissionPayoutSchedule.planned_at <= as_of,
            SalesCommissionEvent.site_id == site_id))).scalars())
    paid = 0  # 지급 건수 누적(silent-fail 아님 — 단순 카운터 초기값).
    if rows:
        # 지급 부가컬럼(tax_type/vat) 보장은 루프 진입 전 '한 번만'(매 건 ALTER race/직렬화 제거).
        await _ensure_payout_columns(db)
    for sch in rows:
        split = (await db.execute(select(SalesCommissionSplit).where(
            SalesCommissionSplit.id == sch.split_id))).scalar_one()
        gross = (Decimal(split.amount or 0) * Decimal(str(sch.ratio or 0))).quantize(Decimal("1"))
        hb = (await db.execute(select(SalesCommissionHoldback).where(
            SalesCommissionHoldback.split_id == sch.split_id,
            SalesCommissionHoldback.released_at.is_(None)))).scalars()
        gross -= sum(Decimal(h.amount or 0) for h in hb)
        if gross <= 0:
            sch.status = "PAID"
            continue
        # 수령자(노드) 세금유형 선택: WITHHOLDING(3.3% 원천) 또는 VAT(부가세 10% 가산).
        # ★[현장 격리] site_id 를 함께 넘겨 타 현장이 적재한 동일 node_id 의 세금유형을
        #   잘못 열람·적용하지 않게 한다(머니패스 격리 — 원천/부가세 오산 차단).
        from app.services.sales.commission.engine import get_node_tax_type
        tt = await get_node_tax_type(db, split.node_id, site_id=site_id)
        net = payout_net(gross, tt)
        po = SalesCommissionPayout(claim_id=None, gross=int(net["gross"]),
             withholding=int(net["withholding"]), net=int(net["net"]),
             paid_at=datetime.now(UTC), method="SCHEDULE")
        db.add(po)
        await db.flush()
        # tax_type/vat 는 모델 외 컬럼(정본=Alembic 033). 컬럼 보장은 루프 진입 전 1회 수행했으므로
        # 여기선 부가세 가산 지급액만 raw 갱신한다(매 건 ALTER 제거).
        await db.execute(text(
            "UPDATE sales_commission_payouts SET tax_type=:t, vat=:v WHERE id=:i"),
            {"t": net["tax_type"], "v": int(net["vat"]), "i": str(po.id)})
        sch.status = "PAID"
        sch.paid_payout_id = po.id
        paid += 1
    await db.flush()
    return paid
