"""조직(ltree) 서비스 — 노드 생성/하위·상위 조회/서브트리 이동."""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.site_org import SalesOrgNode, SalesOrgMembershipHistory


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
