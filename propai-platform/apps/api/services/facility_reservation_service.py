"""공유시설 AI 예약 서비스 (G115).

[B08 버그 패치] 동시 예약 Race Condition 방지를 위해
DB 쿼리 시 with_for_update(nowait=True) 비관적 락 적용.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.exc import OperationalError

from apps.api.database.models.facility_reservation import FacilityReservation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class FacilityReservationService:
    """공유시설 예약 서비스.

    [B08 패치] SELECT ... FOR UPDATE NOWAIT 으로
    동시 예약 시 Race Condition을 방어한다.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
        """예약을 생성한다.

        [B08 패치] 시간 겹침 검사 시 with_for_update(nowait=True) 를 사용하여
        동일 시설에 대한 동시 예약 요청을 직렬화한다.
        다른 트랜잭션이 이미 해당 행을 잠근 경우 즉시 에러를 반환하여
        데드락을 방지한다.
        """
        if start_time >= end_time:
            raise ValueError("시작 시간은 종료 시간보다 이전이어야 합니다")

        # [B08 핵심] 비관적 락으로 시간 겹침 검사
        # with_for_update(nowait=True): 행이 잠겨있으면 대기하지 않고 즉시 에러
        try:
            overlap_query = (
                select(FacilityReservation)
                .where(
                    and_(
                        FacilityReservation.tenant_id == tenant_id,
                        FacilityReservation.project_id == project_id,
                        FacilityReservation.facility_name == facility_name,
                        FacilityReservation.status == "confirmed",
                        FacilityReservation.start_time < end_time,
                        FacilityReservation.end_time > start_time,
                    )
                )
                .with_for_update(nowait=True)
            )

            result = await self.db.execute(overlap_query)
            overlapping = result.scalars().all()

        except OperationalError as e:
            # nowait=True: 다른 트랜잭션이 이미 락을 보유 중
            logger.warning(
                "예약 락 획득 실패 — 다른 사용자가 동시 예약 중",
                facility=facility_name,
                error=str(e),
            )
            raise ValueError(
                "현재 다른 사용자가 같은 시설을 예약 중입니다. 잠시 후 다시 시도해 주세요."
            ) from e

        if overlapping:
            existing = overlapping[0]
            raise ValueError(
                f"해당 시간대에 이미 예약이 존재합니다: "
                f"{existing.start_time.isoformat()} ~ {existing.end_time.isoformat()}"
            )

        reservation = FacilityReservation(
            tenant_id=tenant_id,
            project_id=project_id,
            facility_name=facility_name,
            reserved_by=reserved_by,
            status="confirmed",
            start_time=start_time,
            end_time=end_time,
            notes=notes,
        )
        self.db.add(reservation)
        await self.db.commit()
        await self.db.refresh(reservation)

        logger.info(
            "예약 생성 완료",
            reservation_id=str(reservation.id),
            facility=facility_name,
        )
        return reservation

    async def cancel_reservation(
        self,
        *,
        tenant_id: UUID,
        reservation_id: UUID,
    ) -> FacilityReservation:
        """예약을 취소한다."""
        result = await self.db.execute(
            select(FacilityReservation).where(
                FacilityReservation.id == reservation_id,
                FacilityReservation.tenant_id == tenant_id,
            )
        )
        reservation: FacilityReservation | None = result.scalar_one_or_none()
        if reservation is None:
            raise ValueError("예약을 찾을 수 없습니다")

        reservation.status = "cancelled"
        await self.db.commit()
        await self.db.refresh(reservation)
        return reservation
