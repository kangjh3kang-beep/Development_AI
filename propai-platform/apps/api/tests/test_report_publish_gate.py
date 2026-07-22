"""발행 게이트(publish_gate, W1-C · v4.0 P12, R2=R1 리뷰 반영) 테스트.

R1 라이브 검증에서 순수 부분어 매칭이 "확정일자·확정판결·경계확정·재산권 보장(헌법 인용)·
완벽한 입지" 같은 정직 용례를 대량 오탐 차단(미검증 어댑터 보고서 500)한 사실이 드러났다.
이 테스트는 그 R2 이원화 설계(hard/soft)와 오탐 축소를 고정한다.

검증 축:
 (a) claim_type 스키마 — Evidence/NarrativeBlock 5종 허용 + None 허용 + 불법값 조기거부.
 (b) 게이트①: APPROVED 라벨인데 approved_by 없음 → 항상 hard(violations). approved_by 있으면 통과.
 (c) 게이트②③ 이원화: DRAFT/MACHINE_VALIDATED 는 결정론 금지어·ASSUMPTION 결합을 soft
     (warnings, 절대 차단 안 함) 로, EXPERT_REVIEWED 이상("승인 트랙")은 hard(violations, 차단)로.
 (d) ★R1 실측 오탐방지 7종 — 확정일자·확정판결·경계확정·재산권 보장(헌법 인용)·완벽한 입지·
     확정신고(동음이의/관용구) + 진짜 위반 1종을 대조군으로 — 오탐 5(6)종은 어느 승인등급에서도
     절대 걸리지 않고, 대조군은 등급에 따라 warnings/violations 로 정확히 분류됨을 고정한다.
 (e) ★무회귀 — 실제 프로덕션 어댑터 9종(land/appraisal_multi/design_audit/cost_estimation/
     market/regulation/bank/persona/feasibility-rough) 산출물은 hard 위반 0건(soft-gate 통과).
 (f) render_report 진입부 배선 — hard 위반은 ReportPublishGateError, soft(DRAFT) 는 렌더 진행.
 (g) apps.api.exceptions 전역 핸들러 — ReportPublishGateError → 409(REPORT_PUBLISH_GATE_VIOLATION).
 (h) JSON 우회 경로(rough_scenario_report._model_to_json) — 절대 차단 안 함, gate 필드 동봉.
"""
from __future__ import annotations

import pytest

from app.services.report.render import (
    build_report_model_from_appraisal_multi,
    build_report_model_from_bank,
    build_report_model_from_cost_estimation,
    build_report_model_from_design_audit,
    build_report_model_from_land,
    build_report_model_from_market,
    build_report_model_from_persona,
    build_report_model_from_regulation,
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


# ── (b) 게이트① APPROVED 라벨 사칭 차단 — 항상 hard ──────────────────


def test_approved_without_approver_is_hard_violation():
    model = _model(approval_state="APPROVED")
    result = check_publishable(model)
    assert not result.ok
    assert any(v.code == "APPROVED_WITHOUT_APPROVER" for v in result.violations)


def test_approved_with_approver_passes():
    model = _model(approval_state="APPROVED", approved_by="reviewer@propai.io")
    result = check_publishable(model)
    assert result.ok
    assert not result.violations and not result.warnings


@pytest.mark.parametrize("approval_state", ["DRAFT", "MACHINE_VALIDATED", "EXPERT_REVIEWED"])
def test_non_approved_states_never_require_approver(approval_state):
    """APPROVED 미만 상태는 approved_by 미기입이어도 규칙①에 걸리지 않는다(무회귀)."""
    model = _model(approval_state=approval_state)
    result = check_publishable(model)
    assert not any(v.code == "APPROVED_WITHOUT_APPROVER" for v in result.violations)


# ── (c) 게이트②③ 이원화(hard/soft) ───────────────────────────────────


@pytest.mark.parametrize("approval_state", ["DRAFT", "MACHINE_VALIDATED"])
def test_forbidden_word_is_soft_warning_below_expert_reviewed(approval_state):
    """★R1 이원화 핵심: DRAFT/MACHINE_VALIDATED 는 결정론 금지어가 있어도 절대 차단하지
    않는다(violations 비어있음=ok) — warnings 로만 수집."""
    model = _model(
        blocks=[NarrativeBlock(paragraphs=["본 사업성 분석 결과는 확정된 것입니다."])],
        approval_state=approval_state,
    )
    result = check_publishable(model)
    assert result.ok, "soft 등급에서 금지어는 절대 차단하면 안 된다(무회귀 위반)"
    assert any(v.code == "FORBIDDEN_WORD" for v in result.warnings)
    assert not any(v.code == "FORBIDDEN_WORD" for v in result.violations)


@pytest.mark.parametrize("approval_state", ["EXPERT_REVIEWED", "APPROVED", "SUPERSEDED"])
def test_forbidden_word_is_hard_violation_at_or_above_expert_reviewed(approval_state):
    """★R1 이원화 핵심: '승인 트랙'(EXPERT_REVIEWED 이상)에서는 같은 금지어가 hard 위반."""
    model = _model(
        blocks=[NarrativeBlock(paragraphs=["본 사업성 분석 결과는 확정된 것입니다."])],
        approval_state=approval_state,
        approved_by="reviewer@propai.io" if approval_state != "EXPERT_REVIEWED" else None,
    )
    result = check_publishable(model)
    assert not result.ok
    assert any(v.code == "FORBIDDEN_WORD" for v in result.violations)
    assert not any(v.code == "FORBIDDEN_WORD" for v in result.warnings)


@pytest.mark.parametrize("text", [
    "본 분석은 아직 확정이 아닙니다.",
    "인허가 결과는 미확정 상태입니다.",
    "심의 결과를 보장하지 않습니다.",
    "이 수치는 완벽하지 않으며 참고용입니다.",
])
def test_honest_negation_context_is_not_a_hit_at_any_tier(text):
    """정직한 부정 문구는 어느 등급에서도(soft/hard 무관) 전혀 검출되지 않는다."""
    for approval_state in ("DRAFT", "EXPERT_REVIEWED"):
        model = _model(blocks=[NarrativeBlock(paragraphs=[text])], approval_state=approval_state)
        result = check_publishable(model)
        assert result.ok, result.violations
        assert not result.warnings, result.warnings


def test_assumption_combined_with_forbidden_word_soft_at_draft_hard_at_expert_reviewed():
    ev_block = EvidenceBlock(items=[Evidence(value="분양가 5억원 확정입니다", claim_type="ASSUMPTION")])

    draft = _model(blocks=[ev_block])
    r_draft = check_publishable(draft)
    assert r_draft.ok
    assert any(v.code == "ASSUMPTION_STATED_AS_FACT" for v in r_draft.warnings)

    reviewed = _model(blocks=[ev_block], approval_state="EXPERT_REVIEWED")
    r_reviewed = check_publishable(reviewed)
    assert not r_reviewed.ok
    assert any(v.code == "ASSUMPTION_STATED_AS_FACT" for v in r_reviewed.violations)


def test_assumption_with_honest_hedge_is_never_a_hit():
    model = _model(blocks=[EvidenceBlock(items=[
        Evidence(value="분양가 5억원(미확정 가정치)", claim_type="ASSUMPTION"),
    ])])
    result = check_publishable(model)
    assert not result.warnings and not result.violations


def test_non_assumption_evidence_with_forbidden_word_only_hits_rule2_not_rule3():
    """claim_type=FACT(또는 None)인 Evidence 는 규칙③(ASSUMPTION 결합) 대상이 아니다."""
    model = _model(blocks=[EvidenceBlock(items=[
        Evidence(value="용적률 250% 확정입니다", claim_type="FACT"),
    ])])
    result = check_publishable(model)
    assert not any(v.code == "ASSUMPTION_STATED_AS_FACT" for v in result.warnings + result.violations)
    assert any(v.code == "FORBIDDEN_WORD" for v in result.warnings)


def test_legal_link_evidence_is_out_of_scope_even_with_forbidden_word():
    """검증된 법령 인용(legal_link 보유)은 스캔 대상에서 제외 — 원본 법령 사실이지 이 보고서의
    확정 주장이 아니다."""
    model = _model(blocks=[EvidenceBlock(items=[
        Evidence(value="재산권은 보장됩니다", legal_link="https://law.go.kr/법령/헌법"),
    ])])
    result = check_publishable(model)
    assert not result.warnings and not result.violations


# ── (d) ★R1 실측 오탐방지 7종 — 동음이의/관용구는 절대 걸리지 않음, 대조군은 정확히 분류 ──


_R1_HONEST_CASES = [
    "임대차 계약서에 확정일자를 받아 대항력을 확보했습니다.",
    "법원의 확정판결에 따라 소유권 이전이 완료되었습니다.",
    "인접 필지와의 경계확정 측량을 완료했습니다.",
    "헌법 제23조는 국민의 재산권 보장을 명시하고 있습니다.",
    "본 물건은 역세권의 완벽한 입지 조건을 갖추고 있습니다.",
    "종합소득세 확정신고 기한은 5월 말입니다.",
]


@pytest.mark.parametrize("text", _R1_HONEST_CASES)
@pytest.mark.parametrize("approval_state", ["DRAFT", "EXPERT_REVIEWED"])
def test_r1_honest_domain_terms_never_flagged_at_any_tier(text, approval_state):
    """R1 라이브 실증: 확정일자/확정판결/경계확정/재산권 보장/완벽한 입지/확정신고는
    동음이의·관용구이지 결정론적 확정 주장이 아니다 — soft/hard 어느 쪽으로도 검출되면 안 된다."""
    model = _model(blocks=[NarrativeBlock(paragraphs=[text])], approval_state=approval_state)
    result = check_publishable(model)
    assert result.ok, f"오탐 재발: {text!r} -> violations={result.violations}"
    assert not result.warnings, f"오탐 재발: {text!r} -> warnings={result.warnings}"


def test_r1_control_case_genuine_violation_is_still_caught():
    """대조군(7번째 케이스) — 진짜 확정 주장 문장은 화이트리스트로 안 걸리고 여전히 검출돼야
    한다(오탐 축소가 과잉 관대화로 이어지지 않았는지 확인)."""
    text = "본 사업성 분석 결과는 확정된 것입니다."
    draft = _model(blocks=[NarrativeBlock(paragraphs=[text])])
    r_draft = check_publishable(draft)
    assert r_draft.ok  # soft — 차단 안 함
    assert any(v.code == "FORBIDDEN_WORD" for v in r_draft.warnings)

    reviewed = _model(blocks=[NarrativeBlock(paragraphs=[text])], approval_state="EXPERT_REVIEWED")
    r_reviewed = check_publishable(reviewed)
    assert not r_reviewed.ok  # hard — 승인 트랙에서는 차단
    assert any(v.code == "FORBIDDEN_WORD" for v in r_reviewed.violations)


# ── (e) ★무회귀 — 실제 프로덕션 어댑터 9종 산출물은 hard 위반 0건(soft-gate 통과) ──


def test_land_adapter_real_output_passes_soft_gate_with_zero_hard_violations():
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


def test_appraisal_multi_adapter_real_output_passes_soft_gate():
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


def test_design_audit_adapter_real_output_passes_soft_gate():
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


def test_cost_estimation_adapter_real_output_passes_soft_gate():
    data = {
        "project_name": "테스트 적산",
        "overview": {"total_won": 100_000_000_000, "unit_cost_per_sqm": 3_000_000, "items": []},
    }
    model = build_report_model_from_cost_estimation(data)
    result = check_publishable(model)
    assert result.ok, result.violations


def _market_full_rep() -> dict:
    """market_report_service.build_report 산출 표본(test_market_report_adapter._full_rep 미러
    — 이 저장소에 apps/api/tests/ 와 별개인 최상위 tests/ 패키지가 동시에 존재해 bare
    'tests.X' 크로스 임포트가 sys.path 순서에 따라 엉뚱한 tests 패키지로 해석될 수 있다
    (한계·발견 — 새 모듈 X, 값만 로컬 인라인)."""
    return {
        "address": "서울 강남 역삼", "generated_at": "2026-07-17 09:00",
        "months": ["202605", "202606", "202607"], "coordinates": {"lat": 37.5, "lon": 127.0},
        "zone_type": "일반상업지역", "official_price_per_sqm": 25000000,
        "trade": {"아파트": {"count": 120, "per_pyeong": {"avg": 3200}}},
        "narrative": {
            "summary": "인라인 시장 요약", "opportunities": ["기회 1"], "risks": ["리스크 1"],
            "price_trend": "상승", "target_persona": "30대 실수요",
        },
        "senior_insight": {
            "market_overview": "전용 시장개요.", "price_trend_analysis": "가격추이 전용해석.",
            "comparable_analysis": "비교분석 전용해석.", "investment_insight": "투자 시사점.",
            "risk_factors": "리스크 정밀.", "timing_recommendation": "매수 적기.",
        },
        "feasibility_analysis": {
            "financials": {"roi_percent": 14.5, "total_cost_10k": 5000000,
                           "total_revenue_10k": 6200000, "net_profit_10k": 1200000, "npv_10k": 800000},
            "massing": {"land_area_sqm": 1000, "gfa_sqm": 2500, "gfa_pyeong": 756},
            "assumptions": {"note": "개략 가정"},
        },
        "pricing_band": {"data_source": "live", "fair_price_10k": 92000,
                         "affordability_verdict": "within_optimistic", "note": "적정 범위"},
        "unit_mix_recommendation": {"data_source": "live", "recommended_mix": {"59㎡": 40, "84㎡": 60},
                                    "rationale": "수요기반"},
        "target_profile": {
            "primary_age": {"band": "30-39", "value": "30대"},
            "primary_household": {"type": "1인 가구"},
            "income_tier": {"tier_label": "중상위 소득권(추정)"},
            "commercial": {"data_source": "live", "total_stores": 820, "grade": "B",
                          "vitality_score": 72, "category_distribution": [{"category": "음식", "count": 300}]},
            "location": {"nearest_subway": "역삼역", "subway_distance_m": 300, "school_count": 2},
            "premium": {"note": "신용평점·카드소비는 PREMIUM 제휴 예정"},
        },
        "raw_data": {
            "real_estate": {
                "source": "국토교통부 실거래가", "data_source": "live",
                "trade_table": [{"type": "아파트", "count": 120, "per_pyeong_manwon": 3200,
                                 "avg_10k": 92000, "avg_area_m2": 84.9}],
                "rent_table": [{"type": "아파트", "count": 40, "avg_10k": 45000,
                                "min_10k": 20000, "max_10k": 90000}],
                "trend_series": [{"ym": "202606", "per_pyeong_manwon": 3200, "mom_pct": 1.6},
                                  {"ym": "202607", "per_pyeong_manwon": 3250, "mom_pct": 1.6}],
                "competitor_complexes": [
                    {"name": "역삼래미안", "deal_count": 12, "avg_per_pyeong_manwon": 3300,
                     "price_basis": "전용", "recent_deal_ym": "202607", "build_year": 2015},
                ],
            },
            "population": {
                "data_source": "live", "migration_data_source": "live",
                "summary": {"total_population": 45000, "household_count": 18000, "avg_household_size": 2.5},
                "age_distribution": [{"label": "30-39", "count": 320}],
                "household_types": [{"label": "1인", "ratio": 45.0}],
                "migration": {"net_migration": 1300, "total_inflow": 12500, "total_outflow": 11200},
                "source": "통계청",
            },
            "income": {"data_source": "live", "avg_income_10k": 4800, "median_income_10k": 4080,
                       "median_estimated": True, "source": "국세청"},
        },
    }


def test_market_adapter_real_output_passes_soft_gate():
    """R1 이 갭으로 지목한 5종 중 하나 — market_adapter 실산출물 회귀락."""
    model = build_report_model_from_market(_market_full_rep())
    result = check_publishable(model)
    assert result.ok, result.violations


def _regulation_result_full() -> dict:
    """RegulationAnalysisService.analyze 산출 표본(test_regulation_report_adapter._result_full
    미러 — 크로스 tests 패키지 임포트 함정 회피를 위해 로컬 인라인)."""
    return {
        "address": "서울시 강남구 역삼동 1-1", "pnu": "1168010100101010001",
        "zone_type": "제3종일반주거지역", "zone_type_secondary": None,
        "land_area_sqm": 1234.5, "land_category": "대", "land_use_situation": "상업용",
        "limits": {
            "bcr": {"legal": 60, "ordinance": 50, "effective": 50, "unit": "%"},
            "far": {"legal": 250, "ordinance": 200, "effective": 200, "unit": "%"},
            "height": {"value": 20, "unit": "m", "max_floors": None, "basis": "건축법 제60조"},
            "parking": {"description": "주차장법 시행령 별표1 부설주차장 설치기준 적용"},
        },
        "hierarchy": [
            {
                "level": "상위법령",
                "items": [
                    {"name": "국토의 계획 및 이용에 관한 법률", "ref": "제76·77·78조",
                     "desc": "용도지역 행위제한·건폐율·용적률 상한"},
                    {"name": "건축법", "ref": "제55·56조", "desc": "건폐율·용적률 제한"},
                ],
                "legal_refs": [
                    {"key": "far_limit", "law_name": "국토계획법", "article": "제78조",
                     "title": "용적률", "url": "https://law.go.kr/x", "url_status": "verified"},
                ],
            },
            {
                "level": "지자체 조례",
                "items": [
                    {"name": "강남구 도시계획 조례", "ref": "-", "desc": "건폐율 50% · 용적률 200%"},
                ],
                "legal_refs": [],
            },
        ],
        "districts": [
            {"name": "지구단위계획구역", "code": "D-1", "impact": "상", "status": "결정"},
        ],
        "evidence": [
            {"label": "용적률 상한", "value": "200%", "basis": "조례 강화 적용",
             "legal_ref_key": "far_limit"},
        ],
        "ai": {
            "generated": True,
            "summary": "제3종일반주거지역으로 용적률 200%(조례 강화)가 적용됩니다.",
            "dev_impact": "밀도 계획 시 조례 한도를 기준으로 검토 필요.",
            "key_constraints": ["용적률 조례 강화", "높이 20m"],
            "strategies": ["인센티브 검토"], "opportunities": [], "risks": ["일조권 사선"],
        },
    }


def test_regulation_adapter_real_output_passes_soft_gate():
    model = build_report_model_from_regulation(_regulation_result_full(), address="테스트주소")
    result = check_publishable(model)
    assert result.ok, result.violations


def test_bank_adapter_real_output_passes_soft_gate():
    bank = {
        "meta": {"title": "사업성 분석 보고서 — <샘플>", "generated_at": "2026-07-03",
                 "legal_disclaimer": "AI 기반 자동 분석 결과."},
        "sections": [
            {"id": "summary", "title": "1. 사업개요", "has_data": True,
             "content": {"address": "용인 <샘플> & 처인", "land_area_sqm": 11465, "estimated_value": 0}},
            {"id": "esg", "title": "9. ESG 분석", "has_data": False, "content": {}},
        ],
        "completeness": {"total": 2, "filled": 1, "empty": 1, "pct": 50},
    }
    model = build_report_model_from_bank(bank)
    result = check_publishable(model)
    assert result.ok, result.violations


def test_persona_adapter_real_output_passes_soft_gate():
    """빈 artifacts(무목업 최소 표본)로도 게이트 위반 없이 통과해야 한다."""
    report = {"persona_key": "developer", "address": "테스트", "status": "ok", "artifacts": {}}
    model = build_report_model_from_persona(report, "developer")
    result = check_publishable(model)
    assert result.ok, result.violations


def _rough_scenario() -> dict:
    """개략수지 정상(actual) 표본(test_rough_scenario_report._scenario 미러 — 크로스 tests
    패키지 임포트 함정 회피를 위해 로컬 인라인)."""
    return {
        "address": "서울특별시 강남구 역삼동 736", "project_id": "abcd1234-ef56-7890",
        "scenario_status": "actual",
        "inputs": {
            "land_area_sqm": 1000.0, "zone_type": "제2종일반주거지역",
            "effective_far_pct": 200.0, "dev_type": "M06", "dev_type_name": "일반분양",
            "gfa_sqm": 2000.0, "saleable_area_pyeong": 423.5, "parcel_count": 1,
            "project_months": 30,
        },
        "land_cost": {
            "total_won": 5_000_000_000, "per_sqm_won": 5_000_000,
            "basis": "탁상감정 적정단가 5,000,000원/㎡ × 1,000㎡ + 취득세 등",
            "evidence": {"evidence": [{"label": "채택 단가", "value": "5,000,000원/㎡"}]},
            "source": "desk_appraisal(탁상감정)",
        },
        "construction_cost": {
            "total_won": 5_000_000_000, "unit_per_sqm_won": 2_500_000,
            "basis": "국토부 기본형건축비 직접공사비 + 간접비 15%",
            "source": "construction_cost_engine(국토부 SSOT)",
        },
        "revenue": {
            "total_won": 16_000_000_000, "sale_price_per_pyeong": 40_000_000,
            "saleable_area_pyeong": 423.5, "basis": "지역×유형 시장표준 시세 × 분양가능면적",
            "source": "지역 시세 테이블",
        },
        "cost_breakdown": {
            "land_won": 5_000_000_000, "construction_won": 5_000_000_000,
            "finance_won": 800_000_000, "other_won": 400_000_000,
        },
        "margin": {"developer_profit_won": 2_440_000_000, "rate_pct": 20.0, "target_revenue_won": 14_640_000_000},
        "summary": {
            "total_cost_won": 12_200_000_000, "total_revenue_won": 16_000_000_000,
            "net_profit_won": 3_800_000_000, "roi_pct": 31.1, "npv_won": 3_000_000_000,
            "irr_pct": 25.0, "payback_month": 28, "grade": "A",
        },
        "cashflow": {
            "monthly_rows": [
                {"month": m, "inflow": 0, "outflow": 100, "net": -100, "cumulative": -100 * (m + 1)}
                for m in range(30)
            ],
            "summary": {"peak_negative_cashflow": -3_000_000_000, "discount_rate_annual_pct": 6.0,
                       "irr_annual_pct": 25.0},
        },
        "overrides_applied": [], "degraded_notes": [],
    }


def test_feasibility_rough_scenario_adapter_real_output_passes_soft_gate():
    from app.services.feasibility.rough_scenario_report import build_rough_scenario_report_model

    model = build_rough_scenario_report_model(_rough_scenario())
    result = check_publishable(model)
    assert result.ok, result.violations


# ── (f) render_report 진입부 배선(hard 차단 / soft 통과) ─────────────


def test_render_report_raises_on_hard_violation_at_expert_reviewed():
    model = _model(
        blocks=[NarrativeBlock(paragraphs=["본 사업성 분석 결과는 확정된 것입니다."])],
        approval_state="EXPERT_REVIEWED",
    )
    with pytest.raises(ReportPublishGateError) as exc_info:
        render_report(model, "pdf")
    assert "FORBIDDEN_WORD" in str(exc_info.value)


def test_render_report_raises_on_approved_without_approver_before_touching_renderer():
    """approved_by 누락은 reportlab 유무와 무관하게 렌더러 진입 전에 걸러진다."""
    model = _model(approval_state="APPROVED")
    with pytest.raises(ReportPublishGateError) as exc_info:
        render_report(model, "pdf")
    assert "APPROVED_WITHOUT_APPROVER" in str(exc_info.value)


def test_render_report_draft_with_forbidden_word_never_raises_and_reaches_renderer():
    """★R1 무회귀 핵심: DRAFT 상태에서 금지어가 있어도 render_report 는 절대 예외를 던지지
    않고 PDF 렌더까지 도달한다(경고는 표지 워터마크로만 노출)."""
    pytest.importorskip("reportlab")
    model = _model(blocks=[NarrativeBlock(paragraphs=["본 사업성 분석 결과는 확정된 것입니다."])])
    data, mime, ext = render_report(model, "pdf")
    assert ext == "pdf" and mime == "application/pdf"
    assert data[:4] == b"%PDF"


def test_render_report_default_draft_model_passes_gate_and_reaches_renderer():
    pytest.importorskip("reportlab")
    model = _model(blocks=[NarrativeBlock(paragraphs=["정상적인 결론 문단입니다."])])
    data, mime, ext = render_report(model, "pdf")
    assert ext == "pdf" and mime == "application/pdf"
    assert data[:4] == b"%PDF"


# ── (g) apps.api.exceptions 전역 핸들러 — ReportPublishGateError → 409 ──


def test_report_publish_gate_error_maps_to_409_via_registered_handler():
    """공용 처리 1곳(apps.api.exceptions.register_exception_handlers) — 라우터 개별 수정 없이
    ReportPublishGateError 가 어디서 발생하든 정직한 409(REPORT_PUBLISH_GATE_VIOLATION)로 응답."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from apps.api.exceptions import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/__test_boom__")
    def _boom():
        model = _model(approval_state="APPROVED")  # approved_by 누락 -> hard 위반
        gate = check_publishable(model)
        raise ReportPublishGateError(gate)

    client = TestClient(app)
    resp = client.get("/__test_boom__")
    assert resp.status_code == 409
    body = resp.json()
    assert body["error_code"] == "REPORT_PUBLISH_GATE_VIOLATION"
    assert any(v["code"] == "APPROVED_WITHOUT_APPROVER" for v in body["details"]["violations"])


# ── (h) JSON 우회 경로 — 절대 차단 안 함, gate 필드 동봉 ─────────────


def test_json_bypass_path_never_blocks_and_carries_gate_field():
    """rough_scenario_report._model_to_json 은 render_report 를 거치지 않는다 — hard 위반이
    있어도(APPROVED+approved_by 없음) JSON 직렬화는 절대 예외를 던지지 않고 gate 필드로
    violations/warnings 를 정직하게 동봉한다(스코프 결정 — JSON은 프리뷰 채널)."""
    from app.services.feasibility.rough_scenario_report import _model_to_json

    model = _model(
        blocks=[NarrativeBlock(paragraphs=["본 사업성 분석 결과는 확정된 것입니다."])],
        approval_state="APPROVED",  # approved_by 없음 -> hard 위반이지만 JSON은 차단 안 함
    )
    out = _model_to_json(
        model, scenario={}, narrative={}, consultation=None,
        use_llm=False, ai_included=False, ai_note="",
    )
    assert "gate" in out
    assert any(v["code"] == "APPROVED_WITHOUT_APPROVER" for v in out["gate"]["violations"])
