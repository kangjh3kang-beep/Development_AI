"""Phase1-C 공유·바이럴 — MGM 추천코드 발급/공유링크·QR페이로드/퍼널추적/수수료 귀속훅.

설계(명세 45 C절)
- 공유링크 + QR(방문데스크 mh_desks QR 결합) + Web Share + 카카오알림톡.
- ★MGM 추천코드: 상담사별/현장별 추천코드 → 공유링크(?ref=code) → 방문·계약 추적
  → 조직도(SalesOrgNode user_id)·수수료(sales_commission_*) 자동귀속.

격리/보안 모델
- referral_* 테이블은 PUBLIC/전역 성격(상담사 코드는 현장무관 재사용 가능, site_id 선택).
  테이블명이 sales_/mh_ 접두가 아니므로 sales_rls_bootstrap 동적조회에서 자동 제외 →
  격리는 앱계층 소유자검증(owner_user_id == 현재 사용자)으로 강제한다.
- 코드는 추측·도용 방지를 위해 secrets 기반 base62 8자 랜덤(예측불가).
- 귀속은 코드소유자 = 코드의 owner_user_id 로 확정. customer 당 1귀속(first-touch) 정책 →
  중복귀속 시 기존 귀속 유지(409 아닌 멱등 반환).
- 수수료 자동귀속은 "기록·pending(referral_attributions.status=pending)"까지만 하고
  실제 지급은 기존 수수료 승인흐름(claim→approval→payout)을 거친다(임의 지급 금지).
  계약확정 시 commission_split_id 를 best-effort 로 연결(훅), 미연결이어도 귀속은 보존.
- 추적 이벤트(track)는 랜딩페이지 공개 호출 허용(get_current_user 불필요)하되 코드유효성 검증.
  나머지(발급·목록·귀속·통계)는 전역 SSO(get_current_user) 필요.
- 정보통신망법: 공유 페이로드 안내문구에 수신동의·야간발송 제한·수신거부 고지를 포함.

엔드포인트(prefix=/api/v1/sales)
- POST /referral/codes {kind, site_id?}                내 추천코드 발급(멱등)
- GET  /referral/codes                                 내 코드목록
- GET  /referral/share?code=&site_id=                  공유 페이로드(링크·QR데이터·안내문구)
- POST /referral/track {code, event, visitor_ref?, customer_id?, contract_id?}  퍼널 이벤트(공개)
- POST /referral/attribute {code, customer_id, contract_id?}  귀속 생성(first-touch) + 수수료훅
- GET  /referral/stats?code=&from=&to=                 퍼널 통계(클릭→방문→리드→계약·전환율)
"""

import os
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db

referral_router = APIRouter(tags=["sales-referral"])

# 코드 종류(상담사 개인코드 / 현장 코드)
_KINDS = {"staff", "site"}
# 퍼널 이벤트(순서: click→visit→lead→contract)
_EVENTS = ["click", "visit", "lead", "contract"]
_EVENT_SET = set(_EVENTS)

# 공유링크 베이스(현장 서브도메인 미지정 시 폴백). 환경변수 우선.
_SHARE_BASE = os.getenv("SALES_APP_BASE_URL", "https://4t8t.net").rstrip("/")

# base62 알파벳(혼동문자 포함이나 secrets 랜덤이므로 사람이 입력보다 링크클릭 전제)
_B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# 공유 안내문구(정보통신망법 — 수신동의·야간발송 제한·수신거부 고지)
_SHARE_NOTICE = (
    "본 링크 공유 및 후속 알림(문자·알림톡)은 정보통신망법을 준수합니다. "
    "광고성 정보는 수신자 사전 동의 시에만 발송되며, 야간(21시~익일 08시) 발송이 제한되고, "
    "수신거부(무료수신거부) 안내를 포함합니다."
)


# ── 멱등 테이블(_ensure) ─────────────────────────────────────────────────────
_CODES_DDL = (
    "CREATE TABLE IF NOT EXISTS referral_codes ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  code varchar(16) NOT NULL UNIQUE,"
    "  owner_user_id uuid NOT NULL,"
    "  site_id uuid,"                                  # 선택(현장무관 재사용 가능)
    "  kind varchar(8) NOT NULL DEFAULT 'staff',"      # staff|site
    "  active boolean NOT NULL DEFAULT true,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
# 소유자+종류+현장 조합당 1개(멱등 발급 보장). site_id NULL 은 인덱스에서 coalesce 처리.
_CODES_UNIQ = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_codes_owner"
    " ON referral_codes(owner_user_id, kind, COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid))"
)
_EVENTS_DDL = (
    "CREATE TABLE IF NOT EXISTS referral_events ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  code varchar(16) NOT NULL,"
    "  event varchar(12) NOT NULL,"                    # click|visit|lead|contract
    "  visitor_ref varchar(120),"                      # 익명 방문 식별(쿠키/디바이스 해시)
    "  customer_id uuid,"
    "  contract_id uuid,"
    "  site_id uuid,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_EVENTS_IDX = (
    "CREATE INDEX IF NOT EXISTS ix_referral_events_code"
    " ON referral_events(code, created_at DESC)"
)
_ATTR_DDL = (
    "CREATE TABLE IF NOT EXISTS referral_attributions ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  code varchar(16) NOT NULL,"
    "  owner_user_id uuid NOT NULL,"                   # 귀속 상담사(=코드소유자)
    "  customer_id uuid NOT NULL,"
    "  contract_id uuid,"
    "  site_id uuid,"
    "  status varchar(12) NOT NULL DEFAULT 'pending',"  # pending|confirmed
    "  commission_split_id uuid,"                      # 수수료 연결(승인흐름 거침)
    "  attributed_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
# customer 당 1귀속(first-touch) — 중복귀속 방지.
_ATTR_UNIQ = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_attr_customer"
    " ON referral_attributions(customer_id)"
)


async def _ensure(db: AsyncSession) -> None:
    """추천코드·퍼널이벤트·귀속 테이블 멱등 생성(최초 호출 1회). 기존 무파괴.

    ★ 테이블명이 sales_/mh_ 접두가 아니므로 RLS 부트스트랩 동적조회에서 자동 제외(앱계층 소유자검증).
    """
    await db.execute(text(_CODES_DDL))
    await db.execute(text(_CODES_UNIQ))
    await db.execute(text(_EVENTS_DDL))
    await db.execute(text(_EVENTS_IDX))
    await db.execute(text(_ATTR_DDL))
    await db.execute(text(_ATTR_UNIQ))


def _gen_code(n: int = 8) -> str:
    """secrets 기반 base62 랜덤 코드(추측·도용 방지)."""
    return "".join(secrets.choice(_B62) for _ in range(n))


# ── 스키마 ───────────────────────────────────────────────────────────────────
class CodeCreate(BaseModel):
    kind: str = "staff"                 # staff|site
    site_id: uuid.UUID | None = None    # site 코드 또는 현장한정 staff 코드


class TrackEvent(BaseModel):
    code: str
    event: str                          # click|visit|lead|contract
    visitor_ref: str | None = None
    customer_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None


class AttributeCreate(BaseModel):
    code: str
    customer_id: uuid.UUID
    contract_id: uuid.UUID | None = None


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────
async def _load_code(db: AsyncSession, code: str):
    return (await db.execute(text(
        "SELECT code, owner_user_id, site_id, kind, active FROM referral_codes WHERE code = :c"),
        {"c": code})).first()


async def issue_code(db: AsyncSession, owner_user_id, kind: str, site_id) -> dict:
    """추천코드 발급(멱등) — owner+kind+site 조합이 이미 있으면 기존 코드 반환.

    공통 진입점(엔드포인트 + 방문/계약 자동기록 훅에서 재사용). 호출자가 commit 책임.
    """
    await _ensure(db)
    sid = str(site_id) if site_id else None
    existing = (await db.execute(text(
        "SELECT code FROM referral_codes WHERE owner_user_id = :u AND kind = :k"
        " AND COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid)"
        "   = COALESCE(CAST(:s AS uuid), '00000000-0000-0000-0000-000000000000'::uuid)"),
        {"u": str(owner_user_id), "k": kind, "s": sid})).first()
    if existing:
        return {"code": existing[0], "kind": kind, "site_id": sid, "created": False}

    # 고유 코드 생성(충돌 시 재시도) — UNIQUE 제약과 ON CONFLICT 멱등으로 경쟁 안전화.
    for _ in range(6):
        candidate = _gen_code()
        res = (await db.execute(text(
            "INSERT INTO referral_codes (code, owner_user_id, site_id, kind)"
            " VALUES (:c, :u, CAST(:s AS uuid), :k)"
            " ON CONFLICT (code) DO NOTHING RETURNING code"),
            {"c": candidate, "u": str(owner_user_id), "s": sid, "k": kind})).first()
        if res:
            return {"code": res[0], "kind": kind, "site_id": sid, "created": True}
    # 6회 충돌은 사실상 불가(62^8) — 경쟁 시 owner 유니크로 이미 발급됐을 수 있어 재조회.
    again = (await db.execute(text(
        "SELECT code FROM referral_codes WHERE owner_user_id = :u AND kind = :k"
        " AND COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid)"
        "   = COALESCE(CAST(:s AS uuid), '00000000-0000-0000-0000-000000000000'::uuid)"),
        {"u": str(owner_user_id), "k": kind, "s": sid})).first()
    if again:
        return {"code": again[0], "kind": kind, "site_id": sid, "created": False}
    raise HTTPException(500, "추천코드 발급에 실패했습니다(코드 공간 충돌)")


async def record_event(db: AsyncSession, code: str, event: str, *, visitor_ref=None,
                       customer_id=None, contract_id=None) -> bool:
    """퍼널 이벤트 기록(유효코드일 때만). 자동기록 훅에서 best-effort 재사용. 호출자가 commit.

    유효하지 않은 코드는 조용히 무시(False) — 방문/계약 본흐름을 막지 않는다.
    """
    if event not in _EVENT_SET:
        return False
    row = await _load_code(db, code)
    if not row or not row[4]:  # 미존재/비활성 코드
        return False
    sid = row[2]  # 코드의 site_id(있으면)
    await db.execute(text(
        "INSERT INTO referral_events (code, event, visitor_ref, customer_id, contract_id, site_id)"
        " VALUES (:c, :e, :vr, CAST(:cu AS uuid), CAST(:co AS uuid), CAST(:s AS uuid))"),
        {"c": code, "e": event, "vr": visitor_ref,
         "cu": str(customer_id) if customer_id else None,
         "co": str(contract_id) if contract_id else None,
         "s": str(sid) if sid else None})
    return True


async def attribute_customer(db: AsyncSession, code: str, customer_id, contract_id=None) -> dict:
    """귀속 생성(first-touch) — customer 당 1귀속. 이미 있으면 기존 유지(멱등).

    수수료 연결은 best-effort(연결 가능 시 commission_split_id 채움, 아니면 pending 보존).
    실제 지급은 기존 승인흐름을 거친다(여기서는 기록만). 호출자가 commit.
    """
    row = await _load_code(db, code)
    if not row or not row[4]:
        raise HTTPException(404, "유효하지 않은 추천코드입니다")
    owner_user_id, code_site_id = row[1], row[2]

    # first-touch: 이미 귀속된 고객이면 기존 귀속 반환(중복귀속 방지·멱등)
    existing = (await db.execute(text(
        "SELECT id, code, owner_user_id, status, commission_split_id FROM referral_attributions"
        " WHERE customer_id = :cu"), {"cu": str(customer_id)})).first()
    if existing:
        return {"id": str(existing[0]), "code": existing[1], "owner_user_id": str(existing[2]),
                "status": existing[3],
                "commission_split_id": str(existing[4]) if existing[4] else None,
                "idempotent": True}

    # 수수료 귀속 훅(best-effort) — 계약확정 + 해당 계약에 연결된 split 이 있으면 연결태그.
    split_id = None
    if contract_id is not None:
        split_id = await _try_link_commission_split(db, contract_id, owner_user_id, code_site_id)
    status = "confirmed" if contract_id is not None else "pending"

    attr_id = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO referral_attributions"
        " (id, code, owner_user_id, customer_id, contract_id, site_id, status, commission_split_id)"
        " VALUES (:id, :c, :o, CAST(:cu AS uuid), CAST(:co AS uuid), CAST(:s AS uuid), :st, CAST(:sp AS uuid))"
        " ON CONFLICT (customer_id) DO NOTHING"),
        {"id": str(attr_id), "c": code, "o": str(owner_user_id), "cu": str(customer_id),
         "co": str(contract_id) if contract_id else None,
         "s": str(code_site_id) if code_site_id else None,
         "st": status, "sp": str(split_id) if split_id else None})

    # 경쟁(동시 first-touch)으로 INSERT가 무시됐다면 기존 행을 반환
    final = (await db.execute(text(
        "SELECT id, code, owner_user_id, status, commission_split_id FROM referral_attributions"
        " WHERE customer_id = :cu"), {"cu": str(customer_id)})).first()
    return {"id": str(final[0]), "code": final[1], "owner_user_id": str(final[2]),
            "status": final[3], "commission_split_id": str(final[4]) if final[4] else None,
            "idempotent": str(final[0]) != str(attr_id)}


async def _try_link_commission_split(db: AsyncSession, contract_id, owner_user_id, site_id):
    """수수료 귀속 훅 — 계약/코드소유자에 대응하는 기존 commission split 을 best-effort 조회.

    정직: 새 split 을 임의 생성·지급하지 않는다. 기존 수수료 흐름(event→split)이 이미
    만든 split 중 코드소유자(상담사) 노드에 해당하는 것을 '귀속태그'로만 연결한다.
    매칭 실패(흔함)면 None → 귀속은 pending/confirmed 로 기록되고 split 은 추후 연결.
    """
    try:
        row = (await db.execute(text(
            "SELECT s.id FROM sales_commission_splits s"
            " JOIN sales_commission_events e ON e.id = s.event_id"
            " JOIN sales_org_nodes n ON n.id = s.node_id"
            " WHERE e.contract_id = CAST(:co AS uuid) AND n.user_id = CAST(:u AS uuid)"
            " ORDER BY s.id LIMIT 1"),
            {"co": str(contract_id), "u": str(owner_user_id)})).first()
        return row[0] if row else None
    except Exception:  # noqa: BLE001 — 훅 실패는 귀속을 막지 않음(best-effort)
        return None


def _share_payload(code: str, site_code: str | None, site_id: str | None) -> dict:
    """공유 페이로드 — 공유링크 URL·QR용 데이터·기본 안내문구. QR 이미지는 프론트(qrcode) 생성.

    현장 서브도메인(siteCode.4t8t.net)이 있으면 그 오리진을, 없으면 폴백 베이스를 사용한다.
    """
    base = f"https://{site_code}.4t8t.net" if site_code else _SHARE_BASE
    link = f"{base}/?ref={code}"
    return {
        "code": code,
        "share_url": link,
        "qr_data": link,                 # 프론트 qrcode 라이브러리에 그대로 전달
        "default_text": "관심 가져주셔서 감사합니다. 아래 링크에서 분양 정보를 확인하세요.",
        "site_id": site_id,
        "notice": _SHARE_NOTICE,
        "web_share": {"title": "분양 정보", "text": "분양 정보를 확인하세요", "url": link},
    }


# ── 엔드포인트 ───────────────────────────────────────────────────────────────
@referral_router.post("/referral/codes", summary="내 추천코드 발급(멱등)")
async def create_code(body: CodeCreate, db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)) -> dict:
    if body.kind not in _KINDS:
        raise HTTPException(400, f"kind 는 {sorted(_KINDS)} 중 하나여야 합니다")
    if body.kind == "site" and body.site_id is None:
        raise HTTPException(400, "site 코드는 site_id 가 필요합니다")
    res = await issue_code(db, user.id, body.kind, body.site_id)
    await db.commit()
    return res


@referral_router.get("/referral/codes", summary="내 추천코드 목록")
async def list_codes(db: AsyncSession = Depends(get_db),
                     user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    rows = (await db.execute(text(
        "SELECT code, kind, site_id, active, created_at FROM referral_codes"
        " WHERE owner_user_id = :u ORDER BY created_at DESC"),
        {"u": str(user.id)})).all()
    return {"items": [
        {"code": r[0], "kind": r[1], "site_id": str(r[2]) if r[2] else None,
         "active": r[3], "created_at": str(r[4]) if r[4] else None}
        for r in rows
    ]}


@referral_router.get("/referral/share", summary="공유 페이로드(링크·QR·안내문구)")
async def share(code: str = Query(...), site_id: uuid.UUID | None = Query(None),
                db: AsyncSession = Depends(get_db),
                user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    row = await _load_code(db, code)
    if not row or not row[4]:
        raise HTTPException(404, "유효하지 않은 추천코드입니다")
    # 소유자만 자기 코드 공유 페이로드 조회(도용 방지)
    if str(row[1]) != str(user.id):
        raise HTTPException(403, "본인 추천코드만 공유할 수 있습니다")
    eff_site = site_id or row[2]
    site_code = None
    if eff_site:
        sc = (await db.execute(text("SELECT site_code FROM sales_sites WHERE id = :id"),
                               {"id": str(eff_site)})).first()
        site_code = sc[0] if sc else None
    return _share_payload(code, site_code, str(eff_site) if eff_site else None)


@referral_router.post("/referral/track", summary="퍼널 이벤트 기록(공개 — 랜딩)")
async def track(body: TrackEvent, db: AsyncSession = Depends(get_db)) -> dict:
    """랜딩페이지 공개 호출 허용(인증 불필요)이나 코드유효성은 검증. 무효코드는 ok=False."""
    if body.event not in _EVENT_SET:
        raise HTTPException(400, f"event 는 {_EVENTS} 중 하나여야 합니다")
    await _ensure(db)
    ok = await record_event(db, body.code, body.event, visitor_ref=body.visitor_ref,
                            customer_id=body.customer_id, contract_id=body.contract_id)
    await db.commit()
    return {"ok": ok, "event": body.event}


@referral_router.post("/referral/attribute", summary="귀속 생성(first-touch)+수수료훅")
async def attribute(body: AttributeCreate, db: AsyncSession = Depends(get_db),
                    user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    res = await attribute_customer(db, body.code, body.customer_id, body.contract_id)
    # 귀속 발생 시 lead/contract 퍼널 이벤트도 함께 기록(통계 일관성)
    ev = "contract" if body.contract_id is not None else "lead"
    await record_event(db, body.code, ev, customer_id=body.customer_id, contract_id=body.contract_id)
    await db.commit()
    return res


@referral_router.get("/referral/stats", summary="퍼널 통계(클릭→방문→리드→계약·전환율)")
async def stats(code: str = Query(...), from_: datetime | None = Query(None, alias="from"),
                to: datetime | None = Query(None, alias="to"),
                db: AsyncSession = Depends(get_db),
                user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    row = await _load_code(db, code)
    if not row:
        raise HTTPException(404, "유효하지 않은 추천코드입니다")
    if str(row[1]) != str(user.id):
        raise HTTPException(403, "본인 추천코드 통계만 조회할 수 있습니다")

    where = "WHERE code = :c"
    params: dict = {"c": code}
    if from_ is not None:
        where += " AND created_at >= :f"
        params["f"] = from_
    if to is not None:
        where += " AND created_at <= :t"
        params["t"] = to
    rows = (await db.execute(text(
        f"SELECT event, COUNT(*) FROM referral_events {where} GROUP BY event"), params)).all()
    counts = {e: 0 for e in _EVENTS}
    for ev, cnt in rows:
        if ev in counts:
            counts[ev] = int(cnt)
    # 귀속 고객 수(distinct) — 실질 리드 전환 보조지표
    attr_cnt = (await db.execute(text(
        "SELECT COUNT(*) FROM referral_attributions WHERE code = :c"), {"c": code})).scalar() or 0

    def _rate(n: int, d: int) -> float:
        return round(n / d, 4) if d else 0.0

    return {
        "code": code,
        "funnel": counts,
        "attributions": int(attr_cnt),
        "conversion": {
            "click_to_visit": _rate(counts["visit"], counts["click"]),
            "visit_to_lead": _rate(counts["lead"], counts["visit"]),
            "lead_to_contract": _rate(counts["contract"], counts["lead"]),
            "click_to_contract": _rate(counts["contract"], counts["click"]),
        },
    }
