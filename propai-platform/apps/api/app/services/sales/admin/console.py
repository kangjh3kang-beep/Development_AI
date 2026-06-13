"""분양관리요약(관리자) 현장별 통합 관리 콘솔 — 담당자·근태·계약·매출·수수료·방문·광고·회계 집계.

'같이 또 따로': 시행사/관리자가 보유 현장 전체(포트폴리오)와 현장 단위 상세를 모두 본다.
기존 자산(org/contracts/commission/mh_visitors/attendance/ad)을 집계하고, 신규 회계 원장
(sales_site_accounting: 인건비/경비/공과금/광고비/기타)으로 현장별 손익을 산출한다.
가짜값 금지: 데이터 없으면 0/빈값으로 정직 표기.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_ENTRY_TYPES = {"LABOR": "인건비", "EXPENSE": "경비", "UTILITY": "공과금", "AD": "광고비", "ETC": "기타"}

_ACCT_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_site_accounting ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  entry_type varchar(12) NOT NULL,"          # LABOR/EXPENSE/UTILITY/AD/ETC
    "  amount numeric(16,0) NOT NULL,"
    "  memo text,"
    "  entry_date date NOT NULL DEFAULT current_date,"
    "  created_by uuid,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_ACCT_READY = False


async def _ensure_acct(db: AsyncSession) -> None:
    global _ACCT_READY
    if _ACCT_READY:
        return
    await db.execute(text(_ACCT_DDL))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_site_acct_site ON sales_site_accounting(site_id)"))
    await db.commit()
    _ACCT_READY = True


async def add_accounting_entry(db: AsyncSession, site_id, entry_type: str, amount: int,
                               memo: str | None, entry_date: str | None, by) -> dict[str, Any]:
    et = (entry_type or "").upper()
    if et not in _ENTRY_TYPES or int(amount) <= 0:
        raise ValueError("entry_type(LABOR/EXPENSE/UTILITY/AD/ETC)·amount(양수) 필요")
    await _ensure_acct(db)
    await db.execute(text(
        "INSERT INTO sales_site_accounting (site_id, entry_type, amount, memo, entry_date, created_by) "
        "VALUES (:s,:t,:a,:m,COALESCE(:d::date, current_date),:u)"),
        {"s": str(site_id), "t": et, "a": int(amount), "m": memo, "d": entry_date, "u": str(by) if by else None})
    await db.commit()
    return {"ok": True, "entry_type": et, "amount": int(amount)}


async def _cost_by_type(db: AsyncSession, site_id) -> dict[str, int]:
    await _ensure_acct(db)
    rows = (await db.execute(text(
        "SELECT entry_type, COALESCE(SUM(amount),0) FROM sales_site_accounting WHERE site_id=:s GROUP BY entry_type"),
        {"s": str(site_id)})).all()
    return {t: int(a) for t, a in rows}


async def _scalar(db: AsyncSession, sql: str, **p) -> int:
    try:
        r = (await db.execute(text(sql), p)).first()
        return int(r[0] or 0) if r else 0
    except Exception:  # noqa: BLE001 — 테이블 미존재/빈 경우 0(정직)
        return 0


async def site_management_detail(db: AsyncSession, site_id) -> dict[str, Any]:
    """현장 1곳의 통합 관리 지표 — 담당자·근태·계약·매출·수수료·방문·광고·회계·손익."""
    s = str(site_id)
    today = datetime.now(timezone.utc).date().isoformat()
    staff = await _scalar(db, "SELECT count(*) FROM sales_org_nodes WHERE site_id=:s AND user_id IS NOT NULL AND deleted_at IS NULL", s=s)
    contracts = await _scalar(db, "SELECT count(*) FROM sales_contracts_ext WHERE site_id=:s AND status='ACTIVE'", s=s)
    revenue = await _scalar(db, "SELECT COALESCE(SUM(total_price),0) FROM sales_contracts_ext WHERE site_id=:s AND status='ACTIVE'", s=s)
    # 수수료 이벤트엔 site_id 가 없으므로 계약(contract_ext_id)을 경유해 현장을 잇는다.
    commission = await _scalar(db,
        "SELECT COALESCE(SUM(sp.amount),0) FROM sales_commission_splits sp "
        "JOIN sales_commission_events e ON e.id=sp.event_id "
        "JOIN sales_contracts_ext c ON c.id=e.contract_ext_id WHERE c.site_id=:s", s=s)
    visitors = await _scalar(db, "SELECT count(*) FROM mh_visitors WHERE site_id=:s", s=s)
    attend_today = await _scalar(db, "SELECT count(*) FROM sales_staff_attendance WHERE site_id=:s AND check_in::date=:d::date", s=s, d=today)
    ad_budget = await _scalar(db, "SELECT COALESCE(SUM(budget),0) FROM sales_ad_campaigns WHERE site_id=:s", s=s)

    cost = await _cost_by_type(db, site_id)
    cost_total = sum(cost.values())
    # 손익(개략) = 매출 − 회계비용 − 수수료지급(배분). 매출은 계약 총액 기준.
    profit = revenue - cost_total - commission
    return {
        "site_id": s,
        "staff_assigned": staff,
        "contracts": contracts,
        "revenue": revenue,
        "commission": commission,
        "visitors": visitors,
        "attendance_today": attend_today,
        "ad_budget": ad_budget,
        "accounting": {
            "by_type": [{"type": t, "label": _ENTRY_TYPES.get(t, t), "amount": a} for t, a in sorted(cost.items())],
            "cost_total": cost_total,
        },
        "profit_estimate": profit,
        "note": "손익(개략) = 계약 매출 − 회계비용 − 수수료배분. 정밀 손익은 회계 확정분 기준.",
    }
