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


# ★진입 판정의 **전체** 결과. 라우터는 이것을 HTTP 로 옮기기만 한다.
#   `forbidden` 을 여기 두는 것이 핵심이다 — 종전엔 «멤버 아님» 이 라우터 안 `if not role:`
#   **한 줄**에만 살아서, `if role is None:` 로 바꿔도(비멤버는 `""` 를 받으므로 **영원히 거짓**)
#   락 11건이 전부 초록이었다(`::VERDICT=SURVIVED`). 그 변이는 **인증된 아무나 아무 현장에**
#   진입시킨다. 판정이 값이 되어야 태울 수 있다.
ENTRY_OUTCOMES = ("membership", "password", "reject", "no_secret_supplied", "forbidden")


def resolve_entry(role: str | None, stored_hash: str | None, supplied: str | None) -> str:
    """현장 진입을 허용할지 — **하나의 값**으로 판정한다.

    | 반환 | 뜻 | 호출부 |
    |---|---|---|
    | `forbidden` | 이 현장의 **멤버가 아니다** | 403 |
    | `membership` | 비번 **미설정** — 승인된 멤버십이 곧 인증 | 토큰 발급 |
    | `password` | 비번 설정 + **일치** | 토큰 발급 |
    | `no_secret_supplied` | 비번 설정인데 **아무것도 안 보냈다** | 400 — ★**실패 카운트 금지** |
    | `reject` | 비번 설정 + **불일치** | 401 + 실패 카운트 |

    ## ★`no_secret_supplied` 를 `reject` 와 가르는 이유 (2026-09-09 · 리뷰 C1)

    프론트 모달이 열릴 때 «비번 없이 먼저 시도» 하도록 만들었는데, 빈 비번이 **실패로 세어졌다**.
    그리고 `sales_site_login_attempts` 는 **시간으로 감쇠하지 않는다**(지우는 곳은 성공 진입·
    membership 진입·관리자 비번 변경 **셋뿐**). 즉 «15분 안에 5회» 가 아니라
    **«성공하기 전까지 누적 5회»** 다.

    ⇒ 모달을 다섯 번 여는 것만으로(비번을 몰라 닫았다 다시 여는 것만으로) 계정이 잠기고,
      실패는 **설계상 조용해서** 사용자는 아무것도 못 본다. 하필 «2차 요소를 조용히 걷어내지
      않으려고 남긴» 비번 설정 현장을 정확히 때린다. **내가 이번 라운드에 만든 결함이다.**

    ★**「안 보냈다」와 「틀렸다」는 다른 사건이다.** 같은 값으로 뭉개면 전자가 후자의 예산을 쓴다.
    """
    if not role:
        return "forbidden"
    if not stored_hash:
        return "membership"
    if supplied is None or supplied == "":
        return "no_secret_supplied"
    return "password" if verify_site_secret(stored_hash, supplied) == "password" else "reject"


#: 멤버십이 **어떻게** 생겼는지 — 응답·감사에 싣는 값.
MEMBERSHIP_KINDS = ("membership", "platform_fallback")


def membership_kind(org_path: str | None) -> str:
    """노드 기반 승인과 **플랫폼 역할 폴백**을 가른다(2026-09-12 · 리뷰 M6).

    ★**이 PR 의 주석이 거짓이었다.** *"멤버십은 관리자·상위 레벨이 승인해야 생긴다
      (`sales_org_nodes`)"* 라고 단정했는데, `resolve_site_membership` 은 노드가 **0건**일 때
      플랫폼 역할만 보고 `("", "SUPERADMIN")` / `("", "DEVELOPER")` 를 돌려준다.
      그 경로에는 **승인이 없다.** 그런데 라우터가 둘을 똑같이 `auth="membership"` 으로
      기록해, 감사 로그에서 «승인받은 사람» 과 «폴백으로 들어온 사람» 이 **구별되지 않았다.**

    ★가르는 근거는 `org_path` 다 — 노드 기반은 ltree 경로를 갖고, 폴백은 **빈 문자열**이다
      (`deps_sales.resolve_site_membership` 의 두 반환 형태). 역할 이름으로 가르지 않는다:
      역할은 노드 타입과 플랫폼 역할이 같은 문자열 공간을 쓴다.

    ★**선재 결함을 여기서 고치지 않는다**(별건). 저장소는 *"가입 시 모든 사용자가 자기
      테넌트의 role='admin' 이 되므로 role 게이트는 누출"* 을 **자기 언어로 6곳에** 적어 두고
      `tier` 로 판별한다(`routers/growth.py:166` · `routers/billing.py` ·
      `routers/admin_secrets.py:51` · `routers/admin_sales_rls.py:29` 등).
      그런데 `deps_sales._SUPERADMIN_ROLES` 는 `"admin"` 을 담은 **role 게이트**다.
      ⇒ 이 함수는 그 경로를 **보이게** 만든다. 없애는 것은 사용자 결정이 필요한 별건이다.
    """
    return "membership" if (org_path or "") else "platform_fallback"
