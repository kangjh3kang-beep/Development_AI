"""R2 — HITL 태스크 계약. 우선순위(사용빈도+임박가중) + SLA. 승인 시 후보 ACTIVE(INV-14).

SoD(직무분리, v4.0 Wave1 W1-B): author(작성자)가 기록돼 있고 author == approver(승인/거부자)면
HITLQueue.approve()가 SelfApprovalError로 거부한다(동일인 작성·승인 기술적 차단).
author 미기록(레거시 데이터)은 차단 불가하나 무언 통과 금지 — sod_check에 명시 표식을 남긴다.
history는 승인/거부 이벤트의 감사 가능한 이력(태스크 레코드 내, 새 인프라 신설 없이).
"""
from __future__ import annotations

from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, Field


class Priority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class HITLTask(BaseModel):
    task_id: str
    candidate_id: str
    usage_freq: float = 0.0
    imminent: bool = False
    sla_due_day: int = 0
    priority: Priority = Priority.LOW
    status: str = "PENDING"
    author: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_by: str | None = None
    rejected_at: datetime | None = None
    sod_check: str | None = None
    history: list[dict] = Field(default_factory=list)
