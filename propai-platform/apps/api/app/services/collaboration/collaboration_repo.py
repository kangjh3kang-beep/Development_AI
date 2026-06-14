"""SP2 협업 DB 연산(repo) — 멤버/초대 영속. 라우터가 호출하며, 테스트는 본 함수들을 monkeypatch.

순수 결정 로직은 collaboration_service에, DB I/O는 여기에 분리(테스트 용이·관심사 분리).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration import CollaboratorInvite, ProjectMember


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
