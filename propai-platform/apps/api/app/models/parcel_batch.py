"""F-Parcel 배치 SQLAlchemy 모델(3종).

무PostGIS 원칙: union_boundary 등 geometry 는 geoalchemy2 Geometry 대신
JSON(GeoJSON) 컬럼으로 저장한다(PostGIS 의존 회피).
org/project FK 는 nullable String 으로 둔다(느슨한 결합).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
)
from sqlalchemy.dialects.postgresql import UUID

from apps.api.database.models.base import Base


class ParcelBatchJobRow(Base):
    """배치 잡 헤더 테이블."""

    __tablename__ = "parcel_batch_job"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    snapshot_id = Column(String(64), nullable=False)
    idempotency_key = Column(String(64), nullable=True, index=True, unique=True)
    state = Column(String(20), nullable=False, default="queued")
    region_input = Column(JSON, default=dict)
    completeness = Column(String(20), nullable=False, default="partial")
    counts = Column(JSON, default=dict)
    org_id = Column(String(64), nullable=True)
    project_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BatchItemResultRow(Base):
    """배치 필지 결과 테이블."""

    __tablename__ = "batch_item_result"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(
        UUID(as_uuid=False), ForeignKey("parcel_batch_job.id"), nullable=False, index=True
    )
    pnu = Column(String(32), nullable=False)
    status = Column(String(20), nullable=False)
    record_ref = Column(JSON, nullable=True)
    reason = Column(String(500), nullable=True)


class BatchAggregateRow(Base):
    """배치 집계 테이블(geometry 는 GeoJSON JSON 컬럼)."""

    __tablename__ = "batch_aggregate"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(
        UUID(as_uuid=False), ForeignKey("parcel_batch_job.id"), nullable=False, index=True
    )
    union_boundary = Column(JSON, nullable=True)        # GeoJSON
    total_area_sqm = Column(Float, nullable=True)
    jurisdiction_flags = Column(JSON, nullable=True)
    held = Column(Boolean, default=True)
