"""design_ingest 법규 연결성(coverage) 검증 — 전 단계 매핑 키가 레지스트리에 실재하는지 전수 확인.

사용자 요구: 부동산개발·건축 관련 모든 법규를 참조하고 '연결되어 있는지' 분석·검증.
"""

from app.services.design_ingest.law_coverage import (
    DESIGN_LAW_MAP,
    all_referenced_laws,
    laws_for,
    verify_coverage,
)
from app.services.legal.legal_reference_registry import get_legal_ref


def test_all_mapped_keys_resolve_in_registry():
    """매핑된 모든 법규 키가 레지스트리에 연결(전수) — unresolved 0이어야 완결."""
    cov = verify_coverage()
    assert cov["ok"], f"미연결 법규 키: {cov['unresolved']}"
    assert cov["resolved"] == cov["total_keys"]
    assert cov["total_keys"] >= 50  # 전수조사 보강 후 충분한 커버리지


def test_key_newly_added_laws_present():
    """사용자 지적 법규(집합건물법·기부채납·국유재산·공동주택관리·개발이익환수 등) 연결 확인."""
    must_have = {
        "condo_ownership": "집합건물",
        "public_facility_contribution": "공공시설",  # 기부채납(국토계획법 제65조)
        "state_property": "국유재산",
        "public_property": "공유재산",
        "apartment_management": "공동주택관리",
        "development_levy": "개발이익",
        "fire_safety": "소방",
        "env_impact": "환경영향평가",
        "appraisal": "감정평가",
        "farmland_conversion": "농지",
        "forest_conversion": "산지관리",
        "cultural_heritage": "문화유산",
    }
    for key, kw in must_have.items():
        ref = get_legal_ref(key)
        assert ref is not None, f"{key} 미연결"
        # 기부채납은 국토계획법 제65조라 키워드가 title에 있음 → law_name+title로 확인
        assert kw in (ref["law_name"] + " " + ref["title"]), f"{key} 불일치: {ref}"


def test_condo_ownership_has_verified_article_link():
    """집합건물법 제20조(대지권 일체성)는 조문 딥링크 verified."""
    ref = get_legal_ref("condo_ownership")
    assert ref["article"] == "제20조" and ref["url"] and "law.go.kr" in ref["url"]


def test_laws_for_domain_returns_records_with_urlstatus():
    recs = laws_for("sales_rights")
    assert recs and all("url_status" in r and "law_name" in r for r in recs)
    # 집합건물법이 분양·권리 단계에 연결돼 있어야 함
    assert any("집합건물" in r["law_name"] for r in recs)


def test_all_referenced_laws_dedup():
    allrecs = all_referenced_laws()
    keys = [r["key"] for r in allrecs]
    assert len(keys) == len(set(keys))  # 중복 제거
    # 매핑 총 유니크 키 수와 일치(미존재 키 없음)
    unique_mapped = {k for ks in DESIGN_LAW_MAP.values() for k in ks}
    assert len(allrecs) == len(unique_mapped)
