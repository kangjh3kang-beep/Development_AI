"""R2 — HITL 태스크 계약. 우선순위(사용빈도+임박가중) + SLA. 승인 시 후보 ACTIVE(INV-14).

SoD(직무분리, v4.0 Wave1 W1-B): author(작성자)가 기록돼 있고 author == approver(승인/거부자,
양측 공백 strip 후 비교 — approver/author는 정규화된 principal ID라는 계약을 전제)면
HITLQueue.approve()가 SelfApprovalError로 거부한다(동일인 작성·승인 기술적 차단).
정직 표기: author를 채우는 생성 경로(추출 파이프라인·라우터)가 저장소에 아직 없어, 현재
신규 태스크는 기본적으로 author=None이며 이 경우 SoD는 사실상 전면 skip 상태다(레거시 데이터
문제가 아니라 배선 미완료). add()가 author를 전달받으면 그 태스크부터 SoD가 실질 적용된다.
skip 상태는 무언 통과가 아니라 sod_check="skipped(author 미기록)" 표식으로 명시한다.
history는 승인/거부 이벤트의 감사 가능한 이력(태스크 레코드 내, 새 인프라 신설 없이·append 전용).
"""
from __future__ import annotations

from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, Field


class Priority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class HITLHistoryEvent(BaseModel):
    """HITL 승인/거부 이벤트 1건. append 전용(과거 원소 변경 금지 — 관례, HITLQueue._append_history만 사용)."""

    action: str
    actor: str
    at: datetime
    sod_check: str


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
    history: list[HITLHistoryEvent] = Field(default_factory=list)
