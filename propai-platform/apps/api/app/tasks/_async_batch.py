"""Celery 동기 태스크에서 async 코드를 돌릴 때 **커넥션을 남기지 않고** 끝내는 공용 진입점.

## 왜 이게 필요한가 — 2026-08-08 프로덕션 장애의 근본

Celery 태스크는 동기 함수라 `asyncio.run(...)` 으로 async 배치를 돌린다. 그런데
`asyncio.run` 은 **끝나면 이벤트 루프를 닫는다**. 반면 SQLAlchemy 비동기 엔진과 그
**커넥션 풀은 모듈 전역**이다(`app/core/database.py`·`database/session.py`).

그래서 배치가 끝나면 풀에는 **이미 닫힌 루프에 묶인 연결**이 남는다. 여기까지는 무해하다.
문제는 **다음 배치**다:

  1. 다음 실행이 새 루프에서 그 연결을 풀에서 꺼낸다
  2. `pool_pre_ping=True`(두 엔진 모두 켜져 있다) 가 연결 생사를 검사하려고
     **asyncpg 트랜잭션을 연다 → `BEGIN` 이 서버에 실제로 나간다**
  3. 그 응답 future 는 **죽은 루프**에 붙어 있어 `RuntimeError: got Future attached to a
     different loop` 로 끊긴다
  4. 서버에는 **끝나지 않는 트랜잭션**이 남는다 = `idle in transaction`, 마지막 쿼리 `BEGIN;`

★이 단계는 **추론이 아니라 재현으로 확인했다**(프로덕션 컨테이너에서 실행):
  종전 패턴 4회 → `idle in transaction` **+2** · 위 RuntimeError 발생
  이 진입점 4회 → **4회 전부 성공 · 누수 0**
★부수 확인: 종전 패턴은 누수만 한 게 아니라 **배치 자체가 조용히 실패**하고 있었다.

**실제 피해**: 누적된 고착 연결이 **Supabase 트랜잭션 풀러(6543) 슬롯을 고갈**시켜, DB 를 쓰는
모든 요청이 60초 타임아웃으로 죽었다(로그인 불가). 세션 포트(5432)는 멀쩡했고
`pg_stat_activity` 의 고착 16건은 **전부 마지막 쿼리가 `BEGIN;`**, 나이는 2~17일이었다.

★**정직 경계**: *기전*은 재현으로 증명했지만, **어느 스케줄이 그 16건을 만들었는지는 특정하지
  못했다.** DB 를 건드리는 스케줄이 여럿이고(시간별 `analyze_growth`, 일별 익명화·PII 파기·
  경매 동기화), 관측된 빈도(~1일 1건)와 단순 계산이 맞지 않는다. 이 진입점은 **경로 전체**를
  덮으므로 특정 없이도 유효하다 — 다만 "매일 X 태스크가 범인"이라고 단정하지 않는다.

★이 저장소는 이 현상을 **이미 알고 있었다** — `tests/integration/test_growth_loop_e2e.py` 가
`engine.dispose()` 를 부르며 "교차-이벤트루프 풀 바인딩 초기화"라고 적어 뒀다.
테스트에서만 처리하고 **배치 경로엔 적용하지 않은 것**이 이 사고다.

## 처방

루프가 닫히기 **전에**, 그 루프 안에서 엔진을 `dispose()` 한다. dispose 는 **풀에 반납된**
연결의 소켓을 닫고(ROLLBACK 을 보내지는 않는다 — 절단 시 서버가 롤백한다), 그래서 다음
실행이 죽은 루프의 연결을 물려받지 않는다. 체크아웃 중인 연결은 닫지 않는다(아래 한계 참조).

★태스크마다 손으로 `dispose` 를 넣지 않는다 — 6개 파일이 같은 결함을 공유했으므로
**한 곳을 고치면 전역이 따라오도록** 이 진입점으로 모은다.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

# ★PEP695(`def f[T](...)`)를 쓰지 않는다 — 3.12 전용 문법이라 이 모듈을 임포트하는
#   태스크 8개가 3.12 미만에서 통째로 임포트 불가가 된다(운영은 3.12지만 로컬·도구가 깨진다).
#   실제로 그렇게 바꿨다가 로컬 테스트가 SyntaxError 로 죽었다.
# ★변이 도구가 이 줄의 삭제·상수화를 **생존**으로 보고한다(설명 가능한 생존):
#   `from __future__ import annotations` 로 애노테이션이 문자열이라 **런타임 동작이 없다**.
#   이 줄을 지키는 것은 테스트가 아니라 **타입 검사기**다 — 여기에 가짜 락을 만들지 않는다.
T = TypeVar("T")


# 이 저장소의 **모듈 스코프 비동기 엔진 전부**(모듈, 속성명).
#
# ★실측(프로덕션 3.12 컨테이너):
#     app.core.database.engine                   → AsyncAdaptedQueuePool  ← **유일하게 실효**
#     apps.api.database.session.engine           → NullPool
#     apps.api.database.session.timescale_engine → NullPool
#     core.database.engine                       → NullPool
#   `NullPool.dispose()` 는 SQLAlchemy 소스상 **문자 그대로 `pass`** 다. 즉 이 목록에서
#   **풀드 엔진 하나가 이탈하면 프로덕션 누수가 그대로 돌아온다** — 나머지가 남아 있어도
#   "엔진을 찾았다"는 검사는 통과한다(적대검증이 이 형태로 실증했다).
#   그래서 테스트는 개수가 아니라 **풀드 엔진의 실재**를 단언한다.
# ★새 엔진을 만들면 여기 추가한다 — 빠지면 그 엔진의 연결만 조용히 새어 나간다.
_ENGINES: tuple[tuple[str, str], ...] = (
    ("app.core.database", "engine"),
    ("apps.api.database.session", "engine"),
    ("apps.api.database.session", "timescale_engine"),
    # ★현재 임포트 소비처 0이지만 모듈 스코프 엔진이라 넣어 둔다(누락이 다음 사고가 된다).
    # ★변이 도구가 이 항목의 문자열 변경을 **생존**으로 보고한다(설명 가능한 생존):
    #   이 엔진은 오늘 **소비처 0 + NullPool** 이라 이름을 바꿔도 런타임 차이가 없다.
    #   실효 엔진의 이탈은 위 `test_계약에_풀드_엔진이_최소_하나_실재한다` 가 잡는다.
    #   여기에 이름 검사를 박으면 **상수를 복창하는 동어반복 락**이 되므로 두지 않는다.
    ("core.database", "engine"),
)


async def _dispose_engines() -> int:
    """현재 루프에 묶인 커넥션 풀을 정리하고, 정리한 엔진 수를 돌려준다.

    ★`dispose()` 가 닫는 것은 **풀에 반납된(checked-in) 연결**이다. 아직 **체크아웃 중**인
      연결은 닫지 않고 엔진에서 분리만 한다 — 그래서 배치가 연결을 쥔 채 예외로 빠지거나,
      `create_task` 로 띄운 백그라운드 작업이 DB 를 쥐고 있으면 **그 연결은 여전히 샌다**
      (`asyncio.run` 의 pending 태스크 취소는 이 정리보다 **뒤**에 일어난다).
      막지 못하는 그 경로를 **조용히 두지 않고 경고로 드러낸다** — 관측이 없으면 다음 사고도
      사용자 신고로 알게 된다.
    ★그리고 dispose 는 ROLLBACK 을 보내지 않는다(소켓을 닫고 서버가 절단 시 롤백한다).
      종전 주석이 "ROLLBACK 후 close" 라고 적었는데 사실이 아니라 바로잡았다.
    """
    disposed = 0
    for module_name, attr in _ENGINES:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 — 해당 엔진이 없는 배포 형태도 있다
            continue
        engine = getattr(module, attr, None)
        if engine is None:
            continue
        try:
            checked_out = engine.pool.checkedout()
            if checked_out:
                logger.warning(
                    "정리 시점에 반납되지 않은 연결 %d개 — 이 연결은 dispose 로 닫히지 않는다"
                    " (%s.%s). 배치가 연결을 쥔 채 끝났거나 백그라운드 태스크가 남았다.",
                    checked_out,
                    module_name,
                    attr,
                )
        except Exception:  # noqa: BLE001 — 관측 실패가 정리를 막지 않게 한다
            pass
        try:
            await engine.dispose()
            disposed += 1
        except Exception:  # noqa: BLE001 — 정리 실패가 배치 결과를 덮지 않게 한다
            logger.warning("engine dispose 실패: %s.%s", module_name, attr, exc_info=True)
    return disposed


# 자식 태스크를 기다려 주는 상한(초). 넘으면 **포기하고 시끄럽게 알린 뒤** 정리로 넘어간다.
# ★상한을 반드시 둔다: 무한 대기는 "누수를 막으려다 배치를 멈추는" 새 결함이 된다
#   (CLAUDE.md §"봉합이 새 결함을 만듦"). 상한을 넘은 경우의 결과는 **종전과 동일**하므로
#   이 값이 커지든 작아지든 안전 방향은 바뀌지 않는다 — 그래서 여기에 가짜 락을 만들지 않는다.
_CHILD_DRAIN_TIMEOUT_SEC = 30.0


async def _drain_child_tasks(timeout: float | None = None) -> int:
    """배치가 이 루프에 띄워 둔 **아직 끝나지 않은 자식 태스크**를 기다린다.

    ★왜 필요한가 — `dispose()` 는 **풀에 반납된** 연결만 닫는다. 배치 본문이
      `create_task(...)` 로 백그라운드 작업을 띄웠고 그 작업이 DB 를 쥔 채 남아 있으면,
      정리는 그 연결을 못 닫고 곧이어 `asyncio.run` 이 **루프를 닫으며 그 태스크를 취소**한다.
      쿼리 도중 취소된 연결은 서버에 트랜잭션을 남긴 채 끊긴다 = **이 모듈이 막으려던
      바로 그 `idle in transaction` 이 다른 문으로 돌아온다.**
      종전 이 모듈은 그 상황을 **경고로 알리기만 했다**(탐지≠교정) — 여기서 교정한다.

    ★도달성(정직 경계): 오늘 이 저장소에서 배치가 자식을 띄우는 경로는
      `growth_dispatch.fire_and_forget` 하나이고, 그 경로에 닿는 배치 두 개
      (`tasks.memory.ingest_experience`·`tasks.specialists.run_for_analysis`)는
      **`GROWTH_CELERY_WORKER` 가 켜져야만 발화**한다(전 배포 설정에 미설정 — 실측).
      즉 **잠재이고 오늘 라이브가 아니다.** 그럼에도 막아 두는 이유는 그 플래그가
      "미래 배포 대비"로 코드에 명시돼 있고, 켜는 순간 조용히 사고가 돌아오기 때문이다.

    ★모집단을 "성장뇌 태스크"로 좁히지 않는다 — **누가 띄웠든** 정리 시점에 살아 있는
      자식은 같은 결함이다(목록형 금지·CLAUDE.md §A-4).
    """
    # ★상한은 **호출 시점에** 읽는다 — 기본 인자로 굳히면 상수를 바꿔도 반영되지 않아
    #   테스트가 실제 경로를 태우지 못한다(값이 장식이 되는 형태).
    timeout = _CHILD_DRAIN_TIMEOUT_SEC if timeout is None else timeout

    pending = {t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()}
    if not pending:
        return 0

    _done, still_pending = await asyncio.wait(pending, timeout=timeout)
    if still_pending:
        # 막지 못한 것을 조용히 두지 않는다 — 관측이 없으면 다음 사고도 사용자 신고로 안다.
        logger.warning(
            "자식 태스크 %d개가 %.0f초 안에 끝나지 않았다 — 루프가 닫히며 취소되고,"
            " 그 연결은 서버에 트랜잭션을 남길 수 있다: %s",
            len(still_pending),
            timeout,
            sorted(t.get_name() for t in still_pending),
        )
    return len(pending) - len(still_pending)


# ruff: noqa: UP047 — PEP695(`def f[T](...)`)를 쓰지 않는 것은 **의도**다(위 T 정의 주석 참조).
#   3.12 전용 문법이라 이 모듈을 임포트하는 태스크 8개가 3.12 미만에서 임포트 불가가 된다.
def run_async_batch(factory: Callable[[], Awaitable[T]]) -> T:
    """async 배치를 돌리고, **루프를 닫기 전에** 커넥션 풀을 정리한다.

    `factory` 는 코루틴을 만드는 함수다(코루틴 객체가 아니라). 재시도 경로에서 코루틴을
    두 번 await 하는 사고를 막기 위해 매번 새로 만들게 한다.

    ★**`except RuntimeError` 폴백을 두지 않는다**(적대검증이 두 가지를 실증했다):
      ① 원래 노린 상황(이미 루프가 도는 환경)에서 **작동하지 않는다** — 러닝 루프 안에서
         `loop.run_until_complete()` 는 원리적으로 불가능하고, 미-await 코루틴 경고까지 남는다.
      ② 실제로 발화하는 유일한 경로는 **본문이 던진 RuntimeError** 이고, 그때 배치가
         **통째로 재실행**된다. 종전에 폴백이 없던 4곳(경공매 전국 수집·대량필지 배치(과금
         게이트)·성장뇌 적재·전문가 원장(append-only))에 그 위험을 새로 넣을 뻔했다.
      대신 **진입 시점에 판정해 시끄럽게 거절**한다 — 같은 저장소의
      `services/deliberation-review/.../reconcile_tasks.py` 가 같은 사고(INC-13) 뒤 택한 방식이다.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # 러닝 루프 없음 = 정상적인 동기 배치 경로
    else:
        raise RuntimeError(
            "run_async_batch 는 동기 컨텍스트 전용이다 — 러닝 루프 안에서는 코루틴을 직접 await 하라"
        )

    async def _runner() -> T:
        try:
            return await factory()
        finally:
            # ★배치가 실패해도 정리는 반드시 한다 — 예외 경로가 오히려 더 잘 샌다.
            # ★정리 **전에** 배치가 띄운 자식 태스크를 먼저 기다린다(아래 함수 주석 참조).
            await _drain_child_tasks()
            await _dispose_engines()

    return asyncio.run(_runner())
