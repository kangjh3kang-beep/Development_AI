"""(P1 B-1 G6) DevelopmentMethodInterpreter — generate_interpretation 계약 테스트.

recommend 노드(POST /api/v1/development-methods/optimal-recommend)가 산출한 Top3 순위+게이트
데이터를 해석하는 신설 인터프리터. LLM 실호출 없이 _invoke를 모킹해(기존
tests/test_interpreter_context.py의 TestGenerateInterpretationSignature 스타일 재사용) 계약만
검증한다: (1) 입력 수치가 프롬프트에 포함되는지(무날조 그라운딩 확인), (2) _invoke 응답을
그대로 반환하는지(응답 구조 계약).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ai.development_method_interpreter import (  # noqa: E402
    DevelopmentMethodInterpreter,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _sample_recommend_data() -> dict:
    """optimal_recommend(IntegratedRecommender.recommend) 응답의 최소 대표 샘플."""
    return {
        "site": {
            "addresses": ["서울특별시 강남구 역삼동 123"],
            "parcel_count": 1,
            "primary_zone": "일반상업지역",
        },
        "gate": {"developability": "POSSIBLE", "resolvable": None, "severity_label": None},
        "integrated_area_sqm": 660.0,
        "baseline_far_pct": 800.0,
        "scenario_status": "actual",
        "land_price_reliable": True,
        "honest_disclosure": "랭킹은 동일 면적·현행 실효용적률 기준 상대비교입니다.",
        "ranked": [
            {
                "method": "M06", "type_name": "오피스텔", "applied_far_pct": 800.0,
                "total_gfa_sqm": 5280.0, "net_profit": 3_000_000_000, "profit_rate_pct": 18.5,
                "npv": 2_500_000_000, "composite": 72.3, "far_basis": "현행",
            },
            {
                "method": "M03", "type_name": "근린생활시설", "applied_far_pct": 800.0,
                "total_gfa_sqm": 5000.0, "net_profit": 2_000_000_000, "profit_rate_pct": 12.0,
                "npv": 1_500_000_000, "composite": 55.1, "far_basis": "현행",
            },
        ],
    }


class TestGenerateInterpretationContract:
    def test_prompt_includes_input_figures(self):
        """프롬프트에 입력 수치(1위 방식·용적률·수지)가 그대로 포함된다(무날조 그라운딩)."""
        interp = DevelopmentMethodInterpreter()
        captured: dict = {}

        async def _fake_invoke(user_prompt, **kwargs):  # noqa: ANN001
            captured["user_prompt"] = user_prompt
            captured.update(kwargs)
            return {"overall_recommendation": "ok"}

        interp._invoke = _fake_invoke  # type: ignore[method-assign]
        data = _sample_recommend_data()
        _run(interp.generate_interpretation(data))

        prompt = captured["user_prompt"]
        assert "역삼동 123" in prompt
        assert "일반상업지역" in prompt
        assert "800.0" in prompt  # baseline_far_pct
        assert "M06" in prompt  # 1위 방식 코드
        # cache_data(top3 compact)에도 수지 핵심 수치가 실린다(캐시 키가 입력을 반영).
        compact = captured["cache_data"]
        assert compact["top3"][0]["method"] == "M06"
        assert compact["top3"][0]["net_profit_won"] == 3_000_000_000

    def test_returns_invoke_result_structure(self):
        """_invoke 응답을 그대로 반환한다(응답 구조 계약 — 6개 키 통과)."""
        interp = DevelopmentMethodInterpreter()
        fake_result = {
            "overall_recommendation": "M06 오피스텔이 최적",
            "top1_analysis": "1위 분석",
            "top2_analysis": "2위 분석",
            "top3_analysis": "3위 분석",
            "gate_risk_assessment": "게이트 리스크 없음",
            "next_steps": "인허가 착수",
        }

        async def _fake_invoke(user_prompt, **kwargs):  # noqa: ANN001, ARG001
            return fake_result

        interp._invoke = _fake_invoke  # type: ignore[method-assign]
        result = _run(interp.generate_interpretation(_sample_recommend_data()))
        assert result == fake_result
        assert set(result.keys()) == set(DevelopmentMethodInterpreter.expected_keys)


class TestExtractCompactData:
    def test_top3_capped_and_gate_summary_included(self):
        """랭킹 3위 초과분은 제외(top3만)하고, 게이트·정직고지 요약이 포함된다."""
        interp = DevelopmentMethodInterpreter()
        data = _sample_recommend_data()
        data["ranked"].append({
            "method": "M01", "type_name": "아파트", "applied_far_pct": 800.0,
            "total_gfa_sqm": 5000.0, "net_profit": 1_000_000_000, "profit_rate_pct": 8.0,
            "npv": 500_000_000, "composite": 30.0, "far_basis": "현행",
        })
        compact = interp._extract_compact_data(data)
        assert len(compact["top3"]) == 3  # 4번째(M01) 컷
        assert compact["gate"]["developability"] == "POSSIBLE"
        assert compact["land_price_reliable"] is True
