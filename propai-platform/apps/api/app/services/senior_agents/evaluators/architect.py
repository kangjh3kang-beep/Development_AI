"""시니어 설계사 정량 평가기 — 정북일조 이격·동지 일조(실수치).

architect spec(design.bukchuk_setback·design.winter_daylight_gate)을 실제 입력으로 평가.
입력(context['inputs']): building_height_m·north_distance_m(실 북측이격)·
winter_daylight_continuous_min(동지 09~15시 연속 일조 분).

★정북일조 임계 일원화 메모(통합자): 동일 산식의 정본은 공용 sunlight_setback(현행 10m)이며
fix/north-setback-10m 브랜치에 있다. 본 senior 브랜치엔 미머지라 현행법(건축법 시행령 86조
2023.9.12 개정: 10m·1.5m·h/2)을 로컬 상수로 둔다. 두 브랜치 머지 후 required_north_setback_m로
일원화할 것(현재 값은 정본과 동일·드리프트 없음).
"""

from __future__ import annotations

from app.services.senior_agents.evaluators.base import (
    BLOCK,
    PASS,
    WARN,
    RuleEvaluation,
    num,
)

# 건축법 시행령 제86조 제1항(2023.9.12 개정) 정북일조 임계·이격(공용 sunlight_setback와 동일).
NORTH_SETBACK_HEIGHT_THRESHOLD_M = 10.0
NORTH_SETBACK_MIN_LOW_M = 1.5
WINTER_DAYLIGHT_MIN_MINUTES = 120.0       # 동지 09~15시 연속 2시간(법정 채광 인동간격 예외요건)
WINTER_DAYLIGHT_DISPUTE_TOTAL_MINUTES = 240.0  # 동지 08~16시 총 4시간(판례 수인한도)


def _required_north_setback(height_m: float) -> float:
    """높이별 정북 최소 이격(현행: ≤10m→1.5m·초과→높이/2). sunlight_setback 정본과 동일."""
    return NORTH_SETBACK_MIN_LOW_M if height_m <= NORTH_SETBACK_HEIGHT_THRESHOLD_M else height_m / 2.0


def evaluate_architect(inputs: dict) -> list[RuleEvaluation]:
    """정북일조 이격 적합·동지 연속일조 게이트(결측 생략·무목업)."""
    out: list[RuleEvaluation] = []

    # 정북일조 이격: 실 북측이격 vs 필요(현행 10m). 미달 BLOCK(위반).
    h = num(inputs, "building_height_m")
    nd = num(inputs, "north_distance_m")
    if h is not None and nd is not None and h > 0:
        req = _required_north_setback(h)
        rule_txt = "10m이하 1.5m" if h <= NORTH_SETBACK_HEIGHT_THRESHOLD_M else "높이/2"
        out.append(RuleEvaluation(
            rule_id="design.bukchuk_setback", label="정북일조 이격", value=round(nd, 2), unit="m",
            verdict=PASS if nd >= req else BLOCK, threshold=f"≥{req:.2f}m (높이 {h:.1f}m·{rule_txt})",
            basis="건축법 시행령 제86조 제1항(정북 일조 높이제한·2023.9.12 개정 현행 10m)",
            detail=f"북측 이격 {nd:.2f}m vs 필요 {req:.2f}m (높이 {h:.1f}m)"))

    # 동지 연속일조(법정 게이트): 09~15시 연속 2시간(120분) 미만 BLOCK(인허가 reject).
    cont = num(inputs, "winter_daylight_continuous_min")
    if cont is not None and cont >= 0:
        out.append(RuleEvaluation(
            rule_id="design.winter_daylight_gate", label="동지 연속일조(법정)", value=round(cont, 0), unit="분",
            verdict=PASS if cont >= WINTER_DAYLIGHT_MIN_MINUTES else BLOCK,
            threshold="≥120분(동지 09~15시 연속 2h)",
            basis="건축법 시행령 제86조 제3항(채광 인동간격 예외=동지 09~15시 2시간)",
            detail=f"동지 09~15시 연속 일조 {cont:.0f}분 vs 법정 {WINTER_DAYLIGHT_MIN_MINUTES:.0f}분"))
        # 분쟁 경고(판례 수인한도·별도): 법정 게이트는 통과(연속 2h)하나 총 4h 미만 → 일조분쟁 위험 WARN.
        total = num(inputs, "winter_daylight_total_min")
        if (total is not None and total >= 0 and cont >= WINTER_DAYLIGHT_MIN_MINUTES
                and total < WINTER_DAYLIGHT_DISPUTE_TOTAL_MINUTES):
            out.append(RuleEvaluation(
                rule_id="design.winter_daylight_dispute", label="동지 일조분쟁(판례)",
                value=round(total, 0), unit="분", verdict=WARN,
                threshold="≥240분(08~16시 총 4h) AND 연속 2h",
                basis="일조방해 수인한도 판례(동지 08~16시 4h AND 09~15시 2h)",
                detail=f"08~16시 총 일조 {total:.0f}분<240분 — 법정 게이트는 충족하나 일조분쟁 위험"))

    return out
