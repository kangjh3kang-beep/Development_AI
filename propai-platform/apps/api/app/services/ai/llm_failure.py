"""LLM 폴백을 **정직하게** 표기하는 공용 헬퍼.

## 왜 필요한가 (2026-08-21 실측)

종합 부지분석 화면이 *"AI 종합은 일시적으로 미제공"* 이라고 말하고 있었다.
**일시적이 아니었다.** 라이브 로그에는 두 개의 결정론적 영구 실패가 있었다.

  · `claude-opus-4-8`(사용자가 고른 **프리미엄** 모델)이 `temperature` 를 400 으로 거부
  · `parse_llm_json` 이 배열을 줬는데 호출부가 dict 를 가정 → `list indices ... not str`

둘 다 **매번** 실패한다. 그런데 화면이 "일시적"이라고 단정해 **아무도 이상하게 여기지
않았다**. 조용한 폴백이 장애를 숨긴 것이지, 장애가 조용했던 게 아니다.

## 규칙

1. **"일시적"이라고 단정하지 않는다.** 재시도로 풀릴지 우리는 모른다.
2. **사유를 함께 싣는다**(`failure_reason`). 화면·로그·원장 어디서든 원인이 보여야 한다.
3. **규칙기반 결과가 있으면 그것으로 답한다고 밝힌다** — 사용자는 무엇을 보고 있는지 알아야 한다.
"""

from __future__ import annotations

from typing import Any

# 사유 문자열 상한 — 로그·응답에 실릴 수 있으므로 과도한 길이를 막는다.
_REASON_MAX = 160


def failure_reason(exc: BaseException) -> str:
    """예외를 `타입: 메시지` 한 줄로 요약한다(길이 제한)."""
    return f"{type(exc).__name__}: {str(exc)[:_REASON_MAX]}"


def honest_llm_fallback(
    exc: BaseException,
    *,
    what: str,
    rule_based: bool = True,
) -> dict[str, Any]:
    """LLM 실패 시 **정직한** 폴백 페이로드를 만든다.

    Args:
        exc: 실제로 발생한 예외.
        what: 무엇을 생성하지 못했는지(예: "AI 종합", "AI 권리분석").
        rule_based: 규칙기반 결과로 대체 제공하는지 여부.

    Returns:
        `summary` + `failure_reason` 을 담은 dict. 호출부가 자기 스키마에 병합한다.
    """
    tail = " — 아래 규칙기반 결과로 답합니다." if rule_based else ""
    return {
        "summary": f"{what}을(를) 생성하지 못했습니다{tail}",
        "failure_reason": failure_reason(exc),
    }
