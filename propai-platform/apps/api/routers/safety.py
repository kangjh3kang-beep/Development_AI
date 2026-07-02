"""공사현장 AI 안전관리 라우터 (G116)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.models.safety_violation import SafetyViolation
from apps.api.database.session import get_db
from apps.api.services.safety_service import SafetyService

router = APIRouter()


class StreamAnalysisRequest(BaseModel):
    project_id: UUID
    camera_id: str
    rtsp_url: str
    max_frames: int = 300


class ViolationResponse(BaseModel):
    id: UUID
    violation_type: str
    confidence: float
    bbox: dict | None = None
    camera_id: str


class StreamAnalysisResponse(BaseModel):
    violations_count: int
    violations: list[ViolationResponse]


class SafetyDashboardViolationResponse(BaseModel):
    id: UUID
    camera_id: str
    violation_type: str
    confidence: float
    detected_at: datetime
    frame_url: str | None
    zone: str


class SafetyDashboardStatsResponse(BaseModel):
    total_violations_today: int
    helmet_off_count: int
    vest_off_count: int
    active_cameras: int


class SafetyDashboardResponse(BaseModel):
    stream_url: str
    violations: list[SafetyDashboardViolationResponse]
    stats: SafetyDashboardStatsResponse


def _resolve_zone(camera_id: str) -> str:
    suffix = camera_id.split("-")[-1].upper()
    return f"{suffix} Zone"


@router.get("/dashboard", response_model=SafetyDashboardResponse)
async def get_safety_dashboard(
    current_user: CurrentUser = Depends(RequirePermission("safety", "read")),
    db: AsyncSession = Depends(get_db),
) -> SafetyDashboardResponse:
    """Return the latest safety monitoring dashboard snapshot."""
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    recent_result = await db.execute(
        select(SafetyViolation)
        .where(SafetyViolation.tenant_id == current_user.tenant_id)
        .order_by(SafetyViolation.detected_at.desc())
        .limit(8)
    )
    recent = list(recent_result.scalars().all())

    total_today = await db.scalar(
        select(func.count())
        .select_from(SafetyViolation)
        .where(
            SafetyViolation.tenant_id == current_user.tenant_id,
            SafetyViolation.detected_at >= today_start,
        )
    )
    helmet_count = await db.scalar(
        select(func.count())
        .select_from(SafetyViolation)
        .where(
            SafetyViolation.tenant_id == current_user.tenant_id,
            SafetyViolation.detected_at >= today_start,
            SafetyViolation.violation_type == "helmet_off",
        )
    )
    vest_count = await db.scalar(
        select(func.count())
        .select_from(SafetyViolation)
        .where(
            SafetyViolation.tenant_id == current_user.tenant_id,
            SafetyViolation.detected_at >= today_start,
            SafetyViolation.violation_type == "vest_off",
        )
    )
    active_cameras = await db.scalar(
        select(func.count(func.distinct(SafetyViolation.camera_id)))
        .where(
            SafetyViolation.tenant_id == current_user.tenant_id,
            SafetyViolation.detected_at >= today_start,
        )
    )

    return SafetyDashboardResponse(
        stream_url="/api/v1/safety/analyze-stream",
        violations=[
            SafetyDashboardViolationResponse(
                id=violation.id,
                camera_id=violation.camera_id,
                violation_type=violation.violation_type,
                confidence=violation.confidence,
                detected_at=violation.detected_at,
                frame_url=violation.frame_url,
                zone=violation.description or _resolve_zone(violation.camera_id),
            )
            for violation in recent
        ],
        stats=SafetyDashboardStatsResponse(
            total_violations_today=int(total_today or 0),
            helmet_off_count=int(helmet_count or 0),
            vest_off_count=int(vest_count or 0),
            active_cameras=int(active_cameras or 0),
        ),
    )


@router.post("/analyze-stream", response_model=StreamAnalysisResponse)
async def analyze_safety_stream(
    body: StreamAnalysisRequest,
    current_user: CurrentUser = Depends(RequirePermission("safety", "write")),
    db: AsyncSession = Depends(get_db),
) -> StreamAnalysisResponse:
    """RTSP 스트림에서 안전 위반을 감지한다."""
    service = SafetyService(db)
    violations = await service.analyze_stream(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        camera_id=body.camera_id,
        rtsp_url=body.rtsp_url,
        max_frames=body.max_frames,
    )
    return StreamAnalysisResponse(
        violations_count=len(violations),
        violations=[
            ViolationResponse(
                id=v.id,
                violation_type=v.violation_type,
                confidence=v.confidence,
                bbox=v.bbox_json,
                camera_id=v.camera_id,
            )
            for v in violations
        ],
    )


@router.post("/analyze-frame", response_model=StreamAnalysisResponse)
async def analyze_safety_frame(
    project_id: UUID,
    camera_id: str,
    file: UploadFile,
    current_user: CurrentUser = Depends(RequirePermission("safety", "write")),
    db: AsyncSession = Depends(get_db),
) -> StreamAnalysisResponse:
    """단일 이미지 프레임에서 안전 위반을 감지한다."""
    image_bytes = await file.read()
    service = SafetyService(db)
    violations = await service.analyze_single_frame(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
        camera_id=camera_id,
        image_bytes=image_bytes,
    )
    return StreamAnalysisResponse(
        violations_count=len(violations),
        violations=[
            ViolationResponse(
                id=v.id,
                violation_type=v.violation_type,
                confidence=v.confidence,
                bbox=v.bbox_json,
                camera_id=v.camera_id,
            )
            for v in violations
        ],
    )
