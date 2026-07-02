"""CSRF 보호 — Double Submit Cookie 패턴.

토큰 생성, 쿠키 설정, 요청 검증을 제공한다.
"""

import hashlib
import hmac
import secrets
import time


class CSRFProtection:
    """Double Submit Cookie 패턴 CSRF 보호."""

    TOKEN_LENGTH = 32
    COOKIE_NAME = "csrf_token"
    HEADER_NAME = "x-csrf-token"
    MAX_AGE_SEC = 3600  # 1시간

    def __init__(self, secret_key: str | None = None):
        if secret_key is None:
            from app.core.config import settings
            secret_key = settings.APP_SECRET_KEY
        self._secret_key = secret_key.encode()

    def generate_token(self) -> str:
        """CSRF 토큰 생성."""
        raw = secrets.token_hex(self.TOKEN_LENGTH)
        timestamp = str(int(time.time()))
        signature = self._sign(raw + timestamp)
        return f"{raw}.{timestamp}.{signature}"

    def validate_token(self, token: str) -> bool:
        """CSRF 토큰 유효성 검증."""
        parts = token.split(".")
        if len(parts) != 3:
            return False

        raw, timestamp_str, signature = parts

        # 서명 검증
        expected_sig = self._sign(raw + timestamp_str)
        if not hmac.compare_digest(signature, expected_sig):
            return False

        # 만료 검증
        try:
            created = int(timestamp_str)
        except ValueError:
            return False
        return not time.time() - created > self.MAX_AGE_SEC

    def validate_double_submit(self, cookie_token: str | None,
                                header_token: str | None) -> bool:
        """Double Submit Cookie 검증.

        쿠키와 헤더의 토큰이 일치하고 유효해야 통과.
        """
        if not cookie_token or not header_token:
            return False
        if cookie_token != header_token:
            return False
        return self.validate_token(cookie_token)

    def _sign(self, data: str) -> str:
        """HMAC-SHA256 서명."""
        return hmac.new(
            self._secret_key,
            data.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]

    @property
    def cookie_config(self) -> dict:
        """쿠키 설정 딕셔너리."""
        return {
            "key": self.COOKIE_NAME,
            "httponly": False,  # JS에서 읽어야 하므로
            "samesite": "strict",
            "secure": True,
            "max_age": self.MAX_AGE_SEC,
        }


_csrf = CSRFProtection()


def get_csrf_protection() -> CSRFProtection:
    """전역 CSRFProtection 반환."""
    return _csrf
