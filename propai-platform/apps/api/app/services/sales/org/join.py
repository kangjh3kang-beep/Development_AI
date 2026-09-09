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

# ★sponsor 해석 실패의 **단일 표면**. 세 갈래(미가입·현장 밖·직급 부족)가 같은 말을 한다 —
#   갈라 말하면 그 자체가 계정 열거·소속·직급 오라클이 된다(R3 리뷰 M-2).
_SPONSOR_OPAQUE = (
    "이 현장의 담당자로 확인되지 않습니다 — 이메일과 담당자 소속을 확인해 주세요")

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


class SponsorNotFoundError(ValueError):
    """희망 직속 상위를 그 현장에서 찾지 못했다(이메일 오타 · 그 현장 멤버가 아님)."""


class SponsorNotEligibleError(ValueError):
    """찾았으나 **아래를 둘 수 없는 직급**이다(MEMBER 는 서열 최하위)."""


async def resolve_sponsor_node(db: AsyncSession, site_id, sponsor_email: str):
    """희망 직속 상위(sponsor)를 **이메일로** 그 현장의 조직 노드로 해석한다.

    ## 왜 sponsor 를 신청 시점에 정하나 (2026-09-09 · 볼트 §0 조회가 짚은 누락)

    채택된 설계(벤치마킹 R2)가 *"신청 시 **희망 직속 상위 필수** + 승인·삽입 원자성"* 인데
    구현에서 빠져 있었다. 그 결과 부모가 **승인자의 노드**로 정해졌고, 한 현장에 승인자가
    여럿이면(팀장·본부장) **누가 먼저 누르느냐로 신입의 조상 체인이 갈렸다.**
    정산이 `chain[0]` 을 대행사로 보므로 **수수료 귀속이 클릭 순서에 좌우된다** — 조용하다.

    ★기각된 대안(X1 도메인 자동가입)의 기각 사유가 정확히 *"sponsor 확정 시점을 없애
      R2 와 구조적 양립 불가"* 였다. 시점을 **신청**으로 고정하는 것이 이 함수의 존재 이유다.

    ## 왜 조직도 목록이 아니라 **이메일**인가

    신청자는 아직 그 현장의 멤버가 아니다. 후보를 고르게 하려면 **남의 현장 조직도를 보여 줘야**
    하는데, 그건 이 파이프라인이 «축소 필드만 준다» 고 선언한 격리를 스스로 깨는 것이다.
    이메일은 **신청자가 이미 아는 정보**(나를 부른 사람)라 새 노출이 0 이다.
    ★해석 패턴은 새로 만들지 않았다 — `org/service.assign_user_to_node` 가 쓰는 그 SQL 이다.
    """
    # ★★**세 실패를 한 문구로 합친다**(2026-09-09 R3 리뷰 M-2).
    #   앞 판은 «플랫폼에 없는 이메일» · «있으나 이 현장 멤버 아님» · «멤버이나 직급 부족» 을
    #   **서로 다른 문구**로 갈랐다. 그리고 바로 위 주석이 «계정 존재 여부가 새지 않게
    #   뭉뚱그린다» 고 적었는데 **다음 분기가 그 뭉뚱그림을 깼다** — 없는 면역을 주장한 것이다.
    #
    #   공격 조건이 낮다: `/sites/discover` 가 **모든 인증 사용자에게 전 현장 id** 를 주고,
    #   신청은 멤버십이 필요 없으며, 자기 신청은 스스로 취소할 수 있어 **무제한 반복**된다.
    #   그러면 «임의 이메일의 가입 여부 + 임의 현장 소속 여부 + 정확한 직급» 이 새어 나간다 —
    #   이 모듈이 `organization_id` 한 컬럼을 감추려고 쓴 독스트링보다 **훨씬 넓은 표면**이다.
    #
    #   ⇒ **표면은 하나**, 예외 클래스는 그대로(호출부가 상태코드를 가르는 데 쓴다).
    #     상세는 로그로만 남긴다.
    em = (sponsor_email or "").strip()
    if not em:
        raise SponsorNotFoundError(_SPONSOR_OPAQUE)

    row = (await db.execute(text(
        "SELECT id FROM users WHERE lower(email)=lower(:em)"), {"em": em})).first()
    if row is None:
        logger.info("sponsor 해석 실패: 플랫폼에 없는 이메일(site=%s)", site_id)
        raise SponsorNotFoundError(_SPONSOR_OPAQUE)

    nodes = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.site_id == site_id, SalesOrgNode.user_id == row[0],
        SalesOrgNode.active.is_(True),
        SalesOrgNode.deleted_at.is_(None)))).scalars().all()
    if not nodes:
        logger.info("sponsor 해석 실패: 이 현장의 구성원이 아님(site=%s)", site_id)
        raise SponsorNotFoundError(_SPONSOR_OPAQUE)

    # ★복수 노드면 **권한 우선순위**로 고른다(형제 셋과 같은 기준).
    node = min(nodes, key=lambda n: (node_priority(str(n.node_type)), str(n.path), str(n.id)))
    if str(node.node_type) not in APPROVER_NODE_TYPES:
        logger.info("sponsor 해석 실패: 직급이 아래를 둘 수 없음(site=%s, type=%s)",
                    site_id, node.node_type)
        raise SponsorNotEligibleError(_SPONSOR_OPAQUE)
    return node


async def site_has_approver_nodes(db: AsyncSession, site_id) -> bool:
    """이 현장에 **아래를 둘 수 있는 조직 노드가 하나라도** 있나.

    ★★2026-09-09 R3 리뷰 C-1. `sponsor_email` 을 **무조건 필수**로 만들었더니,
      **조직도가 없는 현장은 어떤 이메일을 넣어도 400** 이 됐다 — 신청이 원리적으로 불가능해졌다.
      그런데 같은 PR 이 *"라이브 13현장 중 10현장이 조직도 미시드"* 라고 적는다.
      **두 문장은 동시에 참일 수 없다** — 사용자 요구(«모든 회원이 모든 현장에 신청»)를
      **다수 현장에서 막은 것**이다.

    ⇒ sponsor 는 «조직도가 있는 현장» 에서만 필수다. 없는 현장은 sponsor 없이 신청을 받고
      승인 시 `ORG_NOT_SEEDED` 보류로 간다(그 경로는 이미 있다).
      ★«없으면 그냥 통과» 가 아니라 **현장의 상태로 갈라진다** — 조용한 우회로가 아니다.
    """
    row = (await db.execute(select(SalesOrgNode.id).where(
        SalesOrgNode.site_id == site_id,
        SalesOrgNode.node_type.in_(sorted(APPROVER_NODE_TYPES)),
        SalesOrgNode.active.is_(True),
        SalesOrgNode.deleted_at.is_(None)).limit(1))).first()
    return row is not None


async def link_membership(db: AsyncSession, site_id, applicant_user_id, approver_node,
                          sponsor_node=None) -> str:
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

    # ★★부모는 **신청 시 정해진 sponsor** 가 우선이다(2026-09-09).
    #   승인자 노드를 부모로 쓰면 **누가 먼저 누르느냐로 조상 체인이 갈리고**,
    #   정산이 `chain[0]` 을 보므로 **수수료 귀속이 클릭 순서에 좌우된다.**
    #   sponsor 는 신청 시점에 고정되므로 **누가 승인해도 같은 자리**에 붙는다.
    parent = sponsor_node or approver_node
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


async def prepare_join_request(db: AsyncSession, site_id, sponsor_email: str | None):
    """신청을 만들기 **전에** sponsor 를 확정한다 — 조직도 유무로 갈라서.

    반환: `sponsor_node_id 또는 None`

    ★★2026-09-09 R3 리뷰 M-1: 이 판정이 라우터에 흩어져 있었고, 그래서 **무잠금**이었다
      (변이 4종이 전부 생존 — 저장·전달·차단·재확인). 이 PR 이 스스로 선언한 원칙
      *"판정은 라우터가 아니라 서비스 층에 산다"* 를 **이번 라운드에 만든 판정에는 안 썼다.**

    ⇒ «조직도가 있나 → 있으면 sponsor 필수, 없으면 sponsor 없이 진행» 을 **한 값 흐름**으로.
      라우터에는 HTTP 매핑만 남는다.
    """
    if not await site_has_approver_nodes(db, site_id):
        # ★조직도가 아직 없는 현장 — sponsor 를 요구하면 **신청 자체가 불가능**해진다(C-1).
        #   승인 시 `ORG_NOT_SEEDED` 보류로 가고, 조직도를 시드한 뒤 재승인으로 풀린다.
        return None
    sponsor = await resolve_sponsor_node(db, site_id, sponsor_email or "")
    return sponsor.id


async def reload_sponsor_node(db: AsyncSession, site_id, sponsor_node_id):
    """신청에 박힌 sponsor 를 **승인 시점에 다시 확인**한다(그 사이 해촉될 수 있다).

    ★현장 술어를 **함께** 건다(R3 리뷰 M-3). 앞 판은 `id` 만 봐서 이론상 타 현장 노드가
      부모로 올 수 있었고, 2차 방어(`create_node` 의 부모 site 스코프)가 막긴 하지만
      그때 사용자에게 가는 말이 **틀린 사유**가 된다(«조직도를 시드하라» ← 실제는 «상위가 죽었다»).

    살아 있지 않으면 `None` — 조용히 승인자 노드로 **바꿔치기하지 않는다**
    (바꿔치기하면 «클릭 순서가 체인을 정한다» 가 되살아난다).
    """
    if sponsor_node_id is None:
        return None
    return (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.id == sponsor_node_id,
        SalesOrgNode.site_id == site_id,
        SalesOrgNode.active.is_(True),
        SalesOrgNode.deleted_at.is_(None)))).scalars().first()


class SelfApprovalError(ValueError):
    """자기 신청은 스스로 결정할 수 없다 — **승인은 남이 하는 것**이다."""


def assert_not_self_decision(applicant_user_id, decider_user_id) -> None:
    """신청자와 결정자가 같은 사람인지 — **서비스 층에서** 판정한다.

    ## 왜 라우터가 아니라 여기인가 (2026-09-09 R3 리뷰 M-1)

    앞 판은 이 비교를 라우터에 인라인으로 두고 락은 **AST 모양**(«비교문이 있고 그 안에 raise 가
    있다»)만 봤다. 그래서 리뷰어가 `==` 를 `is` 로 바꾸자 — 파이썬에서 `str(a) is str(b)` 는
    **새 객체라 항상 False** 라 차단이 **완전히 꺼지는데** — 모든 락이 초록이었다
    (`::VERDICT=SURVIVED`). **존재를 잠그면 행위는 안 잠긴다.**

    ★플랫폼 역할(`superadmin`/`developer`)은 조직노드가 **없어서** 「이미 멤버」 검사를
      통과해 자기 신청을 만들 수 있고, 그다음 플랫폼 분기로 자기가 자기를 승인해
      대행사 루트 아래에 자신을 넣을 수 있었다.
    """
    if str(applicant_user_id) == str(decider_user_id):
        raise SelfApprovalError("자기 신청은 스스로 승인·거절할 수 없습니다")
