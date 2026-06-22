"""중도금 집단대출 — 은행 실행분을 해당 회차 납입처리(method=LOAN, 차주 자납과 구분) + 상환 기록. 기록만."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.contract_crm_ad import SalesContractInstallment
from apps.api.database.models.sales.loan import SalesLoanAgreement, SalesLoanDisbursement
from apps.api.database.models.sales.payment import SalesPayment


async def execute_disbursement(db: AsyncSession, site_id, agreement_id, installment_seq, amount, disbursed_at=None):
    # ★현장 격리: repay/reverse 와 대칭으로 disburse 도 site_id 를 필터한다 — 예전엔 id 만 조회해
    #   타 현장의 약정 id 를 알면 그 약정을 실행(회차 가산)할 수 있었다(격리 누락). 없으면 404.
    ag = (await db.execute(select(SalesLoanAgreement).where(
        SalesLoanAgreement.id == agreement_id,
        SalesLoanAgreement.site_id == site_id))).scalar_one_or_none()
    if ag is None:
        raise HTTPException(404, "해당 현장의 대출약정을 찾을 수 없습니다.")
    inst = (await db.execute(select(SalesContractInstallment).where(
        SalesContractInstallment.contract_ext_id == ag.contract_ext_id,
        SalesContractInstallment.seq == installment_seq))).scalar_one()
    when = disbursed_at or datetime.now(UTC)
    db.add(SalesLoanDisbursement(agreement_id=agreement_id, installment_seq=installment_seq,
           amount=amount, disbursed_at=when))
    inst.paid_amount = (inst.paid_amount or 0) + int(amount)
    inst.paid_at = when
    db.add(SalesPayment(site_id=site_id, contract_ext_id=ag.contract_ext_id, installment_id=inst.id,
           method="LOAN", amount=amount, paid_at=when, matched=True, status="MATCHED",
           raw_ref=f"loan:{agreement_id}"))
    ag.status = "EXECUTED"
    await db.flush()


def _disbursed_total(disbs) -> int:
    """실행분 합계(원). 자금이동 없는 기록 합산."""
    return sum(int(d.amount or 0) for d in disbs)


def _repaid_total(disbs) -> int:
    """누적 상환액 합계(원)."""
    return sum(int(d.repaid_amount or 0) for d in disbs)


def _allocate_repayment(disbs: list, amount: int) -> list:
    """상환액을 실행분(disbursement)에 disbursed_at(없으면 seq) 오래된 순서로 배분한다.

    각 disbursement 의 잔여미상환(amount - repaid_amount) 만큼 채우고 넘기면 다음으로 잇는다.
    반환=[(disbursement, 추가상환액)] (추가상환액>0 인 항목만). DB 무관 순수함수(배분규칙 테스트용).
    초과 상환(amount > 미상환총액)은 미상환총액까지만 배분한다(과상환 차단).
    """
    ordered = sorted(disbs, key=lambda d: (
        d.disbursed_at is None, d.disbursed_at or datetime.min.replace(tzinfo=UTC),
        d.installment_seq is None, d.installment_seq or 0))
    remaining = int(amount)
    out = []
    for d in ordered:
        if remaining <= 0:
            break
        outstanding = int(d.amount or 0) - int(d.repaid_amount or 0)
        if outstanding <= 0:
            continue
        applied = min(outstanding, remaining)
        out.append((d, applied))
        remaining -= applied
    return out


async def repay_loan(db: AsyncSession, site_id, agreement_id, amount, repaid_at=None) -> dict:
    """대출 상환 — 부분/전액 상환을 멱등하게 기록하고, 전액 상환되면 status=REPAID 로 전이한다.

    - 부분상환: 실행분(disbursement)에 오래된 순서로 누적(repaid_amount) 가산. 마지막 1원까지 채워진
      disbursement 에 repaid_at 을 찍는다.
    - 멱등/과상환 차단: 이미 REPAID 면 추가 충당 없이 그대로 반환(중복 상환 콜백 방어). 남은 미상환
      총액을 초과하는 상환은 미상환총액까지만 반영(over-repay 방지).
    - 자금이동 미수행(상환 '기록'만). 반환=상환 결과 요약.
    """
    ag = (await db.execute(select(SalesLoanAgreement).where(
        SalesLoanAgreement.id == agreement_id,
        SalesLoanAgreement.site_id == site_id))).scalar_one_or_none()
    if ag is None:
        raise HTTPException(404, "해당 현장의 대출약정을 찾을 수 없습니다.")
    amt = int(amount)
    if amt <= 0:
        raise HTTPException(400, "상환액은 양수여야 합니다.")
    # 같은 약정의 실행분을 행잠금(FOR UPDATE)해 동시 상환 콜백의 경쟁을 막는다(이중 충당 방지).
    disbs = list((await db.execute(select(SalesLoanDisbursement).where(
        SalesLoanDisbursement.agreement_id == agreement_id).with_for_update())).scalars())
    if not disbs:
        raise HTTPException(409, "실행(disbursement) 기록이 없어 상환 처리할 수 없습니다.")
    # 이미 전액 상환된 약정이면 멱등하게 그대로 반환(추가 충당 없음).
    # ★응답계약 통일: 두 분기(멱등/정상)가 같은 키집합을 항상 반환한다
    #   (status·applied·fully_repaid·duplicate·disbursed·repaid·outstanding).
    if ag.status == "REPAID":
        disbursed_now = _disbursed_total(disbs)
        repaid_now = _repaid_total(disbs)
        return {"status": "REPAID", "applied": 0, "fully_repaid": True, "duplicate": True,
                "disbursed": disbursed_now, "repaid": repaid_now,
                "outstanding": max(disbursed_now - repaid_now, 0)}
    when = repaid_at or datetime.now(UTC)
    plan = _allocate_repayment(disbs, amt)
    applied_total = 0
    for d, applied in plan:
        d.repaid_amount = int(d.repaid_amount or 0) + applied
        applied_total += applied
        # 이 실행분이 완납되면 상환완료 시각을 찍는다(부분상환 단계에선 None 유지).
        if int(d.repaid_amount) >= int(d.amount or 0):
            d.repaid_at = when
    repaid_now = _repaid_total(disbs)
    disbursed_now = _disbursed_total(disbs)
    # 전액 상환(누적 상환 >= 실행 총액)되면 약정 상태를 REPAID 로 전이.
    fully = disbursed_now > 0 and repaid_now >= disbursed_now
    if fully:
        ag.status = "REPAID"
    await db.flush()
    return {"status": ag.status, "applied": applied_total, "fully_repaid": fully, "duplicate": False,
            "disbursed": disbursed_now, "repaid": repaid_now,
            "outstanding": max(disbursed_now - repaid_now, 0)}
