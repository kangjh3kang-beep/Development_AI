"""시니어 LLM 런너 — narrative 생성/graceful 강등(단일경유·기본off)."""

import pytest

from app.services.senior_agents.llm_runner import (
    SeniorDebateInterpreter,
    SeniorNarratorInterpreter,
    generate_senior_debate,
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


@pytest.mark.asyncio
async def test_debate_off_or_none_returns_none():
    assert await generate_senior_debate({"pro": "p", "con": "c"}, use_llm=False) is None
    assert await generate_senior_debate(None, use_llm=True) is None


@pytest.mark.asyncio
async def test_debate_executes_both_sides(monkeypatch):
    async def fake_invoke(self, prompt):  # noqa: ANN001, ARG001
        # 프롬프트 입장에 따라 다른 텍스트(여기선 단순 에코 텍스트)
        return {"text": f"논증({len(prompt)})"}

    monkeypatch.setattr(SeniorDebateInterpreter, "_invoke", fake_invoke)
    r = await generate_senior_debate({"pro": "적합 입장", "con": "부적합 입장"}, use_llm=True)
    assert r is not None and r["pro"].startswith("논증") and r["con"].startswith("논증")


@pytest.mark.asyncio
async def test_debate_partial_failure_keeps_other_side(monkeypatch):
    async def half(self, prompt):  # noqa: ANN001, ARG001
        # '부적합'(con)만 빈결과 → con 생략. 'pro'/'con' 마커로 입장 구분(부분문자열 충돌 회피).
        return {} if "부적합" in prompt else {"text": "프로 논증"}

    monkeypatch.setattr(SeniorDebateInterpreter, "_invoke", half)
    r = await generate_senior_debate({"pro": "적합하다는 입장", "con": "부적합하다는 입장"}, use_llm=True)
    assert r == {"pro": "프로 논증"}  # con 빈결과는 생략(graceful)


@pytest.mark.asyncio
async def test_debate_both_fail_returns_none(monkeypatch):
    async def boom(self, prompt):  # noqa: ANN001, ARG001
        raise RuntimeError("LLM 다운")

    monkeypatch.setattr(SeniorDebateInterpreter, "_invoke", boom)
    assert await generate_senior_debate({"pro": "p", "con": "c"}, use_llm=True) is None


def test_narrator_single_path_contract():
    # 단일경유 메터링 계약 — name(귀속)·expected_keys·fallback·citation/면허 시스템프롬프트
    i = SeniorNarratorInterpreter()
    assert i.name == "senior_reasoning"
    assert i.expected_keys == ["narrative"] and i.fallback_key == "narrative"
    assert "만들지 마라" in i.system_prompt and "면허" in i.system_prompt


# ── 백로그①(2026-07-22): 절단신호(is_truncated) 기반 강등 회귀앵커 ──
# fallback_key="narrative"/"text"가 유일한 expected_key라 _invoke_or_empty(is_fallback_only)를
# 못 쓴다(정상 응답도 폴백과 동일 형태). 대신 BaseInterpreter._invoke가 매 호출 인스턴스에
# 남기는 last_truncated(최소 노출 속성)로만 강등 여부를 가른다 — parse_ok는 이 인터프리터엔
# 부적합(산문이 정상 출력이라 JSON 미준수=오탐)해서 의도적으로 게이트에서 제외했다.

@pytest.mark.asyncio
async def test_truncated_narrative_degrades_to_none(monkeypatch):
    async def truncated_invoke(self, prompt):  # noqa: ANN001, ARG001
        self.last_truncated = True  # max_tokens 캡 절단 시뮬레이션
        return {"narrative": "…에서 중간에 잘려나간 부분 JSON/텍스트 뭉치"}

    monkeypatch.setattr(SeniorNarratorInterpreter, "_invoke", truncated_invoke)
    # 절단된 원문이 narrative로 노출되지 않고 None(호출처 결정론 강등)으로 떨어져야 한다.
    assert await generate_senior_narrative("FinCoT 프롬프트", use_llm=True) is None


@pytest.mark.asyncio
async def test_non_json_prose_narrative_is_preserved(monkeypatch):
    """LLM이 JSON 지시(시스템프롬프트)를 어기고 순수 산문으로만 답해도 — 그 자체는 정상
    답변이다(narrative는 산문이 정상 출력). parse_ok=False(비JSON)만으로는 강등하지
    않고, 절단이 없으면 그대로 노출해야 한다(오탐 방지 회귀앵커)."""
    async def prose_invoke(self, prompt):  # noqa: ANN001, ARG001
        self.last_parse_ok = False  # JSON 형식 미준수(정상 산문 응답)
        self.last_truncated = False  # 절단 아님
        return {"narrative": "종합 판단: 조건부 Go. 핵심 리스크는 …"}

    monkeypatch.setattr(SeniorNarratorInterpreter, "_invoke", prose_invoke)
    r = await generate_senior_narrative("FinCoT 프롬프트", use_llm=True)
    assert r == "종합 판단: 조건부 Go. 핵심 리스크는 …"


@pytest.mark.asyncio
async def test_debate_truncated_side_degrades_like_failure(monkeypatch):
    """pro/con 중 한쪽만 절단되면 그 쪽만 생략하고 나머지는 유지(기존 partial-failure
    graceful 패턴과 동일 처리)."""
    async def half(self, prompt):  # noqa: ANN001, ARG001
        if "부적합" in prompt:
            self.last_truncated = True
            return {"text": "절단된 con 논증 뭉치…"}
        return {"text": "프로 논증"}

    monkeypatch.setattr(SeniorDebateInterpreter, "_invoke", half)
    r = await generate_senior_debate({"pro": "적합하다는 입장", "con": "부적합하다는 입장"}, use_llm=True)
    assert r == {"pro": "프로 논증"}
