"""분양 조직 **역할·서열 상수의 SSOT** — 의존이 없는 최하위 모듈.

## 왜 여기인가 (2026-09-09)

`deps_sales.py` 가 스스로 *"sales 인증의 최하위 모듈이므로 여기서 1회 정의하고 상위 모듈은
import 해 재사용한다"* 고 선언하고 이 상수들을 갖고 있었다. **선언은 옳았지만 자리가 아니었다** —
그 모듈은 FastAPI `Depends` 와 인증 서비스를 끌고 오므로, 서비스 층이 상수 하나를 쓰려고
임포트하면 **앱 전체가 딸려 온다.**

실측(2026-09-09): 서비스 층에서 `from app.api.deps_sales import _SUPERADMIN_ROLES` 를 했더니
`deps_sales → app.api.deps → auth_service → app.models → mass_template` 체인이 끌려와
개발 환경(python 3.10)에서 **테스트가 임포트 단계에서 죽었다**. 상수를 공유하려다
**태울 수 없는 자리로** 밀려난 것이다.

★PR #1021 에서 `_ORG_RANK` 에 정확히 같은 처방을 썼다: **SSOT 는 아래로 내린다.**
  그래야 위쪽이 임포트하는 방향이 되어 순환이 없고, 아래쪽은 가벼운 채로 남는다.

여기에는 **표준 라이브러리 외 의존이 없다.** 어디서든 임포트해도 아무것도 안 딸려 온다.
"""

from __future__ import annotations

# 플랫폼 등급 역할 — 현장 소속과 무관하게 관리자로 인정한다.
# ★한국어 토큰이 실재한다(라이브 데이터). 목록에서 빠뜨리면 그 계정은 «전 현장을 보는데
#   아무 것도 승인 못 하는» 상태가 된다 — 실제로 그 결함을 냈다.
#
# ★★**가입 기본값(`admin`·`owner`)은 여기 담지 않는다**(#1034 · 2026-09-12 사용자 결정).
#   `POST /register`(`apps/api/routers/auth.py:347`)가 **모든 가입자**에게
#   `role=UserRole.ADMIN.value`("admin") 를 준다 — 독스트링 그대로 *"Create a **tenant**
#   admin account"*. 즉 `admin`·`owner` 는 **「내 테넌트의 관리자」**라는 **테넌트 스코프 라벨**이다.
#   그런데 이 집합은 **플랫폼 스코프**다 — `join.resolve_approver_node` 가 이 집합에 들면
#   **테넌트 검사 없이** `return True, None` 을 낸다. 두 스코프가 같은 문자열을 공유하면
#   ***가입한 누구나 「모든 테넌트의 모든 현장」의 승인자***가 된다. 승인은 조직도에 MEMBER
#   노드를 **쓰고**, 그 노드가 곧 `enter_site` 의 게이트다 — 읽기 노출이 아니라 **권한 상승**이다.
#   ★실측(2026-09-12 라이브·읽기전용): 사용자 16명 중 **role=admin 이 14명**.
#   ⇒ 플랫폼 판별자는 `tier == 'super_admin'` 이다(`billing_service.is_super_admin` · 8파일이 그 축을 쓴다).
#     **이 집합에 `admin`·`owner` 를 다시 넣지 마라.** 넣으면
#     `tests/test_sales_role_gate_tenant_scope.py` 가 빨개진다(그게 유일한 기계 잠금이다).
SUPERADMIN_ROLES = frozenset(
    {"superadmin", "super_admin", "총괄관리자", "platform_admin"})

# 시행사 계열 — **자기 테넌트 현장에 한해** 운영자로 인정한다(쓰기 경로에서 특히).
DEVELOPER_ROLES = frozenset({"developer", "시행사", "dev"})

# 한 사용자가 같은 현장에 **복수의 살아있는 조직노드**를 가질 수 있다
# (`sales_org_nodes` 에 `(site_id, user_id)` UNIQUE 가 없다).
# 그때 «상위 권한» 노드를 **결정적으로** 고르기 위한 우선순위(작을수록 상위).
NODE_TYPE_PRIORITY = {
    "AGENCY": 0,
    "SUBAGENCY": 1,
    "GM_DIRECTOR": 2,
    "DIRECTOR": 3,
    "TEAM_LEADER": 4,
    "MEMBER": 5,
}


def node_priority(node_type: str) -> int:
    """조직노드 권한 우선순위(작을수록 상위). 미등록 타입은 **가장 낮은** 우선순위로."""
    return NODE_TYPE_PRIORITY.get(node_type, len(NODE_TYPE_PRIORITY))
