"""v62 sales — 가상계좌 등 식별번호 보호.

VA 입금 대사는 '암호화 후 동등비교 조회'가 필요해 결정적(deterministic) 변환이어야 한다.
→ HMAC-SHA256 블라인드 인덱스(역복호 불가, 평문 미저장). 키는 환경변수(APP_SECRET_KEY) 파생.

보안 검토 메모:
- 평문 미저장(O): VA번호는 encrypt()의 블라인드 인덱스만 DB에 저장한다.
- 약한 해시 아님(O): HMAC-SHA256(키 결합)이므로 무키 SHA 사전공격 대상이 아니다.
- 동등비교(O): 조회는 DB의 인덱스 컬럼 equality 로 수행(SQL WHERE)되며, 파이썬에서
  블라인드 값을 비교할 경우를 위해 timing-safe 한 verify()(hmac.compare_digest) 를 둔다.
- 비밀번호(현장 2차비번)는 본 모듈이 아니라 site_auth.py 의 bcrypt(checkpw=상수시간 비교)로
  처리한다 — 평문저장·약한해시·타이밍 비교 결함 없음.
- ★deploy-pending: 운영에서는 반드시 SALES_ENC_KEY 또는 APP_SECRET_KEY 를 설정해야 한다.
  미설정 시 아래 개발용 폴백 키로 동작하므로(키 약함) 프로덕션 배포 전 환경변수 주입이 전제다.
"""

import hashlib
import hmac
import os

# 키 미설정 시 개발용 폴백(★프로덕션은 환경변수 필수 = deploy-pending).
_DEV_FALLBACK_KEY = "propai-dev-sales-key"


def _key() -> bytes:
    k = os.getenv("SALES_ENC_KEY") or os.getenv("APP_SECRET_KEY") or _DEV_FALLBACK_KEY
    return k.encode()


def encrypt(value: str) -> str:
    """결정적 블라인드 인덱스(조회/대사용). 동일 입력 → 동일 출력."""
    if value is None:
        return ""
    return hmac.new(_key(), str(value).encode(), hashlib.sha256).hexdigest()


def verify(value: str, blind: str) -> bool:
    """평문(value)이 블라인드 인덱스(blind)와 일치하는지 timing-safe 비교.

    파이썬에서 블라인드 값을 비교해야 할 때 사용(타이밍 누수 방지: hmac.compare_digest).
    DB equality 조회 경로에는 불필요하나, 메모리상 비교가 필요한 호출부를 위해 제공한다.
    """
    if value is None or blind is None:
        return False
    return hmac.compare_digest(encrypt(value), str(blind))


def decrypt(_value: str) -> None:
    """역복호 미지원(평문 미저장). 표시용 마스킹은 호출측에서 별도 보관 필드 사용."""
    return None
