"""LLM 텍스트 응답 → JSON 관대 파싱 공용 헬퍼(파서 SSOT).

배경(2026-07-22 라이브 실측): 규제분석 등 '직접 호출' 서비스 11곳이 "선행 코드펜스만
벗기는" 자체 파서를 복제해 썼다. 모델이 프리앰블("다음은 JSON입니다:")이나 후행 설명을
붙이면 json.loads가 실패해 "AI 해석 일시 미제공" 폴백으로 강등되는 간헐 결함 클래스.
BaseInterpreter._parse_response에는 이미 중괄호 경계 추출 폴백이 있어 같은 응답에도
살아남는 격차가 있었다 — 그 관대 추출 로직을 이 한 곳으로 일원화한다(한 곳 수정=전역 전파).
"""

import json
from typing import Any


def is_truncated(response: Any) -> bool:
    """LLM 응답이 max_tokens 절단으로 끝났는지 판정(절단감지 SSOT).

    provider stop_reason(anthropic)/finish_reason(openai 등)이 max_tokens/length면
    출력이 중간에서 잘린 것 — 잘린 JSON은 어떤 관대 파서로도 복구할 수 없으므로,
    호출처는 이 판정으로 절단을 'parse'가 아닌 별도 사유로 정직하게 분류해야 한다.
    (2026-07-22 라이브 실측: 규제분석 output_tokens==캡(2500)인 호출만 정확히 파싱 실패
    — 파서 격차가 아니라 응답 절단이 잔여 근본원인이었다.)
    """
    meta = getattr(response, "response_metadata", None)
    if not isinstance(meta, dict):
        return False
    stop = str(meta.get("stop_reason") or meta.get("finish_reason") or "")
    return stop in ("max_tokens", "length")


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


def _boundary_candidates(text: str) -> list[str]:
    """최초 여는 괄호({/[ 중 먼저 등장하는 쪽)~최후 닫는 괄호 경계 후보들.

    리스트 응답에서 내부 dict만 건져 리스트를 잃는 오추출을 막기 위해, 먼저 등장하는
    괄호 종류를 우선한다.
    """
    first_obj = text.find("{")
    first_arr = text.find("[")
    if first_obj != -1 and (first_arr == -1 or first_obj < first_arr):
        pairs = [("{", "}"), ("[", "]")]
    elif first_arr != -1:
        pairs = [("[", "]"), ("{", "}")]
    else:
        return []
    out: list[str] = []
    for open_ch, close_ch in pairs:
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            out.append(text[start:end + 1])
    return out


def parse_llm_json(raw: Any) -> Any:
    """LLM 텍스트에서 JSON 값(dict/list)을 관대하게 추출·파싱한다.

    후보 순서(각 후보마다 직접 파싱→괄호 경계 복구를 시도, 전부 실패면 json.JSONDecodeError
    — 호출처 폴백 분류가 'parse'로 잡게):
    1) 원문 전체 — JSON 문자열 값 '안에' 펜스(```)가 든 무펜스 응답을 펜스 추출이
       망가뜨리지 않게 원문을 항상 1차 후보로 둔다.
    2) 최후 닫는 펜스 '뒤' 꼬리 — 모델이 예시를 펜스로 감싸고 실제 답을 뒤에 두는 패턴.
    3) 펜스 내부 블록들 '역순' — 예시(앞)보다 실제 답(뒤)이 이기게(R1 MINOR-1: 첫 펜스만
       집으면 예시 JSON을 오답 무음 반환).
    """
    original = coerce_llm_text(raw).strip()
    candidates = [original]
    if "```" in original:
        seg = original.split("```")
        # 균형 펜스(닫는 펜스 존재)일 때만 꼬리를 후보로 — 미종단 펜스의 꼬리는 내부와 동일.
        if len(seg) >= 3 and len(seg) % 2 == 1 and seg[-1].strip():
            candidates.append(seg[-1].strip())
        inner_blocks: list[str] = []
        for i in range(1, len(seg), 2):
            block = seg[i]
            if block[:4].lower() == "json":
                block = block[4:]
            if block.strip():
                inner_blocks.append(block.strip())
        candidates.extend(reversed(inner_blocks))
    last_err: json.JSONDecodeError | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError as e:
            last_err = last_err or e
        for bounded in _boundary_candidates(cand):
            try:
                return json.loads(bounded)
            except json.JSONDecodeError:
                continue
    raise last_err if last_err else json.JSONDecodeError("JSON 미발견", doc=original[:80], pos=0)
