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


def test_compose_est_gfa_envelope_and_underuse_warning():
    # ★실효 패리티: 작은 참조평면(200㎡)+높이한도면 est_gfa는 보수(600), 법적 상한 envelope는
    #   부지 잠재력(footprint600×3층=1800) 명시 산출. 둘이 벌어지면 정직 고지(조용한 저평가 제거).
    s = _site()  # footprint600·max_gfa2000·max_floors3
    top = compose(s, [{"point_id": "small", "drawing_type": "floor_plan",
                       "total_area_sqm": 200.0, "score": 0.9}])[0]
    assert top.estimated_gfa_sqm == 600.0          # 값 불변(참조평면 기준 보수)
    assert top.max_envelope_gfa_sqm == 1800.0      # 법적 상한(부지 잠재력) 명시 산출
    assert "max_envelope_gfa_sqm" in top.to_dict()
    assert any("법적 상한" in w and "상향 여지" in w for w in top.warnings)


def test_compose_est_gfa_no_underuse_warning_when_full():
    # 큰 평면(600㎡)으로 상한 근접(est_gfa==envelope==1800) 시 저평가 경고 없음(무회귀)
    s = _site()
    top = compose(s, [{"point_id": "big", "drawing_type": "floor_plan",
                       "total_area_sqm": 600.0, "score": 0.9}])[0]
    assert top.estimated_gfa_sqm == 1800.0 and top.max_envelope_gfa_sqm == 1800.0
    assert not any("법적 상한" in w and "상향 여지" in w for w in top.warnings)


def test_compute_placement_area_not_exceed_bcr_footprint():
    # ★정확성: 건물 area_sqm은 BCR footprint(actual_fp)를 초과하면 안 됨(w·d 개별반올림 드리프트 제거)
    from app.services.design_ingest.composition import compute_placement
    for w, d, bcr in [(40, 25, 60), (33, 33, 50), (50, 20, 70), (17, 23, 40)]:
        s = _site(area_sqm=float(w * d), legal_bcr_pct=float(bcr), width_m=float(w), depth_m=float(d))
        pl = compute_placement(s)
        if pl and pl.get("building"):
            actual_fp = min(s.buildable_footprint_sqm, pl["buildable_region_sqm"])
            assert pl["building"]["area_sqm"] <= actual_fp + 0.05, (w, d, bcr)


def test_compose_sources_provenance():
    # ★근거(provenance): 조합 출처가 채택 도면 종류·유사도·hash를 노출(어느 코퍼스에서 왔는지)
    s = _site()
    matches = [
        {"point_id": "fp1", "drawing_type": "floor_plan", "total_area_sqm": 500.0, "score": 0.95,
         "content_hash": "a1b2c3d4e5f60718"},  # 유효 16자 hex
        {"point_id": "sp1", "drawing_type": "site_plan", "total_area_sqm": 980.0, "score": 0.9},
    ]
    top = compose(s, matches, top_n=1)[0]
    srcs = top.sources
    assert srcs and isinstance(srcs, list)
    by_t = {x["drawing_type"]: x for x in srcs}
    assert "floor_plan" in by_t and "site_plan" in by_t  # 채택된 모든 종류 출처 노출
    assert by_t["floor_plan"]["point_id"] == "fp1"
    assert by_t["floor_plan"]["score"] == 0.95
    assert by_t["floor_plan"]["content_hash"] == "a1b2c3d4e5f60718"  # 유효 hex hash 통과
    # 짧은(무효) hash는 None으로 정직 처리 — site_plan은 hash 미제공 → None
    assert by_t["site_plan"]["content_hash"] is None
    # to_dict 직렬화 경로에도 포함
    assert "sources" in top.to_dict() and len(top.to_dict()["sources"]) == len(srcs)


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


# ── P0~P2 성숙기능 배선(cad→design_ingest) 테스트 ─────────────────────────────

from app.services.design_ingest.composition import (  # noqa: E402
    _sunlight_envelope,
    compute_unit_breakdown,
)


def test_unit_breakdown_greedy_mix_no_fake_units():
    # P1-3: cad UNIT_TYPES 그리디 라운드로빈으로 평형 믹스 분해(소형 우선·가짜세대 금지)
    ub = compute_unit_breakdown(per_floor_net_sqm=500.0, floors=10, unit_types=["59A", "84A"])
    assert ub is not None
    assert ub["total_units"] > 0
    # 평형별 세대수 모두 양수(0세대 유형은 제외 — 가짜 1세대 강제 없음)
    assert all(u["count_per_floor"] > 0 and u["total_count"] > 0 for u in ub["units"])
    # 구성%(전용 면적 가중) 합 ~100
    assert abs(sum(u["ratio_pct"] for u in ub["units"]) - 100.0) < 1.0
    # 전용률은 평형 기반 산출(상수 0.75 탈피) — 합리적 범위
    assert 0.70 <= ub["efficiency"] <= 0.82


def test_unit_breakdown_none_when_infeasible_or_unknown():
    # 인식 불가 평형 → None(폴백은 호출자 책임)
    assert compute_unit_breakdown(500.0, 10, ["ZZZ"]) is None
    # 층당 순면적이 최소 평형보다 작음 → 세대 성립 불가 → None(무가짜세대)
    assert compute_unit_breakdown(20.0, 5, ["84A"]) is None
    # 근거 없음(면적/층수 미상) → None
    assert compute_unit_breakdown(None, 10, ["59A"]) is None
    assert compute_unit_breakdown(500.0, 0, ["59A"]) is None


def test_sunlight_envelope_residential_binding():
    # P0-1: 주거지역에서 정북일조 단계후퇴가 매스 층수/연면적을 제약(binding)
    s = SiteContext(area_sqm=1000.0, zone_code="2R", zone_name="제2종일반주거지역",
                    legal_bcr_pct=60.0, legal_far_pct=250.0, far_source="statutory",
                    legal_setback_m=1.0)
    env = _sunlight_envelope(s, bldg_w=30.0, bldg_d=20.0, far_floors=15, max_gfa=2500.0)
    assert env is not None
    assert env["binding"] is True              # 15층 요구 대비 일조로 증층 제약
    assert env["floors"] < 15
    assert len(env["profile"]) == env["floors"]
    # 상부층일수록 북측 후퇴(inset) 증가(또는 동일) — 단조 비감소
    insets = [p["inset_m"] for p in env["profile"]]
    assert insets == sorted(insets)


def test_sunlight_envelope_not_applicable_non_residential():
    # 준주거·상업·공업은 정북일조 미적용 → None(법 61조 적용범위 외)
    for zn in ("준주거지역", "일반상업지역", "준공업지역"):
        s = SiteContext(area_sqm=1000.0, zone_code="GC", zone_name=zn,
                        legal_bcr_pct=60.0, legal_far_pct=500.0)
        assert _sunlight_envelope(s, bldg_w=30.0, bldg_d=20.0, far_floors=20,
                                  max_gfa=10000.0) is None


def test_compose_seeds_reference_hint_and_sunlight():
    # P0-1+P0-2: 유사사례 종횡비 시딩 + 일조 envelope가 후보에 반영
    s = SiteContext(area_sqm=1500.0, zone_code="2R", zone_name="제2종일반주거지역",
                    legal_bcr_pct=60.0, legal_far_pct=250.0, far_source="statutory",
                    legal_setback_m=1.0, unit_types=["59A", "84A"],
                    reference_mass={"used": True,
                                    "hint": {"aspect": 2.0, "basis": "유사사례 종횡비 2.00"}})
    matches = [{"point_id": "fp1", "drawing_type": "floor_plan",
                "total_area_sqm": 700.0, "score": 0.95}]
    top = compose(s, matches, top_n=1)[0]
    d = top.to_dict()
    # 평형 분해 부착(P1-3)
    assert d["unit_breakdown"] and len(d["unit_breakdown"]) >= 1
    assert d["unit_efficiency"] is not None and d["estimated_units"] > 0
    # 일조 envelope 부착(P0-1)
    assert d["sunlight_profile"] is not None
    assert d["sunlight_profile"]["floors"] >= 1
    # 유사사례 힌트 부착(P0-2·검색 환류)
    assert d["reference_hint"] is not None and d["reference_hint"]["aspect"] == 2.0
    assert any("유사사례 피드백" in w for w in d["warnings"])


def test_site_context_zone_23_failclosed():
    # P1-4: 23종 fail-closed 계약 — 인식 zone은 확정 한도, 미인식은 None(무근거 폴백 금지)
    # 인식: 일반상업지역(7코드엔 없으나 23종엔 있음 — 확충 효과)
    s_known = site_context_from_zone("GC", 1000.0, zone_name="일반상업지역")
    assert s_known.legal_far_pct is not None and s_known.legal_bcr_pct is not None
    assert s_known.far_source in ("statutory", "ordinance")
    # 미인식 zone_name + 미인식 코드 → 확정 한도 None(fail-closed)·정직 경고
    s_unk = site_context_from_zone("ZZZ", 1000.0, zone_name="없는지역")
    # zone_code ZZZ는 7코드 폴백표가 있으므로 far가 채워질 수 있다 → fail-closed 검증은
    # zone_name 미인식 경고가 떴는지로 확인(무경고 폴백 차단).
    assert any("미확정" in w or "fail-closed" in w for w in s_unk.warnings)


def test_site_context_ordinance_height_setback_injection():
    # P2-5: 조례 height/setback 주입 → 매스 층수캡·이격 base 반영(floor_height 기본 3.0m)
    s = site_context_from_zone("3R", 2000.0, zone_name="제3종일반주거지역",
                               ordinance_height_m=30.0, ordinance_setback_m=3.0)
    assert s.legal_height_m == 30.0 and s.height_source == "ordinance"
    assert s.legal_setback_m == 3.0
    # 높이 30m / 층고 3m = 10층 캡
    assert s.max_floors_by_height == 10


def test_site_context_height_caps_floors():
    # 높이한도가 FAR 산정 층수보다 작으면 max_floors_est가 높이로 캡(min)
    # 제1종전용주거: far 100·bcr 50·height 10m → 높이캡 3층
    s = site_context_from_zone("1R", 1000.0, zone_name="제1종전용주거지역")
    assert s.legal_height_m == 10.0
    # max_floors_by_height = 10//3 = 3
    assert s.max_floors_by_height == 3
    # max_floors_est는 FAR(far100,bcr50: gfa1000/fp500=2)·높이(3) 중 작은 값
    assert s.max_floors_est is not None and s.max_floors_est <= 3


# ── D-A: 동간거리(0.8H)·1동 길이≤80m 게이트 ──

def test_dong_gap_uses_080h_with_min_floor():
    from app.services.design_ingest.composition import _DONG_GAP_MIN_M, _dong_gap_m
    # 높이 미상 → 하한 6m(정직 폴백)
    assert _dong_gap_m(None) == _DONG_GAP_MIN_M
    assert _dong_gap_m(0) == _DONG_GAP_MIN_M
    # 높이 30m → 0.8H = 24m
    assert _dong_gap_m(30.0) == 24.0
    # 저층(5m → 0.8H=4 < 6) → 하한 6m로 클램프
    assert _dong_gap_m(5.0) == _DONG_GAP_MIN_M


def test_compute_placement_dong_gap_height_based():
    # 고층 공동주택 다동 → 동간거리가 6m 고정이 아니라 0.8H(>6) 적용
    s = SiteContext(area_sqm=5000.0, zone_code="3R", legal_bcr_pct=50.0, legal_far_pct=300.0,
                    legal_height_m=60.0, far_source="ordinance", width_m=100.0, depth_m=50.0,
                    legal_setback_m=3.0, building_use_kr="공동주택")
    p = compute_placement(s)
    if p["dong_count"] > 1:
        # 60m 높이/3m 층고면 층수 다수 → 0.8H가 6m를 크게 상회
        assert p["gap_m"] > 6.0
        assert any("0.8H" in n or "인동간격" in n for n in p["notes"])


def test_compute_placement_one_dong_length_capped_80m():
    # 폭이 매우 긴 부지(149m급 단일매스 유발) → 1동 길이 게이트로 분동(각 동 길이 ≤ ~80m).
    s = SiteContext(area_sqm=150.0 * 30.0, zone_code="3R", legal_bcr_pct=80.0, legal_far_pct=300.0,
                    far_source="ordinance", width_m=150.0, depth_m=30.0, legal_setback_m=2.0,
                    building_use_kr="공동주택")
    p = compute_placement(s)
    # 분동되어 최대 1동 길이가 80m 이내(가용영역 제약 폴백 시 경고로 정직 고지)
    assert p["dong_count"] >= 2
    if p["max_dong_length_m"] > 80.0:
        assert any("80" in n for n in p["notes"])


def test_compute_core_layout_corridor_type_and_egress():
    from app.services.cad.auto_design_engine import AutoDesignEngineService as E
    # 중복도(기본) → 2.4m, 편복도 → 1.8m(공동주택)
    mass = {"building_width_m": 40.0, "building_depth_m": 15.0,
            "total_floor_area_sqm": 1200.0, "num_floors": 2,
            "building_footprint_sqm": 600.0}
    core_d = E.compute_core_layout(mass, "공동주택", corridor_type="double")
    core_s = E.compute_core_layout(mass, "공동주택", corridor_type="single")
    assert core_d["corridor_width_m"] == 2.4 and core_d["corridor_type"] == "double"
    assert core_s["corridor_width_m"] == 1.8 and core_s["corridor_type"] == "single"


def test_compute_core_layout_egress_adds_cores_for_long_block():
    from app.services.cad.auto_design_engine import AutoDesignEngineService as E
    # 1동 폭 300m·비내화(보행거리 30m) → 코어가 보행거리 기준으로 증설(연면적 기준보다 많아짐)
    mass = {"building_width_m": 300.0, "building_depth_m": 15.0,
            "total_floor_area_sqm": 1500.0, "num_floors": 1,
            "building_footprint_sqm": 1500.0}
    core = E.compute_core_layout(mass, "공동주택", fire_resistant=False)
    # 보행거리 기준 코어수 = ceil(300/(2*30)) = 5 ≥ 연면적기준 ceil(1500/1500)=1
    assert core["num_cores"] >= 5
    assert any("보행거리" in w for w in core["core_warnings"])
    assert core["travel_distance_m"] == 30.0
