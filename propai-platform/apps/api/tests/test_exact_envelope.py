"""exact_envelope(W3-2: 3D exact solid Envelope) — 해석적 prism×정북사선 half-space 교차 검증.

검증 축:
  1) 폐형식(closed-form) 대조 — 직사각형 대지에서 손으로 유도한 정확한 적분값과 일치(무근사).
  2) round-trip — 참조 Riemann 구적(150분할)과의 오차가 명시된 한계(1%) 이내.
  3) property test — 결정론 격자 샘플점의 정북사선(g(z)) 제약 검사(내부면 만족, 경계 바로 바깥이면 위반).
     ★R1 정직 축소: side_setback·height_limit까지 포함한 "전 제약"이 아니라 정북사선 half-plane
     경계 하나만 검증한다(과대표기 금지).
  4) 3종 envelope(conservative/base/conditional) 차등·제약별 차감체적(offending face) 정합.
  5) 부정형 폴리곤 footprint 지원 + 무효입력 정직 에러.
  6) solar_envelope_service 배선(additive) — 기존 2D 근사 필드 무손상 + exact_envelope 병행노출.
"""

from __future__ import annotations

import math

from app.services.cad.exact_envelope import (
    build_exact_envelope,
    build_footprint_polygon,
    footprint_polygon_at_height,
    north_light_min_distance_m,
)

# ── 1) 폐형식 대조 ──────────────────────────────────────────────────────────


def test_rectangle_closed_form_deep_lot_matches_hand_derivation():
    """W=1(측면이격 0)·D=20(≥5) → V = D²+10 = 410 (손으로 유도한 정확 적분값).

    g(z)=1.5(z≤10)·z/2(z>10) 적분: ∫₀¹⁰1.5·dz는 아니라 실제로는 usable_W×(D-g(z))를
    z에 대해 적분한 것 — ∫₀^{2D}(D-g(z))dz = D²+10 (D≥5일 때, 본문 주석 유도 참고).
    """
    r = build_exact_envelope({"width_m": 1.0, "depth_m": 20.0}, {"side_setback_m": 0.0, "floor_height_m": 3.0})
    assert "error" not in r
    base = r["variants"]["base"]
    expected = 20.0**2 + 10.0
    assert math.isclose(base["volume_m3"], expected, rel_tol=1e-9), (base["volume_m3"], expected)
    assert math.isclose(base["max_height_m"], 2 * 20.0, rel_tol=1e-9)


def test_rectangle_closed_form_shallow_lot_flat_only():
    """W=1·D=3(1.5<D<5) → 정북사선이 10m까지는 상수(1.5m) 허용이라 V=(D-1.5)*10=15, 최고높이=10m."""
    r = build_exact_envelope({"width_m": 1.0, "depth_m": 3.0}, {"side_setback_m": 0.0, "floor_height_m": 3.0})
    base = r["variants"]["base"]
    assert math.isclose(base["volume_m3"], (3.0 - 1.5) * 10.0, rel_tol=1e-9)
    assert math.isclose(base["max_height_m"], 10.0, rel_tol=1e-9)


def test_rectangle_too_shallow_zero_volume():
    """D≤1.5(정북 최소이격) → 어떤 높이에서도 지을 수 없음(체적 0)."""
    r = build_exact_envelope({"width_m": 5.0, "depth_m": 1.0}, {"side_setback_m": 0.0})
    base = r["variants"]["base"]
    assert base["volume_m3"] == 0.0
    assert base["max_height_m"] == 0.0


# ── 2) round-trip: 해석적분 vs Riemann 참조 ──────────────────────────────────


def test_round_trip_error_within_documented_bound():
    """해석적(Simpson) 체적과 150분할 Riemann 참조값의 오차 — 명시 한계 1% 이내."""
    r = build_exact_envelope({"width_m": 12.0, "depth_m": 28.0}, {"side_setback_m": 1.0, "floor_height_m": 3.0})
    base = r["variants"]["base"]
    assert base["round_trip_error_pct"] < 1.0, base["round_trip_error_pct"]
    assert base["round_trip_reference_m3"] > 0


def test_round_trip_flat_only_zero_error():
    """전 구간이 상수(flat) 적분이면 참조 Riemann과 오차가 사실상 0(둘 다 정확한 상수 적분)."""
    r = build_exact_envelope({"width_m": 8.0, "depth_m": 4.0}, {"side_setback_m": 0.0})
    base = r["variants"]["base"]
    assert base["round_trip_error_pct"] < 0.01


# ── 3) property test: 결정론 격자 샘플점 경계 정확성 ──────────────────────────


def test_property_interior_points_satisfy_north_light_constraint_boundary_violates():
    """결정론 격자(무작위 아님)로 여러 (x,z) 조합을 순회 — 허용영역 내부점은 항상 정북사선
    최소거리 조건(g(z))을 만족하고, 그 바로 바깥(북쪽으로 살짝 더 가까운) 인접점은 위반한다.

    ★R1 정직 축소: 이 테스트는 '정북사선 제약'만 검사한다(side_setback·height_limit까지
    포함한 "전 제약 만족"이 아니다 — 과대표기 금지). footprint 자체는 side_setback 없이
    직접 구성한 순수 대지 폴리곤이라 side_setback 위반 여부는 이 테스트의 범위 밖이다.
    """
    footprint = {"width_m": 10.0, "depth_m": 20.0}
    base_poly, north_y, _ = build_footprint_polygon(footprint)

    z_values = [1.0, 5.0, 9.9, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0]  # 결정론 격자(threshold 안팎 포함)
    x_values = [0.5, 2.5, 5.0, 7.5, 9.5]  # 결정론 격자(동서 방향)

    for z in z_values:
        allowed = footprint_polygon_at_height(base_poly, north_y, z)
        if allowed.is_empty:
            continue
        # 구멍 폴리곤 방어 — half-plane 클리핑 결과가 무효(자기교차 등)가 되면 안 된다.
        assert allowed.is_valid, f"z={z} half-plane 클리핑 결과가 무효 폴리곤(구멍 등)이 됨"
        g = north_light_min_distance_m(z)
        for x in x_values:
            # 내부점: 북측 경계로부터 g+0.05m 확보 지점(허용영역 내부 — within이어야 함).
            y_interior = north_y - g - 0.05
            if y_interior < 0:
                continue
            interior_ok = allowed.contains(_point(x, y_interior)) or allowed.intersects(_point(x, y_interior))
            assert interior_ok, f"z={z} x={x} 내부점이 허용영역 밖으로 판정됨(경계 오류)"

            # 바로 바깥(북쪽으로 0.1m 더 가까운) 인접점: 반드시 위반(허용영역 밖).
            y_exterior = north_y - g + 0.1
            if y_exterior > north_y:
                continue
            exterior_violates = not allowed.contains(_point(x, y_exterior))
            assert exterior_violates, f"z={z} x={x} 경계 바로 바깥점이 여전히 허용됨(경계 오류)"


def _point(x: float, y: float):
    from shapely.geometry import Point

    return Point(x, y)


def test_property_area_monotonic_nonincreasing_with_height():
    """정북사선의 단조성(스파이크에서 확정한 수학적 정당성) — 높이가 높아질수록 허용영역
    면적은 절대 늘지 않는다(포함관계 A(z2)⊆A(z1), z2>z1)."""
    footprint = {"width_m": 15.0, "depth_m": 25.0}
    base_poly, north_y, _ = build_footprint_polygon(footprint)
    zs = [0.0, 2.0, 5.0, 9.9, 10.0, 10.1, 15.0, 20.0, 30.0, 40.0]
    areas = [footprint_polygon_at_height(base_poly, north_y, z).area for z in zs]
    for a_prev, a_next in zip(areas, areas[1:], strict=False):
        assert a_next <= a_prev + 1e-9, (areas,)


# ── 4) 3종 envelope 차등 + 제약별 차감체적 ────────────────────────────────────


def test_conservative_le_base_le_conditional_with_zone_and_joint_dev():
    footprint = {"width_m": 20.0, "depth_m": 30.0}
    constraints = {
        "side_setback_m": 0.5,
        "zone_min_setback_m": 3.0,           # 용도지역 법정 최소 이격(conservative가 채택)
        "height_limit_m": 60.0,              # 정북사선 제거 대조가 유한하도록(절대 상한 제공)
        "joint_development_agreement": True,  # §61 단서 — conditional에서 정북사선 미적용
    }
    r = build_exact_envelope(footprint, constraints)
    c, b, cond = r["variants"]["conservative"], r["variants"]["base"], r["variants"]["conditional"]
    assert c["volume_m3"] <= b["volume_m3"] <= cond["volume_m3"]
    assert c["side_setback_m"] == 3.0  # max(0.5, 3.0)
    assert cond["north_light_applies"] is False
    assert b["north_light_applies"] is True


def test_conditional_without_explicit_agreement_equals_base_no_fabrication():
    """joint_development_agreement 미지정(기본 False) → conditional은 base와 동일(완화 날조 금지)."""
    footprint = {"width_m": 20.0, "depth_m": 30.0}
    r = build_exact_envelope(footprint, {"side_setback_m": 0.5})
    b, cond = r["variants"]["base"], r["variants"]["conditional"]
    assert cond["volume_m3"] == b["volume_m3"]
    assert cond["north_light_applies"] == b["north_light_applies"] is True


def test_constraint_contributions_have_offending_faces():
    footprint = {"width_m": 20.0, "depth_m": 30.0}
    r = build_exact_envelope(footprint, {"side_setback_m": 1.0, "height_limit_m": 50.0})
    by_constraint = {c["constraint"]: c for c in r["constraint_contributions"]}
    assert by_constraint["side_setback"]["offending_faces"] == ["east", "west"]
    assert by_constraint["side_setback"]["removed_volume_m3"] >= 0
    assert by_constraint["north_light"]["offending_faces"] == ["north"]
    assert by_constraint["north_light"]["removed_volume_m3"] >= 0
    assert by_constraint["height_limit"]["offending_faces"] == ["top"]


def test_north_light_contribution_honestly_unbounded_without_height_limit():
    """height_limit_m 없이 정북사선만이 유일한 상한이면, 제거 시 무한체적이라 계산불가를
    정직하게(None) 표기해야 한다 — 임의로 0을 채워 '차감 없음'처럼 보이면 안 된다(무날조)."""
    footprint = {"width_m": 20.0, "depth_m": 30.0}
    r = build_exact_envelope(footprint, {"side_setback_m": 0.5})
    by_constraint = {c["constraint"]: c for c in r["constraint_contributions"]}
    assert by_constraint["north_light"]["removed_volume_m3"] is None
    assert "계산 불가" in by_constraint["north_light"]["basis"]


def test_conditional_unbounded_reports_none_not_zero_r1_repro():
    """★R1 HIGH 재현·회귀방지: joint_development_agreement=True(정북사선 해제)+height_limit_m
    미지정 조합에서 conditional 변형은 유일한 상한이 사라져 무한체적이 된다. 예전엔 내부
    z_cap-None 가드가 volume_m3=0.0을 반환해 base(17,290)≤conditional(0)이라는 불변식
    붕괴(가장 관대한 변형이 오히려 못 지음)를 유발했다 — 0이 아니라 unbounded=True·
    volume_m3=None으로 정직 표기해야 하고, base는 여전히 정상 유한값이어야 한다.
    """
    footprint = {"width_m": 20.0, "depth_m": 30.0}
    r = build_exact_envelope(footprint, {"side_setback_m": 0.5, "joint_development_agreement": True})
    base, cond = r["variants"]["base"], r["variants"]["conditional"]

    assert base["unbounded"] is False
    assert base["volume_m3"] is not None and base["volume_m3"] > 0

    assert cond["north_light_applies"] is False
    assert cond["unbounded"] is True
    assert cond["volume_m3"] is None, "무한체적을 0.0으로 오보고(R1 HIGH 회귀)"
    assert cond["max_height_m"] is None
    assert isinstance(cond.get("note"), str) and "무한" in cond["note"]

    # 숫자 비교(불변식 검사)는 None/unbounded를 반드시 제외해야 한다 — 포함시키면 비교 자체가 오류.
    numeric_volumes = [v["volume_m3"] for v in r["variants"].values() if not v.get("unbounded")]
    assert all(v is not None for v in numeric_volumes)
    assert base["volume_m3"] in numeric_volumes


# ── 5) 부정형 폴리곤 + 무효입력 ────────────────────────────────────────────────


def test_irregular_polygon_footprint_supported():
    """직사각형이 아닌 실측 부정형 필지(오각형)도 예외 없이 solid를 산출한다."""
    polygon = [(0, 0), (18, 0), (18, 22), (9, 30), (0, 22)]  # 오각형(북쪽으로 갈수록 좁아짐)
    r = build_exact_envelope({"polygon": polygon}, {"side_setback_m": 0.5, "floor_height_m": 3.0})
    assert "error" not in r
    base = r["variants"]["base"]
    assert base["volume_m3"] > 0
    assert base["round_trip_error_pct"] < 2.0  # 정점 breakpoint가 늘어 참조오차가 약간 더 클 수 있음


def test_invalid_footprint_returns_honest_error_not_exception():
    r1 = build_exact_envelope({}, {"side_setback_m": 0.5})
    assert "error" in r1
    r2 = build_exact_envelope({"width_m": 0, "depth_m": 10}, {})
    assert "error" in r2


def test_unbounded_without_north_light_or_height_limit_is_honest_error():
    r = build_exact_envelope(
        {"width_m": 10.0, "depth_m": 10.0},
        {"north_light": {"applies": False}},
    )
    assert "error" in r


# ── 6) solar_envelope_service 배선(additive) ─────────────────────────────────


def test_wired_into_solar_envelope_service_additive_no_regression():
    """기존 2D 근사 필드는 그대로 두고 exact_envelope만 병행 노출(무회귀)."""
    from app.services.site_score.solar_envelope_service import compute_buildable_envelope

    r = compute_buildable_envelope(
        land_area_sqm=11975, zone="제2종일반주거지역", bcr_limit_pct=60, far_limit_pct=250, floor_height_m=3.0
    )
    assert r["applies_north_light"] is True
    # 기존 키 무손상(회귀 없음).
    for k in ("envelope_gfa_sqm", "effective_gfa_sqm", "max_floors", "daylight_ceiling_m", "binding"):
        assert k in r

    ee = r.get("exact_envelope")
    assert ee is not None, "exact_envelope additive 필드가 배선되지 않음"
    assert ee["volume_m3"] > 0
    assert set(ee["variants"]) == {"conservative", "base", "conditional"}
    assert isinstance(ee["constraint_contributions"], list) and ee["constraint_contributions"]
    # ★R1 MEDIUM 수정: 단일 뭉뚱그린 필드(vs_2d_strip_approx_gfa_sqm_diff, 오표기) 대신
    # 층별 이산화 보수화분과 진짜 방법론 차이를 분리 노출 — 합치면 예전 단일값과 일치해야 한다.
    assert "exact_volume_vs_2d_gfa_diff" in ee
    assert "exact_floorstack_vs_2d_gfa_diff" in ee
    assert "vs_2d_strip_approx_gfa_sqm_diff" not in ee  # 오표기 필드 제거 확인
    recombined = ee["exact_volume_vs_2d_gfa_diff"] + ee["exact_floorstack_vs_2d_gfa_diff"]
    assert math.isclose(recombined, ee["gfa_sqm"] - r["envelope_gfa_sqm"], abs_tol=0.5)
    # 진짜 방법론 차이(exact 해석적분 vs 2D 스트립적분)는 작아야 한다(같은 물리적 envelope).
    assert abs(ee["exact_volume_vs_2d_gfa_diff"]) < 0.05 * r["envelope_gfa_sqm"]


def test_wired_service_non_north_light_zone_has_no_exact_envelope_key():
    """정북일조 미적용 분기(상업 등)는 exact_envelope 대상이 아니므로 키 자체가 없어야 한다
    (가짜/무의미한 값을 채우지 않는다)."""
    from app.services.site_score.solar_envelope_service import compute_buildable_envelope

    r = compute_buildable_envelope(land_area_sqm=11975, zone="일반상업지역", bcr_limit_pct=60, far_limit_pct=800)
    assert r["applies_north_light"] is False
    assert "exact_envelope" not in r
