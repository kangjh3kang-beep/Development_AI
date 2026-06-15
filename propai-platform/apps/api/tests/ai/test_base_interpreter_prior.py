"""Phase 1: _invoke prior_context가 프롬프트에 부착되고 캐시키를 분리하는지(LLM mock)."""
import sys
import types

import pytest

from app.services.ai.base_interpreter import BaseInterpreter


def _install_fake_langchain(monkeypatch):
    """_invoke 내부의 `from langchain_core.messages import ...`를 hermetic하게 충족.

    이 단위테스트는 우리 프롬프트 조립 로직만 검증하므로 무거운 langchain 의존성을 주입하지 않는다.
    """
    class _Msg:
        def __init__(self, content=None, **kw):
            self.content = content

    mod = types.ModuleType("langchain_core.messages")
    mod.SystemMessage = _Msg
    mod.HumanMessage = _Msg
    pkg = types.ModuleType("langchain_core")
    pkg.messages = mod
    monkeypatch.setitem(sys.modules, "langchain_core", pkg)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", mod)


class _Probe(BaseInterpreter):
    name = "probe"
    expected_keys = ("text",)
    fallback_key = "text"
    max_tokens = 256
    system_prompt = "test"


class _FakeResp:
    content = '{"text": "ok"}'
    usage_metadata: dict = {}


class _FakeLLM:
    model = "fake"

    def __init__(self, sink: dict):
        self._sink = sink

    async def ainvoke(self, messages, config=None):
        # messages[-1] = HumanMessage(user_prompt) — prior 블록이 부착된 최종 프롬프트
        self._sink["prompt"] = messages[-1].content
        return _FakeResp()


@pytest.mark.asyncio
async def test_prior_context_appended_to_prompt(monkeypatch):
    captured: dict = {}

    async def _noop_billing(*a, **k):
        return None

    _install_fake_langchain(monkeypatch)
    monkeypatch.setattr(BaseInterpreter, "_get_llm", lambda self: _FakeLLM(captured), raising=True)
    monkeypatch.setattr(
        "app.services.ai.base_interpreter._record_llm_billing", _noop_billing, raising=True
    )
    monkeypatch.setenv("INTERP_REDIS_CACHE", "0")

    itp = _Probe()
    # cache_data=None → 캐시 경로 스킵, 곧장 evidences→LLM
    await itp._invoke(
        "BASE PROMPT", cache_data=None,
        prior_context="## 이전 분석 기록 v2\n- FAR-01: fail",
    )
    assert "이전 분석 기록" in captured["prompt"]
    assert "FAR-01" in captured["prompt"]
    # 기존 동작: 추가 근거 헤더로 부착됨
    assert "추가 근거 자료" in captured["prompt"]


def test_prior_context_separates_cache_key():
    itp = _Probe()
    k_no = itp._cache_key({"_data": {"x": 1}})
    # prior가 있으면 cache_data가 묶여 키가 달라져야 함(stale 캐시 미반환)
    k_prior = itp._cache_key({"_data": {"_data": {"x": 1}, "_prior": "v2"}})
    assert k_no != k_prior
