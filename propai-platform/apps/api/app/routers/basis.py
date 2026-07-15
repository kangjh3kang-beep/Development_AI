"""부지기반(site basis) 게이트 라우터 — 명세 P7 최소 사상(WP-G).

엔드포인트:
 - POST /api/v1/basis/assess          : P2·P4 게이트 status + P3 확정여부 → P0 자동집계
                                          (ANALYZED/REVIEW_REQUIRED, 원장 감사기록).
 - POST /api/v1/basis/{run_id}/approve: 인간승인 액션 — 전건 P0 재확인 충족일 때만
                                          APPROVED(→AUTHORIZED)로 전이.
 - GET  /api/v1/basis/{run_id}        : 현재 상태 조회.

★불변식: /assess는 절대 AUTHORIZED(APPROVED)를 만들지 않는다. /approve만 가능하고, 그마저
approved_by(호출자)·P0 전건 충족이 필수다(site_basis_state.can_approve 구조적 강제).
게이트: 인증(get_current_user)만. 규칙기반(LLM 무의존)이라 무과금(enforce_llm_quota 미부착).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.basis import SiteBasisApproveRequest, SiteBasisAssessRequest, SiteBasisResult
from app.services.auth.auth_service import get_current_user

router = APIRouter(prefix="/basis", tags=["부지기반 게이트(P7)"])


@router.post("/assess", response_model=SiteBasisResult)
async def assess_endpoint(
    req: SiteBasisAssessRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SiteBasisResult:
    """P0 게이트(P2·P3·P4) 자동집계 — 인간승인 없이는 ADVISORY(ANALYZED/REVIEW_REQUIRED)까지만."""
    from app.services.basis.site_basis_service import assess_site_basis
    from app.services.ledger.analysis_ledger_service import attach_ledger_hash

    result = await assess_site_basis(
        db=db,
        tenant_id=str(getattr(current_user, "tenant_id", "") or "") or None,
        pnu=req.pnu, address=req.address, project_id=req.project_id,
        access_status=req.access_status, dev_act_status=req.dev_act_status,
        rights_confirmed=req.rights_confirmed,
        created_by=str(getattr(current_user, "id", "") or "") or None,
    )
    attach_ledger_hash(result, result.pop("ledger", None))
    return SiteBasisResult(**result)


@router.post("/{run_id}/approve", response_model=SiteBasisResult)
async def approve_endpoint(
    run_id: str,
    req: SiteBasisApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SiteBasisResult:
    """인간승인 액션 — ANALYZED + 승인시점 P0 전건 충족일 때만 APPROVED(AUTHORIZED)."""
    from app.services.basis.site_basis_service import approve_site_basis
    from app.services.ledger.analysis_ledger_service import attach_ledger_hash

    approved_by = str(getattr(current_user, "id", "") or getattr(current_user, "email", "") or "")
    result = await approve_site_basis(
        db=db, run_id=run_id, approved_by=approved_by,
        access_status=req.access_status, dev_act_status=req.dev_act_status,
        rights_confirmed=req.rights_confirmed,
    )
    if not result.get("ok", True):
        raise HTTPException(status_code=409, detail=result.get("message") or "승인 거부")
    attach_ledger_hash(result, result.pop("ledger", None))
    result.pop("ok", None)
    return SiteBasisResult(**result)


@router.get("/{run_id}", response_model=SiteBasisResult)
async def get_endpoint(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SiteBasisResult:
    """현재 상태 조회(projection 테이블 단건)."""
    from app.services.basis.site_basis_service import get_site_basis

    result = await get_site_basis(db=db, run_id=run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id} 없음(먼저 /basis/assess 호출 필요)")
    result.pop("ledger", None)
    return SiteBasisResult(**result)
