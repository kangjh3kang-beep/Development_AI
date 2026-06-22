"""INC-PD2(보정) — 심의 계측 단위정합·등급밴드: conformance 값 직접 검증(이전 누락 근본원인).

게이트가 잡은 2버그 회귀 방지: (1) 절대면적(m²) vs 한도(%) 직접비교 → 대지면적 대비 비율로 환산.
(2) 정성 등급 truthiness('LOW'도 부합) → 등급별 부합도 밴드.
"""
from types import SimpleNamespace

from app.contracts.legal_quantity import LegalQuantity
from app.contracts.permit_process import CriterionKind, CriterionRef
from app.contracts.qualitative import QualAssessment, QualGrade, RubricCitation
from app.services.permit.measurement import measure_qualitative, measure_quantitative

_ZONE = "제2종일반주거지역"   # bcr 60% / far 250% (national_zone_limits.json)
_REF_BCR = CriterionRef(criterion_id="bcr", kind=CriterionKind.QUANTITATIVE, ssot_ref="building_area")


def _res(lqs, quals=()):
    return SimpleNamespace(legal_quantities=list(lqs), qualitative=list(quals))


def test_bcr_uses_ratio_not_absolute_area():
    # 건폐율 = building_area/plot_area*100. 500/1000*100=50% <= 60% → 부합(절대면적 비교 버그 회귀 방지)
    res = _res([LegalQuantity(variable_id="building_area", value=500.0),
                LegalQuantity(variable_id="plot_area", value=1000.0)])
    cr = measure_quantitative(res, _REF_BCR, _ZONE)
    assert cr.conformance == "부합"
    assert cr.calc_trace["computed_pct"] == 50.0
    assert cr.limit == 60.0


def test_bcr_over_limit_is_noncompliant():
    # 700/1000*100=70% > 60% → 미흡
    res = _res([LegalQuantity(variable_id="building_area", value=700.0),
                LegalQuantity(variable_id="plot_area", value=1000.0)])
    cr = measure_quantitative(res, _REF_BCR, _ZONE)
    assert cr.conformance == "미흡"


def test_quantitative_without_plot_area_is_held_not_fabricated():
    # plot_area 부재 → 비율 형성 불가 → HELD(무음 '미흡' 날조 금지)
    res = _res([LegalQuantity(variable_id="building_area", value=500.0)])
    cr = measure_quantitative(res, _REF_BCR, _ZONE)
    assert cr.conformance == "HELD"


def test_quantitative_negative_inputs_are_held_not_fabricated():
    # ★음수 면적/대지면적 → 비율 음수 → share<=limit 항상 참으로 '부합' 날조되던 버그 회귀 방지(HELD)
    neg_plot = _res([LegalQuantity(variable_id="building_area", value=500.0),
                     LegalQuantity(variable_id="plot_area", value=-1000.0)])
    neg_area = _res([LegalQuantity(variable_id="building_area", value=-500.0),
                     LegalQuantity(variable_id="plot_area", value=1000.0)])
    zero_plot = _res([LegalQuantity(variable_id="building_area", value=500.0),
                      LegalQuantity(variable_id="plot_area", value=0.0)])
    assert measure_quantitative(neg_plot, _REF_BCR, _ZONE).conformance == "HELD"
    assert measure_quantitative(neg_area, _REF_BCR, _ZONE).conformance == "HELD"
    assert measure_quantitative(zero_plot, _REF_BCR, _ZONE).conformance == "HELD"


def test_qualitative_grade_band_with_real_feature_token():
    # 실 qual_facts feature(한글)와 정합된 ssot_ref로 등급밴드 발화. LOW/NONE이 '부합' 침묵하던 버그 회귀 방지.
    ref = CriterionRef(criterion_id="layout", kind=CriterionKind.QUALITATIVE, ssot_ref="배치적정성")
    low = QualAssessment(item="배치적정성", grade=QualGrade.LOW,
                         citation=RubricCitation(rubric_item="배치", source="심의기준"))
    high = QualAssessment(item="배치적정성", grade=QualGrade.HIGH,
                          citation=RubricCitation(rubric_item="배치", source="심의기준"))
    none = QualAssessment(item="배치적정성", grade=QualGrade.NONE,
                          citation=RubricCitation(rubric_item="배치", source="심의기준"))
    assert measure_qualitative(_res([], [low]), ref).conformance == "미흡"
    assert measure_qualitative(_res([], [none]), ref).conformance == "미흡"
    assert measure_qualitative(_res([], [high]), ref).conformance == "부합"


def test_qualitative_unmatched_feature_is_held():
    # ssot_ref와 무관한 feature → 매칭 실패 → HELD(과대매칭 방지)
    ref = CriterionRef(criterion_id="layout", kind=CriterionKind.QUALITATIVE, ssot_ref="배치적정성")
    other = QualAssessment(item="경관조화", grade=QualGrade.HIGH,
                           citation=RubricCitation(rubric_item="경관", source="심의기준"))
    assert measure_qualitative(_res([], [other]), ref).conformance == "HELD"
