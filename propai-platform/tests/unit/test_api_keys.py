"""API 키 관리 단위 테스트.

APIKey 모델, 스키마, 라우터 소스 코드 패턴 검증.
"""

from pathlib import Path

from apps.api.database.models.api_key import APIKey
from packages.schemas.models import APIKeyCreateRequest, APIKeyCreateResponse, APIKeyResponse

# 라우터 소스를 직접 읽음 (import 시 DB 의존성 회피)
_ROUTER_SOURCE = (
    Path(__file__).resolve().parents[2] / "apps" / "api" / "routers" / "api_keys.py"
).read_text(encoding="utf-8")

# RBAC 소스
_RBAC_SOURCE = (
    Path(__file__).resolve().parents[2] / "apps" / "api" / "auth" / "rbac.py"
).read_text(encoding="utf-8")


class TestAPIKeyModel:
    """APIKey DB 모델 구조 검증."""

    def test_tablename(self) -> None:
        """테이블명이 api_keys이다."""
        assert APIKey.__tablename__ == "api_keys"

    def test_has_key_hash_column(self) -> None:
        """key_hash 컬럼이 존재한다."""
        columns = [c.name for c in APIKey.__table__.columns]
        assert "key_hash" in columns

    def test_has_key_prefix_column(self) -> None:
        """key_prefix 컬럼이 존재한다."""
        columns = [c.name for c in APIKey.__table__.columns]
        assert "key_prefix" in columns

    def test_has_scopes_column(self) -> None:
        """scopes 컬럼이 존재한다."""
        columns = [c.name for c in APIKey.__table__.columns]
        assert "scopes" in columns

    def test_has_is_active_column(self) -> None:
        """is_active 컬럼이 존재한다."""
        columns = [c.name for c in APIKey.__table__.columns]
        assert "is_active" in columns

    def test_has_expires_at_column(self) -> None:
        """expires_at 컬럼이 존재한다."""
        columns = [c.name for c in APIKey.__table__.columns]
        assert "expires_at" in columns


class TestAPIKeySchemas:
    """API 키 스키마 검증."""

    def test_create_request_name_required(self) -> None:
        """APIKeyCreateRequest에 name이 필수이다."""
        fields = APIKeyCreateRequest.model_fields
        assert "name" in fields
        assert fields["name"].is_required()

    def test_create_request_scopes_optional(self) -> None:
        """APIKeyCreateRequest에 scopes가 선택이다."""
        req = APIKeyCreateRequest(name="test")
        assert req.scopes is None

    def test_create_response_has_key(self) -> None:
        """APIKeyCreateResponse에 key(평문) 필드가 있다."""
        fields = APIKeyCreateResponse.model_fields
        assert "key" in fields

    def test_list_response_no_key(self) -> None:
        """APIKeyResponse에 평문 key 필드가 없다."""
        fields = APIKeyResponse.model_fields
        assert "key" not in fields

    def test_list_response_has_key_prefix(self) -> None:
        """APIKeyResponse에 key_prefix 필드가 있다."""
        fields = APIKeyResponse.model_fields
        assert "key_prefix" in fields


class TestAPIKeyRouterCode:
    """API 키 라우터 코드 패턴 검증."""

    def test_sha256_used(self) -> None:
        """SHA-256 해시가 사용된다."""
        assert "sha256" in _ROUTER_SOURCE

    def test_key_prefix_stored(self) -> None:
        """key_prefix가 저장된다."""
        assert "key_prefix" in _ROUTER_SOURCE

    def test_post_endpoint(self) -> None:
        """POST 엔드포인트가 정의되어 있다."""
        assert "@router.post(" in _ROUTER_SOURCE

    def test_get_endpoint(self) -> None:
        """GET 엔드포인트가 정의되어 있다."""
        assert "@router.get(" in _ROUTER_SOURCE

    def test_delete_endpoint(self) -> None:
        """DELETE 엔드포인트가 정의되어 있다."""
        assert "@router.delete" in _ROUTER_SOURCE

    def test_204_for_delete(self) -> None:
        """DELETE는 204를 반환한다."""
        assert "HTTP_204_NO_CONTENT" in _ROUTER_SOURCE


class TestAPIKeyRBAC:
    """API 키 RBAC 정책 검증."""

    def test_admin_read_policy(self) -> None:
        """admin에 api_keys read 권한이 있다."""
        assert '("admin", "api_keys", "read")' in _RBAC_SOURCE

    def test_admin_write_policy(self) -> None:
        """admin에 api_keys write 권한이 있다."""
        assert '("admin", "api_keys", "write")' in _RBAC_SOURCE

    def test_admin_delete_policy(self) -> None:
        """admin에 api_keys delete 권한이 있다."""
        assert '("admin", "api_keys", "delete")' in _RBAC_SOURCE
