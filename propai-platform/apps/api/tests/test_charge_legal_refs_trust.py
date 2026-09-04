"""부담금 근거 프론트 노출 회귀가드 — 세금엔진 코드→레지스트리 키 매핑(PR#247 근거 노출).

_applied_taxes가 부과된 부담금(B01·B02·B03·B04·C07)에 레지스트리 ref_key를 부여해,
_build_cost_trust_blocks의 legal_refs[]·evidence.legal_ref_key로 프론트(LegalRefChip·EvidencePanel)에
근거+링크가 노출되게 한다. v2_feasibility(fastapi) 임포트 → CI(py3.12)에서 실행.
"""
from app.routers.v2_feasibility import _TAX_CODE_TO_REF_KEY, _applied_taxes


def test_charge_codes_mapped_to_registry_keys():
    """부담금 5종 코드가 PR#247 레지스트리 키로 매핑."""
    assert _TAX_CODE_TO_REF_KEY["B01"] == "metro_transport_charge"
    assert _TAX_CODE_TO_REF_KEY["B02"] == "school_land_special"
    assert _TAX_CODE_TO_REF_KEY["B03"] == "water_supply_cause_charge"
    assert _TAX_CODE_TO_REF_KEY["B04"] == "sewage_cause_charge"
    assert _TAX_CODE_TO_REF_KEY["C07"] == "infra_facility_charge"


def test_applied_taxes_assigns_charge_ref_keys():
    """부과된 부담금에 ref_key 부여 — 레지스트리 미보유(B05)는 None(링크 없이 텍스트만)."""
    tax_detail = {
        "construction": {"items": [
            {"code": "B02", "name": "학교용지부담금", "amount_won": 2_000_000_000},
            {"code": "B05", "name": "전기인입부담금", "amount_won": 50_000_000},
        ]},
        "sale": {"items": [
            {"code": "C07", "name": "기반시설부담금", "amount_won": 1_000_000_000},
        ]},
    }
    out = {t["code"]: t for t in _applied_taxes(tax_detail)}
    assert out["B02"]["ref_key"] == "school_land_special"
    assert out["C07"]["ref_key"] == "infra_facility_charge"
    assert out["B05"]["ref_key"] is None


def test_zero_amount_charge_excluded():
    """amount_won=0(예: 표준건축비 미주입 B01) → 노출 제외(부과분만 근거 표기)."""
    tax_detail = {"construction": {"items": [
        {"code": "B01", "name": "광역교통시설부담금", "amount_won": 0},
    ]}}
    assert _applied_taxes(tax_detail) == []
