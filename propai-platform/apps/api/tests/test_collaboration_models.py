"""SP2-1: 협업 데이터모델 + 초대 라이프사이클 순수 규칙.

프로젝트 회의방(F3) MVP 첫 단위 — ProjectMember/CollaboratorInvite 모델 구조와 초대 만료/수락
가능성·역할검증·심의범위 화이트리스트를 결정론 순수함수로 검증한다(DB 불필요). 접근제어 자체는
후속 require_project_member(app-level 1차)·RLS(방어심층)가 담당하며 본 단위는 모델·규칙만.

정직: org RLS GUC가 공용 get_db에 미주입(core/database.py:39·session.py:88)이라 RLS만으론 격리
불충분 → 본 SP2는 멤버십 DB조회 기반 app-level 강제를 1차로 둔다(후속 단위).
"""

import uuid
from datetime import datetime, timedelta

from app.models.collaboration import (
    ProjectMember,
    CollaboratorInvite,
    PROJECT_ROLES,
    REVIEW_CATEGORIES,
)
from app.services.collaboration.collaboration_rules import (
    is_invite_expired,
    is_invite_acceptable,
    validate_project_role,
    filter_scope_categories,
)


class TestModelStructure:
    def test_project_member_table_and_columns(self):
        assert ProjectMember.__tablename__ == "project_members"
        cols = set(ProjectMember.__table__.columns.keys())
        for c in ("id", "project_id", "organization_id", "user_id", "project_role",
                  "status", "invited_by", "created_at"):
            assert c in cols, f"ProjectMember 컬럼 누락: {c}"

    def test_collaborator_invite_table_and_columns(self):
        assert CollaboratorInvite.__tablename__ == "collaborator_invites"
        cols = set(CollaboratorInvite.__table__.columns.keys())
        for c in ("id", "project_id", "organization_id", "invite_token", "email",
                  "project_role", "scope_categories", "status", "expires_at", "created_at"):
            assert c in cols, f"CollaboratorInvite 컬럼 누락: {c}"

    def test_unique_project_user(self):
        names = {
            tuple(sorted(col.name for col in con.columns))
            for con in ProjectMember.__table__.constraints
            if con.__class__.__name__ == "UniqueConstraint"
        }
        assert ("project_id", "user_id") in names


class TestEnums:
    def test_project_roles_include_external_reviewer(self):
        # 외부 협력업체(게스트 심의자) 역할 + 핵심 내부 역할
        for r in ("owner", "manager", "contributor", "reviewer_internal", "external_reviewer", "viewer"):
            assert r in PROJECT_ROLES

    def test_review_categories_six(self):
        assert set(REVIEW_CATEGORIES) == {
            "traffic", "environment", "civil", "landscape", "architecture", "fire",
        }


class TestInviteLifecycleRules:
    def test_expired_when_past(self):
        now = datetime(2026, 6, 14, 12, 0, 0)
        assert is_invite_expired(now - timedelta(seconds=1), now) is True
        assert is_invite_expired(now + timedelta(days=1), now) is False

    def test_acceptable_only_pending_and_unexpired(self):
        now = datetime(2026, 6, 14, 12, 0, 0)
        future = now + timedelta(days=7)
        past = now - timedelta(days=1)
        assert is_invite_acceptable("pending", future, now) is True
        assert is_invite_acceptable("pending", past, now) is False  # 만료
        assert is_invite_acceptable("revoked", future, now) is False  # 회수됨
        assert is_invite_acceptable("accepted", future, now) is False  # 이미 수락

    def test_validate_project_role(self):
        assert validate_project_role("external_reviewer") is True
        assert validate_project_role("nonsense_role") is False

    def test_filter_scope_categories_whitelist(self):
        # 허용 범위 ∩ 유효 카테고리만 통과(가짜 카테고리·범위초과 제거 — 서버측 필터)
        assert filter_scope_categories(
            ["traffic", "fire", "hacking"], allowed=["traffic", "environment"]
        ) == ["traffic"]
        # allowed 비면 전부 차단(기밀 기본 비공개)
        assert filter_scope_categories(["traffic"], allowed=[]) == []
        # 순서 보존·중복 제거
        assert filter_scope_categories(
            ["fire", "fire", "civil"], allowed=["civil", "fire"]
        ) == ["fire", "civil"]
