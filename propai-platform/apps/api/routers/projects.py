"""프로젝트 라우터.

CRUD + 상태 전환 + 소프트 삭제.
"""

from datetime import datetime, timezone
UTC = timezone.utc
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.models.project import Project
from apps.api.database.session import get_db
from apps.api.metrics import PROJECT_CREATED
from apps.api.services.audit_service import record_audit

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


def _to_response(project: Project) -> ProjectResponse:
    """Project ORM 인스턴스를 ProjectResponse로 변환한다."""
    return ProjectResponse(
        id=project.id,
        tenant_id=project.tenant_id,
        name=project.name,
        status=ProjectStatus(project.status),
        address=project.address,
        latitude=project.latitude,
        longitude=project.longitude,
        total_area_sqm=project.total_area_sqm,
        created_at=project.created_at,
        updated_at=project.updated_at,
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
    current_user: CurrentUser = Depends(RequirePermission("projects", "read")),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """프로젝트 목록을 조회한다."""
    offset = (page - 1) * page_size
    query = (
        select(Project)
        .where(Project.tenant_id == current_user.tenant_id, Project.is_deleted == False)  # noqa: E712
        .offset(offset)
        .limit(page_size + 1)
        .order_by(Project.created_at.desc())
    )
    result = await db.execute(query)
    projects = list(result.scalars().all())

    has_next = len(projects) > page_size
    if has_next:
        projects = projects[:page_size]

    items = [_to_response(p).model_dump() for p in projects]
    return PaginatedResponse(items=items, page=page, page_size=page_size, has_next=has_next)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreateRequest,
    request: Request,
    current_user: CurrentUser = Depends(RequirePermission("projects", "write")),
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
    current_user: CurrentUser = Depends(RequirePermission("projects", "read")),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """프로젝트 상세 정보를 조회한다."""
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)
    return _to_response(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    body: ProjectUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(RequirePermission("projects", "write")),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """프로젝트를 수정한다."""
    project = await _get_project_or_404(project_id, current_user.tenant_id, db)

    before = {"name": project.name, "address": project.address}
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await record_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="project",
        entity_id=project.id,
        action="update",
        actor_id=current_user.user_id,
        before_state=before,
        after_state=update_data,
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(project)
    return _to_response(project)


@router.patch("/{project_id}/status", response_model=ProjectResponse)
async def update_project_status(
    project_id: UUID,
    body: ProjectStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(RequirePermission("projects", "write")),
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
    current_user: CurrentUser = Depends(RequirePermission("projects", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """프로젝트를 소프트 삭제한다."""
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
