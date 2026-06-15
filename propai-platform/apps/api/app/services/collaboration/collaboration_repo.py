"""SP2 협업 DB 연산(repo) — 멤버/초대 영속. 라우터가 호출하며, 테스트는 본 함수들을 monkeypatch.

순수 결정 로직은 collaboration_service에, DB I/O는 여기에 분리(테스트 용이·관심사 분리).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration import CollaboratorInvite, ProjectDocument, ProjectMember


async def list_members(db: AsyncSession, project_id: uuid.UUID) -> list[ProjectMember]:
    rows = await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id)
    )
    return list(rows.scalars().all())


async def insert_invite(db: AsyncSession, fields: dict[str, Any]) -> CollaboratorInvite:
    inv = CollaboratorInvite(**fields)
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    return inv


async def get_invite_by_token(db: AsyncSession, token: str) -> Optional[CollaboratorInvite]:
    rows = await db.execute(
        select(CollaboratorInvite).where(CollaboratorInvite.invite_token == token)
    )
    return rows.scalar_one_or_none()


async def get_invite_by_id(db: AsyncSession, invite_id: uuid.UUID) -> Optional[CollaboratorInvite]:
    rows = await db.execute(
        select(CollaboratorInvite).where(CollaboratorInvite.id == invite_id)
    )
    return rows.scalar_one_or_none()


async def accept_invite_persist(
    db: AsyncSession, invite: CollaboratorInvite, user_id: uuid.UUID, now: datetime
) -> ProjectMember:
    """초대 수락 영속 — 멤버 행 생성(external_reviewer, active) + 초대 accepted 표기(동일 트랜잭션)."""
    member = ProjectMember(
        project_id=invite.project_id,
        organization_id=invite.organization_id,
        user_id=user_id,
        project_role=invite.project_role,
        status="active",
        scope_categories=list(invite.scope_categories or []),  # 초대 허용범위 영속(scope 강제용)
        invited_by=invite.invited_by,
    )
    db.add(member)
    invite.status = "accepted"
    invite.accepted_at = now
    invite.accepted_user_id = user_id
    await db.commit()
    await db.refresh(member)
    return member


async def revoke_invite_persist(db: AsyncSession, invite: CollaboratorInvite) -> None:
    """초대 회수 — invite revoked + 연결 멤버(있으면) removed(소프트·행 보존)."""
    invite.status = "revoked"
    if invite.accepted_user_id is not None:
        rows = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == invite.project_id,
                ProjectMember.user_id == invite.accepted_user_id,
            )
        )
        m = rows.scalar_one_or_none()
        if m is not None:
            m.status = "removed"
    await db.commit()


# ── SP3 자료교환 문서 영속(DB I/O) — 순수 분류/상태전이는 collaboration_rules ──

async def insert_document(db: AsyncSession, fields: dict[str, Any]) -> ProjectDocument:
    doc = ProjectDocument(**fields)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def list_documents(db: AsyncSession, project_id: uuid.UUID) -> list[ProjectDocument]:
    """활성(status='active') 문서만 최신순 — 소프트삭제분 제외."""
    rows = await db.execute(
        select(ProjectDocument)
        .where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.status == "active",
        )
        .order_by(ProjectDocument.created_at.desc())
    )
    return list(rows.scalars().all())


async def get_document(db: AsyncSession, doc_id: uuid.UUID) -> Optional[ProjectDocument]:
    rows = await db.execute(
        select(ProjectDocument).where(ProjectDocument.id == doc_id)
    )
    return rows.scalar_one_or_none()


async def soft_delete_document(db: AsyncSession, doc: ProjectDocument) -> None:
    """소프트 삭제 — 행·스토리지 보존, status='deleted'(감사 추적)."""
    doc.status = "deleted"
    await db.commit()


async def update_document_audit(
    db: AsyncSession, doc: ProjectDocument, audit_status: str, audit_summary: Optional[dict]
) -> ProjectDocument:
    """8엔진 투입 결과 기록(SP3-4) — design 문서의 audit_status/summary 갱신."""
    doc.audit_status = audit_status
    doc.audit_summary = audit_summary
    await db.commit()
    await db.refresh(doc)
    return doc


async def set_document_review_state(
    db: AsyncSession, doc: ProjectDocument, target: str, reviewed_by: uuid.UUID, now: datetime
) -> ProjectDocument:
    """표기용 심의 상태 전이 영속(SP3-6) — 전이 허용 검증은 호출측(rules.is_allowed_review_transition)."""
    doc.review_state = target
    doc.reviewed_by = reviewed_by
    doc.reviewed_at = now
    await db.commit()
    await db.refresh(doc)
    return doc
