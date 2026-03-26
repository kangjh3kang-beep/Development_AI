"""법규 검토 모델.

법규 RAG 검토 결과를 저장한다.
위반 사항과 권고 사항을 JSON으로 기록한다.
"""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class Regulation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "regulations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    regulation_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="zoning | building_code | fire_safety | environment | parking | urban_planning"
    )
    is_compliant: Mapped[bool] = mapped_column(default=True, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    violations: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="위반 사항 목록"
    )
    recommendations: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="권고 사항 목록"
    )
    source_documents: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="참조 법령 문서 ID 목록"
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
