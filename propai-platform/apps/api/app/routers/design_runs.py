"""design-runs 라우터 — 설계 실행의 승인차원·실행차원 커맨드(WP-L · A3).

이 라우터가 노출하는 것(두 개의 독립된 축):
 - POST /api/v1/design-runs/{run_id}/approve : 승인차원 전이(DRAFT→APPROVED, 명시 인간승인).
     Idempotency-Key 헤더로 재전송 안전(같은 키 재전송=같은 응답).
 - POST /api/v1/design-runs/{run_id}/job     : 실행차원 전이(QUEUED/RUNNING/SUCCEEDED/FAILED).
 - POST /api/v1/design-runs/{run_id}/cancel  : 실행차원 취소(비터미널만 — 터미널 재취소=409).
 - GET  /api/v1/design-runs/{run_id}         : 승인차원(status)·실행차원(job_status) 결합 뷰.

★두 차원 독립(계획서 §4 WP-L ★): 승인차원 status(DRAFT/APPROVED)는 design_run_store가,
  실행차원 job_status(QUEUED/…)는 design_run_job이 각자 자기 컬럼만 전이한다. /approve는 job_status를,
  /cancel·/job은 status를 서로 건드리지 않는다(혼용 금지가 모듈 경계로 보장).

★오류봉투: 이 라우터는 problem+json opt-in 표면(/api/v1/design-runs*)이라 ProblemException으로
  RFC 9457 봉투를 낸다(409 터미널·404 미존재·422 키오사용 등). is_problem_surface가 경로로 판정.

★테넌트 격리: 모든 커맨드는 current_user.tenant_id를 서비스에 전달해 run_id를 스코프한다(IDOR 차단).
  /approve는 비가역 승인이라 tenant 없는 세션을 fail-closed로 거부(WP-G LOW-a 하드닝 동형).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import idempotency
from app.core.database import get_db
from app.core.problem_details import ProblemException
from app.services.auth.auth_service import get_current_user
from app.services.cad import design_run_job, design_run_store

router = APIRouter(prefix="/design-runs", tags=["설계 실행(design-run) 커맨드"])

# Idempotency 저장소 endpoint 키(테넌트·키 공간 분리용 논리 이름).
_EP_APPROVE = "design-runs.approve"


def _tenant_of(current_user) -> str | None:
    """current_user에서 tenant_id를 정직하게 추출(없으면 None — 날조 금지)."""
    return str(getattr(current_user, "tenant_id", "") or "") or None


def _actor_of(current_user) -> str:
    """승인·전이 행위자 식별(id 우선, 없으면 email)."""
    return str(getattr(current_user, "id", "") or getattr(current_user, "email", "") or "")


class DesignRunApproveRequest(BaseModel):
    """설계 실행 승인 요청(선택 메모). 승인자는 인증 세션에서 도출(본문 신뢰 안 함)."""

    note: str | None = Field(default=None, description="승인 메모(선택)")


class JobTransitionRequest(BaseModel):
    """실행차원 전이 요청 — 목표 상태(+선택 낙관잠금 기대값)."""

    target: str = Field(..., description="목표 실행상태(QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED)")
    expected_current: str | None = Field(
        default=None, description="현재 상태 기대값(If-Match 의미론 — 지정 시 불일치는 409)"
    )


@router.post("/{run_id}/approve")
async def approve_design_run_endpoint(
    run_id: str,
    req: DesignRunApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """설계 실행을 APPROVED로 승격(명시 인간승인) — Idempotency-Key로 재전송 안전.

    같은 Idempotency-Key로 다시 보내면 재실행 없이 처음 응답을 그대로 돌려준다(멱등). 같은 키인데
    본문·대상이 다르면 422(키 오사용 거부). 승인 실패(비-DRAFT·미존재·타테넌트)는 409로 정직 거부.
    """
    tenant_id = _tenant_of(current_user)
    if tenant_id is None:
        # ★비가역 승인(APPROVED)이라 테넌트 미상 세션은 fail-closed(basis /approve 하드닝 동형).
        raise ProblemException(
            status=403, title="Forbidden", code="TENANT_REQUIRED",
            detail="테넌트 정보가 없는 세션은 설계 실행 승인을 수행할 수 없습니다.",
        )
    approved_by = _actor_of(current_user)

    key = idempotency.normalize_key(idempotency_key)
    request_hash = idempotency.compute_request_hash(
        {"run_id": run_id, "approved_by": approved_by, "note": req.note}
    )

    # ── 멱등 재생 판정(키 있을 때만) ──
    if key:
        look = await idempotency.lookup(
            db=db, key=key, tenant_id=tenant_id, endpoint=_EP_APPROVE, request_hash=request_hash
        )
        if look.state == idempotency.STATE_CONFLICT:
            raise ProblemException(
                status=422, title="Unprocessable Entity", code="IDEMPOTENCY_KEY_REUSED",
                detail="같은 Idempotency-Key가 다른 요청에 재사용되었습니다.",
            )
        if look.state == idempotency.STATE_REPLAY and look.stored is not None:
            replay = look.stored.to_response()
            if replay is not None:
                return replay  # 처음 응답 그대로 재생(재실행 0)

    # ── 실제 승인 실행(승인차원만 — job_status 무접촉) ──
    result = await design_run_store.approve_design_run(
        db=db, run_id=run_id, approved_by=approved_by, tenant_id=tenant_id
    )
    if not result.get("ok", False):
        # 미존재·타테넌트·비-DRAFT 모두 동일 취급(존재 비노출 — IDOR 오라클 방지).
        raise ProblemException(
            status=409, title="Conflict", code="APPROVE_REJECTED",
            detail=result.get("message") or "승인 거부",
        )

    body_dict = {
        "run_id": result["run_id"],
        "status": result.get("status"),
        "approved_by": result.get("approved_by"),
    }
    body_bytes = json.dumps(body_dict, ensure_ascii=False).encode("utf-8")

    # ── 성공 응답을 키로 기억(다음 재전송이 이 바이트를 그대로 재생) ──
    if key:
        await idempotency.save(
            db=db, key=key, tenant_id=tenant_id, endpoint=_EP_APPROVE,
            request_hash=request_hash, response_status=200, body=body_bytes,
            media_type="application/json", run_id=result["run_id"],
        )

    from fastapi.responses import Response

    return Response(content=body_bytes, status_code=200, media_type="application/json")


@router.post("/{run_id}/job")
async def transition_job_endpoint(
    run_id: str,
    req: JobTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """실행차원(job_status) 전이 — 규칙 위반·터미널 전이는 409, 미존재는 404. status 무접촉."""
    tenant_id = _tenant_of(current_user)
    result = await design_run_job.set_job_status(
        db=db, run_id=run_id, target=req.target, tenant_id=tenant_id,
        expected_current=req.expected_current, require_expected=req.expected_current is not None,
    )
    if not result.get("ok", False):
        _raise_for_code(result)
    return {
        "run_id": result["run_id"],
        "job_status": result.get("job_status"),
        "previous": result.get("previous"),
    }


@router.post("/{run_id}/cancel")
async def cancel_job_endpoint(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """실행 취소 — 비터미널만 CANCELLED. 터미널(SUCCEEDED/CANCELLED/FAILED) 재취소는 409. status 무접촉."""
    tenant_id = _tenant_of(current_user)
    result = await design_run_job.cancel_job(db=db, run_id=run_id, tenant_id=tenant_id)
    if not result.get("ok", False):
        _raise_for_code(result)
    return {"run_id": result["run_id"], "job_status": result.get("job_status"),
            "previous": result.get("previous")}


@router.get("/{run_id}")
async def get_design_run_endpoint(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """승인차원(status)·실행차원(job_status) 결합 뷰 — 두 축이 독립임을 그대로 노출(테넌트 스코프)."""
    tenant_id = _tenant_of(current_user)
    run = await design_run_store.get_design_run(db=db, run_id=run_id, tenant_id=tenant_id)
    if run is None:
        raise ProblemException(
            status=404, title="Not Found", code="RUN_NOT_FOUND",
            detail=f"run_id={run_id} 없음(먼저 설계 실행 persist 필요).",
        )
    job = await design_run_job.get_job(db=db, run_id=run_id, tenant_id=tenant_id)
    return {
        "run_id": run["run_id"],
        "status": run.get("status"),            # 승인차원(DRAFT/APPROVED)
        "job_status": (job or {}).get("job_status"),  # 실행차원(QUEUED/…/None)
        "input_hash": run.get("input_hash"),
        "geometry_hash": run.get("geometry_hash"),
        "approved_by": run.get("approved_by"),
    }


def _raise_for_code(result: dict) -> None:
    """서비스 결과 code(not_found/conflict)를 problem+json 예외로 사상한다."""
    code = result.get("code")
    message = result.get("message") or "요청을 처리할 수 없습니다."
    if code == "not_found":
        raise ProblemException(status=404, title="Not Found", code="RUN_NOT_FOUND", detail=message)
    # conflict(불법 전이·터미널 재취소·버전충돌) → 409.
    raise ProblemException(status=409, title="Conflict", code="INVALID_TRANSITION", detail=message)
