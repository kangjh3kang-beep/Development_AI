"""공간/시설 예약 서비스.

동시 접속 시 초과 예약 차단을 위한 Serializable 트랜잭션 + 충돌 검사.
시설 예약 CRUD, 가용성 조회, 충돌 감지.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa
import structlog
from sqlalchemy import select

from apps.api.config import get_settings
from apps.api.database.models.facility_reservation import FacilityReservation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# 예약 가능 최대 기간 (일)
_MAX_RESERVATION_DAYS = 30
# 최소 예약 단위 (분)
_MIN_RESERVATION_MINUTES = 30


class ReservationService:
    """공간/시설 예약 관리 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def acquire_lock(self) -> None:
        """Serializable 트랜잭션 격리 수준을 설정한다 (초과 예약 방지)."""
        await self.db.execute(
            sa.text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        )

    async def detect_conflict(
        self,
        project_id: UUID,
        facility_name: str,
        start_time: datetime,
        end_time: datetime,
        exclude_id: UUID | None = None,
    ) -> list[FacilityReservation]:
        """시간대 충돌하는 기존 예약을 조회한다."""
        stmt = select(FacilityReservation).where(
            FacilityReservation.project_id == project_id,
            FacilityReservation.facility_name == facility_name,
            FacilityReservation.status != "cancelled",
            FacilityReservation.start_time < end_time,
            FacilityReservation.end_time > start_time,
        )
        if exclude_id is not None:
            stmt = stmt.where(FacilityReservation.id != exclude_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def check_availability(
        self,
        project_id: UUID,
        facility_name: str,
        start_time: datetime,
        end_time: datetime,
    ) -> dict:
        """시간대 가용성을 확인한다."""
        conflicts = await self.detect_conflict(project_id, facility_name, start_time, end_time)
        return {
            "available": len(conflicts) == 0,
            "conflicts": len(conflicts),
            "project_id": str(project_id),
            "facility_name": facility_name,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }

    @staticmethod
    def validate_reservation_period(start_time: datetime, end_time: datetime) -> None:
        """예약 기간의 유효성을 검증한다."""
        if end_time <= start_time:
            raise ValueError("종료 시간은 시작 시간보다 이후여야 합니다")

        duration_minutes = (end_time - start_time).total_seconds() / 60
        if duration_minutes < _MIN_RESERVATION_MINUTES:
            raise ValueError(f"최소 예약 단위는 {_MIN_RESERVATION_MINUTES}분입니다")

        duration_days = (end_time - start_time).days
        if duration_days > _MAX_RESERVATION_DAYS:
            raise ValueError(f"최대 예약 기간은 {_MAX_RESERVATION_DAYS}일입니다")

    async def create_reservation(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        facility_name: str,
        reserved_by: UUID,
        start_time: datetime,
        end_time: datetime,
        notes: str | None = None,
    ) -> FacilityReservation:
        """예약을 생성한다 (Serializable 락 + 충돌 검사 포함)."""
        self.validate_reservation_period(start_time, end_time)

        # Serializable 격리로 동시 예약 방지
        await self.acquire_lock()

        conflicts = await self.detect_conflict(project_id, facility_name, start_time, end_time)
        if conflicts:
            raise ValueError(f"해당 시간대에 {len(conflicts)}건의 기존 예약이 있습니다")

        reservation = FacilityReservation(
            tenant_id=tenant_id,
            project_id=project_id,
            facility_name=facility_name,
            reserved_by=reserved_by,
            start_time=start_time,
            end_time=end_time,
            notes=notes,
            status="confirmed",
        )
        self.db.add(reservation)
        await self.db.commit()
        await self.db.refresh(reservation)
        logger.info("예약 생성 완료", reservation_id=str(reservation.id))
        return reservation

    async def cancel_reservation(
        self,
        reservation_id: UUID,
        tenant_id: UUID,
    ) -> FacilityReservation | None:
        """예약을 취소한다."""
        result = await self.db.execute(
            select(FacilityReservation).where(
                FacilityReservation.id == reservation_id,
                FacilityReservation.tenant_id == tenant_id,
            )
        )
        reservation = result.scalar_one_or_none()
        if reservation is None:
            return None

        reservation.status = "cancelled"
        await self.db.commit()
        await self.db.refresh(reservation)
        logger.info("예약 취소", reservation_id=str(reservation_id))
        return reservation

    async def list_reservations(
        self,
        project_id: UUID,
        facility_name: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[FacilityReservation]:
        """시설의 예약 목록을 조회한다."""
        stmt = select(FacilityReservation).where(
            FacilityReservation.project_id == project_id,
            FacilityReservation.facility_name == facility_name,
            FacilityReservation.status != "cancelled",
        )
        if start_date:
            stmt = stmt.where(FacilityReservation.end_time >= start_date)
        if end_date:
            stmt = stmt.where(FacilityReservation.start_time <= end_date)
        stmt = stmt.order_by(FacilityReservation.start_time)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def calculate_utilization_rate(
        reservations: list[FacilityReservation],
        total_hours: float,
    ) -> float:
        """시설 이용률을 계산한다 (%)."""
        if total_hours <= 0:
            return 0.0
        reserved_hours = sum(
            (r.end_time - r.start_time).total_seconds() / 3600
            for r in reservations
            if r.status != "cancelled" and r.start_time and r.end_time
        )
        return round(min(reserved_hours / total_hours * 100, 100.0), 2)
