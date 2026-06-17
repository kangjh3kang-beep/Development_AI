"""R2 — HITL 태스크 계약. 우선순위(사용빈도+임박가중) + SLA. 승인 시 후보 ACTIVE(INV-14)."""
from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel


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
