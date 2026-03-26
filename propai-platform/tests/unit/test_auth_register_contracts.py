"""Unit checks for the auth registration contract."""

from pathlib import Path

from apps.api.routers.auth import _slugify_tenant_name

_AUTH_SOURCE = (
    Path(__file__).resolve().parents[2] / "apps" / "api" / "routers" / "auth.py"
).read_text(encoding="utf-8")


class TestAuthRegisterContracts:
    def test_register_endpoint_exists(self) -> None:
        assert '@router.post("/register"' in _AUTH_SOURCE

    def test_register_creates_tenant_slug_helper(self) -> None:
        assert "_build_unique_tenant_slug" in _AUTH_SOURCE

    def test_slugify_tenant_name_normalizes_text(self) -> None:
        assert _slugify_tenant_name("PropAI Holdings Inc.") == "propai-holdings-inc"

    def test_slugify_tenant_name_falls_back_when_empty(self) -> None:
        assert _slugify_tenant_name("!!!") == "tenant"
