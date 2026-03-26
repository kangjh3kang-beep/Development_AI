"""Notifications and e-sign regression tests."""

from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.database.models.esign_request import ESignRequest
from apps.api.database.models.notification_message import NotificationMessage
from packages.schemas.models import AlimTalkRequest, ESignCreateRequest, ESignResponse, NotificationResponse

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_NOTIFICATIONS_SOURCE = (_BASE / "apps" / "api" / "routers" / "notifications.py").read_text(encoding="utf-8")
_ESIGN_SOURCE = (_BASE / "apps" / "api" / "routers" / "esign.py").read_text(encoding="utf-8")


class TestNotificationMessageModel:
    def test_tablename(self) -> None:
        assert NotificationMessage.__tablename__ == "notification_messages"

    def test_required_columns(self) -> None:
        columns = {column.name for column in NotificationMessage.__table__.columns}
        expected = {
            "id",
            "tenant_id",
            "project_id",
            "channel",
            "recipient_phone",
            "template_code",
            "message",
            "payload_json",
            "status",
            "external_ref",
            "sent_at",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)


class TestESignRequestModel:
    def test_tablename(self) -> None:
        assert ESignRequest.__tablename__ == "esign_requests"

    def test_required_columns(self) -> None:
        columns = {column.name for column in ESignRequest.__table__.columns}
        expected = {
            "id",
            "tenant_id",
            "project_id",
            "document_name",
            "document_url",
            "signer_name",
            "signer_email",
            "signer_phone",
            "provider",
            "status",
            "external_request_id",
            "requested_at",
            "completed_at",
            "metadata_json",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)


class TestNotificationAndESignSchemas:
    def test_alimtalk_request_fields(self) -> None:
        fields = AlimTalkRequest.model_fields
        assert "recipient_phone" in fields
        assert "template_code" in fields
        assert "message" in fields

    def test_notification_response_fields(self) -> None:
        fields = NotificationResponse.model_fields
        assert "channel" in fields
        assert "status" in fields
        assert "sent_at" in fields

    def test_esign_create_request_fields(self) -> None:
        fields = ESignCreateRequest.model_fields
        assert "document_name" in fields
        assert "document_url" in fields
        assert "signer_email" in fields

    def test_esign_response_fields(self) -> None:
        fields = ESignResponse.model_fields
        assert "provider" in fields
        assert "status" in fields
        assert "requested_at" in fields


class TestNotificationAndESignRouters:
    def test_notifications_router_registered(self) -> None:
        assert 'prefix="/api/v1/notifications"' in _MAIN_SOURCE

    def test_esign_router_registered(self) -> None:
        assert 'prefix="/api/v1/esign"' in _MAIN_SOURCE

    def test_alimtalk_endpoint_exists(self) -> None:
        assert '@router.post("/alimtalk"' in _NOTIFICATIONS_SOURCE

    def test_esign_request_endpoint_exists(self) -> None:
        assert '@router.post("/request"' in _ESIGN_SOURCE

    def test_esign_status_endpoint_exists(self) -> None:
        assert '@router.get("/{request_id}/status"' in _ESIGN_SOURCE


class TestNotificationAndESignRBAC:
    def test_manager_can_send_notifications(self) -> None:
        assert check_permission("manager", "notifications", "write") is True

    def test_analyst_cannot_send_notifications(self) -> None:
        assert check_permission("analyst", "notifications", "write") is False

    def test_analyst_can_read_esign(self) -> None:
        assert check_permission("analyst", "esign", "read") is True

    def test_viewer_cannot_read_esign(self) -> None:
        assert check_permission("viewer", "esign", "read") is False
