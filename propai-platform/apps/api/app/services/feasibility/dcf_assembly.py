"""월별 DCF 조립 공용 헬퍼 — 개략수지(rough)·상세수지(경로A /calculate) 공용 SSOT.

★감사 결함 수지5·수지7 봉합(2026-07-15, 100% 캠페인 W3):
- 경로A(/calculate)의 NPV는 `순이익/(1+r)^년` 단일기간 근사로 현금흐름 시점을 무시했다.
- 월별 DCF 조립(공사기간 근사·분양시점·자기자본비율·세금 시점주입·무차입 NPV·IRR 선택)은
  rough_feasibility_orchestrator §8에 인라인으로만 존재했다.
이 모듈이 조립 규칙의 단일 출처다 — rough는 리팩토링으로 소비(수치 무회귀),
경로A는 service.calculate가 소비해 NPV를 월별 DCF 기저로 교체하고 IRR·회수기간을 얻는다.

표준 근사(입력 미제공 시 — rough 종전 관례와 동일):
- 공사기간 = max(6, 사업기간 − 6)  (설계 3 + 정산 3 제외)
- 분양개시 = min(6, 공사기간 − 1), 분양기간 = 6개월
- 자기자본비율 = clamp(자기자본/총사업비, 0~1), 총사업비 미확보 시 엔진 기본 30%
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.feasibility.cashflow_generator import CashflowGenerator, npv_from_netflows

logger = logging.getLogger(__name__)


def payback_month(rows: list[dict[str, Any]]) -> int | None:
    """누적 현금흐름이 처음 0 이상이 되는 월(레버드 rows 기준 — 실제 자금위치)."""
    for r in rows:
        try:
            if float(r.get("cumulative") or 0) >= 0 and float(r.get("inflow") or 0) > 0:
                return int(r.get("month"))
        except (TypeError, ValueError):
            continue
    return None


def assemble_monthly_dcf(
    *,
    land_cost_won: float,
    construction_cost_won: float,
    revenue_won: float,
    project_months: int,
    equity_won: float = 0,
    discount_rate: float = 0.08,
    total_cost_won: float | None = None,
    tax_schedule: dict[str, Any] | None = None,
    construction_months: int | None = None,
    sale_start_month: int | None = None,
    sale_duration_months: int | None = None,
) -> dict[str, Any] | None:
    """월별 DCF 실행 — {cf, rows, cf_summary, npv_won, irr_pct, payback_month} 반환.

    실패·입력 불충분 시 None(호출자가 정직 강등 — 절대 raise 안 함).
    NPV는 무차입 프로젝트 FCF(세금 시점주입 시 세금 차감 스트림) 할인,
    IRR은 동일 기저(세금 주입 시 after_tax_irr_annual_pct)를 대표값으로 쓴다.
    """
    try:
        if revenue_won <= 0 or (land_cost_won + construction_cost_won) <= 0:
            return None

        cm = construction_months
        if cm is not None:
            cm = max(1, int(cm))
        else:
            cm = max(6, int(project_months) - 6)  # 설계 3 + 정산 3 제외 근사

        ss = sale_start_month
        ss = int(ss) if ss is not None else min(6, max(0, cm - 1))
        ss = max(0, min(ss, cm - 1))

        sd = sale_duration_months
        sd = max(1, int(sd)) if sd is not None else 6

        equity_ratio = (
            min(1.0, max(0.0, float(equity_won) / float(total_cost_won)))
            if total_cost_won
            else 0.3
        )

        cf = CashflowGenerator().generate_monthly_cashflow(
            land_cost=float(land_cost_won),
            construction_cost=float(construction_cost_won),
            construction_months=cm,
            total_revenue=float(revenue_won),
            sale_start_month=ss,
            sale_duration_months=sd,
            equity_ratio=equity_ratio,
            tax_schedule=tax_schedule,
        )
        rows = cf.get("rows") or []
        cf_summary = cf.get("summary") or {}
        npv_stream = cf.get("after_tax_netflows") or cf.get("unlevered_netflows") or []
        npv = npv_from_netflows(npv_stream, discount_rate)
        irr_pct = (
            cf_summary.get("after_tax_irr_annual_pct")
            if tax_schedule is not None
            else cf_summary.get("irr_annual_pct")
        )
        return {
            "cf": cf,
            "rows": rows,
            "cf_summary": cf_summary,
            "npv_won": npv,
            "irr_pct": irr_pct,
            "payback_month": payback_month(rows),
            "construction_months": cm,
            "sale_start_month": ss,
            "sale_duration_months": sd,
            "equity_ratio": equity_ratio,
        }
    except Exception as e:  # noqa: BLE001 — DCF 실패는 호출자 정직 강등(수지 본체 무손상)
        logger.warning("월별 DCF 조립 실패: %s", str(e)[:120])
        return None
