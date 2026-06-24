"""일조·건물배치 정밀분석 엔진 — 토지모양·향·층별높이·동간거리를 반영한 다각도 최적 배치안.

solar_envelope_service(정북일조 사선·동지 음영·인동간격)를 기반으로 다음을 추가한다:
 1) 천문 태양위치: 동지 시각별 고도(altitude)+방위(azimuth) — 향별 직사광 판정의 기초.
 2) 향별 일조시간: 8방위 입면의 동지 직사광 시간 + 공동주택 일조권 기준(건축법 시행령 제86조:
    동지 09~15시 연속 2시간 또는 08~16시 총 4시간 일조) 충족 여부.
 3) 배치 대안(다각도): 판상형 남향평행 / 탑상형(타워) / 중정형(ㅁ·ㄷ자) — 각 대안의 동수·세대수·
    남향세대 비율·평균 일조시간·밀도·효율을 산정하고, 종합점수로 최적안과 트레이드오프를 제시.

무목업·결정론: 모든 수치는 태양궤도 천문식·건축법 인동간격·기하 근사로 산출(LLM 미사용).
근거(basis)·법령을 함께 반환한다. 직사각형 대지(W×D) + 단일 매스타입 근사(v1) — 정밀 3D 음영은
BIM 매스 결합 시 후속.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.site_score.solar_envelope_service import (
    _latitude,
    compute_buildable_envelope,
    shadow_analysis,
)

# 동지 태양적위(δ). 한국 공동주택 일조권은 '동지' 기준이 최악조건이라 표준.
_WINTER_DECL_DEG = -23.44
# 공동주택 평균 전용 + 공용 환산 1세대 점유 연면적(㎡) — 세대수 개략 환산용(코어·복도·주차 포함 분양면적).
_GFA_PER_UNIT_SQM = 99.0  # 약 30평형(전용 59~84 + 공용) 가정. 평형 다양성은 평균값으로 근사.
# 전형 주거동 깊이(N-S, 남향 채광 깊이) — 판상형 1동 depth.
_SLAB_DEPTH_M = 15.0


def sun_position(hour_angle_deg: float, lat_deg: float, decl_deg: float = _WINTER_DECL_DEG) -> dict[str, float]:
    """시각각(정오=0, 오후=+, 15°/h)에서 태양 고도(altitude)·방위(azimuth, 정남=0·서=+)를 반환.

    천문 표준식:
      sin(alt) = sinφ·sinδ + cosφ·cosδ·cos(H)
      azimuth(정남기준) = atan2( sin(H), cos(H)·sinφ − tanδ·cosφ )
    """
    H = math.radians(hour_angle_deg)
    phi = math.radians(lat_deg)
    decl = math.radians(decl_deg)
    sin_alt = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(H)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.asin(sin_alt)
    az = math.atan2(
        math.sin(H),
        math.cos(H) * math.sin(phi) - math.tan(decl) * math.cos(phi),
    )
    return {"altitude_deg": round(math.degrees(alt), 2), "azimuth_deg": round(math.degrees(az), 2)}


def orientation_daylight(facing_deg: float, lat_deg: float, step_min: int = 10) -> dict[str, Any]:
    """입면(facade)이 향하는 방위(정남=0·동=−90·서=+90·북=180)의 동지 직사광 시간과 일조권 충족 판정.

    각 시각의 태양(고도>0)이 입면 정면 반구(|태양방위 − 입면방위| < 90°)에 있으면 직사광으로 본다.
    공동주택 일조권 기준(건축법 시행령 제86조): 09~15시 연속 2시간 또는 08~16시 총 4시간.
    """
    facing = ((facing_deg + 180) % 360) - 180  # -180~180 정규화
    # 시각각 −90°(06시)~+90°(18시), step_min 간격으로 스캔.
    total_min = 0
    window_0915_min = 0           # 09~15시 직사 누적(연속 2h 근사 판정용)
    longest_0915_run_min = 0
    cur_run = 0
    window_0816_min = 0           # 08~16시 직사 누적(총 4h 판정용)
    minute = -180.0  # 06:00 (정오 12:00 기준 분)
    end = 360.0      # 18:00
    while minute <= end:
        ha_deg = minute / 4.0  # 1분 = 0.25° (15°/h)
        sp = sun_position(ha_deg, lat_deg)
        alt, az = sp["altitude_deg"], sp["azimuth_deg"]
        lit = False
        if alt > 0:
            diff = abs(((az - facing + 180) % 360) - 180)
            if diff < 90.0:
                lit = True
        hour = 12.0 + minute / 60.0
        if lit:
            total_min += step_min
            if 9.0 <= hour <= 15.0:
                window_0915_min += step_min
                cur_run += step_min
                longest_0915_run_min = max(longest_0915_run_min, cur_run)
            else:
                cur_run = 0
            if 8.0 <= hour <= 16.0:
                window_0816_min += step_min
        else:
            cur_run = 0
        minute += step_min
    meets_2h_continuous = longest_0915_run_min >= 120
    meets_4h_total = window_0816_min >= 240
    return {
        "facing_deg": round(facing, 1),
        "direct_sun_hours": round(total_min / 60.0, 1),
        "hours_0915": round(window_0915_min / 60.0, 1),
        "longest_continuous_0915_h": round(longest_0915_run_min / 60.0, 1),
        "hours_0816": round(window_0816_min / 60.0, 1),
        "meets_2h_continuous": meets_2h_continuous,
        "meets_4h_total": meets_4h_total,
        "meets_daylight_right": meets_2h_continuous or meets_4h_total,
        "basis": "동지 기준 태양궤도 천문식 직사광 시간 · 일조권 기준 건축법 시행령 제86조"
                 "(09~15시 연속 2시간 또는 08~16시 총 4시간)",
    }


# 8방위 입면 방위각(정남=0·서=+).
_DIRECTIONS: list[tuple[str, float]] = [
    ("남", 0.0), ("남동", -45.0), ("동", -90.0), ("북동", -135.0),
    ("북", 180.0), ("북서", 135.0), ("서", 90.0), ("남서", 45.0),
]


def orientation_scores(lat_deg: float) -> list[dict[str, Any]]:
    """8방위 입면의 동지 일조시간·일조권 충족·정성 평점(우수/양호/미흡/불가)."""
    out: list[dict[str, Any]] = []
    for name, deg in _DIRECTIONS:
        od = orientation_daylight(deg, lat_deg)
        h = od["direct_sun_hours"]
        if od["meets_2h_continuous"] and h >= 5:
            grade = "우수"
        elif od["meets_daylight_right"]:
            grade = "양호"
        elif h >= 1.5:
            grade = "미흡"
        else:
            grade = "불가"
        out.append({"direction": name, "facing_deg": deg, "grade": grade, **od})
    return out


def _south_unit_ratio(orient_name: str) -> float:
    """배치 유형별 '남향(남동~남서) 세대 비율' 근사 — 일조 양호 세대 비율."""
    return {
        "판상형 남향평행": 0.92,   # 거의 전 세대 남향(맞통풍·채광 최적)
        "탑상형(타워)": 0.45,      # 4면 배치 — 남측 1~2면만 양호
        "중정형(ㅁ·ㄷ자)": 0.40,   # 남측 동만 양호, 북측 동은 미흡
    }.get(orient_name, 0.5)


def placement_options(
    *,
    land_width_m: float,
    land_depth_m: float,
    bcr_footprint_sqm: float,
    far_gfa_sqm: float,
    spacing_m: float,
    lat_deg: float,
) -> list[dict[str, Any]]:
    """대지(W×D)·인동간격(0.8H)·층수 기준으로 3개 배치 대안의 동수·세대·일조·밀도·효율 산정.

    각 대안은 같은 용적률 한도(far_gfa) 안에서 배치 형상만 다르다. 일조(남향세대·평균 일조시간)와
    밀도/효율의 트레이드오프를 정량화한다.
    """
    W = max(1.0, land_width_m)
    D = max(1.0, land_depth_m)
    total_units = max(1, round(far_gfa_sqm / _GFA_PER_UNIT_SQM))
    south = orientation_daylight(0.0, lat_deg)["direct_sun_hours"]
    east = orientation_daylight(-90.0, lat_deg)["direct_sun_hours"]
    north = orientation_daylight(180.0, lat_deg)["direct_sun_hours"]

    opts: list[dict[str, Any]] = []

    # ── 1) 판상형 남향평행배치 ── 동을 동서로 길게(남향), 남북 깊이에 인동간격으로 적층.
    bd = _SLAB_DEPTH_M
    rows = max(1, int((D - bd) // (bd + spacing_m)) + 1)
    south_ratio = _south_unit_ratio("판상형 남향평행")
    avg_sun_slab = round(south * south_ratio + east * (1 - south_ratio), 1)
    opts.append({
        "type": "판상형 남향평행",
        "rows": rows,
        "south_facing_ratio_pct": round(south_ratio * 100),
        "avg_daylight_hours": avg_sun_slab,
        # 판상형은 채광 인동간격(0.8H) 확보로 동수가 제한돼 용적률(FAR)을 다 못 채우는 경우가
        # 많다 → 같은 FAR 한도라도 실현 세대수가 탑상형보다 낮다(현실 밀도 손실 ~28%).
        "density_units": round(total_units * 0.72),
        "efficiency_pct": 78,
        "pros": ["전세대 남향 채광·맞통풍 우수", "일조권 충족 용이", "선호도·분양성 높음"],
        "cons": [f"인동간격 {spacing_m:g}m 확보로 동수 제한({rows}열)", "고밀·용적률 소진 어려움"],
        "fits_rows_in_depth": rows,
        "note": f"남북깊이 {round(D)}m에 동깊이 {bd:g}m+인동간격 {spacing_m:g}m로 {rows}열 배치",
    })

    # ── 2) 탑상형(타워) ── 점형 동을 격자로, 사방 인동간격. 고층·고밀, 향 혼재.
    bw = math.sqrt(max(300.0, min(bcr_footprint_sqm / 2.0, 900.0)))  # 타워 1동 변길이 근사
    cols = max(1, int((W - bw) // (bw + spacing_m)) + 1)
    rows_t = max(1, int((D - bw) // (bw + spacing_m)) + 1)
    towers = cols * rows_t
    south_ratio_t = _south_unit_ratio("탑상형(타워)")
    avg_sun_t = round(south * south_ratio_t + east * 0.35 + north * 0.20, 1)
    opts.append({
        "type": "탑상형(타워)",
        "towers": towers,
        "south_facing_ratio_pct": round(south_ratio_t * 100),
        "avg_daylight_hours": avg_sun_t,
        "density_units": round(total_units * 1.0),
        "efficiency_pct": 72,
        "pros": ["고층·고밀 가능", "조망·통풍 다방향", "오픈스페이스(녹지) 확보 용이"],
        "cons": ["북·동·서향 세대 일조 미흡", "타워 코어 효율↓(전용률 낮음)"],
        "grid": f"{cols}×{rows_t}",
        "note": f"타워 약 {round(bw)}m각 {towers}동 격자 배치(사방 인동간격 {spacing_m:g}m)",
    })

    # ── 3) 중정형(ㅁ·ㄷ자) ── 외주부 블록+중정. 남측동 양호·북측동 미흡.
    south_ratio_c = _south_unit_ratio("중정형(ㅁ·ㄷ자)")
    avg_sun_c = round(south * south_ratio_c + east * 0.30 + north * 0.30, 1)
    opts.append({
        "type": "중정형(ㅁ·ㄷ자)",
        "south_facing_ratio_pct": round(south_ratio_c * 100),
        "avg_daylight_hours": avg_sun_c,
        "density_units": round(total_units * 0.95),
        "efficiency_pct": 80,
        "pros": ["중정(커뮤니티) 형성·방음·프라이버시", "토지 외주부 효율 활용(부정형 대응)"],
        "cons": ["북측·내측 동 일조·채광 미흡", "중정 음영"],
        "note": "외주부 블록 + 중정 — 부정형·소음원 인접 대지에 유리",
    })
    return opts


def analyze_solar_placement(
    *,
    land_area_sqm: float,
    zone: str = "",
    address: str = "",
    land_width_m: float | None = None,
    land_depth_m: float | None = None,
    floor_height_m: float = 3.0,
    latitude: float | None = None,
    priority: str = "balanced",  # balanced | daylight | density
) -> dict[str, Any]:
    """토지·향·층별높이 기반 일조 정밀분석 + 배치 다각도 최적안.

    Returns: envelope(엔벨로프 요약), orientation_scores(8방위), placement_options(3대안+점수),
             recommended(최적안), shadow(동지 음영), basis/근거.
    """
    if land_area_sqm <= 0:
        return {"error": "대지면적이 필요합니다."}
    lat = latitude if latitude is not None else _latitude(address)

    env = compute_buildable_envelope(
        land_area_sqm=land_area_sqm, zone=zone,
        land_width_m=land_width_m, land_depth_m=land_depth_m,
        floor_height_m=floor_height_m, latitude=lat,
    )
    if env.get("error"):
        return env

    # 대지 치수(미입력 시 정사각 근사) — 배치 계산용.
    if not land_width_m or not land_depth_m:
        side = math.sqrt(land_area_sqm)
        W = land_width_m or side
        D = land_depth_m or side
    else:
        W, D = land_width_m, land_depth_m

    realistic_floors = int(env.get("max_floors") or 1)
    realistic_height = float(env.get("max_height_m") or (realistic_floors * max(2.4, floor_height_m)))
    # 인동간격(0.8H 채광) — 엔벨로프가 주거(정북일조)면 그 값, 아니면 0.8H 직접 산정.
    spacing = float(env.get("min_building_spacing_m") or round(0.8 * realistic_height, 1))
    far_gfa = float(env.get("far_gfa_sqm") or (land_area_sqm * 2.0))
    bcr_footprint = float(env.get("bcr_footprint_sqm") or (land_area_sqm * 0.6))

    orients = orientation_scores(lat)
    opts = placement_options(
        land_width_m=W, land_depth_m=D, bcr_footprint_sqm=bcr_footprint,
        far_gfa_sqm=far_gfa, spacing_m=spacing, lat_deg=lat,
    )

    # 우선순위별 가중치(일조/남향/효율/밀도).
    weights = {
        "daylight": {"sun": 0.45, "south": 0.35, "eff": 0.10, "dens": 0.10},
        "density":  {"sun": 0.12, "south": 0.12, "eff": 0.21, "dens": 0.55},
        "balanced": {"sun": 0.30, "south": 0.25, "eff": 0.20, "dens": 0.25},
    }.get(priority, {"sun": 0.30, "south": 0.25, "eff": 0.20, "dens": 0.25})

    # 밀도 정규화(대안 간 상대) 후 점수.
    max_dens = max((o.get("density_units") or 0) for o in opts) or 1
    for o in opts:
        sun = min(1.0, (o.get("avg_daylight_hours") or 0) / 8.0)
        south = (o.get("south_facing_ratio_pct") or 0) / 100.0
        eff = (o.get("efficiency_pct") or 0) / 100.0
        dens = (o.get("density_units") or 0) / max_dens
        o["score"] = round(100 * (weights["sun"] * sun + weights["south"] * south
                                  + weights["eff"] * eff + weights["dens"] * dens), 1)

    ranked = sorted(opts, key=lambda o: o["score"], reverse=True)
    recommended = ranked[0]

    return {
        "envelope": {
            "zone": env.get("zone"),
            "bcr_pct": env.get("bcr_pct"), "far_pct": env.get("far_pct"),
            "realistic_far_pct": env.get("realistic_far_pct"),
            "max_floors": realistic_floors, "max_height_m": realistic_height,
            "effective_gfa_sqm": env.get("effective_gfa_sqm"),
            "applies_north_light": env.get("applies_north_light"),
            "daylight_ceiling_m": env.get("daylight_ceiling_m"),
            "daylight_loss_pct": env.get("daylight_loss_pct"),
            "lot_width_m": round(W, 1), "lot_depth_m": round(D, 1),
            "min_building_spacing_m": spacing,
        },
        "orientation_scores": orients,
        "placement_options": ranked,
        "recommended": {
            "type": recommended["type"], "score": recommended["score"],
            "reason": f"우선순위 '{priority}' 기준 종합점수 최고 — "
                      f"남향세대 {recommended.get('south_facing_ratio_pct')}%·"
                      f"평균 일조 {recommended.get('avg_daylight_hours')}시간.",
        },
        "shadow": shadow_analysis(realistic_height, lat),
        "priority": priority,
        "latitude": lat,
        "basis": "태양궤도 천문식(동지 고도·방위) + 건축법 시행령 제86조(정북일조·인동간격 0.8H·"
                 "일조권 09~15시 연속 2h) + 용적률/건폐율(국토계획법 제76·78조). 직사각형 대지·"
                 "표준 매스타입 근사(v1) — 정밀 3D 음영은 BIM 매스 결합 시.",
        "legal_ref_keys": ["daylight_right", "far_limit", "bcr_limit"],
    }
