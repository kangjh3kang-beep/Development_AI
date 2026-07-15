"""부지기반(site basis) 게이트 라우터 — 명세 P7 최소 사상(WP-G).

엔드포인트:
 - POST /api/v1/basis/assess          : P2·P4 게이트 status + P3 확정여부 → P0 자동집계
                                          (ANALYZED/REVIEW_REQUIRED, 원장 감사기록).
 - POST /api/v1/basis/{run_id}/approve: 인간승인 액션 — 전건 P0 재확인 충족일 때만
                                          APPROVED(→AUTHORIZED)로 전이.
 - GET  /api/v1/basis/{run_id}        : 현재 상태 조회.

★불변식: /assess는 절대 AUTHORIZED(APPROVED)를 만들지 않는다. /approve만 가능하고, 그마저
approved_by(호출자)·P0 전건 충족이 필수다(site_basis_state.can_approve 구조적 강제).

★테넌트 격리(분리 리뷰 HIGH-1): 3개 엔드포인트 모두 current_user.tenant_id를 서비스 계층에
전달해 run_id 조회·승인을 테넌트로 스코프한다(교차테넌트가 남의 run_id를 추정해 조회·승인하는
것을 방지 — §13 IDOR 재발 패턴). run_id 자체도 tenant_id를 해시 입력에 포함해 테넌트별로
분할된다(site_basis_service._fingerprint) — 심층방어 2중화.

★게이트 status 신뢰경계(분리 리뷰 MEDIUM-3): access_status/dev_act_status는 기본이 호출자
자기신고(caller_declared, 위조 가능)다. site_context(판정 재료)를 함께 보내면 서버가 권위
서비스(access_basis_service·dev_act_permit_gate)로 재도출·교차검증한다. 상세는
app/schemas/basis.py 모듈 docstring 참조.

★승인 권한 티어(분리 리뷰 항목6 — 코드 변경 없음, 제품 결정 필요): 현재 /approve는
get_current_user(인증)만 요구하고, "승인 가능 역할/티어"(예: 관리자·특정 직무로 제한)는 별도
강제하지 않는다. 인증된 사용자면 누구나 자신이 속한 테넌트의 ANALYZED 건을 승인할 수 있다.
승인자 역할 제한이 필요한지는 RBAC 정책의 제품 결정 사항으로 이 WP 범위 밖이다(후속 과제).

게이트: 인증(get_current_user)만. 규칙기반(LLM 무의존)이라 무과금(enforce_llm_quota 미부착).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.basis import SiteBasisApproveRequest, SiteBasisAssessRequest, SiteBasisResult
from app.services.auth.auth_service import get_current_user

router = APIRouter(prefix="/basis", tags=["부지기반 게이트(P7)"])


def _tenant_of(current_user) -> str | None:
    """current_user에서 tenant_id를 정직하게 추출(없으면 None — 날조 금지)."""
    return str(getattr(current_user, "tenant_id", "") or "") or None


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
        tenant_id=_tenant_of(current_user),
        pnu=req.pnu, address=req.address, project_id=req.project_id,
        access_status=req.access_status, dev_act_status=req.dev_act_status,
        rights_confirmed=req.rights_confirmed, site_context=req.site_context,
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
    """인간승인 액션 — ANALYZED + 승인시점 P0 전건 충족일 때만 APPROVED(AUTHORIZED).

    ★승인 가능 역할/티어 제한 없음(모듈 docstring "승인 권한 티어" 참조 — 제품 결정 후속 과제).
    """
    from app.services.basis.site_basis_service import approve_site_basis
    from app.services.ledger.analysis_ledger_service import attach_ledger_hash

    approved_by = str(getattr(current_user, "id", "") or getattr(current_user, "email", "") or "")
    result = await approve_site_basis(
        db=db, run_id=run_id, approved_by=approved_by, tenant_id=_tenant_of(current_user),
        access_status=req.access_status, dev_act_status=req.dev_act_status,
        rights_confirmed=req.rights_confirmed,
    )
    if not result.get("ok", True):
        # ★HIGH-1: run_id가 다른 테넌트 소유거나 미존재거나 동일 메시지("없음") — 존재 여부를
        #   노출하지 않는다(IDOR 오라클 방지).
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
    """현재 상태 조회(projection 테이블 단건) — 테넌트 스코프(HIGH-1)."""
    from app.services.basis.site_basis_service import get_site_basis

    result = await get_site_basis(db=db, run_id=run_id, tenant_id=_tenant_of(current_user))
    if result is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id} 없음(먼저 /basis/assess 호출 필요)")
    result.pop("ledger", None)
    return SiteBasisResult(**result)
