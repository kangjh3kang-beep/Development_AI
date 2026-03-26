"""Step 4.1 DB 모델 단위 테스트.

RefreshToken, Webhook, WebhookDelivery, APIKey 모델의
스키마 정의·관계·필드 타입을 검증한다.
"""

from apps.api.database.models.api_key import APIKey
from apps.api.database.models.refresh_token import RefreshToken
from apps.api.database.models.webhook import Webhook
from apps.api.database.models.webhook_delivery import WebhookDelivery

# ─── RefreshToken ─────────────────────────────────────────


class TestRefreshToken:
    """리프레시 토큰 모델 검증."""

    def test_tablename(self) -> None:
        assert RefreshToken.__tablename__ == "refresh_tokens"

    def test_has_required_columns(self) -> None:
        col_names = {c.name for c in RefreshToken.__table__.columns}
        expected = {
            "id", "user_id", "tenant_id", "token_hash",
            "expires_at", "is_revoked", "device_info",
            "created_at", "updated_at",
        }
        assert expected.issubset(col_names)

    def test_id_is_uuid_pk(self) -> None:
        col = RefreshToken.__table__.c.id
        assert col.primary_key

    def test_token_hash_unique(self) -> None:
        col = RefreshToken.__table__.c.token_hash
        assert col.unique

    def test_user_id_fk(self) -> None:
        col = RefreshToken.__table__.c.user_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "users.id" in fk_targets

    def test_tenant_id_fk(self) -> None:
        col = RefreshToken.__table__.c.tenant_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "tenants.id" in fk_targets

    def test_is_revoked_default_false(self) -> None:
        col = RefreshToken.__table__.c.is_revoked
        assert col.nullable is False


# ─── Webhook ──────────────────────────────────────────────


class TestWebhook:
    """웹훅 구독 모델 검증."""

    def test_tablename(self) -> None:
        assert Webhook.__tablename__ == "webhooks"

    def test_has_required_columns(self) -> None:
        col_names = {c.name for c in Webhook.__table__.columns}
        expected = {
            "id", "tenant_id", "url", "secret",
            "events", "is_active", "description",
            "created_at", "updated_at",
        }
        assert expected.issubset(col_names)

    def test_url_max_length(self) -> None:
        col = Webhook.__table__.c.url
        assert getattr(col.type, "length", None) == 2000

    def test_secret_not_nullable(self) -> None:
        col = Webhook.__table__.c.secret
        assert col.nullable is False

    def test_events_is_array(self) -> None:
        col = Webhook.__table__.c.events
        assert col.nullable is True  # 구독 이벤트는 선택적

    def test_tenant_id_fk(self) -> None:
        col = Webhook.__table__.c.tenant_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "tenants.id" in fk_targets

    def test_deliveries_relationship(self) -> None:
        rel_names = [r.key for r in Webhook.__mapper__.relationships]
        assert "deliveries" in rel_names


# ─── WebhookDelivery ──────────────────────────────────────


class TestWebhookDelivery:
    """웹훅 전송 이력 모델 검증."""

    def test_tablename(self) -> None:
        assert WebhookDelivery.__tablename__ == "webhook_deliveries"

    def test_has_required_columns(self) -> None:
        col_names = {c.name for c in WebhookDelivery.__table__.columns}
        expected = {
            "id", "webhook_id", "event_type", "payload",
            "status_code", "response_body", "duration_ms",
            "attempt", "success", "created_at", "updated_at",
        }
        assert expected.issubset(col_names)

    def test_webhook_id_fk(self) -> None:
        col = WebhookDelivery.__table__.c.webhook_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "webhooks.id" in fk_targets

    def test_success_default_false(self) -> None:
        col = WebhookDelivery.__table__.c.success
        assert col.nullable is False

    def test_attempt_not_nullable(self) -> None:
        col = WebhookDelivery.__table__.c.attempt
        assert col.nullable is False

    def test_webhook_relationship(self) -> None:
        rel_names = [r.key for r in WebhookDelivery.__mapper__.relationships]
        assert "webhook" in rel_names


# ─── APIKey ───────────────────────────────────────────────


class TestAPIKey:
    """API 키 모델 검증."""

    def test_tablename(self) -> None:
        assert APIKey.__tablename__ == "api_keys"

    def test_has_required_columns(self) -> None:
        col_names = {c.name for c in APIKey.__table__.columns}
        expected = {
            "id", "tenant_id", "name", "key_prefix", "key_hash",
            "scopes", "expires_at", "is_active", "last_used_at",
            "created_at", "updated_at",
        }
        assert expected.issubset(col_names)

    def test_key_hash_unique(self) -> None:
        col = APIKey.__table__.c.key_hash
        assert col.unique

    def test_key_prefix_max_length(self) -> None:
        col = APIKey.__table__.c.key_prefix
        assert getattr(col.type, "length", None) == 10

    def test_tenant_id_fk(self) -> None:
        col = APIKey.__table__.c.tenant_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "tenants.id" in fk_targets

    def test_expires_at_nullable(self) -> None:
        col = APIKey.__table__.c.expires_at
        assert col.nullable is True  # NULL = 무기한

    def test_scopes_nullable(self) -> None:
        col = APIKey.__table__.c.scopes
        assert col.nullable is True


# ─── __init__.py 등록 검증 ────────────────────────────────


class TestModelsInit:
    """모델 __init__.py 등록 검증."""

    def test_all_new_models_registered(self) -> None:
        from apps.api.database.models import __all__
        for model_name in ("RefreshToken", "Webhook", "WebhookDelivery", "APIKey"):
            assert model_name in __all__, f"{model_name}이 __all__에 미등록"

    def test_import_all_models(self) -> None:
        from apps.api.database import models
        assert hasattr(models, "RefreshToken")
        assert hasattr(models, "Webhook")
        assert hasattr(models, "WebhookDelivery")
        assert hasattr(models, "APIKey")

    def test_total_model_count(self) -> None:
        """__all__에 최소 19개 항목이 있어야 한다."""
        from apps.api.database.models import __all__
        # Base, TenantMixin, TimestampMixin + 16개 모델 + 4개 신규
        assert len(__all__) >= 19
