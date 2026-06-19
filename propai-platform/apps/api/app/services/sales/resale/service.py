"""실거래신고/전매제한 — 신고기한(파라미터) 산정, 전매제한 검사로 명의변경 차단/허용. 기록만.

전매(양도) 상태머신은 SalesResaleTransfer 의 (allowed, decided_at) 두 컬럼으로 표현한다.
  - 요청(PENDING)   : decided_at IS NULL  (allowed 에는 '제한기간 검사 결과' 예비값이 들어감)
  - 승인/반려(DECIDED): decided_at IS NOT NULL  (allowed=True 승인 / False 반려)
머니패스(명의변경)이므로 ①현장(site_id) 격리 ②중복요청·중복결정 멱등(이중 명의변경 차단)을
핵심으로 봉합한다.

★[멱등의 두 겹 — TOCTOU 봉합] 앱레벨 'SELECT-then-INSERT' 만으로는 동시 두 요청이 모두
'PENDING 없음'을 읽고 둘 다 INSERT 해 중복 PENDING 행이 생긴다(read-then-write 경합). 그래서:
  ① DB 정본: 부분 유니크 인덱스(Alembic 040) — 어떤 동시성에서도 중복 PENDING 을 23505 로 거부.
     · sales_resale_transfers  UNIQUE(site_id, contract_ext_id) WHERE decided_at IS NULL
     · sales_realtx_reports    UNIQUE(site_id, contract_ext_id) WHERE status = 'PENDING'
  ② 앱 graceful: INSERT 를 SAVEPOINT(begin_nested)+flush 로 감싸 23505(IntegrityError)를 잡아
     기존 PENDING 행을 재조회·반환한다(미가공 500 금지). 이 둘로 docstring 의 '구조적 차단'이
     실제 구현(부분 유니크 + 캐치)과 일치한다.
"""

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.contract_crm_ad import SalesContractExt
from apps.api.database.models.sales.resale import (
    SalesRealtxReport,
    SalesResaleRestriction,
    SalesResaleTransfer,
)
from apps.api.database.models.sales.site_org import SalesSiteConfig

logger = logging.getLogger(__name__)


async def _load_contract_scoped(db: AsyncSession, site_id, contract_id) -> SalesContractExt:
    """계약을 현장(site_id) 스코프로 로드. 타현장 계약 id 를 넘겨도 조회 안 됨(교차테넌트 차단)."""
    c = (await db.execute(select(SalesContractExt).where(
        SalesContractExt.id == contract_id,
        SalesContractExt.site_id == site_id,
    ))).scalar_one_or_none()
    if c is None:
        # 미존재/타현장은 동일하게 '찾을 수 없음' — 타현장 계약 존재 누설 금지.
        raise ValueError("계약을 찾을 수 없습니다(현장 내 계약만 처리 가능)")
    return c


async def _find_pending_report(db: AsyncSession, site_id, contract_id):
    """같은 계약의 미제출(PENDING) 실거래신고를 1건 조회(없으면 None)."""
    return (await db.execute(select(SalesRealtxReport).where(
        SalesRealtxReport.site_id == site_id,
        SalesRealtxReport.contract_ext_id == contract_id,
        SalesRealtxReport.status == "PENDING",
    ))).scalars().first()


async def create_realtx_report(db: AsyncSession, site_id, contract_id):
    # ★[격리] 계약을 site_id 스코프로 로드 — 타현장 계약으로 실거래신고를 생성하지 못하게 막는다.
    c = await _load_contract_scoped(db, site_id, contract_id)
    # ★[멱등] 같은 계약의 미제출(PENDING) 신고가 이미 있으면 중복 생성하지 않고 기존 건을 반환한다
    #   (재호출마다 PENDING 신고가 쌓여 신고기한이 흐려지는 silent 중복 차단).
    existing = await _find_pending_report(db, site_id, contract_id)
    if existing is not None:
        return existing
    cfg = (await db.execute(select(SalesSiteConfig).where(SalesSiteConfig.site_id == site_id))).scalar_one_or_none()
    report_days = int(((cfg.stage_def if cfg else None) or {}).get("realtx_report_days", 30))  # 신고기한(파라미터)
    base = (c.signed_at or datetime.now(UTC)).date()
    rpt = SalesRealtxReport(site_id=site_id, contract_ext_id=contract_id, status="PENDING",
                            due_date=base + timedelta(days=report_days),
                            payload={"unit_id": str(c.unit_id), "amount": int(c.total_price or 0)})
    # ★[TOCTOU 봉합] 위 SELECT 직후~INSERT 사이에 다른 요청이 같은 PENDING 신고를 먼저 넣을 수 있다.
    #   SAVEPOINT(begin_nested) 안에서 flush 해 부분 유니크(040) 위반(23505)을 잡고, 그 즉시 기존
    #   PENDING 행을 재조회·반환한다(중복행 0·미가공 500 금지). 인덱스 미적용 환경(deploy-pending)에선
    #   IntegrityError 가 안 나므로 정상 INSERT 로 동작(무회귀).
    try:
        async with db.begin_nested():
            db.add(rpt)
            await db.flush()
    except IntegrityError:
        logger.info("실거래신고 동시 생성 경합 흡수(site=%s contract=%s) — 기존 PENDING 재조회",
                    str(site_id), str(contract_id))
        existing = await _find_pending_report(db, site_id, contract_id)
        if existing is not None:
            return existing
        raise  # PENDING 도 아닌데 유니크 위반이면 다른 무결성 문제 — 숨기지 않고 전파.
    return rpt


async def submit_realtx(db: AsyncSession, site_id, report_id, irts_result: dict):
    # ★[격리] 신고건을 site_id 스코프로 로드 — 타현장 신고건을 제출 처리하지 못하게 막는다.
    rpt = (await db.execute(select(SalesRealtxReport).where(
        SalesRealtxReport.id == report_id,
        SalesRealtxReport.site_id == site_id,
    ))).scalar_one_or_none()
    if rpt is None:
        raise ValueError("실거래신고 건을 찾을 수 없습니다(현장 내 신고만 처리 가능)")
    # ★[종결가드·멱등] 이미 제출/수리(PENDING 아님)된 신고는 다시 덮어쓰지 않고 현 상태를 그대로 반환한다.
    #   과거엔 status/report_no 를 무조건 덮어써, 재호출 시 받은 report_no 가 없으면(None) 기존 접수번호가
    #   소실됐다(머니패스 서류 훼손). decide_transfer 의 decided_at 1회종결과 대칭으로 PENDING→1회만 확정.
    if rpt.status != "PENDING":
        logger.info("실거래신고 재제출 무시(이미 종결 status=%s, report=%s) — 멱등 반환",
                    rpt.status, str(report_id))
        return rpt
    rpt.status = irts_result.get("status", "SUBMITTED")
    rpt.report_no = irts_result.get("report_no")
    rpt.reported_at = datetime.now(UTC)
    await db.flush()
    return rpt


async def _find_pending_transfer(db: AsyncSession, site_id, contract_id):
    """같은 계약에 아직 결정되지 않은(PENDING) 전매요청을 1건 조회(없으면 None)."""
    return (await db.execute(select(SalesResaleTransfer).where(
        SalesResaleTransfer.site_id == site_id,
        SalesResaleTransfer.contract_ext_id == contract_id,
        SalesResaleTransfer.decided_at.is_(None),
    ))).scalars().first()


def _duplicate_payload(existing) -> dict:
    """기존 PENDING 전매요청 → 중복 응답. 기존 요청의 transfer_type 을 함께 노출한다.

    ★[과대매칭 해소] '계약당 단일 PENDING' 정책이라 종류(RESALE/NAME_CHANGE)가 달라도 새 행을
    만들지 않는다. 단, 기존 종류를 응답에 담아 호출자가 'RESALE 대기중인데 NAME_CHANGE 가
    조용히 RESALE 으로 처리된 것처럼 보이는' 오인을 막는다(silent-swallow 방지). 종류를 바꾸려면
    기존 PENDING 을 먼저 결정(승인/반려)한 뒤 다시 요청해야 함을 응답으로 알린다.
    """
    return {"transfer_id": str(existing.id), "allowed": bool(existing.allowed),
            "reason": existing.reason or "", "duplicate": True,
            "transfer_type": existing.transfer_type}


async def request_transfer(db: AsyncSession, site_id, contract_id, to_customer, transfer_type, by=None):
    # ★[격리·IDOR] 계약을 site_id 스코프로 로드 — 과거엔 id 만으로 로드해 타현장 계약의 전매요청을
    #   생성할 수 있었다(교차테넌트). 이제 현장 밖 계약은 '찾을 수 없음'으로 거부한다.
    c = await _load_contract_scoped(db, site_id, contract_id)
    # ★[멱등·정책=계약당 단일 PENDING] 같은 계약에 아직 결정되지 않은(PENDING) 전매요청이 있으면
    #   종류와 무관하게 새 행을 만들지 않고 기존 건을 반환한다 — 부분 유니크 인덱스(040)도 (site_id,
    #   contract_ext_id) WHERE decided_at IS NULL 로 같은 정책이라 앱-인덱스 술어가 정합한다. 종류가
    #   다른 요청은 기존 transfer_type 을 응답에 담아 silent-swallow(과대매칭)를 막는다.
    existing = await _find_pending_transfer(db, site_id, contract_id)
    if existing is not None:
        return _duplicate_payload(existing)
    restr = list((await db.execute(select(SalesResaleRestriction).where(
        SalesResaleRestriction.site_id == site_id,
        ((SalesResaleRestriction.unit_id == c.unit_id) |
         (SalesResaleRestriction.round_id == c.round_id))))).scalars())
    today = date.today()
    blocked = False
    note = ""
    for rs in restr:
        if rs.start_at and rs.months:
            end = rs.start_at + timedelta(days=rs.months * 30)
            if rs.start_at <= today <= end:
                blocked = True
                note = f"{rs.restriction_type} 제한기간 내(~{end})"
    t = SalesResaleTransfer(site_id=site_id, contract_ext_id=contract_id, from_customer=c.customer_id,
                            to_customer=to_customer, transfer_type=transfer_type,
                            allowed=(not blocked), reason=note or None)
    # ★[TOCTOU 봉합] SELECT(위 existing) 직후~INSERT 사이에 동시 요청이 같은 PENDING 을 먼저 넣을 수
    #   있다. SAVEPOINT 안에서 flush 해 부분 유니크(040) 위반(23505)을 잡고 기존 PENDING 을 재조회·반환
    #   한다(중복 PENDING 0·미가공 500 금지). 인덱스 미적용 환경(deploy-pending)에선 위반이 없어 정상 INSERT.
    try:
        async with db.begin_nested():
            db.add(t)
            await db.flush()
    except IntegrityError:
        logger.info("전매요청 동시 생성 경합 흡수(site=%s contract=%s) — 기존 PENDING 재조회",
                    str(site_id), str(contract_id))
        existing = await _find_pending_transfer(db, site_id, contract_id)
        if existing is not None:
            return _duplicate_payload(existing)
        raise  # PENDING 이 아닌데 유니크 위반이면 다른 무결성 문제 — 숨기지 않고 전파.
    return {"transfer_id": str(t.id), "allowed": not blocked, "reason": note,
            "transfer_type": transfer_type}


async def decide_transfer(db: AsyncSession, transfer_id, allowed: bool, reason: str = "", site_id=None):
    # site_id를 받으면 같은 현장의 전매요청만 처리 — 타 현장 명의변경 승인 차단(테넌트 격리).
    # SELECT FOR UPDATE 로 같은 요청을 잡아 동시 승인(이중 명의변경) race 를 막는다.
    q = select(SalesResaleTransfer).where(SalesResaleTransfer.id == transfer_id)
    if site_id is not None:
        q = q.where(SalesResaleTransfer.site_id == site_id)
    q = q.with_for_update()
    t = (await db.execute(q)).scalar_one_or_none()
    if t is None:
        raise ValueError("전매 요청을 찾을 수 없습니다")
    # ★[멱등·이중 명의변경 차단] 이미 결정된(decided_at 존재) 요청은 다시 처리하지 않는다.
    #   과거엔 가드가 없어 같은 요청을 두 번 승인하면 명의변경(c.customer_id 대입)이 반복 실행됐고,
    #   반려→재승인 같은 결과 뒤집기도 조용히 통과했다. 결정은 1회만 확정한다(상태머신 종결).
    if t.decided_at is not None:
        return {"transfer_id": str(t.id), "allowed": bool(t.allowed),
                "reason": t.reason or "", "already_decided": True}
    t.allowed = allowed
    t.reason = reason
    t.decided_at = datetime.now(UTC)
    if allowed:  # 명의변경 반영(승인 1회에 한해)
        # 계약도 같은 현장 스코프로 로드(요청 자체가 site_id 로 격리됐지만 이중 안전).
        cq = select(SalesContractExt).where(SalesContractExt.id == t.contract_ext_id)
        if site_id is not None:
            cq = cq.where(SalesContractExt.site_id == site_id)
        c = (await db.execute(cq)).scalar_one_or_none()
        if c is None:
            raise ValueError("전매 대상 계약을 찾을 수 없습니다")
        c.customer_id = t.to_customer
    await db.flush()
    return {"transfer_id": str(t.id), "allowed": allowed, "reason": reason}
