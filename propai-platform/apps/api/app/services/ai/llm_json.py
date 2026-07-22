"""LLM 텍스트 응답 → JSON 관대 파싱 공용 헬퍼(파서 SSOT).

배경(2026-07-22 라이브 실측): 규제분석 등 '직접 호출' 서비스 11곳이 "선행 코드펜스만
벗기는" 자체 파서를 복제해 썼다. 모델이 프리앰블("다음은 JSON입니다:")이나 후행 설명을
붙이면 json.loads가 실패해 "AI 해석 일시 미제공" 폴백으로 강등되는 간헐 결함 클래스.
BaseInterpreter._parse_response에는 이미 중괄호 경계 추출 폴백이 있어 같은 응답에도
살아남는 격차가 있었다 — 그 관대 추출 로직을 이 한 곳으로 일원화한다(한 곳 수정=전역 전파).
"""

import json
from typing import Any


def coerce_llm_text(raw: Any) -> str:
    """LLM 응답 content를 str로 정규화. langchain 콘텐츠 블록(list)도 텍스트로 합친다."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        # Anthropic 콘텐츠 블록: [{'type': 'text', 'text': ...}, ...] 또는 str 조각들
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(raw)


def extract_json_text(raw: Any) -> str:
    """코드펜스를 벗긴 JSON 후보 텍스트를 반환한다(파싱은 하지 않음).

    선행 프리앰블 뒤의 펜스도 처리한다 — startswith("```") 검사만 하던 기존 복제
    파서들이 프리앰블에 무력했던 결함의 교정 지점.
    """
    text = coerce_llm_text(raw).strip()
    if "```" in text:
        seg = text.split("```")
        if len(seg) >= 2:
            inner = seg[1]
            if inner[:4].lower() == "json":
                inner = inner[4:]
            if inner.strip():
                return inner.strip()
    return text


def parse_llm_json(raw: Any) -> Any:
    """LLM 텍스트에서 JSON 값(dict/list)을 관대하게 추출·파싱한다.

    1) 펜스 내부 추출 후 json.loads
    2) 실패 시 최초 여는 괄호({/[ 중 먼저 나오는 쪽)부터 최후 닫는 괄호까지 재시도
    최종 실패면 json.JSONDecodeError를 그대로 던진다(호출처의 폴백 분류가 'parse'로 잡게).
    """
    text = extract_json_text(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        first_obj = text.find("{")
        first_arr = text.find("[")
        # 먼저 등장하는 괄호 종류를 우선 시도 — 리스트 응답에서 내부 dict만 건져
        # 리스트를 잃는 오추출 방지.
        if first_obj != -1 and (first_arr == -1 or first_obj < first_arr):
            pairs = [("{", "}"), ("[", "]")]
        elif first_arr != -1:
            pairs = [("[", "]"), ("{", "}")]
        else:
            raise
        for open_ch, close_ch in pairs:
            start = text.find(open_ch)
            end = text.rfind(close_ch)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    continue
        raise
