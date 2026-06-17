"""법정 산정 — CalcTrace 제외 정량 근거(임계·실측·차감량·description) 전파(설명가능성)."""
from app.contracts.legal_quantity import CalcElement
from app.contracts.semantic_element import SemanticType
from app.services.legal_calc.area_calculator import AreaCalculator
from app.services.legal_calc.calc_params import CalcParamSource
from app.services.legal_calc.height_floor_calc import HeightFloorCalc


def test_balcony_exclusion_quantified():
    calc = AreaCalculator(CalcParamSource())
    # 발코니 깊이 1.2m ≤ 기준 1.5m → 제외. trace에 임계·실측·차감·근거조문 동반.
    els = [CalcElement(semantic_type=SemanticType.BALCONY, area=10.0, depth=1.2)]
    value, entries = calc.building_area(100.0, els)
    assert value == 90.0
    bal = next(e for e in entries if e.rule_id == "ba_balcony")
    assert bal.threshold == 1.5 and bal.threshold_unit == "m"
    assert bal.measured == 1.2 and bal.excluded_amount == 10.0
    assert "1.2m ≤ 기준 1.5m" in bal.note and bal.basis_article == "건축법 시행령 제119조"


def test_far_exclusion_amount():
    calc = AreaCalculator(CalcParamSource())
    els = [CalcElement(semantic_type=SemanticType.BASEMENT, area=30.0)]
    value, entries = calc.far_floor_area(200.0, els)
    assert value == 170.0
    base = next(e for e in entries if "basement" in e.rule_id)
    assert base.excluded_amount == 30.0


def test_rooftop_ratio_quantified():
    calc = HeightFloorCalc(CalcParamSource())
    # 옥탑 면적비 0.1 ≤ 기준 0.125 → 제외. 실측 비율 동반.
    _, entries = calc.building_height(30.0, rooftop_area=10.0, building_area=100.0)
    rt = next(e for e in entries if e.rule_id == "height_rooftop_excluded")
    assert rt.threshold == 0.125 and rt.measured == 0.1 and "0.1" in rt.note


def test_param_meta_carries_basis():
    p = CalcParamSource()
    m = p.meta("balcony_exclusion_depth")
    assert m["value"] == 1.5 and m["basis_article"] == "건축법 시행령 제119조" and m["description"]
