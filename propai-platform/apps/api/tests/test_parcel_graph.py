"""ParcelGraph(W2-5) — 인접 그래프·articulation point·N-1 시나리오·핵심필지 판정 — TDD.

계약:
  · 간선 = 경계 실접촉(shapely touches + intersection 길이>0)만 인정. bbox(외접상자)만
    겹치고 실제 도형이 이격돼 있으면 간선을 만들지 않는다(bbox 스침 배제).
  · geometry 없는 필지는 그래프에서 UNKNOWN 처리(간선 날조 금지) — n_minus_1에도
    "미상" 정직 표기.
  · articulation point = 제거-재탐색 시 연결성분 수가 늘어나는 필지(일자형 3필지 가운데=critical).
  · N-1: 도로접면 유일 필지 제거 시 나머지가 맹지화되는지 검출한다.
  · 상한(MAX_PARCELS_FOR_GRAPH) 초과 시 그래프 산출을 생략한다(status=skipped_large_set).
"""
from __future__ import annotations

from app.services.zoning.parcel_graph import MAX_PARCELS_FOR_GRAPH, build_parcel_graph


def _square(lon0: float, lat0: float, size: float = 0.001) -> dict:
    lon1, lat1 = lon0 + size, lat0 + size
    return {
        "type": "Polygon",
        "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]],
    }


def _triangle(pts: list[tuple[float, float]]) -> dict:
    ring = pts + [pts[0]]
    return {"type": "Polygon", "coordinates": [ring]}


# ─────────────────────────────────────────────────────────────────────────────
# 1) 간선 판정 — 실접촉 vs bbox 스침 vs 이격
# ─────────────────────────────────────────────────────────────────────────────

def test_edge_real_contact_creates_edge():
    """경계를 실제로 공유하는 두 필지 — 간선 생성 + 하나의 연결성분."""
    parcels = [
        {"pnu": "A", "geometry": _square(127.000, 37.000), "area_sqm": 500},
        {"pnu": "B", "geometry": _square(127.001, 37.000), "area_sqm": 500},  # A 우측 변 공유
    ]
    out = build_parcel_graph(parcels)
    assert out["status"] == "ok"
    assert len(out["edges"]) == 1
    assert out["edges"][0]["contact_length"] > 0
    assert out["connected_components"] == [["A", "B"]]
    assert out["component_count"] == 1


def test_edge_bbox_overlap_without_touch_is_excluded():
    """외접상자(bbox)는 겹치지만 실제 도형은 이격된 두 삼각형 — 간선 미생성(스침 배제)."""
    s = 0.001
    ox, oy = 127.0, 37.0
    tri_a = _triangle([(ox, oy), (ox + s, oy), (ox, oy + s)])
    tri_b = _triangle([(ox + 0.9 * s, oy + 0.9 * s), (ox + 2 * s, oy + 0.9 * s), (ox + 0.9 * s, oy + 2 * s)])
    parcels = [
        {"pnu": "A", "geometry": tri_a, "area_sqm": 100},
        {"pnu": "B", "geometry": tri_b, "area_sqm": 100},
    ]
    out = build_parcel_graph(parcels)
    assert out["edges"] == []
    assert sorted(out["connected_components"]) == [["A"], ["B"]]
    assert out["component_count"] == 2


def test_edge_real_separation_no_edge():
    """실제로 멀리 떨어진(이격) 두 필지 — bbox도 겹치지 않고 간선도 없다."""
    parcels = [
        {"pnu": "A", "geometry": _square(127.000, 37.000), "area_sqm": 500},
        {"pnu": "B", "geometry": _square(127.010, 37.000), "area_sqm": 500},  # ~1km 이격
    ]
    out = build_parcel_graph(parcels)
    assert out["edges"] == []
    assert out["component_count"] == 2


def test_edge_corner_only_touch_excluded_length_zero():
    """점(코너)만 맞닿는 두 사각형 — intersection 길이 0이라 간선 미생성."""
    a = _square(127.000, 37.000)
    b = _square(127.001, 37.001)  # A의 우상단 코너에서만 만남
    out = build_parcel_graph([
        {"pnu": "A", "geometry": a, "area_sqm": 500},
        {"pnu": "B", "geometry": b, "area_sqm": 500},
    ])
    assert out["edges"] == []
    assert out["component_count"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# 2) 성분 분리
# ─────────────────────────────────────────────────────────────────────────────

def test_two_groups_separated_components():
    """맞닿은 A-B 한 그룹 + 멀리 떨어진 C 한 그룹 — 성분 2개."""
    parcels = [
        {"pnu": "A", "geometry": _square(127.000, 37.000), "area_sqm": 300},
        {"pnu": "B", "geometry": _square(127.001, 37.000), "area_sqm": 300},
        {"pnu": "C", "geometry": _square(128.000, 38.000), "area_sqm": 300},
    ]
    out = build_parcel_graph(parcels)
    comps = sorted(out["connected_components"], key=len)
    assert comps == [["C"], ["A", "B"]]
    assert out["component_count"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# 3) articulation point — 일자형 3필지 가운데=critical
# ─────────────────────────────────────────────────────────────────────────────

def test_middle_parcel_of_line_is_articulation_and_critical():
    """A-B-C 일자형 인접(가운데 B) — B 제거 시 A/C 분리(articulation) + CRITICAL 등급."""
    parcels = [
        {"pnu": "A", "geometry": _square(127.000, 37.000), "area_sqm": 500, "road_frontage": True},
        {"pnu": "B", "geometry": _square(127.001, 37.000), "area_sqm": 500, "road_frontage": False},
        {"pnu": "C", "geometry": _square(127.002, 37.000), "area_sqm": 500, "road_frontage": False},
    ]
    out = build_parcel_graph(parcels)
    assert out["connected_components"] == [["A", "B", "C"]]
    assert out["articulation_points"] == ["B"]
    assert out["critical_scores"]["B"]["grade"] == "CRITICAL"
    assert out["critical_scores"]["B"]["is_articulation"] is True
    # 양끝(A,C)은 제거해도 나머지가 여전히 연결(articulation 아님).
    assert "A" not in out["articulation_points"]
    assert "C" not in out["articulation_points"]


def test_sole_road_frontage_parcel_is_critical_even_if_not_articulation():
    """도로접면이 A 하나뿐인 그룹 — A는 articulation이 아니어도(끝단) CRITICAL(유일 접면)."""
    parcels = [
        {"pnu": "A", "geometry": _square(127.000, 37.000), "area_sqm": 500, "road_frontage": True},
        {"pnu": "B", "geometry": _square(127.001, 37.000), "area_sqm": 500, "road_frontage": False},
        {"pnu": "C", "geometry": _square(127.002, 37.000), "area_sqm": 500, "road_frontage": False},
    ]
    out = build_parcel_graph(parcels)
    assert out["articulation_points"] == ["B"]  # A는 articulation 아님(끝단)
    assert out["critical_scores"]["A"]["is_sole_frontage"] is True
    assert out["critical_scores"]["A"]["grade"] == "CRITICAL"


# ─────────────────────────────────────────────────────────────────────────────
# 4) N-1 시나리오 — 맹지화 검출
# ─────────────────────────────────────────────────────────────────────────────

def test_n_minus_1_removing_sole_frontage_landlocks_rest():
    """유일 도로접면 필지(A) 제거 — 남은 B,C 전원 맹지화 + 면적 delta 음수."""
    parcels = [
        {"pnu": "A", "geometry": _square(127.000, 37.000), "area_sqm": 500, "road_frontage": True},
        {"pnu": "B", "geometry": _square(127.001, 37.000), "area_sqm": 500, "road_frontage": False},
        {"pnu": "C", "geometry": _square(127.002, 37.000), "area_sqm": 500, "road_frontage": False},
    ]
    out = build_parcel_graph(parcels)
    n1_a = out["n_minus_1"]["A"]
    assert n1_a["remains_connected"] is True  # B-C는 여전히 연결
    assert sorted(n1_a["newly_landlocked_pnus"]) == ["B", "C"]
    assert n1_a["remaining_area_sqm"] == 1000.0
    assert n1_a["area_delta_sqm"] == -500.0


def test_n_minus_1_removing_middle_disconnects_and_landlocks_far_end():
    """가운데(B) 제거 — A/C 분리(remains_connected=False) + C만 맹지화(A는 자체 접면)."""
    parcels = [
        {"pnu": "A", "geometry": _square(127.000, 37.000), "area_sqm": 500, "road_frontage": True},
        {"pnu": "B", "geometry": _square(127.001, 37.000), "area_sqm": 500, "road_frontage": False},
        {"pnu": "C", "geometry": _square(127.002, 37.000), "area_sqm": 500, "road_frontage": False},
    ]
    out = build_parcel_graph(parcels)
    n1_b = out["n_minus_1"]["B"]
    assert n1_b["remains_connected"] is False
    assert n1_b["components_after"] == 2
    assert n1_b["newly_landlocked_pnus"] == ["C"]


# ─────────────────────────────────────────────────────────────────────────────
# 5) geometry 부재 — UNKNOWN 정직 표기(간선 날조 금지)
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_geometry_marked_unknown_no_fabricated_edges():
    """geometry 없는 필지는 UNKNOWN — 간선/연결성분 계산에서 제외되고 n_minus_1도 미상."""
    parcels = [
        {"pnu": "A", "geometry": _square(127.000, 37.000), "area_sqm": 500, "road_frontage": True},
        {"pnu": "B", "area_sqm": 500},  # geometry 없음
    ]
    out = build_parcel_graph(parcels)
    assert out["geometry_unknown_pnus"] == ["B"]
    assert "B" not in out["adjacency"]
    assert out["connected_components"] == [["A"]]
    n1_b = out["n_minus_1"]["B"]
    assert n1_b["remains_connected"] is None
    assert n1_b["newly_landlocked_pnus"] is None
    assert n1_b["area_delta_sqm"] == -500.0  # 면적 영향은 geometry 없이도 산출 가능
    assert any("형상" in w for w in out["warnings"])


def test_all_geometry_missing_returns_empty_graph_honestly():
    """전원 geometry 없음 — 그래프는 비어있고 area 기반 N-1만 남는다(연결성 미상)."""
    parcels = [{"pnu": "A", "area_sqm": 300}, {"pnu": "B", "area_sqm": 200}]
    out = build_parcel_graph(parcels)
    assert out["status"] == "ok"
    assert out["connected_components"] == []
    assert out["articulation_points"] == []
    assert out["n_minus_1"]["A"]["remains_connected"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 6) 상한 가드 — 대량 조합 성능 보호
# ─────────────────────────────────────────────────────────────────────────────

def test_parcel_count_over_cap_skips_graph():
    """MAX_PARCELS_FOR_GRAPH 초과 — 그래프 산출을 생략하고 정직 표식만 반환."""
    big = [{"pnu": f"P{i}", "area_sqm": 10.0} for i in range(MAX_PARCELS_FOR_GRAPH + 1)]
    out = build_parcel_graph(big)
    assert out["status"] == "skipped_large_set"
    assert out["parcel_count"] == MAX_PARCELS_FOR_GRAPH + 1
    assert "note" in out


def test_parcel_count_at_cap_still_computes():
    """정확히 상한(MAX_PARCELS_FOR_GRAPH)까지는 정상 산출된다(경계값)."""
    at_cap = [{"pnu": f"P{i}", "area_sqm": 10.0} for i in range(MAX_PARCELS_FOR_GRAPH)]
    out = build_parcel_graph(at_cap)
    assert out["status"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# 기타 — 빈 입력·실효한도(면적가중) delta
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_parcels_returns_honest_empty_shape():
    out = build_parcel_graph([])
    assert out["status"] == "empty"
    assert out["n_minus_1"] == {}


def test_effective_far_delta_computed_when_far_provided():
    """effective_far_pct 제공 시 면적가중 블렌드 delta 산출(1차 근사 — 명시적 산식)."""
    parcels = [
        {"pnu": "A", "geometry": _square(127.000, 37.000), "area_sqm": 1000, "effective_far_pct": 200.0},
        {"pnu": "B", "geometry": _square(127.001, 37.000), "area_sqm": 500, "effective_far_pct": 100.0},
    ]
    out = build_parcel_graph(parcels)
    n1_b = out["n_minus_1"]["B"]
    # before = (1000*200+500*100)/1500 = 166.7, after(=A만) = 200.0 → delta = +33.3
    assert n1_b["effective_far_pct_before"] == 166.7
    assert n1_b["effective_far_pct_after"] == 200.0
    assert n1_b["effective_far_pct_delta"] == 33.3
