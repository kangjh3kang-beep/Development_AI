"""SP2 협업/회의방(F3) API 스키마 — 멤버·초대 요청/응답.

서버 응답은 scope_categories 화이트리스트로 필터된 뷰만 직렬화(클라이언트 숨김에 의존 금지).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MemberOut(BaseModel):
    id: str
    project_id: str
    user_id: str | None = None
    project_role: str
    status: str
    created_at: datetime | None = None


class InviteCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    project_role: str = "external_reviewer"
    scope_categories: list[str] = Field(default_factory=list)
    ttl_days: int = Field(14, ge=1, le=90)


class InviteOut(BaseModel):
    id: str | None = None
    project_id: str
    email: str
    project_role: str
    scope_categories: list[str]
    status: str
    expires_at: datetime
    invite_token: str | None = None  # 생성 직후 1회 노출(공유용). 목록 조회 시 None.


class InviteActionResult(BaseModel):
    ok: bool
    status: str
    detail: str | None = None


class DocumentOut(BaseModel):
    """회의방 자료교환 문서 뷰 — 실바이트는 미포함(file_url=비공개버킷 서명URL, TTL 후 만료)."""

    id: str
    project_id: str
    uploaded_by: str | None = None
    original_filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    category: str | None = None  # REVIEW_CATEGORIES 화이트리스트 or null
    purpose: str = "storage"        # analysis(8엔진) / storage(공유·저장)
    doc_kind: str                   # design(DXF/IFC, 8엔진 대상) / document(표기용)
    audit_status: str | None = None   # null/pending/completed/skipped/unsupported
    audit_summary: dict | None = None
    review_state: str               # requested/acknowledged/addressed(표기용·자동판정 아님)
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    file_url: str | None = None
    created_at: datetime | None = None


class DocumentActionResult(BaseModel):
    ok: bool
    status: str
    detail: str | None = None


class DocumentReviewUpdate(BaseModel):
    """표기용 심의 상태 전이 요청 — 전진(requested→acknowledged→addressed)만 허용(자동판정 아님)."""

    target_state: str = Field(..., min_length=1, max_length=20)


class DocumentShapesOut(BaseModel):
    """저장된 DXF 설계파일의 CAD2.0 셰이프(읽기전용 뷰어용) — 실파싱 결과만(가짜 기하 금지)."""

    shapes: list[dict] = Field(default_factory=list)
    bounds_px: dict | None = None
    scale_px_per_m: float | None = None


class ReviewCommentCreate(BaseModel):
    """의견교환 생성 — 루트(parent_id=None) 또는 답변(parent_id). anchor는 루트 전용(서버 강제)."""

    body: str = Field(..., min_length=1, max_length=4000)
    parent_id: str | None = None
    anchor: str | None = Field(None, max_length=200)


class ReviewCommentEdit(BaseModel):
    """수정 페이로드 — body만 변경 가능(parent_id·anchor는 생성 이후 불변)."""

    body: str = Field(..., min_length=1, max_length=4000)


class ReviewCommentResolve(BaseModel):
    resolved: bool


class ReviewCommentOut(BaseModel):
    """의견교환 댓글 뷰 — 삭제(soft) 시 body=null. 은닉은 직렬화 계층(라우터 _comment_out의 visible_body) 책임."""

    id: str
    project_id: str
    document_id: str
    parent_id: str | None = None
    anchor: str | None = None
    author_id: str | None = None
    body: str | None = None
    resolved: bool = False
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    edited: bool = False
    status: str = "active"
    created_at: datetime | None = None


class ReviewCommentActionResult(BaseModel):
    ok: bool
    status: str
    detail: str | None = None
