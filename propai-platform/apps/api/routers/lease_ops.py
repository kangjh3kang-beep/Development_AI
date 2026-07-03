"""임대·임차인 운영(LeaseOps) 라우터 — 임차인/임대계약 CRUD + 공실률·임대수익 집계.

운영서비스 연동 1탄(임대·임차인 관리)의 CRUD 백엔드. 기존 /leases/analyze(계약분석),
/tenant/satisfaction/nps(만족도)는 그대로 재사용(프론트가 결합). 본 라우터는 영속/조회 담당.

멀티테넌트 격리: 모든 엔드포인트는 JWT tenant_id 스코프로 강제(교차 테넌트 차단).
권한: 기존 leases 리소스 정책 재사용(read=조회, write=변경) — analyze 엔드포인트와 일관.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.lease_ops.lease_ops_service import LeaseOpsService
from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db

router = APIRouter()


# ── 요청 스키마 ──
class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    contact: str | None = Field(None, max_length=200)
    business_type: str | None = Field(None, max_length=150)
    project_id: str | None = None
    notes: str | None = None


class ContractCreate(BaseModel):
    unit_label: str = Field(..., min_length=1, max_length=150)
    lessee: str | None = None  # tenants.id (uuid)
    deposit: float = Field(0.0, ge=0)
    monthly_rent: float = Field(0.0, ge=0)
    start_date: str | None = None
    end_date: str | None = None
    status: str = "active"
    area_sqm: float = Field(0.0, ge=0)
    project_id: str | None = None
    notes: str | None = None


class StatusUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=30)


# ── 임차인 ──
@router.post("/tenants")
async def create_tenant(
    body: TenantCreate,
    current_user: CurrentUser = Depends(RequirePermission("leases", "write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """임차인 등록."""
    service = LeaseOpsService(db)
    return await service.create_tenant(
        tenant_id=str(current_user.tenant_id),
        name=body.name,
        contact=body.contact,
        business_type=body.business_type,
        project_id=body.project_id,
        notes=body.notes,
    )


@router.get("/tenants")
async def list_tenants(
    project_id: str | None = None,
    current_user: CurrentUser = Depends(RequirePermission("leases", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """임차인 목록(테넌트 격리)."""
    service = LeaseOpsService(db)
    return await service.list_tenants(
        tenant_id=str(current_user.tenant_id), project_id=project_id
    )


# ── 임대계약 ──
@router.post("/contracts")
async def create_contract(
    body: ContractCreate,
    current_user: CurrentUser = Depends(RequirePermission("leases", "write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """임대계약 등록."""
    service = LeaseOpsService(db)
    return await service.create_contract(
        tenant_id=str(current_user.tenant_id),
        unit_label=body.unit_label,
        lessee=body.lessee,
        deposit=body.deposit,
        monthly_rent=body.monthly_rent,
        start_date=body.start_date,
        end_date=body.end_date,
        status=body.status,
        area_sqm=body.area_sqm,
        project_id=body.project_id,
        notes=body.notes,
    )


@router.get("/contracts")
async def list_contracts(
    project_id: str | None = None,
    status: str | None = None,
    current_user: CurrentUser = Depends(RequirePermission("leases", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """임대계약 목록(필터: project_id, status)."""
    service = LeaseOpsService(db)
    return await service.list_contracts(
        tenant_id=str(current_user.tenant_id),
        project_id=project_id,
        status=status,
    )


@router.patch("/contracts/{contract_id}/status")
async def update_contract_status(
    contract_id: str,
    body: StatusUpdate,
    current_user: CurrentUser = Depends(RequirePermission("leases", "write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """임대계약 상태 변경(active/vacant/expired/terminated 등)."""
    service = LeaseOpsService(db)
    return await service.update_status(
        tenant_id=str(current_user.tenant_id),
        contract_id=contract_id,
        status=body.status,
    )


# ── 집계(대시보드) ──
@router.get("/summary")
async def lease_summary(
    project_id: str | None = None,
    current_user: CurrentUser = Depends(RequirePermission("leases", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """공실률·임대수익 집계(총 세대·임대중·공실수·공실률·월임대료합·연환산수익)."""
    service = LeaseOpsService(db)
    return await service.summary(
        tenant_id=str(current_user.tenant_id), project_id=project_id
    )
