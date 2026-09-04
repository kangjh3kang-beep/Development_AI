"""시니어 자문 풍성화(2026-07-22) — IRAC 체인·실패모드·체크리스트 표면화 검증.

사용자 신고 "시니어 분석 빈약"의 후반부 수정: consultation_hook가 include_reasoning으로
IRAC 체인(쟁점→규칙[법령 근거]→적용→결론)을 동봉하고, risk_warnings·checklist를 표준
계약에 additive로 노출한다(결정론·무LLM — 지연/비용 0). 규제분석(with_senior)이 옵트인.
"""
from unittest.mock import AsyncMock, patch

from app.services.senior_agents.consultation_hook import (
    attach_senior_consultation_multi,
    build_compliance_inputs,
)


def _inputs() -> dict:
    return build_compliance_inputs(
        far_actual=80, far_limit=100, bcr_actual=20, bcr_limit=20, height_actual=4, height_limit=4,
    )


def test_default_no_reasoning_backward_compat():
    """기본(include_reasoning 미지정)은 기존 계약 그대로 — reasoning 키 없음(무회귀)."""
    out = attach_senior_consultation_multi(["deliberation", "urban", "legal"], _inputs())
    assert out["consultations"], "시니어 자문이 산출돼야 한다"
    for c in out["consultations"]:
        assert "reasoning" not in c
        # 풍성화 additive 필드는 기본에서도 노출(스펙 정적 콘텐츠 — LLM 무관)
        assert isinstance(c.get("risk_warnings"), list)
        assert isinstance(c.get("checklist"), list)


def test_include_reasoning_surfaces_irac_chain():
    out = attach_senior_consultation_multi(
        ["deliberation", "urban", "legal"], _inputs(), include_reasoning=True,
    )
    assert out["consultations"]
    for c in out["consultations"]:
        reasoning = c.get("reasoning")
        assert isinstance(reasoning, dict), f"{c.get('agent_key')}에 reasoning 없음"
        steps = reasoning.get("irac_steps")
        assert steps, "IRAC 체인이 비면 안 된다"
        for s in steps:
            # 각 단계는 쟁점/규칙/근거를 갖춘다(법령 근거 기반 판단 확장의 핵심 계약)
            assert s.get("issue"), s
            assert s.get("rule"), s
            assert s.get("basis"), s
            assert s.get("conclusion"), s
        # FinCoT 원문 프롬프트는 API 응답에서 제외(페이로드·노출 최소화)
        assert "prompt" not in reasoning


def test_context_signals_data_completeness_flows_to_confidence():
    """완결도 신호가 confidence에 반영된다(높은 완결도 ≥ 낮은 완결도)."""
    hi = attach_senior_consultation_multi(
        ["deliberation"], _inputs(), context_signals={"data_completeness": 1.0},
    )
    lo = attach_senior_consultation_multi(
        ["deliberation"], _inputs(), context_signals={"data_completeness": 0.0},
    )
    c_hi = hi["consultations"][0]["confidence"]
    c_lo = lo["consultations"][0]["confidence"]
    assert c_hi > c_lo


def test_context_signals_cannot_override_inputs():
    """context_signals의 inputs 키는 무시된다(정량 입력 계약 보호)."""
    out = attach_senior_consultation_multi(
        ["deliberation"], _inputs(),
        context_signals={"inputs": {"far_actual": 99999, "far_limit": 1}},
    )
    evals = out["consultations"][0]["evaluations"]
    assert evals, "정량 평가가 산출돼야 한다(공허 통과 방지)"
    assert all(e.get("verdict") != "BLOCK" for e in evals), "오염된 inputs가 반영되면 안 된다"


async def test_regulation_analyze_with_senior_includes_reasoning():
    """규제분석(with_senior=True)의 시니어 자문에 IRAC 체인이 실려 온다(옵트인 배선 검증)."""
    from app.services.regulation.regulation_analysis_service import RegulationAnalysisService

    comp = {
        "zone_type": "자연녹지지역", "zone_type_secondary": "", "pnu": "4146310300100560016",
        "coordinates": {"lat": 37.3, "lng": 127.1}, "land_area_sqm": 1161.0,
        "land_register": {"area_sqm": 1161.0, "land_category": "전"},
        "land_characteristics": {}, "land_use_plan": {"districts": ["자연녹지지역"]},
        "special_districts": [],
        "zone_limits": {"max_bcr_pct": 20, "max_far_pct": 100},
        "local_ordinance": {},
        "effective_far": {
            "effective_far_pct": 80.0, "effective_bcr_pct": 20.0, "structural_cap_pct": 80.0,
            "floor_cap": 4, "floor_cap_basis": "국토계획법 시행령 별표17(자연녹지지역) 두문 — 4층 이하",
            "far_basis": "구조상한(건폐율×층수)",
        },
    }
    with patch(
        "app.services.land_intelligence.land_info_service.LandInfoService.collect_comprehensive",
        new=AsyncMock(return_value=comp),
    ):
        result = await RegulationAnalysisService().analyze(
            "경기도 용인시 수지구 신봉동 56-16", pnu=None, use_llm=False, with_senior=True,
        )
    sc = result.get("senior_consultation")
    assert isinstance(sc, dict) and sc.get("consultations")
    assert any(
        (c.get("reasoning") or {}).get("irac_steps") for c in sc["consultations"]
    ), "규제 시니어 자문에 IRAC 체인이 있어야 한다"
