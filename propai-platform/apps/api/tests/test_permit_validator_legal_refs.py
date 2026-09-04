"""permit_validator 허용용도 판정의 법령 근거(legal_ref_keys) 배선 검증.

허용용도 매트릭스(ZONE_PERMIT_MATRIX)는 국토계획법 §76(용도지역에서의 건축물 제한)이 근거다.
과거 판정 응답에는 근거 키가 0개(무근거 휴리스틱)였다 → registry 실재 키(zone_use)를 부착했다.
★무날조: 부착한 키는 legal_reference_registry에 실재해야 한다(레지스트리 미등재 조문은 키 미부여).
"""

from app.services.feasibility.permit_validator import (
    ZONE_PERMIT_LEGAL_REF_KEYS,
    check_permit_feasibility,
)
from app.services.legal.legal_reference_registry import LEGAL_REFERENCES


def test_permit_feasibility_response_carries_legal_ref_keys():
    """check_permit_feasibility 응답에 legal_ref_keys가 additive로 동봉된다."""
    r = check_permit_feasibility("M10", "제1종전용주거지역")
    assert r["legal_ref_keys"] == ZONE_PERMIT_LEGAL_REF_KEYS
    assert "zone_use" in r["legal_ref_keys"]


def test_legal_ref_keys_exist_in_registry():
    """부착 키는 전부 legal_reference_registry에 실재(무날조 — 딥링크 깨짐 방지)."""
    for key in ZONE_PERMIT_LEGAL_REF_KEYS:
        assert key in LEGAL_REFERENCES, f"legal_ref_key '{key}'가 레지스트리에 없음(날조 금지)"


def test_zone_use_points_to_kookto_76():
    """zone_use 키가 국토계획법 제76조(용도지역에서의 건축물 제한)를 가리킨다."""
    ref = LEGAL_REFERENCES["zone_use"]
    assert "76" in ref.get("article", "")
    assert "국토" in ref.get("law_name", "")
