"""공유시설 예약 라우터 (G115)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.facility_reservation_service import FacilityReservationService

router = APIRouter()


class CreateReservationRequest(BaseModel):
    project_id: UUID
    facility_name: str
    start_time: datetime
    end_time: datetime
    notes: str | None = None


class ReservationResponse(BaseModel):
    id: UUID
    facility_name: str
    status: str
    start_time: datetime
    end_time: datetime
    reserved_by: UUID


class CancelReservationRequest(BaseModel):
    reservation_id: UUID


@router.post("/reserve", response_model=ReservationResponse)
async def create_reservation(
    body: CreateReservationRequest,
    current_user: CurrentUser = Depends(RequirePermission("facility", "write")),
    db: AsyncSession = Depends(get_db),
) -> ReservationResponse:
    """[B08 패치] 공유시설 예약을 생성한다 (비관적 락 적용)."""
    service = FacilityReservationService(db)
    try:
        reservation = await service.create_reservation(
            tenant_id=current_user.tenant_id,
            project_id=body.project_id,
            facility_name=body.facility_name,
            reserved_by=current_user.user_id,
            start_time=body.start_time,
            end_time=body.end_time,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e

    return ReservationResponse(
        id=reservation.id,
        facility_name=reservation.facility_name,
        status=reservation.status,
        start_time=reservation.start_time,
        end_time=reservation.end_time,
        reserved_by=reservation.reserved_by,
    )


@router.post("/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    body: CancelReservationRequest,
    current_user: CurrentUser = Depends(RequirePermission("facility", "write")),
    db: AsyncSession = Depends(get_db),
) -> ReservationResponse:
    """예약을 취소한다."""
    service = FacilityReservationService(db)
    try:
        reservation = await service.cancel_reservation(
            tenant_id=current_user.tenant_id,
            reservation_id=body.reservation_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    return ReservationResponse(
        id=reservation.id,
        facility_name=reservation.facility_name,
        status=reservation.status,
        start_time=reservation.start_time,
        end_time=reservation.end_time,
        reserved_by=reservation.reserved_by,
    )
