"""법제처 DRF 응답 검증 — **오류가 HTTP 200 으로 온다.**

## 왜 이 모듈이 있나 (2026-08-27 라이브 실측)

법제처 DRF(`lawSearch.do`/`lawService.do`)는 실패를 **정상 응답처럼** 돌려준다.
라이브에서 **세 계열**을 확인했다(모두 HTTP 200 · `application/json`):

    ① 키/IP 미검증  {"result":"사용자 정보 검증에 실패하였습니다.","msg":"…IP주소 및 도메인주소를 등록…"}
    ② 필수인자 누락  {"result":"필수입력요소 검증에 실패하였습니다.","msg":…}
    ③ 대상 없음      {"Law":"일치하는 법령이 없습니다.  법령명을 확인하여 주십시오."}

★**대조군으로 ①의 원인을 갈랐다** — `.env` 의 실제 키와 **일부러 틀린 키**가 **바이트 동일한**
  오류를 냈다. 즉 *키가 틀렸다*가 아니라 **호출 IP 가 미등록**이다(프로비저닝 2관문 중 2번째).

## ★왜 「오류 목록」이 아니라 **「기대 루트키」**로 판정하나

첫 판은 오류 봉투를 **열거**했다(`result`/`msg` 가 있고 정상 루트키가 없으면 오류).
독립 리뷰가 그것을 무너뜨렸다:

- **③ 계열을 못 잡았다** — `{"Law": "…없습니다"}` 에는 `result` 도 `msg` 도 없다.
  그래서 `regulation_monitor` 가 **60건 전건 조회 불가인데 조용히 「변경 없음」**을 돌려줬다.
- **정상 루트키 목록이 썩어도 아무도 안 죽었다** — 목록에서 `법령` 을 지워도 테스트 전부 초록.
  그 목록은 *"코드에서 파생"* 이라고 적혀 있었지만 실제로는 **손 목록**이었고,
  코드가 방어하던 루트레벨 폴백(`data["admrul"]`)은 **빠져 있었으며** 쓰이지 않는 키 7개가 **잉여**였다.

> **부정 목록은 새 오류 형태가 생길 때마다 조용히 뚫린다.**
> 그래서 뒤집는다 — **호출부가 「무엇을 기대하는지」 선언하고, 그것이 없으면 실패다.**
> 새 오류 형태가 무엇이든, 기대한 것이 없으면 잡힌다.

★`expect` 는 **호출부가 실제로 파싱하는 키**여야 한다. 어긋나면 `tests/` 의 계약 테스트가 잡는다
(선언과 소비를 같은 커밋에서 결속 — 선언의 존재는 그 선언이 옳은지 말해 주지 않는다).
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "MolegDrfError",
    "drf_failure_reason",
    "moleg_oc_key",
    "raise_unless_expected",
    "raise_unless_expected_xml",
    "xml_failure_reason",
]


def moleg_oc_key() -> str:
    """법제처 DRF 인증키(OC)를 **호출 시점에** 읽는다.

    ## ★왜 `settings.MOLEG_API_KEY` 를 직접 읽으면 안 되나 (2026-09-02 · 적대 리뷰)

    관리자 화면의 시크릿 저장(`PUT /admin/secrets/{name}`)은 `os.environ[name] = value`
    **만** 한다. 그런데 `settings` 는 `app/core/config.py` 의 **모듈 싱글턴**이고
    `get_settings()` 는 `@lru_cache` 라 **재동기화 경로가 0건**이다(전수 조회로 확인).

    → 소비처가 `settings` 를 직접 읽으면 운영자가 화면에서 키를 바꿔도
      **「저장됨」 초록만 뜨고 실제로는 아무것도 안 바뀐다** — 즉 **작동하지 않는 조작 수단**이다.
      저장소가 이미 두 곳에 그 갭을 적어 뒀다:

        app/core/observability.py  *"load_into_env() 가 os.environ 에 올리므로
                                     **settings 에는 반영되지 않는다**"*
        tests/test_base_interpreter_fewshot.py  *"관리자 시크릿으로 켜도 **재시작 전 무효**"*

    ★그래서 **`os.environ` 을 먼저** 본다(런타임 갱신분) → 없으면 부팅 설정.
      `base_interpreter._fewshot_enabled` 가 같은 이유로 같은 순서를 쓴다(저장소 선례).
    ★**빈 문자열도 「없음」으로 본다** — `os.environ` 의 빈 값이 부팅 설정을 가리지 않게.
    """
    import os

    from app.core.config import settings

    return (os.getenv("MOLEG_API_KEY") or "").strip() or (
        getattr(settings, "MOLEG_API_KEY", "") or ""
    ).strip()

#: 법제처가 사유를 싣는 관용 키(계열 ①②). 없으면 값이 문자열인 아무 키나 사유로 쓴다(계열 ③).
_REASON_KEYS: tuple[str, ...] = ("result", "msg")


class MolegDrfError(RuntimeError):
    """법제처 DRF 가 **200 으로 돌려준 실패**.

    ★일반 예외와 **다른 타입**이어야 한다 — 호출측이 *"조회 실패"* 와 *"결과 0건"* 을
      구분해 다뤄야 하고, 뭉치면 다시 침묵이 성공으로 읽힌다.
    """


def drf_failure_reason(payload: Any, *, expect: tuple[str, ...]) -> str | None:
    """`expect` 중 **하나도 없으면** 사람이 읽을 실패 사유를, 있으면 `None`.

    Args:
        payload: `response.json()` 결과.
        expect: 호출부가 **실제로 파싱하는** 루트키들. 하나라도 있으면 정상으로 본다.

    ★`None` 은 *"실패가 아니다"* 이지 *"결과가 있다"* 가 아니다 —
      **진짜 0건**(`{"AdmRulSearch": {"totalCnt": "0"}}`)은 정상이고, 그 판정은 호출부 몫이다.
    """
    if not isinstance(payload, dict):
        return f"응답이 JSON 객체가 아니다({type(payload).__name__})"
    if any(k in payload for k in expect):
        return None
    parts: list[str] = []
    for k in _REASON_KEYS:
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    if not parts:
        # 계열 ③ — 사유가 **루트키 자리에 문자열로** 온다(`{"Law": "일치하는 …없습니다"}`).
        for k, v in payload.items():
            if isinstance(v, str) and v.strip():
                parts.append(f"{k}: {v.strip()}")
    if parts:
        return " / ".join(parts)
    return f"기대 루트키 {list(expect)} 없음 (수신 키: {sorted(map(str, payload))[:6]})"


def xml_failure_reason(text: str, *, expect: tuple[str, ...]) -> str | None:
    """XML 응답판 — `expect` 루트태그가 **하나도 없으면** 실패 사유를, 있으면 `None`.

    ★왜 형제가 필요한가(2026-08-28 실측): 위 JSON 판은 `isinstance(payload, dict)` 라
    **JSON 전용**인데, 조례 조회(`ordinance_service`)는 `type=XML` 로 부른다. 그래서
    형제 둘(`regulation_monitor`·`gosi_search_service`)이 200-실패를 잡는 동안
    **조례 경로만 무방비**였고, 광범위한 `except Exception: return None` 이 그것을 삼켜
    화면에는 *"조례를 확인하지 못해 법정상한 잠정 적용"* 으로 나갔다(= 낙관 방향 폴백).

    법제처 XML 실패 봉투 실측:
        <Response><result>사용자 정보 검증에 실패하였습니다.</result><msg>…</msg></Response>
    """
    if not isinstance(text, str) or not text.strip():
        return "응답 본문이 비어 있다"
    if any(f"<{k}" in text for k in expect):
        return None
    parts: list[str] = []
    # ★형제(JSON 판)의 `_REASON_KEYS` 에서 **파생**시킨다. 손으로 나열하면 두 판이 갈리고,
    #   이 저장소의 교훈대로 **목록이 곧 상한**이 된다(독립 리뷰 지적).
    for tag in (*_REASON_KEYS, "resultMsg"):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
        if m and m.group(1).strip():
            parts.append(m.group(1).strip())
    if parts:
        return " / ".join(parts)
    return f"기대 루트태그 {list(expect)} 없음 (본문 앞 120자: {text.strip()[:120]!r})"


def raise_unless_expected_xml(text: str, *, expect: tuple[str, ...]) -> None:
    """XML 응답에 `expect` 루트태그가 없으면 `MolegDrfError` 로 **시끄럽게** 죽는다."""
    reason = xml_failure_reason(text, expect=expect)
    if reason is not None:
        raise MolegDrfError(reason)


def raise_unless_expected(payload: Any, *, expect: tuple[str, ...]) -> None:
    """`expect` 가 하나도 없으면 `MolegDrfError` 로 **시끄럽게** 죽는다(무음 0건 금지)."""
    reason = drf_failure_reason(payload, expect=expect)
    if reason is not None:
        raise MolegDrfError(reason)
