"""절단을 **「빈 응답」으로 보고하던 것**을 잠근다 — 사유가 틀리면 조사자가 엉뚱한 곳을 본다.

## 무엇이 결함이었나 (사용자 신고 + 라이브 실측 2026-09-04)

특정 등기부만 **계속** 이렇게 실패했다:

    권리분석 실패 — JSONDecodeError: Expecting value: line 1 column 1 (char 0)

`char 0` 은 **「응답이 비었다」**처럼 읽힌다. 실제는 아니었다 — 라이브 로그의 `raw_head`:

    ```json\n{\n  "ownership": {\n    "current_owner": "조영섭(지분 1/2), ...

**응답은 왔고, 최대 길이에서 잘려 코드펜스가 안 닫힌 것**이다. 그러면
`parse_llm_json` 의 후보 중 **첫 번째(원문)** 가 ``` 로 시작해 언제나 `char 0` 을 내고,
`last_err = last_err or e` 가 **그 첫 오류를 유지**해 올라간다.

★그리고 `llm_json.is_truncated()` 는 **이미 있었고** 독스트링이
*"호출처는 이 판정으로 절단을 'parse'가 아닌 **별도 사유로 정직하게 분류해야 한다**"*
라고 **명시**하는데, 등기 서비스가 **안 썼다**(참조 0건).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.ai.llm_json import is_truncated, parse_llm_json

_SVC = (Path(__file__).resolve().parents[1]
        / "app" / "services" / "registry" / "registry_analysis_service.py")

# ★라이브에서 실제로 관측된 형태(절단 → 미종단 펜스). 지어내지 않고 `raw_head` 를 따랐다.
_TRUNCATED = (
    '```json\n'
    '{\n'
    '  "ownership": {\n'
    '    "current_owner": "조영섭(지분 1/2), 김순복(지분 1/2)",\n'
    '    "share": "각 1/2",\n'
    '    "owners": [\n'
    '      {\n'
    '        "name": "조영섭'
)


def test_절단된_응답은_절단을_말하는_오류를_낸다():
    """★핵심 — `char 0`(빈 응답처럼 읽힘)이 아니라 **절단**을 말해야 한다."""
    with pytest.raises(json.JSONDecodeError) as ei:
        parse_llm_json(_TRUNCATED)
    msg = str(ei.value)
    assert "line 1 column 1 (char 0)" not in msg, (
        f"절단인데 「빈 응답」처럼 보고한다: {msg}\n"
        "★첫 후보(원문)의 오류를 남기면 언제나 이 메시지가 된다")
    assert any(k in msg for k in ("Unterminated", "Expecting ','", "Expecting property")), (
        f"절단을 말하는 메시지가 아니다: {msg}")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('{"b": 2}', {"b": 2}),
        ('다음은 JSON입니다:\n```json\n{"c": 3}\n```\n이상입니다.', {"c": 3}),
        ('```\n{"d": 4}\n```', {"d": 4}),
    ],
)
def test_정상_응답은_종전과_같이_파싱된다(raw, expected):
    """★**두 번째 모집단** — 이것이 없으면 「전부 실패」가 만점이 된다."""
    assert parse_llm_json(raw) == expected


class _Resp:
    def __init__(self, stop: str | None):
        self.response_metadata = {"stop_reason": stop} if stop else {}


def test_is_truncated_는_두_모집단을_가른다():
    """절단 판정 자체가 살아 있는지 — 이것이 죽으면 아래 배선이 공허해진다."""
    assert is_truncated(_Resp("max_tokens")) is True
    assert is_truncated(_Resp("end_turn")) is False
    assert is_truncated(None) is False


def test_등기_서비스가_is_truncated_를_실제로_소비한다():
    """★**소비처 0** 을 잠근다 — 탐지기가 있는데 안 쓰던 것이 이 결함의 근본이었다.

    ★소스 검사인 이유: 이 경로는 실제 LLM 호출을 태워야 실행되는데, 그러면
      **유료 호출**이 된다(이 저장소의 「유료 산출물 규율」). 대신 **소비 여부**를 잠근다.
    """
    src = _SVC.read_text(encoding="utf-8")
    code = [ln for ln in src.splitlines()
            if not ln.lstrip().startswith("#") and "is_truncated" in ln]
    assert code, (
        "`registry_analysis_service` 가 `is_truncated` 를 **실행 줄에서** 쓰지 않는다 — "
        "탐지기가 있는데 안 쓰면 절단이 계속 「빈 응답」으로 보고된다")
    assert any("if " in ln and "is_truncated" in ln for ln in code), (
        f"임포트만 하고 **판정에 쓰지 않는다**(장식): {code}")


def test_절단_사유가_사용자_문구로_나온다():
    """사유 문자열이 **사람이 읽고 조치할 수 있는** 말이어야 한다."""
    src = _SVC.read_text(encoding="utf-8")
    assert "최대 길이에서 잘렸습니다" in src, (
        "절단 사유가 사용자 문구로 없다 — `JSONDecodeError` 원문만 보이면 "
        "「빈 응답」으로 오독된다")
    # ★분류는 바꾸지 않는다 — 절단도 결정론적이라 `parse` 가 옳다(재시도 판정 불변)
    assert "_classify_failure(e)" in src, (
        "failure_class 배선이 사라졌다 — 재시도 판정이 바뀌면 이 변경의 범위를 넘는다")
