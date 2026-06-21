"""design_ingest 조합(composition) 단위테스트 — 순수 로직(DB/네트워크 무관)."""

from app.services.design_ingest.composition import (
    SiteContext,
    compose,
    fit_score,
    site_context_from_zone,
)


def _site(**kw) -> SiteContext:
    base = dict(area_sqm=1000.0, zone_code="2R", legal_bcr_pct=60.0, legal_far_pct=200.0,
                far_source="ordinance")
    base.update(kw)
    return SiteContext(**base)


def test_site_context_envelope():
    s = _site()
    assert s.buildable_footprint_sqm == 600.0   # 1000 × 60%
    assert s.max_gfa_sqm == 2000.0              # 1000 × 200%
    assert s.max_floors_est == 3                # 2000 // 600
    # 한도 미상이면 None(추정 금지)
    bare = SiteContext(area_sqm=1000.0)
    assert bare.buildable_footprint_sqm is None and bare.max_gfa_sqm is None


def test_fit_score_area_and_type():
    s = _site()  # footprint 600
    near = fit_score({"drawing_type": "floor_plan", "total_area_sqm": 600.0, "score": 0.9}, s)
    far = fit_score({"drawing_type": "floor_plan", "total_area_sqm": 5000.0, "score": 0.9}, s)
    assert near > far  # 면적 근접이 더 높음
    # 면적 미상 → 중립(0.5 가중)이라 near보다 낮고 far보다 높을 수 있음(추정 금지)
    none_area = fit_score({"drawing_type": "floor_plan", "total_area_sqm": None}, s)
    assert 0.0 <= none_area <= 1.0


def test_compose_compliant_candidate():
    s = _site()  # footprint 600, max_gfa 2000, max_floors 3
    matches = [
        {"point_id": "fp1", "drawing_type": "floor_plan", "total_area_sqm": 500.0, "score": 0.95},
        {"point_id": "sp1", "drawing_type": "site_plan", "total_area_sqm": 980.0, "score": 0.9},
        {"point_id": "pk1", "drawing_type": "parking", "total_area_sqm": None, "score": 0.8},
    ]
    cands = compose(s, matches, top_n=3)
    assert cands, "후보가 비어있음"
    top = cands[0]
    assert top.primary_drawing_type == "floor_plan"
    assert top.selected.get("floor_plan") == "fp1"
    assert "site_plan" in top.selected and "parking" in top.selected
    assert top.estimated_floors == 3 and top.estimated_gfa_sqm == 1500.0  # 500×3, ≤2000
    assert top.estimated_units and top.estimated_units > 0
    assert top.estimated_parking == top.estimated_units  # 세대당 1대
    assert top.compliant is True and top.score > 0


def test_compose_noncompliant_when_drawing_oversized():
    # footprint 600인데 참조도면 5000㎡ → 축소 sqrt(600/5000)=0.346 < 0.5 → 부적합(과대)
    s = _site()
    matches = [{"point_id": "big", "drawing_type": "floor_plan", "total_area_sqm": 5000.0, "score": 0.9}]
    top = compose(s, matches)[0]
    assert top.scale_factor is not None and top.scale_factor < 0.5
    assert top.compliant is False
    assert any("과대" in w or "부적합" in w for w in top.warnings)


def test_compose_no_legal_limits_is_honest():
    s = SiteContext(area_sqm=1000.0)  # 한도 미상
    matches = [{"point_id": "fp", "drawing_type": "floor_plan", "total_area_sqm": 500.0, "score": 0.9}]
    top = compose(s, matches)[0]
    assert top.compliant is False
    assert any("법적 한도 미상" in w for w in top.warnings)


def test_compose_ranking_and_empty():
    s = _site()
    assert compose(s, []) == []  # 빈 입력
    matches = [
        {"point_id": "a", "drawing_type": "floor_plan", "total_area_sqm": 590.0, "score": 0.99},
        {"point_id": "b", "drawing_type": "floor_plan", "total_area_sqm": 590.0, "score": 0.50},
    ]
    cands = compose(s, matches, top_n=2)
    assert len(cands) == 2 and cands[0].score >= cands[1].score  # 점수 내림차순


def test_statutory_source_warns_ordinance_check():
    s = _site(far_source="statutory")
    matches = [{"point_id": "fp", "drawing_type": "floor_plan", "total_area_sqm": 500.0, "score": 0.9}]
    top = compose(s, matches)[0]
    assert any("조례 실효한도" in w for w in top.warnings)


def test_site_context_from_zone_ordinance_priority():
    # 조례(실효) 값이 오면 far_source='ordinance'(전역규칙: 용적률 실효 우선)
    s = site_context_from_zone("2R", 1000.0, ordinance_far_pct=250.0, ordinance_bcr_pct=55.0)
    assert s.far_source == "ordinance"
    assert s.legal_far_pct == 250.0 and s.legal_bcr_pct == 55.0


def test_compose_merges_site_warnings():
    # SiteContext.warnings(부지/한도 경고)가 후보 warnings로 정직 승계
    s = _site()
    s.warnings.append("미지정 용도지역 폴백X")
    matches = [{"point_id": "fp", "drawing_type": "floor_plan", "total_area_sqm": 500.0, "score": 0.9}]
    top = compose(s, matches)[0]
    assert any("폴백X" in w for w in top.warnings)


def test_compose_zero_units_guard():
    # 작은 footprint + 큰 평형 → 추정 세대 0 → 주차 1대규칙 경고 대신 '세대수 0' 경고, parking None
    s = _site(area_sqm=100.0, legal_bcr_pct=20.0, legal_far_pct=50.0)  # footprint20, gfa50
    matches = [{"point_id": "fp", "drawing_type": "floor_plan", "total_area_sqm": 20.0, "score": 0.9}]
    top = compose(s, matches)[0]
    assert top.estimated_units == 0
    assert top.estimated_parking is None
    assert any("세대수 0" in w for w in top.warnings)
    assert not any("세대당 1대" in w for w in top.warnings)
