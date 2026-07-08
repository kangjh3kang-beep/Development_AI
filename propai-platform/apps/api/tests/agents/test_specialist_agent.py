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


# ── A5: allow_llm 과금 게이트 — interpreter 호출(과금 지점)만 스킵, 결정론/prior/recall/원장은 유지 ──


async def test_allow_llm_false_skips_interpreter_but_keeps_deterministic_output():
    called = {"n": 0}

    class _Interp:
        async def generate_interpretation(self, tool_out, *, prior_context=None):
            called["n"] += 1
            return {"items": [{"claim": "x", "basis": "PERMIT"}]}

    async def _rec(*, analysis_type, payload, **kw):
        return {"ok": True, "version": 1, "content_hash": "h",
                "contradictions": {"has_contradiction": False}}

    async def _prior(**kw):
        return None

    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=_Interp(), recorder=_rec, prior_loader=_prior)
    out = await agent.run({"ok": True, "far": 210.0}, tenant_id="t", pnu="P1", allow_llm=False)
    assert called["n"] == 0              # interpreter 미호출(무과금)
    assert out["claims"] == []
    assert out["findings"][0]["current"] == 210.0   # 결정론 산출은 무영향


async def test_allow_llm_default_true_calls_interpreter():
    called = {"n": 0}

    class _Interp:
        async def generate_interpretation(self, tool_out, *, prior_context=None):
            called["n"] += 1
            return {"items": []}

    async def _rec(*, analysis_type, payload, **kw):
        return {"ok": True, "version": 1, "content_hash": "h",
                "contradictions": {"has_contradiction": False}}

    async def _prior(**kw):
        return None

    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=_Interp(), recorder=_rec, prior_loader=_prior)
    await agent.run({"ok": True}, tenant_id="t", pnu="P1")   # allow_llm 미지정 → 기본 True(무회귀)
    assert called["n"] == 1


# ── A3: interpreter 시그니처 호환(prior_context 미지원 인터프리터도 호출되어야 한다) ──
# 배경: PermitInterpreter/DesignInterpreter.generate_interpretation은 prior_context를 받지 않는다
# (evidence_text만, 또는 위치인자 1개). 과거엔 prior_context를 강제 전달해 TypeError→graceful catch로
# claims=[]가 되는 dead-path였다(등록만 되고 실제 해석은 항상 실패).


async def test_interpreter_without_prior_context_param_is_still_called():
    """market과 달리 prior_context를 받지 않는 인터프리터(permit/design 실계약 모사)도 호출된다."""
    captured: dict = {}

    class _NoPriorInterp:
        async def generate_interpretation(self, tool_out):   # prior_context 파라미터 없음
            captured["tool_out"] = tool_out
            return {"items": [{"claim": "용적률 210% 적용", "basis": "PERMIT"}]}

    async def _rec(*, analysis_type, payload, **kw):
        return {"ok": True, "version": 1, "content_hash": "h",
                "contradictions": {"has_contradiction": False}}

    async def _prior(**kw):
        return None

    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=_NoPriorInterp(), recorder=_rec, prior_loader=_prior)
    out = await agent.run({"ok": True, "far": 210.0}, tenant_id="t", pnu="P1")
    assert captured.get("tool_out") is not None   # ★TypeError 없이 실제로 호출됐다
    assert out["claims"]                          # citation_gate grounded 발언이 생성됐다(빈 리스트가 아님)


# ── Phase 3.2 잔여: expert_panel 다관점 통합(panel DI, 선택·graceful) ──

async def _rec_ok(*, analysis_type, payload, **kw):
    return {"ok": True, "version": 1, "content_hash": "h",
            "contradictions": {"has_contradiction": False}}


async def _prior_none(**kw):
    return None


async def test_panel_output_attached_when_provided():
    captured = {}

    async def _panel(domain, context):
        captured["domain"] = domain
        return {"consensus": "조건부 진행", "experts": [{"role": "디벨로퍼"}], "generated": False}

    agent = SpecialistAgent(domain="market", task_type="analysis", tool=_tool,
                            interpreter=None, recorder=_rec_ok, prior_loader=_prior_none, panel=_panel)
    out = await agent.run({"ok": True}, tenant_id="t", pnu="P1")
    assert out["panel"]["consensus"] == "조건부 진행" and captured["domain"] == "market"


async def test_panel_failure_is_graceful():
    async def _boom(domain, context):
        raise RuntimeError("panel down")

    agent = SpecialistAgent(domain="market", task_type="analysis", tool=_tool,
                            interpreter=None, recorder=_rec_ok, prior_loader=_prior_none, panel=_boom)
    out = await agent.run({"ok": True}, tenant_id="t", pnu="P1")
    assert out["panel"] is None and out["findings"]   # 패널 실패해도 결정론 findings 유지


async def test_no_panel_key_is_none_when_not_provided():
    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=None, recorder=_rec_ok, prior_loader=_prior_none)
    out = await agent.run({"ok": True}, tenant_id="t", pnu="P1")
    assert out["panel"] is None   # panel 미주입 → None(additive·기존 불변)


# ── MemoryHub #2 디커플: 회상이 interpreter 유무와 무관히 표면화(계산 후 버림 차단) ──

class _Mem:
    """MemoryRecallResponse 모사(.id/.summary/.score/.source_type)."""
    def __init__(self, id, summary, score, source_type="agent_execution"):
        self.id = id
        self.summary = summary
        self.score = score
        self.source_type = source_type


def test_format_recall_block():
    from app.services.agents.specialist_agent import _format_recall_block
    assert _format_recall_block([]) == ""          # 빈 회상 → 빈 블록(prompt 오염 없음)
    block = _format_recall_block([{"summary": "용적률 250 적용", "score": 0.9}])
    assert "[Past Agent Memories (Know-how)]" in block and "용적률 250 적용" in block
    assert _format_recall_block([{"summary": "x", "score": None}]).endswith("- x")  # 비수치 score 안전


async def test_recall_surfaces_in_return_and_ingest_without_interpreter():
    # ★핵심 디커플: interpreter=None(현 7도메인)이어도 회상이 run() 반환 + ingest provenance로 표면화
    captured_ingest = {}

    def _ingester(payload):
        captured_ingest["payload"] = payload

    async def _recaller(*, query, domain, top_k):
        return [_Mem("11111111-1111-1111-1111-111111111111", "과거경험A", 0.93),
                _Mem("22222222-2222-2222-2222-222222222222", "과거경험B", 0.81)]

    agent = SpecialistAgent(domain="far", task_type="effective_far", tool=_tool,
                            interpreter=None, recorder=_rec_ok, prior_loader=_prior_none,
                            recaller=_recaller, ingester=_ingester)
    out = await agent.run({"ok": True}, tenant_id="t", pnu="P1")
    assert len(out["rag_memories"]) == 2 and out["rag_memories"][0]["summary"] == "과거경험A"
    md = captured_ingest["payload"]["metadata"]
    assert md["recalled_count"] == 2
    assert md["recalled_memory_ids"] == ["11111111-1111-1111-1111-111111111111",
                                         "22222222-2222-2222-2222-222222222222"]


async def test_ledger_payload_excludes_recall_for_determinism():
    # 회상은 원장 payload에 미주입(content_hash 멱등·모순탐지 불변식 보존)
    captured = {}

    async def _rec(*, analysis_type, payload, **kw):
        captured["payload"] = payload
        return {"ok": True, "version": 1, "content_hash": "h", "contradictions": {}}

    async def _recaller(*, query, domain, top_k):
        return [_Mem("1", "과거경험", 0.9)]

    agent = SpecialistAgent(domain="far", task_type="effective_far", tool=_tool,
                            interpreter=None, recorder=_rec, prior_loader=_prior_none,
                            recaller=_recaller, ingester=lambda p: None)
    await agent.run({"ok": True}, tenant_id="t", pnu="P1")
    for k in ("rag_memories", "recalled_memory_ids", "recalled_count"):
        assert k not in captured["payload"]


async def test_recall_failure_is_graceful():
    async def _recaller(*, query, domain, top_k):
        raise RuntimeError("qdrant down")

    agent = SpecialistAgent(domain="far", task_type="effective_far", tool=_tool,
                            interpreter=None, recorder=_rec_ok, prior_loader=_prior_none,
                            recaller=_recaller, ingester=lambda p: None)
    out = await agent.run({"ok": True}, tenant_id="t", pnu="P1")
    assert out["rag_memories"] == []   # 회상 실패 → 빈 목록(분석 무중단)
    assert out["findings"]             # 결정론 산출 유지


async def test_recall_injected_into_interpreter_prompt():
    # interpreter 있을 때 회상이 prior_context 뒤에 주입(즉시 활용)
    seen = {}

    class _Interp:
        async def generate_interpretation(self, tool_out, *, prior_context=None):
            seen["prior_context"] = prior_context
            return {"items": []}

    async def _recaller(*, query, domain, top_k):
        return [_Mem("1", "과거 노하우 XYZ", 0.88)]

    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=_Interp(), recorder=_rec_ok, prior_loader=_prior_none,
                            recaller=_recaller, ingester=lambda p: None)
    await agent.run({"ok": True}, tenant_id="t", pnu="P1")
    ctx = seen["prior_context"]
    assert ctx and "과거 노하우 XYZ" in ctx and "Past Agent Memories" in ctx


async def test_recall_default_path_graceful_without_infra():
    # ★기본 경로(recaller/ingester 미주입 = 프로덕션 실제 경로): 인프라(langchain/qdrant/celery) 부재 시
    #   MemoryHubService·memory_tasks import 실패가 try/except로 흡수돼 분석 무중단(회상 빈목록·findings 유지).
    agent = SpecialistAgent(domain="far", task_type="effective_far", tool=_tool,
                            interpreter=None, recorder=_rec_ok, prior_loader=_prior_none)
    out = await agent.run({"ok": True}, tenant_id="t", pnu="P1")
    assert out["rag_memories"] == []   # 회상 기본경로 import/생성 실패 → graceful 빈목록
    assert out["findings"]             # 결정론 산출 무중단
