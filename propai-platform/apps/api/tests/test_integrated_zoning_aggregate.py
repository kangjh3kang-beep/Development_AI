"""다필지 통합 용도지역 집계(_aggregate_integrated_zoning) 단위테스트.

검증 포인트:
  - 혼재(2용도·규제성격 상이) → dominant_zone="mixed_review_required"(임의 단일화 금지).
  - 결측(far_eff None) → 면적가중에서 제외 + warning, 통합 GFA는 per-parcel 합(혼재 과대방지).
  - 동률(±5% 이내) → "mixed_review_required".
  - integrated_gfa = Σ(area_i×far_eff_i/100) (단순 통합면적×blended_far 금지) 확인.
"""
from app.services.zoning.special_parcel import (
    _aggregate_integrated_zoning,
    _zone_family,
)


def _p(zone, area, far_eff, bcr_eff, far_legal, bcr_legal, far_basis="조례"):
    """테스트 필지 dict 헬퍼 — _enrich_effective_and_special가 부착하는 키 형태."""
    return {
        "zone_type": zone, "area_sqm": area,
        "_far_eff": far_eff, "_bcr_eff": bcr_eff,
        "_far_legal": far_legal, "_bcr_legal": bcr_legal,
        "_far_basis": far_basis,
    }


def test_mixed_two_zones_requires_review():
    """상업+주거(규제성격 상이) 혼재 → dominant=mixed_review_required + 혼재 경고."""
    enriched = [
        _p("일반상업지역", 1000, 800, 60, 1300, 80),
        _p("제2종일반주거지역", 500, 200, 50, 250, 60, far_basis="법정상한"),
    ]
    r = _aggregate_integrated_zoning(enriched)
    assert r["dominant_zone"] == "mixed_review_required", r["dominant_zone"]
    assert r["dominant_basis"] == "area_weighted"
    # 면적가중 실효 용적률 = (1000*800+500*200)/1500 = 600
    assert r["blended_far_eff_pct"] == 600.0, r["blended_far_eff_pct"]
    # 통합 GFA = Σ(area×far_eff/100) = 1000*8 + 500*2 = 9000 (per-parcel 합)
    assert r["integrated_gfa_sqm"] == 9000.0, r["integrated_gfa_sqm"]
    assert r["gfa_basis"] == "per_parcel_effective_sum"
    # 법정폴백 필지(_far_basis '법정상한') 수가 far_basis_note에 반영.
    assert "1개" in r["far_basis_note"], r["far_basis_note"]
    assert any("혼재" in w for w in r["warnings"]), r["warnings"]
    # zone_mix는 면적 내림차순.
    assert [z["zone"] for z in r["zone_mix"]] == ["일반상업지역", "제2종일반주거지역"]


def test_missing_far_eff_excluded_and_gfa_not_overstated():
    """far_eff 결측 필지는 면적가중 제외 + warning, 통합 GFA는 per-parcel 합(과대방지)."""
    enriched = [
        _p("일반상업지역", 1000, 800, 60, 1300, 80),
        # 결측 필지(면적은 크다) — blended/GFA에서 제외되어야 한다.
        _p("미상", 2000, None, None, None, None, far_basis=None),
    ]
    r = _aggregate_integrated_zoning(enriched)
    # 결측(2000㎡)을 분모에서 제외 → blended_far_eff = 800.
    assert r["blended_far_eff_pct"] == 800.0, r["blended_far_eff_pct"]
    # 통합 GFA = per-parcel 합 = 1000*8 = 8000.
    #   ★단순 통합면적×blended_far = 3000*800/100 = 24000(3배 과대)이 아님을 확인.
    assert r["integrated_gfa_sqm"] == 8000.0, r["integrated_gfa_sqm"]
    assert r["integrated_gfa_sqm"] != round(3000 * 800 / 100, 2)
    assert r["total_area_sqm"] == 3000.0
    # 결측 경고가 들어가야 한다(정직).
    assert any("결측" in w for w in r["warnings"]), r["warnings"]
    # 실값 필지가 1개뿐이라 mixed/tie 아님 → dominant는 일반상업지역.
    assert r["dominant_zone"] == "일반상업지역", r["dominant_zone"]


def test_tie_within_5pct_requires_review():
    """상위 두 용도지역 면적이 ±5% 이내(동률) → mixed_review_required."""
    enriched = [
        _p("제1종일반주거지역", 1000, 150, 60, 200, 60),
        _p("제2종일반주거지역", 1020, 200, 60, 250, 60),  # 2% 차이 → 동률
    ]
    r = _aggregate_integrated_zoning(enriched)
    assert r["dominant_zone"] == "mixed_review_required", r["dominant_zone"]
    assert any("동률" in w for w in r["warnings"]), r["warnings"]


def test_single_family_no_tie_picks_dominant():
    """성격 동일(주거)·면적 격차 큼(동률 아님) → 최대 면적 용도지역을 dominant로 채택."""
    enriched = [
        _p("제1종일반주거지역", 500, 150, 60, 200, 60),
        _p("제2종일반주거지역", 2000, 200, 60, 250, 60),  # 압도적 다수
    ]
    r = _aggregate_integrated_zoning(enriched)
    assert r["dominant_zone"] == "제2종일반주거지역", r["dominant_zone"]
    # 전 필지 조례 반영 → 법정폴백 없음.
    assert "법정폴백 없음" in r["far_basis_note"], r["far_basis_note"]


def test_zone_family_classification():
    """규제성격 대분류(_zone_family) — 혼재 판정의 근거."""
    assert _zone_family("일반상업지역") == "상업"
    assert _zone_family("제2종일반주거지역") == "주거"
    assert _zone_family("일반공업지역") == "공업"
    assert _zone_family("자연녹지지역") == "녹지"
    assert _zone_family("") is None


def test_integrated_footprint_per_parcel_sum():
    """통합 건폐 바닥면적 = Σ(area×bcr_eff/100) — per-parcel 합."""
    enriched = [
        _p("일반상업지역", 1000, 800, 60, 1300, 80),
        _p("준주거지역", 1000, 400, 50, 500, 70),
    ]
    r = _aggregate_integrated_zoning(enriched)
    # footprint = 1000*0.6 + 1000*0.5 = 1100
    assert r["integrated_footprint_sqm"] == 1100.0, r["integrated_footprint_sqm"]
