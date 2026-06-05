"""분석 원장(해시체인) 라우터 — append-only 버전 저장·조회·무결성 검증.

prefix=/api/v1/analysis-ledger. 테넌트 격리(JWT tenant_id). 같은 PNU/주소로
간편분석(대시보드)·정식분석(프로젝트)을 한 체인에 누적해 승계·비교·업데이트에 활용.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from app.services.ledger import analysis_ledger_service as ledger

router = APIRouter(prefix="/api/v1/analysis-ledger", tags=["분석원장(해시체인)"])


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
        tenant_id=str(getattr(current, "tenant_id", "") or "") or None,
        pnu=pnu, address=address, project_id=project_id,
    )
