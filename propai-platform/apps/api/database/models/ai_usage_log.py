"""AI 사용 로그 모델.

AI 서비스 호출 기록. 비용 추적 및 성능 모니터링용.
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class AIUsageLog(Base, TenantMixin, TimestampMixin):
    __tablename__ = "ai_usage_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    service_name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="호출된 AI 서비스명 (예: avm, regulation_rag, design_ai)"
    )
    model_name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="사용된 모델명 (예: claude-3-opus, gpt-4, xgboost-avm-v2)"
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="응답 시간 (ms)"
    )
    cost_usd: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="비용 (USD)"
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    request_summary: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="요청 요약"
    )
    response_summary: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="응답 요약"
    )
    is_cached: Mapped[bool] = mapped_column(default=False, nullable=False)
