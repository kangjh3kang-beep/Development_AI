"""SP2-2: 협업 서비스 코어 — 초대 생성·멤버 접근결정·수락 판정(결정론·DB세션 무관).

DB CRUD는 라우터 의존성(후속)이, 본 코어는 역할검증·심의범위 화이트리스트·만료·토큰을 결정론으로
(now·token_factory 주입) 산출한다. require_project_member의 판정도 member_allows로 분리해 단위검증.
"""

from datetime import datetime, timedelta

import pytest

from app.services.collaboration.collaboration_service import (
    build_invite_fields,
    member_allows,
    accept_invite_result,
    DEFAULT_INVITE_TTL_DAYS,
)

NOW = datetime(2026, 6, 14, 12, 0, 0)


def _tok() -> str:
    return "TESTTOKEN123"


class TestBuildInvite:
    def test_filters_scope_normalizes_email_and_expiry(self):
        inv = build_invite_fields(
            project_id="p1", organization_id="o1", email="  A@B.com ",
            project_role="external_reviewer",
            requested_categories=["traffic", "fire", "hacking"],
            allowed_categories=["traffic", "environment"],
            invited_by="u1", now=NOW, token_factory=_tok,
        )
        assert inv["invite_token"] == "TESTTOKEN123"
        assert inv["email"] == "a@b.com"                 # 정규화(trim+lower)
        assert inv["scope_categories"] == ["traffic"]    # 화이트리스트 ∩
        assert inv["status"] == "pending"
        assert inv["project_role"] == "external_reviewer"
        assert inv["expires_at"] == NOW + timedelta(days=DEFAULT_INVITE_TTL_DAYS)

    def test_custom_ttl(self):
        inv = build_invite_fields(
            project_id="p", organization_id="o", email="x@y.z",
            project_role="external_reviewer", requested_categories=[], allowed_categories=[],
            invited_by=None, now=NOW, ttl_days=7, token_factory=_tok,
        )
        assert inv["expires_at"] == NOW + timedelta(days=7)
        assert inv["scope_categories"] == []  # allowed 비면 전부 차단

    def test_invalid_role_rejected(self):
        with pytest.raises(ValueError):
            build_invite_fields(
                project_id="p", organization_id="o", email="x@y.z",
                project_role="hacker", requested_categories=[], allowed_categories=[],
                invited_by=None, now=NOW, token_factory=_tok,
            )

    def test_invalid_email_rejected(self):
        with pytest.raises(ValueError):
            build_invite_fields(
                project_id="p", organization_id="o", email="not-an-email",
                project_role="viewer", requested_categories=[], allowed_categories=[],
                invited_by=None, now=NOW, token_factory=_tok,
            )

    def test_nonpositive_ttl_rejected(self):
        with pytest.raises(ValueError):
            build_invite_fields(
                project_id="p", organization_id="o", email="x@y.z",
                project_role="viewer", requested_categories=[], allowed_categories=[],
                invited_by=None, now=NOW, ttl_days=0, token_factory=_tok,
            )


class TestMemberAllows:
    def test_active_and_allowed(self):
        assert member_allows("manager", ["owner", "manager"], "active") is True

    def test_wrong_role(self):
        assert member_allows("viewer", ["owner", "manager"], "active") is False

    def test_inactive_blocked_even_if_role_ok(self):
        assert member_allows("manager", ["manager"], "removed") is False
        assert member_allows("manager", ["manager"], "suspended") is False

    def test_empty_allowed_blocks(self):
        assert member_allows("owner", [], "active") is False


class TestAcceptResult:
    def test_acceptable(self):
        ok, reason = accept_invite_result("pending", NOW + timedelta(days=1), NOW)
        assert ok is True and reason == "ok"

    def test_expired(self):
        ok, reason = accept_invite_result("pending", NOW - timedelta(seconds=1), NOW)
        assert ok is False and "만료" in reason

    def test_already_processed(self):
        ok, reason = accept_invite_result("accepted", NOW + timedelta(days=1), NOW)
        assert ok is False and "처리" in reason
        ok2, _ = accept_invite_result("revoked", NOW + timedelta(days=1), NOW)
        assert ok2 is False
