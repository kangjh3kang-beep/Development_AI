"""SP2 협업 접근제어 의존성 — 프로젝트 멤버십 기반(app-level 1차 강제, RLS 방어심층).

공용 get_db(core/database.py·session.py:88)가 RLS GUC(app.current_tenant/user)를 미주입하므로
RLS 정책만으론 런타임 격리가 불충분하다(검증됨). 따라서 외부 게스트 포함 접근제어는 본 멤버십
DB조회(app-level)를 1차로 둔다 — 헤더 위조에 안전하며, 멤버십 행이 가리키는 프로젝트로만 허용.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.collaboration import ProjectMember
from app.models.project import Project
from app.services.auth.auth_service import get_current_user
from app.services.collaboration.collaboration_service import member_allows


def _implicit_owner_member(pid: uuid.UUID, organization_id, user_id) -> ProjectMember:
    """조직 내부 사용자의 암묵 owner 멤버십(비영속 — DB에 추가하지 않음).

    프로젝트는 organization_id로 조직 소유다(개인 owner 컬럼 없음). 따라서 프로젝트 생성자/내부
    팀원은 명시적 ProjectMember 행이 없어도 자기 조직 프로젝트에는 owner로 접근한다(외부 협력업체만
    초대→ProjectMember로 명시 관리). 라우터가 organization_id·project_role·user_id를 활용한다.
    """
    m = ProjectMember()
    m.project_id = pid
    m.organization_id = organization_id
    m.user_id = user_id
    m.project_role = "owner"
    m.status = "active"
    return m


def require_project_member(*allowed_roles: str) -> Callable:
    """FastAPI 의존성 팩토리 — 경로의 project_id에 대해 현재 사용자가 접근 가능한지 강제.

    1차: 명시적 ProjectMember(active·허용역할) — 외부 협력업체 게스트 등. 2차(없으면): 조직 내부
    사용자 암묵 멤버십 — user.tenant_id == project.organization_id면 owner로 허용(프로젝트는 조직
    소유라 생성자/내부팀이 멤버 행 없이도 접근). 둘 다 실패 시 403. 비UUID project_id는 403.
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

        # 명시적 멤버십 행이 있으면 그 행으로만 판정한다 — suspended/removed/강등 행이 아래 암묵
        # owner 폴백으로 복원되는 권한상승을 차단(허용역할·active면 통과, 아니면 403, 폴백 금지).
        if row is not None:
            if member_allows(row.project_role, allowed_roles, row.status):
                return row
            raise HTTPException(status_code=403, detail="이 프로젝트에 대한 권한이 없습니다")

        # 2차(명시적 행이 없을 때만): 조직 내부 사용자 암묵 owner 멤버십(생성자/내부팀 — 행 미생성).
        user_tenant = getattr(user, "tenant_id", None)
        if user_tenant is not None and ("owner" in allowed_roles or not allowed_roles):
            # ★organization_id 컬럼만 선택한다(전체 Project 모델 로드 금지). projects 테이블은
            #   ORM 모델과 컬럼이 드리프트돼 있어 select(Project) 전체로드는 UndefinedColumnError로
            #   죽는다(멤버십 판정엔 organization_id 하나면 충분). org.id==tenant.id(1:1)라 일치 판정.
            proj_org = (
                await db.execute(select(Project.organization_id).where(Project.id == pid))
            ).scalar_one_or_none()
            if proj_org is not None and proj_org == user_tenant:
                return _implicit_owner_member(pid, proj_org, user.id)

        raise HTTPException(status_code=403, detail="이 프로젝트에 대한 권한이 없습니다")

    return _dep
