"""수수료 분할지급/유보 — 마일스톤 스케줄(합계≤1) + 유보 차감 + 도래분 지급(원천징수). 취소시 환수 연계."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.commission.engine import DEFAULT_WITHHOLDING_RATE, payout_net
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
            # ★[테이블 부재 가드] ALTER TABLE ADD COLUMN IF NOT EXISTS 는 '컬럼' 부재만 무시할 뿐,
            #   '테이블' 자체가 없으면(클린 DB·정본 033 미적용) 42P01(undefined_table)로 실패한다.
            #   그래서 to_regclass 로 테이블 존재를 먼저 확인하고, 없으면 ALTER 를 건너뛴다(정본은
            #   Alembic 033 의 create_table). 테이블 부재는 '아직 지급 도메인 미생성'이라 정상 0 상황
            #   이므로 게이트만 닫아(다음 호출 재시도 없이) 조용히 통과한다 — silent-fail 아님(실오류는
            #   여전히 전파). 호출부(run_due_payouts)는 rows 가 있을 때만 이 함수를 부르므로, 테이블이
            #   정말 없으면 그 SELECT 조인(events)도 정상 0건이라 부가컬럼 UPDATE 경로에 도달하지 않는다.
            exists = (await ddl_db.execute(text(
                "SELECT to_regclass('public.sales_commission_payouts')"))).scalar()
            if exists is not None:
                await ddl_db.execute(text(
                    "ALTER TABLE sales_commission_payouts ADD COLUMN IF NOT EXISTS "
                    "tax_type varchar(16) DEFAULT 'WITHHOLDING'"))
                await ddl_db.execute(text(
                    "ALTER TABLE sales_commission_payouts ADD COLUMN IF NOT EXISTS "
                    "vat numeric(16,0) DEFAULT 0"))
            await ddl_db.commit()
        _PAYOUT_COLS_READY = True


def total_paid_of(gross, vat=0) -> int:
    """실지급 현금(총지급액) = 공급가액(gross) + 부가세(vat). 집계 규약(문서/테스트 전용 헬퍼).

    ★[SSOT 과대표현 정정(iter-6)] 이 헬퍼는 'Python 값(gross, vat)'을 받아 합산한다. 그러나 실제
      현금흐름·정산·증명서 집계는 모두 SQL 집계(COALESCE(SUM(p.gross),0)+COALESCE(SUM(p.vat),0)
      형태)로 DB 안에서 이뤄지므로 이 Python 헬퍼를 호출하지 못한다(현재 production 호출처 0건).
      따라서 이 함수는 '집계 규약을 코드로 문서화'하고 단위테스트로 그 규약(gross+vat·음수가드·
      Decimal 정규화)을 고정하는 용도다 — '집계의 SSOT(단일 진실 원천)'가 아니다. 아래 음수가드
      (ValueError)는 이 헬퍼를 직접 부르는 코드만 보호하며, SQL 집계 경로의 음수 데이터는 막지
      못한다(그 보호는 payout_net 의 입력 가드가 담당). SQL 집계와 본 헬퍼는 'gross+vat' 라는
      동일 규약을 공유하되, 실 집계는 SQL 쪽이 정본임을 명시한다.

    ★[정합·집계 규약 명시] sales_commission_payouts 는 'gross'(공급가액=원천징수 전 보수)와
      'vat'(부가세 가산분)을 분리 저장한다. net 컬럼은 'gross 기준 실수령'(WITHHOLDING 은
      gross−원천, VAT 는 gross)이라, VAT 수령자의 '실제로 빠져나간 현금'(total_paid=gross+vat)을
      담지 않는다. 따라서 하류에서 'net/gross 만' 합산하면 VAT 수령자의 부가세가 과소집계된다.

      → '총지급 현금'을 합산해야 하는 회계/현금흐름 집계는 컬럼을 직접 더하지 말고 본 헬퍼로
        (gross + vat)를 산출한다(payout_net 의 total_paid 와 동일 규약). WITHHOLDING 은 vat=0
        이라 gross 와 같다. 이로써 '집계 규약'을 코드 한 곳에 고정해 과소집계 회귀를 막는다.
      (settle_summary 의 paid_gross 는 '공급가액 기준' 잔액계산용이라 의도적으로 gross 만 쓴다 —
       그 컬럼의 의미는 '공급가액'이며 본 헬퍼는 '총지급 현금'으로 의미가 다름을 명확히 한다.)

    [입력 정규화·가드(iter-5)]
      - float 등 비정밀 입력은 Decimal(str(x)) 로 정규화해 부동소수 오차를 배제한다
        (payout_net 의 Decimal 규약과 정합).
      - 음수 vat 는 잘못된 데이터다(환수·차감은 별도 경로). payout_net 의 음수 gross 거부와 대칭으로
        ValueError 로 즉시 거부한다 — 0/빈값으로 흡수하면 현금유출이 과소집계되는 silent-fail 이 된다.
        (gross 는 settle/현금흐름 합산에서 자연스레 0 이상이 정상이나, 음수 gross 도 동일 사유로 거부.)
    """
    g = Decimal(str(gross)) if gross is not None else Decimal(0)
    v = Decimal(str(vat)) if vat is not None else Decimal(0)
    if g < 0:
        raise ValueError(f"total_paid_of: gross(공급가액)는 음수가 될 수 없습니다(받은 값 {gross})")
    if v < 0:
        raise ValueError(f"total_paid_of: vat(부가세)는 음수가 될 수 없습니다(받은 값 {vat})")
    return int(g + v)


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


async def run_due_payouts(db: AsyncSession, site_id, as_of: date, wh_rate=DEFAULT_WITHHOLDING_RATE) -> int:
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
        # ★집계 규약: '실지급 현금'(VAT 포함) 은 gross+vat = total_paid_of(gross, vat). 하류 현금흐름
        #   집계는 컬럼 직접합산 대신 total_paid_of 를 써야 VAT 수령자 부가세 과소집계가 안 난다.
        await db.execute(text(
            "UPDATE sales_commission_payouts SET tax_type=:t, vat=:v WHERE id=:i"),
            {"t": net["tax_type"], "v": int(net["vat"]), "i": str(po.id)})
        sch.status = "PAID"
        sch.paid_payout_id = po.id
        paid += 1
    await db.flush()
    return paid
