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


class CrossSiteOwnershipError(ValueError):
    """교차현장 소유 위반 — 타 현장이 소유한 머니패스 행(세금유형 등)을 덮어쓰려 할 때 raise.

    ★응답계약 SSOT: 이 예외는 엔드포인트에서 409(Conflict)로 매핑한다(권한/리소스 충돌).
      과거엔 한국어 메시지 부분문자열('다른 현장' in str(e))로 409/400 을 분기했는데, 문구가
      바뀌면 상태코드가 흔들렸다. 전용 예외클래스로 분기를 코드화해 문구 변경에도 상태코드를
      불변으로 만든다. ValueError 를 상속하므로 기존 'except ValueError' 경로와도 하위호환된다.
    """

# 테이블/컬럼 미존재 PostgreSQL SQLSTATE(asyncpg). 이것만 '정상 0'(아직 안 만든 테이블)으로 본다.
# 42P01=undefined_table, 42703=undefined_column. 그 외 DB 오류는 은폐 금지(분류 로깅 후 전파).
_MISSING_OBJECT_SQLSTATES = frozenset({"42P01", "42703"})


def _missing_object_sqlstate(exc: BaseException) -> str | None:
    """예외가 '테이블/컬럼 미존재'(42P01/42703)면 해당 SQLSTATE, 아니면 None.

    asyncpg 의 원본 예외는 SQLAlchemy DBAPIError.orig 에 래핑된다. orig.sqlstate
    (또는 pgcode)로 분류한다. 이 두 코드만 '정상 0'(지급 전이라 아직 없는 테이블)으로 본다.
    (app/services/sales/admin/console.py 의 검증된 분류 패턴과 동일.)
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
    # TOTAL_POOL: 계약 1건당 발생액을 산출하지 않는다(풀 총액을 정산 시점에 배분하는 모델).
    #   따라서 여기서 0 을 돌려주면 split_commission 이 즉시 조기반환한다 — 이는 '계약당 자동 split
    #   미수행'이라는 정상 동작(정산 배치에서 별도 배분)이다. ★단, TOTAL_POOL 정산 배치 경로는
    #   아직 구현되지 않았다(deploy-pending) → 풀 과지급 가드(_assert_pool_not_exceeded)는 현재
    #   PER_CONTRACT/RATE_OF_PRICE 발생 경로에만 실효한다(아래 가드 docstring 참고).
    return Decimal(0)


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

    ★[발동 범위 — 정직 고지] 본 가드는 'new_total > 0 인 발생 경로'(split_commission)에서만 효력을
      낸다. 즉 master.basis 가 PER_CONTRACT_FIXED / RATE_OF_PRICE 라서 계약당 발생액(new_total)이
      산출될 때 호출돼 풀 초과를 차단한다. 반면 master.basis=TOTAL_POOL 은 resolve_total 이
      Decimal(0) 을 돌려줘 split_commission 이 _assert_pool_not_exceeded 호출 전(total<=0)에 조기
      반환하므로, '표준 풀 운용(TOTAL_POOL)'에서는 이 가드가 발동하지 않는다.
      → TOTAL_POOL 정산 배치(풀 총액을 정산 시점에 배분)는 아직 구현 전(deploy-pending)이다. 배치
        구현 시 그 산출 지점에서 본 가드를 호출해야 풀 과지급이 차단된다(현재는 미배선 경로 없음 =
        호출하지 못함이지, 0/빈값으로 은폐하는 silent-fail 은 아니다).
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

    [음수 gross 가드] 지급/공급가액(gross)은 음수가 될 수 없다(환수는 clawback 경로로 별도 처리).
      음수가 들어오면 잘못된 데이터이므로 0/빈값으로 흡수하지 않고 ValueError 로 즉시 거부한다
      (silent-fail 차단 — 음수 세액·역분개 산출 방지).
    """
    if gross < 0:
        raise ValueError(f"payout_net: gross(지급·공급가액)는 음수가 될 수 없습니다(받은 값 {gross}) — "
                         "환수는 clawback 경로로 처리하세요")
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


async def ensure_tax_pref(db=None) -> None:
    """sales_commission_tax_pref 멱등 보장(부팅 안전망) — 프로세스 1회만 실제 DDL 수행.

    정본은 Alembic 033. 여기서는 마이그레이션 미적용 환경 대비 CREATE TABLE IF NOT EXISTS 만
    수행한다(파괴적 변경 없음). 최초 1회 성공 후엔 즉시 반환(no-op)해 매 호출 DDL/commit 을 없앤다.
    동시 부팅(멀티프로세스) race 는 advisory-lock 으로, 코루틴 경합은 asyncio.Lock 으로 막는다.

    ★[부분커밋 차단] DDL+commit 을 '호출자 세션(db)'에서 수행하면, 같은 요청 안에서 호출자가 아직
      커밋하지 않은 쓰기(예: tax-pref 설정 → 곧이어 set_node_tax_type 의 INSERT)가 이 commit 에
      휩쓸려 조기 부분커밋된다. 그래서 DDL 은 항상 '별도의 단명 세션'(async_session_factory)에서
      수행한다(append_analysis 패턴). 호출자 트랜잭션 경계를 절대 건드리지 않는다.
      인자 db 는 하위호환 위해 받지만 사용하지 않는다(별도 세션으로 DDL 수행).
    """
    global _TAXPREF_READY
    if _TAXPREF_READY:  # 이미 보장됨 → DB 왕복 없이 즉시 반환.
        return
    async with _taxpref_lock:  # 동시 첫 호출(코루틴 경합)을 1회로 합류.
        if _TAXPREF_READY:
            return
        # ★별도 단명 세션 — 호출자 세션(db)의 미커밋 쓰기를 휩쓸지 않도록 DDL/commit 을 격리.
        from app.core.database import async_session_factory
        async with async_session_factory() as ddl_db:
            # advisory-lock: 트랜잭션 종료(commit/rollback) 시 자동 해제(pg_advisory_xact_lock).
            await ddl_db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_TAXPREF})
            await ddl_db.execute(text(_TAXPREF_DDL))
            await ddl_db.commit()
        _TAXPREF_READY = True  # 성공 시에만 게이트 닫음(실패 시 다음 호출이 재시도).


async def get_node_tax_type(db, node_id, site_id=None) -> str:
    """노드(수령자) 세금유형. 미설정 시 WITHHOLDING(3.3%).

    ★[현장 격리] site_id 가 주어지면 WHERE 에 site_id 를 함께 걸어, 타 현장이 적재한 노드 행을
      잘못 읽지 않게 한다(PK 는 node_id 단일이지만 방어적 격리). site_id 미지정(내부 폴백 호출)은
      기존 동작(노드 단일 조회) 유지 — 하위호환.
    """
    if node_id is None:
        return "WITHHOLDING"
    await ensure_tax_pref(db)
    if site_id is not None:
        r = (await db.execute(text(
            "SELECT tax_type FROM sales_commission_tax_pref WHERE node_id=:n AND site_id=:s"),
            {"n": str(node_id), "s": str(site_id)})).first()
    else:
        r = (await db.execute(text(
            "SELECT tax_type FROM sales_commission_tax_pref WHERE node_id=:n"),
            {"n": str(node_id)})).first()
    return (r[0] if r else "WITHHOLDING") or "WITHHOLDING"


async def set_node_tax_type(db, site_id, node_id, tax_type: str) -> str:
    """노드(수령자) 세금유형 설정.

    ★[현장 격리] 동일 node_id 에 다른 현장 행이 이미 있으면(타 현장 소유) 덮어쓰기를 거부한다.
      PK 가 node_id 단일이라 ON CONFLICT 만으로는 타 현장 행도 무단 덮어쓸 수 있으므로, 먼저
      기존 행의 site_id 를 확인해 '내 현장 소유' 일 때만 갱신/삽입한다(타 현장 데이터 무단변경 차단).

    ★[TOCTOU 차단] 위 선검사(SELECT)와 INSERT 사이에 다른 트랜잭션이 행을 바꿀 수 있는 경합을
      막기 위해, ON CONFLICT DO UPDATE 에도 'WHERE …site_id=:s' 조건을 건다. 충돌 시점에 기존
      행이 타 현장 소유면 UPDATE 가 적용되지 않으므로(영향 행 0), 선검사를 통과한 뒤 경합으로
      타 현장 행이 끼어들어도 무단 덮어쓰기가 원천 차단된다(SELECT 선검사에만 의존하지 않음).

    ★[silent no-op 차단] 위 ON CONFLICT…WHERE site_id 가드가 경합으로 막히면(타 현장 행이
      끼어든 경우) Postgres 는 '0행 갱신·무예외'로 조용히 끝낸다. 이때 함수가 그대로 tt 를
      반환하면 엔드포인트가 {ok:True} 로 응답해 '차단된 머니패스 write 를 성공으로 위장'한다
      (silent no-op). 그래서 result.rowcount 를 확인해, 0행이면(=실제 갱신/삽입 안 됨)
      CrossSiteOwnershipError 로 명시 거부한다(409 매핑). 성공을 위장하지 않는다.
    """
    tt = (tax_type or "").upper()
    if tt not in ("WITHHOLDING", "VAT"):
        raise ValueError("tax_type은 WITHHOLDING 또는 VAT")
    await ensure_tax_pref(db)
    # 기존 행 소유 현장 확인 — 타 현장 소유면 거부(node_id 단일 PK 의 교차현장 덮어쓰기 차단).
    owner = (await db.execute(text(
        "SELECT site_id FROM sales_commission_tax_pref WHERE node_id=:n"),
        {"n": str(node_id)})).first()
    if owner is not None and str(owner[0]) != str(site_id):
        raise CrossSiteOwnershipError("이 노드의 세금유형은 다른 현장 소유입니다 — 변경할 수 없습니다")
    # ON CONFLICT DO UPDATE 에 site_id 가드 — 경합(TOCTOU)으로 타 현장 행이 끼어들어도
    # 그 행은 UPDATE 대상에서 제외(WHERE 불일치)되어 무단 덮어쓰기가 차단된다.
    result = await db.execute(text(
        "INSERT INTO sales_commission_tax_pref (site_id, node_id, tax_type, updated_at) "
        "VALUES (:s,:n,:t, now()) ON CONFLICT (node_id) DO UPDATE SET "
        "site_id=:s, tax_type=:t, updated_at=now() "
        "WHERE sales_commission_tax_pref.site_id=:s"),
        {"s": str(site_id), "n": str(node_id), "t": tt})
    # ★rowcount==0 = 경합으로 갱신/삽입이 차단됨(타 현장 행 선점). 성공 위장 금지 → 명시 거부.
    #   (rowcount 가 -1/None 인 일부 드라이버는 '미지원'이므로 0 일 때만 거부 — 정상 경로 오탐 방지.)
    if getattr(result, "rowcount", -1) == 0:
        raise CrossSiteOwnershipError(
            "이 노드의 세금유형은 다른 현장 소유입니다 — 변경할 수 없습니다(경합 차단)")
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
        # ★[현장 격리·대칭] earned 집계는 e.site_id=:s 로 격리하는데 paid 집계는 s.node_id 만
        #   걸려 비대칭이었다(타 현장에서 같은 node_id 로 지급된 행이 있으면 paid 에 새어 들어와
        #   미지급 잔액을 과소 산정 → 정산 오판). event(e)까지 조인해 e.site_id=:s 격리를 더해
        #   earned 와 동일 기준으로 맞춘다(머니패스 격리 대칭 복원).
        #
        # ★[지급 2소스 합산 — 구조적 누락 해소(iter-5 HIGH)] 지급(payout)은 두 경로로 생긴다.
        #   ① claim 승인 경로: payout.claim_id 가 채워져 claim→split→event 로 잇는다(아래 첫 SELECT).
        #   ② 마일스톤 스케줄 경로(run_due_payouts): payout.claim_id=NULL, method='SCHEDULE' 로
        #      생성되고, sales_commission_payout_schedule.paid_payout_id 가 그 payout 을 가리킨다
        #      (schedule→split→event 로 site/node 를 잇는다, 아래 UNION ALL 둘째 SELECT).
        #   기존 paid 집계는 'JOIN claims c ON c.id=p.claim_id' INNER JOIN 체인이라 claim_id=NULL 인
        #   스케줄 지급분이 전량 누락됐다 → 이미 지급한 돈이 미지급(outstanding)으로 과대 표시되어
        #   해촉/정산 명세의 핵심숫자(미지급 잔액)를 오판했다. 두 소스를 UNION ALL 로 합산해
        #   '실제 지급된 모든 현금(공급가액 기준)'을 paid 로 집계한다.
        #   - 중복합산 차단: ① 경로는 claim_id 가 채워진 payout 만, ② 경로는 claim_id IS NULL 인
        #     payout 만 집계하므로 같은 payout 이 두 소스에 동시에 잡히지 않는다(상호배타).
        #   - 두 소스 모두 s.node_id=:n + e.site_id=:s 로 earned 와 동일한 현장·노드 격리를 건다
        #     (집계규약 통일: earned/paid 모두 'SPLIT 이벤트의 node 귀속 + 현장 격리').
        paid = int((await db.execute(text(
            "SELECT COALESCE(SUM(g),0) FROM ("
            "  SELECT p.gross AS g FROM sales_commission_payouts p "
            "  JOIN sales_commission_claims c ON c.id=p.claim_id "
            "  JOIN sales_commission_splits s ON s.id=c.split_id "
            "  JOIN sales_commission_events e ON e.id=s.event_id "
            "  WHERE s.node_id=:n AND e.site_id=:s "
            "  UNION ALL "
            "  SELECT p.gross AS g FROM sales_commission_payouts p "
            "  JOIN sales_commission_payout_schedule sch ON sch.paid_payout_id=p.id "
            "  JOIN sales_commission_splits s ON s.id=sch.split_id "
            "  JOIN sales_commission_events e ON e.id=s.event_id "
            "  WHERE s.node_id=:n AND e.site_id=:s AND p.claim_id IS NULL"
            ") u"),
            {"n": str(node_id), "s": str(site_id)})).scalar() or 0)
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
    # ★[clawback 후 과지급 클램프 — 의도동작 명시(iter-6 관찰)] earned 는 e.status='SPLIT' 만 합산하므로
    #   환수(clawback)된 이벤트는 earned 에서 빠진다. 그런데 paid 는 그 이벤트에 이미 지급된 payout 을
    #   계속 포함한다(REVERSED 미반영). 따라서 환수 후엔 earned < paid 가 될 수 있고, outstanding 은
    #   max(0,..) 로 0 에 클램프된다 — 즉 '미지급 잔액'은 0 으로만 표시되고 '과지급(환수대상)'은 이 숫자에
    #   드러나지 않는다. 이는 의도된 동작이다: 이 명세의 outstanding 은 '아직 줘야 할 돈(≥0)'을 뜻하며,
    #   과지급 회수는 별도 환수 원장(clawback/REVERSED)이 담당한다(여기서 음수로 섞으면 미지급과 환수를
    #   혼동). 회귀테스트(test_outstanding_clamped_to_zero_after_overpay)로 이 클램프를 고정한다.
    outstanding = max(0, earned - paid)
    # ★[과지급 가시화(iter-7 completeness)] outstanding 은 max(0,..) 로 클램프돼 '아직 줘야 할 돈(≥0)'만
    #   표시하므로, earned<paid(환수 후 등) 상황의 '과지급(환수대상)'이 이 화면에서 보이지 않았다.
    #   의도분리(미지급≥0 / 환수는 별도 원장)는 유지하되, 운영자가 이 정산명세 화면만으로 과지급을 인지
    #   하도록 overpaid 신호를 함께 노출한다. overpaid = max(0, paid-earned)(0 이면 과지급 없음).
    #   clawback_total = '환수(REVERSED)된 이벤트의 배분 합'(별도 환수 원장 합계) — 과지급의 근거숫자.
    #   둘 다 '신호 노출'일 뿐 outstanding/settlement(미지급 분개)에는 섞지 않는다(혼동 차단).
    overpaid = max(0, paid - earned)
    try:
        clawback_total = int((await db.execute(text(
            "SELECT COALESCE(SUM(s.amount),0) FROM sales_commission_splits s "
            "JOIN sales_commission_events e ON e.id=s.event_id "
            "WHERE e.site_id=:s AND s.node_id=:n AND e.status='REVERSED'"),
            {"s": str(site_id), "n": str(node_id)})).scalar() or 0)
    except DBAPIError as e:
        # 환수합 집계도 동일 분류 — 미존재(아직 환수 도메인 미생성)만 0(정상), 실오류는 전파(은폐 금지).
        with contextlib.suppress(Exception):
            await db.rollback()
        code = _missing_object_sqlstate(e)
        if code is not None:
            logger.debug("settle_summary 환수합 미존재객체(%s) → clawback_total=0(node=%s)", code, str(node_id))
            clawback_total = 0
        else:
            logger.error("settle_summary 환수합 DB오류(전파): node=%s err=%s", str(node_id), str(e)[:200])
            raise
    tax_type = await get_node_tax_type(db, node_id, site_id=site_id)  # 현장 격리 조회
    net = payout_net(Decimal(outstanding), tax_type)
    return {
        "node_id": str(node_id), "tax_type": tax_type, "contracts": contracts,
        "earned_gross": earned, "paid_gross": paid, "outstanding_gross": outstanding,
        # 과지급 신호(운영자 인지용) — outstanding/settlement 와 분리(환수 회수는 별도 원장).
        "overpaid_gross": overpaid, "clawback_total": clawback_total,
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
