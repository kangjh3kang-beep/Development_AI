"""MEDIUM 감사: 일영 shadow_polygon 볼록껍질 교정 — 내부점 제거로 음영 과대 해소.

배경: shadow_polygon이 8점(건물4+그림자4)을 centroid 기준 각도정렬만 해서, 내부점이 제거되지
않아 폴리곤이 비볼록/자기교차가 되며 음영 면적을 과대 산정했다(convex hull 아님). Andrew's
monotone chain 진짜 볼록껍질로 교체한다(결정론·math만, 내부점/공선점 제거).
"""
import pytest

from app.services.drawing.shadow_simulator import _convex_hull, shadow_polygon


def _is_convex(poly) -> bool:
    n = len(poly)
    if n < 3:
        return True
    signs = []
    for i in range(n):
        o, a, b = poly[i], poly[(i + 1) % n], poly[(i + 2) % n]
        cr = (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        if abs(cr) > 1e-9:
            signs.append(cr > 0)
    return len(set(signs)) <= 1


def _has_self_overlap_point(poly) -> bool:
    # 동일점 반복(자기교차/중복 정점)이면 True.
    return len(poly) != len(set(poly))


def test_convex_hull_excludes_interior_point():
    hull = _convex_hull([(0, 0), (10, 0), (10, 10), (0, 10), (5, 5)])
    assert (5, 5) not in hull  # 내부점 제거
    assert len(hull) == 4


def test_convex_hull_drops_collinear():
    hull = _convex_hull([(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)])
    assert (5, 0) not in hull  # 변 위 공선점 제거
    assert len(hull) == 4


def test_convex_hull_degenerate_returns_input():
    # 점<3이면 입력 그대로(축퇴 방지).
    assert _convex_hull([(1.0, 2.0)]) == [(1.0, 2.0)]
    assert _convex_hull([(0.0, 0.0), (1.0, 1.0)]) == [(0.0, 0.0), (1.0, 1.0)]


def test_shadow_polygon_diagonal_is_convex_no_overlap():
    # 대각선 태양(az=135)에서 과거 각도정렬은 비볼록/자기교차 → 진짜 hull은 볼록·중복없음.
    poly = shadow_polygon(30.0, 135.0, 20.0, 15.0, 10.0)
    assert len(poly) >= 4
    assert _is_convex(poly)
    assert not _has_self_overlap_point(poly)


@pytest.mark.parametrize("az", [90.0, 135.0, 180.0, 225.0, 270.0])
def test_shadow_polygon_convex_for_various_azimuths(az):
    poly = shadow_polygon(30.0, az, 20.0, 15.0, 10.0)
    assert _is_convex(poly)
