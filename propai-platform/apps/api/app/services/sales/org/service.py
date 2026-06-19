"""조직(ltree) 서비스 — 노드 생성/하위·상위 조회/서브트리 이동."""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.site_org import (
    SalesOrgMembershipHistory,
    SalesOrgNode,
    SalesSite,
)

# move_subtree 의 현장별 직렬화용 advisory-lock '베이스' 키(int4). 같은 현장 동시 이동을 직렬화하려
# 2-인자 advisory-lock(pg_advisory_xact_lock(베이스, hashtext(site_id)))으로 현장마다 다른 락을 잡는다.
# (다른 모듈의 880421xxx 락 키 관례와 일관 — 037 은 이 기능 도입 순번 표식일 뿐 충돌 회피용 임의 상수.)
# ★int4 범위(2^31-1=2147483647)를 넘으면 pg 가 거부하므로 8자리 상수(<2.15e9)로 둔다.
_LOCK_ORG_MOVE = 88042037


# ★[ux·정직성(iter-4)] move_subtree 의 거부 사유를 엔드포인트가 사유별 상태코드(404/422/403)로
#   매핑할 수 있도록 전용 예외 하위클래스를 둔다(commission 의 CrossSiteOwnershipError 와 같은 패턴).
#   모두 ValueError 하위라, 기존에 'except ValueError' 로 잡던 호출부(테스트 포함)는 무회귀로 그대로
#   동작하고, 사유를 구분하려는 엔드포인트만 isinstance/순서 분기로 세분한다(additive).
class OrgNodeNotFoundError(ValueError):
    """이동할 노드(또는 새 부모)가 '어디에도' 없음 — 클라이언트 입력오류 → 404."""


class OrgCrossSiteError(ValueError):
    """노드는 존재하나 '타 현장' 소속 — 현장격리(IDOR) 위반 → 403."""


class OrgCycleError(ValueError):
    """노드를 자기 자신/그 하위 아래로 옮기려는 사이클(입력오류) → 422."""


def _label(node_type: str, id_: uuid.UUID) -> str:
    # ltree 라벨(영숫자/언더스코어, 영문접두). ★[충돌 완화] path 에 UNIQUE 제약이 없고(현행은
    # gist 인덱스 idx_org_path 뿐) 같은 부모 아래 다수 노드를 시드하므로, hex[:8](32bit)는 생일역설로
    # 충돌 가능성이 무시 못 할 수준이다. hex[:12](48bit)로 넓혀 충돌 확률을 수만 배 낮춘다(라벨 길이
    # 여유 충분, text2ltree 캐스트도 영숫자라 안전).
    return f"{node_type[:3].lower()}_{id_.hex[:12]}"


def _is_self_or_descendant(old: str, candidate: str) -> bool:
    """candidate 경로가 old 자신이거나 그 하위(old 를 접두로 가짐)인지 — 사이클 판정용.

    ltree 의 `candidate <@ old`(candidate 가 old 를 조상으로 가짐)와 동치다. 새 부모가 이동노드
    자신이나 그 하위면, 서브트리를 자기 안으로 넣는 셈이라 트리가 자기참조/고아로 깨진다.
    """
    old_labels = old.split(".")
    cand_labels = candidate.split(".")
    return cand_labels[: len(old_labels)] == old_labels


def rewrite_subtree_path(old: str, new_parent_path: str, path: str) -> str:
    """move_subtree 의 ltree 경로 재기록을 '파이썬 순수함수'로 재현(SQL과 동치).

    SQL: text2ltree(:new_parent) || subpath(path, nlevel(:old) - 1)
      - subpath(path, nlevel(old)-1) = '이동노드 라벨'부터 끝까지의 잔여경로
        (이동노드 자신이면 라벨 1개, 하위면 라벨+하위경로).
      - new_parent || 잔여경로 = '새부모 경로'에 잔여경로를 점구분자로 이어붙인 최종경로.
    DB 없이 이동 규칙(off-by-one·구분자)을 단위테스트로 고정하기 위한 동치 구현이다(라이브 SQL 은
    deploy-pending). path 가 old 의 하위가 아니면(접두 불일치) 변경 없이 그대로 돌려준다(방어).

    ★[사이클 가드] 새 부모가 이동노드 자신이거나 그 하위면(old 를 접두로 가짐) 거부한다(ValueError).
      a.b.c 를 a.b.c(자신)·a.b.c.d(직속 하위) 아래로 옮기면 WHERE path<@:old 가 새 부모까지 재기록해
      자기참조/고아가 된다. 이는 move_subtree 가 던지는 거부와 동일 규칙을 순수함수로도 고정한 것이다.
    """
    if _is_self_or_descendant(old, new_parent_path):
        raise ValueError("노드를 자기 자신이나 그 하위 조직 아래로는 옮길 수 없습니다")
    old_labels = old.split(".")
    path_labels = path.split(".")
    # WHERE path <@ :old = path 가 old 를 '접두'로 갖는(=old 자신 또는 그 하위) 경우만 재기록한다.
    if path_labels[: len(old_labels)] != old_labels:
        return path  # old 의 하위가 아님 — 무변경(WHERE path <@ :old 에 안 걸리는 경우)
    offset = len(old_labels) - 1  # nlevel(old)-1 = 이동노드 라벨의 0-기준 위치
    remainder = path_labels[offset:]  # 이동노드 라벨부터의 잔여경로(라벨 + 하위)
    return ".".join([*new_parent_path.split("."), *remainder])


async def create_node(db: AsyncSession, site_id, node_type, parent_id=None, **kw) -> SalesOrgNode:
    """org 노드 생성. parent_id 가 있으면 그 부모의 path 를 상속해 자식 path 를 만든다.

    ★[현장격리·IDOR 차단] 과거엔 parent 를 'id 만'으로 전역 조회(scalar_one)했다. 그래서 A현장
      관리자가 body.parent_id 에 B현장 노드를 넘기면, 새 노드는 caller 의 site_id 로 스탬프되면서도
      B현장 부모의 path 를 상속해 '교차현장 path graft'(타 현장 트리에 끼워넣기)가 가능했다. 또
      미존재 parent_id 는 scalar_one() 이 NoResultFound 를 던져 전역핸들러 500 으로 누출됐다
      (node_type 누락은 400 인데 비대칭). 해결: 부모 조회 WHERE 에 site_id 일치 + 삭제 안 됨
      조건을 걸고, scalar_one_or_none()→None 이면 ValueError 로 거부한다(엔드포인트가 400/404 로
      매핑). 이러면 타 현장 부모는 '못 찾음'으로 거부되고, 미존재 부모도 500 대신 명시 오류가 된다.
    """
    parent = None
    if parent_id:
        parent = (await db.execute(select(SalesOrgNode).where(
            SalesOrgNode.id == parent_id, SalesOrgNode.site_id == site_id,
            SalesOrgNode.deleted_at.is_(None)))).scalar_one_or_none()
        if parent is None:
            raise ValueError("상위(부모) 조직 노드를 찾을 수 없습니다(현장 소속 노드만 상위로 지정 가능)")
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
    node = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.id == node_id, SalesOrgNode.site_id == site_id,
        SalesOrgNode.deleted_at.is_(None)))).scalar_one_or_none()
    if node is None:
        raise ValueError("조직 노드를 찾을 수 없습니다")
    em = (email or "").strip()
    if not em:
        raise ValueError("배정할 사용자의 이메일을 입력하세요")
    # ★public.users 실컬럼은 id·tenant_id·email·name (ORM User 모델은 organization_id/full_name 으로
    #   stale → select(User) 가 UndefinedColumnError). 인증도 raw SQL을 쓰므로 동일하게 raw SQL로 조회한다.
    u = (await db.execute(text(
        "SELECT id, name, tenant_id FROM users WHERE lower(email)=lower(:em)"), {"em": em})).first()
    if u is None:
        raise ValueError(f"'{em}' 사용자를 찾을 수 없습니다(플랫폼 가입 이메일을 확인하세요)")
    # 같은 조직(테넌트)인지 확인 — site.organization_id == users.tenant_id (교차테넌트 차단).
    # raw SQL → ORM 정규화(SalesSite 모델은 organization_id 컬럼을 보유 — stale 아님).
    org_id = (await db.execute(
        select(SalesSite.organization_id).where(SalesSite.id == site_id))).scalar()
    if org_id and u[2] and str(u[2]) != str(org_id):
        raise ValueError("같은 조직(테넌트)에 속한 사용자만 배정할 수 있습니다")
    node.user_id = u[0]
    if not node.display_name:
        node.display_name = u[1]
    db.add(SalesOrgMembershipHistory(node_id=node.id, action="ASSIGN", to_path=node.path, by=u[0]))
    await db.flush()
    return {"ok": True, "node_id": str(node.id), "user_id": str(u[0]),
            "name": node.display_name, "email": em}


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


async def descendants(db: AsyncSession, site_id, node: SalesOrgNode):
    """노드의 하위트리(자신 포함) 반환.

    ★[architecture·정직표기(iter-4)] 본 함수는 현재 '프로덕션 호출자 0' 이다(코드베이스 grep 결과
      test_sales_org.py 의 (k) 격리계약 회귀테스트만 호출). 즉시 '제거'하지 않고 '유지'하기로 한 이유:
      ① subtree 단위 권한/집계 확장(예: 특정 본부장 하위만 일괄작업)에 곧 쓰일 공용 1차 프리미티브라
         삭제하면 재작성 비용이 든다. ② 격리계약(site_id 일치+삭제 안 됨)을 이미 선반영해 두면, 첫
         실사용 배선 시점에 IDOR 가 재발하지 않는다(안전 선반영). 미래에 끝내 미사용으로 판명되면
         그때 제거한다 — 지금은 '미배선 dead-code 임을 정직표기'한 채 격리계약만 회귀로 고정한다.
      team_overview/move_subtree 와 동일한 격리계약(site_id 일치 + 삭제 안 됨)을 WHERE 에 전파한다.
    """
    # ORM 엔티티 select 에 ltree 하위연산자(path <@)만 raw text 로 둔다(<@ 는 ORM 표현 부재).
    return list((await db.execute(
        select(SalesOrgNode).where(
            SalesOrgNode.site_id == site_id, SalesOrgNode.deleted_at.is_(None),
            text("path <@ :p")).params(p=node.path))).scalars().all())


async def ancestors_path(db: AsyncSession, site_id, member_node_id) -> list[SalesOrgNode]:
    """[최상위(대행사) … 팀원] path 순으로 조상 노드 반환.

    ★[현장격리] 과거엔 노드/조상 조회가 `id = :id` / `path = :p` 만으로 site_id 필터가 없어,
      같은 라벨 경로가 타 현장에 우연히 존재하면 교차현장 조상이 혼입될 수 있었다(수수료 배분
      체인이 타 현장 노드로 새는 위험). team_overview/move_subtree 와 동일한 격리계약(site_id
      일치 + 삭제 안 됨)을 모든 조회 WHERE 에 전파한다.
    """
    if not member_node_id:
        return []
    node = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.id == member_node_id, SalesOrgNode.site_id == site_id,
        SalesOrgNode.deleted_at.is_(None)))).scalar_one_or_none()
    if not node:
        return []
    labels = str(node.path).split(".")
    out: list[SalesOrgNode] = []
    for i in range(len(labels)):
        sub = ".".join(labels[: i + 1])
        n = (await db.execute(select(SalesOrgNode).where(
            SalesOrgNode.site_id == site_id, SalesOrgNode.deleted_at.is_(None),
            text("path = :p")).params(p=sub))).scalar_one_or_none()
        if n:
            out.append(n)
    return out


async def _raise_node_reason(db: AsyncSession, node_id, label: str) -> None:
    """현장 스코프 조회가 None 일 때 거부 사유를 구분해 던진다(절대 반환 안 함).

    무스코프(현장 무관) 존재 probe 로 '타 현장에 살아있는 노드'면 OrgCrossSiteError(403·IDOR),
    어디에도 없으면(미존재·삭제됨) OrgNodeNotFoundError(404)를 던진다. 두 예외 모두 ValueError
    하위라, 사유를 구분하지 않는 기존 호출부는 무회귀로 그대로 동작한다."""
    exists_elsewhere = (await db.execute(select(SalesOrgNode.id).where(
        SalesOrgNode.id == node_id, SalesOrgNode.deleted_at.is_(None)))).scalar_one_or_none()
    if exists_elsewhere is not None:
        raise OrgCrossSiteError(f"{label}가 다른 현장 소속입니다(현장 소속 노드만 이동 가능)")
    raise OrgNodeNotFoundError(f"{label}를 찾을 수 없습니다")


async def move_subtree(db: AsyncSession, site_id, node_id, new_parent_id, by=None):
    """노드(및 그 하위 전체)를 새 부모 아래로 옮긴다 — ltree 경로 재기록.

    ★[현장격리·IDOR 차단] 과거엔 node/new_parent 를 id 만으로 '전역' 조회해(site_id 스코프 없음)
      A현장 관리자가 new_parent_id 에 B현장 노드를 넣어 교차테넌트 서브트리 이동이 가능했다
      (현장 격리 우회). assign_user_to_node 와 동일하게 node·new_parent 조회 WHERE 에
      site_id == ctx.site_id 를 걸고, 둘 다 호출자 현장 소속인지 일치검증한다. 경로 UPDATE 의
      WHERE 에도 AND site_id = :sid 를 추가해(같은 라벨이 타 현장에 우연히 있어도) 본 현장
      서브트리만 재기록한다. site_id 인자는 엔드포인트가 ctx.site_id 로 넘긴다.

    ★[사이클 가드] 새 부모가 이동노드 자신이거나 그 하위면(new_parent.path 가 node.path 를 접두로
      가짐) 거부한다(ValueError). a.b.c 를 a.b.c·a.b.c.d 아래로 옮기면 WHERE path<@:old 가 새 부모
      까지 재기록해 자기참조/고아로 트리가 깨지기 때문이다.

    ★[subtree 이동 깨짐 수정] 과거 SQL 은 `:new`(=새부모.이동노드라벨) 에다 다시
      `subpath(path, nlevel(:old)-1)`(=이동노드라벨부터의 잔여경로)을 이어붙여, 이동노드 라벨이
      '두 번' 들어갔다(예: 새부모 x.y, 이동노드 a.b.c → 결과 x.y.cc, 하위 a.b.c.d → x.y.cc.d).
      이는 트리를 망가뜨린다. 올바른 식은 '새부모경로 || (이동노드라벨부터의 잔여경로)' 다:
        - 이동노드 자신 a.b.c: subpath(a.b.c, nlevel(a.b.c)-1)=c → x.y || c = x.y.c
        - 하위    a.b.c.d : subpath(a.b.c.d, nlevel(a.b.c)-1)=c.d → x.y || c.d = x.y.c.d
      따라서 SQL 에는 라벨을 뺀 '새부모 경로'(:new_parent)를 넘기고, ltree '끼리' 이어붙인다
      (text2ltree(:new_parent) || subpath(...)). ltree||ltree 는 점 구분자를 자동으로 넣으므로
      (`'x.y'::ltree || 'c.d'::ltree = x.y.c.d`) 구분자 누락 없이 정확히 재기록된다. 이력(to_path)
      에는 이동노드의 최종 전체경로(new_full)를 기록한다.
    """
    # ★[MEDIUM·TOCTOU 차단(iter-4)] 과거엔 사이클가드(node.path/new_parent.path 읽기) 뒤 경로 UPDATE 를
    #   advisory-lock 없이 수행했다. 동시 이동 2건이 인터리브하면 둘 다 '읽은 시점'엔 가드를 통과한 채
    #   서로의 결과를 못 보고 UPDATE 해 사이클/고아가 생길 수 있었다(create_node/_ensure 와 비대칭).
    #   해결: 본 현장(site_id) 키로 advisory-lock 을 먼저 잡고(같은 현장 이동을 직렬화), 그 '뒤'에
    #   node/new_parent 를 (재)조회→사이클가드→UPDATE 한다. 락은 트랜잭션 종료(commit/rollback) 시
    #   자동 해제(pg_advisory_xact_lock)되어 누수가 없다. 2-인자 형(베이스, hashtext(site_id))이라
    #   현장마다 다른 락이라 타 현장 이동은 막지 않는다(현장 내부에서만 직렬화).
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:k, hashtext(:sid))"),
        {"k": _LOCK_ORG_MOVE, "sid": str(site_id)})
    # ★현장격리: 두 노드 모두 호출자 현장(site_id) 소속이어야 한다(타 현장 노드는 None → 거부).
    #   ★락을 잡은 '뒤'에 (재)조회한다 — 동시 이동이 직렬화돼 가드 시점의 path 가 최신임을 보장(TOCTOU 제거).
    #   ★[사유별 분리(iter-4)] 본 현장 스코프 조회가 None 이면, '어디에도 없음(404)'인지 '타 현장 소속
    #     (403·IDOR)'인지 무스코프 존재 probe 로 구분해 전용 예외를 던진다(엔드포인트가 사유별 매핑).
    node = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.id == node_id, SalesOrgNode.site_id == site_id,
        SalesOrgNode.deleted_at.is_(None)))).scalar_one_or_none()
    if node is None:
        await _raise_node_reason(db, node_id, "이동할 조직 노드")
    new_parent = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.id == new_parent_id, SalesOrgNode.site_id == site_id,
        SalesOrgNode.deleted_at.is_(None)))).scalar_one_or_none()
    if new_parent is None:
        await _raise_node_reason(db, new_parent_id, "새 상위 노드")
    old = str(node.path)
    new_parent_path = str(new_parent.path)
    # ★사이클 가드: 새 부모가 이동노드 자신/하위면 거부(rewrite_subtree_path 와 동일 규칙) → 422(입력오류).
    if _is_self_or_descendant(old, new_parent_path):
        raise OrgCycleError("노드를 자기 자신이나 그 하위 조직 아래로는 옮길 수 없습니다")
    label = old.split(".")[-1]
    new_full = f"{new_parent_path}.{label}"  # 이동노드의 최종 전체경로(이력 기록용)
    # ★UPDATE WHERE 에도 site_id 를 걸어(라벨이 우연히 타 현장에 있어도) 본 현장 서브트리만 재기록.
    await db.execute(text(
        "UPDATE sales_org_nodes "
        "SET path = text2ltree(:new_parent) || subpath(path, nlevel(:old) - 1) "
        "WHERE path <@ :old AND site_id = :sid"
    ), {"new_parent": new_parent_path, "old": old, "sid": str(site_id)})
    # ★인접리스트 동기화: ltree path 와 parent_id 가 함께 정합하도록 이동노드의 직속 부모를 갱신.
    node.parent_id = new_parent.id
    db.add(SalesOrgMembershipHistory(node_id=node_id, action="MOVE", from_path=old, to_path=new_full, by=by))
    await db.flush()
