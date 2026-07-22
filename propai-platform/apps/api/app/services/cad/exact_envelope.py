"""3D exact solid Envelope — 정북사선 half-space × footprint의 해석적 prism 교차(W3-2·P7).

기존 solar_envelope_service의 인벨로프는 2D 근사다(직사각 대지 W×D를 깊이축으로
200분할해 각 스트립의 사선 허용높이를 곱해 더하는 Riemann sum — bbox 개산 + 정북사선
스트립 적분). 이 모듈은 그 갭(exact solid 차감 부재)을 메운다: footprint 폴리곤
(shapely — 실측 부정형 필지도 지원)과 '높이 z의 함수인 half-space'(정북사선·측면이격·
절대높이)를 교차시켜 체적·층별 유효 폴리곤·제약별 차감체적을 해석적으로 산출한다.

── 수학적 정당성(스파이크에서 확정) ──────────────────────────────────────
건축법 시행령 §86①의 정북사선은 '높이 z에서 정북 경계로부터 필요한 최소거리' g(z)로
표현하면 z에 대해 구간별 선형(piecewise-linear)이다:
    g(z) = 1.5m         (z ≤ 10m)
    g(z) = z/2           (z > 10m)      # sunlight_setback.required_north_setback_m과 동일 산식
g(z)는 z에 대해 단조증가(구간 [0,10]에서 상수, (10,∞)에서 기울기 1/2 — 10m 지점에서
1.5m→5m로 불연속 도약. 이는 근사의 결함이 아니라 실제 법조문의 성질이다: 10m 초과분은
'절반'이 아니라 '해당 높이의 절반'이라 임계점에서 요구 이격이 도약한다).
g가 단조증가라는 것은 곧 '허용영역(북측 경계에서 g(z) 이상 떨어진 영역)'이 z가 커질수록
집합적으로 단조 축소함을 뜻한다(포함관계 A(z2)⊆A(z1) for z2>z1) — 구멍/역전 없는 진짜
prismatoid(수직 단면이 위로 갈수록만 줄어드는 입체)가 된다. 이 성질이 이 모듈의 solid
표현이 타당함을 보장한다(위상적으로 스위스치즈가 되거나 팽창하는 층이 나오지 않는다).

체적은 ∫₀^zmax A(z)dz. A(z)는 'footprint 폴리곤을 직선(반평면 경계)으로 자른 넓이'이므로,
그 직선의 위치가 z에 선형인 한 A(z)는 z의 구간별 이차식(quadratic)이다(고전적 사실 —
자르는 직선 위치의 미분은 그 높이에서의 폭이고, 폭은 정점 사이에서 직선(폴리곤 변)이라
폭의 원시함수인 넓이는 이차식). 폴리곤 정점의 y좌표가 sweep-line과 만나는 지점(및 z=10
임계)을 breakpoint로 미리 찾아 그 구간 안에서는 Simpson 3점 구적을 쓰면 이차식(3차 이하)
에 대해 Simpson은 수학적으로 '정확'하다(근사오차 0, 부동소수점 오차만 잔존) — 그래서
이 모듈은 '고정 슬라이스 수'의 근사가 아니라 '해석적 구간 적분'이다. 참고용 Riemann
기준값(round_trip_error_pct)도 함께 계산해 오차를 항상 명시한다.

── 의존성 조사(스파이크) ──────────────────────────────────────────────
trimesh/CGAL/pyvista/open3d 등 3D solid 라이브러리는 레포 전체에 없다(requirements.txt·
pyproject.toml grep 확인 — 신규 의존성 0 유지). shapely(기존 의존성, cad 여러 서비스가
이미 사용)만으로 '높이 슬라이스별 2D 폴리곤 스택'을 해석적으로 표현하면 충분하다 — 사선이
z에 선형인 half-space라는 성질 덕분에 3D 메시 라이브러리가 애초에 불필요하다.

★무날조: 완화(conditional) 변형은 코드베이스에 실재하는 근거(건축법 §61 단서 — 2 이상의
  대지가 공동으로 조성되거나 건축협정을 체결한 경우 정북일조 사선 미적용)만 사용하고,
  호출자가 명시적으로 joint_development_agreement=True를 넘기지 않으면 base와 동일하다
  (가짜 완화를 임의로 만들지 않는다).

신규 의존성 0: shapely(기존)만 사용.
"""

from __future__ import annotations

from typing import Any

from app.services.common.sunlight_setback import (
    NORTH_SETBACK_HEIGHT_THRESHOLD_M,
    NORTH_SETBACK_MIN_LOW_M,
)

# 정북사선 절반 기울기(건축법 시행령 §86① — 10m 초과분은 '해당 부분 높이의 1/2').
_NORTH_SLOPE = 0.5

# Riemann 참조 구적 스텝(오차 명시용 — 기존 2D 근사의 200분할과 유사 규모, 주 계산경로는
# 아니고 round_trip_error_pct 보고 전용).
_REFERENCE_STEPS = 150


def north_light_min_distance_m(
    z_m: float,
    *,
    threshold_m: float = NORTH_SETBACK_HEIGHT_THRESHOLD_M,
    min_low_m: float = NORTH_SETBACK_MIN_LOW_M,
    slope: float = _NORTH_SLOPE,
) -> float:
    """높이 z에서 정북사선이 요구하는 '북측 경계로부터 최소거리' g(z).

    sunlight_setback.required_north_setback_m과 동일 산식(단일 출처 재사용 — z≤threshold는
    상수 min_low_m, 초과분은 slope*z). 대칭적으로, distance_m ≥ g(z)인 지점만 높이 z에서
    건축 가능하다.
    """
    z = max(0.0, float(z_m))
    if z <= threshold_m:
        return min_low_m
    return slope * z


def build_footprint_polygon(footprint: dict[str, Any]) -> tuple[Any, float, bool]:
    """footprint 입력 dict → (shapely Polygon, 북측경계 y좌표, 직사각형 여부).

    두 형태 지원:
      - {"width_m","depth_m"}: 기존 solar_envelope 관례(직사각 대지 근사) — 남서 모서리
        원점(0,0), 북측 경계 y=depth_m(정북=+y, 기존 dims_from_polygon의 위도증가=북쪽
        관례와 정합).
      - {"polygon": [[x,y],...]}: 실측 부정형 필지(로컬 미터 평면, y=북쪽 증가). 북측
        경계 y좌표 = 폴리곤 bounds의 maxy(해당 대지에서 가장 북쪽 지점 — 정북사선은
        이 site 자체의 북측 경계선에서 재는 것이지 이웃 대지 형상과 무관).
    """
    from shapely.geometry import Polygon

    poly_coords = footprint.get("polygon")
    if poly_coords:
        coords = [(float(p[0]), float(p[1])) for p in poly_coords]
        poly = Polygon(coords)
        if not poly.is_valid or poly.is_empty:
            raise ValueError("footprint polygon이 유효하지 않습니다(자기교차 등)")
        return poly, poly.bounds[3], False

    width_m = float(footprint.get("width_m") or 0.0)
    depth_m = float(footprint.get("depth_m") or 0.0)
    if width_m <= 0 or depth_m <= 0:
        raise ValueError("footprint에 polygon 또는 width_m/depth_m(둘 다 양수)이 필요합니다")
    poly = Polygon([(0.0, 0.0), (width_m, 0.0), (width_m, depth_m), (0.0, depth_m)])
    return poly, depth_m, True


def _apply_side_setback(poly: Any, is_rect: bool, side_setback_m: float) -> Any:
    """측면 이격 적용(동서측만 — 기존 solar_envelope usable_W=W-2*side_setback과 정합).

    직사각형(치수 입력)은 동서 변만 정확히 안쪽으로 당긴다(남북 방향은 정북사선이 따로
    처리하므로 이중 침식하지 않는다). 실측 부정형 폴리곤은 어느 변이 '측면'인지 기하적으로
    특정하기 어려워 전 둘레 균등 buffer(-side_setback_m)로 근사한다(한계 — assumptions에 표기).
    """
    if side_setback_m <= 0:
        return poly
    from shapely.geometry import Polygon

    if is_rect:
        minx, miny, maxx, maxy = poly.bounds
        new_minx, new_maxx = minx + side_setback_m, maxx - side_setback_m
        if new_maxx <= new_minx:
            return Polygon()
        return Polygon([(new_minx, miny), (new_maxx, miny), (new_maxx, maxy), (new_minx, maxy)])
    return poly.buffer(-side_setback_m, join_style=2)


def _clip_by_north(poly: Any, north_boundary_y: float, min_distance_m: float) -> Any:
    """footprint ∩ {북측 경계로부터 거리 ≥ min_distance_m} — half-plane 클리핑(정확·근사 없음)."""
    if poly.is_empty:
        return poly
    from shapely.geometry import Polygon, box

    y_cut = north_boundary_y - min_distance_m
    minx, miny, maxx, maxy = poly.bounds
    if y_cut >= maxy - 1e-9:
        return poly
    if y_cut <= miny + 1e-9:
        return Polygon()
    clip = box(minx - 1.0, miny - 1.0, maxx + 1.0, y_cut)
    return poly.intersection(clip)


def footprint_polygon_at_height(
    base_footprint: Any,
    north_boundary_y: float,
    z_m: float,
    *,
    applies: bool = True,
    threshold_m: float = NORTH_SETBACK_HEIGHT_THRESHOLD_M,
    min_low_m: float = NORTH_SETBACK_MIN_LOW_M,
    slope: float = _NORTH_SLOPE,
) -> Any:
    """높이 z에서 실제 건축 가능한 footprint 폴리곤(정북사선 half-plane 클리핑 반영).

    property test 등 외부 검증이 재구성할 수 있도록 공개 함수로 노출한다.
    """
    if not applies:
        return base_footprint
    g = north_light_min_distance_m(z_m, threshold_m=threshold_m, min_low_m=min_low_m, slope=slope)
    return _clip_by_north(base_footprint, north_boundary_y, g)


def _area_at(poly: Any, north_y: float, z: float, *, applies: bool, threshold_m: float, min_low_m: float, slope: float) -> float:
    return footprint_polygon_at_height(
        poly, north_y, z, applies=applies, threshold_m=threshold_m, min_low_m=min_low_m, slope=slope
    ).area


def _area_sloped(poly: Any, north_y: float, z: float, slope: float) -> float:
    """(threshold, z_cap] 구간 전용 넓이 평가 — g(z)=slope*z를 z 값과 무관하게 그대로 적용한다.

    north_light_min_distance_m(z)는 z==threshold_m에서 '<=' 비교로 완화쪽(1.5m, 법적으로
    정확 — 10m '이하' 부분은 여전히 1.5m 허용) 값을 돌려준다. 이는 '높이 z에서의 실제 허용
    영역'을 물을 땐 맞는 값이지만, (threshold, z_cap] 구간의 Simpson 구적은 그 구간에서
    area(z)가 g=slope*z(우극한)로 이어지는 이차식이라고 가정하고 세워진 것이라, 경계점
    z=threshold_m을 이 구간의 좌끝점으로 평가할 때는 완화쪽이 아니라 sloped 쪽 값(불연속
    도약 직후 값)을 써야 적분식이 정합한다(그렇지 않으면 Simpson이 존재하지 않는 함수를
    적분하게 되어 오차가 난다 — 실제로 발견·수정된 버그).
    """
    g = slope * max(0.0, z)
    return _clip_by_north(poly, north_y, g).area


def _polygon_vertex_ys(poly: Any) -> list[float]:
    """폴리곤(또는 buffer로 생긴 MultiPolygon)의 모든 외곽 정점 y좌표 — sweep breakpoint 후보."""
    from shapely.geometry import MultiPolygon, Polygon

    ys: list[float] = []
    geoms = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
    for g in geoms:
        if isinstance(g, Polygon) and not g.is_empty:
            ys.extend(y for _, y in g.exterior.coords)
    return ys


def _z_max_daylight(max_extent_m: float, threshold_m: float, min_low_m: float, slope: float) -> float:
    """footprint 내 '북측 경계로부터 최대거리'(max_extent) 기준, 정북사선이 허용하는 최고높이.

    max_extent보다 먼 지점이 없으므로 g(z) > max_extent가 되는 순간 area(z)=0(더 못 지음).
    g는 z≤threshold에서 상수 min_low_m, 초과분에서 slope*z이므로 역산은 두 경우로 나뉜다.
    """
    if max_extent_m <= min_low_m + 1e-9:
        return 0.0  # 대지 전체가 정북 최소이격보다 얕음 — 건축 불가
    cutoff = max_extent_m / slope
    return cutoff if cutoff > threshold_m else threshold_m


def _integrate_volume(
    poly: Any, north_y: float, z_cap: float,
    *, applies: bool, threshold_m: float, min_low_m: float, slope: float,
) -> tuple[float, list[float]]:
    """z=0..z_cap 체적을 해석적으로 적분한다.

    [0, min(threshold,z_cap)] 구간은 g(z) 상수라 area(z)도 상수 → 폭×넓이로 정확히 계산
    (구적 오차 0). (threshold, z_cap] 구간은 폴리곤 정점이 sweep-line과 만나는 z를
    breakpoint로 찾아 그 사이마다 Simpson 3점(구간 내 area(z)가 이차식이므로 완전히 정확
    — Simpson은 3차 이하 다항식에 대해 exact) 구적을 적용한다.
    """
    if not applies:
        return poly.area * z_cap, [0.0, z_cap]

    flat_top = min(threshold_m, z_cap)
    volume = 0.0
    if flat_top > 0:
        a_flat = _area_at(poly, north_y, 0.0, applies=applies, threshold_m=threshold_m, min_low_m=min_low_m, slope=slope)
        volume += a_flat * flat_top

    breakpoints = {flat_top, z_cap}
    if z_cap > threshold_m:
        minx, miny, maxx, maxy = poly.bounds
        for v in _polygon_vertex_ys(poly):
            if v <= miny + 1e-9 or v >= maxy - 1e-9:
                continue
            z_v = (north_y - v) / slope
            if threshold_m < z_v < z_cap:
                breakpoints.add(z_v)

    sloped_zs = sorted(z for z in breakpoints if z >= flat_top - 1e-9)
    for a, b in zip(sloped_zs, sloped_zs[1:], strict=False):
        if b - a <= 1e-9:
            continue
        mid = (a + b) / 2.0
        # ★sloped 전용 평가(_area_sloped) — north_light_min_distance_m의 z==threshold_m '<='
        # 경계 처리(완화쪽 1.5m)를 그대로 쓰면 불연속 도약 직전 값을 sloped 구간 좌끝점으로
        # 오적분하게 된다(발견된 버그 — 410㎥ 정답 대비 427.5㎥로 과대산정됐었다).
        fa = _area_sloped(poly, north_y, a, slope)
        fm = _area_sloped(poly, north_y, mid, slope)
        fb = _area_sloped(poly, north_y, b, slope)
        volume += (b - a) / 6.0 * (fa + 4 * fm + fb)

    return volume, sorted(breakpoints | {0.0})


def _riemann_reference(
    poly: Any, north_y: float, z_cap: float, steps: int,
    *, applies: bool, threshold_m: float, min_low_m: float, slope: float,
) -> float:
    """중점 Riemann sum 참조값 — 해석적 결과의 오차를 정직하게 보고하기 위한 대조군(주 계산경로 아님)."""
    if z_cap <= 0:
        return 0.0
    dz = z_cap / steps
    total = 0.0
    for i in range(steps):
        z = (i + 0.5) * dz
        total += _area_at(poly, north_y, z, applies=applies, threshold_m=threshold_m, min_low_m=min_low_m, slope=slope) * dz
    return total


def _floor_slices(
    poly: Any, north_y: float, z_cap: float, floor_height_m: float,
    *, applies: bool, threshold_m: float, min_low_m: float, slope: float,
) -> list[dict[str, Any]]:
    """층고 단위로 끊은 '계단식 단면' 층별 footprint 넓이(각 층의 z_top 기준 최소단면 — 단일
    평평한 바닥판이 그 층 구간 전체에서 사선을 넘지 않으려면 그 구간에서 가장 좁은(z_top)
    단면을 채택해야 하므로 — g(z) 단조증가·area(z) 단조비증가 성질에서 나오는 보수적 채택).
    체적 자체(volume_m3)는 이 계단식 근사가 아니라 _integrate_volume의 연속 해석적분이다.
    """
    floors: list[dict[str, Any]] = []
    z = 0.0
    idx = 0
    while z < z_cap - 1e-6:
        area_bottom = _area_at(poly, north_y, z, applies=applies, threshold_m=threshold_m, min_low_m=min_low_m, slope=slope)
        if area_bottom <= 0.05:
            break
        z_top_nominal = z + floor_height_m
        z_top = min(z_top_nominal, z_cap)
        partial = z_top < z_top_nominal - 1e-6
        eval_z = z_top if z_top < z_cap - 1e-6 else max(z, z_top - 1e-6)
        area_top = _area_at(poly, north_y, eval_z, applies=applies, threshold_m=threshold_m, min_low_m=min_low_m, slope=slope)
        idx += 1
        floors.append({
            "floor_index": idx,
            "z_bottom_m": round(z, 3),
            "z_top_m": round(z_top, 3),
            "footprint_area_sqm": round(area_top, 1),
            "gfa_sqm": round(area_top, 1),
            "partial": partial,
        })
        z = z_top
    return floors


def _compute(
    base_poly: Any, north_y: float, is_rect: bool,
    *, side_setback_m: float, nl_applies: bool, height_limit_m: float | None,
    threshold_m: float, min_low_m: float, slope: float, floor_height_m: float,
    with_reference: bool = False,
) -> dict[str, Any]:
    """단일 제약조합(측면이격·정북사선 적용여부·절대높이)에 대한 solid 산출(공용 코어)."""
    poly = _apply_side_setback(base_poly, is_rect, side_setback_m)
    if poly.is_empty:
        return {"volume_m3": 0.0, "max_height_m": 0.0, "gfa_sqm": 0.0, "num_floors": 0,
                "floors": [], "z_breakpoints": []}

    z_cap = height_limit_m
    if nl_applies:
        minx, miny, maxx, maxy = poly.bounds
        max_extent = north_y - miny
        z_daylight = _z_max_daylight(max_extent, threshold_m, min_low_m, slope)
        z_cap = z_daylight if z_cap is None else min(z_cap, z_daylight)

    if z_cap is None or z_cap <= 1e-9:
        return {"volume_m3": 0.0, "max_height_m": 0.0, "gfa_sqm": 0.0, "num_floors": 0,
                "floors": [], "z_breakpoints": []}

    volume, breakpoints = _integrate_volume(
        poly, north_y, z_cap, applies=nl_applies, threshold_m=threshold_m, min_low_m=min_low_m, slope=slope
    )
    floors = _floor_slices(
        poly, north_y, z_cap, floor_height_m,
        applies=nl_applies, threshold_m=threshold_m, min_low_m=min_low_m, slope=slope,
    )
    gfa = sum(f["footprint_area_sqm"] for f in floors)
    out: dict[str, Any] = {
        "volume_m3": round(volume, 3),
        "max_height_m": round(z_cap, 3),
        "gfa_sqm": round(gfa, 1),
        "num_floors": len(floors),
        "floors": floors,
        "z_breakpoints": [round(b, 3) for b in breakpoints],
    }
    if with_reference:
        ref = _riemann_reference(
            poly, north_y, z_cap, _REFERENCE_STEPS,
            applies=nl_applies, threshold_m=threshold_m, min_low_m=min_low_m, slope=slope,
        )
        err_pct = (abs(volume - ref) / ref * 100.0) if ref > 1e-9 else 0.0
        out["round_trip_reference_m3"] = round(ref, 3)
        out["round_trip_error_pct"] = round(err_pct, 4)
    return out


def build_exact_envelope(footprint: dict[str, Any], constraints: dict[str, Any]) -> dict[str, Any]:
    """footprint·제약(setback·높이상한·정북사선)에서 exact solid envelope 3종을 산출한다.

    footprint: {"width_m","depth_m"} 또는 {"polygon":[[x,y],...]} (build_footprint_polygon 참조).
    constraints:
      side_setback_m(측면 이격, 기본 0.5) · zone_min_setback_m(용도지역 법정 최소 이격 — 있으면
      conservative가 이 값과 side_setback_m 중 큰 쪽 채택) · height_limit_m(절대 높이상한,
      없으면 정북사선만으로 z_cap 결정) · floor_height_m(층고, 기본 3.0) ·
      north_light: {applies(기본 True), height_threshold_m, min_setback_low_m, slope} ·
      joint_development_agreement(bool, 기본 False — §61 단서: 공동조성/건축협정 시에만
      conditional에서 정북사선 미적용. 미지정이면 conditional==base, 날조 없음).

    반환: {conservative,base,conditional: {volume_m3,max_height_m,gfa_sqm,floors,...}},
    constraint_contributions(제약별 차감체적+offending face), approximation, assumptions.
    """
    try:
        base_poly, north_y, is_rect = build_footprint_polygon(footprint)
    except ValueError as exc:
        return {"error": str(exc)}

    side_setback_m = max(0.0, float(constraints.get("side_setback_m", 0.5) or 0.0))
    zone_min_setback_m = float(constraints.get("zone_min_setback_m") or 0.0)
    floor_height_m = max(2.4, float(constraints.get("floor_height_m", 3.0) or 3.0))
    height_limit_raw = constraints.get("height_limit_m")
    height_limit_m = float(height_limit_raw) if height_limit_raw else None

    nl_cfg = constraints.get("north_light") or {}
    nl_applies = bool(nl_cfg.get("applies", True))
    threshold_m = float(nl_cfg.get("height_threshold_m", NORTH_SETBACK_HEIGHT_THRESHOLD_M))
    min_low_m = float(nl_cfg.get("min_setback_low_m", NORTH_SETBACK_MIN_LOW_M))
    slope = float(nl_cfg.get("slope", _NORTH_SLOPE))
    joint_dev = bool(constraints.get("joint_development_agreement", False))

    if not nl_applies and height_limit_m is None:
        return {"error": "정북일조 미적용이면서 height_limit_m도 없으면 solid가 무한 체적이 됩니다"
                          "(절대 높이상한이 필요합니다)."}

    def _variant(kind: str) -> dict[str, Any]:
        if kind == "conservative":
            eff_side = max(side_setback_m, zone_min_setback_m)
            eff_nl = nl_applies
        elif kind == "conditional":
            eff_side = side_setback_m
            # §61 단서(건축법) — 2 이상 대지 공동조성 또는 건축협정 체결 시 정북사선 미적용.
            # 호출자가 명시적으로 전제조건을 확인(joint_development_agreement=True)했을 때만 완화.
            eff_nl = nl_applies and not joint_dev
        else:
            eff_side, eff_nl = side_setback_m, nl_applies
        out = _compute(
            base_poly, north_y, is_rect,
            side_setback_m=eff_side, nl_applies=eff_nl, height_limit_m=height_limit_m,
            threshold_m=threshold_m, min_low_m=min_low_m, slope=slope, floor_height_m=floor_height_m,
            with_reference=True,
        )
        out.update({"kind": kind, "side_setback_m": round(eff_side, 3), "north_light_applies": eff_nl})
        return out

    variants = {kind: _variant(kind) for kind in ("conservative", "base", "conditional")}
    base_v = variants["base"]
    v_full = base_v["volume_m3"]

    contributions: list[dict[str, Any]] = []
    if side_setback_m > 0:
        v_alt = _compute(
            base_poly, north_y, is_rect, side_setback_m=0.0, nl_applies=nl_applies,
            height_limit_m=height_limit_m, threshold_m=threshold_m, min_low_m=min_low_m,
            slope=slope, floor_height_m=floor_height_m,
        )["volume_m3"]
        contributions.append({
            "constraint": "side_setback", "label": "측면 이격거리",
            "removed_volume_m3": round(max(0.0, v_alt - v_full), 3),
            "offending_faces": ["east", "west"] if is_rect else ["perimeter"],
            "basis": "설계 기본 이격거리(대지경계선 이격 — 피난·통로 확보 관행)",
        })
    if nl_applies:
        if height_limit_m is not None:
            v_alt = _compute(
                base_poly, north_y, is_rect, side_setback_m=side_setback_m, nl_applies=False,
                height_limit_m=height_limit_m, threshold_m=threshold_m, min_low_m=min_low_m,
                slope=slope, floor_height_m=floor_height_m,
            )["volume_m3"]
            contributions.append({
                "constraint": "north_light", "label": "정북방향 일조 사선",
                "removed_volume_m3": round(max(0.0, v_alt - v_full), 3),
                "offending_faces": ["north"],
                "basis": "건축법 제61조·시행령 제86조 제1항(정북 인접대지경계선 일조 높이제한)",
            })
        else:
            # ★height_limit_m이 없으면 정북사선이 유일한 상한이라, 이를 제거한 대조 체적은
            #   무한(unbounded)이 된다 — _compute의 'z_cap 없음' 내부가드가 0을 돌려주는 것을
            #   '차감체적 0'으로 오독하면 안 되므로(정직성 위반), 계산불가로 정직 표기한다.
            contributions.append({
                "constraint": "north_light", "label": "정북방향 일조 사선",
                "removed_volume_m3": None,
                "offending_faces": ["north"],
                "basis": "건축법 제61조·시행령 제86조 제1항(정북 인접대지경계선 일조 높이제한) — "
                         "절대 높이상한이 없어 유일한 상한이라 제거 시 무한 체적(계산 불가·정직 표기)",
            })
        if height_limit_m is not None:
            v_alt = _compute(
                base_poly, north_y, is_rect, side_setback_m=side_setback_m, nl_applies=nl_applies,
                height_limit_m=None, threshold_m=threshold_m, min_low_m=min_low_m,
                slope=slope, floor_height_m=floor_height_m,
            )["volume_m3"]
            contributions.append({
                "constraint": "height_limit", "label": "절대 높이 상한(가로구역·용도지역)",
                "removed_volume_m3": round(max(0.0, v_alt - v_full), 3),
                "offending_faces": ["top"],
                "basis": "가로구역별 최고높이 또는 용도지역 절대높이 상한",
            })
    elif height_limit_m is not None:
        # 정북사선 미적용 + height_limit이 유일한 상한 → 이를 제거하면 무한 체적이라
        # 차감량을 낼 수 없다(가짜 값 금지 — 정직하게 '계산불가'만 표기).
        contributions.append({
            "constraint": "height_limit", "label": "절대 높이 상한(가로구역·용도지역)",
            "removed_volume_m3": None,
            "offending_faces": ["top"],
            "basis": "가로구역별 최고높이 또는 용도지역 절대높이 상한 — 유일한 상한이라 제거 시 "
                     "무한 체적(계산 불가·정직 표기)",
        })

    return {
        "variants": variants,
        "constraint_contributions": contributions,
        "approximation": "analytic-prismatoid-halfspace-intersection",
        "assumptions": [
            "정북=+y(대지 자체 북측 경계 y=north_boundary_y) — 실측 폴리곤은 dims_from_polygon과 "
            "동일한 위도증가=북쪽 관례",
            "측면 이격은 직사각형 입력만 동서변 정확 적용, 부정형 폴리곤은 전둘레 균등 buffer 근사",
            "정북사선 g(z)는 z=10m에서 1.5m→5m로 불연속 도약(법조문 자체의 성질·근사 아님)",
            "conditional은 joint_development_agreement=True를 명시한 경우에만 §61 단서(공동조성·"
            "건축협정) 완화를 적용 — 미지정 시 base와 동일(날조 없음)",
        ],
    }
