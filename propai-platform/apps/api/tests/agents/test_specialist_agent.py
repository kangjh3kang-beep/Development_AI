"""Phase 3 T1 — SpecialistAgent 코어 단위테스트(의존성 주입 — 무 DB/LLM).

결정론 도구 호출 + prior + citation_gate grounded 발언 + 원장 cite(주입된 recorder) 검증.
asyncio_mode=auto — 데코레이터 불요.
"""
from app.services.agents.specialist_agent import SpecialistAgent


def _tool(data):
    # 계층1 결정론 도구 모사 — 수치는 여기서만 생성
    return {"findings": [{"check_id": "PERMIT", "status": "pass" if data.get("ok") else "fail",
                          "current": data.get("far", 200.0), "limit": 250.0}],
            "summary": {"far": data.get("far", 200.0)}}


async def test_run_calls_tool_and_cites_ledger_deterministically():
    captured = {}

    async def _fake_recorder(*, analysis_type, payload, **kw):
        captured["analysis_type"] = analysis_type
        captured["payload"] = payload
        return {"ok": True, "version": 1, "content_hash": "h1",
                "contradictions": {"has_contradiction": False, "counts": {}, "max_severity": None}}

    async def _fake_prior(**kw):
        return None

    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=None, recorder=_fake_recorder, prior_loader=_fake_prior)
    out = await agent.run({"ok": True, "far": 210.0}, tenant_id="t", pnu="P1")
    assert out["domain"] == "permit"
    assert out["findings"][0]["check_id"] == "PERMIT" and out["findings"][0]["current"] == 210.0
    assert out["ledger"]["content_hash"] == "h1"
    assert captured["analysis_type"] == "domain_agent_permit"
    assert captured["payload"]["findings_brief"][0]["current"] == 210.0
    assert captured["payload"]["claims"] == []   # interpreter 없음 → 발언 없음


async def test_llm_claims_pass_through_citation_gate_grounded_only():
    # interpreter가 미근거 수치를 말해도 citation_gate가 '전문가 확인 필요'로 치환
    class _Interp:
        async def generate_interpretation(self, tool_out, *, prior_context=None):
            return {"items": [{"claim": "용적률 999% 초과 위험", "basis": "PERMIT", "confidence": "high"}]}

    captured = {}

    async def _rec(*, analysis_type, payload, **kw):
        captured["payload"] = payload
        return {"ok": True, "version": 1, "content_hash": "h",
                "contradictions": {"has_contradiction": False}}

    async def _prior(**kw):
        return None

    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=_Interp(), recorder=_rec, prior_loader=_prior)
    out = await agent.run({"ok": True, "far": 200.0}, tenant_id="t", pnu="P1")
    claim_text = out["claims"][0]["claim"]
    assert "999" not in claim_text and "전문가 확인 필요" in claim_text


async def test_interpreter_failure_is_graceful():
    class _Boom:
        async def generate_interpretation(self, *a, **k):
            raise RuntimeError("LLM down")

    async def _rec(*, analysis_type, payload, **kw):
        return {"ok": True, "version": 1, "content_hash": "h",
                "contradictions": {"has_contradiction": False}}

    async def _prior(**kw):
        return None

    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=_Boom(), recorder=_rec, prior_loader=_prior)
    out = await agent.run({"ok": True}, tenant_id="t", pnu="P1")
    assert out["claims"] == []           # LLM 실패 → 발언 없음(결정론 findings는 유지)
    assert out["findings"]               # 결정론 산출은 무중단
