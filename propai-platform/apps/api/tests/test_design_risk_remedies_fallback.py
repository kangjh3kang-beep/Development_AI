"""D3 generate_ai_remedies — _invoke_or_empty 전환 회귀앵커(백로그①, 2026-07-22).

배경: design_change_predictor._RemedyInterpreter는 fallback_key="priority_actions"이고
expected_keys 3개 중 하나다(narrative 계열과 달리 폴백-only 판정이 구조적으로 가능).
과거 interp._invoke(...)를 직접 호출해, JSON 파싱 완전 실패 폴백({priority_actions: 원문
텍스트[:500]})을 "부분 성공"으로 오인해 그대로 병합·반환했다(원문/절단 텍스트 노출).
_invoke_or_empty 전환 후엔 폴백-only 결과가 {}로 강등되고 `if result:`가 false가 되어
룰기반 fallback으로 안전하게 떨어져야 한다. 아래는 그 경로를 고정하는 회귀앵커다.
"""

from __future__ import annotations

import pytest

from app.services.ai.base_interpreter import BaseInterpreter
from app.services.design_risk.design_change_predictor import generate_ai_remedies

_PREDICTION = {
    "summary": {"high": 1, "warn": 0, "info": 0},
    "risks": [
        {
            "category": "법규초과",
            "item": "건폐율 초과",
            "severity": "high",
            "detail": "건폐율 법정 상한 초과",
        }
    ],
}
_ZONE_TYPE = "제2종일반주거지역"


@pytest.mark.asyncio
async def test_fallback_only_llm_result_degrades_to_rule_fallback(monkeypatch):
    """JSON 파싱 실패 폴백(fallback_key 하나만 채워짐)은 {}로 강등 → 룰기반 fallback 반환.

    과거 결함 재현 조건: raw 텍스트 뭉치(원문/절단)가 priority_actions 하나에만 담기고
    나머지 두 키는 없는 상태 — is_fallback_only가 True로 판정하는 정확한 형태.
    """
    async def fallback_only_invoke(self, prompt, **kwargs):  # noqa: ANN001, ARG001
        return {"priority_actions": "AI 응답 파싱 실패 원문 텍스트 뭉치가 여기 노출되면 결함"}

    monkeypatch.setattr(BaseInterpreter, "_invoke", fallback_only_invoke)
    result = await generate_ai_remedies(_PREDICTION, _ZONE_TYPE)

    # 원문 뭉치가 새어나가지 않고, 룰기반 fallback(고위험 항목 근거 텍스트)로 대체됐는지 확인.
    assert "AI 응답 파싱 실패 원문 텍스트 뭉치" not in result["priority_actions"]
    assert result["priority_actions"] == "착공 전 우선 조치: 건폐율 초과"
    assert "확정이 아닙니다" in result["expert_review_note"]


@pytest.mark.asyncio
async def test_full_llm_success_passes_through_unchanged(monkeypatch):
    """3개 키 모두 정상 채워진 성공 결과는 그대로 반환(전환이 정상 경로를 해치지 않음)."""
    ai_result = {
        "priority_actions": "AI 제안: 정북 후퇴선 재검토 우선",
        "savings_opportunity": "AI 제안: 설계변경비 약 8% 절감 가능",
        "expert_review_note": "AI 제안: 구조기술사 검토 권고",
    }

    async def full_success_invoke(self, prompt, **kwargs):  # noqa: ANN001, ARG001
        return dict(ai_result)

    monkeypatch.setattr(BaseInterpreter, "_invoke", full_success_invoke)
    result = await generate_ai_remedies(_PREDICTION, _ZONE_TYPE)

    assert result == ai_result


@pytest.mark.asyncio
async def test_partial_success_fills_missing_keys_from_rule_fallback(monkeypatch):
    """fallback_key 외 다른 키도 채워진 부분 성공은 폴백-only가 아니므로 보존하고,
    누락된 키만 룰기반 fallback으로 채운다(기존 setdefault 보호 로직 회귀 확인)."""
    async def partial_invoke(self, prompt, **kwargs):  # noqa: ANN001, ARG001
        return {
            "priority_actions": "AI 제안 우선조치",
            "savings_opportunity": "AI 제안 절감효과",
        }

    monkeypatch.setattr(BaseInterpreter, "_invoke", partial_invoke)
    result = await generate_ai_remedies(_PREDICTION, _ZONE_TYPE)

    assert result["priority_actions"] == "AI 제안 우선조치"
    assert result["savings_opportunity"] == "AI 제안 절감효과"
    assert "확정이 아닙니다" in result["expert_review_note"]  # 누락 키 → 룰기반으로 채움


@pytest.mark.asyncio
async def test_invoke_exception_returns_rule_fallback(monkeypatch):
    """LLM 호출 자체가 예외를 던져도(키 미설정 등) 룰기반 fallback으로 무중단 강등."""
    async def boom(self, prompt, **kwargs):  # noqa: ANN001, ARG001
        raise RuntimeError("LLM 키 미설정")

    monkeypatch.setattr(BaseInterpreter, "_invoke", boom)
    result = await generate_ai_remedies(_PREDICTION, _ZONE_TYPE)

    assert result["priority_actions"] == "착공 전 우선 조치: 건폐율 초과"
