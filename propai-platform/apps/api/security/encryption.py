"""AES-256-GCM 암호화 서비스.

민감 데이터(API 키, 개인정보 등)를 암호화/복호화한다.
nonce는 매번 랜덤 생성되어 동일 평문도 다른 암호문을 생성한다.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptionService:
    """AES-256-GCM 기반 암복호화 서비스."""

    def __init__(self, key_hex: str) -> None:
        """32바이트(256비트) 16진수 키로 초기화한다."""
        self._key = bytes.fromhex(key_hex)
        if len(self._key) != 32:
            msg = "AES-256에는 32바이트(64자 hex) 키가 필요합니다"
            raise ValueError(msg)

    def encrypt(self, plaintext: str) -> str:
        """평문을 암호화하여 URL-safe base64 문자열로 반환한다."""
        nonce = os.urandom(12)
        ct = AESGCM(self._key).encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ct).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """암호문을 복호화하여 원본 문자열로 반환한다."""
        data = base64.urlsafe_b64decode(ciphertext)
        nonce, ct = data[:12], data[12:]
        return AESGCM(self._key).decrypt(nonce, ct, None).decode("utf-8")
