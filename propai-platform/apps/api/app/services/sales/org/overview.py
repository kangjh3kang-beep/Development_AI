"""P2-3 직급별 관리 — 관리자 하위 조직(ltree subtree) 인원의 활동 통합 집계.

각 직급은 자신의 하위 조직만 본다(시행/대행 본사·관리자는 전체). 계약(member_node_id)·
고객/방문(assigned_node_id)·업무일지(author_node_id) 가 모두 org 노드로 연결돼 있어,
subtree(path <@ 내 path) 노드 집합으로 1차 집계한다. 수수료/근태/단체메시지는 기존 패널
(CommissionBoard·attendance·SocialPanel)이 담당하며, 여기선 관리용 로스터+활동 카운트를 제공.

[응답계약 SSOT — 역할 분리]
  본 모듈의 team_overview(=GET /api/v1/sales/org/team-overview)는 '한 현장의 조직 노드(직원)
  단위' 로스터/집계다(노드별 계약·고객·업무일지·세금유형). 프론트 소비자는 OrgTree.tsx 하나뿐이다.
  이와 별개로 market.py 의 staff_overview(=GET /api/v1/market/staff/overview)는 '여러 현장의
  현장 단위' 요약(현장별 멤버수·계약수·출근수·수수료gross, 다현장 union)으로 역할이 다르며 소비자는
  StaffOverviewPanel.tsx 하나뿐이다. 두 응답은 입도(노드 vs 현장)·범위(단일현장 vs 다현장)가 달라
  단일 계약으로 합치지 않고 '명확히 분리'하되, 각 응답을 Pydantic 모델로 고정해 프론트가 단일
  호출경로로만 소비하도록(이중 구현·드리프트 방지) 계약을 명시한다.
"""
from __future__ import annotations

import logging
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.commission_mh_harness import SalesWorkLog
from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesCustomer
from apps.api.database.models.sales.site_org import SalesOrgNode

logger = logging.getLogger(__name__)

# ★[라벨 SSOT(iter-7)] node_type → 한국어 직급 라벨의 '정본(SSOT)'은 이 _LABEL 한 부다.
#   프론트 OrgTree.tsx 의 NODE_TYPES/LABEL 라벨은 이 값과 6개 전부 byte-동일이어야 한다(트리배지·
#   로스터표·드롭다운이 같은 문자열). 위계는 site_auth._ROLE_LABEL 과도 일치하는 '본부장(GM_DIRECTOR)
#   > 이사(DIRECTOR)'. 라벨 '값' 패리티는 test_sales_org.test_node_type_label_value_parity_*(백)와
#   OrgTree.contract.test.ts(프론트)가 byte-동일로 고정한다(키셋만 비교하던 가짜패리티 교정).
#
# ★[iter-7 backlog — LOW 하드닝, 이번엔 미구현(추가구현 금지·스파이럴 방지)] 다음 verdict 항목은 LOW
#   난이도라 차기 이터레이션으로 이연한다(여기 표기만): ① move_subtree node.path stale refresh(이동 후
#   메모리상 node.path 재동기화), ② no-op 이동(new_parent == 현재 부모) early-return, ③ commission_gross
#   집계의 status 필터(취소/환수분 제외), ④ move 시 new_parent 계층검증(직급 위계 위반 거부).
_LABEL = {"AGENCY": "대행본사", "SUBAGENCY": "대행지사", "GM_DIRECTOR": "본부장",
          "DIRECTOR": "이사", "TEAM_LEADER": "팀장", "MEMBER": "직원"}

# 테이블 미존재 PostgreSQL SQLSTATE(asyncpg) — 이것만 '정상 0'(아직 안 만든 테이블)으로 본다.
# 42P01=undefined_table. 그 외 DB 오류는 은폐 금지(분류 로깅 후 전파).
# (app/services/sales/payment/service.py·commission/engine.py 의 검증된 분류 패턴과 동일.)
_MISSING_OBJECT_SQLSTATES = frozenset({"42P01"})


def _missing_object_sqlstate(exc: BaseException) -> str | None:
    """예외가 '테이블 미존재'(42P01)면 해당 SQLSTATE, 아니면 None(전파신호)."""
    orig = getattr(exc, "orig", None) or exc
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code in _MISSING_OBJECT_SQLSTATES:
        return code
    return None


# ── 응답계약(Pydantic) — 프론트 OrgTree.tsx 의 Ov 타입이 부분소비하는 'superset' ────────────────
#   (이 응답은 OrgTree.tsx 가 쓰는 키의 상위집합이다. 프론트 Ov 타입은 scope/scope_nodes 등
#    일부 키를 소비하지 않을 수 있으나, 소비하는 키는 반드시 여기 키와 1:1 로 일치해야 한다
#    — 키 이름/형태 드리프트는 test_team_overview_response_keys_match_frontend 로 고정.)
class TeamTotals(BaseModel):
    """하위 조직 인원의 활동 합계(계약·고객·업무일지)."""
    contracts: int = 0
    customers: int = 0
    work_logs: int = 0


class TeamRosterItem(BaseModel):
    """조직 노드(직원) 1명의 로스터 행 — 직급·배정여부·활동·세금유형."""
    node_id: str
    name: str
    role: str                     # node_type 원값(AGENCY/MEMBER 등)
    role_label: str               # 한국어 직급 라벨
    assigned: bool                # 플랫폼 사용자 배정 여부(미배정=False)
    contracts: int = 0
    customers: int = 0
    work_logs: int = 0
    tax_type: str = "WITHHOLDING"  # WITHHOLDING(3.3%) | VAT(10%)


class TeamOverviewResponse(BaseModel):
    """직급별 관리 — 내 하위 조직(현장 단위) 노드 로스터+활동 집계.

    ★[합계 범위 명시 — 화면 혼동 방지] totals 는 '범위 안 전체 노드'(scope_nodes, 로스터에서 제외되는
      AGENCY/SUBAGENCY 본사 노드 포함)의 활동 합계다. 반면 roster 행은 직급(MEMBER/TEAM_LEADER/
      GM_DIRECTOR/DIRECTOR)만 표시하므로, sum(roster[*].contracts) ≤ totals.contracts 일 수 있다
      (본사 노드에 직접 귀속된 계약이 있으면 합계가 더 큼). 화면이 '행 합'과 '전체 합'을 혼동하지
      않도록 roster 행만의 합계를 roster_totals 로 따로 제공한다(둘 다 명시 — 어느 쪽도 은폐 안 함)."""
    scope: str                    # 'subtree'(내 하위) | 'site'(현장 전체)
    scope_nodes: int = 0          # 범위 안 전체 노드 수
    members: int = 0              # 로스터에 표시되는 관리대상(직원·관리직) 수
    totals: TeamTotals = Field(default_factory=TeamTotals)        # 범위 전체 노드 합계(본사 포함)
    roster_totals: TeamTotals = Field(default_factory=TeamTotals)  # 로스터 표시 행만의 합계(행 합 일치)
    roster: list[TeamRosterItem] = Field(default_factory=list)


async def team_overview(db: AsyncSession, site_id: uuid.UUID,
                        org_path: str | None) -> TeamOverviewResponse:
    """내 하위 조직 인원의 계약·고객·업무일지 집계 + 로스터(응답계약: TeamOverviewResponse)."""
    # 범위 노드: org_path 있으면 그 하위트리, 없으면(본사/관리자) 현장 전체.
    q = select(SalesOrgNode).where(SalesOrgNode.site_id == site_id, SalesOrgNode.deleted_at.is_(None))
    if org_path:
        q = q.where(text("path <@ :p")).params(p=org_path)
    nodes = list((await db.execute(q)).scalars().all())
    if not nodes:
        return TeamOverviewResponse(scope="subtree" if org_path else "site")
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
    # 업무일지(author_node_id 별 건수) — raw SQL → ORM 정규화(SalesWorkLog 모델 보유).
    work_logs = _count_map((await db.execute(
        select(SalesWorkLog.author_node_id, func.count())
        .where(SalesWorkLog.site_id == site_id, SalesWorkLog.author_node_id.in_(node_ids))
        .group_by(SalesWorkLog.author_node_id))).all())

    # 수령자별 수수료 세금유형(WITHHOLDING 3.3% / VAT 10%) — 멱등 테이블 일괄 조회.
    # ★raw SQL 유지: sales_commission_tax_pref 는 ORM 모델이 없는 런타임/마이그레이션 전용 테이블이라
    #   text() 조회가 불가피하다(다른 모듈 사례처럼 사유 명시).
    # ★[silent-fail 제거] 과거엔 모든 예외를 무시하고 기본값으로 삼았다(테이블 부재·권한·구문 오류를
    #   똑같이 은폐). 이제 '테이블 미존재(42P01)'만 '정상 0(아직 안 만든 선호 테이블)'으로 보고 기본값을
    #   쓰고, 그 외 DB 오류(권한·연결·구문 등)는 분류 로깅 후 전파한다(은폐 금지).
    tax_map: dict[str, str] = {}
    try:
        tx = (await db.execute(text(
            "SELECT node_id, tax_type FROM sales_commission_tax_pref WHERE node_id = ANY(:ids)"),
            {"ids": node_ids})).all()
        tax_map = {str(k): v for k, v in tx}
    except Exception as e:  # noqa: BLE001 — 분류 후 정상0만 흡수, 실오류는 전파
        if _missing_object_sqlstate(e):
            logger.info("team_overview: sales_commission_tax_pref 미존재(42P01) — 세금유형 기본값 사용")
            tax_map = {}
        else:
            logger.exception("team_overview: 세금유형 조회 실패(테이블부재 외 오류 — 전파)")
            raise

    roster: list[TeamRosterItem] = []
    for n in nodes:
        if n.node_type not in ("MEMBER", "TEAM_LEADER", "GM_DIRECTOR", "DIRECTOR"):
            continue
        nid = str(n.id)
        roster.append(TeamRosterItem(
            node_id=nid, name=n.display_name or "-",
            role=n.node_type, role_label=_LABEL.get(n.node_type, n.node_type),
            assigned=bool(n.user_id),
            contracts=contracts.get(nid, 0),
            customers=customers.get(nid, 0),
            work_logs=work_logs.get(nid, 0),
            tax_type=tax_map.get(nid, "WITHHOLDING"),
        ))
    roster.sort(key=lambda r: (-r.contracts, -r.customers))
    # ★roster_totals: 로스터 표시 행만의 합계(화면 '행 합'과 1:1). totals(전체 노드 합)와 분리해
    #   본사 노드 귀속분이 합계 차이를 만들어도 화면이 혼동하지 않도록 둘 다 명시한다.
    roster_totals = TeamTotals(
        contracts=sum(r.contracts for r in roster),
        customers=sum(r.customers for r in roster),
        work_logs=sum(r.work_logs for r in roster),
    )
    return TeamOverviewResponse(
        scope="subtree" if org_path else "site",
        scope_nodes=len(nodes),
        members=len(roster),
        totals=TeamTotals(
            contracts=sum(contracts.values()),
            customers=sum(customers.values()),
            work_logs=sum(work_logs.values()),
        ),
        roster_totals=roster_totals,
        roster=roster,
    )
