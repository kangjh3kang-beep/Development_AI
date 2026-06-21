"""INC-DL2 — 건축설계 라이프사이클: 6단계 스펙·완결성 표면화·법규여유 재사용·결정론."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.design.design_executor import run_design_process
from app.services.design.design_spec_loader import load_design_spec
from app.services.pipeline.analysis_pipeline import run_analysis

_IN = AnalysisInput(
    pnu="1111010100100000030", application_date=date(2026, 1, 1),
    rules=[{"rule": {"rule_id": "far_limit", "target_variable": "far_floor_area",
                     "basis_article": "국토계획법 시행령"}, "measured": 250.0, "limit": 200.0}],
    calc_targets=[{"target": "building_area", "payload": {"outer_area": 500.0},
                   "elements": [{"semantic_type": "EXT_WALL", "confidence": 0.9}]}],
)


def test_design_spec_has_six_stages_in_order():
    spec = load_design_spec()
    assert spec.spec_id == "design-default"
    ids = [s.stage_id for s in spec.stages]
    assert ids == ["programming", "legal_precheck", "massing", "site_layout",
                   "floor_plan", "deliverable_verify"]


def test_incomplete_inputs_surface_needs_input_not_silent():
    # provided 없음 → 산출물 미보유 단계(기획·매스·배치·평면)는 NEEDS_INPUT(완결성 결손 표면화, 무음 금지)
    result = run_analysis(_IN)
    out = run_design_process(result, use_zone="제2종일반주거지역", provided={})
    assert out.spec_id == "design-default"
    by_id = {s.stage_id: s for s in out.stages}
    assert by_id["programming"].status == "NEEDS_INPUT"   # program 결손
    assert by_id["programming"].issues                      # 사유 표면화
    # legal_precheck는 required=use_zone만 → 진행되어 법규여유 계측(시스템1 measure 재사용)
    assert by_id["legal_precheck"].status == "DONE"


def test_provided_artifacts_advance_stages():
    # 산출물 제공 시 해당 단계 진행(완결성 충족)
    result = run_analysis(_IN)
    out = run_design_process(
        result, use_zone="제2종일반주거지역",
        provided={"program": True, "massing": True, "site_layout": True, "floor_plan": True},
    )
    by_id = {s.stage_id: s for s in out.stages}
    assert by_id["programming"].status == "DONE"
    assert by_id["massing"].status == "DONE"
    assert by_id["floor_plan"].status == "DONE"


def test_design_process_is_deterministic():
    result = run_analysis(_IN)
    a = run_design_process(result, use_zone="제2종일반주거지역", provided={"program": True})
    b = run_design_process(result, use_zone="제2종일반주거지역", provided={"program": True})
    assert a.model_dump() == b.model_dump()
