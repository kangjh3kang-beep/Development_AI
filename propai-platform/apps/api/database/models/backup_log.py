"""백업 로그 모델.

데이터베이스/파일 백업 작업의 실행 이력을 기록한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base


class BackupLog(Base):
    __tablename__ = "backup_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    backup_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="백업 유형 (full, incremental, wal)",
    )
    target: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="백업 대상 (database, minio, timescaledb 등)",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="상태 (running, success, failed)",
    )
    storage_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="백업 저장 경로 (S3/MinIO URL 등)",
    )
    size_bytes: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
        comment="백업 파일 크기 (바이트)",
    )
    duration_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="백업 소요 시간 (초)",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="실패 시 에러 메시지",
    )
    retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30,
        comment="보관 기간 (일)",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="백업 시작 시각",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="백업 완료 시각",
    )
