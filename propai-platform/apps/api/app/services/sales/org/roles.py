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
SUPERADMIN_ROLES = frozenset(
    {"superadmin", "super_admin", "admin", "owner", "총괄관리자", "platform_admin"})

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
