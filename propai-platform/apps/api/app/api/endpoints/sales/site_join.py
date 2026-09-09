"""Stage 2 — 현장 **발견 → 신청 → 승인**.

## 왜 이 모듈이 필요한가 (2026-09-09 · 전제는 계획서 §1 에 실측표로 있다)

사용자 요구: *"모든 회원은 … 등록된 모든 분양현장을 확인하고 등록신청을 하고
관리자 및 상위레벨이 승인할경우 … 접속가능하도록"*.

측정해 보니 **세 자리가 비어 있었다**:

| # | 실측 | 무엇이 없나 |
|---|---|---|
| P1 | `views.list_sites` = `organization_id == user.tenant_id`(13건) · `site_auth.my_sites` = 멤버십 ∪ 소유테넌트 ∪ **superadmin=전체**(14건) | 일반 회원의 **발견** 경로 |
| P3 | `market.apply_post(post_id, …)` — 신청 대상이 **공고**다 | **공고 없는 현장**에 신청할 방법 |
| P5 | `SalesSite` 에 가시성 플래그 **부재** | 「무엇을 공개할지」의 기준 |

★**「전체 현장 조회」는 이미 있었다** — `my_sites` 분기 (c). 없는 것은 «전체 현장»이 아니라
  **«일반 회원에게 축소 필드로 주는 발견 경로»** 다. 그래서 이 모듈은 새 조회를 만드는 것이
  아니라, **같은 모집단을 다른 권한·다른 필드로** 준다.

## 격리 — 무엇을 싣고 무엇을 안 싣나

발견 목록은 `site_id · site_code · site_name · development_type · status` + **내 관계**만 싣는다.
★`organization_id` 는 **싣지 않는다.** `sales_sites` 는 테넌트에 묶여 있는데 발견 목록은 그
경계를 넘으므로(사용자 결정), «어느 시행사의 현장인가» 까지 새면 그건 요구를 넘어선 노출이다.
오늘 넘는 양은 **현장 1건**(총 14 − 이 테넌트 13)이지만, 플랫폼이 커지면 이 판단이 값을 갖는다.

현장 **안의** 데이터(세대·계약·수수료·고객)는 이 모듈이 한 건도 주지 않는다 —
그것은 계속 멤버십과 현장 토큰이 가른다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db

# ★사유 어휘를 **채용 승인 경로와 공유한다**. 두 승인 경로가 서로 다른 말을 하면
#   화면이 번역표를 두 벌 갖게 되고, 그 순간 하나가 낡는다.
#   (순환 없음 — `market` 은 이 모듈을 임포트하지 않는다.
#    ★그 방향은 `tests/test_site_join_pipeline.py::test_no_import_cycle_market_does_not_depend_on_join`
#      이 잠근다. 앞 판은 그 락을 **내가 지워 놓고** 이 주석만 남겨 «면역» 을 거짓 주장했다.)
from app.api.endpoints.sales.market import _LINKED_REASONS

# ★판정은 **서비스 층**에 산다(`org/join.py`) — 라우터에 두면 FastAPI 의존 때문에
#   아무도 태울 수 없다(PR #1021 에서 정확히 그 형태로 데였다). 여기 남는 것은 HTTP 매핑뿐이다.
from app.services.sales.org.join import (
    SponsorNotEligibleError,
    SponsorNotFoundError,
    link_membership,
    resolve_approver_node,
    resolve_sponsor_node,
)
from app.services.sales.transition import claim_status_transition
from apps.api.database.models.sales.site_org import SalesOrgNode, SalesSite

site_join_router = APIRouter(tags=["sales-join"])

# ── 신청 상태 ────────────────────────────────────────────────────────────────
# ★값을 **한 곳**에 둔다 — 프론트가 여기서 파생하고, 락이 «코드가 내는 값 ⊆ 이 목록» 을 잠근다.
#   (PR #1021 에서 «사유가 여러 상황을 한 값으로 덮는» 결함을 겪은 뒤의 규율이다.)
JOIN_STATUSES = ("pending", "approved", "rejected", "cancelled")

_JOIN_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_site_join_requests ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  user_id uuid NOT NULL,"
    "  message text,"
    # ★신청 시 확정되는 **희망 직속 상위**. 승인자가 아니라 이것이 부모가 된다 —
    #   그래야 «누가 먼저 누르느냐» 로 수수료 체인이 갈리지 않는다.
    "  sponsor_node_id uuid,"
    "  status varchar(20) NOT NULL DEFAULT 'pending',"
    "  decided_by uuid,"
    "  decided_at timestamptz,"
    "  decision_note text,"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)

# ★부분 유니크 인덱스 — 같은 사람이 같은 현장에 **대기 중 신청을 두 개** 만들 수 없다.
#   전체 유니크로 걸면 «거절당한 뒤 다시 신청» 이 원리적으로 막힌다(정당한 재신청을 거부하는
#   가드는 그 자체가 결함이다 — 저장소가 「유일성이 정당한 재전송을 거부한다」로 이미 데였다).
_JOIN_IDX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_join_pending_one "
    "ON sales_site_join_requests (site_id, user_id) WHERE status = 'pending'",
    "CREATE INDEX IF NOT EXISTS ix_join_site_status "
    "ON sales_site_join_requests (site_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_join_user "
    "ON sales_site_join_requests (user_id)",
    # ★기존 테이블(이 컬럼 이전에 만들어진 것)에도 붙인다 — 멱등.
    "ALTER TABLE sales_site_join_requests ADD COLUMN IF NOT EXISTS sponsor_node_id uuid",
)

_ENSURED = False


async def _ensure(db: AsyncSession) -> None:
    """멱등 생성 — 프로세스당 1회(요청마다 DDL 은 락을 잡아 지연·503 을 만든다)."""
    global _ENSURED
    if _ENSURED:
        return
    await db.execute(text(_JOIN_DDL))
    for idx in _JOIN_IDX:
        await db.execute(text(idx))
    await db.commit()   # DDL 영속 보장 후에만 플래그를 닫는다(실패 시 다음 호출이 재시도).
    _ENSURED = True


# ═══════════════════════════════════════════════════════════════════════════
# 1) 발견 — 모든 현장 + 내 관계
# ═══════════════════════════════════════════════════════════════════════════
@site_join_router.get("/sites/discover", summary="등록된 모든 분양현장 + 내 관계(발견)")
async def discover_sites(db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)) -> list[dict]:
    """모든 미삭제 현장을 **축소 필드**로 준다 + 내가 그 현장과 어떤 관계인가.

    `membership`: `active`(이미 멤버) · `pending`(신청 대기) · `none`(신청 가능)

    ★세 값이 **서로 다른 다음 행동**을 뜻한다 — 「들어간다 / 기다린다 / 신청한다」.
      하나로 뭉치면 화면이 무엇을 보여줄지 정할 수 없다.
    """
    await _ensure(db)

    sites = (await db.execute(select(SalesSite).where(
        SalesSite.deleted_at.is_(None)).order_by(SalesSite.created_at.desc()))).scalars().all()

    # 내 멤버십(현장 집합) — 한 번의 조회로.
    member_ids = {
        str(sid) for (sid,) in (await db.execute(select(SalesOrgNode.site_id).where(
            SalesOrgNode.user_id == user.id,
            SalesOrgNode.active.is_(True),
            SalesOrgNode.deleted_at.is_(None)))).all()
    }
    # 내 소유 테넌트 현장도 「이미 접근 가능」이다(my_sites 분기 (b) 와 같은 기준).
    tenant_id = getattr(user, "tenant_id", None)
    # 내 대기 중 신청.
    pending_ids = {
        str(r[0]) for r in (await db.execute(text(
            "SELECT site_id FROM sales_site_join_requests "
            "WHERE user_id = :u AND status = 'pending'"), {"u": str(user.id)})).all()
    }

    out: list[dict] = []
    for s in sites:
        sid = str(s.id)
        if sid in member_ids or (tenant_id and s.organization_id == tenant_id):
            rel = "active"
        elif sid in pending_ids:
            rel = "pending"
        else:
            rel = "none"
        out.append({
            "site_id": sid,
            "site_code": s.site_code,
            "site_name": s.site_name,
            "development_type": s.development_type,
            "status": s.status,
            "membership": rel,
            # ★`organization_id` 는 **의도적으로 뺀다**(모듈 독스트링 「격리」 참조).
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 2) 신청
# ═══════════════════════════════════════════════════════════════════════════
class JoinRequestBody(BaseModel):
    """★`sponsor_email` 은 **필수**다(채택된 설계 — 벤치마킹 R2).

    누구 아래로 들어갈지를 **신청 시점에** 정한다. 승인 시점에 정하면 승인자가 여럿인 현장에서
    **누가 먼저 누르느냐로 조상 체인이 갈리고**, 정산이 `chain[0]` 을 보므로
    **수수료 귀속이 클릭 순서에 좌우된다.**

    ★목록이 아니라 이메일인 이유는 `org/join.resolve_sponsor_node` 독스트링에 있다
      (남의 현장 조직도를 보여 주지 않으려고).
    """

    sponsor_email: str = Field(min_length=3, max_length=320,
                               description="나를 이 현장에 부른 담당자의 이메일(희망 직속 상위)")
    message: str | None = Field(default=None, max_length=1000)


@site_join_router.post("/sites/{site_id}/join-requests", summary="현장 등록신청(공고 불요)")
async def create_join_request(site_id: uuid.UUID, body: JoinRequestBody,
                              db: AsyncSession = Depends(get_db),
                              user=Depends(get_current_user)) -> dict:
    """현장을 **직접** 대상으로 신청한다.

    ★종전에는 신청이 **공고(job_posts)** 를 대상으로만 가능했다(`market.apply_post`).
      공고가 없는 현장에는 «들어가고 싶다» 를 말할 방법이 아예 없었다 — 계획서 P3.

    멱등: 이미 멤버면 `already_member`, 이미 대기 중이면 그 신청을 **그대로 돌려준다**
    (새로 만들지 않는다 — 부분 유니크 인덱스와 같은 계약을 코드에서도 지킨다).
    """
    await _ensure(db)

    site = (await db.execute(select(SalesSite).where(
        SalesSite.id == site_id, SalesSite.deleted_at.is_(None)))).scalar_one_or_none()
    if site is None:
        raise HTTPException(404, "현장을 찾을 수 없습니다")

    already = (await db.execute(select(SalesOrgNode.id).where(
        SalesOrgNode.site_id == site_id, SalesOrgNode.user_id == user.id,
        SalesOrgNode.active.is_(True),
        SalesOrgNode.deleted_at.is_(None)))).first()
    if already:
        # ★`status` 는 **행 상태**의 어휘다(`JOIN_STATUSES`). 「이미 멤버」는 행이 아예 없는
        #   **처리 결과**라 같은 키에 실으면 두 어휘가 섞인다 — 락이 그 혼선을 짚었다(2026-09-09).
        #   ⇒ 결과는 전용 필드로 말한다. 행이 없으면 `status` 는 `None` 이다.
        return {"status": None, "already_member": True,
                "site_id": str(site_id), "request_id": None}

    existing = (await db.execute(text(
        "SELECT id FROM sales_site_join_requests "
        "WHERE site_id = :s AND user_id = :u AND status = 'pending'"),
        {"s": str(site_id), "u": str(user.id)})).first()
    if existing:
        # ★새로 만들지 않는다. 같은 요청을 두 번 눌러도 대기열이 부풀지 않는다.
        return {"status": "pending", "already_member": False, "site_id": str(site_id),
                "request_id": str(existing[0]), "idempotent": True}

    # ★`ON CONFLICT DO NOTHING` — SELECT 와 INSERT 사이에 남이 끼어들면(두 탭·두 기기)
    #   부분 유니크 인덱스가 `IntegrityError` 를 던져 **정당한 재전송이 500** 이 됐다.
    #   («유일성 제약은 정당한 멱등 재전송을 거부한다» — 저장소가 이미 데인 형태.)
    # ★sponsor 를 **여기서** 확정한다(승인 시점이 아니라). 못 찾으면 400 — 신청 자체를 안 만든다.
    try:
        sponsor = await resolve_sponsor_node(db, site_id, body.sponsor_email)
    except SponsorNotEligibleError as e:
        raise HTTPException(409, str(e)) from e
    except SponsorNotFoundError as e:
        raise HTTPException(400, str(e)) from e

    row = (await db.execute(text(
        "INSERT INTO sales_site_join_requests (site_id, user_id, message, sponsor_node_id) "
        "VALUES (:s, :u, :m, :sp) ON CONFLICT DO NOTHING RETURNING id"),
        {"s": str(site_id), "u": str(user.id), "m": body.message,
         "sp": str(sponsor.id)})).first()
    if row is None:
        # 경쟁에서 졌다 — 남이 만든 그 신청을 **그대로 돌려준다**(터뜨리지 않는다).
        row = (await db.execute(text(
            "SELECT id FROM sales_site_join_requests "
            "WHERE site_id = :s AND user_id = :u AND status = 'pending'"),
            {"s": str(site_id), "u": str(user.id)})).first()
        await db.commit()
        return {"status": "pending", "already_member": False, "site_id": str(site_id),
                "request_id": str(row[0]) if row else None, "idempotent": True}
    await db.commit()
    return {"status": "pending", "already_member": False, "site_id": str(site_id),
            "request_id": str(row[0]), "idempotent": False}


@site_join_router.delete("/join-requests/{request_id}", summary="내 신청 취소")
async def cancel_join_request(request_id: uuid.UUID,
                              db: AsyncSession = Depends(get_db),
                              user=Depends(get_current_user)) -> dict:
    """신청자 본인만 취소할 수 있다.

    ★취소를 두는 이유: 취소가 없으면 잘못 누른 신청이 **영원히 대기열에** 남고,
      부분 유니크 인덱스 때문에 **다시 신청할 수도 없다**(가드가 정상 사용을 막는 형태).
    """
    await _ensure(db)
    r = (await db.execute(text(
        "UPDATE sales_site_join_requests SET status = 'cancelled', updated_at = now() "
        "WHERE id = :i AND user_id = :u AND status = 'pending' RETURNING id"),
        {"i": str(request_id), "u": str(user.id)})).first()
    await db.commit()
    if r is None:
        # 남의 신청인지 · 이미 처리됐는지를 **가르지 않는다**(존재 여부가 새면 IDOR 단서다).
        raise HTTPException(404, "취소할 수 있는 대기 중 신청이 없습니다")
    return {"status": "cancelled", "request_id": str(request_id)}


# ═══════════════════════════════════════════════════════════════════════════
# 3) 승인 — 「관리자 및 상위레벨」
# ═══════════════════════════════════════════════════════════════════════════
@site_join_router.get("/sites/{site_id}/join-requests", summary="현장 신청 목록(승인자)")
async def list_join_requests(site_id: uuid.UUID, status: str = "pending",
                             db: AsyncSession = Depends(get_db),
                             user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    if status not in JOIN_STATUSES:
        raise HTTPException(400, f"status 는 {', '.join(JOIN_STATUSES)} 중 하나여야 합니다")

    can, _ = await resolve_approver_node(db, site_id, user)
    if not can:
        raise HTTPException(403, "이 현장의 신청을 볼 권한이 없습니다")

    rows = (await db.execute(text(
        "SELECT r.id, r.user_id, u.name, u.email, r.message, r.status, r.created_at "
        "  FROM sales_site_join_requests r LEFT JOIN users u ON u.id = r.user_id "
        " WHERE r.site_id = :s AND r.status = :st ORDER BY r.created_at ASC"),
        {"s": str(site_id), "st": status})).all()
    return {"items": [{
        "request_id": str(r[0]), "user_id": str(r[1]), "name": r[2], "email": r[3],
        "message": r[4], "status": r[5],
        "created_at": r[6].isoformat() if r[6] else None,
    } for r in rows], "count": len(rows)}


async def _sponsor_of(db: AsyncSession, sponsor_node_id):
    """신청에 박힌 sponsor 노드를 **승인 시점에 다시 확인**한다.

    ★신청 후 승인 전에 그 사람이 해촉될 수 있다. 죽은 노드를 부모로 쓰면 고아 체인이 생기므로,
      살아 있지 않으면 `None` 을 돌려 `link_membership` 의 **보류 경로**로 떨어뜨린다
      (조용히 승인자 노드로 바꿔치기하지 **않는다** — 그러면 클릭 순서 의존이 되살아난다).
    """
    if sponsor_node_id is None:
        return None
    return (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.id == sponsor_node_id,
        SalesOrgNode.active.is_(True),
        SalesOrgNode.deleted_at.is_(None)))).scalars().first()


class DecideBody(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=1000)


@site_join_router.post("/join-requests/{request_id}/decide", summary="신청 승인/거절")
async def decide_join_request(request_id: uuid.UUID, body: DecideBody,
                              db: AsyncSession = Depends(get_db),
                              user=Depends(get_current_user)) -> dict:
    """승인하면 **`create_node` 를 경유해** 멤버십을 만든다.

    ★`create_node` 를 쓰는 것이 이 함수의 핵심이다. raw INSERT 로 넣으면
      **루트 고아 노드**가 생기고, 정산이 `chain[0]` 을 대행사로 보므로
      **수수료 RESIDUAL 전액이 신입에게** 꽂힌다(PR #1021 이 봉합한 그 결함).
      이 PR 을 #1021 **위에 쌓는 이유**가 그것이다 — main 에 먼저 들어가면
      가드 없는 `create_node` 를 쓰게 되어 **새 문으로 같은 결함이 재유입**된다.

    ★부모는 **승인자의 노드**다(`resolve_approver_node` 가 함께 준다). 그러면 수수료 체인이
      처음부터 대행사에서 시작한다. 승인자가 플랫폼 운영자라 노드가 없으면
      현장의 AGENCY 루트에 붙이고, 그마저 없으면 **보류**한다(고아를 만들지 않는다).
    """
    await _ensure(db)

    req = (await db.execute(text(
        "SELECT site_id, user_id, status, sponsor_node_id "
        "  FROM sales_site_join_requests WHERE id = :i"),
        {"i": str(request_id)})).first()
    if req is None:
        raise HTTPException(404, "신청을 찾을 수 없습니다")
    site_id, applicant_id, cur_status, sponsor_node_id = req[0], req[1], req[2], req[3]

    # ★★**자기 승인 차단**(2026-09-09 R1 C-5 · R2 가 «여전히 가능» 으로 재확인).
    #   플랫폼 역할(superadmin/developer)은 조직노드가 없어 「이미 멤버」 검사를 통과해
    #   자기 신청을 만들 수 있고, 그다음 플랫폼 분기로 **자기가 자기를 승인**해
    #   대행사 루트 아래에 자신을 넣을 수 있었다. 승인은 **남이 하는 것**이다.
    if str(applicant_id) == str(user.id):
        raise HTTPException(403, "자기 신청은 스스로 승인·거절할 수 없습니다")

    can, approver_node = await resolve_approver_node(db, site_id, user)
    if not can:
        raise HTTPException(403, "이 현장의 신청을 결정할 권한이 없습니다")

    new_status = "approved" if body.approve else "rejected"
    if cur_status == new_status:
        # ★★**멱등은 「부작용 없음」이지 「아무것도 안 함」이 아니다**(2026-09-09 R2 리뷰 J-1).
        #   앞 판은 여기서 무조건 단락했다. 그런데 `ORG_NOT_SEEDED` 로 보류되면 신청은 이미
        #   `approved` 이므로, 조직도를 시드하고 **다시 승인해도 이 분기에 먼저 걸려**
        #   멤버십 연결이 **원리적으로 다시 안 불렸다.**
        #   ★그리고 이 PR 이 그 안내를 화면에 올렸다 — «조직도를 만든 뒤 다시 승인해 주세요» →
        #   지시대로 하면 «이미 처리된 신청이라 변경된 것이 없습니다». **승인자가 막다른 길에 갇힌다.**
        #   라이브 13현장 중 10현장이 조직도 미시드라 이건 드문 경로가 아니다.
        #   ⇒ 승인 재시도는 **멤버십 부재를 다시 확인**하고, 없으면 연결을 다시 태운다.
        if not body.approve:
            return {"request_id": str(request_id), "status": new_status,
                    "idempotent": True, "membership_linked": False,
                    "membership_reason": "IDEMPOTENT_NO_CHANGE"}
        retry_reason = await link_membership(db, site_id, applicant_id, approver_node,
                                             sponsor_node=await _sponsor_of(db, sponsor_node_id))
        await db.commit()
        return {"request_id": str(request_id), "status": new_status, "idempotent": True,
                "membership_linked": retry_reason in _LINKED_REASONS,
                "membership_reason": retry_reason}
    if cur_status != "pending":
        raise HTTPException(409, f"이미 처리된 신청입니다(현재 상태: {cur_status})")

    # ★★**CAS** — 읽은 상태가 그대로일 때만 바꾼다(적대 리뷰 B-1).
    #   종전엔 `WHERE id` 만 걸어, 두 승인자가 동시에 눌러도 **둘 다 통과**했고 둘 다
    #   멤버십 연결로 들어가 `create_node` 가 **두 번** 실행됐다.
    #   `sales_org_nodes` 에 `(site_id,user_id)` UNIQUE 가 없어(`deps_sales:41`) 조용히 성공한다.
    claimed = await claim_status_transition(
        db, "sales_site_join_requests", request_id,
        expected_status="pending", new_status=new_status,
        extra_set=", decided_by = :by, decided_at = now(), decision_note = :n",
        params={"by": str(user.id), "n": body.note})
    if not claimed:
        await db.rollback()
        raise HTTPException(409, "이미 다른 사람이 이 신청을 처리했습니다")

    reason = "DECLINED"
    if body.approve:
        reason = await link_membership(db, site_id, applicant_id, approver_node,
                                       sponsor_node=await _sponsor_of(db, sponsor_node_id))
    await db.commit()
    return {"request_id": str(request_id), "status": new_status, "idempotent": False,
            "membership_linked": reason in _LINKED_REASONS,
            "membership_reason": reason}
