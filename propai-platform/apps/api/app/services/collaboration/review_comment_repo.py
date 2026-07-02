"""SP6 의견교환 DB 연산(repo) — 댓글 영속. 라우터가 호출하며 테스트는 본 함수들을 monkeypatch.

순수 규칙은 review_comment_rules, DB I/O는 여기로 분리(collaboration_repo 패턴 동일).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration import ReviewComment


async def list_comments_for_document(db: AsyncSession, document_id: uuid.UUID) -> list[ReviewComment]:
    """문서의 전체 댓글(soft 삭제 포함, created_at 오름차순). body 은닉은 직렬화 계층, \
트리 조립·잎 가시성은 클라이언트."""
    rows = await db.execute(
        select(ReviewComment)
        .where(ReviewComment.document_id == document_id)
        .order_by(ReviewComment.created_at.asc())
    )
    return list(rows.scalars().all())


async def get_comment(db: AsyncSession, comment_id: uuid.UUID) -> ReviewComment | None:
    rows = await db.execute(select(ReviewComment).where(ReviewComment.id == comment_id))
    return rows.scalar_one_or_none()


async def insert_comment(db: AsyncSession, fields: dict[str, Any]) -> ReviewComment:
    c = ReviewComment(**fields)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def update_comment_body(
    db: AsyncSession, c: ReviewComment, body: str, now: datetime
) -> ReviewComment:
    c.body = body
    c.edited = True
    c.updated_at = now
    await db.commit()
    await db.refresh(c)
    return c


async def soft_delete_comment(db: AsyncSession, c: ReviewComment) -> None:
    """소프트 삭제 — 행 보존(트리 무결성), status='deleted'."""
    c.status = "deleted"
    await db.commit()


async def set_comment_resolved(
    db: AsyncSession, c: ReviewComment, resolved: bool, user_id: uuid.UUID, now: datetime
) -> ReviewComment:
    """루트 스레드 해결/재오픈 — resolved=False면 처리자·시각 초기화(정직)."""
    c.resolved = resolved
    c.resolved_by = user_id if resolved else None
    c.resolved_at = now if resolved else None
    await db.commit()
    await db.refresh(c)
    return c
