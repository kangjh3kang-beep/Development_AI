"""★배선 락 — **BaseInterpreter 자신의** LLM 실패도 사유를 남기는가.

## 왜 이 파일이 따로 필요한가 (2026-08-25 실측)

형제 스위트 `test_llm_failure_reason_distribution.py` 는 `record_llm_failure()` 를 태운다.
그런데 그 함수는 docstring 이 스스로 밝히듯 **BaseInterpreter 밖**에서 `llm.ainvoke` 를
직접 부르는 서비스용이다. 정작 인터프리터 자신의 실패는 `_invoke` 안의 별도 쓰기가 남겼고,
그 payload 는 `{"ok": False, "error": ...}` 뿐이라 **`reason` 이 없었다.**

그래서 `_analyze_fallback_rate` 의 사유 집계
(`COALESCE(NULLIF(payload->>'reason',''), 'unlabeled')`)는 그 실패를 전부 `unlabeled`
로 센다 — **사유가 도착한 것처럼 보이면서 실제로는 아무것도 모르는** 상태다.

사소하지 않은 이유(라이브 실측 2026-08-25 · `/growth/insights`):
폴백률이 관측되는 서비스는 `site_analysis`(100%) · `feasibility`(100%) · `market`(40%)
**셋뿐인데 셋 다 BaseInterpreter 서브클래스**다
(`site_analysis_interpreter.py:138` · `feasibility_interpreter.py:106` ·
`market_interpreter.py:117`). 즉 이 한 자리가 **관측되는 폴백 전량**의 사유를 결정한다.

## 규율 각주

- **처방을 적용한 범위 = 결함이 사는 범위인가**(§D-20). `reason` 처방을 절반
  (`record_llm_failure`)에만 적용하고 나머지 절반을 남긴 것이 이 결함이다.
- 여기서는 **실제 대상**을 태운다 — 헬퍼가 아니라 `BaseInterpreter._invoke` 를 실패시킨다.
"""

from __future__ import annotations

import pytest

from app.services.ai.base_interpreter import BaseInterpreter
from app.services.growth import capture_service as gcap


class _Boom:
    """`ainvoke` 가 반드시 터지는 가짜 LLM."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def ainvoke(self, *_a, **_k):
        raise self._exc


class _Probe(BaseInterpreter):
    name = "probe_interpreter"
    expected_keys = ["summary"]
    fallback_key = "summary"
    system_prompt = "test"

    def _extract_compact_data(self, data):  # pragma: no cover - 미사용
        return data


async def _run(exc: BaseException) -> dict:
    """인터프리터를 실제로 실패시키고 **마지막 llm_call 이벤트**를 돌려준다."""
    gcap._QUEUE.clear()
    interp = _Probe(timeout_sec=5.0)
    interp._llm = _Boom(exc)
    out = await interp._invoke("prompt")
    assert out == {}, "실패 시 빈 dict 계약이 깨졌다"
    events = [e for e in gcap._QUEUE if e.get("event_type") == "llm_call"]
    assert events, "실패했는데 llm_call 이벤트가 한 줄도 안 남았다 — 분자가 사라진다"
    return events[-1]


@pytest.mark.asyncio
class TestInterpreterFailureCarriesReason:
    async def test_대조군_실패_이벤트_자체는_남는다(self):
        # ★단언 앞에 두는 생존 확인 — 이벤트가 아예 안 남으면 아래 사유 단언은
        #   "대상 0개"라서 공허해진다(§A-2).
        ev = await _run(TimeoutError("deadline exceeded"))
        assert ev["service"] == "probe_interpreter"
        assert (ev.get("payload") or {}).get("ok") is False
        gcap._QUEUE.clear()

    async def test_핵심_실패_이벤트가_집계가능한_사유를_싣는다(self):
        ev = await _run(TimeoutError("deadline exceeded"))
        pl = ev.get("payload") or {}
        assert pl.get("reason") == "timeout", (
            "인터프리터 실패에 reason 이 없다 — analyzer 가 전부 unlabeled 로 센다"
        )
        assert pl.get("error_type") == "TimeoutError", (
            "예외 타입이 안 실렸다 — other 안이 깜깜해진다"
        )
        gcap._QUEUE.clear()

    async def test_특이도_다른_예외는_다른_사유가_된다(self):
        # ★"항상 timeout 을 넣는" 구현도 위 테스트는 통과한다 — 두 모집단이
        #   실제로 **다른 값**을 내야 배선이 잠긴다(§A-2 픽스처 분리).
        ev = await _run(KeyError("ownership"))
        assert (ev.get("payload") or {}).get("reason") == "shape"
        gcap._QUEUE.clear()

    async def test_지연_지표가_함께_보존된다(self):
        # ★공용 헬퍼로 합류시키면서 latency_ms 를 빠뜨리면 latency_regression·
        #   latency_baseline 의 모집단(`latency_ms IS NOT NULL`)이 조용히 줄어든다.
        #   합류가 만든 회귀를 여기서 막는다.
        ev = await _run(TimeoutError("x"))
        assert isinstance(ev.get("latency_ms"), int), "latency_ms 가 유실됐다"
        gcap._QUEUE.clear()

    async def test_이중계상이_아니다(self):
        # ★record_llm_failure 를 여기서 부르면 같은 실패가 두 줄이 되어 분자·분모가
        #   함께 부풀고 폴백률이 왜곡된다. 실패 1회 = llm_call 1줄이어야 한다.
        gcap._QUEUE.clear()
        interp = _Probe(timeout_sec=5.0)
        interp._llm = _Boom(TimeoutError("x"))
        await interp._invoke("prompt")
        calls = [e for e in gcap._QUEUE if e.get("event_type") == "llm_call"]
        assert len(calls) == 1, f"실패 1회에 llm_call 이 {len(calls)}줄 — 이중계상"
        gcap._QUEUE.clear()
