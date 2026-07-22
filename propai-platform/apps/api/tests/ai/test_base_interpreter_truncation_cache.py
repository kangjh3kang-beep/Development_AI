"""BaseInterpreter 절단 정직 관측 + 파싱 폴백 캐시오염 봉합 검증.

2026-07-22 실측 결함 클래스의 기반클래스 일반화 회귀 잠금:
- 파싱 폴백({fallback_key: 원문})이 truthy라 성공과 구분 없이 L1/L2에 박제
  → 강등 결과가 TTL까지 서빙(#411 라우터 폴백 캐시오염과 동일 클래스).
- max_tokens 절단은 파서로 복구 불가한 별개 결함 — 경고+텔레메트리 truncated
  플래그로 표면화(절단 사냥=쿼리 1방).
"""
import sys
import types

import pytest

from app.services.ai.base_interpreter import BaseInterpreter


def _install_fake_langchain(monkeypatch):
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
    name = "probe_trunc"
    expected_keys = ("text",)
    fallback_key = "text"
    max_tokens = 256
    system_prompt = "test"


class _FakeResp:
    def __init__(self, content: str, stop: str | None = None):
        self.content = content
        self.usage_metadata: dict = {}
        self.response_metadata = {"stop_reason": stop} if stop else {}


class _CountingLLM:
    model = "fake"

    def __init__(self, resp: _FakeResp):
        self._resp = resp
        self.calls = 0

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        return self._resp


@pytest.fixture(autouse=True)
def _clean_result_cache():
    """L1 전역 캐시를 테스트 전후 청소 — 스위트 전역 격리(R1 위생 권고)."""
    from app.services.ai import base_interpreter as bi

    bi._RESULT_CACHE._store.clear()
    yield
    bi._RESULT_CACHE._store.clear()


def _setup(monkeypatch, llm):
    async def _noop_billing(*a, **k):
        return None

    from app.services.ai import base_interpreter as bi

    _install_fake_langchain(monkeypatch)
    monkeypatch.setattr(BaseInterpreter, "_get_llm", lambda self: llm, raising=True)
    monkeypatch.setattr(
        "app.services.ai.base_interpreter._record_llm_billing", _noop_billing, raising=True
    )
    monkeypatch.setenv("INTERP_REDIS_CACHE", "0")
    bi._env_flag_cache.clear()  # 30초 TTL 플래그 캐시 즉시 반영(직전 테스트 잔상 차단)


@pytest.mark.asyncio
async def test_parse_fallback_not_cached_retries_next_call(monkeypatch):
    """★캐시오염 봉합 — 파싱 폴백은 미저장 → 같은 입력 재호출 시 LLM 재시도(자가치유)."""
    llm = _CountingLLM(_FakeResp("죄송합니다. JSON을 만들 수 없습니다."))
    _setup(monkeypatch, llm)
    itp = _Probe()

    out1 = await itp._invoke("P", cache_data={"unique": "fallback-case-1"})
    out2 = await itp._invoke("P", cache_data={"unique": "fallback-case-1"})

    assert "text" in out1  # 폴백 자체는 종전대로 반환(호출자 계약 불변)
    assert out2 == out1
    assert llm.calls == 2  # 캐시 미적중 = 폴백이 박제되지 않았다는 행위 증거


@pytest.mark.asyncio
async def test_parse_success_still_cached(monkeypatch):
    """무회귀 — 성공 파싱은 종전대로 L1 캐시 적중(재호출 시 LLM 미호출)."""
    llm = _CountingLLM(_FakeResp('{"text": "ok"}'))
    _setup(monkeypatch, llm)
    itp = _Probe()

    await itp._invoke("P", cache_data={"unique": "success-case-1"})
    out2 = await itp._invoke("P", cache_data={"unique": "success-case-1"})

    assert out2 == {"text": "ok"}
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_truncated_flag_surfaces_in_telemetry(monkeypatch):
    """절단 관측성 — stop_reason=max_tokens면 텔레메트리 payload에 truncated=True."""
    llm = _CountingLLM(_FakeResp('{"text": "절단직전이지만 완결', stop="max_tokens"))
    _setup(monkeypatch, llm)
    events: list[dict] = []
    monkeypatch.setattr(
        "app.services.growth.capture_service.record_event",
        lambda kind, data: events.append({"kind": kind, **data}),
        raising=True,
    )
    itp = _Probe()

    await itp._invoke("P", cache_data=None)

    payloads = [e["payload"] for e in events if e.get("kind") == "llm_call"]
    assert payloads and payloads[-1]["truncated"] is True
    assert payloads[-1]["parse_ok"] is False


@pytest.mark.asyncio
async def test_untruncated_success_flags(monkeypatch):
    """경계 무회귀 — 정상 완결 응답은 truncated=False·parse_ok=True."""
    llm = _CountingLLM(_FakeResp('{"text": "ok"}', stop="end_turn"))
    _setup(monkeypatch, llm)
    events: list[dict] = []
    monkeypatch.setattr(
        "app.services.growth.capture_service.record_event",
        lambda kind, data: events.append({"kind": kind, **data}),
        raising=True,
    )
    itp = _Probe()

    await itp._invoke("P", cache_data=None)

    payloads = [e["payload"] for e in events if e.get("kind") == "llm_call"]
    assert payloads and payloads[-1]["truncated"] is False
    assert payloads[-1]["parse_ok"] is True


class _OverrideProbe(BaseInterpreter):
    """_parse_response를 오버라이드하는 서브클래스(blindspot·brief 패턴 대역)."""

    name = "probe_override"
    expected_keys = ("items",)
    fallback_key = ""
    max_tokens = 256
    system_prompt = "test"

    def _parse_response(self, raw: str) -> dict[str, str]:
        # blindspot 패턴: 리스트 값을 str() 평탄화 대신 유효 JSON 문자열로 보존.
        import json as _json

        parsed = _json.loads(raw)
        return {"items": _json.dumps(parsed["items"], ensure_ascii=False)}


@pytest.mark.asyncio
async def test_invoke_respects_parse_response_override(monkeypatch):
    """★R1 CRITICAL 회귀 잠금 — _invoke는 반드시 다형성 _parse_response를 태운다.

    _parse_response_ex 직접 호출로 오버라이드가 우회되면 blindspot(심의 쟁점 소실)·
    brief(quote/confidence 소실)가 무경보로 깨진다(라이브 재현됐던 결함).
    """
    import json as _json

    llm = _CountingLLM(_FakeResp('{"items": [{"k": "v"}]}'))
    _setup(monkeypatch, llm)
    itp = _OverrideProbe()

    out = await itp._invoke("P", cache_data={"unique": "override-case-1"})

    # 오버라이드가 살아있으면 items는 '유효 JSON 문자열'(json.loads 가능·쌍따옴표).
    assert _json.loads(out["items"]) == [{"k": "v"}]


@pytest.mark.asyncio
async def test_truncated_but_parseable_not_cached(monkeypatch):
    """★R1 MEDIUM 잠금 — 절단됐지만 관대파서가 살린 부분 JSON은 캐시 박제 금지."""
    llm = _CountingLLM(_FakeResp('{"text": "ok"}', stop="max_tokens"))
    _setup(monkeypatch, llm)
    itp = _Probe()

    await itp._invoke("P", cache_data={"unique": "trunc-parsed-1"})
    await itp._invoke("P", cache_data={"unique": "trunc-parsed-1"})

    assert llm.calls == 2  # 캐시 미적중 = 미완결 응답이 박제되지 않았다는 행위 증거
