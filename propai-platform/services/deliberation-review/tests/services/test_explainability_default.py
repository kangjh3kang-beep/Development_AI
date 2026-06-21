"""EX1 — 설명가능성 기본화: 결과물에 근거(LegalRef)+링크(source URL) 기본 동반 + enforcement.

표준([[explainability-by-default]]): 값 보유 결과는 근거 동반(무음 금지), 근거조문은 해소가능 링크 동반.
"""
from datetime import date
from types import SimpleNamespace

from app.contracts.legal_quantity import LegalQuantity
from app.contracts.permit_process import CriterionKind, CriterionRef
from app.contracts.analysis import AnalysisInput
from app.services.permit.measurement import _legal_basis, measure_quantitative
from app.services.permit.executor import run_process
from app.services.permit.spec_loader import load_default_spec
from app.services.design.design_executor import run_design_process
from app.services.pipeline.analysis_pipeline import run_analysis

_ZONE = "제2종일반주거지역"


def test_legal_basis_resolves_to_ref_with_source_link():
    # 근거조문 → LegalRef(법령명·조항·요지·1차출처 링크)
    refs = _legal_basis("국토계획법 시행령")
    assert refs and refs[0].law and refs[0].source
    assert refs[0].source.startswith("https://")          # 해소가능 링크
    assert _legal_basis("건축법")[0].source.startswith("https://")
    assert _legal_basis("미등록법령xyz") == []             # 미해소→[](식별자만, 날조 금지)


def test_quantitative_criterion_carries_basis_and_link():
    res = SimpleNamespace(legal_quantities=[LegalQuantity(variable_id="building_area", value=500.0),
                                            LegalQuantity(variable_id="plot_area", value=1000.0)],
                          qualitative=[])
    ref = CriterionRef(criterion_id="bcr", kind=CriterionKind.QUANTITATIVE, ssot_ref="building_area",
                       basis_article="국토계획법 시행령")
    cr = measure_quantitative(res, ref, _ZONE)
    assert cr.calc_trace is not None                       # 도출근거(measured/limit/source)
    assert cr.legal_basis and cr.legal_basis[0].source.startswith("https://")   # 법령 근거+링크


def test_explicit_legal_ref_ids_wire_specific_articles():
    # orphan §77 배선 + 정밀 다중 근거 — bcr 기준에 국토계획법§77·시행령§84 명시 연결
    res = SimpleNamespace(legal_quantities=[LegalQuantity(variable_id="building_area", value=500.0),
                                            LegalQuantity(variable_id="plot_area", value=1000.0)],
                          qualitative=[])
    ref = CriterionRef(criterion_id="bcr", kind=CriterionKind.QUANTITATIVE, ssot_ref="building_area",
                       basis_article="국토계획법 시행령",
                       legal_ref_ids=["국토계획법§77", "국토계획법시행령§84"])
    cr = measure_quantitative(res, ref, _ZONE)
    ids = {r.ref_id for r in cr.legal_basis}
    assert "국토계획법§77" in ids and "국토계획법시행령§84" in ids   # 정밀 조문 근거 동반(§77 orphan 배선)
    assert all(r.source for r in cr.legal_basis)                    # 모두 1차출처 링크 동반


def test_default_specs_wire_far_bcr_articles():
    # 기본 스펙(permit·design)의 far/bcr 기준에 §77/§78·시행령§84/§85가 연결됐는지(orphan 해소)
    from app.services.design.design_spec_loader import load_design_spec
    from app.services.permit.spec_loader import load_default_spec
    for spec in (load_default_spec(), load_design_spec()):
        refs = {c.criterion_id: c.legal_ref_ids
                for s in spec.stages for c in s.criteria_refs}
        assert "국토계획법§77" in refs.get("bcr", [])
        assert "국토계획법§78" in refs.get("far", [])


def _enforce_basis_links(out):
    # enforcement: basis_article 있는 모든 기준은 legal_basis(근거+링크) 동반(무음 금지)
    for s in out.stages:
        for c in s.criteria:
            if c.basis_article and resolve_ok(c.basis_article):
                assert c.legal_basis, f"{s.stage_id}/{c.criterion_id}: 근거조문에 legal_basis 누락"
                assert any(r.source for r in c.legal_basis), "근거에 출처/링크 누락"


def resolve_ok(article: str) -> bool:
    from app.services.explain.legal_refs import resolve_text
    return resolve_text(article) is not None


def test_permit_and_design_results_carry_basis_links_by_default():
    inp = AnalysisInput(
        pnu="1111010100100000040", application_date=date(2026, 1, 1),
        rules=[{"rule": {"rule_id": "far_limit", "target_variable": "far_floor_area",
                         "basis_article": "국토계획법 시행령"}, "measured": 250.0, "limit": 200.0}],
        calc_targets=[{"target": "building_area", "payload": {"outer_area": 500.0},
                       "elements": [{"semantic_type": "EXT_WALL", "confidence": 0.9}]}],
    )
    result = run_analysis(inp)
    _enforce_basis_links(run_process(result, load_default_spec(), use_zone=_ZONE))
    _enforce_basis_links(run_design_process(result, use_zone=_ZONE, provided={"program": True}))
