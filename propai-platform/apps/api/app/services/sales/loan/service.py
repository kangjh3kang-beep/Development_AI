"""중도금 집단대출 — 은행 실행분을 해당 회차 납입처리(method=LOAN, 차주 자납과 구분). 기록만."""

from datetime import datetime, timezone, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.contract_crm_ad import SalesContractInstallment
from apps.api.database.models.sales.loan import SalesLoanAgreement, SalesLoanDisbursement
from apps.api.database.models.sales.payment import SalesPayment


async def execute_disbursement(db: AsyncSession, site_id, agreement_id, installment_seq, amount, disbursed_at=None):
    ag = (await db.execute(select(SalesLoanAgreement).where(SalesLoanAgreement.id == agreement_id))).scalar_one()
    inst = (await db.execute(select(SalesContractInstallment).where(
        SalesContractInstallment.contract_ext_id == ag.contract_ext_id,
        SalesContractInstallment.seq == installment_seq))).scalar_one()
    when = disbursed_at or datetime.now(UTC)
    db.add(SalesLoanDisbursement(agreement_id=agreement_id, installment_seq=installment_seq,
           amount=amount, disbursed_at=when))
    inst.paid_amount = (inst.paid_amount or 0) + int(amount)
    inst.paid_at = when
    db.add(SalesPayment(site_id=site_id, contract_ext_id=ag.contract_ext_id, installment_id=inst.id,
           method="LOAN", amount=amount, paid_at=when, matched=True, raw_ref=f"loan:{agreement_id}"))
    ag.status = "EXECUTED"
    await db.flush()
