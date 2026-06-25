import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class AgentMemory(Base):
    """
    Stores metadata for RAG-based agent memories.
    The actual vector embeddings and chunked texts are stored in Qdrant.

    ★컬럼 타입은 부팅 schema_guard(agent_memories DDL)와 정합 유지: jsonb·timestamptz.
    """
    __tablename__ = "agent_memories"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    session_id = Column(String(100), nullable=True, index=True)
    domain = Column(String(50), nullable=False, index=True)  # e.g., 'permit', 'cost', 'zoning'
    source_type = Column(String(50), nullable=False) # e.g., 'expert_panel', 'agent_execution', 'user_feedback'
    summary = Column(Text, nullable=False)
    qdrant_point_ids = Column(JSONB, default=list) # List of point IDs in Qdrant
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
