"""SP2 협업 접근제어 의존성 — 프로젝트 멤버십 기반(app-level 1차 강제, RLS 방어심층).

공용 get_db(core/database.py·session.py:88)가 RLS GUC(app.current_tenant/user)를 미주입하므로
RLS 정책만으론 런타임 격리가 불충분하다(검증됨). 따라서 외부 게스트 포함 접근제어는 본 멤버십
DB조회(app-level)를 1차로 둔다 — 헤더 위조에 안전하며, 멤버십 행이 가리키는 프로젝트로만 허용.
"""

from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.collaboration import ProjectMember
from app.services.auth.auth_service import get_current_user
from app.services.collaboration.collaboration_service import member_allows


def require_project_member(*allowed_roles: str) -> Callable:
    """FastAPI 의존성 팩토리 — 경로의 project_id에 대해 현재 사용자가 active 멤버이며 허용역할인지 강제.

    실패(멤버 아님/비활성/허용역할 아님) 시 403. 성공 시 ProjectMember를 반환(라우터가
    organization_id·project_role 등 활용). 비UUID project_id는 멤버십 불가로 403.
    """

    async def _dep(
        project_id: str,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
    ) -> ProjectMember:
        try:
            pid = uuid.UUID(str(project_id))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=403, detail="이 프로젝트에 대한 권한이 없습니다") from exc

        row = (
            await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == pid,
                    ProjectMember.user_id == user.id,
                )
            )
        ).scalar_one_or_none()

        if row is None or not member_allows(row.project_role, allowed_roles, row.status):
            raise HTTPException(status_code=403, detail="이 프로젝트에 대한 권한이 없습니다")
        return row

    return _dep
