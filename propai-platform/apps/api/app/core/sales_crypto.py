"""v62 sales — 가상계좌 등 식별번호 보호.

VA 입금 대사는 '암호화 후 동등비교 조회'가 필요해 결정적(deterministic) 변환이어야 한다.
→ HMAC-SHA256 블라인드 인덱스(역복호 불가, 평문 미저장). 키는 환경변수(APP_SECRET_KEY) 파생.

보안 검토 메모:
- 평문 미저장(O): VA번호는 encrypt()의 블라인드 인덱스만 DB에 저장한다.
- 약한 해시 아님(O): HMAC-SHA256(키 결합)이므로 무키 SHA 사전공격 대상이 아니다.
- 동등비교(O): 입금 대사 조회는 DB 인덱스 컬럼 equality 로 수행(payment/service.py 의
  `va_number_enc == encrypt(va_number)` SQL WHERE). 결정적 변환이라 동일 입력→동일 블라인드
  이므로 SQL equality 만으로 안전하게 매칭된다. 파이썬 메모리상 블라인드 비교 경로는 현재
  없다(YAGNI: 미배선 timing-safe verify 헬퍼는 제거 — 호출부 0건이었음).
- 비밀번호(현장 2차비번)는 본 모듈이 아니라 site_auth.py 의 bcrypt(checkpw=상수시간 비교)로
  처리한다 — 평문저장·약한해시·타이밍 비교 결함 없음.
- ★키 강제: 프로덕션(APP_ENV≠development/test)에서는 SALES_ENC_KEY 또는 APP_SECRET_KEY 가
  반드시 필요하다. 미설정 시 _key() 가 예외로 차단한다(약한 폴백키 silent 사용 방지).
  dev/test 한정으로만 폴백키를 명시 경고와 함께 사용한다.
"""

import hashlib
import hmac
import os
import warnings

# 키 미설정 시 개발용 폴백(★프로덕션은 환경변수 필수). dev/test 외 환경에서 폴백이
# silent 하게 쓰이면 약한 키로 VA 블라인드 인덱스가 생성되므로, 프로덕션에서는 예외로
# 막는다(config.py 의 _validate_secret 차단 방식과 동일 정신).
_DEV_FALLBACK_KEY = "propai-dev-sales-key"

# 폴백키 경고는 프로세스당 1회만(매 encrypt 호출마다 경고 스팸 방지).
_FALLBACK_WARNED = False


def _is_production() -> bool:
    """dev/test 가 아닌 환경이면 프로덕션으로 본다(config.APP_ENV 기준과 동일 판정)."""
    return (os.getenv("APP_ENV") or "development").lower() not in ("development", "test")


def _key() -> bytes:
    """VA 블라인드 인덱스용 HMAC 키. SALES_ENC_KEY → APP_SECRET_KEY → (dev 한정)폴백 순.

    ★프로덕션(APP_ENV≠development/test)에서 두 키가 모두 미설정이면 예외로 차단한다.
    silent 폴백키 사용 시 약한 키로 식별번호 블라인드 인덱스가 만들어져 보안 결함이 되므로,
    배포 전 환경변수 주입을 강제한다(fail-fast, 0/빈값 은폐 금지).
    """
    global _FALLBACK_WARNED
    k = os.getenv("SALES_ENC_KEY") or os.getenv("APP_SECRET_KEY")
    if not k:
        if _is_production():
            raise RuntimeError(
                "SALES_ENC_KEY(또는 APP_SECRET_KEY) 미설정 — 프로덕션에서 가상계좌 암호화 "
                "폴백키 사용은 차단됩니다. 운영 배포 전 강한 키를 환경변수로 주입하세요."
            )
        # dev/test 한정: 폴백키 사용을 명시 경고(silent 금지, 프로세스당 1회).
        if not _FALLBACK_WARNED:
            warnings.warn(
                "SALES_ENC_KEY/APP_SECRET_KEY 미설정 — 개발용 폴백키 사용(프로덕션 금지)",
                stacklevel=2,
            )
            _FALLBACK_WARNED = True
        k = _DEV_FALLBACK_KEY
    return k.encode()


def encrypt(value: str) -> str:
    """결정적 블라인드 인덱스(조회/대사용). 동일 입력 → 동일 출력."""
    if value is None:
        return ""
    return hmac.new(_key(), str(value).encode(), hashlib.sha256).hexdigest()


def decrypt(_value: str) -> None:
    """역복호 미지원(평문 미저장). 표시용 마스킹은 호출측에서 별도 보관 필드 사용."""
    return None
