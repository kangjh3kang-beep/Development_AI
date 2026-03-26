"""v44.0 건축 법규 DB (G96) -- 용도지역별 법규 한도 테이블."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class BuildingRegulation(Base, TenantMixin, TimestampMixin):
    """용도지역별 건축 법규 한도 (건폐율, 용적률, 높이, 이격거리 등)."""

    __tablename__ = "building_regulations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    zone_code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="용도지역 코드 (1R, 2R, 3R, 준주거 등)"
    )
    zone_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="용도지역 명칭"
    )
    building_coverage_ratio: Mapped[float] = mapped_column(
        Float, nullable=False, comment="건폐율 상한 (0~1)"
    )
    floor_area_ratio: Mapped[float] = mapped_column(
        Float, nullable=False, comment="용적률 상한 (0~N)"
    )
    max_height_m: Mapped[float] = mapped_column(
        Float, nullable=False, comment="최고 높이 제한 (m)"
    )
    min_setback_m: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, comment="최소 이격거리 (m)"
    )
    sunlight_hours_min: Mapped[float] = mapped_column(
        Float, nullable=False, default=2.0, comment="일조권 최소 시간 (h)"
    )
    effective_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="시행 일자"
    )
