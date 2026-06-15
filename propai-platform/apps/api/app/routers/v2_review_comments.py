"""SP6 회의방 의견교환(심의 스레드) API — 문서/지적별 댓글·답변(무제한 중첩) + 루트 해결.

접근제어는 require_project_member(멤버십 1차) + document_in_scope(외부 협력업체 scope 강제, SP5)로
기존 자료교환과 동일 보안경계를 공유한다. 읽기=활성멤버 전원, 쓰기/답변=viewer 제외, 해결=심의자·
관리자, 수정/삭제=작성자 본인(+관리자 소프트삭제). 결정 로직은 review_comment_rules, DB I/O는
review_comment_repo로 분리. resolved는 문서 review_state와 별개 사람주도 트랙(자동판정 아님, LLM=0).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_collaboration import require_project_member
from app.core.database import get_db
from app.models.collaboration import PROJECT_ROLES
from app.schemas.collaboration import (
    ReviewCommentActionResult,
    ReviewCommentCreate,
    ReviewCommentEdit,
    ReviewCommentOut,
    ReviewCommentResolve,
)
from app.services.auth.auth_service import get_current_user
from app.services.collaboration import collaboration_repo as doc_repo
from app.services.collaboration import review_comment_repo as repo
from app.services.collaboration.collaboration_rules import document_in_scope
from app.services.collaboration.review_comment_rules import (
    anchor_allowed,
    parent_is_valid,
    resolve_allowed,
    validate_comment_body,
    visible_body,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v2/collaboration", tags=["collaboration"])

# 모듈레벨 의존성(테스트가 dependency_overrides로 정확히 대체 가능하도록).
_require_member = require_project_member(*PROJECT_ROLES)  # 읽기: 활성멤버 전원(viewer 포함)
# 쓰기/답변/수정/삭제: viewer 제외 전원(+외부 게스트는 scope 강제).
_require_commenter = require_project_member(
    "owner", "manager", "contributor", "reviewer_internal", "external_reviewer"
)
# 해결/재오픈: 심의자·관리자(SP3 _require_reviewer와 동일 집합).
_require_reviewer = require_project_member(
    "owner", "manager", "reviewer_internal", "external_reviewer"
)


def _comment_out(c) -> ReviewCommentOut:
    return ReviewCommentOut(
        id=str(c.id),
        project_id=str(c.project_id),
        document_id=str(c.document_id),
        parent_id=str(c.parent_id) if getattr(c, "parent_id", None) is not None else None,
        anchor=getattr(c, "anchor", None),
        author_id=str(c.author_id) if getattr(c, "author_id", None) is not None else None,
        body=visible_body(c.status, c.body),
        resolved=bool(getattr(c, "resolved", False)),
        resolved_by=str(c.resolved_by) if getattr(c, "resolved_by", None) is not None else None,
        resolved_at=getattr(c, "resolved_at", None),
        edited=bool(getattr(c, "edited", False)),
        status=c.status,
        created_at=getattr(c, "created_at", None),
    )


async def _load_scoped_document(db, project_id: str, doc_id: str, member):
    """문서 로드 + 프로젝트·active·scope 검증(자료교환 엔드포인트와 동일 경계). 실패 시 404."""
    try:
        did = uuid.UUID(doc_id)
        pid = uuid.UUID(project_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다") from exc
    doc = await doc_repo.get_document(db, did)
    if doc is None or str(doc.project_id) != str(pid) or doc.status != "active":
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    if not document_in_scope(
        member.project_role, getattr(member, "scope_categories", None), getattr(doc, "category", None)
    ):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")  # scope 밖(존재 비노출)
    return doc


async def _load_active_comment(db, comment_id: str, document_id):
    """댓글 로드 + 동일 문서·active 확인. 비UUID·부재·타문서·삭제는 404."""
    try:
        cid = uuid.UUID(comment_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다") from exc
    c = await repo.get_comment(db, cid)
    if c is None or str(c.document_id) != str(document_id) or c.status != "active":
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다")
    return c


@router.get(
    "/projects/{project_id}/documents/{doc_id}/comments",
    response_model=list[ReviewCommentOut],
)
async def list_comments(
    project_id: str,
    doc_id: str,
    member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
):
    """문서 댓글 목록(flat, 오래된→최신; soft 삭제 포함·본문 null). 트리·가시성은 클라이언트."""
    doc = await _load_scoped_document(db, project_id, doc_id, member)
    comments = await repo.list_comments_for_document(db, doc.id)
    return [_comment_out(c) for c in comments]


@router.post(
    "/projects/{project_id}/documents/{doc_id}/comments",
    response_model=ReviewCommentOut,
)
async def create_comment(
    project_id: str,
    doc_id: str,
    body: ReviewCommentCreate,
    member=Depends(_require_commenter),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """댓글/답변 생성 — viewer 제외 멤버. parent_id 있으면 답변(부모 active·동일문서). anchor는 루트만."""
    doc = await _load_scoped_document(db, project_id, doc_id, member)

    try:
        text = validate_comment_body(body.body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parent_id = None
    if body.parent_id:
        try:
            parent_id = uuid.UUID(body.parent_id)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=404, detail="부모 댓글을 찾을 수 없습니다") from exc
        parent = await repo.get_comment(db, parent_id)
        if parent is None or not parent_is_valid(parent.status, parent.document_id, doc.id):
            raise HTTPException(status_code=404, detail="부모 댓글을 찾을 수 없습니다")

    # 빈/공백 앵커는 미지정(None)으로 정규화(표기용 포인터 — 빈 문자열 저장 방지).
    anchor = (body.anchor or "").strip() or None
    if anchor is not None and not anchor_allowed(parent_id):
        raise HTTPException(status_code=400, detail="답변에는 지적 앵커를 붙일 수 없습니다(루트 전용)")

    fields = {
        "project_id": uuid.UUID(project_id),
        "organization_id": member.organization_id,
        "document_id": doc.id,
        "parent_id": parent_id,
        "anchor": anchor,
        "author_id": user.id,
        "body": text,
        "resolved": False,
        "edited": False,
        "status": "active",
    }
    c = await repo.insert_comment(db, fields)
    return _comment_out(c)


@router.put(
    "/projects/{project_id}/documents/{doc_id}/comments/{comment_id}",
    response_model=ReviewCommentOut,
)
async def edit_comment(
    project_id: str,
    doc_id: str,
    comment_id: str,
    body: ReviewCommentEdit,
    member=Depends(_require_commenter),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """본문 수정 — 작성자 본인만(edited=true 정직 표기)."""
    doc = await _load_scoped_document(db, project_id, doc_id, member)
    c = await _load_active_comment(db, comment_id, doc.id)
    if c.author_id is None or str(c.author_id) != str(user.id):
        raise HTTPException(status_code=403, detail="수정 권한이 없습니다(작성자만)")
    try:
        text = validate_comment_body(body.body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    c2 = await repo.update_comment_body(db, c, text, datetime.utcnow())
    return _comment_out(c2)


@router.delete(
    "/projects/{project_id}/documents/{doc_id}/comments/{comment_id}",
    response_model=ReviewCommentActionResult,
)
async def delete_comment(
    project_id: str,
    doc_id: str,
    comment_id: str,
    member=Depends(_require_commenter),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """소프트삭제 — 작성자 본인 또는 admin(owner/manager). 행 보존(트리 무결성)."""
    doc = await _load_scoped_document(db, project_id, doc_id, member)
    c = await _load_active_comment(db, comment_id, doc.id)
    is_admin = member.project_role in ("owner", "manager")
    is_author = c.author_id is not None and str(c.author_id) == str(user.id)
    if not (is_admin or is_author):
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다(작성자 또는 관리자만)")
    await repo.soft_delete_comment(db, c)
    return ReviewCommentActionResult(ok=True, status="deleted")


@router.post(
    "/projects/{project_id}/documents/{doc_id}/comments/{comment_id}/resolve",
    response_model=ReviewCommentOut,
)
async def resolve_comment(
    project_id: str,
    doc_id: str,
    comment_id: str,
    body: ReviewCommentResolve,
    member=Depends(_require_reviewer),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """스레드 해결/재오픈 — 심의자·관리자. 루트 댓글만(답변 409). review_state와 별개 트랙(정직)."""
    doc = await _load_scoped_document(db, project_id, doc_id, member)
    c = await _load_active_comment(db, comment_id, doc.id)
    if not resolve_allowed(c.parent_id):
        raise HTTPException(status_code=409, detail="답변은 해결할 수 없습니다(루트 스레드만)")
    c2 = await repo.set_comment_resolved(db, c, bool(body.resolved), user.id, datetime.utcnow())
    return _comment_out(c2)
