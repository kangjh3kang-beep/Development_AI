"""P2-3 직급별 관리 — 관리자 하위 조직(ltree subtree) 인원의 활동 통합 집계.

각 직급은 자신의 하위 조직만 본다(시행/대행 본사·관리자는 전체). 계약(member_node_id)·
고객/방문(assigned_node_id)·업무일지(author_node_id) 가 모두 org 노드로 연결돼 있어,
subtree(path <@ 내 path) 노드 집합으로 1차 집계한다. 수수료/근태/단체메시지는 기존 패널
(CommissionBoard·attendance·SocialPanel)이 담당하며, 여기선 관리용 로스터+활동 카운트를 제공.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.site_org import SalesOrgNode
from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesCustomer

_LABEL = {"AGENCY": "대행본사", "SUBAGENCY": "대행지사", "GM_DIRECTOR": "본부장",
          "DIRECTOR": "이사", "TEAM_LEADER": "팀장", "MEMBER": "직원"}


async def team_overview(db: AsyncSession, site_id: uuid.UUID, org_path: str | None) -> dict[str, Any]:
    """내 하위 조직 인원의 계약·고객·업무일지 집계 + 로스터."""
    # 범위 노드: org_path 있으면 그 하위트리, 없으면(본사/관리자) 현장 전체.
    q = select(SalesOrgNode).where(SalesOrgNode.site_id == site_id, SalesOrgNode.deleted_at.is_(None))
    if org_path:
        q = q.where(text("path <@ :p")).params(p=org_path)
    nodes = list((await db.execute(q)).scalars().all())
    if not nodes:
        return {"scope": "subtree" if org_path else "site", "scope_nodes": 0, "members": 0,
                "totals": {"contracts": 0, "customers": 0, "work_logs": 0}, "roster": []}
    node_ids = [n.id for n in nodes]

    # 노드별 집계(계약·고객·업무일지).
    def _count_map(rows):
        return {str(k): int(v) for k, v in rows}

    contracts = _count_map((await db.execute(
        select(SalesContractExt.member_node_id, func.count())
        .where(SalesContractExt.site_id == site_id, SalesContractExt.member_node_id.in_(node_ids))
        .group_by(SalesContractExt.member_node_id))).all())
    customers = _count_map((await db.execute(
        select(SalesCustomer.assigned_node_id, func.count())
        .where(SalesCustomer.site_id == site_id, SalesCustomer.assigned_node_id.in_(node_ids),
               SalesCustomer.deleted_at.is_(None))
        .group_by(SalesCustomer.assigned_node_id))).all())
    # 업무일지(원시 테이블 author_node_id).
    wl_rows = (await db.execute(text(
        "SELECT author_node_id, count(*) FROM sales_work_logs "
        "WHERE author_node_id = ANY(:ids) GROUP BY author_node_id"),
        {"ids": node_ids})).all()
    work_logs = {str(k): int(v) for k, v in wl_rows}

    roster = []
    for n in nodes:
        if n.node_type not in ("MEMBER", "TEAM_LEADER", "GM_DIRECTOR", "DIRECTOR"):
            continue
        nid = str(n.id)
        roster.append({
            "node_id": nid, "name": n.display_name or "-",
            "role": n.node_type, "role_label": _LABEL.get(n.node_type, n.node_type),
            "assigned": bool(n.user_id),
            "contracts": contracts.get(nid, 0),
            "customers": customers.get(nid, 0),
            "work_logs": work_logs.get(nid, 0),
        })
    roster.sort(key=lambda r: (-r["contracts"], -r["customers"]))
    return {
        "scope": "subtree" if org_path else "site",
        "scope_nodes": len(nodes),
        "members": len(roster),
        "totals": {
            "contracts": sum(contracts.values()),
            "customers": sum(customers.values()),
            "work_logs": sum(work_logs.values()),
        },
        "roster": roster,
    }
