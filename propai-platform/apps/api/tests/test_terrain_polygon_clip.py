"""P0 폴리곤 클립 계약 테스트 — 경사도·토공 격자를 필지 폴리곤 내부로 마스킹.

배경: terrain_service의 경사도/토공 격자(11×11)는 필지 bbox(외접 사각형)에 깔린다.
비정형(삼각형·L자) 필지는 bbox 모서리에 이웃 필지 지형이 들어와 평균경사도·토공량을
오염시킨다. 격자점 중 "필지 폴리곤 내부 점"만 마스킹해 집계하도록 개선했다.

원칙(비협상): 사각형(=bbox) 필지 무회귀, 내부 점 부족시 bbox 폴백(정직 강등),
developability 게이트는 이 파일과 무관(값 정확도만 개선 — 무날조).
"""
from __future__ import annotations

import numpy as np

from app.services.terrain import terrain_service as ts


# ── 순수 ray-casting 내부판정(shapely 미설치 폴백) ──


def _square_ring(mn_lon, mn_lat, mx_lon, mx_lat):
    return [
        (mn_lon, mn_lat), (mx_lon, mn_lat), (mx_lon, mx_lat),
        (mn_lon, mx_lat), (mn_lon, mn_lat),
    ]


def test_ray_cast_inside_square():
    ring = _square_ring(0.0, 0.0, 10.0, 10.0)
    assert ts._ray_cast_inside(5.0, 5.0, ring)       # 내부
    assert not ts._ray_cast_inside(15.0, 5.0, ring)  # 우측 밖
    assert not ts._ray_cast_inside(-1.0, 5.0, ring)  # 좌측 밖
    assert not ts._ray_cast_inside(5.0, 20.0, ring)  # 위쪽 밖


def test_ray_cast_inside_triangle():
    # (lon,lat) 좌하단 삼각형: lon>=0, lat>=0, lon+lat<=10 영역
    ring = [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0), (0.0, 0.0)]
    assert ts._ray_cast_inside(1.0, 1.0, ring)       # 내부(합=2)
    assert not ts._ray_cast_inside(9.0, 9.0, ring)   # 밖(합=18)


def test_ray_cast_degenerate_ring_false():
    assert not ts._ray_cast_inside(1.0, 1.0, [(0.0, 0.0), (1.0, 1.0)])


# ── 폴리곤 내부 마스크(shapely covers 우선, raycast 폴백) ──


def test_polygon_interior_mask_triangle_shape_and_exclusion():
    lat_axis = np.linspace(0.0, 10.0, 11)
    lon_axis = np.linspace(0.0, 10.0, 11)
    ring = [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0), (0.0, 0.0)]
    mask = ts._polygon_interior_mask(lat_axis, lon_axis, ring)
    assert mask is not None and mask.shape == (11, 11)
    # mask[r, c] ↔ (lat_axis[r], lon_axis[c]). 우상단 코너는 삼각형 밖.
    assert not mask[10, 10]   # lat=10, lon=10 → 합 20 > 10
    assert not mask[9, 9]     # lat=9, lon=9 → 합 18 > 10
    assert mask[1, 1]         # lat=1, lon=1 → 합 2 → 내부
    # 삼각형은 사각형의 절반 → 내부 점 대략 절반(경계 포함 여유 범위)
    assert 40 <= int(mask.sum()) <= 78


def test_polygon_interior_mask_axis_not_transposed():
    """비대칭(수평 밴드) 폴리곤으로 lat/lon(row/col) 전치 회귀를 방어.

    대칭 삼각형은 축을 뒤바꿔도 결과가 불변이라 전치 버그를 못 잡는다. lat∈[0,3]로
    좁은 수평 밴드를 쓰면 mask[r,c]↔(lat_axis[r],lon_axis[c]) 매핑이 어긋나는 순간
    선택 row 집합이 달라져 실패한다.
    """
    lat_axis = np.linspace(0.0, 10.0, 11)
    lon_axis = np.linspace(0.0, 10.0, 11)
    # (lon,lat) ring: lon 전폭[0,10] × lat 하단밴드[0,3]
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 3.0), (0.0, 3.0), (0.0, 0.0)]
    mask = ts._polygon_interior_mask(lat_axis, lon_axis, ring)
    assert mask is not None
    # (lat=0, lon=9) 내부 / (lat=9, lon=0) 밖 — 전치되면 정반대가 되어 실패
    assert mask[0, 9] and not mask[9, 0]
    # 선택된 row(=lat idx)는 밴드 [0,3]에 정확히 대응(전 col 포함)
    selected_rows = sorted({r for r in range(11) for c in range(11) if mask[r, c]})
    assert selected_rows == [0, 1, 2, 3]


def test_polygon_interior_mask_none_for_degenerate():
    lat_axis = np.linspace(0.0, 10.0, 11)
    lon_axis = np.linspace(0.0, 10.0, 11)
    assert ts._polygon_interior_mask(lat_axis, lon_axis, []) is None
    assert ts._polygon_interior_mask(lat_axis, lon_axis, [(0.0, 0.0), (1.0, 1.0)]) is None


# ── _compute_slope 마스킹 ──


def test_slope_mask_all_true_no_regression():
    """사각형(=bbox) 필지: 마스크 전부 True → 무마스크와 결과 동일(무회귀)."""
    grid = np.arange(121, dtype=float).reshape(11, 11)
    full = ts._compute_slope(grid, 30.0, 30.0)
    masked = ts._compute_slope(grid, 30.0, 30.0, interior_mask=np.ones((11, 11), bool))
    assert masked["mean_pct"] == full["mean_pct"]
    assert masked["max_pct"] == full["max_pct"]
    assert masked["clip_applied"] is True
    assert masked["interior_pts"] == 121
    assert masked["grid_pts"] == 121


def test_slope_mask_excludes_steep_neighbor():
    """왼쪽 평지만 내부로 마스킹 → 오른쪽 급경사 이웃 지형이 평균에서 빠져 mean 하락."""
    grid = np.zeros((11, 11), dtype=float)
    for c in range(11):
        grid[:, c] = 0.0 if c <= 4 else (c - 4) * 20.0  # 오른쪽 급경사 램프
    mask = np.zeros((11, 11), dtype=bool)
    mask[:, 0:4] = True  # 왼쪽 평지 4열(44점) 내부
    full = ts._compute_slope(grid, 30.0, 30.0)
    clipped = ts._compute_slope(grid, 30.0, 30.0, interior_mask=mask)
    assert clipped["clip_applied"] is True
    assert clipped["interior_pts"] == 44
    assert clipped["mean_pct"] < full["mean_pct"]  # 이웃 급경사 제외 효과


def test_slope_sparse_interior_falls_back_to_bbox():
    """내부 격자점 < 최소치(4) → 클립 미적용, bbox 전체로 폴백(정직 강등)."""
    grid = np.arange(121, dtype=float).reshape(11, 11)
    mask = np.zeros((11, 11), dtype=bool)
    mask[0, 0] = mask[0, 1] = True  # 2점 < _MIN_INTERIOR_PTS
    out = ts._compute_slope(grid, 30.0, 30.0, interior_mask=mask)
    full = ts._compute_slope(grid, 30.0, 30.0)
    assert out["clip_applied"] is False
    assert out["interior_pts"] == 2
    assert out["mean_pct"] == full["mean_pct"]  # 전체 격자와 동일


def test_slope_clip_note_in_detail():
    grid = np.arange(121, dtype=float).reshape(11, 11)
    out = ts._compute_slope(grid, 30.0, 30.0, interior_mask=np.ones((11, 11), bool))
    assert "폴리곤 내부" in out["detail"]


# ── _compute_earthwork 마스킹(동일 bbox 결함 전파방지) ──


def test_earthwork_mask_restricts_to_interior():
    grid = np.zeros((11, 11), dtype=float)
    grid[:, 5:] = 100.0  # 오른쪽만 높음(이웃 지형)
    mask = np.zeros((11, 11), dtype=bool)
    mask[:, 0:5] = True  # 왼쪽 평지(0m)만 내부(55점)
    ew_clip = ts._compute_earthwork(grid, 900.0, None, interior_mask=mask)
    ew_full = ts._compute_earthwork(grid, 900.0, None)
    # 내부(왼쪽)는 전부 0m 평지 → base=0, 절/성토 0
    assert ew_clip["cut_volume_m3"] == 0.0
    assert ew_clip["fill_volume_m3"] == 0.0
    # 전체는 오른쪽 성토/절토 발생
    assert ew_full["cut_volume_m3"] > 0.0 and ew_full["fill_volume_m3"] > 0.0


def test_earthwork_sparse_interior_falls_back():
    grid = np.zeros((11, 11), dtype=float)
    grid[:, 5:] = 100.0
    mask = np.zeros((11, 11), dtype=bool)
    mask[0, 0] = mask[0, 1] = True  # 2점 < 최소치 → 폴백
    ew_clip = ts._compute_earthwork(grid, 900.0, None, interior_mask=mask)
    ew_full = ts._compute_earthwork(grid, 900.0, None)
    assert ew_clip["base_level_m"] == ew_full["base_level_m"]


# ── _confidence 클립 반영 ──


def test_confidence_penalizes_sparse_interior():
    """폴리곤 있으나 내부점 부족(clip 미적용) → 신뢰도 하향 + note."""
    area = 5000.0  # 충분한 면적(다른 감점 없음)
    good = ts._confidence(area, 121, 121, slope_clip={"clip_applied": True, "interior_pts": 60})
    poor = ts._confidence(area, 121, 121, slope_clip={"clip_applied": False, "interior_pts": 2})
    assert poor[0] < good[0]                 # 신뢰도 하락
    assert "bbox 근사" in poor[1]
    assert "이웃 지형 제외" in good[1]


def test_confidence_mild_penalty_for_few_clipped_points():
    """clip 적용됐어도 내부 표본이 적으면(<10) 완만 감점 + 노이즈 경고(정직)."""
    area = 5000.0
    many = ts._confidence(area, 121, 121, slope_clip={"clip_applied": True, "interior_pts": 60})
    few = ts._confidence(area, 121, 121, slope_clip={"clip_applied": True, "interior_pts": 6})
    assert few[0] < many[0]              # 표본 적으면 신뢰도 완만 하락
    assert "노이즈 가능" in few[1]
    assert "노이즈 가능" not in many[1]
