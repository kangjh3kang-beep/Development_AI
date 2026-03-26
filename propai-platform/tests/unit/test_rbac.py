"""RBAC 권한 검사 단위 테스트.

Casbin 기반 역할별 리소스/동작 권한 검증.
"""

from apps.api.auth.rbac import check_permission


class TestAdminPermissions:
    """admin 역할 권한 — 전체 접근."""

    def test_projects_read(self) -> None:
        assert check_permission("admin", "projects", "read") is True

    def test_projects_write(self) -> None:
        assert check_permission("admin", "projects", "write") is True

    def test_avm_read(self) -> None:
        assert check_permission("admin", "avm", "read") is True

    def test_blockchain_write(self) -> None:
        assert check_permission("admin", "blockchain", "write") is True


class TestManagerPermissions:
    """manager 역할 권한."""

    def test_projects_write(self) -> None:
        assert check_permission("manager", "projects", "write") is True

    def test_design_write(self) -> None:
        assert check_permission("manager", "design", "write") is True


class TestAnalystPermissions:
    """analyst 역할 권한."""

    def test_avm_read(self) -> None:
        assert check_permission("analyst", "avm", "read") is True

    def test_regulation_read(self) -> None:
        assert check_permission("analyst", "regulation", "read") is True


class TestViewerPermissions:
    """viewer 역할 권한 — 읽기 전용."""

    def test_projects_read(self) -> None:
        assert check_permission("viewer", "projects", "read") is True

    def test_projects_write_denied(self) -> None:
        assert check_permission("viewer", "projects", "write") is False

    def test_blockchain_write_denied(self) -> None:
        assert check_permission("viewer", "blockchain", "write") is False


class TestUnknownRole:
    """미정의 역할은 모든 접근 거부."""

    def test_unknown_read(self) -> None:
        assert check_permission("hacker", "projects", "read") is False

    def test_unknown_write(self) -> None:
        assert check_permission("unknown", "avm", "write") is False
