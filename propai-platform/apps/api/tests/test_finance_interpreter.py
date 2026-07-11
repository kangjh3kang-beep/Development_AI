"""(P1 B-1 G6) FinanceInterpreter — generate_interpretation 계약 테스트.

finance 노드(POST /api/v2/feasibility/development-finance)가 산출한 PF/브릿지 구조·LTV·DSCR을
해석하는 신설 인터프리터. LLM 실호출 없이 _invoke를 모킹해(tests/test_interpreter_context.py의
TestGenerateInterpretationSignature 스타일 재사용) 계약만 검증한다: (1) 입력 수치가 프롬프트에
포함되는지(무날조 그라운딩 확인), (2) _invoke 응답을 그대로 반환하는지(응답 구조 계약).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ai.finance_interpreter import FinanceInterpreter  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _sample_finance_data() -> dict:
    """_build_development_finance()의 대표 응답 샘플."""
    return {
        "total_project_cost_won": 10_000_000_000,
        "equity_won": 3_000_000_000,
        "equity_ratio": 0.3,
        "pf_loan": {
            "amount_won": 5_000_000_000, "rate": 0.065, "interest_won": 812_500_000,
            "guarantee_fee_won": 50_000_000, "months": 30, "total_cost_won": 862_500_000,
        },
        "bridge_loan": {
            "amount_won": 2_000_000_000, "rate": 0.08, "interest_won": 160_000_000,
            "arrangement_fee_won": 20_000_000, "months": 12, "total_cost_won": 180_000_000,
        },
        "total_debt_won": 7_000_000_000,
        "ltv": 0.7,
        "dscr": None,
        "annual_debt_service_won": 485_000_000,
        "total_financing_cost_won": 1_042_500_000,
    }


class TestGenerateInterpretationContract:
    def test_prompt_includes_input_figures(self):
        """프롬프트에 입력 수치(PF/브릿지 금액·금리·LTV)가 그대로 포함된다(무날조 그라운딩)."""
        interp = FinanceInterpreter()
        captured: dict = {}

        async def _fake_invoke(user_prompt, **kwargs):  # noqa: ANN001
            captured["user_prompt"] = user_prompt
            captured.update(kwargs)
            return {"structure_analysis": "ok"}

        interp._invoke = _fake_invoke  # type: ignore[method-assign]
        data = _sample_finance_data()
        _run(interp.generate_interpretation(data))

        prompt = captured["user_prompt"]
        assert "5000000000" in prompt  # pf_loan.amount_won
        assert "0.065" in prompt  # pf_loan.rate
        assert "0.7" in prompt  # ltv
        compact = captured["cache_data"]
        assert compact["pf_loan"]["amount_won"] == 5_000_000_000
        assert compact["dscr"] is None  # 데이터 없음(NOI 미제공) 무날조 보존

    def test_returns_invoke_result_structure(self):
        """_invoke 응답을 그대로 반환한다(응답 구조 계약 — 4개 키 통과)."""
        interp = FinanceInterpreter()
        fake_result = {
            "structure_analysis": "브릿지→PF 전환 구조 적정",
            "rate_sensitivity": "±1%p 변동 시 연이자 영향 방향성",
            "risk_assessment": "LTV 70% 수준",
            "recommendation": "대주단 협상 시 금리 조건 재검토",
        }

        async def _fake_invoke(user_prompt, **kwargs):  # noqa: ANN001, ARG001
            return fake_result

        interp._invoke = _fake_invoke  # type: ignore[method-assign]
        result = _run(interp.generate_interpretation(_sample_finance_data()))
        assert result == fake_result
        assert set(result.keys()) == set(FinanceInterpreter.expected_keys)


class TestExtractCompactData:
    def test_pf_and_bridge_subfields_extracted(self):
        """pf_loan/bridge_loan 핵심 하위 필드만 추출(불필요 상세 제거)."""
        interp = FinanceInterpreter()
        compact = interp._extract_compact_data(_sample_finance_data())
        assert compact["pf_loan"]["rate"] == 0.065
        assert compact["bridge_loan"]["amount_won"] == 2_000_000_000
        assert compact["ltv"] == 0.7
        assert compact["total_debt_won"] == 7_000_000_000

    def test_missing_sub_dicts_graceful(self):
        """pf_loan/bridge_loan 키 자체가 없어도 KeyError 없이 빈 하위 dict로 처리."""
        interp = FinanceInterpreter()
        compact = interp._extract_compact_data({"total_project_cost_won": 1_000_000_000})
        assert compact["pf_loan"]["amount_won"] is None
        assert compact["bridge_loan"]["amount_won"] is None
