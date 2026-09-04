"""Stage 4 — 토지모양·향·접도 기반 배치도(buildable footprint + 동배치) on 구역도.

목표 파이프라인 4단계: 토지 폴리곤(parcel geometry)·향·접도를 입력받아
① buildable footprint(세트백 오프셋) → ② 동배치 멀티오브젝티브 그리드샘플링
(일조준수율·조망개방성·yield) → ③ 구역도(parcel-boundaries) 위 배치도(GeoJSON)를 산출한다.

기존 직사각형 W×D solar_placement의 한계(부정형 폴리곤 미지원)를 폴리곤 기하로 확장한다.
계산·배치는 결정론(무거운 GA 회피·그리드 샘플링), LLM은 부지맞춤 미세조정 '조언'만.

좌표계: 입력 parcel geometry는 WGS84(경위도)다. 세트백·동치수는 미터이므로 대지 중심점
기준 국소 평면(equirectangular 근사)으로 투영해 shapely 미터 연산 후 WGS84로 역투영해
출력한다. 위도 35~38°(한국)에서 수십~수백 m 규모 오차는 무시 가능(배치 미리보기 정밀도).

무날조·정직: 폴리곤 미확보(geometry 없음)·shapely 미가용 시 honest 사유 + 빈 배치(가짜
배치 금지). v1 한계(축정렬 직사각형 동·균일 세트백·동지 일조 근사)를 honest 플래그로 표기한다.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# 국소 평면 투영 상수(WGS84 1도 ≈ m). 위도별 경도거리는 cos(lat)로 보정.
_M_PER_DEG_LAT = 110_540.0
_M_PER_DEG_LON_EQ = 111_320.0

# 동(건물 1개) 표준 풋프린트(m) — 유형별. massing_strategy 형상과 정합(판상=넓고얕게·타워=정방).
_SLAB_W_M, _SLAB_D_M = 40.0, 15.0      # 판상형 1동(동서로 길게·남북 얕게)
_TOWER_W_M, _TOWER_D_M = 22.0, 22.0    # 탑상형 1동(정방형 플레이트)
_FLOOR_HEIGHT_M = 3.0

# 세트백 기본값(m·보수). 도로/인접 대지경계 이격(건축법·조례 통념·미확인 시 보수 기본).
_DEFAULT_ROAD_SETBACK_M = 3.0
_DEFAULT_SIDE_SETBACK_M = 1.0

# GFA per 세대(㎡) — 동수·세대 추정(solar_placement와 동일 가정).
_GFA_PER_UNIT_SQM = 100.0


def _projector(lat0: float, lon0: float):
    """중심(lat0,lon0) 기준 국소 평면 투영기 closures 반환(to_local·to_wgs84)."""
    coslat = math.cos(math.radians(lat0)) or 1e-6

    def to_local(lon: float, lat: float) -> tuple[float, float]:
        return ((lon - lon0) * _M_PER_DEG_LON_EQ * coslat, (lat - lat0) * _M_PER_DEG_LAT)

    def to_wgs84(x: float, y: float) -> tuple[float, float]:
        return (lon0 + x / (_M_PER_DEG_LON_EQ * coslat), lat0 + y / _M_PER_DEG_LAT)

    return to_local, to_wgs84


def _largest_polygon(geom):
    """shapely geom에서 최대 면적 Polygon 추출(MultiPolygon 대응)."""
    gt = getattr(geom, "geom_type", "")
    if gt == "Polygon":
        return geom
    if gt in ("MultiPolygon", "GeometryCollection"):
        polys = [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
        if polys:
            return max(polys, key=lambda p: p.area)
    return None


def _parcel_to_local(parcel_geojson: dict[str, Any]):
    """parcel GeoJSON geometry → (shapely Polygon[m], to_wgs84, (lat0,lon0)). 실패 시 (None,..)."""
    from shapely.geometry import shape

    geom = shape(parcel_geojson)
    poly = _largest_polygon(geom)
    if poly is None or poly.is_empty:
        return None, None, None
    c = poly.centroid
    lat0, lon0 = c.y, c.x
    to_local, to_wgs84 = _projector(lat0, lon0)

    from shapely.geometry import Polygon

    ext = [to_local(x, y) for x, y in poly.exterior.coords]
    holes = [[to_local(x, y) for x, y in r.coords] for r in poly.interiors]
    local = Polygon(ext, holes).buffer(0)  # buffer(0)로 자가교차 보정
    return _largest_polygon(local) or local, to_wgs84, (lat0, lon0)


# ── 정북 일조 이격 밴드(W3-b) ────────────────────────────────────────────────────
# ★계획서 W3의 두 산출물 중 하나("정북 이격 필요 거리를 필지 위 반투명 밴드로")가 배치
#   미리보기(#506)에서 빠진 채 인도됐다. 그 갭을 메운다.
#
# ★무엇을 그리나: 정북일조 사선 때문에 **그 높이로는 지을 수 없는** 북측 띠다(금지 영역).
#   설계사가 "왜 북쪽이 비는가"를 지도에서 즉시 본다.
#
# ★정직 경계(전부 응답 note로 나간다):
#   ① 건축법 §61 정북일조는 **전용·일반주거지역에만** 적용된다 — 그 밖에서는 밴드를
#      만들지 않고 "미적용"이라고 말한다(빈 밴드를 0으로 그리면 "제약 없음"으로 오독된다).
#   ② 정북 경계를 **필지 북쪽 끝 직선**으로 근사한다(부정형 필지에서 실제 인접지 경계와
#      다를 수 있다). `exact_envelope`가 같은 근사를 쓰고 그 한계를 명시한 선례를 따른다.
#   ③ 이격 거리는 **선택한 대안의 높이**에 대한 값이다 — 높이가 바뀌면 밴드도 바뀐다.
# ★R1 HIGH-2 봉합: 적용 판정을 여기서 다시 구현하지 않는다. 공용 SSOT를 재수출만 한다
#   (기존 소비처·테스트의 import 경로를 깨지 않으면서 판정은 한 곳에서만 나오게 한다).
from app.services.common.sunlight_setback import north_light_applies  # noqa: E402


def compute_north_light_band(parcel_m, *, height_m: float, base_setback_m: float = 0.0):
    """그 높이로는 지을 수 없는 **북측 금지 띠**를 필지 안에서 잘라낸다.

    이격 거리는 공용 산식 SSOT(`common.sunlight_setback.required_north_setback_m`)를 그대로
    쓴다 — 같은 산식을 여기서 다시 구현하면 법 개정 시 한쪽만 바뀐다.

    @returns (band_polygon | None, required_distance_m). 필지 밖·빈 교집합이면 None.
    """
    from app.services.common.sunlight_setback import required_north_setback_m

    if parcel_m is None or parcel_m.is_empty:
        return None, 0.0
    d = required_north_setback_m(height_m, base_setback_m)
    if d <= 0:
        return None, 0.0

    from shapely.affinity import translate

    # ★R1 HIGH-3 봉합 — 전역 maxy 한 줄로 띠를 만들면 **L자·계단형 필지에서 위치 자체가
    #   틀린다**: 북으로 뻗은 팔에만 밴드가 생기고, 자기 정북 경계가 더 남쪽에 있는 다른 팔에는
    #   **0**이 된다(비보수적 과소). 내가 쓴 "부정형 필지도 그대로 따른다"는 거짓이었고,
    #   내 테스트가 북단이 하나뿐인 볼록 오각형이라 우연히 통과했다.
    #
    #   올바른 정의: 열 x마다 그 열의 **자기 북측 경계** maxY(x)에서 d 이내가 금지다.
    #   `parcel − (parcel를 남으로 d만큼 평행이동)`이 정확히 그 집합이다 —
    #   열 y∈[a,b]에서 이동본은 [a−d, b−d]이므로 차집합이 (b−d, b], 즉 그 열의 상단 d다.
    #   폭이 d보다 얇은 열은 통째로 금지가 된다(그 높이로는 못 짓는다 — 맞는 결과).
    band = parcel_m.difference(translate(parcel_m, yoff=-d))
    if band.is_empty or band.area <= 0:
        return None, d
    return band, d


def _to_geojson(geom_m, to_wgs84) -> dict[str, Any]:
    """shapely 미터 geom → WGS84 GeoJSON geometry."""
    from shapely.geometry import mapping
    from shapely.ops import transform

    return mapping(transform(lambda x, y, z=None: to_wgs84(x, y), geom_m))


def compute_buildable_footprint(parcel_m, setback_m: float):
    """대지 폴리곤(m)을 세트백만큼 내측 오프셋해 buildable footprint 반환(붕괴 시 None)."""
    if parcel_m is None or parcel_m.is_empty or setback_m <= 0:
        return parcel_m
    inner = parcel_m.buffer(-setback_m)
    inner = _largest_polygon(inner)
    if inner is None or inner.is_empty or inner.area <= 0:
        return None
    return inner


def _place_grid(buildable_m, bldg_w: float, bldg_d: float, spacing_m: float, angle_deg: float) -> list:
    """buildable 폴리곤 안에 (bldg_w×bldg_d) 직사각형 동을 angle 회전 격자로 배치.

    격자 회전: buildable 중심 기준으로 -angle 회전한 좌표계에서 축정렬 격자를 깔고, 각 칸을
    +angle 역회전해 원좌표로 되돌린 뒤 buildable.contains(완전 내포)만 채택한다.
    """
    from shapely.affinity import rotate
    from shapely.geometry import box

    # ★R2 HIGH-1 봉합 — 빈 영역이면 **여기서 끝낸다**. 정북 금지 띠를 차감하면 배치 영역이
    #   통째로 비는 필지가 실재하는데(세장 주거필지+고FAR), 빈 geometry의 `centroid.x`는
    #   shapely가 `GEOSException: getX called on empty Point`로 던져 라우터가 무가드라
    #   **프로덕션 500**이 됐다(실측 스윕 910건 중 62건). 배치 불가는 예외가 아니라 빈 결과다.
    if buildable_m is None or buildable_m.is_empty or buildable_m.area <= 0:
        return []
    cx, cy = buildable_m.centroid.x, buildable_m.centroid.y
    # 회전한 buildable의 bbox 위에서 격자 생성(역회전으로 원좌표 복귀).
    rot_inv = rotate(buildable_m, -angle_deg, origin=(cx, cy))
    minx, miny, maxx, maxy = rot_inv.bounds
    step_x = bldg_w + spacing_m
    step_y = bldg_d + spacing_m
    placed: list = []
    y = miny
    # 무한루프·과대격자 방지 상한.
    max_cells = 400
    while y + bldg_d <= maxy and len(placed) < max_cells:
        x = minx
        while x + bldg_w <= maxx and len(placed) < max_cells:
            cell = box(x, y, x + bldg_w, y + bldg_d)
            # 원좌표로 역회전(=+angle 회전) 후 내포 검사.
            cell_world = rotate(cell, angle_deg, origin=(cx, cy))
            if buildable_m.contains(cell_world):
                placed.append(cell_world)
            x += step_x
        y += step_y
    return placed


def _daylight_compliance(angle_deg: float, lat_deg: float) -> dict[str, Any]:
    """동의 장변 방위(남향 정렬도)로 일조준수 근사. angle=0(동서로 긺=남향) 최선."""
    from app.services.site_score.solar_placement_service import orientation_daylight

    # 동은 마주보는 두 장변 입면(법선이 180° 반대)을 갖는다. 채광에 유효한 '남향 입면'은
    # 둘 중 직사광이 많은 쪽이다 → 두 법선을 모두 평가해 더 밝은 쪽(남향 입면)을 채택한다.
    # 이로써 회전각 부호 규약과 무관하게 남향 입면 일조를 일관 산출한다(부호 모호성 제거).
    base = ((angle_deg + 90) % 180) - 90  # 장변 정렬 → 입면 법선 후보(-90~90)
    cand_a = orientation_daylight(base, lat_deg)
    cand_b = orientation_daylight(((base + 180 + 180) % 360) - 180, lat_deg)
    actual = cand_a if cand_a["direct_sun_hours"] >= cand_b["direct_sun_hours"] else cand_b
    south = orientation_daylight(0.0, lat_deg)
    # 일조권 충족 = orientation_daylight의 meets_daylight_right(09~15 연속2h 또는 08~16 총4h).
    return {
        "facade_facing_deg": round(actual["facing_deg"], 1),
        "direct_sun_hours": actual["direct_sun_hours"],
        "meets_sunlight": bool(actual.get("meets_daylight_right")),
        "longest_continuous_0915_h": actual.get("longest_continuous_0915_h"),
        "south_optimal_hours": south["direct_sun_hours"],
    }


def build_site_layout(
    *,
    parcel_geojson: dict[str, Any] | None,
    zone_type: str = "",
    building_type: str = "",
    far_pct: float | None = None,
    bcr_pct: float | None = None,
    land_area_sqm: float | None = None,
    latitude: float | None = None,
    road_setback_m: float | None = None,
    priority: str = "balanced",  # balanced | daylight | density
) -> dict[str, Any]:
    """토지 폴리곤 기반 동배치 배치도(여러 대안 + 최적안) 산출.

    Returns:
        {
          "ok": bool, "honest_notes": [..],
          "parcel_geojson": GeoJSON, "buildable_geojson": GeoJSON | None,
          "options": [{kind, angle_deg, buildings, floors, total_units, daylight,
                       yield_pct, openness_pct, score, buildings_geojson}],
          "best": option | None, "priority": priority,
        }
        폴리곤·shapely 미가용 시 ok=False·honest_notes(가짜 배치 금지).
    """
    notes: list[str] = [
        "v1 한계: 축정렬 직사각형 동·균일 세트백·동지 일조 근사. 부정형 정밀배치·3D 음영은 후속.",
    ]
    if not parcel_geojson:
        return {
            "ok": False,
            "honest_notes": ["토지 경계(폴리곤) 데이터 미확보 — 배치도 산출 불가(구획도 조회 필요)."],
            "parcel_geojson": None, "buildable_geojson": None,
            "options": [], "best": None, "priority": priority,
        }
    try:
        parcel_m, to_wgs84, latlon = _parcel_to_local(parcel_geojson)
    except Exception as e:  # noqa: BLE001 — 폴리곤 파싱 실패는 honest 처리
        logger.info("배치도 폴리곤 파싱 실패: %s", str(e)[:120])
        return {
            "ok": False,
            "honest_notes": [f"토지 경계 파싱 실패({str(e)[:80]}) — 배치도 산출 불가."],
            "parcel_geojson": parcel_geojson, "buildable_geojson": None,
            "options": [], "best": None, "priority": priority,
        }
    if parcel_m is None:
        return {
            "ok": False,
            "honest_notes": ["유효한 대지 폴리곤이 없습니다(빈 geometry)."],
            "parcel_geojson": parcel_geojson, "buildable_geojson": None,
            "options": [], "best": None, "priority": priority,
        }

    lat0 = latitude if latitude is not None else (latlon[0] if latlon else 37.5)
    parcel_area_m = parcel_m.area
    # 대지면적: 입력 우선(실효), 없으면 폴리곤 면적(국소투영 근사).
    area = land_area_sqm if (land_area_sqm and land_area_sqm > 0) else parcel_area_m
    # ★SSOT 정합 고지: 입력 대지면적과 폴리곤 실측이 크게 어긋나면 yield 산식(입력면적 목표)과
    #   배치(폴리곤) 기준이 달라 yield가 왜곡될 수 있으므로 정직 고지(무날조·다필지 면적 SSOT 패턴).
    if land_area_sqm and parcel_area_m > 0 and abs(area - parcel_area_m) / parcel_area_m > 0.2:
        notes.append(
            f"입력 대지면적({area:,.0f}㎡)과 폴리곤 실측({parcel_area_m:,.0f}㎡)이 괴리 — "
            "yield는 입력면적 목표 FAR 기준, 동배치는 폴리곤 기준입니다(면적 SSOT 확인 권장)."
        )

    # 세트백 → buildable footprint(균일 내측 오프셋). 도로+인접 보수 기본.
    setback = (road_setback_m if road_setback_m is not None else _DEFAULT_ROAD_SETBACK_M)
    setback = max(setback, _DEFAULT_SIDE_SETBACK_M)
    buildable_m = compute_buildable_footprint(parcel_m, setback)
    if buildable_m is None:
        return {
            "ok": False,
            "honest_notes": notes + [f"세트백 {setback:g}m 적용 후 가용 대지가 소멸(소규모·세장 필지)."],
            "parcel_geojson": _to_geojson(parcel_m, to_wgs84),
            "buildable_geojson": None, "options": [], "best": None, "priority": priority,
        }

    # 목표 연면적(가용 far)·건폐 상한(bcr) → 층수·동수 추정. 미상이면 통념 폴백.
    far = far_pct if (far_pct and far_pct > 0) else 200.0
    bcr = bcr_pct if (bcr_pct and bcr_pct > 0) else 60.0
    target_gfa = area * far / 100.0
    footprint_budget = area * bcr / 100.0  # 건폐율 상한 바닥면적(법적 제약)
    target_units = max(1, round(target_gfa / _GFA_PER_UNIT_SQM))

    # 유형별 동 풋프린트(판상/탑상). 빌라류는 판상만.
    bt = building_type or ""
    is_slab = ("빌라" in bt or "연립" in bt or "다세대" in bt or "도시형" in bt)
    kinds = [("판상형", _SLAB_W_M, _SLAB_D_M), ("탑상형", _TOWER_W_M, _TOWER_D_M)]
    if is_slab:
        kinds = [("판상형", _SLAB_W_M, _SLAB_D_M)]

    # 동 높이(층수) → 인동간격(채광 0.8H 통념). footprint_budget으로 동수 상한.
    options: list[dict[str, Any]] = []
    # 대지 주축 방위(min rotated rect 장변 각도) — 남향(0°)과 함께 후보.
    principal = _principal_angle(buildable_m)
    angle_candidates = sorted({0.0, round(principal, 1)})

    # ★W3-b: 정북일조 적용 여부는 **부지 단위**로 한 번 판정하고, 밴드 기하는 대안 높이별로
    #   계산한다. 미적용이면 두 값 모두 None/0으로 두고 note가 사유를 말한다(무날조).
    nl_applies = north_light_applies(zone_type)
    _nl_cache: dict[float, Any] = {}

    def _nl_band(h: float):
        if not nl_applies:
            return None
        if h not in _nl_cache:
            _nl_cache[h] = compute_north_light_band(parcel_m, height_m=h)[0]
        return _nl_cache[h]

    def _nl_place_area(h: float):
        """★R1 HIGH-1 봉합 — 정북 금지 띠를 **배치 영역에서 차감**한다.

        종전엔 밴드를 계산해 응답에 얹기만 하고 배치로 되먹이지 않았다. 그래서 같은 응답이
        "이 높이로 건축 불가"라고 칠한 자리에 그 높이의 건물을 그렸고(실측 겹침 80%),
        화면은 그 위에 "일조권 충족"이라고 썼다 — 밴드가 없던 때보다 나쁜 상태다
        (플랫폼이 자기 권장안의 위법을 그려놓고 적법하다고 말한다).

        밴드를 차감하면 겹침이 **구조적으로 0**이 되고, 계획서가 W3의 부수 효과로 적은
        "실효 건폐율 가시화"도 비로소 성립한다(FAR 미달은 note로 고지된다).
        """
        band = _nl_band(h)
        if band is None or band.is_empty:
            return buildable_m
        return buildable_m.difference(band)

    def _nl_distance(h: float) -> float | None:
        if not nl_applies:
            return None
        return round(compute_north_light_band(parcel_m, height_m=h)[1], 2)

    cap60_hit = False
    spacing_capped = False
    # 정북 금지 띠 때문에 표준 동을 못 앉힌 유형(사유 고지용 — 침묵하면 "왜 안 나오나"를 모른다).
    nl_blocked_kinds: set[str] = set()
    for kind, bw, bd in kinds:
        per_footprint = bw * bd
        # 건폐율 상한 → 동수 캡(총 바닥면적 ≤ footprint_budget). 법적 제약 준수.
        max_dongs_by_bcr = max(1, int(footprint_budget / per_footprint)) if per_footprint else 1
        for angle in angle_candidates:
            # ★인동간격↔층수 수렴 반복(법적 정합): 고층화하면 채광 인동간격(0.8H)이 커져 동수가
            #   줄고, 그러면 다시 더 고층화된다. 단일 동(인접 없음)이거나 간격이 최종 층수와
            #   정합될 때까지 재배치해, '배치된 간격 < 최종 층수의 0.8H' 위반(거짓 일조준수)을 막는다.
            spacing = round(max(6.0, 0.8 * max(3, min(40, round(far / 30))) * _FLOOR_HEIGHT_M), 1)
            buildings: list = []
            floors, n = 1, 0
            placed_spacing = spacing  # ★실제 배치에 쓰인 간격(기록·정합의 단일 진실)
            # ★정북 금지 띠를 뺀 실제 배치 가능 영역. 층수가 올라가면 띠가 넓어지므로
            #   간격↔층수와 **같은 루프에서 함께 수렴**시킨다(관용구 재사용).
            place_area = buildable_m
            nl_infeasible = False
            for _ in range(6):
                placed = _place_grid(place_area, bw, bd, spacing, angle)
                if not placed:
                    # ★띠를 차감한 뒤 못 앉으면 이 안은 정북일조 아래 **성립하지 않는다**.
                    #   여기서 그냥 break하면 이전 반복의 (띠를 모르는) 배치가 남아 위법 배치를
                    #   그대로 내보낸다 — 실제로 그렇게 겹침 80%가 유지됐다.
                    if place_area is not buildable_m:
                        buildings = []
                        nl_infeasible = True
                    break
                # 건폐율 초과분 절단 — 중심 근접 동 우선 유지(한쪽 모서리 편향 방지).
                if len(placed) > max_dongs_by_bcr:
                    bc = buildable_m.centroid
                    placed = sorted(placed, key=lambda b: b.centroid.distance(bc))[:max_dongs_by_bcr]
                n2 = len(placed)
                floors2 = max(1, min(60, math.ceil(target_gfa / max(1.0, per_footprint * n2))))
                buildings, floors, n, placed_spacing = placed, floors2, n2, spacing
                required = round(max(6.0, 0.8 * floors2 * _FLOOR_HEIGHT_M), 1)
                # 이 층수에 대응하는 금지 띠를 반영한 배치 영역(다음 반복의 입력).
                next_area = _nl_place_area(floors2 * _FLOOR_HEIGHT_M)
                area_changed = abs(next_area.area - place_area.area) > 1.0
                place_area = next_area
                spacing_ok = n2 <= 1 or required <= spacing + 0.5
                if spacing_ok and not area_changed:
                    break  # 간격·금지띠 모두 정합 → 종료
                if not spacing_ok:
                    spacing = required  # 더 큰 인동간격으로 재배치(최종 고층 반영)
            # ★R2 HIGH-2 봉합 — 루프가 **소진**되는 경로에도 같은 정합 검사가 필요하다.
            #   `if not placed` 경로의 스테일 배치만 막고 여기를 빠뜨렸더니, 진동(2-주기)으로
            #   비수렴 확정된 안에서 **배치 영역과 밴드가 불일치**해 겹침 33.75%가 살아남았다
            #   (n=1이면 floors↑→띠↑→2동→floors↓→띠↓→1동을 반복하고, `spacing_ok`가 n≤1이라
            #    항상 True·`area_changed`가 항상 True라 종료 조건이 영원히 성립하지 않는다).
            #   ★확정 층수의 띠를 기준으로 **다시 앉혀** 정합을 강제한다. 못 앉으면 그 안은
            #   정북일조 아래 성립하지 않으므로 버린다(위법 배치를 대안 목록에 올리지 않는다).
            if buildings and nl_applies:
                final_area = _nl_place_area(floors * _FLOOR_HEIGHT_M)
                refit = _place_grid(final_area, bw, bd, placed_spacing, angle)
                if len(refit) > max_dongs_by_bcr:
                    _c = final_area.centroid
                    refit = sorted(refit, key=lambda b: b.centroid.distance(_c))[:max_dongs_by_bcr]
                if not refit:
                    # ★미잠금 고지(정직): 이 분기와 아래 최종 정합 검증은 실측 1044 케이스에서
                    #   **한 번도 발화하지 않는다**(refit이 먼저 정합을 만든다). 그래서 이 두 줄을
                    #   지우는 변이가 테스트를 통과한다 — 잠긴 계약이 아니라 **미발화 방어층**이다.
                    #   숨기지 않고 적는다. 도달 케이스를 찾으면 그때 회귀락을 건다.
                    #   ★이 저장소에서 같은 결함 클래스(스테일 배치 잔존)를 이미 두 번 고쳤다
                    #   (`if not placed` 경로 · `for` 소진 경로). 여기가 세 번째 출구다.
                    buildings = []
                    nl_infeasible = True
                else:
                    buildings = refit
                    n = len(refit)
                    # 동수가 바뀌면 층수도 다시 산정한다(연면적 목표는 그대로).
                    floors = max(1, min(60, math.ceil(target_gfa / max(1.0, per_footprint * n))))
                    if n > 1:
                        _cap = max(1, int(placed_spacing / (0.8 * _FLOOR_HEIGHT_M)))
                        if floors > _cap:
                            floors = _cap
                            spacing_capped = True
                    place_area = final_area

            if not buildings:
                if nl_infeasible:
                    nl_blocked_kinds.add(kind)
                continue
            # ★법적 정합 보장(미수렴 케이스): 실제 배치 간격(placed_spacing)이 허용하는 최대
            #   층수로 캡한다. 다동(n>1)은 인동간격 0.8H가 높이를 제약하므로, 간격을 키워도
            #   재배치 못 한 미수렴 안은 '간격이 허용하는 높이'까지만 인정(거짓 일조준수 제거).
            #   단일동(n≤1)은 인접동이 없어 채광이격 무관 → 캡 미적용.
            spacing = placed_spacing  # 기록 간격 = 실제 배치 간격(과대표시 제거)
            if n > 1:
                floors_max_by_spacing = max(1, int(placed_spacing / (0.8 * _FLOOR_HEIGHT_M)))
                if floors > floors_max_by_spacing:
                    floors = floors_max_by_spacing
                    spacing_capped = True
            height_m = floors * _FLOOR_HEIGHT_M
            # ★최종 정합 검증(방어 심층) — 재배치로 층수가 다시 바뀔 수 있어 한 번의 fixpoint로는
            #   정합을 보장하지 못한다. **확정 높이의 띠**로 마지막에 검사해, 조금이라도 침범하면
            #   그 안을 버린다. 이 검사가 "밴드 안에는 단 한 동도 앉지 않는다"를 구조적으로 만든다
            #   (수렴이 실패해도 위법 배치가 목록에 오르지 않는다).
            if nl_applies:
                _fb = _nl_band(height_m)
                if _fb is not None and not _fb.is_empty:
                    _viol = sum(b.intersection(_fb).area for b in buildings)
                    if _viol > 1e-9:
                        nl_blocked_kinds.add(kind)
                        continue
            realized_gfa = n * per_footprint * floors
            if floors >= 60 and realized_gfa < target_gfa:
                cap60_hit = True
            yield_pct = round(min(100.0, realized_gfa / target_gfa * 100.0), 1) if target_gfa else 0.0
            day = _daylight_compliance(angle, lat0)
            # 조망개방성: 동이 차지하지 않은 가용 대지 비율(오픈스페이스).
            covered = sum(b.area for b in buildings)
            # ★분모는 **실제 배치 가능 영역**(정북 금지 띠 차감 후)이다. buildable 전체로 나누면
            #   지을 수 없는 띠까지 '오픈스페이스'로 계상돼 과대표시된다.
            _open_base = place_area.area if place_area.area > 0 else buildable_m.area
            openness_pct = round(max(0.0, (_open_base - covered) / _open_base * 100.0), 1)
            # 멀티오브젝티브 점수(우선순위별 가중).
            score = _score(yield_pct, day, openness_pct, priority)
            options.append({
                "kind": kind,
                "angle_deg": round(angle, 1),
                # 단일동(n≤1)은 인접동이 없어 인동간격 개념이 무의미 → None(오도 방지).
                "spacing_meaningful": n > 1,
                "buildings": n,
                "floors": floors,
                "height_m": round(height_m, 1),
                "spacing_m": spacing if n > 1 else None,
                # ★세대수 = 실현 연면적 / 세대당 면적(층바닥수 아님 — n·floors는 층바닥수다).
                "total_units_est": round(realized_gfa / _GFA_PER_UNIT_SQM),
                "daylight": day,
                "yield_pct": yield_pct,
                "openness_pct": openness_pct,
                "score": score,
                # ★W3-b: 이 대안의 **높이 기준** 정북 금지 띠. 대안마다 높이가 다르므로
                #   대안별로 계산한다(전역 1개면 토글할 때 틀린 밴드가 남는다).
                "north_light_band_geojson": (
                    _to_geojson(_nl_band(height_m), to_wgs84) if _nl_band(height_m) else None
                ),
                "north_light_setback_m": _nl_distance(height_m),
                "buildings_geojson": {
                    "type": "FeatureCollection",
                    "features": [
                        {"type": "Feature", "properties": {"dong": i + 1, "floors": floors},
                         "geometry": _to_geojson(b, to_wgs84)}
                        for i, b in enumerate(buildings)
                    ],
                },
            })
    if cap60_hit:
        notes.append("일부 안은 60층 상한으로 가용 용적률(FAR)을 다 소진하지 못합니다(yield<100%).")
    if spacing_capped:
        notes.append(
            "일부 안은 채광 인동간격(0.8H) 확보를 위해 층수를 제한했습니다 — 동수·간격↔높이 "
            "트레이드오프로 FAR를 다 못 채울 수 있습니다(필지 통합·단면 재검토 여지)."
        )

    options.sort(key=lambda o: o["score"], reverse=True)
    if not options:
        if nl_blocked_kinds:
            notes.append(
                "정북 일조 이격을 확보하면 표준 동이 들어가지 않습니다"
                f"({'·'.join(sorted(nl_blocked_kinds))}) — 남북 폭이 얕은 필지입니다. "
                "동 규모 축소·필지 통합·저층 계획을 검토하세요.",
            )
        else:
            notes.append("가용 대지에 표준 동(판상 40×15·타워 22×22)이 들어가지 않습니다(소규모·세장).")
    elif nl_blocked_kinds:
        notes.append(
            f"일부 유형({'·'.join(sorted(nl_blocked_kinds))})은 정북 일조 이격 확보 후 표준 동이 "
            "들어가지 않아 제외했습니다.",
        )

    # ★W3-b: 밴드의 한계·미적용 사유를 honest_notes로도 내보낸다 — 화면이 서버 note를 그대로
    #   고지하는 계약이라, 여기 없으면 사용자는 밴드가 없는 이유를 영영 모른다.
    if nl_applies:
        notes.append(
            "정북 일조 이격 밴드는 선택한 안의 높이 기준이며, 정북 경계를 필지 북쪽 끝 "
            "직선으로 근사했습니다(부정형 필지는 실제 인접지 경계와 다를 수 있습니다).",
        )
    elif zone_type:
        notes.append(
            "정북일조(건축법 §61)는 전용·일반주거지역에만 적용되어 이 부지에는 이격 밴드가 없습니다.",
        )
    else:
        notes.append("용도지역을 확인하지 못해 정북일조 적용 여부를 판정하지 못했습니다(밴드 미표시).")

    return {
        "ok": bool(options),
        "honest_notes": notes,
        "zone_type": zone_type,
        # ★W3-b: 정북일조 적용 여부와 근사 한계를 **응답 자체가** 말한다. 소비처가 판정
        #   로직을 재구현하면(용도지역 문자열 파싱 등) 서버와 화면이 갈라진다.
        "north_light": {
            "applies": nl_applies,
            "reason": (
                None if nl_applies
                else (
                    "정북일조(건축법 §61)는 전용·일반주거지역에만 적용됩니다."
                    if zone_type
                    else "용도지역을 확인하지 못해 정북일조 적용 여부를 판정할 수 없습니다."
                )
            ),
            "boundary_approximation": (
                "정북 경계를 필지 북쪽 끝 직선으로 근사했습니다(부정형 필지는 실제 인접지 "
                "경계와 다를 수 있습니다)." if nl_applies else None
            ),
        },
        "building_type": building_type,
        "land_area_sqm": round(area, 1),
        "parcel_area_sqm": round(parcel_area_m, 1),
        "far_pct": far,
        "bcr_pct": bcr,
        "target_units_est": target_units,
        "parcel_geojson": _to_geojson(parcel_m, to_wgs84),
        "buildable_geojson": _to_geojson(buildable_m, to_wgs84),
        "buildable_area_sqm": round(buildable_m.area, 1),
        "setback_m": setback,
        "options": options,
        "best": options[0] if options else None,
        "guidance": _layout_guidance(options[0] if options else None),
        "priority": priority,
    }


def _layout_guidance(best: dict[str, Any] | None) -> list[str]:
    """최적안 점수로 결정론 부지맞춤 가이던스(LLM 불필요·항상 가용·무날조)."""
    if not best:
        return ["가용 대지·동치수 제약으로 표준 배치가 어렵습니다. 소규모·세장 필지는 맞춤 단면 검토가 필요합니다."]
    g: list[str] = []
    d = best.get("daylight") or {}
    g.append(
        f"권장 배치: {best['kind']} {best['buildings']}개동·약 {best['floors']}층"
        f"(동지 직사광 {d.get('direct_sun_hours')}h, 일조권 {'충족' if d.get('meets_sunlight') else '미흡(향·간격 조정 필요)'})."
    )
    if best.get("yield_pct", 0) < 95:
        g.append(
            f"가용 용적률 소진 {best['yield_pct']}% — 대지 형상·세트백 제약으로 FAR를 다 못 채웁니다"
            "(동 형상·코어 효율·필지 통합 검토)."
        )
    else:
        g.append(f"가용 용적률 {best['yield_pct']}% 소진(목표 FAR 충족).")
    if not d.get("meets_sunlight"):
        g.append("동 장변을 남향(정남 0°)으로 정렬하거나 인동간격을 넓혀 동지 연속 2시간 일조를 확보하세요.")
    if best.get("openness_pct", 0) >= 70:
        g.append(f"오픈스페이스 {best['openness_pct']}% — 조경·통경축·커뮤니티 공간 확보에 유리합니다.")
    g.append("※ v1 결정론 배치 미리보기 — 정밀 동선·주차·부정형 정밀배치는 설계 단계에서 확정합니다.")
    return g


async def attach_layout_llm_advice(layout: dict[str, Any], *, use_llm: bool = False) -> dict[str, Any]:
    """LLM 부지맞춤 미세조정 '조언'(옵트인·graceful). 기하는 불변 — 조언만 가산.

    ★결정론 우선: 계산·배치는 결정론(build_site_layout)이고, LLM은 유기적 조언만 첨부한다.
    use_llm=False 또는 LLM 미가용 시 결정론 guidance만 유지(가짜 조언 금지).
    """
    if not use_llm or not layout.get("ok"):
        return layout
    try:
        from app.services.ai.llm_provider import get_llm

        llm = get_llm()  # 기본 프로바이더(anthropic). 키 미설정 시 ValueError → graceful.
        best = layout.get("best") or {}
        prompt = (
            "다음 부지 배치 분석(결정론 산출)을 보고, 한국 공동주택 설계 실무 관점에서 "
            "부지맞춤 미세조정 조언 3가지를 한국어로 간결히 제시하라(기하 수치는 바꾸지 말고 "
            "방향성만). 배치: "
            f"{best.get('kind')} {best.get('buildings')}동 {best.get('floors')}층, "
            f"일조 {(best.get('daylight') or {}).get('direct_sun_hours')}h, "
            f"yield {best.get('yield_pct')}%, openness {best.get('openness_pct')}%."
        )
        resp = await llm.ainvoke(prompt)
        text = getattr(resp, "content", None) or str(resp)
        if text:
            layout["llm_advice"] = str(text)[:1200]
    except Exception as e:  # noqa: BLE001 — LLM 조언 실패는 결정론 guidance 유지(무손상)
        logger.info("배치 LLM 조언 생략: %s", str(e)[:120])
    return layout


def _principal_angle(poly) -> float:
    """폴리곤 주축(min rotated rectangle 장변) 방위각(deg, -90~90). 격자 정렬 후보."""
    try:
        mrr = poly.minimum_rotated_rectangle
        xs, ys = mrr.exterior.coords.xy
        # 첫 변 벡터의 각도(장변 근사).
        edges = []
        pts = list(zip(xs, ys, strict=False))
        for i in range(len(pts) - 1):
            dx = pts[i + 1][0] - pts[i][0]
            dy = pts[i + 1][1] - pts[i][1]
            edges.append((math.hypot(dx, dy), math.degrees(math.atan2(dy, dx))))
        if not edges:
            return 0.0
        _, ang = max(edges, key=lambda e: e[0])
        return ((ang + 90) % 180) - 90
    except Exception:  # noqa: BLE001
        return 0.0


def _score(yield_pct: float, daylight: dict[str, Any], openness_pct: float, priority: str) -> float:
    """멀티오브젝티브 점수(0~100). 우선순위별 가중(일조·밀도·균형)."""
    day_hours = float(daylight.get("direct_sun_hours") or 0.0)
    opt_hours = float(daylight.get("south_optimal_hours") or 1.0) or 1.0
    day_pct = min(100.0, day_hours / opt_hours * 100.0)
    if priority == "daylight":
        w_yield, w_day, w_open = 0.25, 0.55, 0.20
    elif priority == "density":
        w_yield, w_day, w_open = 0.6, 0.2, 0.2
    else:  # balanced
        w_yield, w_day, w_open = 0.4, 0.35, 0.25
    return round(w_yield * yield_pct + w_day * day_pct + w_open * openness_pct, 1)
