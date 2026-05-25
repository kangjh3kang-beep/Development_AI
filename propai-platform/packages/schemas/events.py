"""PropAI SSE 이벤트 스키마.

Codex의 StreamingReport, AgentTimeline 컴포넌트와 정합을 위해
필드를 사전 확정한다. (부록 B 기준)
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class AgentStepEvent(BaseModel):
    """에이전트 오케스트레이션 단계 이벤트 (7단계)"""
    event_type: str = Field(default="agent_step", description="이벤트 타입")
    step_index: int = Field(ge=0, le=6, description="단계 인덱스 (0~6)")
    step_name: str = Field(
        description="단계명: parcel_analysis | regulation | design | avm | feasibility | permit | report",
    )
    status: str = Field(description="상태: pending | running | completed | error")
    progress_pct: float = Field(ge=0.0, le=1.0, description="진행률 (0.0~1.0)")
    data: dict | None = Field(default=None, description="단계별 결과 요약 (JSON)")
    error_message: str | None = Field(default=None, description="오류 메시지")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="발생 시각 (ISO 8601)")


class StreamingReportEvent(BaseModel):
    """보고서 스트리밍 청크 이벤트"""
    event_type: str = Field(default="report_chunk", description="이벤트 타입")
    chunk_index: int = Field(ge=0, description="청크 순서 번호")
    content: str = Field(description="마크다운 텍스트 청크")
    is_final: bool = Field(default=False, description="마지막 청크 여부")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="발생 시각")


class DroneAlertEvent(BaseModel):
    """드론 하자 탐지 알림 이벤트"""
    event_type: str = Field(default="drone_alert", description="이벤트 타입")
    inspection_id: str = Field(description="점검 ID")
    severity: str = Field(description="심각도: EMERGENCY | HIGH | MEDIUM | LOW")
    defect_type: str = Field(description="하자 유형")
    location: dict = Field(description="좌표 {x, y, z}")
    image_url: str | None = Field(default=None, description="하자 이미지 URL")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="발생 시각")
