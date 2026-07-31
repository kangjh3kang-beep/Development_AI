"""정북방향 일조 확보 이격(건축법 제61조·시행령 제86조 제1항) 공용 산식 — 단일 출처.

★현행(2023.9.12 개정): 전용/일반주거지역에서 정북방향 인접대지경계선으로부터
 - 높이 10m 이하 부분: 1.5m 이상
 - 높이 10m 초과 부분: 해당 부분 높이의 1/2 이상
개정 전 임계는 9m였다(→ 현행 10m). 이격 하한 1.5m는 건축조례로 가중 가능(여기선 법정 하한).

전 분석엔진(solar_envelope·auto_design·building_code_rules·building_compliance)은 정북일조
임계·이격을 반드시 이 모듈을 경유한다. 하드코딩 9m 금지 — 한 곳을 고치면 전역이 따라오게.
"""

from __future__ import annotations

# 건축법 시행령 제86조 제1항(2023.9.12 개정) 정북일조 적용 임계높이(m).
NORTH_SETBACK_HEIGHT_THRESHOLD_M = 10.0
# 임계높이 이하 부분의 정북 최소 이격(m). 조례로 1.5m 이상 가중 가능(기본=법정 하한).
NORTH_SETBACK_MIN_LOW_M = 1.5


# ── 적용 범위(건축법 §61 — 전용·일반주거지역) ────────────────────────────────────
# ★R1 HIGH-2 봉합: 이 판정이 저장소에 **네 벌** 있었다(auto_design_engine.SUNLIGHT_ZONES ·
#   massing_strategy._NORTH_LIGHT_ZONE_KEYWORDS · solar_envelope_service._NORTH_LIGHT_ZONES ·
#   site_layout_service). 게다가 실제로 **발산**했다 — 코드형("2R","1R")을 한쪽만 인식해
#   같은 필지가 지도에서는 정북 적용, 일조 인벨로프에서는 미적용으로 갈렸다(프론트가
#   `zoneType`에 `zoneCode`를 넣는 경로가 여러 곳이라 실제로 도달한다).
#   이 모듈 docstring이 이미 "전 분석엔진은 이 모듈을 경유한다"고 선언하므로 여기로 모은다.
_NORTH_LIGHT_ZONE_CODES = frozenset({"1R", "2R", "3R"})
# ★오탐 방지(R1 MEDIUM-3): "제2종근린생활시설"·"제2종지구단위계획구역"처럼 **주거가 아닌**
#   문자열이 "종"만으로 걸리면, 지도에 법적 금지구역을 잘못 칠한다. '주거'를 요구한다.
_NORTH_LIGHT_ZONE_KEYWORDS = ("전용주거", "일반주거")


def north_light_applies(zone_type: str | None) -> bool:
    """정북일조(건축법 §61)가 적용되는 용도지역인가 — **단일 판정 출처**.

    한글 명칭과 엔진 코드(1R/2R/3R) 양쪽을 받는다(호출자마다 어느 쪽을 주는지 일정하지 않다).

    ★판정 불가(빈 값)면 **False**를 돌려준다. 모르는 상태에서 '적용'으로 흘리면 없는 제약을
      보여주고, '미적용'으로 흘리면 있는 제약을 감춘다. 소비처는 이 False를 "적용 안 함"이
      아니라 **"판정 못 함"**으로 구분해 고지해야 한다(이 함수는 그 구분을 하지 않는다).
    """
    z = (zone_type or "").strip()
    if not z:
        return False
    if z.upper() in _NORTH_LIGHT_ZONE_CODES:
        return True
    return any(k in z for k in _NORTH_LIGHT_ZONE_KEYWORDS)


def required_north_setback_m(height_m: float, base_setback_m: float = 0.0) -> float:
    """건물(부분) 높이에 필요한 정북방향 최소 이격거리(m).

    높이 ≤ 10m → 1.5m, 초과 → 높이/2. base_setback_m(설계 기본 세트백)과 max.
    """
    h = max(0.0, float(height_m))
    req = NORTH_SETBACK_MIN_LOW_M if h <= NORTH_SETBACK_HEIGHT_THRESHOLD_M else h / 2.0
    return max(base_setback_m, req)


def max_height_for_north_distance_m(distance_m: float) -> float:
    """정북 경계로부터 거리 d에서 일조사선이 허용하는 최대 높이(m)의 보수적 근사.

    d ≥ 5m(=임계/2)면 높이 ≤ 2d, d < 5m면 임계높이(10m)까지 허용(d ≥ 1.5m 전제).
    = max(임계높이, 2d). solar_envelope 스트립 적분·하드캡 산정에 공용.
    """
    return max(NORTH_SETBACK_HEIGHT_THRESHOLD_M, 2.0 * float(distance_m))
