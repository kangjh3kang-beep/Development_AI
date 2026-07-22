"""발행 게이트(publish_gate, W1-C · v4.0 P12) 테스트 — claim 분류 + 미승인 확정표현 차단
+ 가정의 사실화 차단.

검증 축:
 (a) claim_type 스키마 — Evidence/NarrativeBlock 5종 허용 + None 허용 + 불법값 조기거부.
 (b) 게이트①: APPROVED 라벨인데 approved_by 없음 → 위반. approved_by 있으면 통과.
 (c) 게이트②: 결정론 금지어('확정'·'보장'·'완벽')가 APPROVED 미만에서 확정 표현으로 쓰이면 위반.
     정직 부정 문맥('미확정'·'~아닙니다'·'~않습니다')은 위반 아님(오탐 방지).
 (d) 게이트③: claim_type=ASSUMPTION Evidence 가 '확정' 계열 문구와 결합되면 위반.
 (e) ★무회귀 회귀방지 핵심: 실제 프로덕션 어댑터(land_adapter/appraisal_adapter)가 만드는
     ReportModel 은 기존에도 '확정'/'보장' 단어를 정직한 문맥(표 상태라벨·위임형 서술)으로
     써왔다 — 이 스파이크에서 실측 발견한 패턴이며, 게이트가 이들을 위반으로 오판하면 기존
     보고서 생성이 깨진다(무회귀 위반). 이 두 어댑터의 실제 산출물이 위반 0건임을 고정한다.
 (f) render_report 진입부 배선 — 위반 있으면 ReportPublishGateError, 없으면(기존 DRAFT 모델)
     기존과 동일하게 통과(reportlab 미설치 환경은 스킵 관례 유지).
"""
from __future__ import annotations

import pytest

from app.services.report.render import (
    build_report_model_from_appraisal_multi,
    build_report_model_from_cost_estimation,
    build_report_model_from_design_audit,
    build_report_model_from_land,
    render_report,
)
from app.services.report.render.model import (
    Evidence,
    EvidenceBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
)
from app.services.report.render.publish_gate import (
    GateResult,
    ReportPublishGateError,
    check_publishable,
)


def _model(*, blocks=None, approval_state: str = "DRAFT", approved_by: str | None = None) -> ReportModel:
    return ReportModel(
        meta=ReportMeta(title="테스트 보고서", approval_state=approval_state, approved_by=approved_by),
        sections=[Section(title="본문", blocks=blocks or [])],
    )


# ── (a) claim_type 스키마 ────────────────────────────────────────────


@pytest.mark.parametrize("claim_type", ["FACT", "CALCULATION", "ASSUMPTION", "INTERPRETATION", "RECOMMENDATION", None])
def test_evidence_accepts_valid_claim_types_and_none(claim_type):
    ev = Evidence(value="용적률 250%", claim_type=claim_type)
    assert ev.claim_type == claim_type


def test_evidence_rejects_illegal_claim_type():
    with pytest.raises(ValueError):
        Evidence(value="용적률 250%", claim_type="NOT_A_REAL_CLAIM_TYPE")


@pytest.mark.parametrize("claim_type", ["FACT", "ASSUMPTION", None])
def test_narrative_block_accepts_valid_claim_types_and_none(claim_type):
    nb = NarrativeBlock(paragraphs=["결론입니다."], claim_type=claim_type)
    assert nb.claim_type == claim_type


def test_narrative_block_rejects_illegal_claim_type():
    with pytest.raises(ValueError):
        NarrativeBlock(paragraphs=["결론입니다."], claim_type="BOGUS")


# ── (b) 게이트① APPROVED 라벨 사칭 차단 ──────────────────────────────


def test_approved_without_approver_is_violation():
    model = _model(approval_state="APPROVED")
    result = check_publishable(model)
    assert not result.ok
    assert any(v.code == "APPROVED_WITHOUT_APPROVER" for v in result.violations)


def test_approved_with_approver_passes():
    model = _model(approval_state="APPROVED", approved_by="reviewer@propai.io")
    result = check_publishable(model)
    assert result.ok


@pytest.mark.parametrize("approval_state", ["DRAFT", "MACHINE_VALIDATED", "EXPERT_REVIEWED"])
def test_non_approved_states_never_require_approver(approval_state):
    """APPROVED 미만 상태는 approved_by 미기입이어도 규칙①에 걸리지 않는다(무회귀)."""
    model = _model(approval_state=approval_state)
    result = check_publishable(model)
    assert not any(v.code == "APPROVED_WITHOUT_APPROVER" for v in result.violations)


# ── (c) 게이트② 결정론 금지어 + 오탐 방지 ─────────────────────────────


def test_forbidden_word_without_hedge_is_violation_below_approved():
    model = _model(blocks=[NarrativeBlock(paragraphs=["본 사업성 분석 결과는 확정된 것입니다."])])
    result = check_publishable(model)
    assert not result.ok
    assert any(v.code == "FORBIDDEN_WORD" for v in result.violations)


@pytest.mark.parametrize("text", [
    "본 분석은 아직 확정이 아닙니다.",
    "인허가 결과는 미확정 상태입니다.",
    "심의 결과를 보장하지 않습니다.",
    "이 수치는 완벽하지 않으며 참고용입니다.",
])
def test_honest_negation_context_is_not_a_violation(text):
    """spec 예시(확정 아님/미확정/확정 필요류) — 정직한 부정 문구는 위반이 아니다."""
    model = _model(blocks=[NarrativeBlock(paragraphs=[text])])
    result = check_publishable(model)
    assert result.ok, result.violations


def test_forbidden_word_gate_does_not_apply_once_approved():
    """APPROVED 등급(+approved_by)이면 결정론 금지어 게이트 대상이 아니다(인간 승인 완료)."""
    model = _model(
        blocks=[NarrativeBlock(paragraphs=["본 사업성은 확정되었습니다."])],
        approval_state="APPROVED", approved_by="reviewer@propai.io",
    )
    result = check_publishable(model)
    assert result.ok


def test_forbidden_word_gate_does_not_apply_to_superseded():
    """SUPERSEDED 는 사슬상 APPROVED 다음 단계(폐기)이지 'APPROVED 미만'이 아니므로 스펙 문언
    그대로 이 규칙 대상이 아니다 — 표지 워터마크가 '폐기' 경고를 이미 눈에 띄게 표시한다."""
    model = _model(
        blocks=[NarrativeBlock(paragraphs=["본 사업성은 확정되었습니다."])],
        approval_state="SUPERSEDED",
    )
    result = check_publishable(model)
    assert not any(v.code == "FORBIDDEN_WORD" for v in result.violations)


# ── (d) 게이트③ ASSUMPTION + 확정 결합 차단 ──────────────────────────


def test_assumption_combined_with_forbidden_word_is_violation():
    model = _model(blocks=[EvidenceBlock(items=[
        Evidence(value="분양가 5억원 확정", claim_type="ASSUMPTION"),
    ])])
    result = check_publishable(model)
    assert not result.ok
    assert any(v.code == "ASSUMPTION_STATED_AS_FACT" for v in result.violations)


def test_assumption_with_honest_hedge_is_not_a_violation():
    model = _model(blocks=[EvidenceBlock(items=[
        Evidence(value="분양가 5억원(미확정 가정치)", claim_type="ASSUMPTION"),
    ])])
    result = check_publishable(model)
    assert not any(v.code == "ASSUMPTION_STATED_AS_FACT" for v in result.violations)


def test_non_assumption_evidence_with_forbidden_word_only_hits_rule2():
    """claim_type=FACT(또는 None)인 Evidence 는 규칙③ 대상이 아니다(규칙②만 적용될 수 있음)."""
    model = _model(blocks=[EvidenceBlock(items=[
        Evidence(value="용적률 250% 확정", claim_type="FACT"),
    ])])
    result = check_publishable(model)
    assert not any(v.code == "ASSUMPTION_STATED_AS_FACT" for v in result.violations)
    assert any(v.code == "FORBIDDEN_WORD" for v in result.violations)


# ── (e) ★무회귀 — 실제 어댑터 산출물은 위반 0건(스파이크 실측 회귀방지 고정) ──


def test_land_adapter_real_output_has_zero_gate_violations():
    """land_adapter 는 필지 상태를 표 셀에 '확정'/'보완필요'로, 종합의견에 '…검토로 확정되며'로
    표기해왔다(실측) — 게이트가 이를 오탐하면 기존 토지분석보고서 생성이 깨진다."""
    data = {
        "project_name": "테스트 토지분석",
        "parcels": [
            {"jibun": "용인시 1-1", "area_sqm": 500, "zone_type": "제2종일반주거지역",
             "bcr_pct": 60, "far_pct": 200, "jimok": "대", "official_price_per_sqm": 1_000_000,
             "parcel_case": "land", "status": "ok"},
            {"jibun": "용인시 1-2", "area_sqm": 300, "zone_type": "제2종일반주거지역",
             "bcr_pct": 60, "far_pct": 200, "jimok": "대", "official_price_per_sqm": None,
             "parcel_case": "land", "status": "needs_fix"},
        ],
    }
    model = build_report_model_from_land(data)
    result = check_publishable(model)
    assert isinstance(result, GateResult)
    assert result.ok, result.violations


def test_appraisal_multi_adapter_real_output_has_zero_gate_violations():
    """appraisal_adapter 다필지 총괄 표/캡션/서술도 '확정' 표현을 정직한 문맥으로 써왔다(실측)."""
    pairs = [
        ({"ok": True, "appraised_price_per_sqm": 1_000_000, "appraised_total_won": 500_000_000,
          "area_sqm": 500, "confidence": 0.8,
          "methods": [{"method": "공시지가 기준 추정", "unit_price": 1_000_000, "rationale": "산식"}],
          "disclaimer": "참고용"}, "주소1"),
        ({"ok": False, "message": "공시지가 미확인"}, "주소2"),
    ]
    model = build_report_model_from_appraisal_multi(pairs, addresses=["주소1", "주소2"])
    result = check_publishable(model)
    assert result.ok, result.violations


def test_design_audit_adapter_real_output_has_zero_gate_violations():
    """design_audit_adapter 는 "확정이 아닙니다"(격식체 부정)와 면책문 "보장하지 않습니다"를
    실제로 쓴다 — 격식체 '아닙니다'는 한글 음절합성으로 '아니'를 문자열로 포함하지 않는
    함정이 있었다(스파이크에서 발견·수정). 이 어댑터 실산출물로 회귀를 고정한다."""
    data = {
        "id": 1, "project_id": "p1", "created_at": "2026-07-22",
        "overall": {"grade": "normal"},
        "findings": [],
        "blindspot": {"items": [{"claim": "테스트 쟁점", "basis": "테스트 근거", "confidence": "med"}],
                      "summary": "요약문"},
    }
    model = build_report_model_from_design_audit(data)
    result = check_publishable(model)
    assert result.ok, result.violations


def test_cost_estimation_adapter_real_output_has_zero_gate_violations():
    """cost_estimation_adapter 면책문 "확정 공사비가 아니며"도 정직 부정 문맥으로 통과해야 한다."""
    data = {
        "project_name": "테스트 적산",
        "overview": {"total_won": 100_000_000_000, "unit_cost_per_sqm": 3_000_000, "items": []},
    }
    model = build_report_model_from_cost_estimation(data)
    result = check_publishable(model)
    assert result.ok, result.violations


# ── (f) render_report 진입부 배선 ────────────────────────────────────


def test_render_report_raises_on_gate_violation():
    model = _model(blocks=[NarrativeBlock(paragraphs=["본 사업성 분석 결과는 확정된 것입니다."])])
    with pytest.raises(ReportPublishGateError) as exc_info:
        render_report(model, "pdf")
    assert "FORBIDDEN_WORD" in str(exc_info.value)


def test_render_report_raises_on_approved_without_approver_before_touching_renderer():
    """approved_by 누락은 reportlab 유무와 무관하게 렌더러 진입 전에 걸러진다."""
    model = _model(approval_state="APPROVED")
    with pytest.raises(ReportPublishGateError) as exc_info:
        render_report(model, "pdf")
    assert "APPROVED_WITHOUT_APPROVER" in str(exc_info.value)


def test_render_report_default_draft_model_passes_gate_and_reaches_renderer():
    """★무회귀: 위반 없는 기본 DRAFT 모델은 게이트를 통과해 렌더러까지 도달한다(reportlab
    미설치 로컬 venv 는 그 다음 단계에서 스킵 — 기존 관례와 동일, 게이트 자체는 항상 실행 가능)."""
    pytest.importorskip("reportlab")
    model = _model(blocks=[NarrativeBlock(paragraphs=["정상적인 결론 문단입니다."])])
    data, mime, ext = render_report(model, "pdf")
    assert ext == "pdf" and mime == "application/pdf"
    assert data[:4] == b"%PDF"
