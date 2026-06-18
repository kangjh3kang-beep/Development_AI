"""Part5 라이프사이클 액션 — 청약 배정/예비/선착순 + 옵션 + 대출실행 + 수납(VA/대사/수동매칭)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, require_role, sales_ctx
from app.services.sales.loan.service import execute_disbursement, repay_loan
from app.services.sales.options.service import add_option
from app.services.sales.payment.locks import ADJ_LOCK_KEY, OVERDUE_LOCK_KEY
from app.services.sales.payment.service import (
    ingest_payment,
    issue_va,
    overdue_calc,
    reverse_payment,
)
from app.services.sales.subscription.engine import claim_offer, promote_reserve, run_draw

r5 = APIRouter(tags=["sales-p5"])

# 연체 일배치(main.py _overdue_batch_loop)와 '같은' advisory-lock 키 — 수동 트리거와 일배치가
# 같은 현장·기준일에 동시 진입해도 직렬화되도록 동일 키로 상호배제한다(23505 race 제거 이중방어).
# ★키는 app/services/sales/payment/locks.py 단일 상수(SSOT)에서 import 한다(main.py 와 값 동기화).
_OVERDUE_LOCK_KEY = OVERDUE_LOCK_KEY


def _parse_dt(v):
    """ISO8601 문자열(또는 None)을 datetime 으로 파싱. 형식 오류면 400(은폐 금지).

    날짜만('YYYY-MM-DD') 들어오면 fromisoformat 은 tz 정보 없는 naive(자정) 를 만든다 →
    DateTime(timezone=True) 컬럼에 naive 를 넣으면 서버 로컬TZ로 해석돼 모호하다. naive 면
    UTC 로 보정해 일관된 시각으로 저장한다(연체·납부 시각 비교의 기준 일치).
    """
    if v in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(v))
    except (ValueError, TypeError):
        raise HTTPException(400, "시각은 ISO8601(YYYY-MM-DDTHH:MM:SS) 형식이어야 합니다.") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


# 금액 상한 — 1조 원. 오타/위조 페이로드로 비현실 금액이 들어오는 것을 1차 차단한다.
_AMOUNT_CAP = 1_000_000_000_000


@r5.post("/subscription/{ann_id}/draw")
async def draw(ann_id: uuid.UUID, body: dict | None = None, db: AsyncSession = Depends(get_db),
               ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY"))):
    n = await run_draw(db, ctx.site_id, ann_id, (body or {}).get("seed"))
    await db.commit()
    return {"winners": n}


@r5.post("/subscription/reserve/promote")
async def reserve_promote(body: dict, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY", "DIRECTOR"))):
    aid = await promote_reserve(db, ctx.site_id, uuid.UUID(body["unit_id"]), by=ctx.user.id)
    await db.commit()
    return {"promoted_application": str(aid) if aid else None}


@r5.post("/subscription/claim")
async def subscription_claim(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    uid = await claim_offer(db, ctx.site_id, uuid.UUID(body["unit_id"]),
                            body.get("customer_id"), body.get("kind", "FCFS"))
    await db.commit()
    return {"unit_id": str(uid)}


@r5.post("/contracts/{contract_id}/options")
async def contract_add_option(contract_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                              ctx: SalesCtx = Depends(sales_ctx)):
    res = await add_option(db, contract_id, uuid.UUID(body["option_id"]), int(body.get("qty", 1)))
    await db.commit()
    return res


@r5.post("/loan/disburse")
async def loan_disburse(body: dict, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY"))):
    await execute_disbursement(db, ctx.site_id, uuid.UUID(body["agreement_id"]),
                               int(body["installment_seq"]), int(body["amount"]), body.get("disbursed_at"))
    await db.commit()
    return {"ok": True}


# ── #4 머니패스(대출상환·연체재계산·입금취소) 요청/응답 계약(OpenAPI) ──────────────
class LoanRepayRequest(BaseModel):
    agreement_id: uuid.UUID
    amount: int = Field(gt=0, le=_AMOUNT_CAP, description="상환액(원, 양수)")
    repaid_at: str | None = Field(default=None, description="상환 시각(ISO8601, 생략 시 현재)")


class LoanRepayResponse(BaseModel):
    status: str
    applied: int
    fully_repaid: bool
    duplicate: bool
    disbursed: int
    repaid: int
    outstanding: int


class RunOverdueResponse(BaseModel):
    rows: int
    as_of: str
    locked: bool = Field(description="advisory-lock 획득 여부(False면 일배치가 보유 중이라 skip)")


class PaymentReverseRequest(BaseModel):
    reason: str | None = Field(default=None, description="취소/반려 사유(선택)")


class PaymentReverseResponse(BaseModel):
    status: str
    reversed: bool
    duplicate: bool = False
    reverted_amount: int = 0


class PaymentIngestResponse(BaseModel):
    """입금 대사(webhook) 응답계약 — ingest_payment 세 분기(매칭/미매칭/중복)가 같은 키집합 반환.

    소비자(프론트·재시도 콜백)가 분기마다 다른 키를 가정하지 않게 통일한다(SSOT).
    """
    matched: bool
    status: str
    duplicate: bool = False
    contract: str | None = None
    allocated: int = 0   # 회차에 실제 충당된 합계(원)
    unapplied: int = 0   # 충당 못 하고 남은 금액(원, 미매칭/완납계약 등)


@r5.post("/loan/repay", response_model=LoanRepayResponse)
async def loan_repay(body: LoanRepayRequest, db: AsyncSession = Depends(get_db),
                     ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY"))):
    """대출 상환 기록 — 부분/전액 상환 멱등 처리, 전액 상환 시 status=REPAID 전이. 자금이동 없음."""
    res = await repay_loan(db, ctx.site_id, body.agreement_id, body.amount, _parse_dt(body.repaid_at))
    await db.commit()
    return res


@r5.post("/payments/run-overdue", response_model=RunOverdueResponse)
async def run_overdue(db: AsyncSession = Depends(get_db),
                      ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY", "DIRECTOR", "GM_DIRECTOR"))):
    """연체이자 산정 수동/크론 트리거 — 현재 현장(ctx.site_id)의 미납 회차 연체이자를 오늘 기준 산정.

    인프로세스 스케줄러(main.py)가 전 현장을 일배치로 돌지만, 즉시 재계산이 필요할 때 쓰는
    크론-호출 진입점. 자금이동 미수행(산출·적재만).

    [동시성·멱등 — 실제 보장수준]
    - overdue_calc 는 (site_id, installment_id, calc_date) 에 ON CONFLICT DO UPDATE 라 같은 날
      재호출/동시진입에도 UNIQUE 위반(23505) 없이 덮어쓴다(행 중복 0).
    - 추가로 일배치(_overdue_batch_loop)와 '같은' advisory-lock(_OVERDUE_LOCK_KEY)을 try-lock 한다.
      ★pg_try_advisory_xact_lock(트랜잭션 종료 시 자동해제) 으로 잡는다 — 기존 세션락 +
      finally 수동 unlock 은 overdue_calc 가 (테이블 미존재 폴백에서) rollback 한 뒤 aborted/
      세션 상태에서 unlock 이 재실패하거나 세션락이 잔존할 위험이 있었다. xact 락은 commit/
      rollback 어느 쪽으로 끝나도 자동해제돼 락 누수가 원천 차단된다(별도 unlock 호출 불필요).
      일배치가 돌고 있으면(락 보유) 수동 호출은 곧 다시 산정되므로 skip(locked=False)한다 —
      불필요한 중복 작업을 줄이는 best-effort 직렬화이며, 정합성은 ON CONFLICT 가 보장한다.
    """
    now = datetime.now(UTC)
    got = bool((await db.execute(
        text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _OVERDUE_LOCK_KEY})).scalar())
    if not got:
        # 일배치(또는 다른 워커)가 이미 산정 중 → 곧 반영되므로 즉시 반환(중복 작업 회피).
        # xact 락이라 이 트랜잭션이 끝나면(아래 return 후 세션 정리) 자동해제된다.
        await db.rollback()
        return {"rows": 0, "as_of": str(now.date()), "locked": False}
    # xact 락은 이 트랜잭션 종료 시 자동해제 → 산정 후 commit 하면 락도 함께 풀린다(누수 0).
    n = await overdue_calc(db, ctx.site_id, now)
    await db.commit()
    return {"rows": n, "as_of": str(now.date()), "locked": True}


@r5.post("/payments/va/issue")
async def va_issue(body: dict, db: AsyncSession = Depends(get_db),
                   ctx: SalesCtx = Depends(require_role("AGENCY", "DIRECTOR", "GM_DIRECTOR", "DEVELOPER"))):
    # 가상계좌 발급은 자금 흐름과 직결되는 민감 작업 → 일반 팀원(MEMBER)이 아닌 관리 권한만 허용.
    from fastapi import HTTPException
    try:
        cid = uuid.UUID(str(body["contract_id"]))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "contract_id가 올바르지 않습니다.") from None
    if not body.get("bank") or not body.get("va_number"):
        raise HTTPException(400, "은행·가상계좌번호는 필수입니다.")
    await issue_va(db, ctx.site_id, cid, body["bank"],
                   body["va_number"], body.get("holder"), body.get("pool_ref"))
    await db.commit()
    return {"ok": True}


@r5.post("/payments/webhook", response_model=PaymentIngestResponse)
async def payments_webhook(body: dict, db: AsyncSession = Depends(get_db),
                           ctx: SalesCtx = Depends(require_role("AGENCY", "DIRECTOR", "GM_DIRECTOR", "DEVELOPER"))):
    """내부 수동 입금 기록·대사(★외부 PG/은행 콜백 아님).

    [신뢰경계 정직표기] 이 엔드포인트는 인증된 현장 멤버가 직접 입금 통지를 입력해 미납 회차에
    충당하는 '내부 수동' 진입점이다(프론트 PaymentsPanel '입금 대사'). 외부 시스템이 서명 없이
    호출하는 공개 콜백이 아니므로 HMAC 시그니처 검증을 두지 않는다 — 대신 멤버 인증 토큰이
    신뢰경계다. (장차 PG/은행 직접 콜백을 받으려면 별도 공개 엔드포인트에 HMAC 서명검증을
    신설해야 한다. 현재 경로로는 외부에서 서명 없이 위조입금을 넣을 수 없다.)

    [권한·금액 게이트] 입금 충당은 회차 납입액(자금 정합)을 직접 바꾸는 민감 작업이라
    일반 팀원(MEMBER)이 아닌 관리 권한(AGENCY 이상)만 허용한다(대출 상환 loan/repay 와 대칭).
    또 오타/위조로 비현실 금액이 들어오는 것을 _AMOUNT_CAP(1조 원)로 1차 차단한다.

    입력 가드는 ingest_payment 내부에서도 수행한다: amount>0(400), raw_ref 중복(멱등) 차단.
    """
    # 금액 상한 가드(loan/repay 와 대칭) — 비현실 금액 1차 차단(정밀 검증은 ingest_payment 가 수행).
    raw_amount = body.get("amount")
    if raw_amount is None:
        raise HTTPException(400, "입금액(amount)은 필수입니다.")
    try:
        amt = int(raw_amount)
    except (TypeError, ValueError):
        raise HTTPException(400, "입금액(amount)이 올바르지 않습니다.") from None
    if amt > _AMOUNT_CAP:
        raise HTTPException(400, f"입금액이 상한({_AMOUNT_CAP:,}원)을 초과했습니다.")
    # 입금 시각(paid_at)이 들어오면 ISO8601 검증 후 datetime 으로 정규화한다
    # (형식 오류는 400·은폐 금지, 문자열을 그대로 DateTime 컬럼에 넣지 않도록 객체로 변환).
    if body.get("paid_at") not in (None, ""):
        body = {**body, "paid_at": _parse_dt(body.get("paid_at"))}
    res = await ingest_payment(db, ctx.site_id, body)
    await db.commit()
    return res


@r5.post("/payments/{payment_id}/reverse", response_model=PaymentReverseResponse)
async def payment_reverse(payment_id: uuid.UUID, body: PaymentReverseRequest | None = None,
                          db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role("AGENCY", "DIRECTOR", "GM_DIRECTOR", "DEVELOPER"))):
    """입금 취소/반려(MATCHED→REVERSED) — 충당했던 회차 납입액을 되돌리고 종료상태로 전이.

    데드스테이트 해소: 기존엔 REVERSED 로 전이하는 writer 가 없어 상태머신이 한쪽으로만 흘렀다.
    같은 현장 결제만 취소 가능(현장 격리), 이미 REVERSED 면 멱등(추가 차감 없음). 자금이동 없음."""
    res = await reverse_payment(db, ctx.site_id, payment_id, (body.reason if body else None))
    await db.commit()
    return res


@r5.get("/payments/overdue")
async def payments_overdue(db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    """연체 현황 — 회차별 '최신 산정일(calc_date)' 1건만 반환(현장 격리, 최신순).

    [왜 전용 엔드포인트인가]
    기존엔 자동 CRUD(GET /payments/overdue)가 order_by·calc_date 필터 없이 limit100 으로 전체
    sales_overdue_interest 행을 그대로 반환했다. 일배치가 매일 산정(INSERT)하므로 한 회차가
    N일 미납이면 그 회차의 산정행이 N개 쌓여, 연체현황 표에 같은 회차가 중복 표기되고 100행
    캡에 최신이 가려졌다. 이 전용 핸들러는 회차별 최신 calc_date 1건만 골라(DISTINCT ON) 최신순
    으로 돌려준다(중복 0·최신 보존). r5 가 자동 CRUD 보다 먼저 등록되므로 이 경로가 우선한다.

    테이블/컬럼 미존재(42P01/42703)면 마이그레이션 직전이므로 정상 빈 목록(은폐 아님)."""
    try:
        # DISTINCT ON (installment_id): 같은 회차는 calc_date 가장 늦은(최신) 1행만 남긴다.
        # calc_date 가 NULL 인 구행(마이그레이션 전)도 포함하되 최신 정렬에서 뒤로 보낸다(nulls last).
        rows = (await db.execute(text(
            "SELECT DISTINCT ON (installment_id) id, installment_id, overdue_days, amount, "
            "       calc_date, calculated_at "
            "FROM sales_overdue_interest "
            "WHERE site_id = :s "
            "ORDER BY installment_id, calc_date DESC NULLS LAST, calculated_at DESC"),
            {"s": str(ctx.site_id)})).all()
    except Exception as e:  # noqa: BLE001 — 미존재(정상 빈목록)만 폴백, 실오류는 재전파(은폐 금지).
        from app.services.sales.payment.service import _missing_object_sqlstate
        if _missing_object_sqlstate(e):
            await db.rollback()
            return []
        raise
    # 최신순(연체이자 큰 순이 아니라 산정일 최신순)으로 정렬해 반환한다(프론트 표 정합).
    items = [{
        "id": str(r[0]),
        "installment_id": str(r[1]) if r[1] else None,
        "overdue_days": int(r[2] or 0),
        "amount": int(r[3] or 0),
        "calc_date": str(r[4]) if r[4] else None,
    } for r in rows]
    items.sort(key=lambda x: (x["calc_date"] or "", x["overdue_days"]), reverse=True)
    return items


@r5.get("/payments/unmatched")
async def payments_unmatched(status: str = "UNMATCHED", db: AsyncSession = Depends(get_db),
                             ctx: SalesCtx = Depends(sales_ctx)):
    """입금 큐 조회 — 기본은 미대사(UNMATCHED), status 파라미터로 매칭완료(MATCHED) 목록도 조회(현장 격리).

    [왜 status 파라미터인가] 기존엔 UNMATCHED 만 화면에 노출돼 취소(reverse) 버튼이 미대사 큐에만
    달렸다. 그런데 이번 머니패스의 핵심가치(다회차 분산 입금을 회차별 정확히 역배분하는 reverse)는
    'MATCHED' 입금이 대상이라 화면 도달 경로가 없었다. 신규 엔드포인트를 늘리지 않고 이 기존 핸들러를
    status(화이트리스트) 필터로 일반화해 MATCHED 목록도 같은 형식으로 돌려준다(취소 버튼 출하).
    기본값 UNMATCHED 라 기존 호출(파라미터 없음)은 거동 불변(무회귀).

    수동매칭(manual-match) 또는 취소(reverse)의 대상 목록을 화면에 제공한다(머니패스 가시성).
    테이블 미존재(42P01/42703)면 마이그레이션 직전이므로 정상 빈 목록(은폐 아님)."""
    from apps.api.database.models.sales.payment import SalesPayment
    # 허용 상태만(위조 파라미터 차단). 그 외 값은 400(은폐 금지).
    st = (status or "UNMATCHED").upper()
    if st not in ("UNMATCHED", "MATCHED"):
        raise HTTPException(400, "status는 UNMATCHED 또는 MATCHED 여야 합니다.")
    try:
        rows = list((await db.execute(
            select(SalesPayment).where(
                SalesPayment.site_id == ctx.site_id,
                SalesPayment.status == st,
            ).order_by(SalesPayment.paid_at.desc().nullslast()))).scalars())
    except Exception as e:  # noqa: BLE001 — 미존재(정상 빈목록)만 폴백, 실오류는 재전파(은폐 금지).
        from app.services.sales.payment.service import _missing_object_sqlstate
        if _missing_object_sqlstate(e):
            return {"count": 0, "items": []}
        raise
    items = [{
        "id": str(p.id),
        "method": p.method,
        "amount": int(p.amount or 0),
        "paid_at": str(p.paid_at) if p.paid_at else None,
        "raw_ref": p.raw_ref,
        # MATCHED 목록에서 어느 계약 입금인지 식별(reverse 대상 가시성). UNMATCHED 면 None.
        "contract": str(p.contract_ext_id) if p.contract_ext_id else None,
    } for p in rows]
    return {"count": len(items), "items": items}


@r5.post("/payments/{payment_id}/manual-match")
async def manual_match(payment_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(require_role("AGENCY", "DIRECTOR", "DEVELOPER"))):
    from fastapi import HTTPException

    from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesContractInstallment
    from apps.api.database.models.sales.payment import SalesPayment
    try:
        inst_id = uuid.UUID(str(body["installment_id"]))
        contract_id = uuid.UUID(str(body["contract_id"]))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "installment_id·contract_id가 올바르지 않습니다.") from None
    # 같은 현장(site_id)의 결제만 수동매칭 허용 — 타 현장 결제 위조 차단. with_for_update 로 행잠금
    # (회차 조회와 잠금 대칭 — 동시 매칭/취소 경쟁에서 이중 가산·교차 갱신 차단).
    p = (await db.execute(select(SalesPayment).where(
        SalesPayment.id == payment_id, SalesPayment.site_id == ctx.site_id
    ).with_for_update())).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "결제 내역을 찾을 수 없습니다.")
    # 이미 매칭된 결제를 또 매칭하면 회차 납입액이 이중 가산된다 → 막는다(멱등 가드).
    # MATCHED/REVERSED 는 종료상태 → 재매칭 불가. matched(bool)·status(상태머신) 둘 다로 차단.
    if p.matched or p.status in ("MATCHED", "REVERSED"):
        raise HTTPException(409, "이미 대사 완료(또는 반려)된 입금입니다.")
    # 대상 회차가 (a)같은 현장 계약 소속이고 (b)요청한 contract_id 소속인지 둘 다 확인한다.
    # ★contract_ext_id == contract_id 교차검증 — 운영자가 회차는 A계약, 계약은 B계약으로 잘못
    #   지정해도 그 회차가 B계약 소속이 아니면 거부해 '타 계약 회차 오귀속'을 차단한다.
    #   with_for_update 로 회차도 잠가 동시 충당/취소와 잠금 대칭을 맞춘다.
    it = (await db.execute(select(SalesContractInstallment)
        .join(SalesContractExt, SalesContractExt.id == SalesContractInstallment.contract_ext_id)
        .where(SalesContractInstallment.id == inst_id,
               SalesContractInstallment.contract_ext_id == contract_id,
               SalesContractExt.site_id == ctx.site_id)
        .with_for_update(of=SalesContractInstallment))).scalar_one_or_none()
    if it is None:
        raise HTTPException(404, "해당 현장·계약의 회차를 찾을 수 없습니다.")
    applied = int(p.amount or 0)
    p.installment_id = inst_id
    p.contract_ext_id = contract_id
    p.matched = True
    p.status = "MATCHED"
    # 충당 내역 기록 — 단일 회차지만 reverse 가 allocations 기반으로 정확히 되돌리도록 동일 형식으로 남긴다.
    p.allocations = [{"installment_id": str(inst_id), "applied_amount": applied}]
    it.paid_amount = (it.paid_amount or 0) + applied
    it.paid_at = datetime.now(UTC)
    await db.commit()
    return {"matched": True, "status": "MATCHED"}


# ── #4 할인/환급 + 계약자별 통합 수납현황 ──────────────────────────────────────
# 회차(installment 납부)·연체(SalesOverdueInterest)는 기존 존재. 할인/환급은 별도 조정 레코드로
# 멱등 테이블에 적립하고, 계약자 기준으로 납부/연체/할인/환급을 한 번에 집계한다(가짜값 없음).
#
# ★정본은 Alembic 마이그레이션(035_sales_payment_adjustments)이다. 아래 _ensure_adj 는 마이그레이션
#   미적용 환경(샌드박스/구버전 배포)에서도 끊김 없이 동작하게 하는 '런타임 안전망'일 뿐이다.
#   여러 워커가 동시에 CREATE 를 쏘면 race 가 나므로 Postgres advisory lock 으로 1회만 실행한다.
_ADJ_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_payment_adjustments ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  contract_ext_id uuid NOT NULL,"
    "  adj_type varchar(12) NOT NULL,"          # DISCOUNT(할인) | REFUND(환급)
    "  amount numeric(16,0) NOT NULL,"
    "  reason text,"
    "  created_by uuid,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
# 이 테이블 보장 전용 advisory lock 키(다른 모듈과 충돌하지 않는 고유 상수).
# ★app/services/sales/payment/locks.py 단일 상수(SSOT)에서 import(매직넘버 중복 제거).
_ADJ_LOCK_KEY = ADJ_LOCK_KEY
_ADJ_READY = False


async def _ensure_adj(db: AsyncSession) -> None:
    """sales_payment_adjustments 테이블 보장(런타임 안전망, 프로세스당 1회).

    advisory lock 으로 동시 CREATE race 를 제거한다(여러 워커여도 실제 DDL 은 1번만).
    정본은 Alembic 035 마이그레이션 — 마이그레이션이 적용된 환경에선 IF NOT EXISTS 라 no-op.
    """
    global _ADJ_READY
    if _ADJ_READY:
        return
    # best-effort 락: 잡았으면 DDL 1회 실행 후 해제. 실패해도 IF NOT EXISTS 라 안전(중복 무해).
    got = bool((await db.execute(
        text("SELECT pg_try_advisory_lock(:k)"), {"k": _ADJ_LOCK_KEY})).scalar())
    try:
        await db.execute(text(_ADJ_DDL))
        await db.commit()
    finally:
        if got:
            await db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADJ_LOCK_KEY})
            await db.commit()
    _ADJ_READY = True


@r5.post("/payments/adjustment")
async def payment_adjustment(body: dict, db: AsyncSession = Depends(get_db),
                             ctx: SalesCtx = Depends(require_role("AGENCY", "GM_DIRECTOR", "DIRECTOR", "DEVELOPER"))):
    """할인(DISCOUNT)·환급(REFUND) 조정 등록. amount는 원(KRW) 양수."""
    from fastapi import HTTPException
    await _ensure_adj(db)
    try:
        cid = uuid.UUID(str(body["contract_ext_id"]))
        atype = str(body["adj_type"]).upper()
        amount = int(body["amount"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "contract_ext_id·adj_type(DISCOUNT/REFUND)·amount 필요") from None
    if atype not in ("DISCOUNT", "REFUND") or amount <= 0:
        raise HTTPException(400, "adj_type은 DISCOUNT/REFUND, amount는 양수여야 합니다.")
    await db.execute(text(
        "INSERT INTO sales_payment_adjustments (site_id, contract_ext_id, adj_type, amount, reason, created_by) "
        "VALUES (:s,:c,:t,:a,:r,:u)"),
        {"s": str(ctx.site_id), "c": str(cid), "t": atype, "a": amount,
         "r": body.get("reason"), "u": str(getattr(ctx.user, "id", "")) or None})
    await db.commit()
    return {"ok": True, "adj_type": atype, "amount": amount}


@r5.get("/payments/contract-summary")
async def payment_contract_summary(contract_id: str, db: AsyncSession = Depends(get_db),
                                   ctx: SalesCtx = Depends(sales_ctx)):
    """계약자(계약) 기준 통합 수납현황 — 납부/연체/할인/환급(원 단위)."""
    from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesContractInstallment
    await _ensure_adj(db)
    cid = uuid.UUID(contract_id)
    c = (await db.execute(select(SalesContractExt).where(
        SalesContractExt.id == cid, SalesContractExt.site_id == ctx.site_id))).scalar_one_or_none()
    if not c:
        from fastapi import HTTPException
        raise HTTPException(404, "해당 현장의 계약을 찾을 수 없습니다.")
    insts = list((await db.execute(select(SalesContractInstallment).where(
        SalesContractInstallment.contract_ext_id == cid)
        .order_by(SalesContractInstallment.seq))).scalars())
    billed = sum(int(i.amount or 0) for i in insts)
    paid = sum(int(i.paid_amount or 0) for i in insts)
    today = datetime.now(UTC).date()
    overdue = [{"seq": i.seq, "due_date": str(i.due_date), "unpaid": int((i.amount or 0) - (i.paid_amount or 0))}
               for i in insts if i.due_date and i.due_date < today and (i.paid_amount or 0) < (i.amount or 0)]
    adj = (await db.execute(text(
        "SELECT adj_type, count(*), coalesce(sum(amount),0) FROM sales_payment_adjustments "
        "WHERE site_id=:s AND contract_ext_id=:c GROUP BY adj_type"),
        {"s": str(ctx.site_id), "c": str(cid)})).all()
    adj_map = {t: {"count": int(n), "amount": int(a)} for t, n, a in adj}
    return {
        "contract_id": str(cid),
        "total_price": int(c.total_price or 0),
        "installments": {"count": len(insts), "billed": billed, "paid": paid, "unpaid": billed - paid},
        "overdue": {"count": len(overdue), "items": overdue,
                    "unpaid_amount": sum(o["unpaid"] for o in overdue)},
        "discount": adj_map.get("DISCOUNT", {"count": 0, "amount": 0}),
        "refund": adj_map.get("REFUND", {"count": 0, "amount": 0}),
    }


@r5.get("/payments/installments")
async def payment_installments(contract_id: str, db: AsyncSession = Depends(get_db),
                               ctx: SalesCtx = Depends(sales_ctx)):
    """계약 회차별 납부 스케줄 — 계약금·중도금·잔금 회차의 약정일·금액·납부·미납·상태(PAID/PARTIAL/UNPAID/OVERDUE)
    + 연체(일수·이자)를 오늘 기준으로 실시간 산출. 자금이동 미수행(현황·산출만)."""
    from decimal import Decimal

    from fastapi import HTTPException

    from app.services.sales.payment.service import overdue_interest
    from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesContractInstallment
    from apps.api.database.models.sales.site_org import SalesSiteConfig
    cid = uuid.UUID(contract_id)
    c = (await db.execute(select(SalesContractExt).where(
        SalesContractExt.id == cid, SalesContractExt.site_id == ctx.site_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "해당 현장의 계약을 찾을 수 없습니다.")
    cfg = (await db.execute(select(SalesSiteConfig).where(
        SalesSiteConfig.site_id == ctx.site_id))).scalar_one_or_none()
    # 연체이율(약관 파라미터, 0이면 미설정 → 이자 0).
    rate = float(((cfg.stage_def if cfg else None) or {}).get("overdue_rate", 0))
    insts = list((await db.execute(select(SalesContractInstallment).where(
        SalesContractInstallment.contract_ext_id == cid).order_by(SalesContractInstallment.seq))).scalars())
    today = datetime.now(UTC).date()
    kind_label = {"DOWN": "계약금", "MIDDLE": "중도금", "BALANCE": "잔금", "OPTION": "옵션"}
    rows = []
    t_billed = t_paid = t_unpaid = t_interest = 0
    for it in insts:
        amt = int(it.amount or 0)
        paid = int(it.paid_amount or 0)
        unpaid = amt - paid
        overdue_days = 0
        interest = 0
        if unpaid <= 0:
            status = "PAID"
        elif paid > 0:
            status = "PARTIAL"
        else:
            status = "UNPAID"
        if unpaid > 0 and it.due_date and it.due_date < today:
            status = "OVERDUE"
            overdue_days = (today - it.due_date).days
            # ★정본 산식 통일: 화면 표시값을 적재값과 동일한 overdue_interest(ROUND_HALF_EVEN)로 계산한다.
            #   기존 int(Decimal(...)) 는 ROUND_DOWN(절사)이라 화면값과 일배치 적재값이 1원 어긋날 수
            #   있었다(같은 입력 다른 반올림). 정본 순수함수로 통일해 화면·DB 값을 일치시킨다.
            interest = overdue_interest(unpaid, overdue_days, Decimal(str(rate)))
        rows.append({
            "installment_id": str(it.id),  # 수동매칭(manual-match) 대상 회차 식별자.
            "seq": it.seq, "kind": it.kind,
            "kind_label": kind_label.get((it.kind or "").upper(), it.kind),
            "amount": amt, "paid_amount": paid, "unpaid": unpaid,
            "due_date": str(it.due_date) if it.due_date else None,
            "paid_at": str(it.paid_at) if it.paid_at else None,
            "status": status, "overdue_days": overdue_days, "overdue_interest": interest,
        })
        t_billed += amt
        t_paid += paid
        t_unpaid += unpaid
        t_interest += interest
    return {
        "contract_id": str(cid), "total_price": int(c.total_price or 0),
        "overdue_rate": rate, "as_of": str(today), "count": len(rows), "installments": rows,
        "totals": {"billed": t_billed, "paid": t_paid, "unpaid": t_unpaid, "overdue_interest": t_interest},
    }
