"""자가성장 엔진 — 텔레메트리 수집 라우터(설계서 §3.2).

POST /api/v1/growth/events
- 프론트 event-collector 가 5초/20건 배치로 sendBeacon 전송하는 이벤트 수신.
- 인증 선택적(익명 허용). Authorization: Bearer 가 있으면 user_id/tenant_id 추출
  → user_id 는 서버가 HMAC 익명화(capture_service), 원본 미저장.
- event_id(uuid) 멱등(중복 전송은 적재 시 DO NOTHING).
- 동기 INSERT 없음: record_event() 로 큐 push 만(적재는 Celery/폴백).
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.session import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/growth", tags=["자가성장 텔레메트리"])

# 프론트가 임의로 큰 배열을 보내지 못하게 1회 배치 상한.
_MAX_BATCH = 100

_ALLOWED_TYPES = {
    "page_view", "click", "funnel_step", "api_call", "api_error", "js_error",
    "promise_rejection", "web_vital", "llm_call", "verify_result", "fallback",
    "heal_action",
}


class GrowthEventIn(BaseModel):
    """프론트 collector 가 보내는 단일 이벤트 스키마(익명화 전)."""

    event_id: str | None = Field(default=None, description="클라이언트 멱등키(uuid)")
    event_type: str
    surface: str | None = Field(default="web")
    route: str | None = None
    status_code: int | None = None
    latency_ms: int | None = None
    severity: str | None = None
    service: str | None = None
    session_id: str | None = None
    app_version: str | None = None
    payload: dict | None = None


class GrowthEventBatch(BaseModel):
    events: list[GrowthEventIn] = Field(default_factory=list)


class GrowthIngestResult(BaseModel):
    accepted: int
    rejected: int


def _extract_identity(request: Request) -> tuple[str | None, str | None]:
    """Authorization 헤더(선택적)에서 (user_id, tenant_id) 추출. 없으면 (None, None)."""
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None, None
    try:
        from apps.api.auth.jwt_handler import decode_token

        payload = decode_token(auth.split(" ", 1)[1].strip())
        uid = str(payload.sub) if getattr(payload, "sub", None) else None
        tid = str(payload.tenant_id) if getattr(payload, "tenant_id", None) else None
        return uid, tid
    except Exception:  # noqa: BLE001 — 무효/만료 토큰은 익명 처리.
        return None, None


@router.post("/events", response_model=GrowthIngestResult)
async def ingest_events(batch: GrowthEventBatch, request: Request) -> GrowthIngestResult:
    """프론트 이벤트 배치를 수신해 큐에 적재(논블로킹). 인증 선택·익명 허용."""
    from app.services.growth import capture_service

    user_id, tenant_id = _extract_identity(request)

    accepted = 0
    rejected = 0
    for ev in batch.events[:_MAX_BATCH]:
        if ev.event_type not in _ALLOWED_TYPES:
            rejected += 1
            continue
        try:
            capture_service.record_event(
                ev.event_type,
                {
                    "event_id": ev.event_id,
                    "surface": ev.surface or "web",
                    "route": ev.route,
                    "status_code": ev.status_code,
                    "latency_ms": ev.latency_ms,
                    "severity": ev.severity,
                    "service": ev.service,
                    "session_id": ev.session_id,
                    "app_version": ev.app_version,
                    "payload": ev.payload,
                    "tenant_id": tenant_id,
                    "user_id": user_id,  # capture_service 가 HMAC 익명화 후 폐기
                },
            )
            accepted += 1
        except Exception:  # noqa: BLE001
            rejected += 1
    # 상한 초과분은 거부 카운트에 반영.
    rejected += max(0, len(batch.events) - _MAX_BATCH)
    return GrowthIngestResult(accepted=accepted, rejected=rejected)


# ════════════════════════════════════════════════════════════════════════════
# 인사이트 조회·확인 (Phase 2, 관리자 전용 — 설계서 §5.2)
# ════════════════════════════════════════════════════════════════════════════
# RBAC: 플랫폼 총괄관리자(users.tier='super_admin')만. admin_secrets 선례와 동일.
#  ★role 기반 금지(가입 시 전원 자기 테넌트 role='admin' → 전역 인사이트 누출).
# 전역(tenant NULL)+테넌트 분리 정책은 설계 §11 미결 → 우선 관리자=전역 전체 조회.

_INSIGHT_STATUSES = {"open", "acknowledged", "acted", "dismissed"}
_ACK_STATUSES = {"acknowledged", "dismissed"}


class GrowthInsightOut(BaseModel):
    """성장 대시보드가 소비하는 인사이트 응답 스키마(프론트 계약)."""

    id: str
    insight_type: str
    severity: str | None = None
    status: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    metrics_json: dict | None = None
    narrative: str | None = None
    recommended_action: str | None = None
    created_at: datetime | None = None


class GrowthInsightList(BaseModel):
    items: list[GrowthInsightOut]
    total: int


class InsightAckRequest(BaseModel):
    """status 전이 요청. open → acknowledged|dismissed."""

    status: str = Field(..., description="acknowledged 또는 dismissed")
    note: str | None = Field(default=None, max_length=500, description="확인 메모(선택)")


class InsightAckResult(BaseModel):
    id: str
    status: str


async def _require_admin(request: Request, db: AsyncSession) -> str:
    """총괄관리자(tier)만 허용. 통과 시 user_id 반환, 아니면 401/403."""
    user_id, _tenant_id = _extract_identity(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    from app.services.billing.billing_service import is_super_admin

    if not await is_super_admin(db, user_id):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")
    return user_id


@router.get("/insights", response_model=GrowthInsightList)
async def list_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    insight_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: datetime | None = Query(default=None, description="created_at >= since"),
    until: datetime | None = Query(default=None, description="created_at < until"),
    sort: str = Query(default="severity", description="severity | created_at"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> GrowthInsightList:
    """인사이트 목록(관리자=전역 전체). 필터·기간·정렬·페이지네이션."""
    from sqlalchemy import text

    await _require_admin(request, db)

    where = ["1=1"]
    params: dict = {}
    if insight_type:
        where.append("insight_type = :itype")
        params["itype"] = insight_type
    if severity:
        where.append("severity = :sev")
        params["sev"] = severity
    if status:
        if status not in _INSIGHT_STATUSES:
            raise HTTPException(status_code=400, detail="잘못된 status 값입니다.")
        where.append("status = :st")
        params["st"] = status
    if since is not None:
        where.append("created_at >= :since")
        params["since"] = since
    if until is not None:
        where.append("created_at < :until")
        params["until"] = until
    where_sql = " AND ".join(where)

    # 정렬: severity 는 critical>warn>info 가중치 후 created_at DESC.
    if sort == "created_at":
        order_sql = "created_at DESC"
    else:
        order_sql = (
            "CASE severity WHEN 'critical' THEN 3 WHEN 'warn' THEN 2 "
            "WHEN 'info' THEN 1 ELSE 0 END DESC, created_at DESC"
        )

    total = (await db.execute(
        text(f"SELECT COUNT(*) FROM platform_insights WHERE {where_sql}"), params
    )).scalar() or 0

    params["limit"] = limit
    params["offset"] = offset
    rows = (await db.execute(text(
        "SELECT id, insight_type, severity, status, window_start, window_end, "
        "       metrics_json, narrative, recommended_action, created_at "
        f"FROM platform_insights WHERE {where_sql} "
        f"ORDER BY {order_sql} LIMIT :limit OFFSET :offset"
    ), params)).fetchall()

    items = [
        GrowthInsightOut(
            id=str(r[0]), insight_type=r[1], severity=r[2], status=r[3],
            window_start=r[4], window_end=r[5],
            metrics_json=r[6] if isinstance(r[6], dict) else None,
            narrative=r[7], recommended_action=r[8], created_at=r[9],
        )
        for r in rows
    ]
    return GrowthInsightList(items=items, total=int(total))


@router.post("/insights/{insight_id}/ack", response_model=InsightAckResult)
async def ack_insight(
    insight_id: str,
    req: InsightAckRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> InsightAckResult:
    """인사이트 status 전이(open → acknowledged|dismissed). 관리자 전용 + 감사기록."""
    from sqlalchemy import text

    user_id = await _require_admin(request, db)
    if req.status not in _ACK_STATUSES:
        raise HTTPException(
            status_code=400, detail="status 는 acknowledged 또는 dismissed 여야 합니다."
        )

    # 허용 전이만(open/acknowledged → acknowledged|dismissed). acted/dismissed 등
    # 이미 처리된 상태는 임의 재전이 금지.
    row = (await db.execute(text(
        "UPDATE platform_insights SET status = :st "
        "WHERE id = :id AND status IN ('open','acknowledged') "
        "RETURNING id, status"
    ), {"st": req.status, "id": insight_id})).fetchone()
    if row is None:
        await db.rollback()
        # 행이 없으면: 존재하지 않거나(404) 이미 처리됨(409)을 구분.
        exists = (await db.execute(text(
            "SELECT status FROM platform_insights WHERE id = :id"
        ), {"id": insight_id})).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="인사이트를 찾을 수 없습니다.")
        raise HTTPException(
            status_code=409,
            detail=f"이미 처리된 인사이트입니다(현재 상태: {exists[0]}).",
        )
    await db.commit()

    # 감사기록(누가·어떤 인사이트를 어떤 상태로) — best-effort.
    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=user_id, actor_role="super_admin",
            action=f"growth.insight.{req.status}", target=insight_id,
            detail={"note": req.note} if req.note else None,
        )
    except Exception:  # noqa: BLE001
        pass

    return InsightAckResult(id=str(row[0]), status=str(row[1]))


# ════════════════════════════════════════════════════════════════════════════
# 자가치유 heal-log·롤백 (Phase 3, 관리자 전용 — 설계서 §6.1)
# ════════════════════════════════════════════════════════════════════════════
# heal-log: heal_action 이벤트 이력 + 현재 활성 플래그(platform_settings, TTL 미만료).
# rollback: action_id 의 setting_key 를 platform_settings 에서 즉시 원복 + 감사기록.

class HealActionOut(BaseModel):
    """heal_action 이벤트 1건(프론트 heal-log 계약)."""

    action_id: str | None = None
    action_type: str | None = None
    severity: str | None = None
    service: str | None = None
    rollbackable: bool = False
    setting_key: str | None = None
    ttl_expires_at: str | None = None
    params: dict | None = None
    created_at: datetime | None = None


class ActiveFlagOut(BaseModel):
    """현재 활성(미만료) platform_settings 플래그 1건."""

    key: str
    scope: str
    value: dict | None = None
    ttl_expires_at: datetime | None = None
    updated_by: str | None = None


class HealLogOut(BaseModel):
    """GET /growth/heal-log 응답(프론트 계약)."""

    actions: list[HealActionOut]
    active_flags: list[ActiveFlagOut]
    total: int


class RollbackResult(BaseModel):
    """POST /growth/heal/{action_id}/rollback 응답."""

    action_id: str
    rolled_back: bool
    setting_key: str | None = None
    detail: str | None = None


@router.get("/heal-log", response_model=HealLogOut)
async def heal_log(
    request: Request,
    db: AsyncSession = Depends(get_db),
    action_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None, description="created_at >= since"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> HealLogOut:
    """heal_action 이벤트 이력 + 현재 활성 플래그(미만료) 조회. 관리자 전용."""
    import json as _json

    from sqlalchemy import text

    await _require_admin(request, db)

    where = ["event_type = 'heal_action'"]
    params: dict = {}
    if action_type:
        where.append("payload->>'action_type' = :at")
        params["at"] = action_type
    if since is not None:
        where.append("created_at >= :since")
        params["since"] = since
    where_sql = " AND ".join(where)

    total = (await db.execute(
        text(f"SELECT COUNT(*) FROM platform_events WHERE {where_sql}"), params
    )).scalar() or 0

    params["limit"] = limit
    params["offset"] = offset
    rows = (await db.execute(text(
        "SELECT severity, service, payload, created_at FROM platform_events "
        f"WHERE {where_sql} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    ), params)).fetchall()

    actions: list[HealActionOut] = []
    for r in rows:
        pl = r[2]
        if isinstance(pl, str):
            try:
                pl = _json.loads(pl)
            except Exception:  # noqa: BLE001
                pl = {}
        pl = pl or {}
        actions.append(HealActionOut(
            action_id=pl.get("action_id"), action_type=pl.get("action_type"),
            severity=r[0], service=r[1],
            rollbackable=bool(pl.get("rollbackable")),
            setting_key=pl.get("setting_key"), ttl_expires_at=pl.get("ttl_expires_at"),
            params=pl.get("params") if isinstance(pl.get("params"), dict) else None,
            created_at=r[3],
        ))

    # 현재 활성(미만료) 플래그 — TTL 이 NULL 이거나 미래인 것만.
    flag_rows = (await db.execute(text(
        "SELECT key, scope, value, ttl_expires_at, updated_by FROM platform_settings "
        "WHERE ttl_expires_at IS NULL OR ttl_expires_at > now() "
        "ORDER BY updated_at DESC LIMIT 200"
    ))).fetchall()
    active_flags = [
        ActiveFlagOut(
            key=fr[0], scope=fr[1],
            value=fr[2] if isinstance(fr[2], dict) else None,
            ttl_expires_at=fr[3], updated_by=fr[4],
        )
        for fr in flag_rows
    ]

    return HealLogOut(actions=actions, active_flags=active_flags, total=int(total))


@router.post("/heal/{action_id}/rollback", response_model=RollbackResult)
async def rollback_heal(
    action_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RollbackResult:
    """heal_action 즉시 롤백(platform_settings 원복) + 감사기록. 관리자 전용."""
    from app.services.growth import heal_actions

    user_id = await _require_admin(request, db)
    result = await heal_actions.rollback(db, action_id, actor_id=user_id)

    if not result.get("rolled_back") and result.get("detail") == "action_not_found":
        raise HTTPException(status_code=404, detail="heal 액션을 찾을 수 없습니다.")
    detail = result.get("detail")
    if isinstance(detail, dict):
        detail = None  # 성공 메타는 본문에 노출 안 함(setting_key 로 충분).
    return RollbackResult(
        action_id=action_id,
        rolled_back=bool(result.get("rolled_back")),
        setting_key=result.get("setting_key"),
        detail=detail if isinstance(detail, str) else None,
    )


# ════════════════════════════════════════════════════════════════════════════
# 피드백 수집 (Phase 4 — 설계서 §2.2(C), §6.4 학습 신호)
# ════════════════════════════════════════════════════════════════════════════
# 👍/👎 + 자유 교정 + 평점을 ai_feedback 에 INSERT 한다. 인증 선택(로그인 사용자는
# user_id 를 HMAC 익명화, 익명 허용). content_hash 로 analysis_ledger 와 조인 가능.
# verify_result(Phase3 verifier 발행) + 이 피드백이 analyzer.quality_drop 의
# 양쪽 신호(verify fail 비율 + feedback down 비율)를 채운다.

_FEEDBACK_TARGET_TYPES = {"llm_output", "analysis", "recommendation"}
_FEEDBACK_VERDICTS = {"up", "down"}


class FeedbackIn(BaseModel):
    """프론트 FeedbackWidget 이 보내는 피드백 1건(익명화 전 — 프론트 계약)."""

    target_type: str = Field(..., description="llm_output | analysis | recommendation")
    verdict: str = Field(..., description="up | down")
    service: str | None = Field(default=None, description="LLM service명(base_interpreter.name)")
    analysis_type: str | None = Field(default=None, description="analysis_ledger.analysis_type 와 정합")
    content_hash: str | None = Field(default=None, description="analysis_ledger.content_hash 조인키")
    correction: str | None = Field(default=None, max_length=4000, description="사용자 교정 텍스트(학습 신호)")
    rating: int | None = Field(default=None, ge=1, le=5, description="1~5 선택")
    payload: dict | None = Field(default=None, description="추가 컨텍스트(서버가 PII 마스킹)")


class FeedbackResult(BaseModel):
    id: str
    accepted: bool


@router.post("/feedback", response_model=FeedbackResult)
async def submit_feedback(
    fb: FeedbackIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FeedbackResult:
    """사용자 피드백을 ai_feedback 에 INSERT. 인증 선택(익명 허용)·PII 마스킹."""
    import json as _json

    from sqlalchemy import text

    from app.services.growth import capture_service

    if fb.target_type not in _FEEDBACK_TARGET_TYPES:
        raise HTTPException(status_code=400, detail="잘못된 target_type 입니다.")
    if fb.verdict not in _FEEDBACK_VERDICTS:
        raise HTTPException(status_code=400, detail="verdict 는 up 또는 down 이어야 합니다.")

    # 인증 선택: 로그인 사용자면 user_id → HMAC user_hash(원본 미저장), tenant_id 귀속.
    user_id, tenant_id = _extract_identity(request)
    user_hash = capture_service.hash_user_id(user_id) if user_id else None
    # payload 는 capture_service 의 PII 마스킹 재사용(이메일/전화/주민번호/주소 등).
    masked_payload = capture_service.mask_pii(fb.payload) if fb.payload else None

    try:
        row = (await db.execute(text(
            "INSERT INTO ai_feedback "
            "(tenant_id, user_hash, target_type, service, analysis_type, "
            " content_hash, verdict, correction, rating, payload) "
            "VALUES (:tid, :uh, :tt, :svc, :at, :ch, :v, :corr, :rt, "
            " CAST(:pl AS jsonb)) "
            "RETURNING id"
        ), {
            "tid": tenant_id, "uh": user_hash, "tt": fb.target_type,
            "svc": fb.service, "at": fb.analysis_type, "ch": fb.content_hash,
            "v": fb.verdict, "corr": fb.correction, "rt": fb.rating,
            "pl": _json.dumps(masked_payload, ensure_ascii=False, default=str)
            if masked_payload is not None else None,
        })).fetchone()
        await db.commit()
    except Exception as e:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning("ai_feedback INSERT 실패", err=str(e)[:160])
        raise HTTPException(status_code=500, detail="피드백 저장에 실패했습니다.") from e

    return FeedbackResult(id=str(row[0]) if row else "", accepted=True)


# ════════════════════════════════════════════════════════════════════════════
# 설정 API (Phase 4 — L1 자가수정 수동제어, 관리자 전용, 설계서 §6.2)
# ════════════════════════════════════════════════════════════════════════════
# POST /settings        : platform_settings 수동 upsert(key/value/scope/ttl).
# POST /settings/{key}/rollback : clear_setting 으로 즉시 원복(롤백) + 감사.
# 모두 super_admin(tier) 전용. L1 자동조치가 만든 설정도 같은 경로로 사람이 제어 가능.

class SettingIn(BaseModel):
    """수동 설정 upsert 요청(프론트 계약)."""

    key: str = Field(..., min_length=1, max_length=200)
    value: dict | list | str | int | float | bool | None = Field(
        default=None, description="jsonb 로 저장될 값"
    )
    scope: str = Field(default="global", max_length=100)
    ttl_minutes: int | None = Field(
        default=None, ge=1, le=10080, description="만료(분). 지정 시 만료 후 자동원복"
    )


class SettingResult(BaseModel):
    key: str
    scope: str
    ok: bool
    ttl_expires_at: datetime | None = None


class SettingRollbackResult(BaseModel):
    key: str
    scope: str
    rolled_back: bool


@router.post("/settings", response_model=SettingResult)
async def set_growth_setting(
    body: SettingIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SettingResult:
    """platform_settings 수동 upsert(관리자 전용) + 감사기록."""
    from datetime import timedelta

    from app.services.growth import schema_guard

    user_id = await _require_admin(request, db)

    ttl_expires_at = None
    if body.ttl_minutes:
        ttl_expires_at = datetime.now(UTC) + timedelta(minutes=body.ttl_minutes)

    ok = await schema_guard.set_setting(
        db, body.key, body.value, scope=body.scope,
        ttl_expires_at=ttl_expires_at, updated_by=user_id,
    )

    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=user_id, actor_role="super_admin",
            action="growth.setting.set", target=f"{body.key}@{body.scope}",
            detail={"value": body.value, "ttl_minutes": body.ttl_minutes, "ok": ok},
        )
    except Exception:  # noqa: BLE001
        pass

    return SettingResult(
        key=body.key, scope=body.scope, ok=ok, ttl_expires_at=ttl_expires_at
    )


@router.post("/settings/{key}/rollback", response_model=SettingRollbackResult)
async def rollback_growth_setting(
    key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: str = Query(default="global"),
) -> SettingRollbackResult:
    """platform_settings 설정 즉시 삭제(롤백 = 원래값으로 즉시 원복) + 감사. 관리자 전용."""
    from app.services.growth import schema_guard

    user_id = await _require_admin(request, db)
    rolled = await schema_guard.clear_setting(db, key, scope=scope)

    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=user_id, actor_role="super_admin",
            action="growth.setting.rollback", target=f"{key}@{scope}",
            detail={"rolled_back": rolled},
        )
    except Exception:  # noqa: BLE001
        pass

    return SettingRollbackResult(key=key, scope=scope, rolled_back=rolled)


# ════════════════════════════════════════════════════════════════════════════
# 자가학습 L3 — 데이터셋 다운로드 · few-shot 후보 승인 (Phase 5, 관리자, 설계 §6.4)
# ════════════════════════════════════════════════════════════════════════════
# GET  /learning/dataset      : (input_summary, good_output) 페어 JSONL 다운로드.
#                               ★생성/다운로드까지만 — 파인튜닝 잡 트리거 절대 없음.
# POST /learning/promote      : learning_example candidate → active (사람 승인) + 감사.
#                               ★자동 활성 금지 — 이 경로(관리자 사람)로만 활성화.
# 모두 super_admin(tier) 전용.

_PROMOTE_STATUSES = {"active", "rejected"}


@router.get("/learning/dataset", response_class=PlainTextResponse)
async def learning_dataset(
    request: Request,
    db: AsyncSession = Depends(get_db),
    service: str | None = Query(default=None, description="service 필터(미지정=전체)"),
    status: str = Query(default="active", description="active(기본) | candidate"),
    limit: int = Query(default=5000, ge=1, le=20000),
) -> PlainTextResponse:
    """learning_examples (input_summary, good_output) 페어 JSONL 다운로드(관리자).

    ★생성/다운로드까지만 — 파인튜닝 잡은 절대 트리거하지 않는다(사람이 수동 실행).
    기본 status='active'(사람이 promote 한 것)만. candidate 도 옵션 지정 가능.
    """
    from app.services.growth import learning_loop

    user_id = await _require_admin(request, db)
    statuses = ("active",) if status != "candidate" else ("candidate",)
    ds = await learning_loop.build_dataset_jsonl(
        db, service=service, statuses=statuses, limit=limit
    )

    # 감사: 누가 어떤 학습셋을 다운로드했는지(데이터 반출 추적).
    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=user_id, actor_role="super_admin",
            action="growth.learn.dataset_download",
            target=f"{service or 'all'}@{status}",
            detail={"count": ds.get("count", 0), "statuses": ds.get("statuses")},
        )
    except Exception:  # noqa: BLE001
        pass

    fname = f"learning_dataset_{service or 'all'}_{status}.jsonl"
    return PlainTextResponse(
        content=ds.get("jsonl", ""),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Dataset-Count": str(ds.get("count", 0))},
    )


class PromoteRequest(BaseModel):
    """few-shot 후보 승인/거부 요청(프론트 계약)."""

    example_id: str = Field(..., description="learning_examples.id")
    status: str = Field(default="active", description="active(승인) | rejected(거부)")


class PromoteResult(BaseModel):
    example_id: str
    status: str


@router.post("/learning/promote", response_model=PromoteResult)
async def promote_learning_example(
    body: PromoteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PromoteResult:
    """learning_example 후보를 사람 승인으로 active(또는 rejected) 전환 + 감사.

    ★few-shot 활성화는 이 경로(관리자 사람)로만 — 자동 활성 절대 금지.
    candidate 상태만 전이 허용(이미 처리된 건 재전이 금지).
    """
    from sqlalchemy import text

    user_id = await _require_admin(request, db)
    if body.status not in _PROMOTE_STATUSES:
        raise HTTPException(
            status_code=400, detail="status 는 active 또는 rejected 여야 합니다."
        )

    row = (await db.execute(text(
        "UPDATE learning_examples SET status = :st "
        "WHERE id = :id AND status = 'candidate' "
        "RETURNING id, status"
    ), {"st": body.status, "id": body.example_id})).fetchone()
    if row is None:
        await db.rollback()
        exists = (await db.execute(text(
            "SELECT status FROM learning_examples WHERE id = :id"
        ), {"id": body.example_id})).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="학습 예시를 찾을 수 없습니다.")
        raise HTTPException(
            status_code=409,
            detail=f"이미 처리된 예시입니다(현재 상태: {exists[0]}).",
        )
    await db.commit()

    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=user_id, actor_role="super_admin",
            action=f"growth.learn.promote.{body.status}", target=body.example_id,
            detail={"status": body.status},
        )
    except Exception:  # noqa: BLE001
        pass

    return PromoteResult(example_id=str(row[0]), status=str(row[1]))
