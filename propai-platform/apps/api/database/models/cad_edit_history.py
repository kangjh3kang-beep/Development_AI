"""v44.0 CAD 편집 이력 (G97) -- 점/선/면 조작 로그."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class CADEditHistory(Base, TenantMixin, TimestampMixin):
    """CAD 편집 이력: 점/선/면 조작을 시계열로 기록."""

    __tablename__ = "cad_edit_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="프로젝트 FK"
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="편집 수행 사용자"
    )
    edit_type: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="point_move | line_add | surface_create | ..."
    )
    element_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="조작 대상 요소 ID"
    )
    before_state: Mapped[dict] = mapped_column(
        JSONB, nullable=True, comment="변경 전 상태 JSON"
    )
    after_state: Mapped[dict] = mapped_column(
        JSONB, nullable=True, comment="변경 후 상태 JSON"
    )
    design_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=True, comment="편집 시점 전체 설계 스냅샷"
    )
    revision_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="리비전 번호"
    )
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
