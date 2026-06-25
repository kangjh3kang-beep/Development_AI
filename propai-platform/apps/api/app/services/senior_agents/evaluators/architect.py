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

# ── 시니어 평면 성립성 게이트 임계(D-B) ──
# 복도 최소폭(건축법 시행령 §48): 편복도 1.8m / 중복도(양면 거실) 2.4m.
CORRIDOR_SINGLE_MIN_M = 1.8
CORRIDOR_DOUBLE_MIN_M = 2.4
# 피난(건축법 시행령 §34 ②): 5층 이상 또는 층당 거실 200㎡ 초과 → 직통계단 2개소 이상.
EGRESS_FLOOR_THRESHOLD = 5
EGRESS_FLOOR_AREA_THRESHOLD_SQM = 200.0
EGRESS_MIN_STAIRS = 2
# 보행거리(피난·방화구조 기준 규칙 §15 ①): 비내화 30m / 내화·불연 50m.
TRAVEL_DISTANCE_NONCOMBUSTIBLE_M = 50.0
TRAVEL_DISTANCE_DEFAULT_M = 30.0
# 승강기 의무(건축법 §64·시행령 §89): 6층 이상.
ELEVATOR_FLOOR_THRESHOLD = 6
# 코어당 세대수 권고 상한(과다 시 피난·EV 혼잡 — WARN). 실무 통상 1코어 60세대 내외.
CORE_UNITS_WARN = 60
# 전용률(전용/공급) 상식 범위: 100% 초과는 물리적 불가(BLOCK), 70% 미만/85% 초과는 비전형(WARN).
UNIT_EFFICIENCY_MIN_NORMAL = 0.70
UNIT_EFFICIENCY_MAX_NORMAL = 0.85


def _required_north_setback(height_m: float) -> float:
    """높이별 정북 최소 이격(현행: ≤10m→1.5m·초과→높이/2). sunlight_setback 정본과 동일."""
    return NORTH_SETBACK_MIN_LOW_M if height_m <= NORTH_SETBACK_HEIGHT_THRESHOLD_M else height_m / 2.0


def _eval_corridor_width(inputs: dict) -> RuleEvaluation | None:
    """복도폭 적합(건축법 시행령 §48) — 편복도≥1.8m·중복도≥2.4m 미달 BLOCK(결측 생략)."""
    cw = num(inputs, "corridor_width_m")
    if cw is None or cw <= 0:
        return None
    ctype = str(inputs.get("corridor_type") or "double").strip().lower()
    is_single = ctype == "single"
    req = CORRIDOR_SINGLE_MIN_M if is_single else CORRIDOR_DOUBLE_MIN_M
    type_kr = "편복도" if is_single else "중복도(양면거실)"
    return RuleEvaluation(
        rule_id="design.corridor_width", label="복도 너비", value=round(cw, 2), unit="m",
        verdict=PASS if cw >= req else BLOCK, threshold=f"≥{req:.1f}m ({type_kr})",
        basis="건축법 시행령 제48조(복도의 너비·공동주택 공용복도)",
        detail=f"{type_kr} 복도폭 {cw:.2f}m vs 법정 최소 {req:.1f}m")


def _eval_egress(inputs: dict) -> list[RuleEvaluation]:
    """피난(건축법 시행령 §34·피난규칙 §15) — 직통계단 2개소·보행거리. 결측 생략(무목업)."""
    out: list[RuleEvaluation] = []
    floors = num(inputs, "floor_count")
    floor_area = num(inputs, "floor_area_per_floor_sqm")
    stairs = num(inputs, "direct_stair_count")
    # 직통계단 2개소: 5층↑ or 층당 거실>200㎡일 때만 의무 — 그 조건과 계단수가 모두 주어져야 평가.
    needs_dual = (
        (floors is not None and floors >= EGRESS_FLOOR_THRESHOLD)
        or (floor_area is not None and floor_area > EGRESS_FLOOR_AREA_THRESHOLD_SQM)
    )
    if needs_dual and stairs is not None:
        out.append(RuleEvaluation(
            rule_id="design.egress", label="직통계단 개소", value=round(stairs, 0), unit="개소",
            verdict=PASS if stairs >= EGRESS_MIN_STAIRS else BLOCK,
            threshold=f"≥{EGRESS_MIN_STAIRS}개소(5층↑ 또는 층당 거실 200㎡↑)",
            basis="건축법 시행령 제34조 제2항(직통계단의 설치)",
            detail=f"직통계단 {stairs:.0f}개소 vs 법정 최소 {EGRESS_MIN_STAIRS}개소"))
    # 보행거리(거실→직통계단): 내화 50m / 비내화 30m 초과 BLOCK. 실측·내화여부 모두 주어질 때만.
    travel = num(inputs, "travel_distance_m")
    if travel is not None and travel >= 0:
        fire_resistant = bool(inputs.get("fire_resistant", True))
        limit = TRAVEL_DISTANCE_NONCOMBUSTIBLE_M if fire_resistant else TRAVEL_DISTANCE_DEFAULT_M
        kind = "내화" if fire_resistant else "비내화"
        out.append(RuleEvaluation(
            rule_id="design.egress_travel", label="피난 보행거리", value=round(travel, 1), unit="m",
            verdict=PASS if travel <= limit else BLOCK, threshold=f"≤{limit:.0f}m ({kind}구조)",
            basis="피난·방화구조 등의 기준에 관한 규칙 제15조 제1항(보행거리)",
            detail=f"거실→직통계단 보행거리 {travel:.1f}m vs 한도 {limit:.0f}m({kind})"))
    return out


def _eval_core_adequacy(inputs: dict) -> list[RuleEvaluation]:
    """코어 적정성 — 6층↑ EV 누락 WARN·코어당 세대 과다 WARN. 결측 생략(무목업)."""
    out: list[RuleEvaluation] = []
    floors = num(inputs, "floor_count")
    has_ev = inputs.get("has_elevator")
    if floors is not None and floors >= ELEVATOR_FLOOR_THRESHOLD and has_ev is False:
        out.append(RuleEvaluation(
            rule_id="design.core_adequacy", label="승강기 설치", value=float(floors), unit="층",
            verdict=WARN, threshold=f"{ELEVATOR_FLOOR_THRESHOLD}층 이상 승강기 의무",
            basis="건축법 제64조·시행령 제89조(승강기 설치)",
            detail=f"{floors:.0f}층 — 승강기 설치 누락(6층 이상 의무) — 코어에 EV 반영 필요"))
    units = num(inputs, "total_units")
    cores = num(inputs, "num_cores")
    if units is not None and units > 0 and cores is not None and cores > 0:
        per_core = units / cores
        out.append(RuleEvaluation(
            rule_id="design.core_load", label="코어당 세대수", value=round(per_core, 1), unit="세대/코어",
            verdict=WARN if per_core > CORE_UNITS_WARN else PASS,
            threshold=f"≤{CORE_UNITS_WARN}세대/코어(권고)",
            basis="피난 동선·승강기 운영 통상 권고(코어 1개소당 세대 부하)",
            detail=f"코어 {cores:.0f}개·{units:.0f}세대 → 코어당 {per_core:.1f}세대"
                   + (" — 과다(코어 증설·동 분리 검토)" if per_core > CORE_UNITS_WARN else "")))
    return out


def _eval_unit_efficiency(inputs: dict) -> RuleEvaluation | None:
    """전용률(전용/공급) 상식 게이트 — >100% BLOCK·<70%/>85% WARN. 결측 생략(무목업)."""
    eff = num(inputs, "unit_efficiency")
    if eff is None or eff <= 0:
        return None
    pct = eff * 100.0 if eff <= 1.5 else eff  # 0~1 비율 입력 또는 % 입력 모두 수용
    ratio = pct / 100.0
    if ratio > 1.0:
        verdict, note = BLOCK, " — 전용면적이 공급면적 초과(물리적 불가)"
    elif ratio < UNIT_EFFICIENCY_MIN_NORMAL or ratio > UNIT_EFFICIENCY_MAX_NORMAL:
        verdict, note = WARN, " — 전형 범위(70~85%) 벗어남(평면 재검토)"
    else:
        verdict, note = PASS, ""
    return RuleEvaluation(
        rule_id="design.unit_efficiency", label="전용률", value=round(pct, 1), unit="%",
        verdict=verdict, threshold="≤100%(필수)·70~85%(전형)",
        basis="전용/공급 면적비 상식 범위(공동주택 통상 전용률)",
        detail=f"전용률 {pct:.1f}%{note}")


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

    # ── 평면 성립성 게이트(D-B·생성 폐루프용) — 각 게이트는 입력 결측 시 생략(무목업) ──
    cw = _eval_corridor_width(inputs)
    if cw is not None:
        out.append(cw)
    out.extend(_eval_egress(inputs))
    out.extend(_eval_core_adequacy(inputs))
    ue = _eval_unit_efficiency(inputs)
    if ue is not None:
        out.append(ue)

    return out
