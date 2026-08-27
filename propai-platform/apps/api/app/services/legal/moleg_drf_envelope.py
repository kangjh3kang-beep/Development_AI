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

from typing import Any

__all__ = ["MolegDrfError", "drf_failure_reason", "raise_unless_expected"]

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


def raise_unless_expected(payload: Any, *, expect: tuple[str, ...]) -> None:
    """`expect` 가 하나도 없으면 `MolegDrfError` 로 **시끄럽게** 죽는다(무음 0건 금지)."""
    reason = drf_failure_reason(payload, expect=expect)
    if reason is not None:
        raise MolegDrfError(reason)
