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
