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


class DocumentOut(BaseModel):
    """회의방 자료교환 문서 뷰 — 실바이트는 미포함(file_url=비공개버킷 서명URL, TTL 후 만료)."""

    id: str
    project_id: str
    uploaded_by: Optional[str] = None
    original_filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    category: Optional[str] = None  # REVIEW_CATEGORIES 화이트리스트 or null
    doc_kind: str                   # design(DXF/IFC, 8엔진 대상) / document(표기용)
    audit_status: Optional[str] = None   # null/pending/completed/skipped/unsupported
    audit_summary: Optional[dict] = None
    review_state: str               # requested/acknowledged/addressed(표기용·자동판정 아님)
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    file_url: Optional[str] = None
    created_at: Optional[datetime] = None


class DocumentActionResult(BaseModel):
    ok: bool
    status: str
    detail: Optional[str] = None


class DocumentReviewUpdate(BaseModel):
    """표기용 심의 상태 전이 요청 — 전진(requested→acknowledged→addressed)만 허용(자동판정 아님)."""

    target_state: str = Field(..., min_length=1, max_length=20)
