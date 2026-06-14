"""SP2 협업/회의방(F3) API 스키마 — 멤버·초대 요청/응답.

서버 응답은 scope_categories 화이트리스트로 필터된 뷰만 직렬화(클라이언트 숨김에 의존 금지).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemberOut(BaseModel):
    id: str
    project_id: str
    user_id: Optional[str] = None
    project_role: str
    status: str
    created_at: Optional[datetime] = None


class InviteCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    project_role: str = "external_reviewer"
    scope_categories: list[str] = Field(default_factory=list)
    ttl_days: int = Field(14, ge=1, le=90)


class InviteOut(BaseModel):
    id: Optional[str] = None
    project_id: str
    email: str
    project_role: str
    scope_categories: list[str]
    status: str
    expires_at: datetime
    invite_token: Optional[str] = None  # 생성 직후 1회 노출(공유용). 목록 조회 시 None.


class InviteActionResult(BaseModel):
    ok: bool
    status: str
    detail: Optional[str] = None
