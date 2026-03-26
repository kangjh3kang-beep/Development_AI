"""Rate Limit 위반 기록 모델.

API 요청 제한 초과 이벤트를 기록하여 악용 감지 및 정책 조정에 활용한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin


class RateLimitViolation(Base, TenantMixin):
    __tablename__ = "rate_limit_violations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
        comment="위반 사용자 ID (인증된 경우)",
    )
    client_ip: Mapped[str] = mapped_column(
        String(45), nullable=False,
        comment="클라이언트 IP 주소 (IPv6 포함)",
    )
    endpoint: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="요청 엔드포인트 경로",
    )
    http_method: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="HTTP 메서드 (GET, POST 등)",
    )
    limit_name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="적용된 제한 규칙명 (예: tenant_api_global, user_avm)",
    )
    limit_max: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="설정된 최대 요청 수",
    )
    window_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="제한 윈도우 (초)",
    )
    current_count: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="현재 윈도우 내 누적 요청 수",
    )
    violated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="위반 발생 시각",
    )
