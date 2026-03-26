"""AES-256-GCM 암호화 서비스 단위 테스트.

encrypt/decrypt 라운드트립, 키 불일치, 한국어 데이터 검증.
"""

import pytest

from apps.api.security.encryption import EncryptionService

# 테스트용 256비트(32바이트) 키 (64자 hex)
_TEST_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
_OTHER_KEY = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"


class TestEncryptDecrypt:
    """encrypt/decrypt 라운드트립 검증."""

    def test_roundtrip(self) -> None:
        """암호화 후 복호화하면 원본이 복원된다."""
        svc = EncryptionService(_TEST_KEY)
        plaintext = "Hello, PropAI!"
        encrypted = svc.encrypt(plaintext)
        decrypted = svc.decrypt(encrypted)
        assert decrypted == plaintext

    def test_korean_text(self) -> None:
        """한국어 데이터를 정상 암복호화한다."""
        svc = EncryptionService(_TEST_KEY)
        plaintext = "부동산 개발 전주기 AI 자동화 플랫폼"
        encrypted = svc.encrypt(plaintext)
        decrypted = svc.decrypt(encrypted)
        assert decrypted == plaintext

    def test_empty_string(self) -> None:
        """빈 문자열을 암복호화한다."""
        svc = EncryptionService(_TEST_KEY)
        encrypted = svc.encrypt("")
        decrypted = svc.decrypt(encrypted)
        assert decrypted == ""

    def test_nonce_uniqueness(self) -> None:
        """동일 평문도 매번 다른 암호문을 생성한다."""
        svc = EncryptionService(_TEST_KEY)
        plaintext = "same text"
        ct1 = svc.encrypt(plaintext)
        ct2 = svc.encrypt(plaintext)
        assert ct1 != ct2

    def test_different_key_fails(self) -> None:
        """다른 키로 복호화하면 실패한다."""
        svc1 = EncryptionService(_TEST_KEY)
        svc2 = EncryptionService(_OTHER_KEY)
        encrypted = svc1.encrypt("secret data")
        with pytest.raises(Exception):  # noqa: B017
            svc2.decrypt(encrypted)

    def test_encrypted_is_url_safe_base64(self) -> None:
        """암호문이 URL-safe base64 형식이다."""
        svc = EncryptionService(_TEST_KEY)
        encrypted = svc.encrypt("test")
        # URL-safe base64에는 +, / 가 없음
        assert "+" not in encrypted
        assert "/" not in encrypted.rstrip("=")

    def test_invalid_key_length_raises(self) -> None:
        """32바이트가 아닌 키로 초기화하면 ValueError를 발생시킨다."""
        with pytest.raises(ValueError, match="32바이트"):
            EncryptionService("abcdef")
