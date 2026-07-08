"""다필지 조립(D-assembly) 테스트 — §84 걸침 규정·W1 합류·최종 보고 계약.

계획서 MULTI_PARCEL_ATTRIBUTES_PLAN_2026-07-03 §S3-A(제84조)·S3-B/C 합류·S4 훅·S5 조립.

검증 축:
  A. 국계법 §84 zone_straddle_ruling — 330㎡ 이하/초과/단일/도로변 띠모양 상업지역 660㎡/
     녹지 걸침(§84③ 각각 적용) 5계열 + 기존 _aggregate_integrated_zoning 키·수치 불변(INV).
  B. detect_multi_parcel 합류 형상 — per_parcel.area_sqm, usable_area, area_verification
     (refresh_fn 주입), senior_review, exclusion_scenario. 기존 키 전부 불변.
  C. 제외 시나리오 재산정 정합 — 제외 후 통합한도 = remaining 재실행 결과.
  D. build_multi_parcel_report 최종 보고 계약(S5) — matrix·usable 3계층·straddle·
     charges 통합 합산·verification·senior_review·honest_limitations.
"""
from __future__ import annotations

from app.services.zoning.special_parcel import (
    _aggregate_integrated_zoning,
    build_multi_parcel_report,
    detect_multi_parcel,
)


def _p(zone, area, far_eff, bcr_eff, far_legal, bcr_legal, far_basis="조례", **extra):
    """테스트 필지 dict — _enrich_effective_and_special 부착 키 형태(기존 테스트 관례)."""
    d = {
        "zone_type": zone, "area_sqm": area,
        "_far_eff": far_eff, "_bcr_eff": bcr_eff,
        "_far_legal": far_legal, "_bcr_legal": bcr_legal,
        "_far_basis": far_basis,
    }
    d.update(extra)
    return d


# ──────────────────────────────────────────────────────────────────────────
# A. §84 걸침 규정 — zone_straddle_ruling
# ──────────────────────────────────────────────────────────────────────────

def test_straddle_small_part_weighted_average():
    """가장 작은 부분 300㎡ ≤ 330㎡ → '가중평균+과반'(§84① + 령 §94)."""
    enriched = [
        _p("일반상업지역", 1000, 800, 60, 1300, 80),
        _p("제2종일반주거지역", 300, 200, 50, 250, 60),
    ]
    r = _aggregate_integrated_zoning(enriched)
    ruling = r["zone_straddle_ruling"]
    assert ruling["straddle"] is True
    assert ruling["applied_rule"] == "가중평균+과반"
    assert ruling["threshold_sqm"] == 330.0
    assert ruling["smallest_part"]["zone"] == "제2종일반주거지역"
    assert ruling["smallest_part"]["area_sqm"] == 300.0
    # 그 밖의 규정 적용 대상 = 가장 넓은 부분(일반상업지역).
    assert ruling["largest_part"]["zone"] == "일반상업지역"
    # 법령 근거(레지스트리 verified) — §84(법)·§94(령) 동반.
    arts = [str(ref.get("article") or "") for ref in ruling["legal_refs"]]
    assert any("제84조" in a for a in arts), ruling["legal_refs"]
    assert any("제94조" in a for a in arts), ruling["legal_refs"]
    assert ruling["per_zone_breakdown"], "per_zone_breakdown 누락"
    assert ruling["honest_notes"], "honest_notes 누락"


def test_straddle_over_threshold_each_part():
    """가장 작은 부분 500㎡ > 330㎡ → '부분별각각' + blended 지표 참고치 정직 고지."""
    enriched = [
        _p("일반상업지역", 1000, 800, 60, 1300, 80),
        _p("제2종일반주거지역", 500, 200, 50, 250, 60),
    ]
    r = _aggregate_integrated_zoning(enriched)
    ruling = r["zone_straddle_ruling"]
    assert ruling["straddle"] is True
    assert ruling["applied_rule"] == "부분별각각"
    # 부분별각각인 경우 면적가중(blended) 지표는 법적 적용치가 아님을 정직 고지.
    assert any("참고치" in n for n in ruling["honest_notes"]), ruling["honest_notes"]


def test_single_zone_no_straddle():
    """단일 용도지역 → straddle=False, applied_rule=None(§84 미적용)."""
    enriched = [
        _p("제2종일반주거지역", 700, 200, 50, 250, 60),
        _p("제2종일반주거지역", 300, 200, 50, 250, 60),
    ]
    r = _aggregate_integrated_zoning(enriched)
    ruling = r["zone_straddle_ruling"]
    assert ruling["straddle"] is False
    assert ruling["applied_rule"] is None


def test_roadside_strip_commercial_threshold_660():
    """도로변 띠 모양 상업지역 걸침(옵션 주입) → 임계 660㎡(령 §94 단서)."""
    enriched = [
        _p("일반상업지역", 1000, 800, 60, 1300, 80),
        _p("제2종일반주거지역", 500, 200, 50, 250, 60),
    ]
    r = _aggregate_integrated_zoning(enriched, roadside_strip_commercial=True)
    ruling = r["zone_straddle_ruling"]
    assert ruling["threshold_sqm"] == 660.0
    assert ruling["roadside_strip_commercial"] is True
    # 500 ≤ 660 → 가중평균+과반.
    assert ruling["applied_rule"] == "가중평균+과반"


def test_green_zone_straddle_each_part_and_exception():
    """§84③ — 녹지지역 걸침은 각각 적용. 단, 가장 작은 부분이 녹지이고 임계 이하면 ①(가중평균)."""
    # (a) 녹지 1000 + 주거 300: 가장 작은 부분(주거)이 녹지가 아님 → ③ 각각 적용(부분별각각).
    r_a = _aggregate_integrated_zoning([
        _p("자연녹지지역", 1000, 80, 20, 100, 20),
        _p("제2종일반주거지역", 300, 200, 50, 250, 60),
    ])
    ruling_a = r_a["zone_straddle_ruling"]
    assert ruling_a["applied_rule"] == "부분별각각", ruling_a
    assert ruling_a["green_zone_rule_applied"] is True
    # (b) 녹지 300 + 주거 1000: 가장 작은 부분이 녹지이고 300 ≤ 330 → ③ 괄호 예외 → ① 가중평균.
    r_b = _aggregate_integrated_zoning([
        _p("자연녹지지역", 300, 80, 20, 100, 20),
        _p("제2종일반주거지역", 1000, 200, 50, 250, 60),
    ])
    ruling_b = r_b["zone_straddle_ruling"]
    assert ruling_b["applied_rule"] == "가중평균+과반", ruling_b
    assert ruling_b["green_zone_rule_applied"] is False


def test_aggregate_existing_keys_invariant():
    """INV — 기존 _aggregate_integrated_zoning 키·수치 계산 불변(기존 테스트 수치 재검)."""
    enriched = [
        _p("일반상업지역", 1000, 800, 60, 1300, 80),
        _p("제2종일반주거지역", 500, 200, 50, 250, 60, far_basis="법정상한"),
    ]
    r = _aggregate_integrated_zoning(enriched)
    assert r["dominant_zone"] == "mixed_review_required"
    assert r["blended_far_eff_pct"] == 600.0
    assert r["integrated_gfa_sqm"] == 9000.0
    assert r["gfa_basis"] == "per_parcel_effective_sum"
    assert r["total_area_sqm"] == 1500.0
    for key in ("parcel_count", "zone_mix", "dominant_basis", "blended_bcr_eff_pct",
                "blended_far_legal_pct", "blended_bcr_legal_pct",
                "integrated_footprint_sqm", "far_basis_note", "warnings"):
        assert key in r, f"기존 키 {key} 소실"


# ──────────────────────────────────────────────────────────────────────────
# B. detect_multi_parcel 합류 형상 + 기존 키 불변
# ──────────────────────────────────────────────────────────────────────────

def _parcels_mixed():
    return [
        {"pnu": "P-A", "address": "A", "land_category": "대",
         "zone_type": "제2종일반주거지역", "area_sqm": 1000,
         "_far_eff": 200, "_bcr_eff": 50, "_far_legal": 250, "_bcr_legal": 60,
         "_far_basis": "조례"},
        {"pnu": "P-F", "address": "F", "land_category": "임야",
         "zone_type": "계획관리지역", "area_sqm": 600,
         "_far_eff": 100, "_bcr_eff": 40, "_far_legal": 100, "_bcr_legal": 40,
         "_far_basis": "조례"},
        {"pnu": "P-N", "address": "N", "land_category": "전",
         "zone_type": "계획관리지역", "area_sqm": 400,
         "official_land_price_per_m2": 100000,
         "_far_eff": 100, "_bcr_eff": 40, "_far_legal": 100, "_bcr_legal": 40,
         "_far_basis": "조례"},
    ]


def test_multi_parcel_confluence_shape_and_invariants():
    """합류 형상 — 신규 키(usable_area·area_verification·senior_review·zone_straddle_ruling·
    exclusion_scenario)와 per_parcel.area_sqm, 기존 키·게이트 판정 전부 불변."""
    m = detect_multi_parcel(_parcels_mixed())
    # ── 기존 키 불변(INV) ──
    for key in ("parcel_count", "special_count", "developability", "resolvable",
                "blocking_parcels", "per_parcel", "honest_disclosure",
                "recommendation", "note"):
        assert key in m, f"기존 키 {key} 소실"
    assert m["developability"] == "NEEDS_OFFICIAL_SURVEY"  # 임야 게이트 보존
    assert m["blocking_parcels"] == []
    assert m["parcel_count"] == 3
    # ── per_parcel 에 area_sqm 부착(additive) + 기존 필드 보존 ──
    for x in m["per_parcel"]:
        for key in ("index", "pnu", "address", "land_category", "special"):
            assert key in x
    assert [x["area_sqm"] for x in m["per_parcel"]] == [1000.0, 600.0, 400.0]
    # ── usable_area 3계층(합류) — 면적 보존 불변식 ──
    ua = m["usable_area"]
    assert ua["gross_sqm"] == 2000.0
    assert ua["usable_confirmed_sqm"] + ua["usable_conditional_sqm"] + ua["excluded_sqm"] \
        == ua["gross_sqm"]
    assert ua["usable_confirmed_sqm"] == 1000.0        # 대(일상)
    assert ua["usable_conditional_sqm"] == 1000.0      # 임야(NEEDS_OFFICIAL_SURVEY)+농지(CONDITIONAL)
    # ── area_verification(S4 훅) ──
    av = m["area_verification"]
    assert av["parcel_count"] == 3
    assert av["policy"]["auto_correction"] is False
    # ── senior_review(RuleEvaluation.to_dict 리스트) ──
    sr = m["senior_review"]
    assert isinstance(sr, list) and sr, "senior_review 비어있음"
    for ev in sr:
        for key in ("rule_id", "label", "verdict", "threshold", "basis", "detail"):
            assert key in ev, ev
    assert any(ev["rule_id"] == "assembly.blocked_share" for ev in sr)
    # ── straddle ruling 동반(additive) ──
    assert m["zone_straddle_ruling"]["straddle"] is True
    # 차단필지 없음 → 제외 시나리오 없음(None).
    assert m["exclusion_scenario"] is None


def test_no_special_branch_confluence():
    """전 필지 일상(특이 없음) 조기반환 분기에도 합류 키 동반 + 기존 키(summary) 불변."""
    m = detect_multi_parcel([
        {"pnu": "N1", "land_category": "대", "zone_type": "제2종일반주거지역", "area_sqm": 500},
        {"pnu": "N2", "land_category": "대", "zone_type": "제2종일반주거지역", "area_sqm": 500},
    ])
    for key in ("parcel_count", "special_count", "developability", "resolvable",
                "blocking_parcels", "per_parcel", "honest_disclosure", "summary"):
        assert key in m, f"기존 키 {key} 소실"
    assert m["developability"] == "POSSIBLE"
    assert m["usable_area"]["usable_confirmed_sqm"] == 1000.0
    assert m["area_verification"]["parcel_count"] == 2
    assert isinstance(m["senior_review"], list)
    assert m["zone_straddle_ruling"]["straddle"] is False
    assert m["exclusion_scenario"] is None
    assert [x["area_sqm"] for x in m["per_parcel"]] == [500.0, 500.0]


def test_refresh_fn_passthrough_converges():
    """S4 훅 — detect_multi_parcel(refresh_fn=...)이 verify_parcel_areas 재보강에 전달돼
    괴리 필지가 1회 재보강 후 수렴한다(원본 parcel 불변·자동 보정 없음)."""
    parcel = {"pnu": "R1", "land_category": "대", "zone_type": "제2종일반주거지역",
              "area_sqm": 1000, "area_input_sqm": 2000}
    calls: list[str] = []

    def refresh(p):
        calls.append(p.get("pnu"))
        return {"area_input_sqm": 1000.0}

    m = detect_multi_parcel([parcel], refresh_fn=refresh)
    entry = m["area_verification"]["per_parcel"][0]
    assert calls == ["R1"], "refresh_fn 미호출 — 훅 배선 단선"
    assert entry["refresh_attempted"] is True
    assert entry["converged_after_refresh"] is True
    assert entry["status"] == "consistent"
    # 무날조 — 원본 parcel은 절대 변형되지 않는다.
    assert parcel["area_input_sqm"] == 2000


# ──────────────────────────────────────────────────────────────────────────
# C. 제외 시나리오 재산정 정합
# ──────────────────────────────────────────────────────────────────────────

def _parcels_with_gb():
    return [
        {"pnu": "P-A", "address": "A", "land_category": "대",
         "zone_type": "제2종일반주거지역", "area_sqm": 1000,
         "_far_eff": 200, "_bcr_eff": 50, "_far_legal": 250, "_bcr_legal": 60,
         "_far_basis": "조례"},
        {"pnu": "P-GB", "address": "GB", "land_category": "대",
         "zone_type": "자연녹지지역", "area_sqm": 500,
         "special_districts": ["개발제한구역"],
         "_far_eff": 80, "_bcr_eff": 20, "_far_legal": 100, "_bcr_legal": 20,
         "_far_basis": "조례"},
    ]


def test_exclusion_scenario_recalculates_integrated_limits():
    """차단필지(GB, resolvable=NO) 존재 → 전부 제외안 1건 동반, 제외 후 통합한도는
    remaining 필지로 _aggregate_integrated_zoning 재실행 결과와 정합."""
    m = detect_multi_parcel(_parcels_with_gb())
    assert m["resolvable"] == "NO"
    assert [b["pnu"] for b in m["blocking_parcels"]] == ["P-GB"]
    sc = m["exclusion_scenario"]
    assert sc is not None
    assert sc["applied_exclude_pnus"] == ["P-GB"]
    assert sc["lost_area_sqm"] == 500.0
    # 제외 후 3계층: 잔여 1000㎡ 전부 confirmed.
    assert sc["after"]["gross_sqm"] == 1000.0
    assert sc["after"]["usable_confirmed_sqm"] == 1000.0
    # 정합: after.gross == before.gross - lost.
    assert sc["after"]["gross_sqm"] == sc["before"]["gross_sqm"] - sc["lost_area_sqm"]
    # 제외 후 통합한도 = remaining 재실행 결과(단일 주거 필지).
    iz = sc["integrated_zoning_after_exclusion"]
    assert iz["total_area_sqm"] == 1000.0
    assert iz["blended_far_eff_pct"] == 200.0
    assert iz["dominant_zone"] == "제2종일반주거지역"
    assert iz["zone_straddle_ruling"]["straddle"] is False
    # 응답 비대·내부키 누출 방지 — 원본 dict 리스트는 시나리오에 싣지 않는다.
    assert "remaining_parcels" not in sc
    assert sc["remaining_parcel_count"] == 1


# ──────────────────────────────────────────────────────────────────────────
# D. build_multi_parcel_report — 최종 보고 계약(S5)
# ──────────────────────────────────────────────────────────────────────────

def test_report_contract_full():
    """S5 계약 — matrix·usable 3계층·straddle·charges 통합 합산·verification·
    senior_review·honest_limitations 전 키 + 근거 동반."""
    parcels = [
        {"pnu": "P-A", "address": "A", "land_category": "대",
         "zone_type": "제2종일반주거지역", "area_sqm": 1000,
         "_far_eff": 200, "_bcr_eff": 50, "_far_legal": 250, "_bcr_legal": 60,
         "_far_basis": "조례"},
        {"pnu": "P-N", "address": "N", "land_category": "전",
         "zone_type": "계획관리지역", "area_sqm": 500,
         "official_land_price_per_m2": 100000,
         "_far_eff": 100, "_bcr_eff": 40, "_far_legal": 100, "_bcr_legal": 40,
         "_far_basis": "조례"},
        {"pnu": "P-GB", "address": "GB", "land_category": "대",
         "zone_type": "자연녹지지역", "area_sqm": 300,
         "special_districts": ["개발제한구역"],
         "_far_eff": 80, "_bcr_eff": 20, "_far_legal": 100, "_bcr_legal": 20,
         "_far_basis": "조례"},
    ]
    r = build_multi_parcel_report(parcels)
    # ── 보고 계약 키 전수 ──
    for key in ("report_type", "parcel_count", "matrix", "usable_area",
                "zone_straddle_ruling", "integrated_zoning", "charges",
                "verification", "senior_review", "senior_verdict",
                "exclusion_scenario", "developability", "resolvable",
                "blocking_parcels", "honest_disclosure", "recommendation",
                "honest_limitations", "basis"):
        assert key in r, f"보고 키 {key} 누락"
    assert r["report_type"] == "multi_parcel_report"
    assert r["parcel_count"] == 3
    # ── matrix: 필지×속성×판정 ──
    assert len(r["matrix"]) == 3
    for row in r["matrix"]:
        for key in ("index", "pnu", "address", "land_category", "zone_type",
                    "area_sqm", "developability", "resolvable", "gate",
                    "usable_tier", "verification_status", "factor_categories"):
            assert key in row, f"matrix 행 키 {key} 누락: {row}"
    by_pnu = {row["pnu"]: row for row in r["matrix"]}
    assert by_pnu["P-A"]["usable_tier"] == "confirmed"
    assert by_pnu["P-N"]["usable_tier"] == "conditional"
    assert by_pnu["P-GB"]["usable_tier"] == "excluded"
    assert by_pnu["P-GB"]["gate"] == "BLOCK"
    # ── usable 3계층(면적 보존) ──
    ua = r["usable_area"]
    assert ua["gross_sqm"] == 1800.0
    assert ua["usable_confirmed_sqm"] + ua["usable_conditional_sqm"] + ua["excluded_sqm"] \
        == ua["gross_sqm"]
    # ── charges 통합 합산: 농지보전부담금 100,000×30%×500 = 15,000,000(캡 미적용) ──
    ch = r["charges"]
    assert ch["estimated"] is True
    assert ch["total_estimated_won"] == 15_000_000.0
    assert len(ch["per_parcel"]) == 1
    assert ch["per_parcel"][0]["pnu"] == "P-N"
    assert ch["per_parcel"][0]["charge_name"] == "농지보전부담금"
    assert ch["unestimated_count"] == 0
    assert "확정 부과액 아님" in ch["honest_note"]
    # ── straddle·verification·senior ──
    assert r["zone_straddle_ruling"]["straddle"] is True
    assert r["verification"]["parcel_count"] == 3
    assert isinstance(r["senior_review"], list) and r["senior_review"]
    assert r["senior_verdict"] in ("PASS", "WARN", "BLOCK")
    # ── 차단필지 존재 → 제외 시나리오 동반 + 게이트 미러 ──
    assert r["exclusion_scenario"] is not None
    assert r["resolvable"] == "NO"
    assert r["developability"] == "BLOCKED"
    # ── 정직 한계 고지(설명가능성 기본화) ──
    assert isinstance(r["honest_limitations"], list) and r["honest_limitations"]
    assert any("하나의 대지" in s or "합필" in s for s in r["honest_limitations"])


def test_report_charges_none_when_no_notice():
    """부담금 고지 필지가 없으면 total=None(0 날조 금지) + per_parcel 빈 리스트."""
    r = build_multi_parcel_report([
        {"pnu": "N1", "land_category": "대", "zone_type": "제2종일반주거지역", "area_sqm": 500},
    ])
    assert r["charges"]["total_estimated_won"] is None
    assert r["charges"]["per_parcel"] == []
    # 단일 필지 — straddle 미적용.
    assert r["zone_straddle_ruling"]["straddle"] is False
    assert r["exclusion_scenario"] is None
