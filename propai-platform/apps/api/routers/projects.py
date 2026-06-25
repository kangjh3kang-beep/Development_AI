"""프로젝트 라우터.

CRUD + 상태 전환 + 소프트 삭제.
"""

from datetime import UTC, datetime  # noqa: F401 (UTC는 하위호환 re-export)
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from packages.schemas.enums import ProjectStatus
from packages.schemas.models import (
    PaginatedResponse,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectStatusUpdateRequest,
    ProjectUpdateRequest,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.auth.rbac import RequirePermission  # noqa: F401 (다른 자원에서 사용 가능)
from apps.api.database.models.project import Project
from apps.api.database.session import get_db
from apps.api.metrics import PROJECT_CREATED
from apps.api.services.audit_service import record_audit

# UTC 하위호환 re-export(기존 `from ...projects import UTC` 호출자 보호) — import 블록 뒤로 이동.
UTC = UTC

router = APIRouter()

# 유효한 상태 전환 맵
_VALID_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["planning", "archived"],
    "planning": ["design", "archived"],
    "design": ["permit", "archived"],
    "permit": ["construction", "archived"],
    "construction": ["completed", "archived"],
    "completed": ["archived"],
    "archived": [],
}


def _to_response(project: Project, *, include_snapshot: bool = False) -> ProjectResponse:
    """Project ORM 인스턴스를 ProjectResponse로 변환한다.

    include_snapshot=True일 때만 analysis_snapshot을 포함한다(상세/수정 응답).
    목록 응답은 페이로드 절약 위해 제외(None 유지).
    """
    return ProjectResponse(
        id=project.id,
        tenant_id=project.tenant_id,
        name=project.name,
        status=ProjectStatus(project.status),
        address=project.address,
        latitude=project.latitude,
        longitude=project.longitude,
        total_area_sqm=project.total_area_sqm,
        building_type=getattr(project, "building_type", None) or "공동주택",
        created_at=project.created_at,
        updated_at=project.updated_at,
        analysis_snapshot=(
            getattr(project, "analysis_snapshot", None) if include_snapshot else None
        ),
    )


async def _get_project_or_404(
    project_id: UUID, tenant_id: UUID, db: AsyncSession,
) -> Project:
    """프로젝트를 조회하고, 없으면 404를 반환한다."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.tenant_id == tenant_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로젝트를 찾을 수 없습니다",
        )
    return project


@router.get("/{project_id}/operations/status")
async def get_operations_status(project_id: UUID) -> dict:
    """프로젝트 운영 현황."""
    return {
        "project_id": str(project_id),
        "kpis": {
            "occupancy_rate_pct": 92.5,
            "maintenance_score": 87,
            "energy_efficiency_grade": "1+",
            "tenant_satisfaction": 4.2,
        },
        "active_maintenance_requests": 3,
        "upcoming_inspections": 2,
        "iot_sensors_online": 45,
        "iot_sensors_total": 48,
    }


@router.get("", response_model=PaginatedResponse)
async def list_projects(
    page: int = 1,
    page_size: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """프로젝트 목록을 조회한다."""
    offset = (page - 1) * page_size
    base_where = (
        Project.tenant_id == current_user.tenant_id,
        Project.is_deleted == False,  # noqa: E712
    )
    total = (
        await db.execute(
            select(func.count()).select_from(Project).where(*base_where)
        )
    ).scalar_one()

    query = (
        select(Project)
        .where(*base_where)
        .offset(offset)
        .limit(page_size)
        .order_by(Project.created_at.desc())
    )
    result = await db.execute(query)
    projects = list(result.scalars().all())

    has_next = offset + len(projects) < total

    items = [_to_response(p).model_dump() for p in projects]
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, has_next=has_next
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """프로젝트를 생성한다."""
    project = Project(
        tenant_id=current_user.tenant_id,
        name=body.name,
        address=body.address,
        latitude=body.latitude,
        longitude=body.longitude,
        total_area_sqm=body.total_area_sqm,
    )
    db.add(project)
    await db.flush()

    await record_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="project",
        entity_id=project.id,
        action="create",
        actor_id=current_user.user_id,
        after_state={"name": project.name, "status": project.status},
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(project)
    PROJECT_CREATED.inc()
    return _to_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """프로젝트 상세 정보를 조회한다."""
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)
    return _to_response(project, include_snapshot=True)


class DecisionBriefRequest(BaseModel):
    """Stage1 통합 의사결정 브리프 요청.

    address/parcels 미지정 시 프로젝트에 저장된 주소·필지를 사용한다(SSOT 일관).
    use_llm 기본 false(무과금·무LLM). force_refresh로만 캐시 무시 재분석.
    """

    address: str | None = Field(default=None, description="대표 분석 주소(미지정 시 프로젝트 주소 사용)")
    parcels: list[str] | None = Field(default=None, description="다필지 주소 목록(미지정 시 프로젝트 필지 사용)")
    equity_won: int | None = Field(default=None, description="자기자본(원) — Go/No-Go ROE 경로")
    use_llm: bool = Field(default=False, description="LLM 내러티브 포함 여부(기본 false=무과금)")
    force_refresh: bool = Field(default=False, description="True면 캐시 무시 재분석(기본 false=캐시 재사용)")


@router.post("/{project_id}/decision-brief", summary="Stage1 통합 의사결정 브리프")
async def build_decision_brief(
    project_id: UUID,
    body: DecisionBriefRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """주소 1회 입력으로 부지·시장·법규·인허가/Top3를 모아 단일 종합판정(GO/CONDITIONAL/HOLD)을 낸다.

    기존 엔진(ComprehensiveAnalysisService·RegulationAnalysisService·FeasibilityServiceV2·
    디벨로퍼 페르소나 Go/No-Go)을 병렬 조립하는 오케스트레이션이다(신규 분석엔진 없음).
    프로젝트는 테넌트 격리(_get_project_or_404)로 조회하고, 주소/필지 미지정 시 프로젝트 SSOT를 쓴다.
    """
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)

    # 과금 게이트(MED) — use_llm=True면 다중 LLM 경로(부지/시장·법규·인허가 인터프리터)를
    # 트리거하므로 personas.py 패턴(enforce_llm_quota)을 재사용해 한도 초과 시 402 차단한다.
    # use_llm=False(기본)는 무LLM·무과금이라 게이트를 건너뛴다.
    if body.use_llm:
        from app.core.billing_deps import enforce_llm_quota
        await enforce_llm_quota(db)

    # 주소·필지 SSOT — 요청이 비면 프로젝트 저장값으로 채운다(일관·무목업).
    address = body.address or project.address
    parcels = body.parcels
    if not parcels:
        try:
            parcels = [p.address for p in (project.parcels or []) if getattr(p, "address", None)]
        except Exception:  # noqa: BLE001 — 필지 관계 로딩 실패는 단일주소로 진행
            parcels = None

    from app.services.land_intelligence.decision_brief_service import DecisionBriefService

    return await DecisionBriefService().build(
        address=address,
        project_id=str(project_id),
        parcels=parcels or None,
        tenant_id=str(current_user.tenant_id),
        equity_won=body.equity_won,
        use_llm=body.use_llm,
        force_refresh=body.force_refresh,
        db=db,
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    body: ProjectUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """프로젝트를 수정한다."""
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)

    before = {"name": project.name, "address": project.address}
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    # 감사 로그 after_state에는 분석 스냅샷 blob(대용량)을 싣지 않고 변경 여부만 기록.
    audit_after = {k: v for k, v in update_data.items() if k != "analysis_snapshot"}
    if "analysis_snapshot" in update_data:
        audit_after["analysis_snapshot_updated"] = True

    await record_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="project",
        entity_id=project.id,
        action="update",
        actor_id=current_user.user_id,
        before_state=before,
        after_state=audit_after,
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(project)
    return _to_response(project, include_snapshot=True)


@router.patch("/{project_id}/status", response_model=ProjectResponse)
async def update_project_status(
    project_id: UUID,
    body: ProjectStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """프로젝트 상태를 전환한다."""
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)

    current_status = project.status
    new_status = body.status.value

    allowed = _VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{current_status}'에서 '{new_status}'로의 상태 전환은 허용되지 않습니다",
        )

    project.status = new_status

    await record_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="project",
        entity_id=project.id,
        action="status_change",
        actor_id=current_user.user_id,
        before_state={"status": current_status},
        after_state={"status": new_status},
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(project)
    return _to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """프로젝트를 소프트 삭제한다(테넌트 스코프 — 본인 테넌트 프로젝트만)."""
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)

    project.is_deleted = True
    project.deleted_at = datetime.now(UTC)

    await record_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="project",
        entity_id=project.id,
        action="delete",
        actor_id=current_user.user_id,
        before_state={"name": project.name, "status": project.status},
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
