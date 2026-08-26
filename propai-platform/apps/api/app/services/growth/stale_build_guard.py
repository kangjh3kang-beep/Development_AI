"""**낡은 스택이 성장루프를 쓰지 못하게** 막는 단일 관문.

## 무엇이 있었나 (2026-08-25 실측 — 이 모듈이 존재하는 이유)

158 서버에 `2026-08-07` 부터 **18일째** 도는 옛 api 컨테이너
(`propai-platform_api_1` · 이미지 `propai-api:oracle`)가 있었고, 그것이 **같은
프로덕션 DB 에 성장루프를 병렬로 쓰고 있었다.** 사용자 트래픽은 **0**(24시간
요청 2,850건 전부 자기 healthcheck)이었는데 DB 쓰기는 살아 있었다.

24시간 실측:

    platform_insights  INSERT 298   ← 그 중 129건이 아래의 "구조적 불가능 행"
    platform_settings  INSERT  14   ← 스케줄 워터마크. 이걸 옮겨 **정상 스택의 차례를 뺏었다**
    threshold_relax    executed:True 로 **실제 실행**(action_id 발급)

★대조가 결정적이었다: 같은 창에서 **정상 스택(168)은 `executed:True` 가 0건**이었다.
  즉 **프로덕션 임계를 실제로 완화해 온 것은 옛 스택 쪽**이었다.

## 왜 advisory lock 으로는 못 막았나

`_growth_run_locked` 의 `pg_try_advisory_lock` 은 **동시 실행만** 막는다.
스케줄은 `platform_settings` 의 **워터마크**로 정해지는데 두 스택이 그 워터마크를
공유하므로, 옛 스택이 먼저 도착하면 **정상적으로 락을 얻어** 자기 코드로 돌고
워터마크를 옮긴다. 상호배제는 성공했고 **틀린 쪽이 이긴 것**이다.

## 판별식과 그 근거

`APP_BUILD_ID`(예: `propai-v002765-08ca697e`)는 이미지 빌드 시 주입된다. 실측:

    168 의 propai-api/celery-beat/celery-worker/arq-worker/flower  → 전부 설정됨
    158 의 옛 propai-platform_api_1                                → **미설정**

그래서 **fail-closed**: 빌드 식별자가 없으면 성장루프 쓰기를 **거부**한다.
★값을 비교하지 않고 **존재만** 본다 — "무엇이 최신인가"를 이 프로세스가 알 방법이
없기 때문이다. 아는 것만 강제한다(모르는 것을 아는 척하면 그게 다음 결함이 된다).

★**읽기는 막지 않는다.** 막는 것은 **쓰기(잡 실행)** 뿐이다.
"""

from __future__ import annotations

import os

#: 빌드 식별자를 담는 환경변수. 이미지 빌드 시 주입된다.
BUILD_ID_ENV = "APP_BUILD_ID"

#: 게이트를 강제로 끄는 탈출구(운영 사고 시 · 로컬 개발). 기본은 **켜짐**.
DISABLE_ENV = "GROWTH_STALE_BUILD_GUARD_OFF"


def running_build_id() -> str | None:
    """이 프로세스의 빌드 식별자. 미설정/공백이면 ``None``."""
    v = (os.getenv(BUILD_ID_ENV) or "").strip()
    return v or None


def growth_writes_allowed() -> tuple[bool, str]:
    """성장루프 잡을 **이 프로세스에서 돌려도 되는가**.

    반환: ``(허용여부, 사유)``. 사유는 **항상** 채운다 —
    ★무언 거부는 "엔진 정지"와 "정상"을 같은 모양으로 만든다(이 저장소가 이미 데인 형태).
    """
    if (os.getenv(DISABLE_ENV) or "").strip() == "1":
        return True, f"게이트 해제됨({DISABLE_ENV}=1)"
    bid = running_build_id()
    if bid is None:
        return False, (
            f"{BUILD_ID_ENV} 미설정 — 배포 이미지가 아닌 낡은/수동 스택으로 판단해 "
            f"성장루프 쓰기를 거부한다. 정당한 프로세스라면 {BUILD_ID_ENV} 를 주입하거나 "
            f"{DISABLE_ENV}=1 로 명시 해제하라."
        )
    return True, f"빌드 식별자 확인({bid})"
