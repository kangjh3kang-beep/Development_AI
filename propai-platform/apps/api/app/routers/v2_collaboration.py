"""SP2 프로젝트 회의방(F3) 협업 API — 멤버 조회 + 외부 협력업체 초대(발급/수락/회수).

접근제어는 require_project_member(멤버십 DB조회, app-level 1차)가 담당. 초대 생성/회수는 owner/
manager만. 수락은 토큰 기반(수락자는 아직 멤버가 아닐 수 있음 → 로그인만 요구). 결정 로직은
collaboration_service, DB I/O는 collaboration_repo로 분리.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.storage_service import StorageError, upload_collab_document
from app.api.deps_collaboration import require_project_member
from app.core.database import get_db
from app.models.collaboration import PROJECT_ROLES, REVIEW_CATEGORIES
from app.schemas.collaboration import (
    DocumentActionResult,
    DocumentOut,
    InviteActionResult,
    InviteCreate,
    InviteOut,
    MemberOut,
)
from app.services.auth.auth_service import get_current_user
from app.services.collaboration import collaboration_repo as repo
from app.services.collaboration.collaboration_rules import (
    classify_doc_kind,
    normalize_document_category,
)
from app.services.collaboration.collaboration_service import (
    accept_invite_result,
    build_invite_fields,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v2/collaboration", tags=["collaboration"])

_MAX_DOC_BYTES = 30 * 1024 * 1024  # 30MB(협업 문서 — DXF/IFC/PDF는 이미지보다 큼)

# 모듈레벨 의존성(테스트가 dependency_overrides로 정확히 대체 가능하도록).
_require_member = require_project_member(*PROJECT_ROLES)        # 활성 멤버 누구나
_require_admin = require_project_member("owner", "manager")     # 초대 발급/회수


def _member_out(m) -> MemberOut:
    return MemberOut(
        id=str(m.id),
        project_id=str(m.project_id),
        user_id=str(m.user_id) if m.user_id is not None else None,
        project_role=m.project_role,
        status=m.status,
        created_at=getattr(m, "created_at", None),
    )


def _invite_out(inv, *, with_token: bool) -> InviteOut:
    return InviteOut(
        id=str(inv.id) if getattr(inv, "id", None) is not None else None,
        project_id=str(inv.project_id),
        email=inv.email,
        project_role=inv.project_role,
        scope_categories=list(inv.scope_categories or []),
        status=inv.status,
        expires_at=inv.expires_at,
        invite_token=inv.invite_token if with_token else None,
    )


@router.get("/projects/{project_id}/members", response_model=list[MemberOut])
async def list_members(
    project_id: str,
    _member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 팀 멤버(내부+외부 게스트) 목록 — 활성 멤버만 조회 가능."""
    members = await repo.list_members(db, uuid.UUID(project_id))
    return [_member_out(m) for m in members]


@router.post("/projects/{project_id}/invites", response_model=InviteOut)
async def create_invite(
    project_id: str,
    body: InviteCreate,
    member=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """외부 협력업체(게스트) 초대 발급 — owner/manager만. scope는 6 심의카테고리로 화이트리스트 필터."""
    try:
        fields = build_invite_fields(
            project_id=str(project_id),
            organization_id=str(member.organization_id),
            email=body.email,
            project_role=body.project_role,
            requested_categories=body.scope_categories,
            allowed_categories=list(REVIEW_CATEGORIES),
            invited_by=str(user.id),
            now=datetime.utcnow(),
            token_factory=lambda: secrets.token_urlsafe(32),
            ttl_days=body.ttl_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    inv = await repo.insert_invite(db, fields)
    return _invite_out(inv, with_token=True)  # 생성 직후 1회만 토큰 노출(공유용)


@router.post("/invites/{token}/accept", response_model=InviteActionResult)
async def accept_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """초대 수락 — 토큰 기반(수락자는 로그인만 필요). pending·미만료일 때만 멤버 생성."""
    inv = await repo.get_invite_by_token(db, token)
    if inv is None:
        raise HTTPException(status_code=404, detail="초대를 찾을 수 없습니다")
    ok, reason = accept_invite_result(inv.status, inv.expires_at, datetime.utcnow())
    if not ok:
        raise HTTPException(status_code=409, detail=reason)
    await repo.accept_invite_persist(db, inv, user.id, datetime.utcnow())
    return InviteActionResult(ok=True, status="accepted")


@router.post("/projects/{project_id}/invites/{invite_id}/revoke", response_model=InviteActionResult)
async def revoke_invite(
    project_id: str,
    invite_id: str,
    _member=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """초대 회수 — owner/manager만. invite revoked + 연결 멤버 removed(소프트)."""
    inv = await repo.get_invite_by_id(db, uuid.UUID(invite_id))
    if inv is None:
        raise HTTPException(status_code=404, detail="초대를 찾을 수 없습니다")
    if str(inv.project_id) != str(uuid.UUID(project_id)):
        raise HTTPException(status_code=403, detail="해당 프로젝트의 초대가 아닙니다")
    await repo.revoke_invite_persist(db, inv)
    return InviteActionResult(ok=True, status="revoked")


# ── SP3 자료교환(협력업체 업로드자료) ──

def _document_out(d) -> DocumentOut:
    return DocumentOut(
        id=str(d.id),
        project_id=str(d.project_id),
        uploaded_by=str(d.uploaded_by) if getattr(d, "uploaded_by", None) is not None else None,
        original_filename=d.original_filename,
        content_type=getattr(d, "content_type", None),
        size_bytes=getattr(d, "size_bytes", None),
        category=getattr(d, "category", None),
        doc_kind=d.doc_kind,
        audit_status=getattr(d, "audit_status", None),
        audit_summary=getattr(d, "audit_summary", None),
        review_state=d.review_state,
        reviewed_by=str(d.reviewed_by) if getattr(d, "reviewed_by", None) is not None else None,
        reviewed_at=getattr(d, "reviewed_at", None),
        file_url=getattr(d, "file_url", None),
        created_at=getattr(d, "created_at", None),
    )


@router.post("/projects/{project_id}/documents", response_model=DocumentOut)
async def upload_project_document(
    project_id: str,
    file: UploadFile = File(...),
    category: str | None = Form(None),
    member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """협력업체 자료(문서) 업로드 — 활성 멤버. 실파일은 비공개 버킷(서명URL), DB엔 메타+path만.

    doc_kind=design(DXF/IFC)은 8엔진 자동검증 대상(audit_status='pending' — SP3-4가 실투입),
    document(PDF 등)은 8엔진 미지원이라 audit_status='unsupported'(사람 심의자 review_state로 처리).
    """
    filename = file.filename or "upload"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(status_code=413, detail="문서가 너무 큽니다(최대 30MB).")

    doc_kind = classify_doc_kind(file.content_type, filename)
    try:
        up = await upload_collab_document(data, file.content_type or "", filename, ttl_days=14)
    except StorageError as exc:
        logger.warning("collab_document_upload_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"스토리지 업로드 실패: {exc}") from exc

    safe_name = filename.replace("\\", "/").rsplit("/", 1)[-1][:255]
    fields = {
        "project_id": uuid.UUID(project_id),
        "organization_id": member.organization_id,
        "uploaded_by": user.id,
        "storage_path": up["path"],
        "file_url": up["url"],
        "original_filename": safe_name,
        "content_type": file.content_type,
        "size_bytes": len(data),
        "category": normalize_document_category(category),
        "doc_kind": doc_kind,
        "audit_status": "unsupported" if doc_kind == "document" else "pending",
        "review_state": "requested",
        "status": "active",
    }
    doc = await repo.insert_document(db, fields)
    return _document_out(doc)


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut])
async def list_project_documents(
    project_id: str,
    _member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
):
    """자료교환 문서 목록(활성, 최신순). file_url은 마지막 발급 서명URL이다.

    정직: 서명URL은 TTL(14일) 후 만료된다. 만료분 재서명은 후속(sign_collab_document 존재) — 본
    MVP는 마지막 발급 URL을 그대로 반환한다(과대표기 금지: 영구 URL 아님).
    """
    docs = await repo.list_documents(db, uuid.UUID(project_id))
    return [_document_out(d) for d in docs]


@router.delete("/projects/{project_id}/documents/{doc_id}", response_model=DocumentActionResult)
async def delete_project_document(
    project_id: str,
    doc_id: str,
    member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
):
    """문서 소프트삭제 — admin(owner/manager) 또는 업로더 본인만. 행·스토리지 보존(status=deleted)."""
    try:
        did = uuid.UUID(doc_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다") from exc

    doc = await repo.get_document(db, did)
    if doc is None or str(doc.project_id) != str(uuid.UUID(project_id)) or doc.status != "active":
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

    is_admin = member.project_role in ("owner", "manager")
    is_uploader = (
        getattr(doc, "uploaded_by", None) is not None
        and str(doc.uploaded_by) == str(member.user_id)
    )
    if not (is_admin or is_uploader):
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다(관리자 또는 업로더만)")

    await repo.soft_delete_document(db, doc)
    return DocumentActionResult(ok=True, status="deleted")
