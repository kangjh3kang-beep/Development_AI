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
- ★프로덕션 키 검증은 config._validate_secret 을 '직접 재사용'한다(드리프트 0). 과거에는
  길이(≥32)만 복제하고 유출/예제 시크릿 denylist(config._KNOWN_WEAK_SECRETS)는 복제하지
  않아, 유출 예제키 'propai_secret_key_change_in_production_32chars_min'(50자)가 config 에선
  거부되는데 _key() 에선 통과하는 불일치가 있었다. 이제 동일 함수를 호출하므로 denylist·
  길이 검사가 완전히 일치한다.
- ★config 보호 우회 금지: 핵심 결함은 '읽는 위치'가 아니라 _key() 가 config 의 prod 검증
  (denylist+길이)을 거치지 않고 키를 ACCEPT 하던 점이었다. 이제 어느 env 에서 읽든 프로덕션
  에서는 config._validate_secret 으로 동일 검사하므로 config 가 거부하는 키는 _key() 도 거부
  한다(우회 경로 제거).
"""

import hashlib
import hmac
import os
import warnings

from app.core.config import _validate_secret

# 키 미설정 시 개발용 폴백(★프로덕션은 환경변수 필수). dev/test 외 환경에서 폴백이
# silent 하게 쓰이면 약한 키로 VA 블라인드 인덱스가 생성되므로, 프로덕션에서는 예외로
# 막는다(config.py 의 _validate_secret 차단 방식과 동일 정신).
_DEV_FALLBACK_KEY = "propai-dev-sales-key"

# 프로덕션 키 길이 하한(config._validate_secret 와 동일=32자). 짧은 키(예: 'x' 1자)는
# 무차별 추측에 취약해 약한 폴백키와 다를 바 없으므로, 직접 경로에도 동일 하한을 강제한다.
# ★주의: 실제 prod 검증은 _validate_secret 을 '직접 호출'한다(길이+denylist 동시). 이 상수는
#   하위호환(테스트 노출)·문서용으로만 남긴다.
_MIN_KEY_LEN = 32

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

    ★키 강도 검증 = config._validate_secret '직접 재사용'(드리프트 0): 과거 'len<32' 만
    복제하면 유출 예제키(50자)가 길이는 통과해 config 가 거부하는 키를 _key() 가 ACCEPT 했다.
    이제 동일 함수로 denylist(_KNOWN_WEAK_SECRETS)+길이(≥32)를 함께 검사하므로 일치한다.

    ★config 보호 우회 금지(검증 일원화): 핵심 결함은 '어디서 읽느냐'가 아니라 _key() 가
    config 의 prod 검증(denylist+길이)을 거치지 않고 키를 ACCEPT 하던 점이었다. 그래서 키
    소스는 런타임 env(테스트·재설정이 즉시 반영)를 그대로 쓰되, 선택된 키를 프로덕션에서
    아래 _validate_secret 으로 config 와 '동일하게' 검사한다 → config 가 거부하는 키(유출
    예제키 50자 등)는 _key() 도 반드시 거부한다(우회 불가).
    """
    global _FALLBACK_WARNED
    # 키 소스: SALES_ENC_KEY(전용) → APP_SECRET_KEY. 둘 다 비면 k=빈문자열 → 아래 폴백 분기.
    # (os.getenv 로 런타임 최신값을 읽되, prod 검증은 _validate_secret 으로 config 와 일치.)
    k = os.getenv("SALES_ENC_KEY") or os.getenv("APP_SECRET_KEY") or ""
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
    elif _is_production():
        # 키는 있으나 약할 수 있음(짧음 또는 유출/예제 denylist). 프로덕션에서는 config 와
        # '동일 함수'로 검사해 약한 폴백키와 동일하게 차단한다(길이+denylist 일치 보장).
        # _validate_secret 은 빈값/denylist/len<32 에 RuntimeError 를 던진다.
        _validate_secret("SALES_ENC_KEY(또는 APP_SECRET_KEY)", k)
    return k.encode()


def encrypt(value: str) -> str:
    """결정적 블라인드 인덱스(조회/대사용). 동일 입력 → 동일 출력."""
    if value is None:
        return ""
    return hmac.new(_key(), str(value).encode(), hashlib.sha256).hexdigest()


def decrypt(_value: str) -> None:
    """역복호 미지원(평문 미저장). 표시용 마스킹은 호출측에서 별도 보관 필드 사용."""
    return None
