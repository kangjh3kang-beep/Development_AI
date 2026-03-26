"""Regression tests for v53 phase 5 operator shells and auth lifecycle hardening."""

from pathlib import Path

from apps.api.auth.rbac import check_permission
from packages.schemas.models import TokenResponse

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_AUTH_SOURCE = (_BASE / "apps" / "api" / "routers" / "auth.py").read_text(encoding="utf-8")
_SAFETY_SOURCE = (_BASE / "apps" / "api" / "routers" / "safety.py").read_text(encoding="utf-8")
_PARKING_SOURCE = (_BASE / "apps" / "api" / "routers" / "parking.py").read_text(encoding="utf-8")
_WEBRTC_SOURCE = (_BASE / "apps" / "api" / "routers" / "webrtc.py").read_text(encoding="utf-8")
_SRE_SOURCE = (_BASE / "apps" / "api" / "routers" / "sre.py").read_text(encoding="utf-8")


class TestV53Phase5Contracts:
    def test_token_contract_still_exposes_refresh_token(self) -> None:
        assert "refresh_token" in TokenResponse.model_fields


class TestV53Phase5Routers:
    def test_main_registers_sre_router(self) -> None:
        assert 'prefix="/api/v1/sre"' in _MAIN_SOURCE

    def test_operator_shell_endpoints_exist(self) -> None:
        assert '@router.get("/dashboard"' in _SAFETY_SOURCE
        assert '@router.get("/dashboard"' in _PARKING_SOURCE
        assert '@router.get("/transcripts"' in _WEBRTC_SOURCE
        assert '@router.get("/sessions/active"' in _WEBRTC_SOURCE
        assert '@router.get("/dashboard"' in _SRE_SOURCE

    def test_auth_lifecycle_endpoints_exist(self) -> None:
        assert '@router.post("/refresh"' in _AUTH_SOURCE
        assert '@router.post("/logout"' in _AUTH_SOURCE
        assert '@router.post("/kakao/callback"' in _AUTH_SOURCE


class TestV53Phase5Rbac:
    def test_viewer_can_read_operator_modules(self) -> None:
        assert check_permission("viewer", "safety", "read") is True
        assert check_permission("viewer", "parking", "read") is True
        assert check_permission("viewer", "webrtc", "read") is True
        assert check_permission("viewer", "sre", "read") is True

    def test_analyst_can_write_operator_modules(self) -> None:
        assert check_permission("analyst", "safety", "write") is True
        assert check_permission("analyst", "parking", "write") is True
        assert check_permission("analyst", "webrtc", "write") is True
        assert check_permission("analyst", "sre", "write") is True
