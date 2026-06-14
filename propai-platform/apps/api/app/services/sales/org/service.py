"""조직(ltree) 서비스 — 노드 생성/하위·상위 조회/서브트리 이동."""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.site_org import SalesOrgMembershipHistory, SalesOrgNode


def _label(node_type: str, id_: uuid.UUID) -> str:
    return f"{node_type[:3].lower()}_{id_.hex[:8]}"  # ltree 라벨(영숫자/언더스코어)


async def create_node(db: AsyncSession, site_id, node_type, parent_id=None, **kw) -> SalesOrgNode:
    parent = None
    if parent_id:
        parent = (await db.execute(select(SalesOrgNode).where(SalesOrgNode.id == parent_id))).scalar_one()
    node = SalesOrgNode(site_id=site_id, node_type=node_type, parent_id=parent_id, path="tmp", **kw)
    db.add(node)
    await db.flush()
    label = _label(node_type, node.id)
    node.path = f"{parent.path}.{label}" if parent else label
    await db.flush()
    return node


async def assign_user_to_node(db: AsyncSession, site_id, node_id, email: str) -> dict:
    """org 노드에 같은 조직(테넌트)의 플랫폼 사용자를 이메일로 배정(미배정 해소).

    배정하면 그 사용자가 로그인 시 본인 노드의 실적(계약·고객·업무일지)을 본다. 교차테넌트
    배정은 차단(같은 organization 사용자만)하고, 배정 이력을 남긴다(감사)."""
    from sqlalchemy import func

    from app.models.auth import User
    node = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.id == node_id, SalesOrgNode.site_id == site_id,
        SalesOrgNode.deleted_at.is_(None)))).scalar_one_or_none()
    if node is None:
        raise ValueError("조직 노드를 찾을 수 없습니다")
    em = (email or "").strip()
    if not em:
        raise ValueError("배정할 사용자의 이메일을 입력하세요")
    u = (await db.execute(select(User).where(func.lower(User.email) == em.lower()))).scalar_one_or_none()
    if u is None:
        raise ValueError(f"'{em}' 사용자를 찾을 수 없습니다(플랫폼 가입 이메일을 확인하세요)")
    # 같은 조직(테넌트)인지 확인 — site.organization_id == user.organization_id (교차테넌트 차단).
    org_id = (await db.execute(text("SELECT organization_id FROM sales_sites WHERE id=:s"),
                               {"s": str(site_id)})).scalar()
    if org_id and getattr(u, "organization_id", None) and str(u.organization_id) != str(org_id):
        raise ValueError("같은 조직(테넌트)에 속한 사용자만 배정할 수 있습니다")
    node.user_id = u.id
    if not node.display_name:
        node.display_name = u.full_name
    db.add(SalesOrgMembershipHistory(node_id=node.id, action="ASSIGN", to_path=node.path, by=u.id))
    await db.flush()
    return {"ok": True, "node_id": str(node.id), "user_id": str(u.id),
            "name": node.display_name, "email": u.email}


async def unassign_user(db: AsyncSession, site_id, node_id, by=None) -> dict:
    """노드에서 배정 사용자 해제(미배정으로 되돌림). 노드·display_name·실적은 유지."""
    node = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.id == node_id, SalesOrgNode.site_id == site_id,
        SalesOrgNode.deleted_at.is_(None)))).scalar_one_or_none()
    if node is None:
        raise ValueError("조직 노드를 찾을 수 없습니다")
    node.user_id = None
    db.add(SalesOrgMembershipHistory(node_id=node.id, action="UNASSIGN", to_path=node.path, by=by))
    await db.flush()
    return {"ok": True, "node_id": str(node.id)}


async def seed_default_org(db: AsyncSession, site_id, teams: int = 5, members_per_team: int = 10) -> dict:
    """P2 기본조직 생성: 대행사(AGENCY)→본부장(GM_DIRECTOR)→N팀(TEAM_LEADER)→팀당 M명(MEMBER).

    user 미배정 placeholder 노드로 생성(이후 직급별 등록권한으로 실제 인원 배정·추가·삭제).
    이미 노드가 있으면 가드(중복 시드 방지).
    """
    existing = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.site_id == site_id, SalesOrgNode.deleted_at.is_(None)))).first()
    if existing:
        return {"ok": False, "note": "이미 조직 노드가 있습니다 — 기본조직 시드는 빈 조직에서만 가능합니다."}

    agency = await create_node(db, site_id, "AGENCY", display_name="대행사")
    gm = await create_node(db, site_id, "GM_DIRECTOR", parent_id=agency.id, display_name="본부장")
    n_team = n_member = 0
    for t in range(1, teams + 1):
        tl = await create_node(db, site_id, "TEAM_LEADER", parent_id=gm.id, display_name=f"{t}팀 팀장")
        n_team += 1
        for m in range(1, members_per_team + 1):
            await create_node(db, site_id, "MEMBER", parent_id=tl.id, display_name=f"{t}팀 직원{m}")
            n_member += 1
    return {"ok": True, "agency": 1, "gm_director": 1, "team_leaders": n_team, "members": n_member,
            "total": 2 + n_team + n_member}


async def descendants(db: AsyncSession, node: SalesOrgNode):
    return list((await db.execute(
        select(SalesOrgNode).where(text("path <@ :p")).params(p=node.path))).scalars().all())


async def ancestors_path(db: AsyncSession, member_node_id) -> list[SalesOrgNode]:
    """[최상위(대행사) … 팀원] path 순으로 조상 노드 반환."""
    if not member_node_id:
        return []
    node = (await db.execute(select(SalesOrgNode).where(SalesOrgNode.id == member_node_id))).scalar_one_or_none()
    if not node:
        return []
    labels = str(node.path).split(".")
    out: list[SalesOrgNode] = []
    for i in range(len(labels)):
        sub = ".".join(labels[: i + 1])
        n = (await db.execute(select(SalesOrgNode).where(text("path = :p")).params(p=sub))).scalar_one_or_none()
        if n:
            out.append(n)
    return out


async def move_subtree(db: AsyncSession, node_id, new_parent_id, by=None):
    node = (await db.execute(select(SalesOrgNode).where(SalesOrgNode.id == node_id))).scalar_one()
    new_parent = (await db.execute(select(SalesOrgNode).where(SalesOrgNode.id == new_parent_id))).scalar_one()
    old = str(node.path)
    label = old.split(".")[-1]
    new = f"{new_parent.path}.{label}"
    await db.execute(text(
        "UPDATE sales_org_nodes "
        "SET path = text2ltree(:new || subpath(path, nlevel(:old) - 1)::text) "
        "WHERE path <@ :old"
    ), {"new": new, "old": old})
    db.add(SalesOrgMembershipHistory(node_id=node_id, action="MOVE", from_path=old, to_path=new, by=by))
    await db.flush()
