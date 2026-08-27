"""법제처 DRF 오류 봉투 판별 — **오류가 HTTP 200 으로 온다.**

## 왜 이 모듈이 있나 (2026-08-27 라이브 실측)

법제처 DRF(`lawSearch.do`/`lawService.do`)는 인증 실패를 **정상 응답처럼** 돌려준다:

    HTTP 200 · Content-Type: application/json;charset=UTF-8
    {
        "result" : "사용자 정보 검증에 실패하였습니다.",
        "msg" : "OPEN API 호출 시 사용자 검증을 위하여 정확한 서버장비의 IP주소 및 도메인주소를 등록해 주세요."
    }

★**대조군으로 원인을 갈랐다** — `.env` 의 실제 키와 **일부러 틀린 키**가 **바이트 동일한 오류**를
  냈다. 즉 이것은 *키가 틀렸다*가 아니라 **호출 IP 가 등록되지 않았다**는 뜻이다
  (법제처 프로비저닝 2관문: ①키 발급 ②**서버 IP·도메인 등록**).

## 이 봉투가 실제로 무엇을 망가뜨렸나 (두 소비처 모두 **거짓을 단정**했다)

| 소비처 | 종전 결과 |
|---|---|
| `gosi_search_service.search_admrule` | 루트키 매칭 실패 → `results=[]` → **`available=True`** 반환 → `basic_building_cost.detect_gosi_update` 가 **`checked=True, changed=False`**(= *"확인했고 고시 안 바뀜"*) |
| `regulation_monitor.check_law_updates` | `raise_for_status()` **통과**(200) → `법령` 키 없음 → `공포일자=""` → `recent=False` → **"변경 없음"**. `failures=0` 이라 *"전건 실패 시 RuntimeError"* 가드가 **발화하지 않는다** |

★**둘째가 특히 아프다** — 그 함수는 주석에 *"실패 표면화(정직·무음0) … 빈 `[]`(=변경없음 확인)와
  '감지 불가'(키 무효·네트워크 장애)를 **구분**한다"* 고 **명시**하고, 무효키를 **`非200(403)`** 이라
  적었다. **법제처는 무효키에 200 을 준다.** 모듈이 자기 근거로 적어 둔 전제가 틀렸고,
  그래서 **자기가 막겠다고 선언한 바로 그 위장**에 뚫렸다.

`raise_for_status()` 는 이 봉투를 **원리적으로 못 잡는다.** 그래서 판별을 한 자리에 둔다.
"""

from __future__ import annotations

from typing import Any

__all__ = ["DRF_ERROR_KEYS", "MolegDrfError", "drf_error_reason", "raise_if_drf_error"]

#: 오류 봉투의 표식 — 법제처는 실패 시 이 두 키만 담은 얕은 dict 를 준다.
#: ★**`result` 하나로 판정하지 않는다** — 정상 응답에도 `result` 라는 이름이 쓰일 수 있다.
#:   *"정상 루트키가 하나도 없고"* + *"오류 키가 있다"* 를 **함께** 본다.
DRF_ERROR_KEYS: tuple[str, ...] = ("result", "msg")

#: 정상 응답의 루트키(알려진 것). 이 중 하나라도 있으면 오류 봉투가 아니다.
_OK_ROOT_KEYS: frozenset[str] = frozenset({
    "AdmRulSearch", "admRulSearch", "admrulSearch", "LawSearch", "lawSearch",
    "AdmRulService", "admrulService", "LawService", "법령", "행정규칙",
    "OrdinSearch", "ordinSearch", "OrdinService",
})


class MolegDrfError(RuntimeError):
    """법제처 DRF 가 **200 으로 돌려준 오류**.

    ★일반 예외와 **다른 타입**이어야 한다 — 호출측이 *"조회 실패"* 와 *"결과 없음"* 을
      구분해서 다룰 수 있어야 하고, 뭉치면 다시 침묵이 성공으로 읽힌다.
    """


def drf_error_reason(payload: Any) -> str | None:
    """오류 봉투면 **사람이 읽을 사유**를, 아니면 `None`.

    ★`None` 은 *"오류가 아니다"* 이지 *"성공했다"* 가 아니다 — 결과가 0건인지는 호출측이 따로 본다.
    """
    if not isinstance(payload, dict):
        return None
    if any(k in payload for k in _OK_ROOT_KEYS):
        return None
    if not any(k in payload for k in DRF_ERROR_KEYS):
        return None
    result = str(payload.get("result") or "").strip()
    msg = str(payload.get("msg") or "").strip()
    if not result and not msg:
        return None
    return " / ".join(p for p in (result, msg) if p)


def raise_if_drf_error(payload: Any) -> None:
    """오류 봉투면 `MolegDrfError` 로 **시끄럽게** 죽는다(무음 0건 금지)."""
    reason = drf_error_reason(payload)
    if reason is not None:
        raise MolegDrfError(reason)
