"""분석 원장(해시체인) 라우터 — append-only 버전 저장·조회·무결성 검증.

prefix=/api/v1/analysis-ledger. 테넌트 격리(JWT tenant_id). 같은 PNU/주소로
간편분석(대시보드)·정식분석(프로젝트)을 한 체인에 누적해 승계·비교·업데이트에 활용.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ledger import analysis_ledger_service as ledger
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

router = APIRouter(prefix="/api/v1/analysis-ledger", tags=["분석원장(해시체인)"])

# 관리자군 role(빌링/시크릿과 동기화 — 단일 기준)
_ADMIN_ROLES = {"admin", "manager", "owner", "superadmin", "super_admin", "총괄관리자", "platform_admin"}


def _tid(current: CurrentUser) -> str | None:
    return str(getattr(current, "tenant_id", "") or "") or None


async def _require_admin(current: CurrentUser, db) -> None:
    # ★tier(super_admin)로만 판별 — 가입 시 모두 role='admin'이라 role 게이트는 누출.
    from app.services.billing.billing_service import is_super_admin
    if not await is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")


class AppendRequest(BaseModel):
    analysis_type: str                       # site_analysis | feasibility | design | esg | permit | pipeline ...
    payload: dict[str, Any]
    pnu: str | None = None
    address: str | None = None
    project_id: str | None = None
    source: str = "quick"                    # quick(간편) | project(정식)


@router.post("/append", summary="분석 결과 원장 적재(버전+해시체인)")
async def append(req: AppendRequest, current: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return await ledger.append_analysis(
        analysis_type=req.analysis_type, payload=req.payload,
        tenant_id=str(getattr(current, "tenant_id", "") or "") or None,
        pnu=req.pnu, address=req.address, project_id=req.project_id,
        source=req.source, created_by=str(getattr(current, "user_id", "") or "") or None,
    )


@router.get("/latest", summary="체인 최신 분석 조회(타입 지정 또는 전체)")
async def latest(
    analysis_type: str | None = None, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None,
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    data = await ledger.get_latest(
        analysis_type=analysis_type,
        tenant_id=str(getattr(current, "tenant_id", "") or "") or None,
        pnu=pnu, address=address, project_id=project_id,
    )
    return {"ok": data is not None, "data": data}


@router.get("/history", summary="체인 버전 이력(타임라인)")
async def history(
    analysis_type: str, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None, limit: int = 50,
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    rows = await ledger.get_history(
        analysis_type=analysis_type,
        tenant_id=str(getattr(current, "tenant_id", "") or "") or None,
        pnu=pnu, address=address, project_id=project_id, limit=limit,
    )
    return {"ok": True, "count": len(rows), "history": rows}


@router.get("/verify", summary="체인 무결성 검증(변조탐지)")
async def verify(
    analysis_type: str, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None,
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await ledger.verify_chain(
        analysis_type=analysis_type,
        tenant_id=_tid(current),
        pnu=pnu, address=address, project_id=project_id,
    )


@router.get("/verify-all", summary="전 체인 무결성 일괄검증(테넌트/프로젝트)")
async def verify_all(
    project_id: str | None = None,
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await ledger.verify_all_chains(tenant_id=_tid(current), project_id=project_id)


# ── 사용 용량(구독자별) 제한·삭제·상향 ──
@router.get("/usage", summary="저장 사용량/한도 조회")
async def usage(current: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return await ledger.get_usage(_tid(current))


class DeleteChainRequest(BaseModel):
    analysis_type: str
    pnu: str | None = None
    address: str | None = None
    project_id: str | None = None


@router.post("/delete-chain", summary="특정 분석 체인 삭제(용량 확보)")
async def delete_chain(req: DeleteChainRequest, current: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return await ledger.delete_chain(
        analysis_type=req.analysis_type, tenant_id=_tid(current),
        pnu=req.pnu, address=req.address, project_id=req.project_id,
    )


@router.post("/prune", summary="체인별 최신 N개만 남기고 정리(용량 확보)")
async def prune(keep_per_chain: int = 5, current: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return await ledger.prune_old_versions(_tid(current), keep_per_chain=max(1, keep_per_chain))


class SetQuotaRequest(BaseModel):
    tenant_id: str
    max_entries: int


@router.post("/admin/set-quota", summary="관리자: 테넌트 용량 한도 상향/조정")
async def admin_set_quota(
    req: SetQuotaRequest, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    await _require_admin(current, db)
    result = await ledger.set_quota(req.tenant_id, req.max_entries)
    from app.core.audit import audit_admin_action
    await audit_admin_action(
        actor_id=str(getattr(current, "user_id", "") or ""), actor_role=getattr(current, "role", ""),
        action="ledger.set_quota", target=req.tenant_id, tenant_id=_tid(current),
        detail={"max_entries": req.max_entries},
    )
    return result
