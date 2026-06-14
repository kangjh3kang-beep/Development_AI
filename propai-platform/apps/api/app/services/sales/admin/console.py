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
        "VALUES (:s,:t,:a,:m,COALESCE(CAST(:d AS date), current_date),:u)"),
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
    except Exception:  # noqa: BLE001 — 테이블 미존재/오류 시 0(정직). 트랜잭션 오염 방지 위해 롤백.
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
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
    attend_today = await _scalar(db, "SELECT count(*) FROM sales_staff_attendance WHERE site_id=:s AND check_in::date=CAST(:d AS date)", s=s, d=today)
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


# ── 급여관리(근태×단가 자동산정) ─────────────────────────────────────────────
_WAGE_TYPES = {"DAILY": "일급", "HOURLY": "시급", "MONTHLY": "월급"}
_WAGE_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_staff_wage ("
    "  staff_id uuid PRIMARY KEY,"
    "  site_id uuid NOT NULL,"
    "  wage_type varchar(10) NOT NULL DEFAULT 'DAILY',"   # DAILY/HOURLY/MONTHLY
    "  base_wage numeric(14,0) NOT NULL DEFAULT 0,"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_WAGE_READY = False


async def _ensure_wage(db: AsyncSession) -> None:
    global _WAGE_READY
    if _WAGE_READY:
        return
    await db.execute(text(_WAGE_DDL))
    await db.commit()
    _WAGE_READY = True


def _month_bounds(ym: str) -> tuple[str, str]:
    """'YYYY-MM' → (이달1일, 다음달1일) ISO 문자열."""
    y, m = int(ym[:4]), int(ym[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-01", f"{ny:04d}-{nm:02d}-01"


async def set_staff_wage(db: AsyncSession, site_id, staff_id, wage_type: str, base_wage: int) -> dict[str, Any]:
    wt = (wage_type or "").upper()
    if wt not in _WAGE_TYPES or int(base_wage) < 0:
        raise ValueError("wage_type(DAILY/HOURLY/MONTHLY)·base_wage(0 이상) 필요")
    await _ensure_wage(db)
    await db.execute(text(
        "INSERT INTO sales_staff_wage (staff_id, site_id, wage_type, base_wage, updated_at) "
        "VALUES (:st,:s,:wt,:w, now()) "
        "ON CONFLICT (staff_id) DO UPDATE SET wage_type=:wt, base_wage=:w, updated_at=now()"),
        {"st": str(staff_id), "s": str(site_id), "wt": wt, "w": int(base_wage)})
    await db.commit()
    return {"ok": True, "staff_id": str(staff_id), "wage_type": wt, "base_wage": int(base_wage)}


async def compute_payroll(db: AsyncSession, site_id, ym: str) -> dict[str, Any]:
    """현장 직원별 급여 자동산정 — 근태(출근일수·근무분) × 단가. 회계 인건비 후보."""
    await _ensure_wage(db)
    start, end = _month_bounds(ym)
    s = str(site_id)
    rows = (await db.execute(text(
        "SELECT s.id, s.name, s.position, "
        "  count(distinct a.check_in::date) AS days, "
        "  COALESCE(sum(a.work_minutes),0) AS minutes "
        "FROM sales_staff s "
        "LEFT JOIN sales_staff_attendance a ON a.staff_id=s.id "
        "  AND a.check_in >= CAST(:start AS date) AND a.check_in < CAST(:end AS date) "
        "WHERE s.site_id=:s AND s.deleted_at IS NULL AND s.status='ACTIVE' "
        "GROUP BY s.id, s.name, s.position ORDER BY s.name"),
        {"s": s, "start": start, "end": end})).all()
    wages = {str(k): (wt, int(w)) for k, wt, w in (await db.execute(text(
        "SELECT staff_id, wage_type, base_wage FROM sales_staff_wage WHERE site_id=:s"), {"s": s})).all()}
    staff = []
    total = 0
    for sid, name, pos, days, minutes in rows:
        wt, base = wages.get(str(sid), ("DAILY", 0))
        hours = round(int(minutes) / 60)
        if wt == "HOURLY":
            amount = hours * base
        elif wt == "MONTHLY":
            amount = base if int(days) > 0 else 0  # 무출근이면 미지급
        else:  # DAILY
            amount = int(days) * base
        total += amount
        staff.append({
            "staff_id": str(sid), "name": name or "-", "position": pos,
            "days": int(days), "hours": hours,
            "wage_type": wt, "wage_label": _WAGE_TYPES.get(wt, wt), "base_wage": base,
            "amount": amount, "wage_set": str(sid) in wages,
        })
    return {"year_month": ym, "staff": staff, "headcount": len(staff),
            "total_payroll": total,
            "note": "급여=근태×단가(일급:출근일수·시급:근무시간·월급:출근시 정액). 미설정 단가는 0."}


async def post_payroll_to_accounting(db: AsyncSession, site_id, ym: str, by) -> dict[str, Any]:
    """산정 급여 총액을 회계 인건비(LABOR)로 자동전기 — 동일 월 중복전기 방지(멱등)."""
    pr = await compute_payroll(db, site_id, ym)
    total = int(pr["total_payroll"])
    if total <= 0:
        return {"ok": False, "reason": "산정 급여가 0원입니다(단가·근태 확인)."}
    await _ensure_acct(db)
    memo = f"급여 {ym} 자동전기"
    dup = (await db.execute(text(
        "SELECT count(*) FROM sales_site_accounting WHERE site_id=:s AND entry_type='LABOR' AND memo=:m"),
        {"s": str(site_id), "m": memo})).first()
    if dup and int(dup[0] or 0) > 0:
        return {"ok": False, "reason": f"{ym} 급여는 이미 전기되었습니다.", "total": total}
    await add_accounting_entry(db, site_id, "LABOR", total, memo, f"{ym}-01", by)
    return {"ok": True, "posted": total, "year_month": ym, "memo": memo}


# ── 광고집행 ROI(집행비 대비 집객·계약 효율) ─────────────────────────────────
async def ad_roi(db: AsyncSession, site_id) -> dict[str, Any]:
    """광고 집행비(예산/실집행) 대비 집객(방문·리드)·계약 효율 = 단가 산출."""
    s = str(site_id)
    budget = await _scalar(db, "SELECT COALESCE(SUM(budget),0) FROM sales_ad_campaigns WHERE site_id=:s", s=s)
    spend = await _scalar(db, "SELECT COALESCE(SUM(amount),0) FROM sales_ad_spend WHERE site_id=:s", s=s)
    leads = await _scalar(db, "SELECT count(*) FROM sales_ad_leads WHERE site_id=:s", s=s)
    visitors = await _scalar(db, "SELECT count(*) FROM mh_visitors WHERE site_id=:s", s=s)
    contracts = await _scalar(db, "SELECT count(*) FROM sales_contracts_ext WHERE site_id=:s AND status='ACTIVE'", s=s)
    eff = spend or budget  # 실집행 우선, 없으면 예산 기준
    return {
        "budget": budget, "spend": spend, "leads": leads, "visitors": visitors, "contracts": contracts,
        "cost_per_lead": round(eff / leads) if leads else 0,
        "cost_per_visitor": round(eff / visitors) if visitors else 0,
        "cost_per_contract": round(eff / contracts) if contracts else 0,
        "note": "단가=실집행비(없으면 예산)÷각 성과수. 광고 집행비는 회계 광고비(AD)로 전기 가능.",
    }
