"""다필지 통합분석 — AI 부지분석 해석이 대표번지가 아닌 '통합 N필지' 기준인지 검증.

★사용자 신고: 부지분석이 아직도 대표번지 기준. 근본=interp_input land_area_sqm이 단일 PNU값.
수정=다필지면 통합면적 주입 + integrated_multi_parcel 컨텍스트로 LLM이 통합 종합판단.
"""
from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter


def test_compact_includes_integrated_for_multi_parcel():
    """다필지(integrated) input → compact에 integrated_multi_parcel 주입."""
    itp = SiteAnalysisInterpreter()
    data = {
        "address": "서울 종로구 사직동", "zone_type": "제2종일반주거지역", "land_area_sqm": 990,
        "integrated": {"is_multi_parcel": True, "parcel_count": 3, "total_area_sqm": 990,
                       "blended_far_pct": 210, "blended_bcr_pct": 60, "note": "통합 3필지 990㎡ 기준"},
    }
    c = itp._extract_compact_data(data)
    assert "integrated_multi_parcel" in c
    ig = c["integrated_multi_parcel"]
    assert ig["parcel_count"] == 3 and ig["total_area_sqm"] == 990
    assert "통합" in (ig["note"] or "")


def test_single_parcel_no_integrated():
    """단일 필지(integrated 없음/미다필지) → 무회귀(integrated_multi_parcel 미주입)."""
    itp = SiteAnalysisInterpreter()
    c = itp._extract_compact_data({"address": "x", "zone_type": "제2종일반주거지역", "land_area_sqm": 300})
    assert "integrated_multi_parcel" not in c
    # is_multi_parcel=False면 주입 안 함
    c2 = itp._extract_compact_data({"address": "x", "land_area_sqm": 300,
                                    "integrated": {"is_multi_parcel": False, "parcel_count": 1}})
    assert "integrated_multi_parcel" not in c2
