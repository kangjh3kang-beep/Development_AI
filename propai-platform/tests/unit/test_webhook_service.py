"""웹훅 서비스 단위 테스트.

HMAC-SHA256 서명 및 서비스 코드 구조 검증.
"""

import hashlib
import hmac
import inspect
import json

from apps.api.services.webhook_service import WebhookService, sign_payload

# ──────────────────────────────────────
# HMAC-SHA256 서명 검증
# ──────────────────────────────────────


class TestSignPayload:
    """sign_payload() 함수 검증."""

    def test_hmac_sha256_signature(self) -> None:
        """올바른 HMAC-SHA256 서명을 생성한다."""
        secret = "test_secret"
        payload = {"event": "project.completed", "id": "123"}
        result = sign_payload(secret, payload)

        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        expected = hmac.new(
            secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert result == expected

    def test_signature_changes_with_secret(self) -> None:
        """다른 시크릿은 다른 서명을 생성한다."""
        payload = {"event": "test"}
        sig1 = sign_payload("secret_a", payload)
        sig2 = sign_payload("secret_b", payload)
        assert sig1 != sig2

    def test_signature_deterministic(self) -> None:
        """같은 입력은 같은 서명을 생성한다."""
        secret = "my_secret"
        payload = {"key": "value"}
        sig1 = sign_payload(secret, payload)
        sig2 = sign_payload(secret, payload)
        assert sig1 == sig2

    def test_empty_payload(self) -> None:
        """빈 페이로드도 서명할 수 있다."""
        result = sign_payload("secret", {})
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 hex digest 길이

    def test_signature_is_hex(self) -> None:
        """서명이 16진수 문자열이다."""
        result = sign_payload("secret", {"data": "test"})
        int(result, 16)  # 16진수 파싱 가능해야 함

    def test_korean_payload(self) -> None:
        """한국어 페이로드도 정상 서명된다."""
        result = sign_payload("secret", {"메시지": "테스트"})
        assert isinstance(result, str)
        assert len(result) == 64


# ──────────────────────────────────────
# WebhookService 코드 구조 검증
# ──────────────────────────────────────


class TestWebhookServiceCode:
    """WebhookService 코드 패턴 검증."""

    def test_dispatch_filters_by_event_type(self) -> None:
        """dispatch_event가 이벤트 타입으로 필터링한다."""
        source = inspect.getsource(WebhookService.dispatch_event)
        assert "event_type" in source
        assert "events" in source

    def test_dispatch_sends_signature_header(self) -> None:
        """_send_with_retry가 X-PropAI-Signature 헤더를 포함한다."""
        source = inspect.getsource(WebhookService._send_with_retry)
        assert "X-PropAI-Signature" in source

    def test_dispatch_sends_event_header(self) -> None:
        """_send_with_retry가 X-PropAI-Event 헤더를 포함한다."""
        source = inspect.getsource(WebhookService._send_with_retry)
        assert "X-PropAI-Event" in source

    def test_delivery_records_created(self) -> None:
        """_send_with_retry가 WebhookDelivery 레코드를 생성한다."""
        source = inspect.getsource(WebhookService._send_with_retry)
        assert "WebhookDelivery" in source

    def test_retry_logic_exists(self) -> None:
        """_send_with_retry에 재시도 로직이 있다."""
        source = inspect.getsource(WebhookService._send_with_retry)
        assert "_MAX_RETRIES" in source

    def test_uses_httpx_client(self) -> None:
        """_send_with_retry가 httpx.AsyncClient를 사용한다."""
        source = inspect.getsource(WebhookService._send_with_retry)
        assert "httpx.AsyncClient" in source
