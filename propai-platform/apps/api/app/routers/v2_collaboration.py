"""SP2 프로젝트 회의방(F3) 협업 API — 멤버 조회 + 외부 협력업체 초대(발급/수락/회수).

접근제어는 require_project_member(멤버십 DB조회, app-level 1차)가 담당. 초대 생성/회수는 owner/
manager만. 수락은 토큰 기반(수락자는 아직 멤버가 아닐 수 있음 → 로그인만 요구). 결정 로직은
collaboration_service, DB I/O는 collaboration_repo로 분리.
"""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_collaboration import require_project_member
from app.core.database import get_db
from app.models.collaboration import PROJECT_ROLES, REVIEW_CATEGORIES
from app.schemas.collaboration import (
    DocumentActionResult,
    DocumentOut,
    DocumentReviewUpdate,
    DocumentShapesOut,
    InviteActionResult,
    InviteCreate,
    InviteOut,
    MemberOut,
)
from app.services.auth.auth_service import get_current_user
from app.services.collaboration import collaboration_repo as repo
from app.services.collaboration.collaboration_rules import (
    analysis_allows_kind,
    classify_doc_kind,
    document_in_scope,
    is_allowed_review_transition,
    is_blocked_upload,
    normalize_document_category,
    normalize_purpose,
)
from app.services.collaboration.collaboration_service import (
    accept_invite_result,
    build_invite_fields,
)
from app.services.collaboration.document_audit_service import (
    parse_design_shapes,
    run_design_document_audit,
)
from apps.api.services.storage_service import (
    StorageError,
    download_collab_document,
    upload_collab_document,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v2/collaboration", tags=["collaboration"])

_MAX_DOC_BYTES = 30 * 1024 * 1024  # 30MB(협업 문서 — DXF/IFC/PDF는 이미지보다 큼)

# 모듈레벨 의존성(테스트가 dependency_overrides로 정확히 대체 가능하도록).
_require_member = require_project_member(*PROJECT_ROLES)        # 활성 멤버 누구나
_require_admin = require_project_member("owner", "manager")     # 초대 발급/회수
# 심의 상태 전이(표기용) — 심의자·관리자만. viewer/외부 게스트 외 contributor도 제외.
_require_reviewer = require_project_member(
    "owner", "manager", "reviewer_internal", "external_reviewer"
)


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
    member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 팀 멤버 목록. 외부 협력업체(external_reviewer)는 내부 팀 + 본인만(SP5 scope 연장 —
    다른 외부 협력업체/경쟁사 명부 열람 차단). 내부 역할은 전체 조회."""
    members = await repo.list_members(db, uuid.UUID(project_id))
    if member.project_role == "external_reviewer":
        members = [
            m
            for m in members
            if m.project_role != "external_reviewer"
            or str(getattr(m, "user_id", "")) == str(getattr(member, "user_id", ""))
        ]
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

def _doc_in_member_scope(member, doc) -> bool:
    """문서가 멤버 허용 범위 안인지 — 외부 협력업체(external_reviewer) scope 강제(SP5)."""
    return document_in_scope(
        member.project_role, getattr(member, "scope_categories", None), getattr(doc, "category", None)
    )


def _document_out(d) -> DocumentOut:
    return DocumentOut(
        id=str(d.id),
        project_id=str(d.project_id),
        uploaded_by=str(d.uploaded_by) if getattr(d, "uploaded_by", None) is not None else None,
        original_filename=d.original_filename,
        content_type=getattr(d, "content_type", None),
        size_bytes=getattr(d, "size_bytes", None),
        category=getattr(d, "category", None),
        purpose=getattr(d, "purpose", "storage"),
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
    purpose: str = Form("storage"),
    member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """협력업체 자료(문서) 업로드 — 활성 멤버. 실파일은 비공개 버킷(서명URL), DB엔 메타+path만.

    purpose 구분(SP4): analysis(8엔진 자동검증 대상 — DXF/IFC 설계파일만 허용, 그 외 400) /
    storage(공유·저장 전용 — 임의 형식 무제한, 8엔진 미투입). analysis+design만 업로드 시 8엔진을
    결정론 투입한다(audit_status pending→completed/failed). storage는 audit_status=null(미검증).
    """
    purpose = normalize_purpose(purpose)
    filename = file.filename or "upload"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(status_code=413, detail="문서가 너무 큽니다(최대 30MB).")
    if is_blocked_upload(data, filename):
        raise HTTPException(status_code=400, detail="실행·스크립트 파일은 업로드할 수 없습니다.")

    doc_kind = classify_doc_kind(file.content_type, filename)
    run_audit = purpose == "analysis" and doc_kind == "design"
    if purpose == "analysis" and not analysis_allows_kind(doc_kind):
        # 분석용은 8엔진이 입력으로 받는 설계파일(DXF/IFC)만 — 보고서·문서는 거부(과대표기 금지).
        raise HTTPException(
            status_code=400,
            detail="분석용 업로드는 DXF/IFC 설계파일만 가능합니다. 보고서·문서는 '저장·공유용'으로 올려주세요.",
        )

    try:
        up = await upload_collab_document(data, file.content_type or "", filename, ttl_days=14)
    except StorageError as exc:
        logger.warning("collab_document_upload_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"스토리지 업로드 실패: {exc}") from exc

    # 파일명 정규화 — null-byte 제거 + basename(경로 traversal·표시 위조 차단). 빈값은 'upload'.
    safe_name = os.path.basename(filename.replace("\\", "/")).split("\x00", 1)[0][:255] or "upload"
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
        "purpose": purpose,
        "doc_kind": doc_kind,
        "audit_status": "pending" if run_audit else None,  # 저장용/미검증은 null(정직)
        "review_state": "requested",
        "status": "active",
    }
    doc = await repo.insert_document(db, fields)

    # SP3-4/SP4-1 — 분석용 설계파일만 8엔진 실투입(결정론·LLM 0). 업로드는 이미 성공했으므로 감사는
    # best-effort(실패 시 audit_status='failed' 정직 표기, 업로드 무중단).
    if run_audit:
        try:
            a_status, a_summary = await run_design_document_audit(
                db, filename=filename, data=data,
                project_id=project_id,                       # Phase 0 unit d: 원장 backlink context
                tenant_id=str(member.organization_id),
                created_by=str(user.id),
            )
        except Exception as exc:  # noqa: BLE001 — best-effort: 업로드 성공 보존, 정직 표기
            logger.warning("collab_document_audit_failed", error=str(exc)[:200])
            a_status, a_summary = "failed", {"error": str(exc)[:160]}
        doc = await repo.update_document_audit(db, doc, a_status, a_summary)

    return _document_out(doc)


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut])
async def list_project_documents(
    project_id: str,
    member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
):
    """자료교환 문서 목록(활성, 최신순). 외부 협력업체는 허용 심의범위(scope) 문서만 노출(SP5).

    정직: 서명URL은 TTL(14일) 후 만료된다. 만료분 재서명은 후속(sign_collab_document 존재) — 본
    MVP는 마지막 발급 URL을 그대로 반환한다(과대표기 금지: 영구 URL 아님).
    """
    docs = await repo.list_documents(db, uuid.UUID(project_id))
    return [_document_out(d) for d in docs if _doc_in_member_scope(member, d)]


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
    if not _doc_in_member_scope(member, doc):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")  # scope 밖(존재 비노출)

    is_admin = member.project_role in ("owner", "manager")
    is_uploader = (
        getattr(doc, "uploaded_by", None) is not None
        and str(doc.uploaded_by) == str(member.user_id)
    )
    if not (is_admin or is_uploader):
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다(관리자 또는 업로더만)")

    await repo.soft_delete_document(db, doc)
    return DocumentActionResult(ok=True, status="deleted")


@router.post("/projects/{project_id}/documents/{doc_id}/review-state", response_model=DocumentOut)
async def set_document_review_state(
    project_id: str,
    doc_id: str,
    body: DocumentReviewUpdate,
    member=Depends(_require_reviewer),
    db: AsyncSession = Depends(get_db),
):
    """표기용 심의 상태 전이 — 심의자/관리자만. 전진(requested→acknowledged→addressed)만 허용.

    정직: 이는 *사람 심의자*가 누른 상태 기록일 뿐 8엔진 자동판정이 아니다(LLM=0). 전이 규칙 위반
    (스킵·역행·무변경·미지)은 409. design 문서의 8엔진 audit_status와는 별개 트랙.
    """
    try:
        did = uuid.UUID(doc_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다") from exc

    doc = await repo.get_document(db, did)
    if doc is None or str(doc.project_id) != str(uuid.UUID(project_id)) or doc.status != "active":
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    if not _doc_in_member_scope(member, doc):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")  # scope 밖(존재 비노출)

    if not is_allowed_review_transition(doc.review_state, body.target_state):
        raise HTTPException(
            status_code=409,
            detail=f"허용되지 않는 심의 상태 전이: {doc.review_state} → {body.target_state}",
        )

    doc2 = await repo.set_document_review_state(
        db, doc, body.target_state, member.user_id, datetime.utcnow()
    )
    return _document_out(doc2)


@router.get("/projects/{project_id}/documents/{doc_id}/shapes", response_model=DocumentShapesOut)
async def get_document_shapes(
    project_id: str,
    doc_id: str,
    member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
):
    """저장된 DXF 설계파일을 파싱해 CAD2.0 셰이프를 반환 — 회의방 경량 CAD 뷰어용(읽기전용).

    재서명 후 비공개 버킷에서 다운로드 → parse_design_shapes(결정론). DXF만 지원(IFC·문서는 415).
    실파싱 결과만 반환(가짜 기하 금지) — 빈/무효 DXF는 422.
    """
    try:
        did = uuid.UUID(doc_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다") from exc

    doc = await repo.get_document(db, did)
    if doc is None or str(doc.project_id) != str(uuid.UUID(project_id)) or doc.status != "active":
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    if not _doc_in_member_scope(member, doc):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")  # scope 밖(존재 비노출)

    name = (doc.original_filename or "").lower()
    if doc.doc_kind != "design" or not name.endswith(".dxf"):
        raise HTTPException(status_code=415, detail="DXF 설계파일만 도면 미리보기를 지원합니다.")

    try:
        data = await download_collab_document(doc.storage_path)
    except StorageError as exc:
        logger.warning("collab_document_download_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"문서 다운로드 실패: {exc}") from exc

    try:
        result = parse_design_shapes(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"DXF 파싱 실패: {str(exc)[:120]}") from exc

    return DocumentShapesOut(
        shapes=list(result.get("shapes") or []),
        bounds_px=result.get("bounds_px"),
        scale_px_per_m=result.get("scale_px_per_m"),
    )
