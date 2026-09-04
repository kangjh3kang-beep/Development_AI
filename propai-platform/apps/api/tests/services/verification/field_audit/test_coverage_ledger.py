"""커버리지 원장 구조 테스트 — 분모 = 토지속성조합 × 결정변수(계획 §12.1 교정2·§12.6).

W0는 커버리지 %가 낮아도(0이라도) **구조**를 옳게 박제한다: 1차축=토지속성 조합, 2차축=사업유형,
조건부 트리(산지구분은 지목=임야일 때만), 결정변수 축. bare "100%" 금지의 자리를 만든다.
"""

from app.services.verification.field_audit.contracts import AuditReport

from . import strata


def test_coverage_field_exists_even_when_empty():
    """AuditReport.coverage는 빈 dict라도 필드가 존재해야 한다(원장 seed)."""
    rep = AuditReport()
    d = rep.to_dict()
    assert "coverage" in d
    assert isinstance(d["coverage"], dict)


def test_denominator_shape_has_both_axes():
    """분모 구조 = 토지속성조합(1차) × 결정변수. 양 축 존재·카디널리티>0."""
    shape = strata.coverage_denominator_shape()
    assert shape["primary_axis"] == "landattr_combination"   # 1차축 = 토지속성 조합
    assert shape["secondary_axis"] == "biz_model"            # 2차축 = 사업유형
    assert shape["denominator_kind"] == "landattr_combination x decision_var"

    axes = shape["landattr_axes"]
    # 지목 × 용도지역 × 산지구분 축 존재(§12.6 1차 층화축)
    for ax in ("jimok", "zone", "sanji_gubun", "nongji_gubun"):
        assert ax in axes and len(axes[ax]) > 0

    # 결정변수 축 존재(고위험 변수 flip 타깃)
    assert len(shape["decision_vars"]) > 0
    assert "개발가부" in shape["decision_vars"]
    assert "실효FAR" in shape["decision_vars"]


def test_conditional_tree_gates_subdimensions():
    """조건부 트리(§12.6 스키마1): 산지구분은 지목=임야일 때만·농지구분은 전/답일 때만 유효.

    무의미 조합('대 × 보전산지')을 분모에서 배제해 조합폭발을 통제한다.
    """
    # 산지구분: 임야에서만 유효
    assert strata.is_dimension_applicable("sanji_gubun", "임야") is True
    assert strata.is_dimension_applicable("sanji_gubun", "대") is False
    # 농지구분: 전/답에서만 유효
    assert strata.is_dimension_applicable("nongji_gubun", "전") is True
    assert strata.is_dimension_applicable("nongji_gubun", "임야") is False
    # 비조건부 차원(용도지역)은 항상 유효
    assert strata.is_dimension_applicable("zone", "대") is True


def test_biz_model_secondary_axis_seeded():
    """2차 층화축(사업유형) seed 존재 — 재건축·재개발 등(placeholder scaffold의 라벨원)."""
    assert "재건축" in strata.BIZ_MODELS
    assert "재개발" in strata.BIZ_MODELS


def test_effective_envelope_min_binding_dimension_present():
    """overlay 스택 binding=min 원리(§12.6 스키마3)의 자리 — 산지구분에 '보전산지' 값이
    존재해 '실효 ≤ min(적용 overlay)' 불변식(과대표시 회귀골든)을 W1이 얹을 수 있다.
    """
    assert any(v and "보전산지" in v for v in strata.SANJI_GUBUN if v)
