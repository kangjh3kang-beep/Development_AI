"""AI 스마트 주차 관리 라우터 (G119)."""

from datetime import UTC, datetime

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.models.parking_record import ParkingRecord
from apps.api.database.session import get_db
from apps.api.services.parking_service import ParkingService

router = APIRouter()


class PlateRecognitionResponse(BaseModel):
    plate_number: str
    raw_ocr_text: str | None
    zone: str | None
    event_type: str
    record_id: UUID


class ParkingRecordResponse(BaseModel):
    id: UUID
    plate_number: str
    event_type: str
    camera_id: str
    zone: str | None
    recorded_at: datetime


class ParkingDashboardStatsResponse(BaseModel):
    total_today: int
    currently_parked: int
    capacity: int
    occupancy_rate: float


class ParkingDashboardResponse(BaseModel):
    records: list[ParkingRecordResponse]
    stats: ParkingDashboardStatsResponse


@router.get("/dashboard", response_model=ParkingDashboardResponse)
async def get_parking_dashboard(
    current_user: CurrentUser = Depends(RequirePermission("parking", "read")),
    db: AsyncSession = Depends(get_db),
) -> ParkingDashboardResponse:
    """Return the latest parking operations dashboard snapshot."""
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    recent_result = await db.execute(
        select(ParkingRecord)
        .where(ParkingRecord.tenant_id == current_user.tenant_id)
        .order_by(ParkingRecord.recorded_at.desc())
        .limit(12)
    )
    recent = list(recent_result.scalars().all())

    total_today = await db.scalar(
        select(func.count())
        .select_from(ParkingRecord)
        .where(
            ParkingRecord.tenant_id == current_user.tenant_id,
            ParkingRecord.recorded_at >= today_start,
        )
    )
    entry_count = await db.scalar(
        select(func.count())
        .select_from(ParkingRecord)
        .where(
            ParkingRecord.tenant_id == current_user.tenant_id,
            ParkingRecord.recorded_at >= today_start,
            ParkingRecord.event_type == "entry",
        )
    )
    exit_count = await db.scalar(
        select(func.count())
        .select_from(ParkingRecord)
        .where(
            ParkingRecord.tenant_id == current_user.tenant_id,
            ParkingRecord.recorded_at >= today_start,
            ParkingRecord.event_type == "exit",
        )
    )
    currently_parked = max(int(entry_count or 0) - int(exit_count or 0), 0)
    capacity = 120

    return ParkingDashboardResponse(
        records=[
            ParkingRecordResponse(
                id=record.id,
                plate_number=record.plate_number,
                event_type=record.event_type,
                camera_id=record.camera_id,
                zone=record.zone,
                recorded_at=record.recorded_at,
            )
            for record in recent
        ],
        stats=ParkingDashboardStatsResponse(
            total_today=int(total_today or 0),
            currently_parked=currently_parked,
            capacity=capacity,
            occupancy_rate=(currently_parked / capacity) if capacity else 0.0,
        ),
    )


@router.post("/recognize", response_model=PlateRecognitionResponse)
async def recognize_plate(
    project_id: UUID,
    camera_id: str,
    file: UploadFile,
    zone: str | None = None,
    event_type: str = "entry",
    current_user: CurrentUser = Depends(RequirePermission("parking", "write")),
    db: AsyncSession = Depends(get_db),
) -> PlateRecognitionResponse:
    """번호판 이미지를 OCR로 인식하고 정규식 검증 후 기록한다."""
    image_bytes = await file.read()
    service = ParkingService(db)
    record = await service.recognize_plate(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
        camera_id=camera_id,
        image_bytes=image_bytes,
        zone=zone,
        event_type=event_type,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="번호판 인식 실패 또는 정규식 검증 불통과",
        )
    return PlateRecognitionResponse(
        plate_number=record.plate_number,
        raw_ocr_text=record.raw_ocr_text,
        zone=record.zone,
        event_type=record.event_type,
        record_id=record.id,
    )
