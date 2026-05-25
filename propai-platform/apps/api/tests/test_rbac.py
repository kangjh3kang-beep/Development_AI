"""RBAC 엔진 테스트."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestRole:
    """역할 열거형 테스트."""

    def test_all_roles_defined(self):
        from app.core.rbac import Role
        expected = {"admin", "manager", "developer", "user", "viewer", "auditor"}
        actual = {r.value for r in Role}
        assert actual == expected

    def test_role_is_string_enum(self):
        from app.core.rbac import Role
        assert Role.ADMIN == "admin"
        assert isinstance(Role.ADMIN, str)

    def test_role_count(self):
        from app.core.rbac import Role
        assert len(Role) == 6


class TestRBACEngine:
    """RBAC 엔진 테스트."""

    def test_admin_full_access(self):
        from app.core.rbac import RBACEngine, Role
        engine = RBACEngine()
        assert engine.check_permission(Role.ADMIN, "/api/v1/projects/1", "GET") is True
        assert engine.check_permission(Role.ADMIN, "/api/v1/projects/1", "DELETE") is True
        assert engine.check_permission(Role.ADMIN, "/api/v2/something", "POST") is True

    def test_viewer_read_only(self):
        from app.core.rbac import RBACEngine, Role
        engine = RBACEngine()
        assert engine.check_permission(Role.VIEWER, "/api/v1/projects", "GET") is True
        assert engine.check_permission(Role.VIEWER, "/api/v1/projects", "POST") is False
        assert engine.check_permission(Role.VIEWER, "/api/v1/projects", "DELETE") is False

    def test_auditor_audit_only(self):
        from app.core.rbac import RBACEngine, Role
        engine = RBACEngine()
        assert engine.check_permission(Role.AUDITOR, "/api/v1/audit/logs", "GET") is True
        assert engine.check_permission(Role.AUDITOR, "/api/v1/projects", "GET") is False

    def test_user_limited_access(self):
        from app.core.rbac import RBACEngine, Role
        engine = RBACEngine()
        assert engine.check_permission(Role.USER, "/api/v1/avm/estimate", "POST") is True
        assert engine.check_permission(Role.USER, "/api/v1/avm/estimate", "DELETE") is False

    def test_manager_project_access(self):
        from app.core.rbac import RBACEngine, Role
        engine = RBACEngine()
        assert engine.check_permission(Role.MANAGER, "/api/v1/projects/123", "DELETE") is True
        assert engine.check_permission(Role.MANAGER, "/api/v1/agents/run", "POST") is True

    def test_developer_broad_read_write(self):
        from app.core.rbac import RBACEngine, Role
        engine = RBACEngine()
        assert engine.check_permission(Role.DEVELOPER, "/api/v1/test", "GET") is True
        assert engine.check_permission(Role.DEVELOPER, "/api/v1/test", "POST") is True
        assert engine.check_permission(Role.DEVELOPER, "/api/v1/test", "DELETE") is False

    def test_get_allowed_methods(self):
        from app.core.rbac import RBACEngine, Role
        engine = RBACEngine()
        methods = engine.get_allowed_methods(Role.VIEWER, "/api/v1/projects")
        assert "GET" in methods
        assert "POST" not in methods

    def test_list_accessible_paths(self):
        from app.core.rbac import RBACEngine, Role
        engine = RBACEngine()
        paths = engine.list_accessible_paths(Role.ADMIN)
        assert len(paths) >= 1

    def test_unknown_path_denied(self):
        from app.core.rbac import RBACEngine, Role
        engine = RBACEngine()
        assert engine.check_permission(Role.AUDITOR, "/secret/path", "GET") is False

    def test_custom_policy(self):
        from app.core.rbac import RBACEngine, Role
        custom = {Role.USER: {"/custom/*": {"GET", "POST"}}}
        engine = RBACEngine(policies=custom)
        assert engine.check_permission(Role.USER, "/custom/endpoint", "GET") is True
        assert engine.check_permission(Role.ADMIN, "/api/v1/test", "GET") is False


class TestRequireRole:
    """require_role 의존성 테스트."""

    def test_require_role_no_request(self):
        from app.core.rbac import require_role, Role
        dep = require_role(Role.ADMIN)
        result = dep(request=None)
        assert result is True

    def test_get_rbac_engine(self):
        from app.core.rbac import get_rbac_engine, RBACEngine
        engine = get_rbac_engine()
        assert isinstance(engine, RBACEngine)
