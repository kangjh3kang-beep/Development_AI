"""P4 T2 — 설계변경 예측공사비.

design_change_predictor(D3, 착공 전 설계변경 리스크 사전예측)의 결과를 공종(WB) 단위
공사비 delta 시나리오로 변환하고, 항상(리스크 유무와 무관하게) 몬테카를로 추가공사비
밴드(p10/50/90)를 함께 낸다.

무날조 원칙:
  - 시나리오 크기(±%)는 새 수치를 만들지 않고 design_change_predictor 자체 상수
    (_DESIGN_CHG_TYPICAL_PCT=5%, _DESIGN_CHG_MAX_PCT=15% — est_impact 문구에 이미 쓰이는 값)를
    그대로 가져온다.
  - 리스크 item이 사전예측 모듈에서 실제로 수치(±%)를 언급하지 않는 항목(예: "확인 필요"류
    정성 경고, "주차대수 미계획"처럼 %없이 "대폭 증가"로만 서술된 항목)은 시나리오화하지 않고
    data_gaps에 사유를 정직 기록한다(수치 발명 금지).
  - 시나리오별 delta는 alternatives_engine이 산정한 실제 BOQ 항목 금액(wb_code로 집계)에
    ±% 를 적용한 값이다 — 임의의 총액 비율이 아니라 실제 해당 공종의 base 금액 기준.
"""

from __future__ import annotations

from typing import Any

from app.services.cost.alternatives_engine import build_boq_for_params, merge_params
from app.services.cost.cost_monte_carlo import CostMonteCarlo
from app.services.cost.work_breakdown import WB_CATEGORIES

# design_change_predictor의 실제 상수를 재사용(신규 수치 발명 금지).
try:
    from app.services.design_risk.design_change_predictor import (
        _DESIGN_CHG_MAX_PCT as _MAX_PCT,
    )
    from app.services.design_risk.design_change_predictor import (
        _DESIGN_CHG_TYPICAL_PCT as _TYPICAL_PCT,
    )
except Exception:  # noqa: BLE001 — 모듈 재구성 등으로 import 실패해도 MC 밴드는 항상 동작해야 함.
    _TYPICAL_PCT, _MAX_PCT = 5, 15

# 리스크 item(design_change_predictor 실코드 값, grep 확인) → 영향 WB 목록.
# est_impact에 수치(±%)가 실제로 언급되는 high 심각도 항목만 대상(정성 경고뿐인 항목은 스킵).
#   - 건폐율/용적률/높이 초과 → 면적·층수 축소 재설계는 골조(WB04) 물량에 직접 반영.
# ★실코드 확인(무날조): build_boq가 만드는 BOQ 항목은 표준물량 8공종(01~08)뿐이고, 이를 WB로
#   묶는 work_breakdown._NUMERIC_BRIDGE는 WB04/05/06/07/10/11 여섯 개만 실제로 채워진다
#   (WB02 토공사·WB03 지정기초공사는 이 BOQ 엔진에 대응 라인이 아예 없어 base 금액이 항상 0).
#   "법정주차 부족"(주차층 추가→굴토/기초)은 이 6개 WB 밖의 개념이라 델타를 낼 base가 없으므로
#   억지 매핑하지 않고 data_gaps로 정직 강등한다(0원 델타를 "산정됨"처럼 보이게 하지 않음).
_ITEM_TO_WB: dict[str, list[str]] = {
    "건폐율 초과": ["WB04"],
    "용적률 초과": ["WB04"],
    "높이제한 초과": ["WB04"],
}

# 리스크 item → (pct_low, pct_high) — design_change_predictor의 est_impact 문구를 그대로 반영
# (새 숫자 없음): "약 +5%" 단일값은 (TYPICAL,TYPICAL), "최대 +15%"/"+15%"도 단일값(MAX,MAX).
_ITEM_TO_PCT_RANGE: dict[str, tuple[float, float]] = {
    "건폐율 초과": (_TYPICAL_PCT, _TYPICAL_PCT),
    "용적률 초과": (_MAX_PCT, _MAX_PCT),
    "높이제한 초과": (_MAX_PCT, _MAX_PCT),
}


def _wb_base_amount(items: list[dict[str, Any]], wb_codes: list[str]) -> int:
    """base BOQ 항목 중 지정 WB(대공종)에 속하는 금액 합계(실산정 금액 — 날조 없음)."""
    return sum(int(it.get("amount", 0)) for it in items if it.get("wb_code") in wb_codes)


def _risk_scenario(risk: dict[str, Any], base_items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """리스크 1건 → 공종 delta 시나리오. 매핑/수치/base금액 미보유면 None(호출부가 data_gaps에 기록).

    wb_amt<=0이면(이 BOQ 엔진에 해당 WB 라인이 없는 경우) 0원 델타를 "산정됨"처럼 반환하지
    않고 정직하게 스킵한다(가짜 산정치 금지 — 방어적 가드, 현재 매핑표에선 도달하지 않음).
    """
    item = risk.get("item")
    wb_targets = _ITEM_TO_WB.get(item)
    pct_range = _ITEM_TO_PCT_RANGE.get(item)
    if not wb_targets or not pct_range:
        return None

    wb_amt = _wb_base_amount(base_items, wb_targets)
    if wb_amt <= 0:
        return None
    pct_lo, pct_hi = pct_range
    delta_lo = round(wb_amt * pct_lo / 100)
    delta_hi = round(wb_amt * pct_hi / 100)
    return {
        "risk_item": item,
        "risk_category": risk.get("category"),
        "severity": risk.get("severity"),
        "wb_targets": wb_targets,
        "wb_names": [WB_CATEGORIES.get(c) for c in wb_targets],
        "wb_base_amount": wb_amt,
        "delta_pct_low": pct_lo,
        "delta_pct_high": pct_hi,
        "delta_low": delta_lo,
        "delta_high": delta_hi,
        "basis": "design_change_predictor 예측모듈 자체 계수(TYPICAL/MAX) 재사용 — 신규 수치 없음",
    }


async def forecast_change_cost(
    base_spec: dict[str, Any], risks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """base_spec(alternatives base_params와 동일 계약) + risks(opt-in)로 설계변경 예측공사비를 낸다.

    risks가 비어있거나 전부 매핑 불가여도 MC 밴드는 항상 산출된다(요구사항 — 데이터 없음이
    전체 응답 실패로 이어지지 않게 graceful).
    """
    bp = merge_params(base_spec, {})
    base_boq = await build_boq_for_params(bp)
    base_total = int(base_boq["summary"]["total"])

    # ── MC 밴드(항상 산출) — base_boq["_calc"]는 OriginCostCalculator.calculate() 결과 그대로
    #    (direct_material_cost/total_labor_cost/direct_expense_cost/total_project_cost 보유).
    mc = CostMonteCarlo(base_boq["_calc"]).run()
    mc_band = {
        "base_total": mc["base_total"], "p10": mc["p10"], "p50": mc["p50"], "p90": mc["p90"],
        "mean": mc["mean"], "std": mc["std"],
    }

    scenarios: list[dict[str, Any]] = []
    data_gaps: list[str] = []
    for risk in (risks or []):
        scenario = _risk_scenario(risk, base_boq["items"])
        if scenario is None:
            label = risk.get("item") or "(항목 없음)"
            data_gaps.append(f"{label}: 공종(WB) 변환 매핑 또는 수치(±%) 미보유 — 정성 경고만, 시나리오 스킵")
            continue
        scenarios.append(scenario)

    return {
        "base_total": base_total,
        "mc_band": mc_band,
        "scenarios": scenarios,
        "data_gaps": data_gaps,
        "note": (
            "MC 밴드는 건축개요 기반 원가 몬테카를로(design_chg 리스크 계수 포함) 추정입니다. "
            "리스크 시나리오는 design_change_predictor 사전예측(확정 아님) 기반 개산이며 "
            "전문가(건축사·구조기술사) 검토가 필요합니다."
        ),
    }
