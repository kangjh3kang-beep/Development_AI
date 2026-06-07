"""Flagship C-2 — 환경분석(일조·조망·스카이라인) 서비스 본체.

디지털트윈/부지 컨텍스트에서 다음을 **약식·정량** 분석한다(정밀 일조분석/측량 아님·참고용).

  - 일조(solar): 위도·날짜·시각별 천문식 **태양 고도/방위**(numpy만, 외부 천문 라이브러리 무관).
      대상 건물(층수×층고 또는 design_params)과 주변 footprint 압출로 **약식 일영(그림자) 가림
      판정** → 동지 9~15시 기준 일조시간 추정. 주거지역은 **정북 일조사선(건축법 제61조·
      동법 시행령 제86조)** 정량 검토(인접대지경계선 이격거리).
  - 조망(view): 건물 상부에서 주변 건물 높이·거리로 방위별 가림율 → 개방도 점수(0~100)·양호 방향.
  - 스카이라인(skyline): 대상 높이 vs 주변 평균/최고 → 돌출/조화/매몰 정성.

정직성(비협상): 태양위치=천문 근사식(대기굴절·지형 미반영), 주변건물 높이=footprint 추정,
일영=2D 평면투영 약식(실제 그림자·반사·계절변동 정밀 아님). 정북사선은 주거지역 기본 규정값
이며 지자체 조례·완화는 미반영. 전문가(건축사) 검토 필요.

재사용: terrain_service._resolve_location(좌표·필지·PNU), digital_twin.scene_service._build_neighbors
(주변 footprint ENU·추정고), zoning.auto_zoning_service(용도지역·높이한도).
"""
from __future__ import annotations

import asyncio
import math
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()

ENV_TIMEOUT_S = 88.0           # 90초 가드 직전
NEIGHBOR_TIMEOUT_S = 30.0
DEFAULT_FLOOR_HEIGHT_M = 3.3   # 층고 기본(주거 표준)
DEFAULT_FLOORS = 5            # design_params 미제공 시 가정 층수
WINTER_START_HOUR = 9        # 동지 일조시간 산정 구간(법정 일조권 검토 관행: 9~15시)
WINTER_END_HOUR = 15

SOURCES = [
    "좌표·필지·주변필지: VWorld(국토교통부 공간정보 오픈플랫폼)",
    "용도지역·높이한도: VWorld 토지특성/지적 + 국토계획법 제78조(auto_zoning)",
    "태양 위치: NOAA 천문 근사식(declination·equation of time·hour angle) — numpy 자체 계산",
    "정북 일조사선: 건축법 제61조·동법 시행령 제86조(전용·일반주거지역)",
]

# 24절기 대표일(분석 기준일). 동지를 기본으로 한다(최악 일조 조건).
SOLSTICE_DATES = {
    "winter": (12, 22),   # 동지 — 태양고도 최저(최악)
    "summer": (6, 21),    # 하지 — 최고
    "equinox": (3, 20),   # 춘분
}

# 계절 키 → 한글 라벨(요약·등급 표기 일관화)
SEASON_LABELS = {
    "winter": "동지",
    "summer": "하지",
    "equinox": "춘추분",
}

# 정북 일조사선 적용 용도지역(건축법 제61조: 전용·일반주거지역)
_NORTH_SETBACK_ZONES = (
    "전용주거", "일반주거",
)


def _day_of_year(month: int, day: int) -> int:
    """월·일 → 연중 일수(비윤년 기준, 태양 적위 근사에 충분)."""
    cum = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    return cum[month - 1] + day


def solar_position(lat_deg: float, day_of_year: int, hour_local: float,
                   lon_deg: float = 127.0, tz_offset_h: float = 9.0) -> tuple[float, float]:
    """태양 고도(altitude)·방위(azimuth)를 천문 근사식으로 계산(단위: 도).

    NOAA 기반 단순화: 적위(declination)·시간각(hour angle)·equation of time 반영.
    방위는 정북=0, 시계방향(동=90, 남=180, 서=270). 외부 라이브러리 없이 numpy/math만 사용.
    대기 굴절·지형 차폐는 미반영(약식).
    """
    lat = math.radians(lat_deg)
    # 적위(태양 황경 근사) — Cooper 식
    decl = math.radians(23.45) * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))
    # equation of time(분) — Spencer 근사
    b = math.radians(360.0 * (day_of_year - 81) / 364.0)
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    # 진태양시(solar time) = 지방표준시 + 경도보정 + EoT
    std_meridian = 15.0 * tz_offset_h          # KST 기준 자오선 135°E
    time_correction = 4.0 * (lon_deg - std_meridian) + eot   # 분
    solar_time = hour_local + time_correction / 60.0
    hour_angle = math.radians(15.0 * (solar_time - 12.0))    # 시간각(라디안)

    sin_alt = (math.sin(lat) * math.sin(decl)
               + math.cos(lat) * math.cos(decl) * math.cos(hour_angle))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    altitude = math.degrees(math.asin(sin_alt))

    # 방위각(정북 0, 시계방향) — 표준 천문 공식
    cos_alt = math.cos(math.asin(sin_alt))
    if abs(cos_alt) < 1e-6:
        azimuth = 180.0
    else:
        sin_az = -math.cos(decl) * math.sin(hour_angle) / cos_alt
        cos_az = (math.sin(decl) - math.sin(lat) * sin_alt) / (math.cos(lat) * cos_alt)
        sin_az = max(-1.0, min(1.0, sin_az))
        cos_az = max(-1.0, min(1.0, cos_az))
        azimuth = (math.degrees(math.atan2(sin_az, cos_az)) + 360.0) % 360.0
    return round(altitude, 2), round(azimuth, 2)


def _design_height_m(design_params: dict | None) -> tuple[float, int]:
    """design_params → (총 높이 m, 층수). height_m 우선, 없으면 floors×층고."""
    dp = design_params or {}
    floors = int(dp.get("floors") or DEFAULT_FLOORS)
    floors = max(1, floors)
    fh = float(dp.get("floor_height_m") or DEFAULT_FLOOR_HEIGHT_M)
    height = dp.get("height_m")
    if height:
        h = float(height)
    else:
        h = floors * fh
    return round(h, 2), floors


def _neighbor_polar(neighbors: list[dict[str, Any]]) -> list[dict[str, float]]:
    """주변 footprint(ENU [x=동, z=남]) → 대상(원점)에서 본 (방위·거리·높이) 극좌표 목록.

    각 이웃의 가장 가까운 꼭짓점 기준으로 거리·방위를 산정한다. 방위는 정북 0·시계방향.
    """
    out: list[dict[str, float]] = []
    for nb in neighbors:
        fp = nb.get("footprint_enu") or []
        if len(fp) < 3:
            continue
        h = float(nb.get("height_m") or 9.0)
        best_d = None
        best_az = 0.0
        for x, z in fp:
            d = math.hypot(x, z)
            if best_d is None or d < best_d:
                best_d = d
                # ENU: x=동, z=남(북이 -z). 방위(북0·시계) = atan2(동, 북) = atan2(x, -z)
                az = (math.degrees(math.atan2(x, -z)) + 360.0) % 360.0
                best_az = az
        if best_d is None or best_d < 0.5:
            continue
        out.append({"dist_m": round(best_d, 2), "azimuth_deg": round(best_az, 1), "height_m": h})
    return out


def _is_sun_blocked(sun_alt: float, sun_az: float, polar: list[dict[str, float]],
                    subject_top_m: float, az_tol_deg: float = 18.0) -> bool:
    """태양(고도·방위)이 주변 건물에 의해 가려지는지 약식 판정.

    대상 건물 상부(subject_top_m) 관측점에서, 태양 방위 ±tol 내 이웃 중 어떤 것이라도
    '이웃 상단 올려본각 > 태양 고도'이면 가림으로 본다(2D 평면투영 약식).
    """
    if sun_alt <= 0:
        return True  # 지평선 아래 = 일조 없음
    for nb in polar:
        daz = abs((nb["azimuth_deg"] - sun_az + 180.0) % 360.0 - 180.0)
        if daz > az_tol_deg:
            continue
        rel_h = nb["height_m"] - subject_top_m
        if rel_h <= 0:
            continue
        elev_to_top = math.degrees(math.atan2(rel_h, nb["dist_m"]))
        if elev_to_top > sun_alt:
            return True
    return False


def _north_setback(zone_type: str | None, height_m: float) -> dict[str, Any]:
    """정북 일조사선 검토(건축법 제61조·시행령 제86조). 전용/일반주거지역만 적용.

    규정: 높이 10m 이하 → 인접대지경계선에서 1.5m 이상,
          높이 10m 초과 → 해당 부분 높이의 1/2 이상 이격(정북방향).
    상업·공업·녹지 등 미적용은 명시.
    """
    zt = (zone_type or "").replace(" ", "")
    applies = any(k in zt for k in _NORTH_SETBACK_ZONES)
    if not applies:
        return {
            "applies": False,
            "detail": f"'{zone_type or '미상'}'은 정북 일조사선 적용 대상(전용·일반주거지역)이 "
                      f"아니거나 확인 불가 — 본 검토는 약식이며 지자체 조례를 확인하세요.",
        }
    if height_m <= 10.0:
        required = 1.5
        rule = "높이 10m 이하: 인접대지경계선에서 1.5m 이상 이격"
    else:
        required = round(height_m / 2.0, 2)
        rule = "높이 10m 초과: 해당 높이의 1/2 이상 이격"
    return {
        "applies": True,
        "required_m": required,
        "detail": f"정북방향 인접대지경계선에서 약 {required}m 이상 이격 필요 "
                  f"(건축법 제61조·시행령 제86조, {rule}). 지자체 조례·완화규정 미반영(약식).",
    }


def _solar_grade(sunlight_hours: float) -> str:
    """일조시간(9~15시·6시간 만점) 기준 정성 등급(동지=최악조건이 기준이나 선택 계절로 표기)."""
    if sunlight_hours >= 4.0:
        return "양호"
    if sunlight_hours >= 2.0:
        return "보통"
    return "불리"


def _compute_solar(lat: float, lon: float, zone_type: str | None,
                   subject_height_m: int, polar: list[dict[str, float]],
                   season: str) -> dict[str, Any]:
    """태양궤적(매시 정시)·일조시간(선택 계절 9~15시 약식)·정북사선 종합."""
    season_key = season if season in SOLSTICE_DATES else "winter"
    month, day = SOLSTICE_DATES[season_key]
    season_label = SEASON_LABELS[season_key]
    doy = _day_of_year(month, day)

    sun_positions: list[dict[str, float]] = []
    for hour in range(5, 20):  # 05~19시 정시(3D 렌더용 궤적)
        alt, az = solar_position(lat, doy, float(hour), lon_deg=lon)
        sun_positions.append({"hour": hour, "altitude_deg": alt, "azimuth_deg": az})

    # 일조시간: 동지 9~15시 30분 간격 표본 중 미가림 비율 → 시간 환산
    samples = 0
    sunny = 0
    step_min = 30
    h = WINTER_START_HOUR * 60
    end = WINTER_END_HOUR * 60
    while h <= end:
        hour_local = h / 60.0
        alt, az = solar_position(lat, doy, hour_local, lon_deg=lon)
        samples += 1
        if alt > 0 and not _is_sun_blocked(alt, az, polar, float(subject_height_m)):
            sunny += 1
        h += step_min
    span_h = WINTER_END_HOUR - WINTER_START_HOUR
    sunlight_hours = round((sunny / samples) * span_h, 2) if samples else 0.0

    north = _north_setback(zone_type, float(subject_height_m))
    grade = _solar_grade(sunlight_hours)
    blocked = samples - sunny
    max_alt = max(p["altitude_deg"] for p in sun_positions)
    summary = (
        f"{season_label}({month}/{day}) {WINTER_START_HOUR}~{WINTER_END_HOUR}시 기준 약 {sunlight_hours}시간 "
        f"일조 추정(표본 {samples}개 중 가림 {blocked}개). "
        f"태양 최대고도 약 {max_alt:.1f}°. "
        + ("정북 일조사선 적용 대상." if north["applies"] else "정북 일조사선 비적용/미상.")
    )
    return {
        "sun_positions": sun_positions,
        "season": season_key,
        "season_label": season_label,
        "sunlight_hours": sunlight_hours,
        # 하위호환: 기존 프론트(sunlight_hours_winter) 폴백 키 유지
        "sunlight_hours_winter": sunlight_hours,
        "max_altitude_deg": round(max_alt, 1),
        "north_setback": north,
        "summary": summary,
        "grade": grade,
    }


_COMPASS_16 = [
    ("북", 0.0), ("북북동", 22.5), ("북동", 45.0), ("동북동", 67.5),
    ("동", 90.0), ("동남동", 112.5), ("남동", 135.0), ("남남동", 157.5),
    ("남", 180.0), ("남남서", 202.5), ("남서", 225.0), ("서남서", 247.5),
    ("서", 270.0), ("서북서", 292.5), ("북서", 315.0), ("북북서", 337.5),
]


def _compute_view(polar: list[dict[str, float]], subject_top_m: float) -> dict[str, Any]:
    """건물 상부 개방도 분석 — 8방위 섹터별 최대 올려본각으로 가림율 산정.

    각 45° 섹터에서 가장 높이 올려본 이웃의 각도를 막힘으로 보고, 전체 개방도 점수(0~100)와
    방위별 양호(개방) 방향을 산출한다(약식 — 수목·지형·원경 미반영).
    """
    n_sectors = 8
    sector_block: list[float] = [0.0] * n_sectors  # 섹터별 최대 올려본각(도)
    for nb in polar:
        rel_h = nb["height_m"] - subject_top_m
        if rel_h <= 0:
            continue
        elev = math.degrees(math.atan2(rel_h, nb["dist_m"]))
        sec = int(((nb["azimuth_deg"] + 22.5) % 360.0) // 45.0)
        sector_block[sec] = max(sector_block[sec], elev)

    # 가림 정규화: 올려본각 0°=완전개방(1.0), 45°이상=완전가림(0.0)
    opennesses = [max(0.0, 1.0 - b / 45.0) for b in sector_block]
    openness_score = round(sum(opennesses) / n_sectors * 100.0, 1)
    blocked_ratio = round((1.0 - sum(opennesses) / n_sectors) * 100.0, 1)

    sector_names = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]
    ranked = sorted(range(n_sectors), key=lambda i: opennesses[i], reverse=True)
    best_directions = [sector_names[i] for i in ranked if opennesses[i] >= 0.6][:4]
    if not best_directions:
        best_directions = [sector_names[ranked[0]]]

    summary = (
        f"건물 상부({subject_top_m:.0f}m) 기준 개방도 약 {openness_score}/100"
        f"(가림율 {blocked_ratio}%). 양호 조망 방향: {', '.join(best_directions)}. "
        f"수목·지형·원경 미반영 약식."
    )
    return {
        "openness_score": openness_score,
        "best_directions": best_directions,
        "blocked_ratio_pct": blocked_ratio,
        "summary": summary,
    }


def _compute_skyline(subject_height_m: float,
                     neighbors: list[dict[str, Any]]) -> dict[str, Any]:
    """대상 높이 vs 주변 평균/최고 높이 → 돌출/조화/매몰 정성 판정."""
    heights = [float(nb.get("height_m") or 9.0) for nb in neighbors if nb.get("footprint_enu")]
    if heights:
        avg = round(float(np.mean(heights)), 2)
        mx = round(float(np.max(heights)), 2)
    else:
        avg = mx = 0.0

    if avg <= 0:
        position = "조화"
        detail = "주변 건물 데이터 부족 — 맥락 판단 보류."
    elif subject_height_m > mx * 1.3 or subject_height_m > avg * 2.0:
        position = "돌출"
        detail = "주변 대비 두드러지게 높음 — 경관 심의·조망 영향 검토 권장."
    elif subject_height_m < avg * 0.6:
        position = "매몰"
        detail = "주변 대비 낮아 조망·채광 불리 가능."
    else:
        position = "조화"
        detail = "주변 스카이라인과 대체로 조화."

    summary = (
        f"대상 {subject_height_m:.1f}m vs 주변 평균 {avg}m·최고 {mx}m → {position}. {detail}"
    )
    return {
        "subject_height_m": round(float(subject_height_m), 2),
        "neighbor_avg_m": avg,
        "neighbor_max_m": mx,
        "position": position,
        "summary": summary,
    }


async def analyze_environment(
    address: str | None,
    pnu: str | None,
    design_params: dict | None = None,
    season: str = "winter",
) -> dict[str, Any]:
    """환경분석 본체 — 좌표·필지·주변 → 일조·조망·스카이라인. 좌표/필지 불가→ok:false."""
    from app.services.digital_twin.scene_service import _build_neighbors
    from app.services.terrain.terrain_service import _resolve_location

    loc = await _resolve_location(address, pnu)
    if loc is None:
        return {
            "ok": False,
            "message": "주소/PNU로 좌표 또는 필지를 확인하지 못했습니다. 주소 또는 PNU를 확인하세요.",
            "sources": SOURCES,
        }

    lat, lon = loc["lat"], loc["lon"]
    resolved_pnu = loc.get("pnu")
    resolved_addr = loc.get("address") or address or ""

    # 용도지역(정북사선 적용 판정용)
    zone_type: str | None = None
    try:
        from app.services.zoning.auto_zoning_service import AutoZoningService
        az = await asyncio.wait_for(
            AutoZoningService().analyze_by_address(resolved_addr or (address or "")),
            timeout=30.0,
        )
        zone_type = az.get("zone_type")
    except Exception as e:  # noqa: BLE001
        logger.info("용도지역 조회 실패(정북사선 약식 처리): %s", str(e)[:150])

    # 주변 건물 footprint(ENU·추정고) — scene_service 재사용
    try:
        neighbors = await asyncio.wait_for(
            _build_neighbors(lat, lon, resolved_pnu),
            timeout=NEIGHBOR_TIMEOUT_S,
        )
    except Exception as e:  # noqa: BLE001
        logger.info("주변 건물 조회 실패: %s", str(e)[:150])
        neighbors = []

    height_m, floors = _design_height_m(design_params)
    polar = _neighbor_polar(neighbors)

    solar = _compute_solar(lat, lon, zone_type, int(round(height_m)), polar, season)
    view = _compute_view(polar, height_m)
    skyline = _compute_skyline(height_m, neighbors)

    return {
        "ok": True,
        "address": resolved_addr,
        "pnu": resolved_pnu,
        "zone_type": zone_type,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "subject": {"height_m": height_m, "floors": floors,
                    "neighbor_count": len(neighbors)},
        "solar": solar,
        "view": view,
        "skyline": skyline,
        "badges": {
            "note": "약식 계산·정밀 일조분석/측량 아님·참고용. 건축사 검토 필요.",
            "basis": [
                "태양 위치: NOAA 천문 근사식(대기굴절·지형차폐 미반영)",
                "일영: 주변 footprint 추정고 기반 2D 평면투영 약식",
                "정북 일조사선: 건축법 제61조 기본규정값(조례·완화 미반영)",
                "조망 개방도: 8방위 올려본각 약식(수목·원경 미반영)",
            ],
        },
        "sources": SOURCES,
    }
