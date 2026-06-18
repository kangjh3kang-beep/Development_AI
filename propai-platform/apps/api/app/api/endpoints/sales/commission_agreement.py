"""Phase1-G 수수료 더치페이 — 합의기반 분배 + 다자동의 + 변경재동의 + 해시체인.

한 계약(contract)의 수수료를 참여자(직원/팀장/본부장 등 org_node/user)별로
비율(%) 또는 금액으로 분배하는 '합의'를 만들고, 참여자 전원의 동의(서명)로 확정한다.

기존 수수료 구조와의 관계
- 기존 sales_commission_splits 는 event(수수료 발생) 기준 '계산 결과' 저장용(node·rate·amount).
  여기엔 '합의/동의 상태'·'참여자별 서명'·'변경 시 재동의' 개념이 없어 더치페이 합의에 부족.
- 따라서 합의/동의 전용 2개 테이블을 멱등(_ensure)으로 신규 생성한다(기존 무파괴).
    sales_commission_split_agreements : 합의 헤더(계약·총수수료·상태·참여자 스냅샷)
    sales_commission_split_consents    : 참여자별 동의(서명)·거부 레코드

다자동의 플로우
  생성  → status=pending (참여자별 consent=pending)
  동의  → 본인 consent=consented; 전원 동의 시 status=confirmed
  거부  → 본인 consent=rejected; 합의 status=rejected
  변경  → 참여자/비율/금액 갱신 + 기존 동의 전부 무효화(pending) → status=pending → 전원 재동의 필요
  해시  → 생성·각 동의·확정·변경·거부 이벤트를 analysis_ledger(append_analysis)에 best-effort 기록

site 격리는 sales_ctx(SalesCtx.site_id) 로 강제하고, 권한은 합의 참여자 또는 현장 관리자만.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, sales_ctx

commission_agreement_router = APIRouter(tags=["sales-commission-agreement"])
logger = structlog.get_logger(__name__)

# 합의를 만들거나/변경할 수 있는 현장 관리자 역할(참여자는 별도로 항상 본인 동의 가능)
_MANAGER_ROLES = {"SUPERADMIN", "DEVELOPER", "AGENCY", "GM_DIRECTOR", "DIRECTOR"}
# 비율합 검증 허용오차(%) / 금액합 검증 허용오차(원)
_RATIO_TOL = 0.01
_AMOUNT_TOL = 1


# ── 멱등 테이블(_ensure) ─────────────────────────────────────────────────────
_AGREEMENT_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_commission_split_agreements ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  contract_id uuid NOT NULL,"
    "  total_amount numeric(16,0) NOT NULL,"
    "  basis varchar(8) NOT NULL,"            # RATIO | AMOUNT
    "  status varchar(12) NOT NULL DEFAULT 'pending',"  # pending|confirmed|rejected
    "  version int NOT NULL DEFAULT 1,"
    "  created_by uuid,"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now(),"
    "  confirmed_at timestamptz"
    ")"
)
_CONSENT_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_commission_split_consents ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  agreement_id uuid NOT NULL REFERENCES sales_commission_split_agreements(id) ON DELETE CASCADE,"
    "  participant_seq int NOT NULL,"
    "  user_id uuid,"
    "  node_id uuid,"
    "  ratio numeric(7,4),"
    "  amount numeric(16,0),"
    "  status varchar(12) NOT NULL DEFAULT 'pending',"  # pending|consented|rejected
    "  decided_at timestamptz,"
    "  decided_round int NOT NULL DEFAULT 0"            # 어느 합의버전에서 결정했는지(변경 시 재동의 추적)
    ")"
)


async def _ensure(db: AsyncSession) -> None:
    """합의/동의 테이블을 멱등 생성(배포 후 최초 호출 시 1회). 기존 수수료 테이블 무파괴."""
    await db.execute(text(_AGREEMENT_DDL))
    await db.execute(text(_CONSENT_DDL))


# ── 스키마 ───────────────────────────────────────────────────────────────────
class Participant(BaseModel):
    user_id: uuid.UUID | None = None
    node_id: uuid.UUID | None = None
    ratio: float | None = None    # 비율(%) — basis=RATIO
    amount: int | None = None     # 금액(원) — basis=AMOUNT


class AgreementCreate(BaseModel):
    contract_id: uuid.UUID
    total_amount: int
    participants: list[Participant]


class ParticipantsUpdate(BaseModel):
    participants: list[Participant]
    total_amount: int | None = None  # 미지정 시 기존 총액 유지


# ── 검증 ─────────────────────────────────────────────────────────────────────
def _validate_participants(participants: list[Participant], total_amount: int) -> str:
    """참여자 분배 검증 후 basis('RATIO'|'AMOUNT') 반환. 위반 시 HTTPException(400)."""
    if not participants:
        raise HTTPException(400, "참여자가 비어 있습니다")
    if total_amount <= 0:
        raise HTTPException(400, "총 수수료(total_amount)는 0보다 커야 합니다")
    for p in participants:
        if not (p.user_id or p.node_id):
            raise HTTPException(400, "각 참여자는 user_id 또는 node_id 중 하나가 필요합니다")

    has_ratio = any(p.ratio is not None for p in participants)
    has_amount = any(p.amount is not None for p in participants)
    if has_ratio and has_amount:
        raise HTTPException(400, "비율(ratio)과 금액(amount)을 혼용할 수 없습니다 — 하나로 통일하세요")
    if not has_ratio and not has_amount:
        raise HTTPException(400, "참여자별 비율(ratio) 또는 금액(amount)을 입력하세요")

    if has_ratio:
        if any(p.ratio is None for p in participants):
            raise HTTPException(400, "일부 참여자의 비율(ratio)이 비어 있습니다")
        if any((p.ratio or 0) < 0 for p in participants):
            raise HTTPException(400, "비율은 음수가 될 수 없습니다")
        total = sum(float(p.ratio or 0) for p in participants)
        if abs(total - 100.0) > _RATIO_TOL:
            raise HTTPException(400, f"비율 합이 100%가 아닙니다(현재 {total:.4f}%)")
        return "RATIO"

    if any(p.amount is None for p in participants):
        raise HTTPException(400, "일부 참여자의 금액(amount)이 비어 있습니다")
    if any((p.amount or 0) < 0 for p in participants):
        raise HTTPException(400, "금액은 음수가 될 수 없습니다")
    total = sum(int(p.amount or 0) for p in participants)
    if abs(total - int(total_amount)) > _AMOUNT_TOL:
        raise HTTPException(400, f"금액 합({total})이 총 수수료({total_amount})와 일치하지 않습니다")
    return "AMOUNT"


async def _ledger(ctx: SalesCtx, agreement_id: uuid.UUID, event: str, payload: dict) -> None:
    """합의 이벤트를 해시체인 원장에 기록(변조탐지·분쟁증거). 본 흐름(합의 처리)은 막지 않되,
    실패를 '조용히 무시'하지 않는다 — 분쟁 대비 정산 원장 무결성 보존이 목적이므로,
    원장 봉인이 실패하면 WARN 로깅 + 감사기록(append_audit)으로 '봉인 실패 사실'을 강제로 남긴다.

    append_analysis 자체가 예외를 흡수하고 dict 를 돌려주므로(ok=False/quota_exceeded), 그
    실패신호도 점검해 audit 로 승격한다(은폐 금지). audit 기록까지 실패하면 그때만 WARN 후 통과.
    """
    tenant_id = getattr(ctx.user, "tenant_id", None)
    tid = str(tenant_id) if tenant_id else None
    failure_reason: str | None = None
    try:
        from app.services.ledger import analysis_ledger_service as ledger
        res = await ledger.append_analysis(
            analysis_type="commission_agreement",
            payload={"event": event, "agreement_id": str(agreement_id),
                     "site_id": str(ctx.site_id), **payload},
            tenant_id=tid,
            project_id=str(agreement_id),
            source="sales_commission",
            created_by=str(ctx.user.id),
        )
        # append_analysis 는 예외를 흡수하고 {ok: False, ...} 를 돌려줄 수 있다 — 실패신호 점검.
        if isinstance(res, dict) and res.get("ok") is False:
            failure_reason = res.get("message") or ("quota_exceeded" if res.get("quota_exceeded") else "append_failed")
    except Exception as e:  # noqa: BLE001 — 원장 기록 실패는 합의 처리를 막지 않음(아래서 audit 로 승격)
        failure_reason = str(e)[:200]

    if failure_reason is None:
        return
    # ★봉인 실패 = 은폐 금지: WARN + 감사기록(audit) 강제 — 분쟁 대비 '봉인 실패' 흔적 보존.
    #   structlog 는 첫 인자(메시지)를 내부적으로 'event' 로 쓰므로, 우리 도메인 이벤트는
    #   반드시 다른 키(ledger_event)로 넘긴다 — event= 키 충돌 시 TypeError 로 로깅 자체가 깨져
    #   '봉인 실패 흔적'을 또 잃는다(은폐의 재은폐). 그래서 키명을 분리한다.
    logger.warning("수수료 합의 원장 봉인 실패 — audit 로 승격", ledger_event=event,
                   agreement_id=str(agreement_id), reason=failure_reason)
    # ★[은폐의 재은폐 차단] append_audit 도 내부에서 예외를 흡수하고 {ok: False}(특히 quota_exceeded)
    #   를 돌려줄 수 있다. 봉인 실패의 가장 흔한 원인이 '쿼터 초과'인데, audit 적재 역시 같은 쿼터에
    #   걸리면 raise 없이 {ok: False} 만 돌아와 '봉인 실패 흔적'까지 조용히 사라진다.
    #   → 예외(append_audit raise) 와 'ok:False 반환'을 동일하게 취급해 최종 WARN 으로 강등한다
    #     (둘 다 실패해도 최소 1줄 로그는 남겨 무음소실을 막는다).
    audit_failed_reason: str | None = None
    try:
        from app.services.ledger import audit_ledger
        ares = await audit_ledger.append_audit(
            action=f"commission_agreement.ledger_seal_failed:{event}",
            user_id=str(ctx.user.id),
            resource_type="commission_agreement",
            resource_id=str(agreement_id),
            tenant_id=tid,
            metadata={"site_id": str(ctx.site_id), "event": event, "reason": failure_reason},
        )
        # append_audit → append_analysis 도 {ok: False, ...} 를 돌려줄 수 있다(예: quota_exceeded).
        if isinstance(ares, dict) and ares.get("ok") is False:
            audit_failed_reason = ares.get("message") or (
                "quota_exceeded" if ares.get("quota_exceeded") else "audit_append_failed")
    except Exception as e2:  # noqa: BLE001 — audit 까지 실패하면 그때만 WARN 후 통과(본 흐름 무영향)
        audit_failed_reason = str(e2)[:200]

    if audit_failed_reason is not None:
        # 봉인도 실패, audit 승격도 실패 — 최소 로그(sealed_failed_and_audit_skipped)로 강등.
        #   (ledger_event 키 사용 — structlog 의 예약 키 'event'(메시지) 충돌 방지.)
        logger.warning("수수료 합의 봉인실패 audit 기록도 실패 — sealed_failed_and_audit_skipped",
                       ledger_event=event, agreement_id=str(agreement_id),
                       seal_reason=failure_reason, audit_reason=audit_failed_reason)


# ── 조회 헬퍼 ────────────────────────────────────────────────────────────────
async def _load_agreement(db: AsyncSession, site_id: uuid.UUID, agreement_id: uuid.UUID) -> dict:
    row = (await db.execute(text(
        "SELECT id, site_id, contract_id, total_amount, basis, status, version,"
        " created_by, created_at, updated_at, confirmed_at"
        " FROM sales_commission_split_agreements WHERE id = :id AND site_id = :sid"),
        {"id": str(agreement_id), "sid": str(site_id)})).first()
    if not row:
        raise HTTPException(404, "합의를 찾을 수 없습니다")
    consents = (await db.execute(text(
        "SELECT participant_seq, user_id, node_id, ratio, amount, status, decided_at, decided_round"
        " FROM sales_commission_split_consents WHERE agreement_id = :id ORDER BY participant_seq"),
        {"id": str(agreement_id)})).all()
    parts = [{"seq": c[0], "user_id": str(c[1]) if c[1] else None,
              "node_id": str(c[2]) if c[2] else None,
              "ratio": float(c[3]) if c[3] is not None else None,
              "amount": int(c[4]) if c[4] is not None else None,
              "status": c[5], "decided_at": str(c[6]) if c[6] else None,
              "decided_round": c[7]} for c in consents]
    consented = sum(1 for p in parts if p["status"] == "consented")
    return {
        "id": str(row[0]), "site_id": str(row[1]), "contract_id": str(row[2]),
        "total_amount": int(row[3]), "basis": row[4], "status": row[5], "version": row[6],
        "created_by": str(row[7]) if row[7] else None,
        "created_at": str(row[8]), "updated_at": str(row[9]),
        "confirmed_at": str(row[10]) if row[10] else None,
        "participants": parts,
        "consent_progress": {"consented": consented, "total": len(parts),
                             "all_consented": len(parts) > 0 and consented == len(parts)},
    }


def _is_participant(agreement: dict, user_id: uuid.UUID) -> bool:
    return any(p["user_id"] == str(user_id) for p in agreement["participants"])


def _hash_inputs(agreement: dict) -> dict:
    """원장 기록용 분배 스냅샷(변조탐지 핵심 입력)."""
    return {"total_amount": agreement["total_amount"], "basis": agreement["basis"],
            "version": agreement["version"],
            "participants": [{"user_id": p["user_id"], "node_id": p["node_id"],
                              "ratio": p["ratio"], "amount": p["amount"]}
                             for p in agreement["participants"]]}


# ── 1) 생성 ──────────────────────────────────────────────────────────────────
@commission_agreement_router.post("/commission/agreements", summary="수수료 더치페이 합의 생성")
async def create_agreement(body: AgreementCreate, db: AsyncSession = Depends(get_db),
                           ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    if ctx.role not in _MANAGER_ROLES:
        raise HTTPException(403, "합의를 생성할 권한이 없습니다(현장 관리자)")
    await _ensure(db)
    basis = _validate_participants(body.participants, body.total_amount)

    ag_id = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO sales_commission_split_agreements"
        " (id, site_id, contract_id, total_amount, basis, status, version, created_by)"
        " VALUES (:id, :sid, :cid, :tot, :basis, 'pending', 1, :by)"),
        {"id": str(ag_id), "sid": str(ctx.site_id), "cid": str(body.contract_id),
         "tot": int(body.total_amount), "basis": basis, "by": str(ctx.user.id)})
    for seq, p in enumerate(body.participants):
        await db.execute(text(
            "INSERT INTO sales_commission_split_consents"
            " (agreement_id, participant_seq, user_id, node_id, ratio, amount, status, decided_round)"
            " VALUES (:aid, :seq, :uid, :nid, :ratio, :amount, 'pending', 0)"),
            {"aid": str(ag_id), "seq": seq,
             "uid": str(p.user_id) if p.user_id else None,
             "nid": str(p.node_id) if p.node_id else None,
             "ratio": p.ratio, "amount": p.amount})
    await db.commit()

    agreement = await _load_agreement(db, ctx.site_id, ag_id)
    await _ledger(ctx, ag_id, "created", _hash_inputs(agreement))
    return agreement


# ── 2) 동의(서명) ────────────────────────────────────────────────────────────
@commission_agreement_router.post("/commission/agreements/{agreement_id}/consent", summary="합의 동의(서명)")
async def consent_agreement(agreement_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                            ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    agreement = await _load_agreement(db, ctx.site_id, agreement_id)
    if agreement["status"] == "rejected":
        raise HTTPException(409, "거부된 합의는 동의할 수 없습니다")
    if not _is_participant(agreement, ctx.user.id):
        raise HTTPException(403, "이 합의의 참여자만 동의할 수 있습니다")

    res = await db.execute(text(
        "UPDATE sales_commission_split_consents"
        " SET status = 'consented', decided_at = now(), decided_round = :ver"
        " WHERE agreement_id = :aid AND user_id = :uid"),
        {"aid": str(agreement_id), "uid": str(ctx.user.id), "ver": agreement["version"]})
    if res.rowcount == 0:
        raise HTTPException(403, "이 합의의 참여자만 동의할 수 있습니다")

    # 전원 동의 시 확정
    now_all = (await db.execute(text(
        "SELECT count(*) FILTER (WHERE status='consented'), count(*)"
        " FROM sales_commission_split_consents WHERE agreement_id = :aid"),
        {"aid": str(agreement_id)})).first()
    confirmed = now_all[0] == now_all[1] and now_all[1] > 0
    if confirmed:
        await db.execute(text(
            "UPDATE sales_commission_split_agreements"
            " SET status = 'confirmed', confirmed_at = now(), updated_at = now()"
            " WHERE id = :aid"), {"aid": str(agreement_id)})
    else:
        await db.execute(text(
            "UPDATE sales_commission_split_agreements SET updated_at = now() WHERE id = :aid"),
            {"aid": str(agreement_id)})
    await db.commit()

    out = await _load_agreement(db, ctx.site_id, agreement_id)
    await _ledger(ctx, agreement_id, "consented",
                  {"user_id": str(ctx.user.id), "version": out["version"],
                   "consent_progress": out["consent_progress"]})
    if confirmed:
        await _ledger(ctx, agreement_id, "confirmed", _hash_inputs(out))
    return out


# ── 3) 거부 ──────────────────────────────────────────────────────────────────
@commission_agreement_router.post("/commission/agreements/{agreement_id}/reject", summary="합의 거부")
async def reject_agreement(agreement_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                           ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    agreement = await _load_agreement(db, ctx.site_id, agreement_id)
    if not _is_participant(agreement, ctx.user.id):
        raise HTTPException(403, "이 합의의 참여자만 거부할 수 있습니다")

    res = await db.execute(text(
        "UPDATE sales_commission_split_consents"
        " SET status = 'rejected', decided_at = now(), decided_round = :ver"
        " WHERE agreement_id = :aid AND user_id = :uid"),
        {"aid": str(agreement_id), "uid": str(ctx.user.id), "ver": agreement["version"]})
    if res.rowcount == 0:
        raise HTTPException(403, "이 합의의 참여자만 거부할 수 있습니다")
    await db.execute(text(
        "UPDATE sales_commission_split_agreements SET status = 'rejected', updated_at = now() WHERE id = :aid"),
        {"aid": str(agreement_id)})
    await db.commit()

    out = await _load_agreement(db, ctx.site_id, agreement_id)
    await _ledger(ctx, agreement_id, "rejected", {"user_id": str(ctx.user.id), "version": out["version"]})
    return out


# ── 4) 변경 제안(동의 리셋 → 재동의 필요) ─────────────────────────────────────
@commission_agreement_router.patch("/commission/agreements/{agreement_id}", summary="합의 변경(동의 리셋·재동의)")
async def update_agreement(agreement_id: uuid.UUID, body: ParticipantsUpdate,
                           db: AsyncSession = Depends(get_db),
                           ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    agreement = await _load_agreement(db, ctx.site_id, agreement_id)
    # 변경 권한: 현장 관리자 또는 기존 참여자(일방 변경 차단을 위해 전원 재동의를 강제)
    if ctx.role not in _MANAGER_ROLES and not _is_participant(agreement, ctx.user.id):
        raise HTTPException(403, "이 합의를 변경할 권한이 없습니다")
    if agreement["status"] == "rejected":
        raise HTTPException(409, "거부된 합의는 변경할 수 없습니다")

    total = int(body.total_amount) if body.total_amount is not None else agreement["total_amount"]
    basis = _validate_participants(body.participants, total)
    new_version = agreement["version"] + 1

    # 기존 동의 전부 무효화: 참여자 명단 자체를 새로 적재(동의 pending 초기화)
    await db.execute(text("DELETE FROM sales_commission_split_consents WHERE agreement_id = :aid"),
                     {"aid": str(agreement_id)})
    for seq, p in enumerate(body.participants):
        await db.execute(text(
            "INSERT INTO sales_commission_split_consents"
            " (agreement_id, participant_seq, user_id, node_id, ratio, amount, status, decided_round)"
            " VALUES (:aid, :seq, :uid, :nid, :ratio, :amount, 'pending', 0)"),
            {"aid": str(agreement_id), "seq": seq,
             "uid": str(p.user_id) if p.user_id else None,
             "nid": str(p.node_id) if p.node_id else None,
             "ratio": p.ratio, "amount": p.amount})
    await db.execute(text(
        "UPDATE sales_commission_split_agreements"
        " SET total_amount = :tot, basis = :basis, status = 'pending', version = :ver,"
        "     confirmed_at = NULL, updated_at = now()"
        " WHERE id = :aid"),
        {"tot": total, "basis": basis, "ver": new_version, "aid": str(agreement_id)})
    await db.commit()

    out = await _load_agreement(db, ctx.site_id, agreement_id)
    await _ledger(ctx, agreement_id, "amended",
                  {"by": str(ctx.user.id), "from_version": agreement["version"], **_hash_inputs(out)})
    return out


# ── 5) 조회 ──────────────────────────────────────────────────────────────────
@commission_agreement_router.get("/commission/agreements", summary="합의 목록 조회(계약별)")
async def list_agreements(contract_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    where = "site_id = :sid"
    params: dict = {"sid": str(ctx.site_id)}
    if contract_id is not None:
        where += " AND contract_id = :cid"
        params["cid"] = str(contract_id)
    rows = (await db.execute(text(
        "SELECT id FROM sales_commission_split_agreements"
        f" WHERE {where} ORDER BY created_at DESC"), params)).all()
    items = [await _load_agreement(db, ctx.site_id, r[0]) for r in rows]
    return {"items": items, "count": len(items)}


@commission_agreement_router.get("/commission/agreements/{agreement_id}", summary="합의 상세(상태·동의현황·해시)")
async def get_agreement(agreement_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    out = await _load_agreement(db, ctx.site_id, agreement_id)
    # 해시체인 최신 항목(있으면) 부착 — 변조탐지·분쟁증거 참조
    try:
        from app.services.ledger import analysis_ledger_service as ledger
        tenant_id = getattr(ctx.user, "tenant_id", None)
        latest = await ledger.get_latest(
            analysis_type="commission_agreement",
            tenant_id=str(tenant_id) if tenant_id else None,
            project_id=str(agreement_id))
        if latest:
            out["ledger"] = {"version": latest.get("version"),
                             "content_hash": latest.get("content_hash"),
                             "created_at": latest.get("created_at")}
    except Exception:  # noqa: BLE001
        pass
    return out
