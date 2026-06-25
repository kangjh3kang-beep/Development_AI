"""회상(MemoryHub) 결과 → LLM 프롬프트용 텍스트 블록 공용 포맷터(표준 계약·전역전파 SSOT).

회상 과거경험을 prior_context/컨텍스트 뒤에 덧붙일 블록으로 정규화한다. ★score 안전화:
score가 None/비수치/bool 이면 '(Score: …)' 생략(`:.2f` 포맷오류·TypeError 방지). 헤더는 호출처가
지정(specialist=영문·expert_panel=국문 등). 한 곳(이 헬퍼)을 고치면 모든 회상 소비처가 따라온다.
"""
from __future__ import annotations

from typing import Any


def format_recall_block(rag_memories: list[dict[str, Any]], *, header: str) -> str:
    """회상 목록 → 헤더 + 'summary (Score: x.xx)' 라인 블록. 빈 목록은 빈 문자열(prompt 오염 없음).

    score가 유한 수치(bool 제외)일 때만 점수 표기 — None/문자열/누락이어도 안전(KeyError·포맷오류 방지).
    """
    if not rag_memories:
        return ""
    lines = ["", "", header]
    for rm in rag_memories:
        score = rm.get("score")
        score_s = (
            f" (Score: {score:.2f})"
            if isinstance(score, (int, float)) and not isinstance(score, bool)
            else ""
        )
        lines.append(f"- {rm.get('summary', '')}{score_s}")
    return "\n".join(lines)
