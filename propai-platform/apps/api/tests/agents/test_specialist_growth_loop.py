"""성장루프 후반부 절단 수정 검증 — SpecialistAgent (asyncio_mode=auto).

1) 死경로: 기본 ingester 가 `.delay`(워커 부재 시 no-op) 대신 dispatch_memory_ingest
   (워커 유무 자동판별 + in-process 폴백) 공용 디스패처를 쓰는지.
2) 침묵실패: 내러티브형 인터프리터(dict[str,str] — market 등) 출력이 _narrative_to_items
   어댑터로 citation_gate items 에 합류해 claims 로 주입되는지(과거 실효 0).
3) 조인키: run() 응답 최상위 `ledger_hash`(원장 content_hash) 표준 노출.
"""
from __future__ import annotations

from app.services.agents.specialist_agent import (
    SpecialistAgent,
    _call_interpreter,
    _narrative_to_items,
)


def _tool(data):
    # 계층1 결정론 도구 모사 — 수치는 여기서만 생성
    return {"findings": [{"check_id": "MARKET", "status": "info",
                          "current": data.get("avg_price", 850.5), "limit": None}],
            "summary": {"avg_price_10k": data.get("avg_price", 850.5)}}


async def _rec_ok(*, analysis_type, payload, **kw):
    return {"ok": True, "version": 1, "content_hash": "c" * 64,
            "contradictions": {"has_contradiction": False}}


async def _prior_none(**kw):
    return None


# ── _narrative_to_items: 내러티브 dict → citation_gate items 어댑터 ──────────

def test_narrative_to_items_verbatim_claims_and_source_basis():
    raw = {
        "market_overview": "해당 지역 시장은 안정적입니다.",
        "risk_factors": "금리 변동이 핵심 리스크입니다.",
    }
    items = _narrative_to_items(raw, source="interpreter:market")
    assert len(items) == 2
    # ★날조 금지: 내러티브 문장이 그대로 claim(요약·재작성 없음)
    claims = {it["claim"] for it in items}
    assert "해당 지역 시장은 안정적입니다." in claims
    assert "금리 변동이 핵심 리스크입니다." in claims
    # basis 는 인터프리터 출처 표기
    assert all(it["basis"].startswith("interpreter:market:") for it in items)
    assert all(it["confidence"] == "medium" for it in items)


def test_narrative_to_items_skips_items_key_and_non_str():
    raw = {
        "items": [{"claim": "구조화", "basis": "B", "confidence": "high"}],  # _to_items 몫
        "empty": "   ",          # 공백뿐 — 제외
        "numeric": 123,          # 문자열 아님 — 제외
        "overview": "정상 문장",
    }
    items = _narrative_to_items(raw)
    assert [it["claim"] for it in items] == ["정상 문장"]


def test_narrative_to_items_non_dict_returns_empty():
    assert _narrative_to_items(None) == []
    assert _narrative_to_items([{"claim": "x"}]) == []
    assert _narrative_to_items("문장") == []


# ── _call_interpreter: 시그니처 kwargs 필터(단일경유) ────────────────────────

async def test_call_interpreter_filters_unsupported_kwargs_legacy_signature():
    seen = {}

    class _Legacy:
        # 구형: prior_context 미수용 — 필터 없이 넘기면 TypeError → 해석 침묵 스킵이던 경로
        async def generate_interpretation(self, data):
            seen["data"] = data
            return {"overview": "구형 시그니처도 동작"}

    out = await _call_interpreter(_Legacy(), {"k": 1}, prior_context="PRIOR")
    assert out == {"overview": "구형 시그니처도 동작"}
    assert seen["data"] == {"k": 1}


async def test_call_interpreter_passes_supported_kwargs():
    seen = {}

    class _Modern:
        async def generate_interpretation(self, data, *, prior_context=None):
            seen["prior_context"] = prior_context
            return {}

    await _call_interpreter(_Modern(), {}, prior_context="PRIOR")
    assert seen["prior_context"] == "PRIOR"


async def test_call_interpreter_var_kwargs_pass_through():
    seen = {}

    class _VarKw:
        async def generate_interpretation(self, data, **kwargs):
            seen.update(kwargs)
            return {}

    await _call_interpreter(_VarKw(), {}, prior_context="P", extra="E")
    assert seen == {"prior_context": "P", "extra": "E"}


# ── run(): 내러티브 인터프리터 주입(침묵실패 해소) ───────────────────────────

async def test_run_narrative_interpreter_claims_injected():
    # market 실형태: dict[str,str] 내러티브 — 과거 _to_items 만으로는 claims=[] (주입 실효 0)
    class _MarketLike:
        async def generate_interpretation(self, data, *, prior_context=None):
            return {
                "market_overview": "평균 실거래가는 850.5만원 수준입니다.",
                "risk_factors": "공급과잉 리스크에 유의해야 합니다.",
            }

    agent = SpecialistAgent(domain="market", task_type="market_analysis", tool=_tool,
                            interpreter=_MarketLike(), recorder=_rec_ok,
                            prior_loader=_prior_none)
    out = await agent.run({"avg_price": 850.5}, tenant_id="t", pnu="P1")
    assert len(out["claims"]) == 2                       # ★내러티브가 claims 로 합류
    joined = " ".join(c["claim"] for c in out["claims"])
    assert "850.5" in joined                             # findings 근거 수치는 보존(grounded)
    assert "공급과잉 리스크에 유의해야 합니다." in joined  # 문장 원형 유지(날조 없음)


async def test_run_legacy_interpreter_signature_no_typeerror():
    # 구형 시그니처(prior_context 미수용)여도 해석이 침묵 스킵되지 않는다(단일경유 필터)
    class _Legacy:
        async def generate_interpretation(self, data):
            return {"overview": "구형도 주입됩니다."}

    agent = SpecialistAgent(domain="market", task_type="market_analysis", tool=_tool,
                            interpreter=_Legacy(), recorder=_rec_ok,
                            prior_loader=_prior_none)
    out = await agent.run({}, tenant_id="t", pnu="P1")
    assert out["claims"] and "구형도 주입됩니다." in out["claims"][0]["claim"]


async def test_run_structured_items_still_work_with_adapter_merge():
    # 기존 구조화 items 경로 불변(어댑터 합류는 additive)
    class _Structured:
        async def generate_interpretation(self, data, *, prior_context=None):
            return {"items": [{"claim": "평균가 850.5 확인", "basis": "MARKET",
                               "confidence": "high"}]}

    agent = SpecialistAgent(domain="market", task_type="market_analysis", tool=_tool,
                            interpreter=_Structured(), recorder=_rec_ok,
                            prior_loader=_prior_none)
    out = await agent.run({"avg_price": 850.5}, tenant_id="t", pnu="P1")
    assert len(out["claims"]) == 1 and "850.5" in out["claims"][0]["claim"]


# ── run(): 응답 최상위 ledger_hash(성장루프 조인키) ──────────────────────────

async def test_run_exposes_top_level_ledger_hash():
    agent = SpecialistAgent(domain="market", task_type="market_analysis", tool=_tool,
                            interpreter=None, recorder=_rec_ok, prior_loader=_prior_none)
    out = await agent.run({}, tenant_id="t", pnu="P1")
    assert out["ledger_hash"] == "c" * 64                # ★표준 필드(프론트 피드백 키잉)
    assert out["ledger"]["content_hash"] == "c" * 64     # 기존 중첩 필드도 불변(additive)


async def test_run_omits_ledger_hash_when_append_fails():
    async def _rec_fail(*, analysis_type, payload, **kw):
        return {"ok": False, "message": "quota_exceeded"}

    agent = SpecialistAgent(domain="market", task_type="market_analysis", tool=_tool,
                            interpreter=None, recorder=_rec_fail, prior_loader=_prior_none)
    out = await agent.run({}, tenant_id="t", pnu="P1")
    assert "ledger_hash" not in out                      # 미적재 → 키 생략(정직)


# ── 기본 ingester: .delay 死경로 → dispatch_memory_ingest 공용 디스패처 ──────

async def test_default_ingester_uses_dispatch_memory_ingest(monkeypatch):
    from app.tasks import memory_tasks

    captured: dict = {}

    def _fake_dispatch(payload: dict) -> None:          # 계약: dict 1개·fire-and-forget
        captured["payload"] = payload

    monkeypatch.setattr(memory_tasks, "dispatch_memory_ingest", _fake_dispatch)

    async def _recaller(*, query, domain, top_k):
        return []

    agent = SpecialistAgent(domain="market", task_type="market_analysis", tool=_tool,
                            interpreter=None, recorder=_rec_ok, prior_loader=_prior_none,
                            recaller=_recaller)          # ingester 미주입 = 기본(프로덕션) 경로
    await agent.run({}, tenant_id="t", pnu="P1")
    assert captured, "기본 경로가 dispatch_memory_ingest 를 발화해야 한다(死경로 재발 방지)"
    assert captured["payload"]["domain"] == "market"
    assert captured["payload"]["source_type"] == "agent_execution"
