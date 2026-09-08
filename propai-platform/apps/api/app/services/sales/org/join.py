"""현장 **등록신청 승인**의 판정 — 라우터가 아니라 여기 산다.

## 왜 서비스 층인가 (2026-09-09)

PR #1021 에서 정확히 같은 형태로 데였다: 담당 노드 검증을 라우터에 인라인으로 두었더니
**FastAPI 의존 때문에 아무도 그 함수를 부를 수 없었고**, 기계 변이가 그 블록의 조건을
지워도 전부 생존했다(락 0건). 처방은 «규칙을 서비스 층으로 내려라» 였다.

★그 처방을 **이 새 파이프라인에도 미리** 적용한다. 라우터에 두면 이 저장소의 개발 환경
  (python 3.10)에서 `app/crud/base.py` 의 PEP 695 문법(`class CRUDBase[M]:`) 때문에
  **임포트가 원리적으로 불가**해, 행위 락이 전부 «CI 에서 처음 실행되는 테스트» 가 된다.
  서비스 층은 sqlalchemy + 모델만 끌고 오므로 **어디서나 태워진다.**

★저장소 규율: *"처방을 적용한 범위 = 결함이 사는 범위인지 확인하라."*
  결함은 «그 라우터» 가 아니라 **«판정이 라우터에 있다»** 였다.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# ★역할 집합·노드 우선순위는 **`deps_sales` 가 SSOT** 다(그 파일이 명문으로 그렇게 선언한다).
#   앞 판은 이것을 **손으로 복사**해 `총괄관리자`·`platform_admin`·`시행사`·`dev` **네 토큰을
#   떨어뜨렸다** — 그 역할들은 `my_sites` 에서 전 현장을 보면서 승인만 403 이 됐다.
#   ★같은 커밋에서 «사유 어휘를 복사하지 마라» 는 락을 걸어 놓고 옆에서 다른 SSOT 를 복사했다.
from app.services.sales.org.roles import DEVELOPER_ROLES, SUPERADMIN_ROLES, node_priority
from app.services.sales.org.service import create_node
from apps.api.database.models.sales.site_org import SalesOrgNode, SalesSite

logger = logging.getLogger(__name__)

# 승인할 수 있는 **현장 내 역할** — 「관리자 및 상위레벨」(사용자 요구)의 기계적 정의.
# ★MEMBER 는 없다: 서열 최하위라 아래를 승인할 대상이 없다(`_ORG_RANK` 와 정합).
APPROVER_NODE_TYPES = frozenset(
    {"AGENCY", "SUBAGENCY", "GM_DIRECTOR", "DIRECTOR", "TEAM_LEADER"})

# 플랫폼 역할로 승인 가능한 집합 — **SSOT 에서 파생한다**(리터럴 재선언 금지).
# ★이 분기가 없으면 «조직도를 아직 안 만든 현장» 은 **아무도 승인할 수 없어** 영원히 막힌다.
# ★두 집합을 **가른다**: 총괄관리자는 현장 무관, 시행사는 **자기 테넌트 현장만**.
#   앞 판은 둘을 한 집합으로 뭉쳐서, A 테넌트 `developer` 가 B 테넌트 현장의 조직도에
#   제3자를 MEMBER 로 넣을 수 있었다(그 노드가 곧 `enter_site` 의 게이트다).
#   형제들은 전부 **읽기**라 그 비대칭이 안 보였는데, 이 모듈은 **쓰기**다.
APPROVER_PLATFORM_ROLES = frozenset(SUPERADMIN_ROLES)
TENANT_SCOPED_APPROVER_ROLES = frozenset(DEVELOPER_ROLES)


async def resolve_approver_node(db: AsyncSession, site_id, user):
    """이 사용자가 이 현장의 신청을 승인할 수 있는가 — 그렇다면 **부모가 될 노드**를 준다.

    반환: `(가능한가, 부모노드 또는 None)`

    ★부모 노드를 **함께** 돌려주는 이유: 승인은 곧 «내 아래에 넣는다» 이고, 그러면 수수료
      체인이 승인자의 체인을 물려받는다. 「승인 가능한가」와 「누구 아래인가」를 따로 구하면
      두 판정이 갈릴 수 있다 — PR #1021 에서 «검증했다 ≠ 검증한 것을 썼다» 로 데인 형태다.
    """
    # ★★노드를 **권한 우선순위**로 고른다(`path` 순이 아니라).
    #   `deps_sales:41` 이 명문으로 적는다 — *"한 사용자가 같은 현장에 복수의 살아있는
    #   조직노드를 가질 수 있다((site_id,user_id) UNIQUE 부재)."* 그래서 `path` 오름차순
    #   `.first()` 는 **아무 노드나** 집는다. 실제 실패: 대행사 둘인 현장에서 `agc_00aa` 아래
    #   MEMBER 이면서 `agc_ffbb` 아래 DIRECTOR 인 사람이 **403** 을 받는다(MEMBER 가 먼저 나와서).
    #   그리고 승인이 되더라도 **부모가 최상위 노드가 아니면** 신입이 다른 체인에 붙어
    #   수수료 귀속이 바뀐다 — 이 함수 독스트링이 «승인자의 체인을 물려받는다» 고 선언한 그것.
    #   형제 둘(`deps_sales.resolve_site_membership` · `site_auth.my_sites`)이 이미
    #   `(_node_priority, path, id)` 로 고른다. **같은 기준을 쓴다.**
    nodes = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.site_id == site_id, SalesOrgNode.user_id == user.id,
        SalesOrgNode.active.is_(True),
        SalesOrgNode.deleted_at.is_(None)))).scalars().all()
    if nodes:
        node = min(nodes, key=lambda n: (node_priority(str(n.node_type)), str(n.path), str(n.id)))
        if str(node.node_type) in APPROVER_NODE_TYPES:
            return True, node

    role = (getattr(user, "role", "") or "").lower()
    if role in APPROVER_PLATFORM_ROLES:
        return True, None

    # ★시행사(DEVELOPER 계열)는 **자기 테넌트 현장만** 승인한다 — 쓰기 경로의 테넌트 경계.
    if role in TENANT_SCOPED_APPROVER_ROLES:
        tenant_id = getattr(user, "tenant_id", None)
        if tenant_id is not None:
            org_id = (await db.execute(select(SalesSite.organization_id).where(
                SalesSite.id == site_id))).scalar()
            if org_id is not None and str(org_id) == str(tenant_id):
                return True, None

    return False, None


async def link_membership(db: AsyncSession, site_id, applicant_user_id, approver_node) -> str:
    """승인된 신청자를 조직도에 **MEMBER** 로 붙인다 — 사유를 문자열로 돌려준다.

    사유 어휘는 채용 승인 경로(`endpoints/sales/market.py`)와 **같다**. 두 승인 경로가
    서로 다른 말을 하면 화면이 번역표를 두 벌 갖게 되고, 그 순간 하나가 낡는다.

    ★`create_node` 를 경유하는 것이 이 함수의 핵심이다. raw INSERT 로 넣으면 **루트 고아
      노드**가 생기고, 정산이 `chain[0]` 을 대행사로 보므로 **수수료 RESIDUAL 전액이
      신입에게** 꽂힌다(PR #1021 이 봉합한 결함이 **새 문으로 재유입**된다).
    """
    existing = (await db.execute(select(SalesOrgNode.id).where(
        SalesOrgNode.site_id == site_id, SalesOrgNode.user_id == applicant_user_id,
        SalesOrgNode.active.is_(True),
        SalesOrgNode.deleted_at.is_(None)))).first()
    if existing:
        return "ALREADY_MEMBER"

    parent = approver_node
    if parent is None:
        # 승인자가 플랫폼 운영자라 노드가 없다 → 현장의 대행사 루트에 붙인다.
        parent = (await db.execute(select(SalesOrgNode).where(
            SalesOrgNode.site_id == site_id, SalesOrgNode.node_type == "AGENCY",
            SalesOrgNode.active.is_(True),
            SalesOrgNode.deleted_at.is_(None)).order_by(SalesOrgNode.path))).scalars().first()
    if parent is None:
        # ★붙일 자리가 없다 — 조직도가 아직 없는 현장이다. **고아를 만들지 않는다.**
        #   이것은 «실패» 도 «해당없음» 도 아닌 **보류**다(조직도를 시드하면 재승인으로 해결).
        logger.warning(
            "현장 등록승인: 현장 %s 에 상위 노드가 없어 멤버십 배치를 보류한다"
            " (조직도 시드 후 재승인 필요) — 고아 루트 노드를 만들지 않는다", site_id)
        return "ORG_NOT_SEEDED"

    name_row = (await db.execute(text("SELECT name FROM users WHERE id = :u"),
                                 {"u": str(applicant_user_id)})).first()
    try:
        await create_node(db, site_id, "MEMBER", parent_id=parent.id,
                          user_id=applicant_user_id,
                          display_name=name_row[0] if name_row else None)
    except ValueError:
        # ★`create_node` 의 루트·위계 가드가 거부했다 — **삼키지 않는다.**
        #   삼키고 `LINKED` 를 돌려주면 «승인됐다» 는데 조직도엔 아무도 없는 유령 상태가 된다.
        logger.exception("현장 등록승인: 멤버십 노드 생성이 거부됐다(site=%s)", site_id)
        return "ORG_NOT_SEEDED"
    return "LINKED"
