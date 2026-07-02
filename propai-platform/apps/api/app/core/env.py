"""환경 판별 SSOT(단일 진실원천) — fail-secure.

왜 이 모듈이 필요한가(전역 전파방지 공용화):
- 런타임 권위 소스는 ``ENVIRONMENT``(apps.api.config, main.py 기동 기준)인데, 여러 보안
  게이트가 각자 ``app/core/config.APP_ENV`` 나 국소 ``os.getenv('APP_ENV')`` 를 읽어왔다.
- 배포 관례상 ``ENVIRONMENT=production`` 만 설정하고 ``APP_ENV`` 는 .env 의 development 로
  남기는 일이 흔해, 한쪽만 보는 게이트는 '프로덕션을 개발로 오판'해 보안을 우회했다.
- 그래서 '가능한 모든 소스를 모아 하나라도 dev/test 가 아니면 프로덕션으로 본다'(안전측
  차단)는 판정을 한 곳에 모은다. 각 보안게이트는 이 함수만 부르면 된다(고치면 전역이 따라옴).

M1 정답 기준선(``secret_store.enforce_master_key_guard`` 의 os.getenv 병합 로직)과 동일 계약.
순수 함수 · 부작용 없음.

★재귀 금지: 여기서 ``app/core/config.get_settings()`` 를 절대 import/호출하지 말 것.
  config.py 의 get_settings() 가 내부에서 이 헬퍼(is_production)를 부르므로, 반대로 부르면
  무한 재귀가 된다. os.getenv 원시값 + ``apps.api.config`` (다른 모듈, 재귀無)만 사용한다.
"""

from __future__ import annotations

import os

# 개발/테스트로 취급하는 환경 이름 집합(이 밖은 모두 프로덕션으로 간주 = fail-secure).
_DEV = {"development", "test"}


def _collect(extra: tuple[str, ...] = ()) -> set[str]:
    """환경 이름 후보를 모은다 — os.environ 원시 ENVIRONMENT/APP_ENV + 호출자 힌트 + 루트 config.

    루트(apps.api.config)는 별개 모듈이라 재귀 위험이 없다. app/core/config 는 절대 건드리지
    않는다(그쪽 get_settings 가 이 함수를 부르므로 재귀). 실패는 조용히 무시한다.
    """
    vals: set[str] = set()
    for v in (os.getenv("ENVIRONMENT"), os.getenv("APP_ENV"), *extra):
        if v:
            vals.add(str(v).strip().lower())
    try:
        from apps.api.config import get_settings as _root
        vals.add((_root().environment or "").strip().lower())
    except Exception:  # noqa: BLE001 — 루트 config 로딩 실패는 무시(원시값만으로 판정)
        pass
    # app/core/config 의 APP_ENV 도 병합한다(M1 4소스 계약 복원). 이 소스는 CWD .env 파일을
    # 직접 로드하므로, ENVIRONMENT 를 실 env var 로 안 넣고 .env 에 APP_ENV=production 만 둔
    # 좁은 구성에서도 프로덕션을 놓치지 않는다(secret_store 마스터키 폴백 fail-open 방지).
    # ★재귀 안전: get_settings() 를 호출하지 않고 '이미 생성된' 모듈레벨 settings 객체만 읽는다.
    #   config.py 부팅 중(settings 미생성)이면 None → 건너뜀(순환·재귀 없음).
    try:
        import app.core.config as _cc
        v = getattr(getattr(_cc, "settings", None), "APP_ENV", None)
        if v:
            vals.add(str(v).strip().lower())
    except Exception:  # noqa: BLE001 — 부팅 중/로딩 실패는 무시
        pass
    vals.discard("")
    return vals


def is_production(*hints: str) -> bool:
    """fail-secure 프로덕션 판별.

    수집된 환경값이 '있고' 그것들이 전부 {development,test} 부분집합일 때만 개발로 보고,
    그 외(값 없음·불명·staging·production 혼재 등)는 모두 프로덕션으로 간주한다(안전측 차단).

    hints: 호출자가 이미 아는 환경값(예: config.py 의 s.APP_ENV)을 힌트로 넘긴다. 재귀를
    피하려면 app/core/config 를 다시 읽는 대신 이 인자로 값을 전달하라.
    """
    vals = _collect(hints)
    return not (vals and vals <= _DEV)


def is_debug() -> bool:
    """디버그 모드(SQL echo 등) 판별 — 프로덕션에서는 무조건 off.

    프로덕션에서 SQL/바인드 파라미터 로그가 새는 것을 원천 차단한다. 개발 환경에서만
    명시 플래그(APP_DEBUG/DEBUG)가 참이면 True.
    """
    if is_production():
        return False
    raw = (os.getenv("APP_DEBUG") or os.getenv("DEBUG") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")
