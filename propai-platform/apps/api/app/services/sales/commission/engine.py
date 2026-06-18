"""수수료 2단 엔진 — 시행사 총액 → 대행사 배분(조직 path cascade) → 잔여 대행사 귀속,
SUM(배분) ≤ 총액 보장. 지급 원천징수(3.3%). 계약취소 시 역추적 환수(clawback).
"""

import asyncio
import contextlib
import logging
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.org.service import ancestors_path
from apps.api.database.models.sales.commission_mh_harness import (
    SalesCommissionClawback,
    SalesCommissionDistribution,
    SalesCommissionEvent,
    SalesCommissionMaster,
    SalesCommissionSplit,
)

logger = logging.getLogger(__name__)

Q = Decimal("1")

# 테이블/컬럼 미존재 PostgreSQL SQLSTATE(asyncpg). 이것만 '정상 0'(아직 안 만든 테이블)으로 본다.
# 42P01=undefined_table, 42703=undefined_column. 그 외 DB 오류는 은폐 금지(분류 로깅 후 전파).
_MISSING_OBJECT_SQLSTATES = frozenset({"42P01", "42703"})


def _missing_object_sqlstate(exc: BaseException) -> str | None:
    """예외가 '테이블/컬럼 미존재'(42P01/42703)면 해당 SQLSTATE, 아니면 None.

    asyncpg 의 원본 예외는 SQLAlchemy DBAPIError.orig 에 래핑된다. orig.sqlstate
    (또는 pgcode)로 분류한다. 이 두 코드만 '정상 0'(지급 전이라 아직 없는 테이블)으로 본다.
    (admin/console.py 의 검증된 분류 패턴과 동일.)
    """
    orig = getattr(exc, "orig", None) or exc
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code in _MISSING_OBJECT_SQLSTATES:
        return code
    return None


async def _active_master(db, site_id) -> SalesCommissionMaster | None:
    return (await db.execute(select(SalesCommissionMaster).where(
        SalesCommissionMaster.site_id == site_id)
        .order_by(SalesCommissionMaster.effective_at.desc()).limit(1))).scalar_one_or_none()


async def resolve_total(db, site_id, contract) -> Decimal:
    m = await _active_master(db, site_id)
    if not m:
        return Decimal(0)
    if m.basis == "PER_CONTRACT_FIXED":
        return Decimal(m.fixed_amount or 0)
    if m.basis == "RATE_OF_PRICE":
        return (Decimal(getattr(contract, "total_price", 0) or 0) * Decimal(str(m.rate or 0))).quantize(Q)
    return Decimal(0)  # TOTAL_POOL: 정산 배치


async def _rules(db, site_id, master_id):
    rows = list((await db.execute(select(SalesCommissionDistribution).where(
        SalesCommissionDistribution.site_id == site_id,
        SalesCommissionDistribution.master_id == master_id))).scalars())
    by_node = {r.target_node_id: r for r in rows if r.target_node_id}
    by_type = {r.target_node_type: r for r in rows if r.target_node_type and not r.target_node_id}
    return by_node, by_type


def _amount(rule, total: Decimal) -> Decimal:
    if not rule:
        return Decimal(0)
    if rule.basis == "FIXED":
        return Decimal(str(rule.value or 0))
    return (total * Decimal(str(rule.value or 0))).quantize(Q)


async def _assert_pool_not_exceeded(db: AsyncSession, master, site_id, new_total: Decimal) -> None:
    """[동시성] 정산 풀(pool_total)이 설정돼 있으면, 이번 신규 발생액을 더한 누적 발생액이
    풀 총액을 초과하지 않도록 전역 제약한다(분쟁·과지급 차단).

    - master 행을 SELECT … FOR UPDATE 로 잠가 동시 split 들을 직렬화(같은 master 기준 race 제거).
      락 보유 중 기존 미환수(SPLIT/PENDING) 이벤트의 base_amount 합을 읽고, 신규분을 더해 검사한다.
      커밋/롤백 시 락 자동 해제.
    - pool_total 이 없으면(RATE/FIXED 단가 모델) 풀 상한 개념이 없으므로 검사하지 않는다.
    """
    pool_total = getattr(master, "pool_total", None)
    if pool_total is None:
        return
    pool = Decimal(pool_total or 0)
    if pool <= 0:
        return
    # master 행 잠금 — 동시 split 직렬화(트랜잭션 종료 시 자동 해제).
    await db.execute(text(
        "SELECT id FROM sales_commission_master WHERE id=:m FOR UPDATE"), {"m": str(master.id)})
    used = Decimal(int((await db.execute(text(
        "SELECT COALESCE(SUM(base_amount),0) FROM sales_commission_events "
        "WHERE site_id=:s AND status IN ('SPLIT','PENDING')"),
        {"s": str(site_id)})).scalar() or 0))
    if used + new_total > pool:
        # 풀 초과는 은폐 금지 — 명시적 거부(과지급 방지). 남은 풀 잔액을 메시지에 포함.
        raise ValueError(
            f"정산 풀(총 {int(pool)}원) 초과 — 누적 발생 {int(used)}원 + 신규 {int(new_total)}원 "
            f"> 풀 총액. 남은 풀 {int(pool - used)}원.")


async def split_commission(db: AsyncSession, site_id, contract):
    total = await resolve_total(db, site_id, contract)
    if total <= 0:
        return None
    m = await _active_master(db, site_id)
    # [동시성] 풀(pool_total) 설정 시: 누적 발생액 + 신규분이 풀 총액을 넘지 못하게 전역 제약.
    await _assert_pool_not_exceeded(db, m, site_id, total)
    ev = SalesCommissionEvent(site_id=site_id, contract_ext_id=contract.id, base_amount=total, status="PENDING")
    db.add(ev)
    await db.flush()
    chain = await ancestors_path(db, contract.member_node_id)  # [대행사 … 팀원]
    if not chain:
        ev.status = "SPLIT"
        await db.flush()
        return ev
    agency = chain[0]
    by_node, by_type = await _rules(db, site_id, m.id)
    allocated = Decimal(0)
    for node in chain[1:]:
        rule = by_node.get(node.id) or by_type.get(node.node_type)
        amt = _amount(rule, total)
        if amt > 0:
            db.add(SalesCommissionSplit(event_id=ev.id, node_id=node.id, node_type=node.node_type,
                   basis=rule.basis, rate=(rule.value if rule.basis == "RATE" else None), amount=amt))
            allocated += amt
    residual = total - allocated
    if residual < 0:
        raise ValueError("배분 합계가 시행사 총액을 초과")  # 무결성: SUM(배분) ≤ 총액
    db.add(SalesCommissionSplit(event_id=ev.id, node_id=agency.id, node_type=agency.node_type,
           basis="RESIDUAL", amount=residual))  # 대행사 귀속(잔여)
    ev.status = "SPLIT"
    await db.flush()
    return ev


def payout_net(gross: Decimal, tax_type: str = "WITHHOLDING",
               wh_rate: Decimal = Decimal("0.033"), vat_rate: Decimal = Decimal("0.10")) -> dict:
    """수령자 세금유형별 지급 분개.

    - WITHHOLDING(개인 사업소득, 3.3% 원천징수): 지급액에서 원천징수 후 실수령 = gross - 원천.
      세금계산서 없음. (프리랜서/팀원 기본)
    - VAT(사업자 세금계산서, 부가세 10%): 공급가액=gross 에 부가세 10% 가산해 지급(total_paid),
      사업자 실수령 공급가액 = gross(부가세는 별도 신고). 원천징수 없음.
    반환 키는 하위호환(gross/withholding/net) 유지 + tax_type/vat/total_paid 추가.

    [세율 출처]
      - 사업소득 원천징수 3.3% = 소득세 3%(소득세법 §129①(3)) + 지방소득세 0.3%(소득세의 10%,
        지방세법 §103의13). 인적용역 사업소득 일반세율(2026년 기준 변동 없음).
      - 부가가치세 10%(부가가치세법 §30, 일반세율).
    [반올림] 원천징수세액·부가세는 '원 미만 절사'(ROUND_DOWN)로 계산한다 — 국세청 원천징수 실무
      관행(원 단위 미만 버림)과 정합. 기존 quantize 기본값(ROUND_HALF_EVEN, 반올림)은 사사오입으로
      최대 1원 과대징수가 날 수 있어 절사로 교정한다(수령자에게 유리·과대원천 방지).
    [면책] 본 산식은 일반세율 기준 표준 분개이며, 감면·세액공제·누진·외국인·기타소득 전환 등
      개별 특례는 반영하지 않는다(세무 신고는 어댑터+승인 경로에서 별도 확정).
    """
    if (tax_type or "").upper() == "VAT":
        vat = (gross * vat_rate).quantize(Q, rounding=ROUND_DOWN)  # 부가세 원 미만 절사
        return {"tax_type": "VAT", "gross": gross, "withholding": Decimal(0), "vat": vat,
                "total_paid": gross + vat, "net": gross}
    wh = (gross * wh_rate).quantize(Q, rounding=ROUND_DOWN)   # 사업소득 원천징수 3.3%, 원 미만 절사
    return {"tax_type": "WITHHOLDING", "gross": gross, "withholding": wh, "vat": Decimal(0),
            "total_paid": gross, "net": gross - wh}


# 수령자(조직노드)별 세금유형 선호 — 멱등 테이블(WITHHOLDING 기본).
# ★정본은 Alembic 033_sales_commission_tax_pref. 아래 런타임 DDL 은 마이그레이션 미적용
#   환경(개발/신규배포)에서만 '부팅 안전망'으로 동작하며, 동시 부팅 시 advisory-lock 으로
#   중복 DDL race 를 제거하고 프로세스당 최초 1회만 실제 DDL 을 수행한다(매 요청 DDL 제거).
_TAXPREF_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_commission_tax_pref ("
    "  site_id uuid NOT NULL,"
    "  node_id uuid NOT NULL,"
    "  tax_type varchar(16) NOT NULL DEFAULT 'WITHHOLDING',"
    "  updated_at timestamptz NOT NULL DEFAULT now(),"
    "  PRIMARY KEY (node_id)"
    ")"
)
# 런타임 DDL race 제거용 advisory-lock 키(임의 고유 상수, 충돌 회피). 트랜잭션 종료 시 자동 해제.
_LOCK_TAXPREF = 880421101
# 프로세스 1회 게이트(읽기경로 매 요청 DDL/commit 직렬화 제거). asyncio.Lock 으로 동시 첫 호출 합류.
_TAXPREF_READY = False
_taxpref_lock = asyncio.Lock()


async def ensure_tax_pref(db) -> None:
    """sales_commission_tax_pref 멱등 보장(부팅 안전망) — 프로세스 1회만 실제 DDL 수행.

    정본은 Alembic 033. 여기서는 마이그레이션 미적용 환경 대비 CREATE TABLE IF NOT EXISTS 만
    수행한다(파괴적 변경 없음). 최초 1회 성공 후엔 즉시 반환(no-op)해 매 호출 DDL/commit 을 없앤다.
    동시 부팅(멀티프로세스) race 는 advisory-lock 으로, 코루틴 경합은 asyncio.Lock 으로 막는다.
    """
    global _TAXPREF_READY
    if _TAXPREF_READY:  # 이미 보장됨 → DB 왕복 없이 즉시 반환.
        return
    async with _taxpref_lock:  # 동시 첫 호출(코루틴 경합)을 1회로 합류.
        if _TAXPREF_READY:
            return
        # advisory-lock: 트랜잭션 종료(commit/rollback) 시 자동 해제(pg_advisory_xact_lock).
        await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_TAXPREF})
        await db.execute(text(_TAXPREF_DDL))
        await db.commit()
        _TAXPREF_READY = True  # 성공 시에만 게이트 닫음(실패 시 다음 호출이 재시도).


async def get_node_tax_type(db, node_id) -> str:
    """노드(수령자) 세금유형. 미설정 시 WITHHOLDING(3.3%)."""
    if node_id is None:
        return "WITHHOLDING"
    await ensure_tax_pref(db)
    r = (await db.execute(text("SELECT tax_type FROM sales_commission_tax_pref WHERE node_id=:n"),
                          {"n": str(node_id)})).first()
    return (r[0] if r else "WITHHOLDING") or "WITHHOLDING"


async def set_node_tax_type(db, site_id, node_id, tax_type: str) -> str:
    tt = (tax_type or "").upper()
    if tt not in ("WITHHOLDING", "VAT"):
        raise ValueError("tax_type은 WITHHOLDING 또는 VAT")
    await ensure_tax_pref(db)
    await db.execute(text(
        "INSERT INTO sales_commission_tax_pref (site_id, node_id, tax_type, updated_at) "
        "VALUES (:s,:n,:t, now()) ON CONFLICT (node_id) DO UPDATE SET tax_type=:t, updated_at=now()"),
        {"s": str(site_id), "n": str(node_id), "t": tt})
    return tt


async def settle_summary(db: AsyncSession, site_id, node_id) -> dict:
    """노드(영업사원) 수수료 정산 명세 — 해촉/정산용.

    기발생(미환수 SPLIT 이벤트의 배분 합) − 기지급(payout gross) = 미지급 잔액. 노드 세금유형으로
    원천징수(3.3%)/부가세(10%) 분개. 환수(clawback→event.status='REVERSED')된 이벤트는
    기발생에서 자동 제외된다(status='SPLIT' 만 합산). 지급(payout)은 기록만으로 자금이체 미수행."""
    earned = int((await db.execute(text(
        "SELECT COALESCE(SUM(s.amount),0) FROM sales_commission_splits s "
        "JOIN sales_commission_events e ON e.id=s.event_id "
        "WHERE e.site_id=:s AND s.node_id=:n AND e.status='SPLIT'"),
        {"s": str(site_id), "n": str(node_id)})).scalar() or 0)
    contracts = int((await db.execute(text(
        "SELECT COUNT(DISTINCT e.contract_ext_id) FROM sales_commission_splits s "
        "JOIN sales_commission_events e ON e.id=s.event_id "
        "WHERE e.site_id=:s AND s.node_id=:n AND e.status='SPLIT'"),
        {"s": str(site_id), "n": str(node_id)})).scalar() or 0)
    try:
        paid = int((await db.execute(text(
            "SELECT COALESCE(SUM(p.gross),0) FROM sales_commission_payouts p "
            "JOIN sales_commission_claims c ON c.id=p.claim_id "
            "JOIN sales_commission_splits s ON s.id=c.split_id "
            "WHERE s.node_id=:n"), {"n": str(node_id)})).scalar() or 0)
    except DBAPIError as e:
        # 트랜잭션 오염 방지 롤백(미존재/전파 공통). 롤백 자체 실패는 무시.
        with contextlib.suppress(Exception):
            await db.rollback()
        code = _missing_object_sqlstate(e)
        if code is not None:
            # ★정상 0 만 허용: 지급 테이블/컬럼 미생성(아직 지급 1건도 없는 현장)일 때만 0 폴백.
            logger.debug("settle_summary 지급집계 미존재객체(%s) → paid=0 폴백(node=%s)", code, str(node_id))
            paid = 0
        else:
            # ★silent-fail 차단: 권한·연결·문법 등 실오류를 '미지급(0)'으로 은폐하면 정산액 오판.
            #   분류 로깅 후 호출자에게 전파한다(0 으로 흡수 금지).
            logger.error("settle_summary 지급집계 DB오류(전파): node=%s err=%s", str(node_id), str(e)[:200])
            raise
    outstanding = max(0, earned - paid)
    tax_type = await get_node_tax_type(db, node_id)
    net = payout_net(Decimal(outstanding), tax_type)
    return {
        "node_id": str(node_id), "tax_type": tax_type, "contracts": contracts,
        "earned_gross": earned, "paid_gross": paid, "outstanding_gross": outstanding,
        "settlement": {k: (int(v) if isinstance(v, Decimal) else v) for k, v in net.items()},
    }


async def clawback(db: AsyncSession, event_id, reason: str):
    splits = list((await db.execute(select(SalesCommissionSplit).where(
        SalesCommissionSplit.event_id == event_id))).scalars())
    total_rev = sum((s.amount or 0) for s in splits)
    db.add(SalesCommissionClawback(event_id=event_id, reason=reason, reversed_amount=total_rev))
    ev = (await db.execute(select(SalesCommissionEvent).where(
        SalesCommissionEvent.id == event_id))).scalar_one()
    ev.status = "REVERSED"
    await db.flush()
