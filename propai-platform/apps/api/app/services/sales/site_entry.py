"""현장 진입 **판정** — 라우터가 아니라 여기 산다.

## 왜 서비스 층인가 (2026-09-09)

이 저장소는 개발 환경 python 3.10 에서 `app/crud/base.py` 의 PEP 695 문법
(`class CRUDBase[M]:`)을 **파싱조차 못 한다**. 그래서 `endpoints/sales/site_auth.py` 를
임포트하는 테스트는 **CI(3.12)에서 처음 실행**된다.

★그 부채가 실제로 물었다(같은 날): 진입 락 2건이 로컬에서 `skip` 됐고,
CI 에서 `AttributeError: 'tuple' object has no attribute 'password_hash'` 로 빨개졌다 —
**내 스텁이 SQLAlchemy Row 를 튜플로 흉내 냈기** 때문이다.
**skip 된 락은 「통과」가 아니라 「아직 모른다」다.**

⇒ 판정을 **의존 없는 자리**로 내린다. 여기는 표준 라이브러리 + bcrypt 만 쓴다 —
  어디서든 임포트되고, 그래서 **어디서든 태워진다.**
"""

from __future__ import annotations

import bcrypt


def verify_site_secret(stored_hash: str | None, supplied: str | None) -> str:
    """현장 진입을 무엇으로 허용할지 — **한 값 흐름**으로 판정한다.

    반환:
      · `"membership"` — 현장에 2차비밀번호가 **설정돼 있지 않다**. 승인된 멤버십이 곧 인증이다.
      · `"password"`   — 설정돼 있고 **일치**한다.
      · `"reject"`     — 설정돼 있는데 **불일치**한다(호출부가 401 + 실패 카운트).

    ★**멤버십 판정은 여기 없다.** 호출부가 이미 «이 현장의 멤버인가» 를 물어 403 을 내고 온다 —
      이 함수는 **그 위에 비번을 더 요구할지**만 정한다. 둘을 섞으면 «비번을 없앴다» 가
      «아무나 들어온다» 와 구별되지 않는다.

    ★깨진 해시(`bcrypt` 가 파싱 못 하는 값)는 **거부**한다(fail-closed).
      «해시가 이상하니 통과» 는 그 자체가 우회로다.
    """
    if not stored_hash:
        return "membership"
    try:
        ok = bcrypt.checkpw((supplied or "").encode(), stored_hash.encode())
    except (ValueError, TypeError):
        return "reject"
    return "password" if ok else "reject"
