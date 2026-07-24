"""BuildingCodeRuleEngine(app/services/permit/building_code_rules.py) opt-in 재표현.

★소비 배선(opt-in, 이번 W3-7 범위 한정): 기존 ``BuildingCodeRuleEngine._check_bcr``/
``_check_far``는 그대로 유지한다(기본 경로 무회귀 — 실제 인허가 판정 API는 여전히
building_code_rules.py를 사용). 이 모듈은 그 로직을 RuleDef로 병행 재표현하고,
"같은 입력 → 같은 결과"를 이중 실행 대조 테스트(tests/test_rule_dsl_building_code_dual_exec.py)
로 증명하는 것만이 목적이다. 검증된 뒤 실제 판정 경로 교체는 별도 웨이브로 이월한다.

BL-005(주차대수) 등은 per_unit/per_sqm 선택 분기·법정 하한/권장 상한 이원화가 있어
이번 대표 승격 범위(1~3개) 밖으로 남긴다 — BL-001(건폐율)·BL-002(용적률) 2건만 재표현.
"""
from __future__ import annotations

from app.services.rules.contracts import (
    CanonicalVariable,
    Comparator,
    Unit,
    VariableRegistry,
    build_default_registry,
)
from app.services.rules.evaluate import evaluate
from app.services.rules.expr import BinOp, Const, VarRef
from app.services.rules.result import RuleResult
from app.services.rules.rule_def import RuleDef

BUILDING_CODE_REGISTRY: VariableRegistry = build_default_registry([
    CanonicalVariable(id="building_area_sqm", name="building_area_sqm", unit=Unit.M2, required=True),
    CanonicalVariable(id="total_gfa_sqm", name="total_gfa_sqm", unit=Unit.M2, required=True),
    CanonicalVariable(id="land_area_sqm", name="land_area_sqm", unit=Unit.M2, required=True),
    CanonicalVariable(id="max_bcr_pct", name="max_bcr_pct", unit=Unit.PERCENT, required=True),
    CanonicalVariable(id="max_far_pct", name="max_far_pct", unit=Unit.PERCENT, required=True),
    CanonicalVariable(id="bcr_pct", name="bcr_pct", unit=Unit.PERCENT, required=True),
    CanonicalVariable(id="far_pct", name="far_pct", unit=Unit.PERCENT, required=True),
])


def _ratio_pct_formula(numerator_var: str, denominator_var: str) -> BinOp:
    """(분자/분모)*100 — 건폐율·용적률 공용 산식 모양(building_code_rules.py와 동일 산식)."""
    return BinOp(
        op="mul",
        left=BinOp(op="div", left=VarRef(name=numerator_var), right=VarRef(name=denominator_var)),
        right=Const(value=100),
    )


# BL-001 — building_code_rules._check_bcr와 동일 산식(건축면적/대지면적×100, ≤ max_bcr).
BL_001_BCR = RuleDef(
    rule_id="BL-001",
    target_variable="bcr_pct",
    basis_article="국토의 계획 및 이용에 관한 법률 시행령 제84조(건축법 제55조 위임)",
    inputs=["building_area_sqm", "land_area_sqm", "max_bcr_pct"],
    formula=_ratio_pct_formula("building_area_sqm", "land_area_sqm"),
    limit=VarRef(name="max_bcr_pct"),
    comparator=Comparator.LE,
    unit=Unit.PERCENT,
)

# BL-002 — 기본 비교산식(연면적/대지면적×100, ≤ max_far)만 재표현한다.
# ★스테일 주석 교정(레인H R2, 2026-07-24 R1 리뷰): building_code_rules._check_far는
#   2026-07-24부터 구조상한(건폐율×층수, far_cap_with_structural_overlay) 오버레이를 흡수해
#   층수제한 zone(자연/생산/보전녹지 등)에서 max_far를 실효값으로 낮춘다 — 이 DSL 재표현은
#   그 오버레이를 아직 포함하지 않는다("동일 산식"이라는 과거 표현은 이제 부정확). 대조 테스트
#   (test_rule_dsl_building_code_dual_exec.py)는 site에 zone_type을 넣지 않는 입력만 쓰므로
#   현재는 발산 없이 통과하지만, zone_type이 있는 입력을 대조하면 발산한다. 구조상한 흡수는
#   evaluate 계약층(app/services/rules) 후속 스윕 대상으로 남긴다(이번 범위 밖).
BL_002_FAR = RuleDef(
    rule_id="BL-002",
    target_variable="far_pct",
    basis_article="국토의 계획 및 이용에 관한 법률 시행령 제85조(건축법 제56조 위임)",
    inputs=["total_gfa_sqm", "land_area_sqm", "max_far_pct"],
    formula=_ratio_pct_formula("total_gfa_sqm", "land_area_sqm"),
    limit=VarRef(name="max_far_pct"),
    comparator=Comparator.LE,
    unit=Unit.PERCENT,
)


def evaluate_bl001_bcr(design_params: dict, site_params: dict) -> RuleResult:
    """BuildingCodeRuleEngine._check_bcr와 동일 입력 형태(design_params/site_params)를 받는 어댑터."""
    inputs = {
        "building_area_sqm": design_params.get("building_area_sqm"),
        "land_area_sqm": site_params.get("land_area_sqm"),
        "max_bcr_pct": site_params.get("max_bcr"),
    }
    return evaluate(BL_001_BCR, inputs, BUILDING_CODE_REGISTRY)


def evaluate_bl002_far(design_params: dict, site_params: dict) -> RuleResult:
    """BuildingCodeRuleEngine._check_far와 동일 입력 형태(design_params/site_params)를 받는 어댑터.

    ★기본 비교산식만 재표현 — 구조상한(건폐율×층수) 오버레이는 미포함(위 BL_002_FAR 주석 참조,
    evaluate 계약층 후속 스윕 대상). zone_type이 있는 site_params를 넣으면 baseline
    (BuildingCodeRuleEngine._check_far)과 발산할 수 있다.
    """
    inputs = {
        "total_gfa_sqm": design_params.get("total_gfa_sqm"),
        "land_area_sqm": site_params.get("land_area_sqm"),
        "max_far_pct": site_params.get("max_far"),
    }
    return evaluate(BL_002_FAR, inputs, BUILDING_CODE_REGISTRY)


__all__ = [
    "BL_001_BCR",
    "BL_002_FAR",
    "BUILDING_CODE_REGISTRY",
    "evaluate_bl001_bcr",
    "evaluate_bl002_far",
]
