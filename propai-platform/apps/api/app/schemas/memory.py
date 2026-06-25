from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    project_id: UUID | None = None
    session_id: str | None = None
    domain: str = Field(..., description="The domain of the memory, e.g., 'permit', 'cost', 'zoning'")
    source_type: str = Field(..., description="Where this memory came from, e.g., 'expert_panel'")
    summary: str = Field(..., description="The summary text of what happened and the decisions made.")
    metadata: dict[str, Any] = Field(default_factory=dict)

class MemoryRecallResponse(BaseModel):
    id: UUID
    domain: str
    source_type: str
    summary: str
    score: float = Field(..., description="Cosine similarity score from Qdrant")
    # ★Optional — Qdrant payload 에 created_at 이 없을 수 있다(과거 저장분). 필수로 두면 회상
    #   포맷팅에서 ValidationError 로 회상이 통째로 실패한다(인프라 가동 시점에 정확히 터지는 잠복결함).
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
