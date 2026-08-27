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

# ★프론트 유니온(`apps/web/lib/growth/event-collector.ts:GrowthEventType`)과 **1:1 이어야 한다.**
#   한쪽에만 있는 타입은 여기서 조용히 `rejected` 로 버려진다 — 프론트는 논블로킹이라
#   오류를 못 보고, 테스트도 초록이다(계측이 죽어 있는데 아무도 모른다).
#   그 침묵을 `apps/web/lib/growth/__tests__/event-type-whitelist.parity.test.ts` 가 잠근다.
_ALLOWED_TYPES = {
    "page_view", "click", "funnel_step", "api_call", "api_error", "js_error",
    "promise_rejection", "web_vital", "llm_call", "verify_result", "fallback",
    "heal_action",
    # 선택 오염 관측(2026-08-24) — 다필지 선택이 "하나의 개발 부지"가 아닌 빈도.
    "selection_contamination_observation",
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

# ★`superseded` — 정리 배치가 **승계된 옛 행**에 붙이는 상태(`insight_retention`).
#   어휘에 없으면 `GET /growth/insights?status=superseded` 가 **400** 이라
#   2,678행의 상태 전이를 **제품 안에서 확인할 방법이 0** 이 된다(되돌리기가 원시 SQL 뿐).
#   조회는 가능해야 잘못 닫힌 것을 사람이 발견한다(2026-08-27 독립 리뷰 H5).
#   ★`_ACK_STATUSES` 에는 넣지 않는다 — 승계분은 사람이 재처리할 대상이 아니다.
_INSIGHT_STATUSES = {"open", "acknowledged", "acted", "dismissed", "superseded"}
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
    """인사이트 목록 + **집계**.

    ★`total` 과 `actionable_counts` 는 **다른 것**이다 — 이름으로 갈라 둔다:
      · `total`             : 같은 필터에 걸리는 **전체 행 수**(비조치 타입 포함)
      · `actionable_counts` : 같은 필터에서 **조치 대상만** severity 별로 센 값

    ★★왜 서버가 세는가(2026-08-26 라이브 실측):
      화면은 `?sort=severity&limit=200` 으로 받아 **그 200행을 세고 있었다.** 그런데 라이브 분포가
      critical 79 · warn 476 · info 2,544 라 200행은 `critical 79 + warn 121` 로 채워지고
      **info 는 0행 도달**한다. 결과로 요약 카드가 warn 을 **476이 아니라 121**로 표시했다
      (**74% 과소계상**). 페이지 크기가 집계를 결정하는 구조였다.
      → 집계는 **`limit` 과 무관하게** 서버가 같은 술어로 센다.
    """

    items: list[GrowthInsightOut]
    total: int
    #: severity → 건수. **조치 대상만**(NON_ACTIONABLE 타입 제외). 필터 전체 기준.
    actionable_counts: dict[str, int] = Field(default_factory=dict)


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

    # ★조치대상 집계 — `total` 과 **같은 술어**로 세되 비조치 타입만 뺀다.
    #   비조치 타입은 `insight_types.NON_ACTIONABLE`(백엔드 정본)에서 온다. 종전엔 그 상수의
    #   **소비처가 0**이었고 같은 정책이 프론트 리터럴로 중복 구현돼 있었다 — 여기서 잇는다.
    #   ★`limit` 을 타지 않는다: 이 값이 페이지 크기에 따라 변하면 집계가 아니라 표본이다.
    # ★지연 임포트 — 이 라우터의 형제 관행을 따른다(`capture_service`·`heal_actions`·
    #   `schema_guard` 전부 함수 안에서 임포트한다). 모듈 수준으로 올리면 그 관행이
    #   회피하고 있는 것(순환참조·기동비용)을 내가 확인하지 않은 채 깨뜨리게 된다.
    from app.services.growth.insight_types import NON_ACTIONABLE

    _na = sorted(NON_ACTIONABLE)
    _cnt_params = dict(params)
    _cnt_where = where_sql
    if _na:
        _cnt_where = f"{where_sql} AND insight_type <> ALL(:na_types)"
        _cnt_params["na_types"] = _na
    actionable_counts: dict[str, int] = {
        str(r[0]): int(r[1])
        for r in (await db.execute(text(
            f"SELECT severity, COUNT(*) FROM platform_insights "
            f"WHERE {_cnt_where} GROUP BY severity"
        ), _cnt_params)).fetchall()
    }

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
    return GrowthInsightList(items=items, total=int(total),
                             actionable_counts=actionable_counts)


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

    # 허용 전이만. `dismissed` 등 이미 **사람이** 판단한 상태는 임의 재전이 금지.
    #
    # ★`acted → dismissed` 만 연다(2026-08-27). `acted` 는 **기계**(healing_rules)가 쓰는
    #   상태다. 기계가 넣을 수 있는 상태에 사람이 못 들어가면 **한쪽만 걸린 경계**가 된다
    #   (규율 §D-19 — 경계를 걸면 양방향으로).
    #   ★근거는 이론이 아니라 실측이다: `threshold_relax` 는 base_client 를 통해 **실제
    #     프로덕션 HTTP 타임아웃을 곱하는** 유일한 PRODUCT 이펙터인데, 무효한 치유를
    #     걸러 준다던 `heal_escalation` 은 **라이브에 0건**이다(heal 액션 520건이 쌓이는
    #     동안 단 한 건도 없었다 — 대조군 `fallback_rate open` 21건으로 조회기 생존 확인).
    #     발화한 적 없는 안전망 위에 "사람은 못 건드려도 된다"를 세울 수 없다.
    #   ★★열린 것은 **이 한 방향뿐**이다 — `acted → open`(기계 상태 되돌리기)이나
    #     `dismissed → *` 는 여전히 막힌다. 전면 개방이 아니다.
    allowed_from = ["open", "acknowledged"]
    if req.status == "dismissed":
        allowed_from = ["open", "acknowledged", "acted"]
    row = (await db.execute(text(
        "UPDATE platform_insights SET status = :st "
        "WHERE id = :id AND status = ANY(:from_) "
        "RETURNING id, status"
    ), {"st": req.status, "id": insight_id, "from_": allowed_from})).fetchone()
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
    # payload 는 capture_service 의 PII 마스킹 재사용 — 이메일/전화/주민번호 **값 패턴** + 민감 **키**(이름·주소 등). ★주소는 **값 안에서 지워지지 않는다**(2026-08-27 실측 — `_mask_str` 에 주소 정규식 없음). 부채는 `tests/test_pii_mask_diagnostic_keys.py` 의 xfail 로 초록 안에 보인다.
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
# GET  /learning/candidates   : 후보 목록(id 포함) — 사람이 무엇을 승인할지 고를 수 있게.
#                               ★이게 없으면 promote 가 요구하는 example_id 를 알 길이 없어
#                                 "사람 승인 게이트"에 문이 없다(2026-08-19 결함).
# GET  /learning/dataset      : (input_summary, good_output) 페어 JSONL 다운로드.
#                               ★생성/다운로드까지만 — 파인튜닝 잡 트리거 절대 없음.
# POST /learning/promote      : learning_example candidate → active (사람 승인) + 감사.
#                               ★자동 활성 금지 — 이 경로(관리자 사람)로만 활성화.
# 모두 super_admin(tier) 전용.

_PROMOTE_STATUSES = {"active", "rejected"}
# 후보 목록에서 조회 가능한 status(learning_loop._VALID_STATUSES 와 같은 어휘).
_LEARNING_LIST_STATUSES = {"candidate", "active", "rejected"}


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
    import os

    from app.services.growth import learning_loop

    user_id = await _require_admin(request, db)
    statuses = ("active",) if status != "candidate" else ("candidate",)
    # ★P16 학습게이트(WP-H 세션2): 자산권리 미확인 예시를 학습셋에서 제외(권리불명=금지)한다.
    #   실배선은 여기까지(엔드포인트→build_dataset_jsonl→asset_rights). 실소비 활성화는 운영 플래그
    #   GROWTH_ENFORCE_TRAIN_RIGHTS 로 제어하며 기본 OFF(무회귀) — 레지스트리 시딩(ingest 시
    #   upsert_asset_right)과 함께 WP-J 가 ON 으로 전환한다.
    enforce_rights = (os.getenv("GROWTH_ENFORCE_TRAIN_RIGHTS") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    ds = await learning_loop.build_dataset_jsonl(
        db, service=service, statuses=statuses, limit=limit,
        enforce_asset_rights=enforce_rights,
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


class LearningCandidateOut(BaseModel):
    """few-shot 후보 1건(관리자 검토용). ★`id` 가 곧 promote 의 `example_id` 다."""

    id: str
    service: str | None = None
    analysis_type: str | None = None
    status: str
    tenant_id: str | None = None
    content_hash: str | None = None
    input_summary: str = ""
    input_summary_truncated: bool = False
    good_output: str = ""
    good_output_truncated: bool = False
    created_at: str | None = None
    # 자산권리 표시(거르기 아님) — False 면 화면이 "권리 미확인"을 눈에 보이게 띄운다.
    train_allowed: bool = False
    rights_scope: str | None = None


class LearningCandidateList(BaseModel):
    items: list[LearningCandidateOut]
    total: int
    statuses: list[str]
    service: str | None = None
    tenant_id: str | None = None
    limit: int
    offset: int


@router.get("/learning/candidates", response_model=LearningCandidateList)
async def list_learning_candidates(
    request: Request,
    db: AsyncSession = Depends(get_db),
    service: str | None = Query(default=None, description="service 필터(미지정=전체)"),
    status: str = Query(default="candidate", description="candidate(기본) | active | rejected"),
    tenant_id: str | None = Query(default=None, description="테넌트 필터(미지정=전체)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> LearningCandidateList:
    """few-shot 후보 목록(관리자 검토용) — 승인 화면이 이 목록으로 promote 대상을 지목한다.

    ★왜 필요했나: promote 는 `example_id` 를 요구하는데, 그때까지 learning_examples 를 읽는
      유일한 경로(build_dataset_jsonl)가 id 를 안 돌려줬다. 화면을 만들어도 무엇을 승인할지
      지목할 수가 없었다 = 사람 승인 게이트에 문이 없었다.

    ★테넌트 범위: 기본 전체다(테넌트로 자동 축소하지 않는다). 근거 —
      ① 이 엔드포인트의 문지기 `_require_admin` 은 users.tier='super_admin' = **플랫폼 총괄
         관리자**이고, 같은 문지기를 쓰는 promote 도 테넌트 조건 없이 id 로 전이한다.
         목록만 좁히면 다른 테넌트의 후보는 **보이지도 승인되지도 않아** 그 테넌트에서는
         few-shot 이 영영 비는, 지금 고치는 결함이 그대로 남는다.
      ② 대신 행마다 tenant_id 를 실어 보낸다 — 승인 시 그 예시가 **어느 테넌트의 프롬프트에**
         주입될지(base_interpreter._load_fewshot 은 tenant_id 로 스코핑한다) 화면에서 보이게.
      ③ 특정 테넌트만 보려면 `tenant_id` 쿼리로 **명시적으로** 좁힌다(조용히 숨기지 않는다).
      본문은 적재 시점에 이미 PII 마스킹(learning_loop._summarize_payload → mask_pii)된 요약이다.
    """
    from app.services.growth import learning_loop

    user_id = await _require_admin(request, db)
    if status not in _LEARNING_LIST_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="status 는 candidate, active, rejected 중 하나여야 합니다.",
        )

    res = await learning_loop.list_examples(
        db, statuses=(status,), service=service, tenant_id=tenant_id,
        limit=limit, offset=offset,
    )

    # 감사: 누가 어떤 후보 묶음을 열람했는지(승인 이력과 짝이 되게 — promote 도 감사를 남긴다).
    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=user_id, actor_role="super_admin",
            action="growth.learn.candidates_list",
            target=f"{service or 'all'}@{status}",
            detail={"count": len(res.get("items", [])), "total": res.get("total", 0),
                    "tenant_id": tenant_id},
        )
    except Exception:  # noqa: BLE001
        pass

    return LearningCandidateList(
        items=[LearningCandidateOut(**it) for it in res.get("items", [])],
        total=int(res.get("total", 0)),
        # ★폴백을 없앴다(2026-08-19 변이 재분류): `res.get("statuses", [status])` 의 기본값은
        #   400 게이트를 지난 뒤에는 **항상 같은 값**이라 도달 불가였고, 그 때문에 키 이름을
        #   바꾸는 변이가 조용히 살아남았다(설명 가능한 생존이지만 배선 문자열이라 다음 사람이
        #   진짜 구멍과 구분하기 어렵다). list_examples 는 실패 경로에서도 "statuses" 를 반드시
        #   채워 돌려주므로 직접 읽는다 — 키가 어긋나면 즉시 터져서 드러난다.
        statuses=list(res["statuses"]),
        service=service,
        tenant_id=tenant_id,
        limit=int(res.get("limit", limit)),
        offset=int(res.get("offset", offset)),
    )


class PromoteRequest(BaseModel):
    """few-shot 후보 승인/거부 요청(프론트 계약)."""

    example_id: str = Field(..., description="learning_examples.id")
    status: str = Field(default="active", description="active(승인) | rejected(거부)")
    # ★학습권리가 확인되지 않은 자산을 승인하려면 이 값을 명시해야 한다(기본 거부).
    #   "몰랐다"로 활성화되는 것을 막고, 켠 사람이 감사에 남게 한다.
    acknowledge_unverified_rights: bool = Field(
        default=False,
        description="학습권리 미확인 자산임을 알고도 승인한다(출처·이용조건 확인 책임 인수)",
    )


class PromoteResult(BaseModel):
    example_id: str
    status: str
    # 권리 미확인인데 사람이 책임을 인수해 통과시킨 건인지(화면이 그대로 표기).
    rights_acknowledged: bool = False


@router.post("/learning/promote", response_model=PromoteResult)
async def promote_learning_example(
    body: PromoteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PromoteResult:
    """learning_example 후보를 사람 승인으로 active(또는 rejected) 전환 + 감사.

    ★few-shot 활성화는 이 경로(관리자 사람)로만 — 자동 활성 절대 금지.
    candidate 상태만 전이 허용(이미 처리된 건 재전이 금지).

    ★★학습권리 게이트(2026-08-19 적대리뷰 HIGH). **실측하고 적는다**:
      · `base_interpreter._load_fewshot` 은 `status='active'` 만 보고 자산권리를 **전혀 보지
        않는다**(그 파일의 asset_rights/train_allowed 참조 0건 — 대조군 learning_loop 20건).
      · `build_dataset_jsonl` 의 `enforce_asset_rights` 는 `GROWTH_ENFORCE_TRAIN_RIGHTS`
        기본 OFF 이고, 그건 **학습셋 다운로드** 경로지 **프롬프트 주입** 경로가 아니다.
      → 즉 주입 경로에는 권리 게이트가 없다. 그래서 **여기서** 막는다.
      불변식: status='active' 인 행은 (권리 확인됨) **또는** (사람이 미확인임을 알고
      명시적으로 책임을 인수했고 그 사실이 감사에 남았다) 중 하나다.

      ▶왜 '무조건 거부'가 아닌가(실측 근거): 학습예시의 권리를 레지스트리에 넣는 경로가
        **오늘 0건**이다. `upsert_asset_rights_batch` 의 유일한 실사용처는
        `design_ingest/aihub_seed_service.py` 이고 그건 **도면 파일 해시** 키공간이다.
        learning_examples 의 content_hash 는 `analysis_ledger` 해시라 **서로 다른 키공간**이다.
        무조건 거부하면 오늘 승인 가능한 후보가 0이 되어, 이 PR 이 여는 문이 곧 벽이 된다
        (= 지금 고치는 결함과 같은 형태). 그래서 '기본 거부 + 명시적 인수'로 간다.
    """
    from sqlalchemy import text

    user_id = await _require_admin(request, db)
    if body.status not in _PROMOTE_STATUSES:
        raise HTTPException(
            status_code=400, detail="status 는 active 또는 rejected 여야 합니다."
        )

    rights_acknowledged = False
    if body.status == "active":
        # 승인(=프롬프트 주입 허용)일 때만 검사한다. 거부는 안전한 방향이라 권리와 무관.
        from app.services.security.asset_rights import get_asset_right, is_train_allowed

        target = (await db.execute(text(
            "SELECT content_hash, tenant_id FROM learning_examples WHERE id = :id"
        ), {"id": body.example_id})).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="학습 예시를 찾을 수 없습니다.")
        right = await get_asset_right(db, target[0] or "", target[1])
        if not is_train_allowed(right):
            if not body.acknowledge_unverified_rights:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "학습 사용 권리가 확인되지 않은 자산입니다"
                        f"(권리 {getattr(right, 'scope', None) or '미등록'}). "
                        "출처·이용조건을 확인한 뒤 acknowledge_unverified_rights 로 "
                        "명시적으로 승인하세요."
                    ),
                )
            rights_acknowledged = True

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
            # ★권리 미확인인데 사람이 밀어붙인 건은 감사에 반드시 남는다(책임 추적).
            detail={"status": body.status, "rights_acknowledged": rights_acknowledged},
        )
    except Exception:  # noqa: BLE001
        pass

    return PromoteResult(
        example_id=str(row[0]), status=str(row[1]),
        rights_acknowledged=rights_acknowledged,
    )


@router.get("/effectors")
async def effector_firing(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """효과기가 **실제로 발화했는가** — 선언(`effector_reach`) × 실측(`platform_events`).

    ## 왜 이 라우트가 필요한가

    `effector_reach` 표는 *"이 효과기가 동작하면 어디까지 닿는가"* 를 적는다.
    그런데 **"동작한 적이 있는가"** 는 어디에도 없었다. 그래서 표만 읽으면
    `threshold_relax` 를 보고 *"제품에 닿는 효과기가 살아 있다"* 고 읽는데,
    실제로는 며칠째 조용할 수 있고 **그것을 알 방법이 없었다**(라이브 실측 66시간).

    ★**진단하지 판정하지 않는다.** `reach=NONE` 인 효과기가 영원히 발화하지 않는 것이
    정상일 수 있다. 사실(`total`·`last_fired_at`·`hours_since`)과 라벨(`state`)을 함께
    주고, 라벨에 동의하지 않을 수 있게 **원값을 항상 싣는다**.
    """
    from app.services.growth import effector_firing as _ef

    await _require_admin(request, db)
    return await _ef.firing_status(db)
