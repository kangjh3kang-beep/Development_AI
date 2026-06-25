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
    from shapely.affinity import rotate, translate
    from shapely.geometry import box

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

    # 동의 '주 채광면'은 장변이 향하는 남/북. angle을 -90~90로 정규화해 남향 입면 방위로 사용.
    facing = ((angle_deg + 90) % 180) - 90  # 장변 정렬 → 채광면 방위 근사
    south = orientation_daylight(0.0, lat_deg)
    actual = orientation_daylight(facing, lat_deg)
    # 일조권 충족 = orientation_daylight의 meets_daylight_right(09~15 연속2h 또는 08~16 총4h).
    return {
        "facade_facing_deg": round(facing, 1),
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

    for kind, bw, bd in kinds:
        per_footprint = bw * bd
        # 인동간격 추정용 초기 층수(중층 가정). 이는 '간격 산정용 근사'일 뿐 최종 답이 아니다 —
        # 실제 배치 동수(N)가 정해지면 target_gfa를 충족하도록 층수를 재산정한다(아래).
        floors_guess = max(3, min(40, round(far / 30)))
        spacing = round(max(6.0, 0.8 * floors_guess * _FLOOR_HEIGHT_M), 1)  # 채광 0.8H(최소6m)
        # 건폐율 상한 → 동수 캡(총 바닥면적 ≤ footprint_budget). 법적 제약 준수.
        max_dongs_by_bcr = max(1, int(footprint_budget / per_footprint)) if per_footprint else 1
        for angle in angle_candidates:
            buildings = _place_grid(buildable_m, bw, bd, spacing, angle)
            if not buildings:
                continue
            # 건폐율 초과분은 절단(가장 먼저 배치된 동 우선 유지). 건폐율 준수 보장.
            if len(buildings) > max_dongs_by_bcr:
                buildings = buildings[:max_dongs_by_bcr]
            n = len(buildings)
            # ★실배치 동수로 층수 재산정: 적게 들어가면 그만큼 고층화해 FAR를 소진한다(타워 전략).
            #   60층 상한에 막혀 target을 못 채우면 yield<100%로 정직 표기(부지 제약).
            floors = max(1, min(60, math.ceil(target_gfa / max(1.0, per_footprint * n))))
            height_m = floors * _FLOOR_HEIGHT_M
            realized_gfa = n * per_footprint * floors
            yield_pct = round(min(100.0, realized_gfa / target_gfa * 100.0), 1) if target_gfa else 0.0
            day = _daylight_compliance(angle, lat0)
            # 조망개방성: 동이 차지하지 않은 가용 대지 비율(오픈스페이스).
            covered = sum(b.area for b in buildings)
            openness_pct = round(max(0.0, (buildable_m.area - covered) / buildable_m.area * 100.0), 1)
            # 멀티오브젝티브 점수(우선순위별 가중).
            score = _score(yield_pct, day, openness_pct, priority)
            options.append({
                "kind": kind,
                "angle_deg": round(angle, 1),
                "buildings": n,
                "floors": floors,
                "height_m": round(height_m, 1),
                "spacing_m": spacing,
                "total_units_est": min(target_units, n * floors),
                "daylight": day,
                "yield_pct": yield_pct,
                "openness_pct": openness_pct,
                "score": score,
                "buildings_geojson": {
                    "type": "FeatureCollection",
                    "features": [
                        {"type": "Feature", "properties": {"dong": i + 1, "floors": floors},
                         "geometry": _to_geojson(b, to_wgs84)}
                        for i, b in enumerate(buildings)
                    ],
                },
            })

    options.sort(key=lambda o: o["score"], reverse=True)
    if not options:
        notes.append("가용 대지에 표준 동(판상 40×15·타워 22×22)이 들어가지 않습니다(소규모·세장).")
    return {
        "ok": bool(options),
        "honest_notes": notes,
        "zone_type": zone_type,
        "building_type": building_type,
        "land_area_sqm": round(area, 1),
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
        pts = list(zip(xs, ys))
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
