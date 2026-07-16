"""전문가 패널 degraded 사유 전달 검증 — WP-R4(침묵 폴백 제거).

라이브 실측: 패널만 실패 = max_tokens 절단 → json.loads 실패 → 침묵 폴백이었다.
이제 실패 사유(truncation/timeout/validation/invalid_json/provider)를 분류해 프론트에
degraded_reason으로 정직 전달한다(무목업). max_tokens는 8000으로 상향(절단 구조적 제거).
"""
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.expert_panel.expert_panel_service import ExpertPanelService

_ROSTER = [
    {"role": "도시계획 전문가", "lens": "용도지역 관점"},
    {"role": "부동산 법률가", "lens": "규제 충돌 관점"},
]


@pytest.fixture(autouse=True)
def _fake_langchain(monkeypatch):
    """_single 내부 `from langchain_core.messages import ...`를 hermetic하게 충족(무거운 의존성 회피)."""
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


def test_fallback_carries_degraded_reason_and_message():
    """폴백은 degraded_reason과 사유별 정직 메시지를 실어야 한다(침묵 금지)."""
    fb = ExpertPanelService._fallback(_ROSTER, degraded_reason="truncation")
    assert fb["generated"] is False
    assert fb["degraded_reason"] == "truncation"
    assert "잘려" in fb["consensus"] or "토큰 한도" in fb["consensus"]


def test_fallback_without_reason_is_backward_compatible():
    """사유 없는 폴백은 기존 일반 메시지(하위호환·무회귀)."""
    fb = ExpertPanelService._fallback(_ROSTER)
    assert fb["generated"] is False
    assert fb["degraded_reason"] is None
    assert "일시적으로 제공되지 않습니다" in fb["consensus"]


def _mock_llm(content: str, stop_reason: str | None = None):
    resp = MagicMock()
    resp.content = content
    resp.response_metadata = {"stop_reason": stop_reason} if stop_reason else {}
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=resp)
    return llm


async def _run_single(content: str, stop_reason: str | None = None):
    with (
        patch("app.services.ai.llm_provider.get_llm", return_value=_mock_llm(content, stop_reason)),
        patch("app.services.ai.base_interpreter.record_llm_response_billing", new=AsyncMock()),
    ):
        svc = ExpertPanelService()
        return await svc._single("규제 분석", "대상지", "{}", _ROSTER)


async def test_single_truncation_reason_when_stop_max_tokens():
    """절단(stop_reason=max_tokens) + 깨진 JSON → degraded_reason='truncation'."""
    res = await _run_single('{"experts": [{"role": "도시계획', stop_reason="max_tokens")
    assert res["generated"] is False
    assert res["degraded_reason"] == "truncation"


async def test_single_invalid_json_reason_when_no_truncation():
    """절단 신호 없이 깨진 JSON → degraded_reason='invalid_json'."""
    res = await _run_single("이건 JSON이 아닙니다", stop_reason="stop")
    assert res["generated"] is False
    assert res["degraded_reason"] == "invalid_json"


async def test_single_validation_reason_when_experts_missing():
    """유효 JSON이나 experts 누락 → degraded_reason='validation'."""
    res = await _run_single('{"consensus": "무엇"}', stop_reason="stop")
    assert res["generated"] is False
    assert res["degraded_reason"] == "validation"


async def test_single_success_sets_generated_true():
    """정상 응답은 generated=True(회귀 방지)."""
    good = '{"experts": [{"role": "도시계획 전문가", "opinion": "의견"}], "consensus": "결론"}'
    res = await _run_single(good, stop_reason="stop")
    assert res["generated"] is True
    assert "degraded_reason" not in res or res.get("degraded_reason") is None


async def test_single_uses_large_max_tokens_to_prevent_truncation():
    """WP-R4 회귀잠금: max_tokens는 절단을 유발하던 3500이 아니라 충분히 커야 한다(≥6000)."""
    good = '{"experts": [{"role": "도시계획 전문가", "opinion": "의견"}], "consensus": "결론"}'
    captured: dict = {}

    def _capture_get_llm(*args, **kwargs):
        captured.update(kwargs)
        return _mock_llm(good, "stop")

    with (
        patch("app.services.ai.llm_provider.get_llm", side_effect=_capture_get_llm),
        patch("app.services.ai.base_interpreter.record_llm_response_billing", new=AsyncMock()),
    ):
        await ExpertPanelService()._single("규제 분석", "대상지", "{}", _ROSTER)
    assert captured.get("max_tokens", 0) >= 6000, f"max_tokens 회귀 — got {captured.get('max_tokens')}"
