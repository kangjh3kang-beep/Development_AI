"""WebhookService 단위 테스트.

HMAC-SHA256 서명, 페이로드 직렬화 등 순수 로직을 검증한다.
"""

import hashlib
import hmac
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.webhook_service import sign_payload


class TestSignPayload:
    """HMAC-SHA256 서명 함수 테스트."""

    def test_기본_서명_생성(self):
        """시크릿 + 페이로드 → HMAC-SHA256 hex 문자열."""
        signature = sign_payload("my-secret", {"event": "test"})
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex 길이

    def test_동일_입력_동일_서명(self):
        """같은 시크릿 + 같은 페이로드 → 같은 서명."""
        sig1 = sign_payload("secret", {"a": 1, "b": 2})
        sig2 = sign_payload("secret", {"a": 1, "b": 2})
        assert sig1 == sig2

    def test_다른_시크릿_다른_서명(self):
        sig1 = sign_payload("secret-1", {"event": "test"})
        sig2 = sign_payload("secret-2", {"event": "test"})
        assert sig1 != sig2

    def test_다른_페이로드_다른_서명(self):
        sig1 = sign_payload("secret", {"event": "a"})
        sig2 = sign_payload("secret", {"event": "b"})
        assert sig1 != sig2

    def test_키_순서_정렬_보장(self):
        """sort_keys=True이므로 키 순서 무관하게 동일 서명."""
        sig1 = sign_payload("secret", {"b": 2, "a": 1})
        sig2 = sign_payload("secret", {"a": 1, "b": 2})
        assert sig1 == sig2

    def test_수동_검증(self):
        """수동으로 HMAC을 계산하여 서명과 대조."""
        secret = "test-key"
        payload = {"type": "escrow.created", "id": "123"}
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        expected = hmac.new(
            secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert sign_payload(secret, payload) == expected

    def test_한국어_페이로드(self):
        """한국어가 포함된 페이로드도 정상 서명."""
        signature = sign_payload("secret", {"프로젝트": "테스트", "금액": 1000})
        assert len(signature) == 64

    def test_빈_페이로드(self):
        signature = sign_payload("secret", {})
        assert len(signature) == 64


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
