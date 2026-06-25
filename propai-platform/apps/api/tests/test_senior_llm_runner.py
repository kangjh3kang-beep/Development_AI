"""시니어 LLM 런너 — narrative 생성/graceful 강등(단일경유·기본off)."""

import pytest

from app.services.senior_agents.llm_runner import (
    SeniorNarratorInterpreter,
    generate_senior_narrative,
)


@pytest.mark.asyncio
async def test_use_llm_false_returns_none():
    # 기본 off → LLM 미호출·None(결정론 강등)
    assert await generate_senior_narrative("어떤 프롬프트", use_llm=False) is None


@pytest.mark.asyncio
async def test_empty_prompt_returns_none():
    assert await generate_senior_narrative("   ", use_llm=True) is None


@pytest.mark.asyncio
async def test_mocked_invoke_returns_narrative(monkeypatch):
    async def fake_invoke(self, prompt):  # noqa: ANN001, ARG001
        return {"narrative": "종합 판단: 조건부 Go. 핵심 리스크 …"}

    monkeypatch.setattr(SeniorNarratorInterpreter, "_invoke", fake_invoke)
    r = await generate_senior_narrative("FinCoT 프롬프트", use_llm=True)
    assert r is not None and r.startswith("종합 판단")


@pytest.mark.asyncio
async def test_invoke_failure_degrades_to_none(monkeypatch):
    async def boom(self, prompt):  # noqa: ANN001, ARG001
        raise RuntimeError("LLM 키 미설정")

    monkeypatch.setattr(SeniorNarratorInterpreter, "_invoke", boom)
    # 키 미설정/SDK 실패 → None(서비스 중단 없이 결정론 구조로 강등)
    assert await generate_senior_narrative("p", use_llm=True) is None


@pytest.mark.asyncio
async def test_empty_invoke_result_returns_none(monkeypatch):
    async def empty(self, prompt):  # noqa: ANN001, ARG001
        return {}  # _invoke graceful 빈 dict(파싱 실패 등)

    monkeypatch.setattr(SeniorNarratorInterpreter, "_invoke", empty)
    assert await generate_senior_narrative("p", use_llm=True) is None


def test_narrator_single_path_contract():
    # 단일경유 메터링 계약 — name(귀속)·expected_keys·fallback·citation/면허 시스템프롬프트
    i = SeniorNarratorInterpreter()
    assert i.name == "senior_reasoning"
    assert i.expected_keys == ["narrative"] and i.fallback_key == "narrative"
    assert "만들지 마라" in i.system_prompt and "면허" in i.system_prompt
