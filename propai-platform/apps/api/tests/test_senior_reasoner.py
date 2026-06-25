"""SeniorReasoner(FinCoT·debate 구조) 단위테스트 — 결정론·주입식 LLM."""

from app.services.senior_agents.reasoner import (
    build_fincot_prompt,
    build_irac_steps,
    reason,
    should_debate,
)

_CONSULT = {
    "name_ko": "시니어 금융전문가",
    "license_gate": "AI 보조 — 최종 책임은 금융기관.",
    "decision_framework": [
        {"rule_id": "fin.dscr_gate", "condition": "상환능력", "judgment": "DSCR≥1.25",
         "basis": "대주 약정", "tradeoff": "보수 vs 레버리지", "reasoning_blueprint": "NOI→원리금→DSCR"},
        {"rule_id": "fin.equity_ratio_reg", "condition": "자기자본", "judgment": "단계 10/15/20%",
         "basis": "PF 규제"},
    ],
    "evaluations": [
        {"rule_id": "fin.dscr_gate", "verdict": "BLOCK", "detail": "DSCR 0.85x"},
    ],
    "high_risk": True,
    "needs_expert_review": False,
    "overall_verdict": "BLOCK",
    "citations": ["대주 약정", "PF 규제"],
}


def test_irac_steps_map_evaluation_to_conclusion():
    steps = build_irac_steps(_CONSULT)
    assert len(steps) == 2
    dscr = next(s for s in steps if s["rule_id"] == "fin.dscr_gate")
    assert dscr["issue"] == "상환능력" and "DSCR≥1.25" in dscr["rule"]
    assert "BLOCK" in dscr["conclusion"] and "DSCR 0.85x" in dscr["conclusion"]
    # 평가 없는 규칙 → '정량 입력 시 판정' 정직 표기
    eq = next(s for s in steps if s["rule_id"] == "fin.equity_ratio_reg")
    assert "정량 입력" in eq["conclusion"]
    assert eq["application"] == "(추론경로 미정의)"  # blueprint 없음


def test_should_debate_only_when_necessary():
    assert should_debate(_CONSULT) is True  # high_risk + BLOCK
    assert should_debate({"high_risk": False, "needs_expert_review": False,
                          "overall_verdict": "PASS"}) is False
    assert should_debate({"needs_expert_review": True}) is True
    assert should_debate({"overall_verdict": "WARN"}) is True


def test_fincot_prompt_has_irac_and_citation_rule():
    steps = build_irac_steps(_CONSULT)
    p = build_fincot_prompt(_CONSULT, steps)
    assert "IRAC" in p and "쟁점" in p and "결론" in p
    assert "만들지 마라" in p  # citation 제약
    assert "BLOCK" in p  # 정량 종합 판정


def test_reason_structured_default_no_llm():
    r = reason(_CONSULT)
    assert r.mode == "structured" and r.narrative is None
    assert len(r.irac_steps) == 2
    assert r.debate is not None and "pro" in r.debate and "con" in r.debate  # high_risk → 발동
    assert r.prompt and r.to_dict()["mode"] == "structured"


def test_reason_with_injected_llm():
    r = reason(_CONSULT, llm=lambda prompt: f"서술[{len(prompt)}자]")
    assert r.mode == "llm" and r.narrative is not None and r.narrative.startswith("서술[")


def test_reason_llm_failure_degrades_to_structured():
    def boom(_p: str) -> str:
        raise RuntimeError("LLM 다운")

    r = reason(_CONSULT, llm=boom)
    assert r.mode == "structured" and r.narrative is None  # 정직 강등(서비스 중단 없음)


def test_no_debate_when_low_risk_pass():
    low = {**_CONSULT, "high_risk": False, "overall_verdict": "PASS"}
    assert reason(low).debate is None
