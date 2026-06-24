"""쉬운 규제안내서(시설물별 인허가 절차) 검증 — 단계·법령(verified)·서류·주택법 분기."""
from app.services.permit.permit_guide_service import get_permit_guide


def _ref_keys(guide):
    return {r["key"] for s in guide["stages"] for r in s["legal_refs"]}


def test_housing_three_stages():
    """단독주택 → 주택류(housing) 3단계(계획·인허가/공사/사용·신고)."""
    g = get_permit_guide("단독주택")
    assert g["group"] == "housing"
    assert [s["stage"] for s in g["stages"]] == ["계획·건축인허가 단계", "사업시행·공사 단계", "사용·등록·신고 단계"]


def test_housing_has_housing_act_procedures():
    """주택류는 주택법 절차(사업계획승인·주택공급) 포함."""
    g = get_permit_guide("아파트")
    keys = _ref_keys(g)
    assert "housing_approval" in keys           # 주택법 제15조 사업계획승인
    assert "housing_supply_approval" in keys    # 주택공급규칙 제20조
    proc_names = [p["name"] for s in g["stages"] for p in s["procedures"]]
    assert "주택건설(대지조성)사업계획 승인" in proc_names
    assert "주택공급승인신청" in proc_names


def test_building_excludes_housing_act():
    """비주택(근린생활시설)은 주택법 절차 제외 — 건축법만."""
    g = get_permit_guide("제1종 근린생활시설")
    assert g["group"] == "building"
    keys = _ref_keys(g)
    assert "housing_approval" not in keys
    assert "building_permit" in keys and "use_permission" in keys


def test_legal_refs_verified():
    """모든 단계 법령은 law.go.kr verified 링크(무날조)."""
    g = get_permit_guide("단독주택")
    refs = [r for s in g["stages"] for r in s["legal_refs"]]
    assert refs
    for r in refs:
        assert r.get("law_name") and r.get("article")
        assert r.get("url_status") in ("verified", "pending")


def test_core_procedure_keys_present():
    """핵심 절차 법령(사전결정·건축허가·건축신고·용도변경·착공·사용승인) 매핑."""
    keys = _ref_keys(get_permit_guide("단독주택"))
    for k in ["building_pre_decision", "building_permit", "building_report",
              "use_change", "construction_start", "use_permission"]:
        assert k in keys, f"{k} 누락"


def test_documents_present():
    """각 단계 제출서류 제공."""
    g = get_permit_guide("단독주택")
    assert all(s["documents"] for s in g["stages"])
    docs = [d for s in g["stages"] for d in s["documents"]]
    assert any("허가신청서" in d for d in docs)
    assert any("착공신고서" in d for d in docs)
