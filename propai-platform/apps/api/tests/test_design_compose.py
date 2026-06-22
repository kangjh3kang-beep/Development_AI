"""design_ingest 조합(composition) 단위테스트 — 순수 로직(DB/네트워크 무관)."""

from app.services.design_ingest.composition import (
    SiteContext,
    compose,
    compute_parking_design,
    compute_parking_layout,
    compute_placement,
    fit_score,
    map_building_use_kr,
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


def test_compose_score_breakdown_transparency():
    # ★근거: 점수 산출 3성분(적합도·완성도가중·적법가중)이 노출되고 곱이 score와 일치(랭킹 투명성)
    s = _site()
    matches = [
        {"point_id": "fp1", "drawing_type": "floor_plan", "total_area_sqm": 500.0, "score": 0.95},
        {"point_id": "sp1", "drawing_type": "site_plan", "total_area_sqm": 980.0, "score": 0.9},
        {"point_id": "pk1", "drawing_type": "parking", "total_area_sqm": None, "score": 0.8},
    ]
    top = compose(s, matches, top_n=1)[0]
    sb = top.score_breakdown
    assert sb is not None
    assert set(sb) >= {"fitness", "completeness", "completeness_factor", "compliance_factor",
                       "formula", "explanation"}
    # 곱이 score와 일치(반올림 오차 허용)
    recomputed = round(sb["fitness"] * sb["completeness_factor"] * sb["compliance_factor"], 4)
    assert abs(recomputed - top.score) < 0.01
    assert sb["compliance_factor"] == 1.0  # compliant 후보
    assert "종합" in sb["explanation"]


def test_compose_score_breakdown_noncompliant_factor():
    # 부적합 후보는 적법가중 0.6 노출(정직 — 왜 점수가 낮은지)
    s = _site()
    matches = [{"point_id": "big", "drawing_type": "floor_plan", "total_area_sqm": 5000.0, "score": 0.9}]
    top = compose(s, matches)[0]
    assert top.compliant is False
    assert top.score_breakdown is not None
    assert top.score_breakdown["compliance_factor"] == 0.6


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
    # 작은 footprint + 큰 평형 → 추정 세대 0 → '세대수 0' 경고. 공동주택 0세대=주차 0대(정밀)
    s = _site(area_sqm=100.0, legal_bcr_pct=20.0, legal_far_pct=50.0)  # footprint20, gfa50
    matches = [{"point_id": "fp", "drawing_type": "floor_plan", "total_area_sqm": 20.0, "score": 0.9}]
    top = compose(s, matches)[0]
    assert top.estimated_units == 0
    assert top.estimated_parking == 0 and top.parking_required == 0  # 0세대→0대(정직)
    assert top.parking_feasible is True  # 주차 0대 = 배치 부담 없음
    assert any("세대수 0" in w for w in top.warnings)


def test_map_building_use_kr():
    assert map_building_use_kr("apt-housing") == "공동주택"
    assert map_building_use_kr("아파트") == "공동주택"
    assert map_building_use_kr("근린생활시설") == "근린생활시설"
    assert map_building_use_kr("office") == "업무시설"
    assert map_building_use_kr(None) == "공동주택"  # 미상 폴백
    assert map_building_use_kr("듣보용도") == "공동주택"


def test_compute_parking_design_apartment():
    # 공동주택 13세대 → 세대당 1대 = 13대, 대당 33㎡ = 429㎡. footprint 600 → 지하 1층, 현실적
    s = _site()  # footprint 600
    pk = compute_parking_design(s, est_units=13, est_gfa=1500.0)
    assert pk["required"] == 13
    assert pk["area_sqm"] == 429.0           # 13 × 33
    assert pk["basement_floors_site"] == 1   # ceil(429/600)
    assert pk["feasible"] is True


def test_compute_parking_design_infeasible_when_footprint_tiny():
    # 큰 주차 수요 + 아주 작은 footprint → 지하층 과다 → 비현실(feasible False + 경고)
    s = _site(area_sqm=10000.0, legal_bcr_pct=5.0, legal_far_pct=400.0)  # footprint 500
    # 면적당 산정용으로 업무시설(gfa 기반): gfa 40000 → 40000/150 ≈ 266대 × 33 = 8778㎡
    s.building_use_kr = "업무시설"
    pk = compute_parking_design(s, est_units=0, est_gfa=40000.0)
    assert pk["required"] > 0 and pk["area_sqm"] > 0
    assert pk["basement_floors_site"] is not None and pk["basement_floors_site"] > 5
    assert pk["feasible"] is False
    assert any("비현실" in w for w in pk["warnings"])


def test_compute_parking_design_footprint_unknown_warns():
    # 주차 필요하나 footprint(건폐율 한도) 미상 → 배치 현실성 미판정(None) + 정직 경고
    s = SiteContext(area_sqm=1000.0)  # legal_bcr_pct None → footprint None
    pk = compute_parking_design(s, est_units=13, est_gfa=1500.0)
    assert pk["required"] == 13                 # 대수는 산정됨
    assert pk["basement_floors_site"] is None   # footprint 미상 → 지하층 미산
    assert pk["feasible"] is None               # 배치 현실성 미판정(정직)
    assert any("미판정" in w for w in pk["warnings"])


def test_compute_parking_design_no_basis_returns_none():
    # 산정 근거 없음(gfa None & units None) → 전부 None(추정 금지)
    s = _site()
    pk = compute_parking_design(s, est_units=None, est_gfa=None)
    assert pk["required"] is None and pk["feasible"] is None


# ── 건물 배치 폴리곤(compute_placement) ──

def test_compute_placement_known_dims_centered_within_setback():
    # 부지 40×25, 이격 3 → 가용 34×19. BCR 60%→footprint 600㎡. 건물은 가용영역 중앙 배치.
    s = _site(width_m=40.0, depth_m=25.0, legal_setback_m=3.0)
    p = compute_placement(s)
    assert p is not None and p["site"] == {"w": 40.0, "d": 25.0}
    assert p["setback_m"] == 3.0
    assert p["buildable_region_sqm"] == round(34.0 * 19.0, 1)
    b = p["building"]
    # 건물이 부지 안에 들어가고(이격 경계 내), 중앙 배치(좌우 여백 대칭)
    assert b["x"] >= 3.0 - 0.05 and (b["x"] + b["w"]) <= 40.0 - 3.0 + 0.05
    assert abs(b["x"] - (40.0 - b["w"]) / 2) < 0.05
    assert b["area_sqm"] > 0 and p["setback_binds"] is False


def test_compute_placement_square_fallback_when_dims_unknown():
    # 부지 치수 미상 → 면적√ 정사각 가정 + 정직 고지
    s = _site(width_m=None, depth_m=None, legal_setback_m=2.0)  # area 1000 → 31.6각
    p = compute_placement(s)
    assert p["site"]["w"] == p["site"]["d"]  # 정사각
    assert any("정사각" in n for n in p["notes"])


def test_compute_placement_setback_binds_flag():
    # 작은 부지 + 큰 이격 → 가용영역 < BCR footprint → setback_binds True + 정직 경고
    # 부지 20×20(400㎡)·이격 5 → 가용 10×10=100㎡. BCR 60%×400=240㎡ > 100 → binds.
    s = SiteContext(area_sqm=400.0, zone_code="2R", legal_bcr_pct=60.0, legal_far_pct=200.0,
                    far_source="ordinance", width_m=20.0, depth_m=20.0, legal_setback_m=5.0)
    p = compute_placement(s)
    assert p["setback_binds"] is True
    assert any("배치 제약" in n for n in p["notes"])
    assert p["building"]["area_sqm"] <= p["buildable_region_sqm"] + 0.1


def test_compute_placement_no_region_when_setback_too_large():
    # 이격이 부지 절반 이상 → 가용영역 0 → building None + 배치불가 고지
    s = SiteContext(area_sqm=100.0, zone_code="2R", legal_bcr_pct=60.0, legal_far_pct=200.0,
                    far_source="ordinance", width_m=10.0, depth_m=10.0, legal_setback_m=6.0)
    p = compute_placement(s)
    assert p["building"] is None and p["setback_binds"] is True
    assert "가용영역 없음" in p["note"]


def test_compute_placement_none_when_no_area():
    assert compute_placement(SiteContext(area_sqm=0.0)) is None


def test_compute_placement_tiny_site_no_fake_building():
    # 극소 부지(6×6)·이격 2.9 → 가용 0.2×0.2, 라운딩 후 0크기 → 가짜 0면적 건물 금지(building None)
    s = SiteContext(area_sqm=36.0, zone_code="2R", legal_bcr_pct=60.0, legal_far_pct=200.0,
                    far_source="ordinance", width_m=6.0, depth_m=6.0, legal_setback_m=2.9)
    p = compute_placement(s)
    assert p["building"] is None and p["setback_binds"] is True


# ── 다동(단지) 배치(PG2) ──

def test_compute_placement_multi_dong_grid():
    # 공동주택·대형 부지(footprint>1200) → 분동. 동수≥2·blocks=동수·각 동 부지 안·면적>0.
    s = SiteContext(area_sqm=5000.0, zone_code="2R", legal_bcr_pct=60.0, legal_far_pct=300.0,
                    far_source="ordinance", width_m=100.0, depth_m=50.0, legal_setback_m=3.0,
                    building_use_kr="공동주택")
    p = compute_placement(s)
    assert p["dong_count"] >= 2 and len(p["blocks"]) == p["dong_count"]
    assert p["gap_m"] > 0
    for b in p["blocks"]:
        assert b["w"] > 0 and b["d"] > 0
        assert b["x"] >= 3.0 - 0.05 and (b["x"] + b["w"]) <= 100.0 - 3.0 + 0.05  # 이격 경계 내
        assert b["y"] >= 3.0 - 0.05 and (b["y"] + b["d"]) <= 50.0 - 3.0 + 0.05
    assert any("단지 배치" in n for n in p["notes"])


def test_compute_placement_multi_dong_asymmetric_within_bounds():
    # 비대칭 부지에서도 라운딩 후 모든 동이 이격 경계 내(영역 클램프로 드리프트 0)
    s = SiteContext(area_sqm=200.0 * 77.7, zone_code="2R", legal_bcr_pct=60.0, legal_far_pct=300.0,
                    far_source="ordinance", width_m=200.0, depth_m=77.7, legal_setback_m=5.5,
                    building_use_kr="공동주택")
    p = compute_placement(s)
    assert p["dong_count"] >= 2
    for b in p["blocks"]:
        assert b["w"] > 0 and b["d"] > 0
        assert b["x"] >= 5.5 - 1e-6 and (b["x"] + b["w"]) <= 200.0 - 5.5 + 1e-6
        assert b["y"] >= 5.5 - 1e-6 and (b["y"] + b["d"]) <= 77.7 - 5.5 + 1e-6


def test_compute_placement_dim_area_mismatch_note():
    # 입력 치수(폭×깊이=100)와 대지면적(1000) 불일치 → 정직 고지(경고 오귀속 방지)
    s = _site(width_m=10.0, depth_m=10.0)  # area 1000, w*d=100 → 90% 불일치
    p = compute_placement(s)
    assert any("불일치" in n for n in p["notes"])


def test_compute_placement_single_dong_for_nonresidential():
    # 비주거(근생) → footprint 커도 단일 동(blocks 1개 = building), gap 0
    s = SiteContext(area_sqm=5000.0, zone_code="2R", legal_bcr_pct=60.0, legal_far_pct=300.0,
                    far_source="ordinance", width_m=100.0, depth_m=50.0, legal_setback_m=3.0,
                    building_use_kr="근린생활시설")
    p = compute_placement(s)
    assert p["dong_count"] == 1 and len(p["blocks"]) == 1 and p["gap_m"] == 0.0


def test_compute_placement_small_apartment_single_dong():
    # 공동주택이라도 footprint<=1동 상한(1200)이면 단일 동
    s = _site(width_m=40.0, depth_m=25.0, legal_setback_m=3.0, building_use_kr="공동주택")
    # area 1000·BCR60 → footprint 600 < 1200 → 단일
    p = compute_placement(s)
    assert p["dong_count"] == 1 and len(p["blocks"]) == 1


def test_layout_dong_blocks_gap_too_large_returns_none():
    from app.services.design_ingest.composition import _layout_dong_blocks
    # 가용영역 10×10·동간거리 20 → 셀 음수 → None(단일 폴백 신호)
    assert _layout_dong_blocks(0.0, 10.0, 10.0, 500.0, 4, 20.0) is None
    # n<=1도 None(단일 경로 사용)
    assert _layout_dong_blocks(0.0, 50.0, 50.0, 500.0, 1, 6.0) is None


def test_compose_exposes_placement():
    # compose 결과 후보/to_dict에 placement(부지+건물 폴리곤) 노출
    s = _site(width_m=40.0, depth_m=25.0, legal_setback_m=3.0)
    top = compose(s, [{"point_id": "fp1", "drawing_type": "floor_plan",
                       "total_area_sqm": 500.0, "score": 0.95}])[0]
    assert top.placement is not None and top.placement["building"] is not None
    assert top.to_dict()["placement"]["site"]["w"] == 40.0


def test_compose_exposes_primary_content_hash():
    # 피드백(👍👎) 학습 연결키 — 주 도면 content_hash가 후보/to_dict에 노출
    s = _site()
    matches = [{"point_id": "fp1", "drawing_type": "floor_plan", "total_area_sqm": 500.0,
                "score": 0.95, "content_hash": "abc123def4560000"}]
    top = compose(s, matches)[0]
    assert top.primary_content_hash == "abc123def4560000"
    assert top.to_dict()["primary_content_hash"] == "abc123def4560000"
    # content_hash 없는 매치는 None(정직)
    top2 = compose(s, [{"point_id": "x", "drawing_type": "floor_plan",
                        "total_area_sqm": 500.0, "score": 0.9}])[0]
    assert top2.primary_content_hash is None
    # ★비-hex content_hash는 None으로 차단(타 경로와 계약 통일)
    top3 = compose(s, [{"point_id": "y", "drawing_type": "floor_plan", "total_area_sqm": 500.0,
                        "score": 0.9, "content_hash": "../etc/passwd"}])[0]
    assert top3.primary_content_hash is None


def test_compose_assembles_discipline_drawing_set():
    # ★분야별 도면 세트 조합 — 건축+구조+전기 매칭 → selected에 전 종류, 분야 커버리지·미확보 갭
    s = _site()
    matches = [
        {"point_id": "fp1", "drawing_type": "floor_plan", "total_area_sqm": 500.0, "score": 0.95},
        {"point_id": "st1", "drawing_type": "structural_plan", "total_area_sqm": None, "score": 0.9},
        {"point_id": "el1", "drawing_type": "electrical_plan", "total_area_sqm": None, "score": 0.85},
    ]
    top = compose(s, matches)[0]
    # 세트에 3개 종류 모두 포함
    assert set(top.selected) == {"floor_plan", "structural_plan", "electrical_plan"}
    # 분야 커버: 건축·구조·전기
    assert {"건축", "구조", "전기"} <= set(top.disciplines_covered)
    # 미확보 핵심분야(기계설비·급배수위생·소방) 정직 고지
    assert "기계설비" in top.missing_disciplines and "소방" in top.missing_disciplines
    assert any("분야별 도면 미확보" in w for w in top.warnings)
    d = top.to_dict()
    assert "disciplines_covered" in d and "missing_disciplines" in d


def test_compose_ranking_stable_with_shared_set():
    # 분야세트 풍부화 후에도 동일 동반세트 후보는 score 내림차순 유지(회귀 안전).
    s = _site()
    matches = [
        {"point_id": "a", "drawing_type": "floor_plan", "total_area_sqm": 590.0, "score": 0.99},
        {"point_id": "b", "drawing_type": "floor_plan", "total_area_sqm": 590.0, "score": 0.50},
        {"point_id": "st", "drawing_type": "structural_plan", "total_area_sqm": None, "score": 0.9},
    ]
    cands = compose(s, matches, top_n=2)
    assert len(cands) == 2 and cands[0].score >= cands[1].score  # 내림차순 유지
    # 두 후보 모두 동일 분야세트(건축+구조) → completeness 동일, 정렬은 fitness 기반
    assert set(cands[0].disciplines_covered) == set(cands[1].disciplines_covered)


def test_compute_parking_layout_packs_stalls():
    # footprint 600㎡(정사각 ≈24.5m) · 100대 요구 → 베이/열 패킹·소요층수·대표 좌표
    s = _site()  # footprint 600
    lay = compute_parking_layout(s, 100)
    assert lay is not None
    assert lay["stalls_per_floor"] > 0 and lay["floors_for_parking"] >= 1
    # 소요층수 = ceil(요구 / 층당)
    import math as _m
    assert lay["floors_for_parking"] == _m.ceil(100 / lay["stalls_per_floor"])
    # 대표 좌표 — 표준 구획 치수, 캡 이내
    assert lay["stalls"] and all(st["w"] == 2.5 and st["l"] == 5.0 for st in lay["stalls"])
    assert len(lay["stalls"]) <= lay["stalls_per_floor"]


def test_compute_parking_layout_small_footprint_unfit():
    # footprint이 1베이(16m)보다 작으면 자동배치 불가 정직 고지
    s = _site(area_sqm=100.0, legal_bcr_pct=20.0, legal_far_pct=50.0)  # footprint 20㎡ → 한 변 ~4.5m
    lay = compute_parking_layout(s, 10)
    assert lay is not None and lay["stalls_per_floor"] == 0
    assert lay["floors_for_parking"] is None and "자동배치 불가" in lay["note"]


def test_compute_parking_layout_none_when_no_basis():
    assert compute_parking_layout(SiteContext(area_sqm=1000.0), 10) is None  # footprint 미상
    assert compute_parking_layout(_site(), 0) is None                        # 요구 0


def test_compose_attaches_parking_fields():
    # 조합 결과에 주차설계 필드가 부착되는지(통합)
    s = _site()
    matches = [{"point_id": "fp1", "drawing_type": "floor_plan", "total_area_sqm": 500.0, "score": 0.95}]
    top = compose(s, matches)[0]
    assert top.parking_required is not None and top.parking_required > 0
    assert top.parking_area_sqm == top.parking_required * 33.0
    assert top.parking_feasible is True
    d = top.to_dict()
    assert "parking_area_sqm" in d and "parking_feasible" in d
