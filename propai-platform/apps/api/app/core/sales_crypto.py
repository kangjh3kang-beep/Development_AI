"""v62 sales — 가상계좌 등 식별번호 보호.

VA 입금 대사는 '암호화 후 동등비교 조회'가 필요해 결정적(deterministic) 변환이어야 한다.
→ HMAC-SHA256 블라인드 인덱스(역복호 불가, 평문 미저장). 키는 환경변수(APP_SECRET_KEY) 파생.
"""

import hashlib
import hmac
import os


def _key() -> bytes:
    k = os.getenv("SALES_ENC_KEY") or os.getenv("APP_SECRET_KEY") or "propai-dev-sales-key"
    return k.encode()


def encrypt(value: str) -> str:
    """결정적 블라인드 인덱스(조회/대사용). 동일 입력 → 동일 출력."""
    if value is None:
        return ""
    return hmac.new(_key(), str(value).encode(), hashlib.sha256).hexdigest()


def decrypt(_value: str) -> None:
    """역복호 미지원(평문 미저장). 표시용 마스킹은 호출측에서 별도 보관 필드 사용."""
    return None
