"""LiveKit 화상회의 API 스키마 — 토큰·녹화."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LiveKitTokenOut(BaseModel):
    """룸 입장 토큰 — 프론트 LiveKitRoom이 url+token으로 connect. can_publish/can_record는 역할 권한."""

    url: str
    token: str
    room: str
    can_publish: bool
    can_record: bool


class RecordingOut(BaseModel):
    id: str
    project_id: str
    room: str
    status: str  # recording/completed/failed
    egress_id: str | None = None
    s3_key: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
