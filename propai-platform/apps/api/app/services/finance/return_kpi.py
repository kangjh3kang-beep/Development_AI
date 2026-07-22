"""수익 KPI 완성 — MOIC·Equity IRR·LTV/LTC·break-even·RLV·covenant 경고 (W3-1, GAP_v4 P10).

★스파이크 확증(2026-07-23): 수지·금융 엔진(cashflow_generator·dcf_assembly)에는 월별
부채 waterfall(브릿지/PF 잔액·이자·상환)과 무차입 프로젝트 IRR/NPV가 이미 실장돼 있으나,
은행 심사용 KPI(MOIC·Equity IRR·LTV/LTC 시계열·break-even·RLV·covenant 경고)는 어떤
명칭 변형(multiple·자기자본수익률·담보비율 등)으로도 존재하지 않았다(전역 grep 재확증).

설계 원칙(재계산 금지 — 기존 waterfall 위 파생만):
- MOIC·Equity IRR·LTV/LTC 시계열은 assemble_monthly_dcf()가 이미 산출한 rows·summary만
  읽어 파생한다(월별 S-커브·이자·분양 스케줄을 다시 조립하지 않음).
- break-even(분양가/분양률/공사비)·RLV(잔여토지가치)만 예외적으로 assemble_monthly_dcf를
  '블랙박스 NPV 함수'로 재호출한다 — 새 현금흐름 산식을 만드는 게 아니라, 이미 검증된
  동일 엔진에 입력 하나만 바꿔가며 이분법으로 NPV=0 지점을 탐색하는 것(스펙이 명시적으로
  요구하는 방식: "다른 변수 고정 시 NPV=0 되는 값·이분법 탐색·수렴 기록").
- 미산정 입력(자기자본 0 등)은 해당 KPI만 null+사유로 정직 강등한다(절대 raise·날조 없음).
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.feasibility.cashflow_generator import irr_annual_pct_from_netflows
from app.services.feasibility.dcf_assembly import assemble_monthly_dcf

logger = logging.getLogger(__name__)

# ★covenant LTV 임계 기본값 — 갭문서 지적 "LTV 70% 하드코딩" 잔존 위치 실측:
#   app/services/feasibility/modules/common/cost_blocks.py의 PF 자동추정 비율(_STANDARD_PF_LTC_RATIO
#   =0.70, 동일 업계 관행치)과 정합. 그 상수는 '금융비 자동추정용 LTC 가정'이고 이 값은
#   '월별 LTV 시계열의 covenant 경고 임계'로 용도는 다르나, 같은 관행 수치(65~75% 대역
#   대표치)라 하드코딩을 반복하지 않고 여기 하나의 명명 상수로 고정한다. 파라미터로
#   주입 가능(호출자가 실제 대주 term sheet 값으로 교체) — 기본값은 이 상수 그대로.
DEFAULT_LTV_COVENANT_THRESHOLD_PCT = 70.0

# 이분법 탐색 파라미터(공용) — break-even·RLV 공용.
_MAX_BRACKET_EXPANSIONS = 60
_MAX_BISECTIONS = 100
_NPV_TOLERANCE_WON = 1.0  # 이 이내면 '수렴'으로 간주(원 단위 반올림 오차 흡수)


def _bisect_for_zero(
    evaluate: Any,
    x0: float,
    *,
    increasing: bool,
) -> dict[str, Any]:
    """단조함수 evaluate(x)=NPV(x)의 근을 이분법으로 탐색(수렴 기록 포함, 순수 파이썬).

    Args:
        evaluate: x(원화 금액)를 받아 NPV(원) 또는 None(산출 실패)을 반환하는 함수.
        x0: 탐색 시작점(현재 시나리오의 원래 값 — 반드시 0 초과).
        increasing: True면 x가 커질수록 NPV가 커지는 관계(예: 분양수입→NPV).
            False면 x가 커질수록 NPV가 작아지는 관계(예: 공사비·토지비→NPV).

    Returns:
        {"value": 근사근(원, None=탐색실패), "converged": bool, "iterations": int,
         "npv_at_value": 근에서의 잔여 NPV, "reason": 실패 시 사유}
    """
    if x0 is None or x0 <= 0:
        return {"value": None, "converged": False, "iterations": 0,
                "reason": "탐색 기준값이 0 이하 — 이분법 시작 불가"}
    f0 = evaluate(x0)
    if f0 is None:
        return {"value": None, "converged": False, "iterations": 0,
                "reason": "기준 시나리오 NPV 산출 실패"}
    if abs(f0) <= _NPV_TOLERANCE_WON:
        return {"value": round(x0), "converged": True, "iterations": 0, "npv_at_value": round(f0)}

    # NPV를 0으로 옮기려면 x를 늘려야 하는지(need_up) 판정.
    need_up = (f0 < 0) if increasing else (f0 > 0)

    lo, hi = x0, x0
    f_lo, f_hi = f0, f0
    # ★하향 탐색(need_up=False)은 0이 하한이라 첫 스텝이 x0 전체면 곧바로 바닥(0)에
    #   닿아버려 유효 구간(revenue_won>0 등 엔진 제약)을 벗어난다 — 초기 스텝을 10%로
    #   촘촘히 잡아 바닥 도달 전에 부호변화 구간을 찾을 여지를 준다(상향은 무제한이라 무관).
    step = x0 * 0.1
    bracketed = False
    expansions = 0
    for _ in range(_MAX_BRACKET_EXPANSIONS):
        expansions += 1
        if need_up:
            hi = hi + step
            f_hi = evaluate(hi)
            if f_hi is None:
                return {"value": None, "converged": False, "iterations": expansions,
                        "reason": "구간 확장 중 NPV 산출 실패"}
            if (f_hi >= 0) != (f0 >= 0):
                bracketed = True
                break
        else:
            # 바닥을 정확히 0이 아니라 x0의 백만분의 1로 잡는다 — assemble_monthly_dcf가
            # revenue_won<=0 등을 '입력 불충분'으로 거부하므로 정확히 0은 평가 자체가 실패.
            floor = x0 * 1e-6
            new_lo = max(floor, lo - step)
            if new_lo == lo:  # 바닥에 닿았는데도 부호변화 없음 — 더 확장 불가
                break
            lo = new_lo
            f_lo = evaluate(lo)
            if f_lo is None:
                return {"value": None, "converged": False, "iterations": expansions,
                        "reason": "구간 확장 중 NPV 산출 실패"}
            if (f_lo >= 0) != (f0 >= 0):
                bracketed = True
                break
        step *= 1.5
    if not bracketed:
        return {"value": None, "converged": False, "iterations": expansions,
                "reason": f"{_MAX_BRACKET_EXPANSIONS}회 확장 내 부호변화 구간 확보 실패(단조성 가정 밖 가능성)"}

    a, b = (x0, hi) if need_up else (lo, x0)
    fa = f0 if need_up else f_lo
    iterations = 0
    mid, fm = a, fa
    for i in range(_MAX_BISECTIONS):
        iterations = i + 1
        mid = (a + b) / 2
        fm = evaluate(mid)
        if fm is None:
            return {"value": None, "converged": False, "iterations": iterations,
                    "reason": "이분법 중 NPV 산출 실패"}
        if abs(fm) <= _NPV_TOLERANCE_WON or (b - a) < max(1.0, x0 * 1e-6):
            return {"value": round(mid), "converged": True, "iterations": iterations,
                    "npv_at_value": round(fm)}
        if (fm >= 0) == (fa >= 0):
            a, fa = mid, fm
        else:
            b = mid
    return {"value": round(mid), "converged": False, "iterations": iterations,
            "npv_at_value": round(fm), "reason": f"최대반복({_MAX_BISECTIONS}) 도달 — 근사치"}


def _resolve_equity_cash_flow(
    dcf: dict[str, Any], *, land_cost_won: float,
) -> tuple[list[float], dict[str, Any]] | None:
    """dcf(assemble_monthly_dcf 결과)에서 레버드 자기자본 현금흐름을 파생한다(재계산 0).

    cashflow_generator.generate_monthly_cashflow의 자금투입 규칙(월0=토지분 자기자본,
    착공월=시공분 자기자본 추가투입)을 그대로 재현하되, 이미 계산된 equity_ratio·
    equity_amount(cf_summary)만 곱셈으로 나눠 쓴다 — 새 가정 0.
    최종 회수는 마지막 행의 누적현금(rows[-1]['cumulative'])을 그대로 읽는다: 이는
    net_profit + equity_in_total과 항등(부채가 정산월+2까지 전액 상환되는 모델 불변식)이라
    '자기자본 반환 + 이익'을 한 시점(정산 종료)에 일괄 회수하는 표준 근사로 쓸 수 있다.

    Returns:
        (equity_cf, detail) 또는 None(필수 입력 결측 — 정직 강등).
    """
    cf = dcf.get("cf") or {}
    rows = dcf.get("rows") or cf.get("rows") or []
    cf_summary = dcf.get("cf_summary") or cf.get("summary") or {}
    phases = cf.get("phases") or {}
    equity_ratio = dcf.get("equity_ratio")
    equity_amount = cf_summary.get("equity_amount")
    total_months = cf_summary.get("total_months")
    construction_start = (phases.get("construction") or {}).get("start")

    if not rows or equity_ratio is None or equity_amount is None or not total_months or construction_start is None:
        return None

    equity_for_land = float(land_cost_won) * float(equity_ratio)
    equity_remaining = float(equity_amount) - equity_for_land
    equity_in_total = equity_for_land + equity_remaining
    if equity_in_total <= 0:
        return None  # 자기자본 투입 0(전액 타인자본 가정 등) — MOIC/Equity IRR 정의 불가

    n = int(total_months)
    equity_cf = [0.0] * n
    equity_cf[0] -= equity_for_land
    cs_idx = min(max(0, int(construction_start)), n - 1)
    equity_cf[cs_idx] -= equity_remaining
    final_cash = float(rows[-1].get("cumulative") or 0)
    equity_cf[n - 1] += final_cash

    detail = {
        "equity_for_land_won": round(equity_for_land),
        "equity_remaining_won": round(equity_remaining),
        "equity_in_total_won": round(equity_in_total),
        "final_distribution_won": round(final_cash),
        "final_distribution_month": n - 1,
        "construction_start_month": cs_idx,
    }
    return equity_cf, detail


def compute_moic_and_equity_irr(
    dcf: dict[str, Any], *, land_cost_won: float,
) -> dict[str, Any]:
    """MOIC(투하자본배수)·Equity IRR — 레버드 자기자본 현금흐름 파생(재계산 0).

    MOIC = 총 equity 유입(최종 일괄회수 — 자본반환+이익) ÷ 총 equity 투입(토지+시공 시점).
    Equity IRR = 위 3개 시점(월0 투입·착공월 투입·최종월 회수) 현금흐름의 연환산 IRR —
    프로젝트 IRR과 동일한 이분법 산식(irr_annual_pct_from_netflows)을 재사용한다(신규 IRR
    알고리즘 0). 월→연 환산은 (1+월IRR)^12−1 관례(cashflow_generator와 동일).

    Returns:
        {"moic": {...} | None, "equity_irr_pct": {...} | None, "degraded_notes": [...]}
    """
    notes: list[str] = []
    resolved = _resolve_equity_cash_flow(dcf, land_cost_won=land_cost_won)
    if resolved is None:
        notes.append("MOIC·Equity IRR 미산출 — 자기자본 투입액 결측 또는 0(전액 타인자본 가정 등).")
        return {"moic": None, "equity_irr_pct": None, "degraded_notes": notes}

    equity_cf, detail = resolved
    equity_in_total = detail["equity_in_total_won"]
    final_distribution = detail["final_distribution_won"]

    moic_value = round(final_distribution / equity_in_total, 3) if equity_in_total > 0 else None
    moic = None
    if moic_value is not None:
        moic = {
            "value": moic_value,
            "basis": (
                "MOIC = 총 equity 유입(최종 잔존현금 — 자본반환+순이익, 부채 전액상환 후 일괄회수 "
                f"가정) {final_distribution:,.0f}원 ÷ 총 equity 투입(토지+시공 시점) "
                f"{equity_in_total:,.0f}원"
            ),
        }

    irr_pct = irr_annual_pct_from_netflows(equity_cf)
    equity_irr = None
    if irr_pct is not None:
        equity_irr = {
            "value_pct": irr_pct,
            "cash_flow_won": {
                "month_0": -detail["equity_for_land_won"],
                f"month_{detail['construction_start_month']}": -detail["equity_remaining_won"],
                f"month_{detail['final_distribution_month']}": detail["final_distribution_won"],
            },
            "basis": (
                "레버드 equity 현금흐름(토지분·시공분 자기자본 투입 2회 유출 + 정산 종료 시 "
                "잔존현금 1회 일괄 유입)의 연환산 IRR — 프로젝트 IRR과 동일 이분법 산식 재사용"
            ),
        }
    else:
        notes.append("Equity IRR 미산출 — 자기자본 현금흐름에 부호 변화가 없어 IRR 정의 불가.")

    return {"moic": moic, "equity_irr_pct": equity_irr, "degraded_notes": notes}


def compute_ltv_ltc_series(
    dcf: dict[str, Any],
    *,
    total_cost_won: float | None,
    collateral_value_won: float | None,
    gdv_fallback_won: float | None = None,
    ltv_covenant_threshold_pct: float = DEFAULT_LTV_COVENANT_THRESHOLD_PCT,
) -> dict[str, Any]:
    """월별 LTV(대출잔액÷담보가치)·LTC(대출잔액÷총사업비) 시계열 + covenant 경고.

    대출잔액은 rows의 outstanding_bridge+outstanding_pf(엔진이 이미 계산한 잔액 — 재계산
    아님)를 그대로 합산한다. 담보가치(LTV 분모)는 collateral_value_won(감정평가 등 실제값)이
    없으면 gdv_fallback_won(보통 총분양수입=GDV)을 관행적 근사로 쓴다(개발금융에서 흔한
    대리치 — 어느 쪽을 썼는지 collateral_basis에 정직 고지). 총사업비(LTC 분모)는 고정값.

    covenant 경고: LTV가 threshold_pct를 초과하는 월만 나열(경고만 — 대출 조기상환 등의
    시뮬레이션은 하지 않음).

    Returns:
        {"series": [...], "peak_ltv_pct": .., "peak_ltc_pct": .., "covenant": {...},
         "collateral_basis": str, "degraded_notes": [...]}
    """
    notes: list[str] = []
    cf = dcf.get("cf") or {}
    rows = dcf.get("rows") or cf.get("rows") or []
    if not rows:
        return {"series": [], "peak_ltv_pct": None, "peak_ltc_pct": None,
                "covenant": None, "collateral_basis": None,
                "degraded_notes": ["월별 현금흐름 rows 결측 — LTV/LTC 산출 불가."]}

    ltc_denominator = float(total_cost_won) if total_cost_won and total_cost_won > 0 else None
    if ltc_denominator is None:
        notes.append("LTC 미산출 — 총사업비 결측(0 이하).")

    collateral_basis: str | None = None
    ltv_denominator: float | None = None
    if collateral_value_won and collateral_value_won > 0:
        ltv_denominator = float(collateral_value_won)
        collateral_basis = "담보가치=사용자/호출자 제공값(감정평가 등)"
    elif gdv_fallback_won and gdv_fallback_won > 0:
        ltv_denominator = float(gdv_fallback_won)
        collateral_basis = "담보가치=총분양수입(GDV) 관행적 근사(실감정 아님 — 별도 감정평가 미제공)"
        notes.append("담보가치 미제공 — 총분양수입(GDV)을 관행적 근사로 대체(실감정 아님).")
    else:
        notes.append("담보가치·GDV 모두 결측 — LTV 시계열 산출 불가(LTC만 산출).")

    series: list[dict[str, Any]] = []
    peak_ltv = None
    peak_ltc = None
    for r in rows:
        debt = float(r.get("outstanding_bridge") or 0) + float(r.get("outstanding_pf") or 0)
        ltc_pct = round(debt / ltc_denominator * 100, 2) if ltc_denominator else None
        ltv_pct = round(debt / ltv_denominator * 100, 2) if ltv_denominator else None
        series.append({
            "month": r.get("month"), "outstanding_debt_won": round(debt),
            "ltc_pct": ltc_pct, "ltv_pct": ltv_pct,
        })
        if ltc_pct is not None:
            peak_ltc = ltc_pct if peak_ltc is None else max(peak_ltc, ltc_pct)
        if ltv_pct is not None:
            peak_ltv = ltv_pct if peak_ltv is None else max(peak_ltv, ltv_pct)

    covenant: dict[str, Any] | None = None
    if ltv_denominator is not None:
        breaches = [
            {"month": s["month"], "ltv_pct": s["ltv_pct"]}
            for s in series
            if s["ltv_pct"] is not None and s["ltv_pct"] > ltv_covenant_threshold_pct
        ]
        covenant = {
            "threshold_pct": ltv_covenant_threshold_pct,
            "breach_months": breaches,
            "breach_count": len(breaches),
            "basis": f"LTV > {ltv_covenant_threshold_pct:.0f}% 초과 월 나열(경고용 — 대출 조기상환 시뮬레이션 아님)",
        }
    else:
        notes.append("covenant 경고 미산출 — LTV 분모(담보가치) 결측으로 LTV 시계열 자체가 없음.")

    return {
        "series": series, "peak_ltv_pct": peak_ltv, "peak_ltc_pct": peak_ltc,
        "covenant": covenant, "collateral_basis": collateral_basis,
        "degraded_notes": notes,
    }


def detect_multiple_irr_risk(dcf: dict[str, Any]) -> dict[str, Any]:
    """복수 IRR 가능성 검출 — 프로젝트 IRR에 쓰인 현금흐름의 부호 변화 횟수(Descartes 규칙).

    부호 변화가 1회(전형적 유출→유입)를 넘으면 복수 근(복수 IRR) 가능성이 있다는
    '경고'만 낸다 — 실제 추가 IRR 값을 계산/추정하지 않는다(날조 금지).
    """
    cf = dcf.get("cf") or {}
    netflows = cf.get("after_tax_netflows") or cf.get("unlevered_netflows") or []
    signs = [1 if v > 0 else (-1 if v < 0 else 0) for v in netflows if v]
    sign_changes = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
    flagged = sign_changes >= 2
    return {
        "flagged": flagged,
        "sign_changes": sign_changes,
        "basis": (
            "프로젝트 현금흐름 부호 변화 횟수(Descartes 규칙) — 2회 이상이면 복수 IRR 근 존재 "
            "가능성 경고(추가 근을 계산하지 않음, 경고 전용)"
        ),
    }


def check_ledger_invariants(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """월별 잔액 불변식 검증 — opening+inflow-outflow=closing(전건) + 대출잔액 비음수.

    P10 게이트("월별 잔액 불변식 100%") 대상은 cashflow_generator가 이미 산출한 rows다
    (재계산이 아니라 자기정합성 검증). 위반이 있어도 이 함수는 표기만 하고 raise하지 않는다
    (엔진 자체 수정은 이 티켓 스코프 밖 — 발견 시 별도 결함으로 보고).
    """
    violations: list[dict[str, Any]] = []
    prev_cumulative = 0.0
    for r in rows:
        month = r.get("month")
        inflow = float(r.get("inflow") or 0)
        outflow = float(r.get("outflow") or 0)
        net = float(r.get("net") or 0)
        cumulative = float(r.get("cumulative") or 0)
        if abs((inflow - outflow) - net) > 1:
            violations.append({"month": month, "type": "net!=inflow-outflow",
                                "expected": round(inflow - outflow), "actual": round(net)})
        if abs((prev_cumulative + net) - cumulative) > 1:
            violations.append({"month": month, "type": "closing!=opening+net",
                                "expected": round(prev_cumulative + net), "actual": round(cumulative)})
        if float(r.get("outstanding_bridge") or 0) < -1 or float(r.get("outstanding_pf") or 0) < -1:
            violations.append({"month": month, "type": "negative_loan_balance",
                                "outstanding_bridge": r.get("outstanding_bridge"),
                                "outstanding_pf": r.get("outstanding_pf")})
        prev_cumulative = cumulative
    return {"ok": not violations, "violations": violations, "rows_checked": len(rows)}


def compute_break_even_and_rlv(
    dcf: dict[str, Any],
    *,
    land_cost_won: float,
    construction_cost_won: float,
    revenue_won: float,
    discount_rate: float,
    total_cost_won: float | None,
    soft_cost_won: float | None,
    tax_schedule: dict[str, Any] | None,
) -> dict[str, Any]:
    """break-even 3종(분양가·분양률·공사비) + RLV(잔여토지가치) — 동일 dcf 엔진 이분법 재호출.

    ★한계(정직 명시): tax_schedule의 절대 금액(세금·부담금)은 원 시나리오 값 그대로 고정한다
    (분양가·공사비 변동에 따른 재산정은 이번 스코프에 없음 — 실제로는 부가세 등 일부가
    가격에 연동되나, 이 엔진은 세금 시점주입을 절대금액으로만 받는다).
    ★분양가 vs 분양률: 이 엔진은 총분양수입 단일 라인만 모델링해 단가×물량을 분리하지
    않는다. 두 손익분기 모두 '총분양수입에 곱하는 배율'로 산출되어 수치가 동일하다 —
    허위로 별도 계산을 만들지 않고 이 한계를 그대로 고지한다.
    """
    cf = dcf.get("cf") or {}
    construction_months = dcf.get("construction_months")
    sale_start_month = dcf.get("sale_start_month")
    sale_duration_months = dcf.get("sale_duration_months")
    resolved_project_months = int((dcf.get("cf_summary") or cf.get("summary") or {}).get("total_months") or 36)

    if construction_months is None or sale_start_month is None or sale_duration_months is None:
        reason = "손익분기·RLV 미산출 — dcf 조립 파라미터(construction_months 등) 결측."
        return {
            "break_even": {"sale_price": None, "sales_rate": None, "construction_cost": None},
            "rlv": None, "degraded_notes": [reason],
        }

    def _npv_at(*, land: float, construction: float, revenue: float) -> float | None:
        res = assemble_monthly_dcf(
            land_cost_won=land, construction_cost_won=construction, revenue_won=revenue,
            project_months=resolved_project_months,
            equity_won=0.0,  # ★NPV는 무차입 기저라 equity_won 무관(dcf_assembly와 동일 계약)
            discount_rate=discount_rate, total_cost_won=total_cost_won,
            soft_cost_won=soft_cost_won, tax_schedule=tax_schedule,
            construction_months=construction_months, sale_start_month=sale_start_month,
            sale_duration_months=sale_duration_months,
        )
        return res["npv_won"] if res else None

    notes: list[str] = []

    # ── break-even 분양가(=분양수입 배율) ──
    revenue_solve = _bisect_for_zero(
        lambda x: _npv_at(land=land_cost_won, construction=construction_cost_won, revenue=x),
        revenue_won, increasing=True,
    )
    if revenue_solve.get("value") is None:
        notes.append(f"손익분기 분양가 미수렴: {revenue_solve.get('reason', '알 수 없음')}")
    price_pct_of_base = (
        round(revenue_solve["value"] / revenue_won * 100, 2)
        if revenue_solve.get("value") and revenue_won > 0 else None
    )
    sale_price_be = {
        "break_even_revenue_won": revenue_solve.get("value"),
        "pct_of_assumed_revenue": price_pct_of_base,
        "converged": revenue_solve.get("converged", False),
        "iterations": revenue_solve.get("iterations", 0),
        "basis": "다른 변수 고정 시 NPV=0이 되는 총분양수입(분양가 단가는 이 배율만큼 동일 변동 가정)",
    }
    sales_rate_be = {
        "break_even_sales_rate_pct": price_pct_of_base,
        "converged": revenue_solve.get("converged", False),
        "iterations": revenue_solve.get("iterations", 0),
        "basis": (
            "손익분기 분양률 — 이 엔진은 단가·물량을 분리 모델링하지 않아 분양가 손익분기와 "
            "동일한 총분양수입 배율로 산출됨(한계 명시, 허위 별도계산 아님)"
        ),
    }

    # ── break-even 공사비 ──
    cost_solve = _bisect_for_zero(
        lambda x: _npv_at(land=land_cost_won, construction=x, revenue=revenue_won),
        construction_cost_won, increasing=False,
    )
    if cost_solve.get("value") is None:
        notes.append(f"손익분기 공사비 미수렴: {cost_solve.get('reason', '알 수 없음')}")
    construction_be = {
        "break_even_construction_cost_won": cost_solve.get("value"),
        "pct_of_assumed_cost": (
            round(cost_solve["value"] / construction_cost_won * 100, 2)
            if cost_solve.get("value") and construction_cost_won > 0 else None
        ),
        "converged": cost_solve.get("converged", False),
        "iterations": cost_solve.get("iterations", 0),
        "basis": "다른 변수 고정 시 NPV=0이 되는 총공사비(이 이상이면 적자 전환)",
    }

    # ── RLV(잔여토지가치) — 목표수익(=discount_rate 요구수익률) 달성 전제 최대 토지비 ──
    # 정의: NPV(토지비=RLV)=0 — 즉 RLV는 "요구수익률(discount_rate)을 정확히 충족하는
    # 최대 지불가능 토지가"(토지잔여법 표준 정의와 동일). 그 이상 지불하면 요구수익 미달.
    land_solve = _bisect_for_zero(
        lambda x: _npv_at(land=x, construction=construction_cost_won, revenue=revenue_won),
        land_cost_won, increasing=False,
    )
    if land_solve.get("value") is None:
        notes.append(f"RLV 미수렴: {land_solve.get('reason', '알 수 없음')}")
    rlv = {
        "residual_land_value_won": land_solve.get("value"),
        "converged": land_solve.get("converged", False),
        "iterations": land_solve.get("iterations", 0),
        "target_return_pct": round(discount_rate * 100, 2),
        "basis": (
            f"목표수익률(할인율 {discount_rate:.1%}) 달성 전제 최대 토지비 — "
            "NPV(토지비=RLV)=0(토지잔여법 표준 정의, 요구수익 초과분은 전부 토지가에 귀속 가정)"
        ),
    }

    return {
        "break_even": {"sale_price": sale_price_be, "sales_rate": sales_rate_be,
                        "construction_cost": construction_be},
        "rlv": rlv, "degraded_notes": notes,
    }


def compute_return_kpi(
    *,
    dcf: dict[str, Any] | None,
    land_cost_won: float,
    construction_cost_won: float,
    revenue_won: float,
    discount_rate: float,
    total_cost_won: float | None = None,
    soft_cost_won: float | None = None,
    tax_schedule: dict[str, Any] | None = None,
    collateral_value_won: float | None = None,
    ltv_covenant_threshold_pct: float = DEFAULT_LTV_COVENANT_THRESHOLD_PCT,
) -> dict[str, Any] | None:
    """수익 KPI 일괄 산출 — MOIC·Equity IRR·LTV/LTC·break-even·RLV·covenant·불변식.

    Args:
        dcf: assemble_monthly_dcf()의 반환값(None이면 이 함수도 None — 상위 DCF 실패 그대로 전파).
        collateral_value_won: LTV 분모(담보가치). 미제공 시 revenue_won(GDV)을 관행적 근사로
            사용하고 그 사실을 basis에 정직 고지한다(실감정 아님).
        ltv_covenant_threshold_pct: covenant 경고 임계(기본 70% — cost_blocks.py의 표준
            PF LTC 관행치와 동일 대역, 파라미터로 교체 가능).

    Returns:
        None(dcf 실패 전파) 또는 {moic, equity_irr_pct, ltv_ltc, multiple_irr_warning,
        break_even, rlv, ledger_invariants, degraded_notes}
    """
    if not dcf:
        return None

    degraded: list[str] = []

    moic_irr = compute_moic_and_equity_irr(dcf, land_cost_won=land_cost_won)
    degraded.extend(moic_irr["degraded_notes"])

    ltv_ltc = compute_ltv_ltc_series(
        dcf, total_cost_won=total_cost_won,
        collateral_value_won=collateral_value_won,
        gdv_fallback_won=revenue_won if revenue_won > 0 else None,
        ltv_covenant_threshold_pct=ltv_covenant_threshold_pct,
    )
    degraded.extend(ltv_ltc["degraded_notes"])

    multiple_irr = detect_multiple_irr_risk(dcf)

    cf = dcf.get("cf") or {}
    rows = dcf.get("rows") or cf.get("rows") or []
    invariants = check_ledger_invariants(rows)
    if not invariants["ok"]:
        degraded.append(f"월별 잔액 불변식 위반 {len(invariants['violations'])}건 검출(엔진 결함 가능성 — 별도 보고 필요).")

    be_rlv = compute_break_even_and_rlv(
        dcf, land_cost_won=land_cost_won, construction_cost_won=construction_cost_won,
        revenue_won=revenue_won, discount_rate=discount_rate, total_cost_won=total_cost_won,
        soft_cost_won=soft_cost_won, tax_schedule=tax_schedule,
    )
    degraded.extend(be_rlv["degraded_notes"])

    return {
        "moic": moic_irr["moic"],
        "equity_irr_pct": moic_irr["equity_irr_pct"],
        "ltv_ltc": {
            "series": ltv_ltc["series"], "peak_ltv_pct": ltv_ltc["peak_ltv_pct"],
            "peak_ltc_pct": ltv_ltc["peak_ltc_pct"], "collateral_basis": ltv_ltc["collateral_basis"],
        },
        "covenant": ltv_ltc["covenant"],
        "multiple_irr_warning": multiple_irr,
        "break_even": be_rlv["break_even"],
        "rlv": be_rlv["rlv"],
        "ledger_invariants": invariants,
        "degraded_notes": degraded,
    }
