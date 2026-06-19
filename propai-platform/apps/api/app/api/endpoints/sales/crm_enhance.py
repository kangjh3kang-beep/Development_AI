"""Phase1-D 고객관리 강화 — 카드 히스토리·문자/알림톡·업무일지 + 현장별/통합(union) 뷰.

설계(명세 45 D절)
- 토글: [현장별](그 현장+내 역할범위) / [통합](내 멤버십 전 현장 union, 각 현장 역할범위 적용).
- 고객관리카드 히스토리(상담·방문·계약단계 타임라인) + 카드 내 문자/알림톡 발송(발송이력 카드기록)
  + 업무일지(일일활동→고객이력·실적 연계).
- 통합 요약=개인범위 허용(요약필드만), 민감상세=현장 2차인증(X-Site-Token) 후.

정직/보안
- 통합뷰는 멤버십 검증된 현장만 union(타현장 고객 무단노출 차단).
- 문자=수신동의(SalesCustomerConsent MARKETING) 저장·확인 + 발신번호(sales_settings.kakao_sender_key) 사전등록 전제
  + 야간(21~08) 광고성 제한 가드 + 거부(080) 안내. 실제 외부발송은 notify 위임(키 없으면 안전 폴백·기록만).
- 신규 sales_* 테이블은 site_id 보유 → 기존 RLS 부트스트랩 sales_ 접두 자동매칭(정합).

엔드포인트(prefix=/api/v1/sales)
- GET  /my-customers?scope=all|site&site_id=&stage=&q=        현장별/통합 고객 목록
- GET  /customers/{id}/history                                카드 타임라인
- POST /customers/{id}/history {kind, content, stage_to?}     상담/방문/메모/단계변경 기록
- POST /customers/{id}/message {channel, template?, body}     문자/알림톡 발송(동의가드)
- POST /work-logs {log_date, summary, activities[]}           업무일지 작성
- GET  /work-logs?from=&to=&site_id=                          업무일지 목록
- GET  /work-logs/summary?period=                            실적 집계(상담/방문/계약)
"""

import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db

# ★SSOT(단일 출처): 폴백 역할 집합은 deps_sales 한 곳에서만 정의한다. 과거 본 모듈이 동일
# 리터럴을 중복정의해 드리프트(한쪽만 수정 시 불일치) 위험이 있었어 import 로 전환한다.
from app.api.deps_sales import (
    _DEVELOPER_ROLES,
    _SUPERADMIN_ROLES,
    SalesCtx,
    resolve_site,
    sales_ctx,
)
from apps.api.database.models.sales.contract_crm_ad import SalesCustomer
from apps.api.database.models.sales.site_org import SalesOrgNode, SalesSite

crm_enhance_router = APIRouter(tags=["sales-crm-enhance"])
logger = logging.getLogger("sales.crm")

# 발송 차단/보류 사유의 기계코드(프론트 BLOCK_REASON 맵과 1:1). 사람이 읽는 prose(blocked_reason)와
# 함께 reason_code 를 내려, 프론트가 코드로 친화 라벨을 고르게 한다(예전엔 prose만 내려와 맵이 죽어 있었음).
REASON_NO_CONSENT = "no_consent"   # 마케팅 수신동의 없음
REASON_NIGHT = "night"             # 야간(21~08) 광고성 발송 제한
REASON_NO_SENDER = "no_sender"     # 발신번호(발신프로필) 미등록
REASON_NO_KEY = "no_key"           # 발송 채널 키 미설정(알림톡 biz 키 등)
REASON_DISPATCH_FAIL = "dispatch_fail"  # 외부 발송 API 오류(타임아웃·네트워크 등)

# 계약단계 정규값(고객 status/단계 변경 화이트리스트)
_STAGES = {"LEAD", "CONSULT", "VISIT", "RESERVED", "SIGNED", "MIDDLE", "BALANCE", "CLOSED", "DROPPED"}
# 히스토리 종류
_KINDS = {"consult", "visit", "stage", "message", "note"}
# 플랫폼 User.role → sales 전역역할 폴백(현장 노드 없을 때)은 deps_sales SSOT 사용
# (_SUPERADMIN_ROLES/_DEVELOPER_ROLES import). 본 모듈 중복정의는 제거(드리프트 차단).


# ── 멱등 테이블/컬럼(_ensure) ────────────────────────────────────────────────
_HISTORY_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_customer_history ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  customer_id uuid NOT NULL,"
    "  site_id uuid NOT NULL,"
    "  actor_user_id uuid,"
    "  kind varchar(16) NOT NULL,"            # consult|visit|stage|message|note
    "  content text,"
    "  stage_from varchar(20),"
    "  stage_to varchar(20),"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_HISTORY_IDX = (
    "CREATE INDEX IF NOT EXISTS ix_sales_customer_history_cust"
    " ON sales_customer_history(customer_id, created_at DESC)"
)
_MSG_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_message_log ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  customer_id uuid NOT NULL,"
    "  site_id uuid NOT NULL,"
    "  actor_user_id uuid,"
    "  channel varchar(12) NOT NULL,"          # sms|alimtalk
    "  template varchar(40),"
    "  body text,"
    "  status varchar(12) NOT NULL DEFAULT 'PENDING',"  # SENT|SKIPPED|BLOCKED|FAILED
    "  consent_checked boolean NOT NULL DEFAULT false,"
    "  sent_at timestamptz"
    ")"
)
# 업무일지: 기존 sales_work_logs(author_node_id/content/metrics) 재사용 + 누락 컬럼 멱등 추가
_WORKLOG_ALTERS = (
    "ALTER TABLE sales_work_logs ADD COLUMN IF NOT EXISTS user_id uuid",
    "ALTER TABLE sales_work_logs ADD COLUMN IF NOT EXISTS summary text",
    "ALTER TABLE sales_work_logs ADD COLUMN IF NOT EXISTS activities jsonb",
    "ALTER TABLE sales_work_logs ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now()",
)


async def _ensure(db: AsyncSession) -> None:
    """히스토리·메시지로그 멱등 생성 + 업무일지 컬럼 멱등 보강(기존 무파괴)."""
    await db.execute(text(_HISTORY_DDL))
    await db.execute(text(_HISTORY_IDX))
    await db.execute(text(_MSG_DDL))
    for ddl in _WORKLOG_ALTERS:
        await db.execute(text(ddl))


# ── 스키마 ───────────────────────────────────────────────────────────────────
class HistoryCreate(BaseModel):
    kind: str                       # consult|visit|stage|note (message 는 발송 API에서 자동기록)
    content: str | None = None
    stage_to: str | None = None     # kind=stage 일 때 필수: 고객 status 갱신


class MessageSend(BaseModel):
    channel: str                    # sms|alimtalk
    template: str | None = None
    body: str


class WorkLogActivity(BaseModel):
    customer_id: uuid.UUID | None = None
    kind: str | None = None         # consult|visit|stage|note (집계 연계)
    note: str | None = None


class WorkLogCreate(BaseModel):
    log_date: date | None = None
    summary: str
    activities: list[WorkLogActivity] = []
    site_id: uuid.UUID | None = None  # 미지정 시 X-Site-Code 컨텍스트


# ── 멤버십(통합 union) 헬퍼 ──────────────────────────────────────────────────
async def _my_site_roles(db: AsyncSession, user) -> dict[str, str]:
    """내 멤버십 현장 → 역할 매핑(통합 union 범위). 노드 없는 시행사/관리자는 소유/플랫폼역할로 폴백."""
    roles: dict[str, str] = {}
    nodes = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.user_id == user.id, SalesOrgNode.active.is_(True),
        SalesOrgNode.deleted_at.is_(None)))).scalars().all()
    for n in nodes:
        roles[str(n.site_id)] = n.node_type

    role_lower = (getattr(user, "role", "") or "").lower()
    user_tenant = getattr(user, "tenant_id", None)
    # 플랫폼 슈퍼/시행사 또는 본인 테넌트 소유현장 → 노드 없어도 멤버십 인정(DEVELOPER)
    if role_lower in _SUPERADMIN_ROLES or role_lower in _DEVELOPER_ROLES or user_tenant:
        owned = (await db.execute(select(SalesSite).where(
            SalesSite.organization_id == user_tenant,
            SalesSite.deleted_at.is_(None)))).scalars().all() if user_tenant else []
        default_role = "SUPERADMIN" if role_lower in _SUPERADMIN_ROLES else "DEVELOPER"
        for s in owned:
            roles.setdefault(str(s.id), default_role)
    return roles


# 한국 표준시(KST, UTC+9 고정·서머타임 없음). 야간 광고성 발송 제한(정보통신망법 제50조)은
# '국내 수신자 기준 야간(21~08시)' 이므로 KST 로 판정해야 한다. 서버 컨테이너가 UTC 로 도는데
# .astimezone()(서버 로컬TZ) 으로 판정하면 UTC 기준이 되어 야간 차단이 9시간 어긋나 오작동한다.
_KST = timezone(timedelta(hours=9))


def _night_guard(now: datetime) -> bool:
    """야간(21:00~08:00) 광고성 발송 제한 가드(정보통신망법 제50조). True=차단대상.

    ★[KST 고정·iter-2 MED] 기존 .astimezone()(서버 로컬TZ) 은 컨테이너가 UTC 로 돌면 야간 판정이
      9시간 어긋나 오작동했다(국내 수신자 기준이 아님). 국내 수신자 기준 KST(UTC+9) 로 고정 변환해
      판정한다. naive datetime 이 들어오면 UTC 로 간주해 보정 후 KST 로 변환한다(모호성 제거)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    local = now.astimezone(_KST)  # 한국 표준시(KST) 기준
    return local.time() >= time(21, 0) or local.time() < time(8, 0)


async def _append_history(db: AsyncSession, *, customer_id, site_id, actor_user_id,
                          kind: str, content: str | None,
                          stage_from: str | None = None, stage_to: str | None = None) -> str:
    hid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO sales_customer_history"
        " (id, customer_id, site_id, actor_user_id, kind, content, stage_from, stage_to)"
        " VALUES (:id, :cid, :sid, :aid, :kind, :content, :sf, :st)"),
        {"id": str(hid), "cid": str(customer_id), "sid": str(site_id),
         "aid": str(actor_user_id) if actor_user_id else None,
         "kind": kind, "content": content, "sf": stage_from, "st": stage_to})
    return str(hid)


async def _load_customer_in_scope(db: AsyncSession, customer_id: uuid.UUID,
                                  site_ids: set[str]) -> SalesCustomer:
    """고객 로드 + 멤버십 현장 범위 검증(타현장 무단노출 차단)."""
    c = (await db.execute(select(SalesCustomer).where(
        SalesCustomer.id == customer_id, SalesCustomer.deleted_at.is_(None)))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "고객을 찾을 수 없습니다")
    if str(c.site_id) not in site_ids:
        raise HTTPException(403, "이 고객(현장)에 대한 접근 권한이 없습니다")
    return c


# ── 1) 현장별/통합 고객 목록 ─────────────────────────────────────────────────
@crm_enhance_router.get("/my-customers", summary="내 고객(현장별/통합) — scope=all|site")
async def my_customers(request: Request, scope: str = "site",
                       site_id: uuid.UUID | None = None, stage: str | None = None,
                       q: str | None = None,
                       db: AsyncSession = Depends(get_db),
                       user=Depends(get_current_user)) -> dict:
    """scope=site: 단일현장(역할범위). scope=all: 내 멤버십 전현장 union(현장칩 포함, 요약필드만).

    통합(all)은 개인범위 요약(이름·현장·단계·온도)만 노출하고 민감상세(연락처)는 마스킹한다.
    민감상세는 현장별(site) 진입 후 2차인증(X-Site-Token) 컨텍스트에서 조회한다.
    """
    await _ensure(db)
    roles = await _my_site_roles(db, user)
    if not roles:
        return {"scope": scope, "count": 0, "customers": [], "sites": []}

    if scope == "site":
        # 현장별: 단일현장(경로/헤더/파라미터). 멤버십 검증.
        if site_id is not None:
            target = str(site_id)
        else:
            site = await resolve_site(request, db)
            target = str(site.id)
        if target not in roles:
            raise HTTPException(403, "이 현장에 대한 분양(sales) 권한이 없습니다")
        target_sites = {target}
        masked = False  # 현장별 단일진입은 상세 허용(역할범위 내)
    else:
        target_sites = set(roles.keys())
        masked = True   # 통합은 요약만(연락처 마스킹)

    site_rows = (await db.execute(select(SalesSite).where(
        SalesSite.id.in_([uuid.UUID(s) for s in target_sites])))).scalars().all()
    site_name = {str(s.id): s.site_name for s in site_rows}

    stmt = select(SalesCustomer).where(
        SalesCustomer.site_id.in_([uuid.UUID(s) for s in target_sites]),
        SalesCustomer.deleted_at.is_(None))
    if stage:
        stmt = stmt.where(SalesCustomer.status == stage)
    if q:
        stmt = stmt.where(SalesCustomer.name.ilike(f"%{q}%"))
    rows = (await db.execute(stmt.order_by(SalesCustomer.created_at.desc()))).scalars().all()

    items = []
    for c in rows:
        sid = str(c.site_id)
        items.append({
            "customer_id": str(c.id), "name": c.name,
            "phone": None if masked else c.phone_e164,
            "phone_masked": _mask_phone(c.phone_e164) if masked else None,
            "stage": c.status, "grade": c.grade,
            "site_id": sid, "site_name": site_name.get(sid),
            "role_in_site": roles.get(sid),
        })
    return {
        "scope": scope, "masked": masked, "count": len(items), "customers": items,
        "sites": [{"site_id": str(s.id), "site_name": s.site_name,
                   "role": roles.get(str(s.id))} for s in site_rows],
    }


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 7:
        return "***"
    return digits[:3] + "****" + digits[-4:]


# ── 2) 카드 히스토리 ─────────────────────────────────────────────────────────
@crm_enhance_router.get("/customers/{customer_id}/history", summary="고객카드 히스토리(타임라인)")
async def customer_history(customer_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                           ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    # 현장별 컨텍스트: ctx.site_id 범위에서만 조회(현장 격리)
    c = await _load_customer_in_scope(db, customer_id, {str(ctx.site_id)})
    rows = (await db.execute(text(
        "SELECT id, kind, content, stage_from, stage_to, actor_user_id, created_at"
        " FROM sales_customer_history WHERE customer_id = :cid AND site_id = :sid"
        " ORDER BY created_at DESC"),
        {"cid": str(customer_id), "sid": str(ctx.site_id)})).all()
    timeline = [{"id": str(r[0]), "kind": r[1], "content": r[2],
                 "stage_from": r[3], "stage_to": r[4],
                 "actor_user_id": str(r[5]) if r[5] else None,
                 "created_at": str(r[6])} for r in rows]
    return {"customer_id": str(customer_id), "name": c.name, "stage": c.status,
            "grade": c.grade, "count": len(timeline), "timeline": timeline}


@crm_enhance_router.post("/customers/{customer_id}/history", summary="고객카드 기록(상담/방문/메모/단계변경)")
async def add_history(customer_id: uuid.UUID, body: HistoryCreate,
                      db: AsyncSession = Depends(get_db),
                      ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    if body.kind not in (_KINDS - {"message"}):
        raise HTTPException(400, f"kind 는 {sorted(_KINDS - {'message'})} 중 하나여야 합니다")
    c = await _load_customer_in_scope(db, customer_id, {str(ctx.site_id)})

    stage_from = stage_to = None
    if body.kind == "stage":
        if not body.stage_to:
            raise HTTPException(400, "단계변경(stage)은 stage_to 가 필요합니다")
        st = body.stage_to.upper()
        if st not in _STAGES:
            raise HTTPException(400, f"stage_to 는 {sorted(_STAGES)} 중 하나여야 합니다")
        stage_from, stage_to = c.status, st
        # 고객 단계(status) 갱신
        await db.execute(text(
            "UPDATE sales_customers SET status = :st WHERE id = :cid"),
            {"st": st, "cid": str(customer_id)})

    hid = await _append_history(
        db, customer_id=customer_id, site_id=ctx.site_id, actor_user_id=ctx.user.id,
        kind=body.kind, content=body.content, stage_from=stage_from, stage_to=stage_to)
    await db.commit()
    return {"id": hid, "customer_id": str(customer_id), "kind": body.kind,
            "stage_from": stage_from, "stage_to": stage_to}


# ── 3) 문자/알림톡 발송(동의가드) ─────────────────────────────────────────────
@crm_enhance_router.post("/customers/{customer_id}/message", summary="문자/알림톡 발송(수신동의·발신번호 가드)")
async def send_message(customer_id: uuid.UUID, body: MessageSend,
                       db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    channel = (body.channel or "").lower()
    if channel not in {"sms", "alimtalk"}:
        raise HTTPException(400, "channel 은 sms|alimtalk 이어야 합니다")
    if not (body.body or "").strip():
        raise HTTPException(400, "본문(body)이 비어 있습니다")
    c = await _load_customer_in_scope(db, customer_id, {str(ctx.site_id)})

    if not c.phone_e164:
        raise HTTPException(400, "고객 연락처가 없어 발송할 수 없습니다")

    # ① 수신동의 확인(정보통신망법 제50조 — 광고성 정보 사전동의)
    consent = (await db.execute(text(
        "SELECT count(*) FROM sales_customer_consents"
        " WHERE customer_id = :cid AND consent_type = 'MARKETING' AND agreed = true"
        " AND withdrawn_at IS NULL"),
        {"cid": str(customer_id)})).scalar() or 0
    consent_ok = consent > 0

    status = "PENDING"
    blocked_reason = None   # 사람이 읽는 한국어 사유(하위호환)
    reason_code = None      # 기계코드(프론트 BLOCK_REASON 맵 키) — 동시 제공
    from app.core.config_sales import sales_settings

    if not consent_ok:
        status, reason_code = "BLOCKED", REASON_NO_CONSENT
        blocked_reason = "수신동의(MARKETING)가 없어 광고성 발송이 차단되었습니다"
    elif _night_guard(datetime.now(UTC)):
        status, reason_code = "BLOCKED", REASON_NIGHT
        blocked_reason = "야간(21~08시) 광고성 발송 제한(정보통신망법)"
    elif not sales_settings.kakao_sender_key:
        # 발신번호(발신프로필) 사전등록 전제 — 미등록 시 안전 폴백(기록만)
        status, reason_code = "SKIPPED", REASON_NO_SENDER
        blocked_reason = "발신번호(발신프로필) 미등록 — 안전 폴백(기록만)"
    else:
        status, reason_code = await _dispatch_message(channel, c.phone_e164, body)
        if reason_code == REASON_NO_KEY:
            blocked_reason = "발송 채널(알림톡) 키 미설정 — 안전 폴백(기록만)"
        elif reason_code == REASON_DISPATCH_FAIL:
            blocked_reason = "외부 발송 API 오류 — 잠시 후 재시도하세요(기록만)"

    msg_id = uuid.uuid4()
    sent_at = "now()" if status == "SENT" else "NULL"
    # ★silent-drop 방지: SENT/SKIPPED/BLOCKED/FAILED 어떤 결과든 항상 발송이력(sales_message_log)에
    #   status 로 영속한다. 실패(FAILED)도 행으로 남아 운영자가 재시도/추적할 수 있다(0으로 은폐 금지).
    await db.execute(text(
        "INSERT INTO sales_message_log"
        " (id, customer_id, site_id, actor_user_id, channel, template, body, status, consent_checked, sent_at)"
        f" VALUES (:id, :cid, :sid, :aid, :ch, :tpl, :body, :status, :consent, {sent_at})"),
        {"id": str(msg_id), "cid": str(customer_id), "sid": str(ctx.site_id),
         "aid": str(ctx.user.id), "ch": channel, "tpl": body.template,
         "body": body.body, "status": status, "consent": consent_ok})

    # 발송이력을 카드 히스토리(kind=message)에도 기록
    summary = f"[{channel}] {body.body[:60]}" + (f" ({blocked_reason})" if blocked_reason else "")
    await _append_history(db, customer_id=customer_id, site_id=ctx.site_id,
                          actor_user_id=ctx.user.id, kind="message", content=summary)
    await db.commit()
    return {"id": str(msg_id), "channel": channel, "status": status,
            "consent_checked": consent_ok, "blocked_reason": blocked_reason,
            "reason_code": reason_code,
            "opt_out_notice": "수신거부 080 안내 포함 필요(광고성)" if consent_ok else None}


async def _dispatch_message(channel: str, phone: str, body: MessageSend) -> tuple[str, str | None]:
    """실제 외부발송 위임 — (status, reason_code) 반환. 기록은 호출부에서 수행.

    정직/분류: 실패를 0/빈값으로 은폐하지 않는다. 키 미설정(SKIPPED)과 외부 API 오류(FAILED)를
    구분해 reason_code 로 내려주고, 오류는 예외 타입과 함께 분류 로깅한다(원인 추적 가능).
    """
    from app.core.config_sales import sales_settings
    if channel == "alimtalk" and not sales_settings.kakao_biz_key:
        return "SKIPPED", REASON_NO_KEY
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as cli:
            resp = await cli.post(
                "https://kakaoapi.example/v2/sender/send",
                headers={"Authorization": f"Bearer {sales_settings.kakao_biz_key or ''}"},
                json={"senderKey": sales_settings.kakao_sender_key, "to": phone,
                      "templateCode": body.template or "CRM_GENERAL", "text": body.body})
        # HTTP 4xx/5xx 도 발송 실패로 분류(2xx 만 성공). 200대가 아니면 FAILED 로 기록.
        if resp.status_code >= 400:
            logger.warning("CRM 메시지 발송 실패(HTTP %s) channel=%s", resp.status_code, channel)
            return "FAILED", REASON_DISPATCH_FAIL
        return "SENT", None
    except Exception as exc:  # noqa: BLE001 — 외부발송 오류는 흐름을 막지 않되 분류 로깅 후 FAILED 기록
        logger.warning("CRM 메시지 발송 예외 channel=%s err=%s: %s",
                       channel, type(exc).__name__, exc)
        return "FAILED", REASON_DISPATCH_FAIL


# ── 4) 업무일지 ──────────────────────────────────────────────────────────────
@crm_enhance_router.post("/work-logs", summary="업무일지 작성(활동→고객이력 연계)")
async def create_work_log(body: WorkLogCreate, request: Request,
                          db: AsyncSession = Depends(get_db),
                          user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    roles = await _my_site_roles(db, user)
    # 현장 결정: body.site_id 우선, 없으면 컨텍스트(X-Site-Code) 해석
    if body.site_id is not None:
        target = str(body.site_id)
    else:
        try:
            site = await resolve_site(request, db)
            target = str(site.id)
        except HTTPException as e:
            raise HTTPException(400, "site_id 또는 X-Site-Code 가 필요합니다") from e
    if target not in roles:
        raise HTTPException(403, "이 현장에 대한 분양(sales) 권한이 없습니다")

    log_date = body.log_date or date.today()
    activities = [a.model_dump(mode="json") for a in body.activities]
    metrics = _activity_metrics(body.activities)

    wid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO sales_work_logs"
        " (id, site_id, user_id, log_date, summary, content, activities, metrics)"
        " VALUES (:id, :sid, :uid, :ld, :summary, :summary, CAST(:acts AS jsonb), CAST(:metrics AS jsonb))"),
        {"id": str(wid), "sid": target, "uid": str(user.id), "ld": log_date,
         "summary": body.summary, "acts": _json(activities), "metrics": _json(metrics)})

    # 활동에 연계된 고객은 히스토리에도 기록(업무일지↔고객이력 연계)
    for a in body.activities:
        if a.customer_id and (a.kind in (_KINDS - {"message"})):
            c = (await db.execute(select(SalesCustomer).where(
                SalesCustomer.id == a.customer_id, SalesCustomer.site_id == uuid.UUID(target),
                SalesCustomer.deleted_at.is_(None)))).scalar_one_or_none()
            if c:
                await _append_history(db, customer_id=a.customer_id, site_id=uuid.UUID(target),
                                      actor_user_id=user.id, kind=a.kind or "note",
                                      content=(a.note or body.summary)[:200])
    await db.commit()
    return {"id": str(wid), "site_id": target, "log_date": str(log_date),
            "metrics": metrics, "linked_customers": sum(1 for a in body.activities if a.customer_id)}


@crm_enhance_router.get("/work-logs", summary="업무일지 목록(기간·현장)")
async def list_work_logs(request: Request, from_: date | None = None, to: date | None = None,
                         site_id: uuid.UUID | None = None,
                         db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    roles = await _my_site_roles(db, user)
    if not roles:
        return {"count": 0, "items": []}
    sites = {str(site_id)} if site_id is not None else set(roles.keys())
    sites = {s for s in sites if s in roles}
    if not sites:
        raise HTTPException(403, "이 현장에 대한 권한이 없습니다")

    where = ["site_id = ANY(:sids)", "user_id = :uid"]
    params: dict = {"sids": list(sites), "uid": str(user.id)}
    if from_:
        where.append("log_date >= :from")
        params["from"] = from_
    if to:
        where.append("log_date <= :to")
        params["to"] = to
    rows = (await db.execute(text(
        "SELECT id, site_id, log_date, summary, activities, metrics, created_at"
        f" FROM sales_work_logs WHERE {' AND '.join(where)} ORDER BY log_date DESC, created_at DESC"),
        params)).all()
    items = [{"id": str(r[0]), "site_id": str(r[1]), "log_date": str(r[2]) if r[2] else None,
              "summary": r[3], "activities": r[4] or [], "metrics": r[5] or {},
              "created_at": str(r[6]) if r[6] else None} for r in rows]
    return {"count": len(items), "items": items}


@crm_enhance_router.get("/work-logs/summary", summary="업무일지 실적집계(상담/방문/계약)")
async def work_log_summary(request: Request, period: str = "month",
                           site_id: uuid.UUID | None = None,
                           db: AsyncSession = Depends(get_db),
                           user=Depends(get_current_user)) -> dict:
    """실적집계: 내 업무일지 metrics + 고객 히스토리에서 상담/방문/단계(계약)·메시지 카운트 산출."""
    await _ensure(db)
    roles = await _my_site_roles(db, user)
    if not roles:
        return {"period": period, "summary": {}, "by_site": []}
    sites = {str(site_id)} if site_id is not None else set(roles.keys())
    sites = {s for s in sites if s in roles}
    if not sites:
        raise HTTPException(403, "이 현장에 대한 권한이 없습니다")

    interval = {"day": "1 day", "week": "7 days", "month": "1 month", "quarter": "3 months",
                "year": "1 year"}.get(period, "1 month")

    # 히스토리 기반 활동 집계(내가 actor 인 기록)
    rows = (await db.execute(text(
        "SELECT site_id, kind,"
        "       count(*) FILTER (WHERE kind <> 'stage') AS cnt,"
        "       count(*) FILTER (WHERE kind = 'stage' AND stage_to IN "
        "                        ('RESERVED','SIGNED','MIDDLE','BALANCE')) AS contracts"
        " FROM sales_customer_history"
        " WHERE site_id = ANY(:sids) AND actor_user_id = :uid"
        f"   AND created_at >= now() - interval '{interval}'"
        " GROUP BY site_id, kind"),
        {"sids": list(sites), "uid": str(user.id)})).all()

    by_site: dict[str, dict] = {}
    for sid, kind, cnt, contracts in rows:
        s = by_site.setdefault(str(sid), {"consult": 0, "visit": 0, "note": 0,
                                          "message": 0, "stage_changes": 0, "contracts": 0})
        if kind == "stage":
            s["stage_changes"] += int(cnt or 0)
            s["contracts"] += int(contracts or 0)
        elif kind in s:
            s[kind] += int(cnt or 0)

    # 작성 업무일지 수
    log_rows = (await db.execute(text(
        "SELECT site_id, count(*) FROM sales_work_logs"
        " WHERE site_id = ANY(:sids) AND user_id = :uid"
        f"   AND created_at >= now() - interval '{interval}'"
        " GROUP BY site_id"),
        {"sids": list(sites), "uid": str(user.id)})).all()
    for sid, cnt in log_rows:
        by_site.setdefault(str(sid), {"consult": 0, "visit": 0, "note": 0, "message": 0,
                                      "stage_changes": 0, "contracts": 0})["work_logs"] = int(cnt or 0)

    total = {"consult": 0, "visit": 0, "contracts": 0, "message": 0,
             "stage_changes": 0, "work_logs": 0}
    for s in by_site.values():
        for k in total:
            total[k] += int(s.get(k, 0) or 0)

    site_rows = (await db.execute(select(SalesSite).where(
        SalesSite.id.in_([uuid.UUID(s) for s in sites])))).scalars().all()
    name = {str(x.id): x.site_name for x in site_rows}
    return {"period": period, "summary": total,
            "by_site": [{"site_id": sid, "site_name": name.get(sid), **m}
                        for sid, m in by_site.items()]}


def _activity_metrics(activities: list[WorkLogActivity]) -> dict:
    m = {"consult": 0, "visit": 0, "stage": 0, "note": 0, "total": len(activities)}
    for a in activities:
        if a.kind in m:
            m[a.kind] += 1
    return m


def _json(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
