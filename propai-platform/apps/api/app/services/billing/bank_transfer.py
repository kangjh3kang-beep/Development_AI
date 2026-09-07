"""무통장입금(계좌이체) 설정 — **사용자가 실제로 돈을 보내는 주소**를 다룬다.

## 왜 이 모듈이 조심스러운가

토스는 우리가 틀리면 **거절**한다(`INVALID_API_KEY`). 무통장입금은 **거절해 줄 상대가 없다.**
계좌번호를 한 자리 틀리게 안내하면 사용자는 **남의 계좌로 송금**하고, 그것은
**되돌릴 수 없다.** 그래서 이 모듈의 규율은 하나다:

> **불완전하거나 형식이 이상하면 「안내하지 않는다」.**
> 부분 정보로 안내하는 것보다 *"아직 준비되지 않았습니다"* 가 낫다.

## 왜 값을 소스에 박지 않나

계좌번호와 **예금주 성명**은 개인정보다. 소스에 넣으면 **git 이력에 영구히 남아**
사실상 지울 수 없다(저장소가 private 이어도 협업자·미래 공개 시 노출). 그래서
`secret_store` 금고를 경유한다 — 토스 클라이언트 키와 **같은 통로**이고,
관리자 화면이 그룹별로 **자동 렌더**하므로 새 UI 도 필요 없다.

★`secret: False` 다 — 계좌 안내는 **사용자에게 보여 줘야** 하므로 비밀이 아니다.
  다만 **로그인한 사용자에게만** 내보낸다(예금주 성명이 개인정보다).
"""

from __future__ import annotations

import os
import re
from typing import Any

#: 금고 항목 이름 — `secret_store.CATALOG` 와 **이 표가 유일한 선언처**다.
ENV_BANK_NAME = "BANK_TRANSFER_BANK_NAME"
ENV_ACCOUNT_NO = "BANK_TRANSFER_ACCOUNT_NO"
ENV_HOLDER = "BANK_TRANSFER_HOLDER"

#: 세 항목이 **모두** 있어야 켠다. 하나라도 비면 안내가 불완전해지고,
#: 불완전한 안내는 **엉뚱한 곳으로의 송금**을 만든다(되돌릴 수 없다).
REQUIRED_FIELDS: tuple[str, ...] = (ENV_BANK_NAME, ENV_ACCOUNT_NO, ENV_HOLDER)

#: 사람이 읽는 이름 — 관리자에게 **무엇이 비었는지** 말해 준다.
FIELD_LABELS: dict[str, str] = {
    ENV_BANK_NAME: "은행명",
    ENV_ACCOUNT_NO: "계좌번호",
    ENV_HOLDER: "예금주",
}

#: 계좌번호는 **숫자와 하이픈만**. 8~20자.
#: ★`re.ASCII` 를 붙인다 — 파이썬 `\d` 는 유니코드 십진수를 포함해서 **전각 숫자**가
#:   통과한다(이 저장소에 `^\d{19}$` 가 전각 19자를 통과시킨 실측이 있다).
#:   전각으로 안내하면 사용자가 복사해 붙여넣을 때 은행 앱이 거부하거나 **다른 계좌**가 된다.
_ACCOUNT_RE = re.compile(r"^[0-9][0-9-]{6,18}[0-9]$", re.ASCII)

#: 은행명·예금주 — 제어문자 금지, 길이 상한. 화면에 그대로 그리므로 위생이 필요하다.
_TEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,40}$")


def _env(name: str) -> str:
    """환경변수 읽기 — 앞뒤 공백·따옴표 제거.

    ★관리자가 금고에 붙여넣을 때 따옴표가 섞이는 사고가 이 저장소에 실재한다
      (`toss_payments._env` 가 같은 위생을 한다 — 형제와 같은 모양을 유지한다).
    """
    raw = (os.environ.get(name) or "").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        raw = raw[1:-1].strip()
    return raw


def _field_problem(name: str, value: str) -> str | None:
    """이 항목이 왜 못 쓰는지 — 쓸 수 있으면 `None`."""
    if not value:
        return "비어 있습니다"
    if name == ENV_ACCOUNT_NO:
        if not _ACCOUNT_RE.match(value):
            return "숫자와 하이픈만, 8~20자여야 합니다(전각 숫자·공백·문자 불가)"
        return None
    if not _TEXT_RE.match(value):
        return "1~40자여야 하고 제어문자를 포함할 수 없습니다"
    return None


def diagnosis() -> dict[str, Any]:
    """쓸 수 있는가 — 아니라면 **무엇이 왜** 안 되는지.

    ★`bool` 만 돌려주면 관리자가 못 고친다(진단 불가는 그 자체로 장애다).
    ★**값을 반환하지 않는다** — 이 함수는 관리자 진단용이고, 안내는 `account_info()` 다.
    """
    problems: list[str] = []
    for name in REQUIRED_FIELDS:
        p = _field_problem(name, _env(name))
        if p:
            problems.append(f"{FIELD_LABELS[name]}({name}): {p}")
    if not problems:
        return {"ok": True, "code": "ok", "severity": "info",
                "message": "무통장입금 계좌가 설정되어 있습니다.", "action": "", "problems": []}
    return {
        "ok": False,
        "code": "not_configured" if all(not _env(n) for n in REQUIRED_FIELDS) else "incomplete",
        "severity": "info" if all(not _env(n) for n in REQUIRED_FIELDS) else "error",
        "message": "무통장입금 계좌 정보가 완전하지 않아 화면에 노출하지 않습니다.",
        # ★부분 정보로 안내하면 **엉뚱한 곳으로 송금**된다 — 그래서 아예 끈다.
        "action": "관리자 > API 키 > 「무통장입금(계좌이체)」에서 은행명·계좌번호·예금주를 모두 채우세요.",
        "problems": problems,
    }


def is_configured() -> bool:
    """세 항목이 **모두** 있고 **모두 형식이 옳은가**."""
    return bool(diagnosis()["ok"])


def account_info() -> dict[str, str] | None:
    """사용자에게 보여 줄 입금 계좌. 쓸 수 없으면 **`None`**(부분 안내 금지).

    ★반환값은 **로그인한 사용자에게만** 나간다(예금주 성명이 개인정보다).
    ★금고의 다른 항목을 절대 싣지 않는다 — 이 셋만 명시적으로 읽는다.
    """
    if not is_configured():
        return None
    return {
        "bank_name": _env(ENV_BANK_NAME),
        "account_no": _env(ENV_ACCOUNT_NO),
        "holder": _env(ENV_HOLDER),
    }
