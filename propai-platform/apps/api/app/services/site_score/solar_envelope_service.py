"""한국 정북일조 빌더블 인벨로프(베팅 D) — 실제 건축가능 최대 볼륨·층수 산정.

건축법 시행령 제86조(정북방향 일조 확보 이격·2023.9.12 개정 현행 임계 10m):
 - 전용/일반주거지역: 높이 10m 이하 부분은 정북 인접대지경계에서 1.5m 이상,
   10m 초과 부분은 그 부분 높이의 1/2 이상 이격.  → 거리 d에서 최대높이 H(d)=max(10, 2d) 보수 근사.
정북사선을 남북깊이에 대해 스트립 적분해 '일조로 실제 지을 수 있는' 최대 연면적을 구하고,
용적률(FAR) 한도와 비교해 '바인딩 제약'과 '일조 손실률'을 제시한다.

한계(v1 근사): 직사각형 대지 가정(W×D, 정북=깊이방향), 단일 매스, 측면이격 간이.
글로벌 툴(Forma/Zoneomics)이 모르는 '한국 정북일조'를 정량화하는 것이 핵심 차별점.
향후: VWorld 실측 PARCEL 폴리곤(shapely)·도로사선·인동간격·IFC 결합으로 정밀화.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.common.sunlight_setback import max_height_for_north_distance_m
from app.services.permit.building_code_rules import ZONE_DEFAULTS
from app.services.zoning.legal_zone_limits import legal_limits_for

# 정북일조 적용 용도지역(전용/일반주거). 준주거·상업·공업은 통상 미적용/완화.
_NORTH_LIGHT_ZONES = ("전용주거", "일반주거", "1종", "2종", "3종", "제1종", "제2종", "제3종")

# ★녹지지역 층수 제한(자연녹지 4층 등)은 SSOT(legal_limits_for → ZONE_LIMITS.max_floors)에서
#   위임받는다. 종전 로컬 _ZONE_MAX_FLOORS dict(중복 지식)은 제거하고 단일 출처로 일원화.
#   자연녹지는 건폐율 20%·용적률 100%이나 4층 제한 때문에 현실 용적률 = 20%×4층 = 80%(<법정 100%).
#   이 제한을 무시하면 ceil(100/20)=5층·용적률 100%로 과대 산정된다.


def dims_from_polygon(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    """VWorld 필지 GeoJSON(geometry)에서 실측 남북깊이·동서폭·면적 도출.

    경위도(EPSG:4326)를 중심위도 기준 등거리 근사로 미터 변환 →
    bbox로 N-S 깊이(정북일조 핵심축)·E-W 폭, shapely로 실면적 산출.
    """
    if not geometry:
        return None
    try:
        from shapely.geometry import shape

        geom = shape(geometry)
        if geom.is_empty:
            return None
        minx, miny, maxx, maxy = geom.bounds  # lon/lat
        lat0 = (miny + maxy) / 2.0
        m_per_deg_lat = 110540.0
        m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))
        width_m = (maxx - minx) * m_per_deg_lon     # 동서(E-W)
        depth_m = (maxy - miny) * m_per_deg_lat      # 남북(N-S) — 정북일조 축
        # 실면적: 경위도 폴리곤을 미터 평면으로 스케일 후 area
        from shapely.affinity import scale as _scale
        geom_m = _scale(geom, xfact=m_per_deg_lon, yfact=m_per_deg_lat, origin=(minx, miny))
        area_sqm = abs(geom_m.area)
        if depth_m <= 0 or width_m <= 0:
            return None
        return {
            "width_m": round(width_m, 2), "depth_m": round(depth_m, 2),
            "area_sqm": round(area_sqm, 1),
            "irregularity": round(1 - area_sqm / (width_m * depth_m), 3) if width_m * depth_m else 0,
        }
    except Exception:  # noqa: BLE001
        return None


# 시도별 대표 위도(동지 일영 계산용)
_LAT_BY_SIDO = {
    "서울": 37.55, "경기": 37.4, "인천": 37.45, "강원": 37.8,
    "충북": 36.8, "충남": 36.5, "대전": 36.35, "세종": 36.5,
    "전북": 35.8, "전남": 34.9, "광주": 35.16, "경북": 36.4,
    "대구": 35.87, "경남": 35.2, "부산": 35.18, "울산": 35.54, "제주": 33.5,
}


def _latitude(address: str, fallback: float = 37.5) -> float:
    for sido, lat in _LAT_BY_SIDO.items():
        if sido in (address or ""):
            return lat
    return fallback


def shadow_analysis(height_m: float, latitude: float = 37.5) -> dict[str, Any]:
    """동지(δ=-23.44°) 9·12·15시 태양고도→그림자 길이(L=H/tanθ). 일조권 영향 정량.

    태양고도 sin(alt)=sinφ·sinδ + cosφ·cosδ·cos(h), h=시각각(정오 0, ±15°/h).
    """
    if height_m <= 0:
        return {}
    decl = math.radians(-23.44)
    lat = math.radians(latitude)
    out: dict[str, Any] = {}
    hours = {"09시": -45.0, "정오": 0.0, "15시": 45.0}
    for label, ha_deg in hours.items():
        ha = math.radians(ha_deg)
        sin_alt = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha)
        alt = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))
        if alt <= 0.5:
            out[label] = {"solar_altitude_deg": round(alt, 1), "shadow_len_m": None}
        else:
            L = height_m / math.tan(math.radians(alt))
            out[label] = {"solar_altitude_deg": round(alt, 1), "shadow_len_m": round(L, 1)}
    noon_alt = out["정오"]["solar_altitude_deg"]
    max_shadow = max((v["shadow_len_m"] or 0) for v in out.values())
    return {
        "winter_solstice": out,
        "noon_altitude_deg": noon_alt,
        "max_shadow_len_m": round(max_shadow, 1),
        "latitude": latitude,
        "note": f"동지 정오 태양고도 {noon_alt}° 기준 그림자 최대 {round(max_shadow,1)}m. "
                "인접대지 일조 영향·인동간격 검토에 활용(정밀 3D 일영은 BIM 매스 결합 시).",
    }


# 시니어 설계에이전트 교차검증 verdict 우선순위(나쁠수록 큼). 키 생략 회피용 기본 매핑.
_SENIOR_STATUS_RANK = {"block": 3, "warn": 2, "pass": 1, "info": 0}


def _senior_architect_review(
    *, building_height_m: float, north_distance_m: float,
    winter_daylight_continuous_min: float | None,
) -> dict[str, Any] | None:
    """시니어 설계에이전트(evaluators.architect) 교차검증을 best-effort로 호출해 요약 dict 반환.

    ★envelope 흐름을 절대 방해하지 않는다(import/호출 실패 시 None). 결과 RuleEvaluation 리스트를
    {verdict: 최악상태(block>warn>pass>info), rules:[{label,value,unit,status,note}]} 로 변환.
    추정/근사 — 직사각 단면·권장 최고층 높이 가정 기반.
    """
    try:
        from app.services.senior_agents.evaluators.architect import evaluate_architect

        inputs: dict[str, Any] = {
            "building_height_m": building_height_m,
            "north_distance_m": north_distance_m,
        }
        # 동지 연속일조(분)는 산출 가능할 때만 주입(불가하면 키 생략 — 무목업).
        if winter_daylight_continuous_min is not None:
            inputs["winter_daylight_continuous_min"] = winter_daylight_continuous_min

        evals = evaluate_architect(inputs)
        rules: list[dict[str, Any]] = []
        worst_rank = -1
        worst_status = "info"
        for ev in evals:
            # RuleEvaluation.verdict 는 PASS/WARN/BLOCK → 소문자 status 로 정규화.
            status = str(getattr(ev, "verdict", "info") or "info").lower()
            rank = _SENIOR_STATUS_RANK.get(status, 0)
            if rank > worst_rank:
                worst_rank, worst_status = rank, status
            rules.append({
                "label": getattr(ev, "label", ev.rule_id),
                "value": getattr(ev, "value", None),
                "unit": getattr(ev, "unit", ""),
                "status": status,
                "note": getattr(ev, "detail", "") or getattr(ev, "threshold", ""),
            })
        if not rules:
            return None
        return {
            "verdict": worst_status,                 # 최악 상태(block>warn>pass>info)
            "rules": rules,
            "note": "시니어 설계에이전트 교차검증(추정·근사) — 권장 최고층 높이·정북 최소이격 1.5m 가정.",
        }
    except Exception:  # noqa: BLE001 — 교차검증 실패는 envelope 본류를 막지 않는다.
        return None


def _zone_limits(zone: str) -> dict[str, Any]:
    """용도지역 → 건폐율/용적률/층수 한도.

    ★권위 테이블(legal_zone_limits, 국토계획법 시행령 §84/§85) 우선. 자체 ZONE_DEFAULTS 는
    자연녹지 등 녹지지역이 없어 미매칭 시 250% 기본값으로 떨어져 '자연녹지에 용적률 250%' 같은
    심각한 과대(할루시네이션)를 유발했다 → 권위 테이블에 위임해 자연녹지=건폐20/용적100 으로 정합.
    녹지지역은 층수 제한(legal_limits_for.max_floors, SSOT)도 함께 실어 현실 용적률(건폐율×제한층수)을 산정한다.
    """
    legal = legal_limits_for(zone)
    if legal and legal.get("max_far_pct"):
        out: dict[str, Any] = {
            "max_bcr": legal.get("max_bcr_pct", 60),
            "max_far": legal.get("max_far_pct", 250),
            "max_height": 0,
        }
        # 층수 제한(녹지 4층 등)은 SSOT(legal_limits_for.max_floors)에서 위임받는다.
        if legal.get("max_floors"):
            out["max_floors"] = legal["max_floors"]
        return out
    # 보조: 자체 ZONE_DEFAULTS(권위 테이블 미매칭 시 — 주요 주거/상업/공업은 보유)
    for k, v in ZONE_DEFAULTS.items():
        if k in (zone or "") or (zone or "") in k:
            return v
    # 최종 폴백: 미매칭 용도지역은 보수적 추정(과대 금지 — 녹지를 250%로 부풀리던 사고 차단).
    return {"max_bcr": 60, "max_far": 200, "max_height": 0}


def _comfort_bcr_divisors(massing_objective: dict[str, Any] | None) -> tuple[float, float]:
    """건축유형별 권장 층수 산정용 '쾌적 건폐율' 분모(low, high)를 반환한다.

    권장 층수 ≈ 현실 용적률% ÷ 쾌적 건폐율%. 기본(objective 없음)은 30/20(기존 동작
    보존·무회귀). 공동주택(고층저밀·max_height_min_coverage)은 낮은 건폐율(많은 층수),
    빌라/연립(고밀·max_coverage)·상업(max_both)은 높은 건폐율(적은 층수)을 가정한다(추정).
    """
    default = (30.0, 20.0)
    if not isinstance(massing_objective, dict):
        return default
    obj = str(massing_objective.get("objective") or "")
    if obj == "max_height_min_coverage":      # 공동주택 고층저밀 — 낮은 건폐율
        return (20.0, 15.0)
    if obj in ("max_coverage", "max_both", "mixed_use_residential"):  # 빌라/상업/혼합 — 고밀
        return (40.0, 30.0)
    return default


def compute_buildable_envelope(
    *,
    land_area_sqm: float,
    zone: str = "",
    land_width_m: float | None = None,
    land_depth_m: float | None = None,
    floor_height_m: float = 3.0,
    bcr_limit_pct: float | None = None,
    far_limit_pct: float | None = None,
    side_setback_m: float = 0.5,
    latitude: float = 37.5,
    massing_objective: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """정북일조 인벨로프 기반 최대 건축가능 연면적·층수·볼륨과 용적률 대비 손실 산정.

    massing_objective(opt-in·additive): massing_strategy.resolve_massing_objective가
    반환하는 MassingObjective dict. 권장 층수 산정의 '쾌적 건폐율' 분모를 건축유형별로
    조정한다 — 공동주택(고층저밀)은 낮은 건폐율(많은 층수)을, 빌라/상업은 높은 건폐율
    (적은 층수)을 가정. None이면 기존 30/20 분모 보존(무회귀).
    """
    if land_area_sqm <= 0:
        return {"error": "대지면적이 필요합니다."}

    lim = _zone_limits(zone)
    bcr = (bcr_limit_pct if bcr_limit_pct is not None else lim.get("max_bcr", 60)) / 100.0
    far = (far_limit_pct if far_limit_pct is not None else lim.get("max_far", 250)) / 100.0
    fh = max(2.4, floor_height_m)
    # ★건축유형별 쾌적 건폐율 분모(권장 층수 = 현실 용적률% ÷ 쾌적 건폐율%). 기본 30/20
    #   (low/high)을 보존하되, objective가 있으면 유형별로 조정(무회귀 — None=기본).
    #   공동주택(고층저밀)=낮은 건폐율(20/15)·빌라/상업(고밀)=높은 건폐율(40/30).
    comfort_bcr_low, comfort_bcr_high = _comfort_bcr_divisors(massing_objective)

    # 대지 치수: 미입력 시 정사각형 가정(정북=깊이 D)
    if not land_width_m or not land_depth_m:
        side = math.sqrt(land_area_sqm)
        W = land_width_m or side
        D = land_depth_m or side
    else:
        W, D = land_width_m, land_depth_m

    far_gfa = land_area_sqm * far               # 용적률 허용 연면적
    bcr_footprint = land_area_sqm * bcr          # 건폐율 허용 1층 바닥면적

    applies = any(k in (zone or "") for k in _NORTH_LIGHT_ZONES)

    if not applies:
        # 정북일조 미적용(준주거·상업 등) → 용적률·건폐율로 층수. ceil=FAR 담는 최소 층수(round 내림 과소산정 방지).
        floors_by_far = max(1, math.ceil(far / bcr)) if bcr > 0 else 1
        zone_max_floors = lim.get("max_floors")
        if zone_max_floors and bcr > 0 and floors_by_far > zone_max_floors:
            # ★층수 제한이 용적률보다 강한 제약(녹지 4층 등): 현실 연면적 = 건폐율 바닥 × 제한층수.
            #   예) 자연녹지 건폐20%·4층 → 현실 용적률 80%(=20%×4) < 법정 100%. 법정 대신 이 값을 채택.
            floors = zone_max_floors
            realistic_gfa = bcr_footprint * floors
            realistic_far = bcr * floors
            binding = "층수제한"
        else:
            floors = floors_by_far
            realistic_gfa = far_gfa
            realistic_far = far
            binding = "용적률"
        # 신규 층수 필드(프론트 공용 소비) — 정북일조 미적용이라 일조 사선 상한 없음.
        #   arithmetic_min_floors=건폐율 만충 산술 하한(법적 개념 아님). 권장범위는 현실 용적률% 기준 추정.
        _arith_min = floors
        # ★권장 층수 상한 캡:
        #   - 층수제한(녹지 4층 등)이 있으면 그 값으로 캡(현실 용적률=건폐율×제한층).
        #   - 층수제한이 없는 용도지역(상업·준주거 — 정북일조 사선 없음)은 산술하한(_arith_min)
        #     으로 권장을 누르지 않는다(과거 버그: _ceil_floors=floors 라 min 캡이 권장을 17층
        #     같은 만충 산술하한으로 붕괴시켜, 고FAR 상업지 주상복합 권장이 비현실로 낮았다).
        #     절대 높이한도(있으면)를 환산 캡으로, 없으면 무제한(탑상형 고층 — FAR÷쾌적건폐율).
        _max_h = lim.get("max_height")
        _height_cap_floors = max(1, int(_max_h / fh)) if _max_h and _max_h > 0 else None
        _ceil_floors = zone_max_floors or _height_cap_floors   # None=무제한(상업 고층)
        _far_p = realistic_far * 100.0

        def _cap_floors(v: int) -> int:
            """_ceil_floors(층수제한/높이환산)가 있으면 그 값으로만 캡 — 없으면 무제한."""
            return min(_ceil_floors, v) if _ceil_floors else v

        # 쾌적 건폐율 분모: 기본 30/20, objective 있으면 유형별(무회귀 — None=기본).
        #   권장 = 현실 용적률% ÷ 쾌적 건폐율%(탑상형 footprint 가정). 예) 상업 1300%·30/20
        #   → 43~65층(주상복합 실무 밴드). 산술하한보다 낮아지지 않게 max로 하한 보장.
        _rec_low = max(_arith_min, _cap_floors(round(_far_p / comfort_bcr_low)))
        _rec_high = max(_rec_low, _cap_floors(round(_far_p / comfort_bcr_high)))
        return {
            "applies_north_light": False,
            "zone": zone, "bcr_pct": round(bcr * 100, 1),
            "far_pct": round(far * 100, 1),                       # 법정 용적률 상한
            "realistic_far_pct": round(realistic_far * 100, 1),   # 현실 용적률(층수제한 반영)
            "far_gfa_sqm": round(far_gfa),                        # 법정 상한 연면적
            "envelope_gfa_sqm": round(realistic_gfa),
            "effective_gfa_sqm": round(realistic_gfa),            # ★연동 소비처가 쓰는 현실 연면적
            "binding": binding,
            "daylight_loss_pct": 0.0,
            "max_height_m": round(floors * fh, 1), "max_floors": floors,
            "zone_max_floors": zone_max_floors,
            # ── 층수 필드(신규·추정·정북일조 미적용이라 일조 사선 상한 없음) ──
            "arithmetic_min_floors": _arith_min,           # 건폐율 만충 산술 하한(★법적 개념 아님)
            "recommended_floors_low": _rec_low,            # 실무 권장 층수 하한(추정)
            "recommended_floors_high": _rec_high,          # 실무 권장 층수 상한(추정)
            "floors_at_north_edge": floors,                # 정북일조 미적용 — 계단식 단면 없음(전층 동일·근사)
            "floors_at_deep": floors,                      # 정북일조 미적용 — 사선 상한 없음(전층 동일·근사)
            "floor_height_m": round(fh, 2),                # 사용된 층고(echo)
            "floor_profile_note": (
                "정북일조 미적용 용도지역 — 계단식 단면 불요(전층 동일 근사). "
                "정밀 높이는 가로구역별 최고높이 별도 확인."
            ),
            "senior_architect_review": None,               # 정북일조 미적용 — 정북 이격 교차검증 대상 아님
            "note": (
                "정북일조 미적용 용도지역 — 용적률/건폐율이 한도."
                + (
                    f" 녹지 {zone_max_floors}층 제한으로 현실 용적률 {round(realistic_far * 100, 1)}%"
                    f"(=건폐율 {round(bcr * 100)}%×{zone_max_floors}층) < 법정 {round(far * 100, 1)}%."
                    if binding == "층수제한"
                    else ""
                )
                + " (정밀 높이는 가로구역 최고높이 별도 확인)"
            ),
            "approximation": "far-bcr-floorcap",
            "assumptions": [
                "정북일조 미적용 용도지역 — 용적률/건폐율만 적용",
                "가로구역별 최고높이 별도 확인 필요",
            ],
        }

    # ── 정북일조 스트립 적분 ──
    usable_W = max(0.0, W - 2 * side_setback_m)
    strips = 200
    dz = D / strips
    envelope_volume = 0.0
    max_h = 0.0
    for i in range(strips):
        d = (i + 0.5) * dz  # 정북 경계로부터 거리
        if d < 1.5:
            h = 0.0
        else:
            # 10m 초과는 H/2 이격 → H ≤ 2d (보수적). 10m 이하는 1.5m 이격으로 허용(공용 산식).
            h = max_height_for_north_distance_m(d)
        max_h = max(max_h, h)
        envelope_volume += usable_W * dz * h

    # 인벨로프 연면적(전부 채움 가정) = 볼륨/층고. 건폐율로 층당 바닥 상한 반영(개략).
    envelope_gfa = envelope_volume / fh
    effective_gfa = min(envelope_gfa, far_gfa)
    binding = "정북일조" if envelope_gfa < far_gfa else "용적률"
    loss = max(0.0, 1 - envelope_gfa / far_gfa) * 100 if far_gfa > 0 else 0.0
    # 현실 층수: 유효 연면적 ÷ 건폐율 바닥(전층 동일 가정 근사). ★ceil — 연면적을 '담는 데 필요한' 최소 층수
    # (round 내림 시 4.167→4층이 되어 표시 연면적을 담지 못하는 과소산정. 올림이어야 5층이 effective_gfa 수용).
    realistic_floors = max(1, math.ceil(effective_gfa / bcr_footprint)) if bcr_footprint > 0 else 1
    daylight_ceiling_floors = max(1, int(max_h / fh))

    # ── 정밀 층수 시뮬레이션(계단식 단면 근사) ──
    # arithmetic_min_floors: '건폐율 만충 산술 하한'(법적 개념 아님 — 유효 연면적을 담는 최소 층수).
    arithmetic_min_floors = realistic_floors
    # 실무 권장 범위: 쾌적 건폐율 가정으로 far_p(현실 용적률%)를 나눠 층수 추정.
    # 분모는 기본 30/20(기존 동작 보존), objective 있으면 건축유형별로 조정(무회귀).
    far_p = far * 100.0
    recommended_floors_low = max(
        arithmetic_min_floors, min(daylight_ceiling_floors, round(far_p / comfort_bcr_low))
    )
    recommended_floors_high = max(
        recommended_floors_low, min(daylight_ceiling_floors, round(far_p / comfort_bcr_high))
    )
    # 계단식 단면의 북측 최저 층수: 정북 경계 최소이격(1.5m)에서 허용 높이/층고.
    floors_at_north_edge = max(1, int(max_height_for_north_distance_m(1.5) / fh))
    # 단면 최고 층수(남측 계단식 후퇴 시 사선 최고선) = 일조 사선 한도 층수.
    floors_at_deep = daylight_ceiling_floors
    floor_profile_note = (
        f"정북 경계측 약 {floors_at_north_edge}층 → 남측 계단식 후퇴 시 최대 {floors_at_deep}층 "
        f"(층고 {round(fh, 2)}m 기준·직사각 근사·추정)."
    )

    # 공동주택 인동간격(채광 방향): 건축법 시행령 §86② — 통상 0.8H(무창벽 0.5H).
    realistic_height = realistic_floors * fh
    min_spacing_080 = round(0.8 * realistic_height, 1)
    min_spacing_050 = round(0.5 * realistic_height, 1)
    shadow = shadow_analysis(realistic_height, latitude)  # 동지 일영(그림자) 분석

    # 시니어 설계에이전트 교차검증(best-effort — 실패 시 None, envelope 흐름 무영향).
    # ★shadow_analysis 는 연속 일조 '분'을 산출하지 않으므로 winter_daylight_continuous_min 키는 생략.
    senior_architect_review = _senior_architect_review(
        building_height_m=recommended_floors_high * fh,
        north_distance_m=1.5,
        winter_daylight_continuous_min=None,
    )

    return {
        "applies_north_light": True,
        "min_building_spacing_m": min_spacing_080,        # 동간 채광거리 권고(0.8H)
        "min_building_spacing_blank_wall_m": min_spacing_050,  # 무창벽 0.5H
        "shadow_analysis": shadow,                         # 동지 9·12·15시 그림자 길이
        "row_distance_rule": "건축법 시행령 §86② 채광 인동간격 0.8H(무창벽 0.5H) — 공동주택 다동 배치 시 적용",
        "zone": zone, "bcr_pct": round(bcr * 100, 1), "far_pct": round(far * 100, 1),
        "lot_width_m": round(W, 1), "lot_depth_m": round(D, 1),
        "far_gfa_sqm": round(far_gfa),
        "envelope_gfa_sqm": round(envelope_gfa),
        "effective_gfa_sqm": round(effective_gfa),
        "binding": binding,
        "daylight_loss_pct": round(loss, 1),
        "buildable_volume_m3": round(envelope_volume),
        "daylight_ceiling_m": round(max_h, 1),            # 정북일조 사선 최고선
        "daylight_ceiling_floors": daylight_ceiling_floors,
        "max_floors": realistic_floors,                    # 용적률·건폐율 기준 현실 층수(하위호환 유지)
        "max_height_m": round(realistic_floors * fh, 1),
        "bcr_footprint_sqm": round(bcr_footprint),
        # ── 정밀 층수 시뮬레이션(신규·추정) ──
        "arithmetic_min_floors": arithmetic_min_floors,    # 건폐율 만충 산술 하한(★법적 개념 아님)
        "recommended_floors_low": recommended_floors_low,  # 실무 권장 층수 하한(쾌적 건폐율 30% 가정·추정)
        "recommended_floors_high": recommended_floors_high,  # 실무 권장 층수 상한(쾌적 건폐율 20% 가정·추정)
        "floors_at_north_edge": floors_at_north_edge,      # 정북 경계 최소이격(1.5m)측 허용 층수(단면 최저·추정)
        "floors_at_deep": floors_at_deep,                  # 남측 계단식 후퇴 시 사선 최고선 층수(단면 최고·추정)
        "floor_height_m": round(fh, 2),                    # 사용된 층고(echo)
        "floor_profile_note": floor_profile_note,          # 계단식 단면 층수 프로파일 설명(추정)
        # 시니어 설계에이전트 교차검증(추정·best-effort, 실패 시 None).
        "senior_architect_review": senior_architect_review,
        "note": (
            "정북일조 사선(10m↓ 1.5m·10m↑ H/2 이격) 남북깊이 적분 최대 연면적. "
            f"공동주택 다동 배치 시 동간 채광거리 {min_spacing_080}m(0.8H) 확보 필요. "
            "도로사선제한은 2015년 폐지(가로구역별 최고높이로 대체)되어 미적용. "
            "직사각형 대지 근사(v1)."
            + (f" 일조로 용적률 대비 약 {round(loss,1)}% 건축면적 손실." if binding == "정북일조" else " 용적률이 한도(일조 여유).")
        ),
        "approximation": "rectangular-lot-strip-integration",
        "assumptions": [
            "직사각형 대지(W×D, 정북=깊이축) 가정",
            "단일 매스·측면 이격 간이(side_setback)",
            "10m 초과 H≤2d 보수 근사·도로사선 미적용",
            "arithmetic_min_floors=건폐율 만충 산술 하한(법적 개념 아님)",
            "recommended_*·floors_at_*·senior_architect_review=실무 추정/근사(계단식 단면)",
        ],
    }
