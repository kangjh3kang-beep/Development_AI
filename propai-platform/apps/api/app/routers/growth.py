"""자가성장 엔진 — 텔레메트리 수집 라우터(설계서 §3.2).

POST /api/v1/growth/events
- 프론트 event-collector 가 5초/20건 배치로 sendBeacon 전송하는 이벤트 수신.
- 인증 선택적(익명 허용). Authorization: Bearer 가 있으면 user_id/tenant_id 추출
  → user_id 는 서버가 HMAC 익명화(capture_service), 원본 미저장.
- event_id(uuid) 멱등(중복 전송은 적재 시 DO NOTHING).
- 동기 INSERT 없음: record_event() 로 큐 push 만(적재는 Celery/폴백).
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
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


async def _require_admin(request: Request, db: "AsyncSession") -> str:
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
