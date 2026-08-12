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
    cancelled: BaseException | None = None
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
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit) as exc:
            # ★★취소(`CancelledError`)는 **`BaseException` 계열**이라 위 `except Exception` 을
            #   통과한다 → **첫 엔진에서 끊기면 나머지 엔진은 정리 시도조차 못 한다.**
            #   호출부(`_runner`)에서 같은 결함을 고쳐 놓고 **여기 한 겹 아래에 그대로 남아
            #   있었다** — 독립 적대검증 3라운드가 실제 `run_async_batch` 로 재현했다.
            #   ★"처방을 적용한 범위 = 결함이 사는 범위인가"(CLAUDE.md §D-20)의 실례다.
            #   ★`BaseException` 을 통째로 잡지 **않는다** — `GeneratorExit` 까지 잡으면 그 안에서
            #     `await` 하는 순간 `RuntimeError: coroutine ignored GeneratorExit` 가 된다.
            #     한 겹 위(`_runner`)에서 같은 이유로 좁혀 놓고 **여기엔 적용하지 않았다**
            #     (4라운드 지적 — §D-20 "처방을 적용한 범위 = 결함이 사는 범위인가"를
            #     인용한 바로 그 커밋 안에서 재발).
            logger.warning("engine dispose 취소됨: %s.%s", module_name, attr, exc_info=True)
            # ★**우선순위로 보관**한다. 마지막 것만 남기면 앞선 `KeyboardInterrupt` 가 뒤따르는
            #   `CancelledError` 에 덮여 **Ctrl-C 가 먹힌다** — 바로 아래 주석이 "취소를 먹으면
            #   워커 종료가 지연된다"고 쓴 그 일이다(4라운드 실측).
            if cancelled is None or (
                isinstance(cancelled, asyncio.CancelledError)
                and not isinstance(exc, asyncio.CancelledError)
            ):
                cancelled = exc  # 종료 신호(KI·SystemExit)가 취소보다 우선한다
    # ★반환값 `disposed` 는 **소비처 0**이고 잠금도 없다(변이 생존 — 설명 가능한 생존).
    #   진단 로그·수동 확인용으로만 남긴다. 여기에 락을 만들면 아무도 안 쓰는 값을
    #   복창하는 동어반복이 된다 — 대신 그 사실을 적는다(CLAUDE.md §5).
    if cancelled is not None:
        # ★삼키지 않는다 — 취소를 먹으면 워커 종료가 지연된다.
        raise cancelled
    return disposed


# 자식 태스크를 기다려 주는 상한(초). 넘으면 **포기하고 시끄럽게 알린 뒤** 정리로 넘어간다.
# ★상한을 반드시 둔다: 무한 대기는 "누수를 막으려다 배치를 멈추는" 새 결함이 된다
#   (CLAUDE.md §"봉합이 새 결함을 만듦").
# ★★종전 주석은 "값이 커지든 작아지든 안전 방향은 바뀌지 않으므로 잠그지 않는다"고 했는데,
#   **절반만 맞았다**(독립 적대검증 지적). 이 상수가 지키는 것은 *안전*이 아니라 **가용성**이고,
#   3600 같은 값은 바로 그 결함이다 — beat 5초 주기 `flush_growth_events` 가 한 시간 매달릴 수
#   있다(도착률 > 처리율 → 큐 적체 → 같은 워커의 parcel_batch·auction·rates 까지 굶는다).
#   그래서 **동어반복(`== 30.0`)이 아니라 범위**를 잠근다 — 아래 상수가 그 계약이다.
#   `test_상한은_가용성_범위_안에_있다` 가 이 두 값에 결속돼 있다.
_CHILD_DRAIN_TIMEOUT_SEC = 30.0

# 가용성 계약: 배수 상한은 이 범위를 벗어나면 안 된다.
#   상한 60 — 가장 촘촘한 beat 주기(`flush_growth_events` 5초)의 큐 적체를 막는 실무 상한.
_CHILD_DRAIN_TIMEOUT_MAX_SEC = 60.0

# ★하한 쪽은 **기본값 폴백**으로 건다. 종전에는 "경계는 양방향(§D-19)"이라고 **주석에만 적고**
#   런타임에는 `min()` 만 있어서, `timeout=0`·음수를 주면 배수가 **통째로 건너뛰어졌다**
#   (4라운드 실측: drained=0 · elapsed=0.000s). `max-h` 만 걸고 `min-h` 를 안 걸어
#   프로덕션이 0px 이 된 그 사고와 **같은 형태**다.
# ★작은 엡실론(0.001 같은 값)으로 클램프하지 **않는다** — 1ms 배수는 건너뛴 것과 사실상
#   같아서 "고쳤다"는 착각만 만든다. 무의미한 값이 들어오면 **설정된 기본값**으로 돌린다.
# ★단 **양수는 존중한다**: 호출부가 일부러 짧게 주는 것은 의도다(테스트가 그렇게 쓴다).


async def _drain_child_tasks(timeout: float | None = None) -> int:
    """배치가 이 루프에 띄워 둔 **아직 끝나지 않은 자식 태스크**를 기다린다.

    ★왜 필요한가 — `dispose()` 는 **풀에 반납된** 연결만 닫는다. 배치 본문이
      `create_task(...)` 로 백그라운드 작업을 띄웠고 그 작업이 DB 를 쥔 채 남아 있으면,
      정리는 그 연결을 못 닫고 곧이어 `asyncio.run` 이 **루프를 닫으며 그 태스크를 취소**한다.
      쿼리 도중 취소된 연결은 서버에 트랜잭션을 남긴 채 끊긴다 = **이 모듈이 막으려던
      바로 그 `idle in transaction` 이 다른 문으로 돌아온다.**
      종전 이 모듈은 그 상황을 **경고로 알리기만 했다**(탐지≠교정) — 여기서 교정한다.

    ★도달성(정직 경계) — **두 번 고쳐 잡았다. 두 번째는 인과가 뒤집혀 있었다.**

      ① `record_llm_response_billing_sync` → `loop.create_task(...)` — **게이트 없이 라이브**다.
         `analyze_growth`(beat 시간별)·`evaluate_improvement`(일별)이 LLM 을 태우며 발화한다.
         다만 배치에는 요청 컨텍스트가 없어 `get_current_user_id()` 가 None → **DB 접근 전
         조기 반환**한다. 즉 **자식 생성은 라이브이나 DB 를 쥐지는 않는다.**(재확인 완료)

      ② `growth_dispatch.fire_and_forget` — 이쪽이 **DB 를 쥔다**(세션을 연다).
         ★종전 이 문단은 "`GROWTH_CELERY_WORKER` 가 켜져야 발화하고, 켜는 순간 돌아온다"고
         적었는데 **정반대였다**(독립 적대검증 3라운드 지적, 소스로 재확인):

             if _celery is not None and worker_enabled():
                 ...delay(...); return          # 플래그 ON → Celery 로 위임
             fire_and_forget(...)               # 플래그 OFF(=오늘 기본) → in-process 자식

         즉 `fire_and_forget` 은 **게이트 뒤가 아니라 게이트가 꺼졌을 때 도는 기본 경로**다.
         그런데 그때는 배치(`_ingest_experience`·`_run_domain_specialists`)가 **발화하지 않는다**
         — 그것들은 `.delay()` 로만 도달하고 `.delay()` 는 플래그 ON 에서만 쓰인다.
         반대로 플래그 ON 이면 배치 안에서 `dispatch_*` 가 다시 `.delay()` 로 빠져 in-process
         자식이 생기지 않는다. **두 상태가 서로 배타적이라 오늘 배치 안에 DB 를 쥔 자식이 없다.**

      ★그래도 이 배수를 두는 이유(정직하게):
        · 플래그가 **비대칭 설정**되면(디스패치 쪽 ON·워커 쪽 OFF) 워커 배치 안에서
          `fire_and_forget` 이 살아나 DB 를 쥔 자식이 생긴다 — 구성 실수 하나면 열린다.
        · 배치가 자식을 띄우는 경로는 위 ①처럼 **성장뇌와 무관한 곳에서도** 생긴다.
          모집단을 좁히지 않는 이유가 이것이다.
      ★이 문단은 **두 번 틀렸다**(첫 번째는 "경로가 하나", 두 번째는 인과 역전).
        도달성은 한 경로를 찾고 멈추면 틀리고, 조건을 반대로 읽어도 틀린다.

    ★모집단을 "성장뇌 태스크"로 좁히지 않는다 — **누가 띄웠든** 정리 시점에 살아 있는
      자식은 같은 결함이다(목록형 금지·CLAUDE.md §A-4).
    """
    # ★상한은 **호출 시점에** 읽는다 — 기본 인자로 굳히면 상수를 바꿔도 반영되지 않아
    #   테스트가 실제 경로를 태우지 못한다(값이 장식이 되는 형태).
    timeout = _CHILD_DRAIN_TIMEOUT_SEC if timeout is None else timeout
    # ★★상한을 **런타임에 클램프**한다. 종전에는 `_CHILD_DRAIN_TIMEOUT_MAX_SEC` 가
    #   테스트에서만 쓰여 **프로덕션 소비처 0**이었다 — 그래서 두 상수를 차례로 키우는
    #   2단 편집이 범위 락을 통과했다(독립 적대검증 실증: MAX 3600 → SEC 3600 둘 다 생존).
    #   여기서 소비하면 ① 상수가 장식이 아니게 되고 ② `timeout=` **인자 경로까지** 묶인다
    #   (종전 범위 락은 기본 상수만 봤다).
    # ★**양방향**으로 건다. `min()` 만 두면 `timeout=0`·음수가 배수를 통째로 건너뛴다.
    # ★`not (timeout > 0)` 형태여야 **NaN 도 함께 잡힌다** — `min(nan, 60)` 은 `nan` 을 돌려줘
    #   상한마저 무력화된다(4라운드 실측: NaN + 3600초 자식이 5초 뒤에도 대기 중).
    #   `max()` 를 앞에 두는 형태는 NaN 을 못 잡는다(NaN 비교는 전부 False).
    timeout = (
        _CHILD_DRAIN_TIMEOUT_SEC
        if not (timeout > 0)
        else min(timeout, _CHILD_DRAIN_TIMEOUT_MAX_SEC)
    )

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    drained = 0
    still_pending: set[asyncio.Task] = set()

    # ★한 번만 스냅샷하면 **손자가 빠져나간다** — 자식이 끝나며 또 자식을 띄우면 그것은
    #   기다리지 않은 채 루프가 닫힌다(같은 결함의 한 겹 아래). 그래서 마감까지 재스냅샷한다.
    #   마감이 유일한 종료 보장이다 — 자식이 무한히 자식을 낳아도 여기서 멈춘다.
    # ★회귀망은 **손자(깊이 2)까지만** 잠근다 — 증손자 이하는 무잠금이다(변이 생존).
    #   로직은 깊이 무관이지만 락은 아니다. 과대주장하지 않으려 여기 적는다.
    # ★`drained` 반환값도 소비처 0·무잠금이다(설명 가능한 생존).
    while True:
        pending = {
            t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()
        }
        if not pending:
            break
        remaining = deadline - loop.time()
        if remaining <= 0:
            still_pending = pending
            break
        done, still_pending = await asyncio.wait(pending, timeout=remaining)
        drained += len(done)
        # ★끝난 자식의 예외를 **회수**한다. 안 하면 GC 시점에 asyncio 가
        #   "Task exception was never retrieved" 를 찍는다 — 종전에는 `asyncio.run` 의
        #   종료 처리가 대신 해 주던 일이라, 배수를 넣으면서 새로 생기는 소음이다.
        # ★변이 도구가 이 두 줄의 삭제를 **생존**으로 보고한다(설명 가능한 생존):
        #   경고는 **GC 시점에 asyncio 내부**에서 나오므로 결정론적으로 단언할 수 없다.
        #   여기에 사적 속성(`_log_traceback`)을 들여다보는 락을 만들면 깨지기 쉬운
        #   가짜 잠금이 된다 — 그래서 두지 않고 이유를 적는다.
        for task in done:
            if not task.cancelled():
                task.exception()
        if still_pending:
            break

    if still_pending:
        # 막지 못한 것을 조용히 두지 않는다 — 관측이 없으면 다음 사고도 사용자 신고로 안다.
        logger.warning(
            "자식 태스크 %d개가 %.0f초 안에 끝나지 않았다 — 루프가 닫히며 취소되고,"
            " 그 연결은 서버에 트랜잭션을 남길 수 있다: %s",
            len(still_pending),
            timeout,
            sorted(t.get_name() for t in still_pending),
        )
    return drained


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
            # ★정리 **전에** 배치가 띄운 자식 태스크를 먼저 기다린다(위 함수 주석 참조).
            #
            # ★★배수는 **반드시 예외 격리**한다. 이 자리가 `finally` 라, 배수가 던지면
            #   ① `_dispose_engines()` 에 **도달조차 못 해** 이 모듈이 막으려던 누수가
            #      그대로 돌아오고, ② 원래 배치 예외가 배수 예외에 **가려져** 진단을 잃는다.
            #   `_dispose_engines` 는 엔진별 try/except 로 그 대칭을 이미 갖고 있었는데,
            #   앞에 끼워 넣은 배수에는 없었다 — 독립 적대검증이 재현으로 적발했다
            #   (배수에서 OSError → dispose 0회 · 원래 ValueError 가 OSError 로 뒤바뀜).
            #   ★"봉합이 새 결함을 만든다"의 실례다(CLAUDE.md §회귀망 규율).
            try:
                await _drain_child_tasks()
            except Exception:  # noqa: BLE001 — 배수 실패가 **정리를 막아서는 안 된다**
                logger.warning("자식 배수 실패 — 정리는 계속한다", exc_info=True)
            except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                # ★★`CancelledError`·`KeyboardInterrupt` 는 **`BaseException` 계열**이라 위
                #   `except Exception` 을 통과해 `finally` 를 빠져나간다 → 정리에 도달 못 한다.
                #   그냥 잔존 결함이 아니라 **이 배수가 만든 노출면**이다: 도입 전에는 `finally`
                #   가 즉시 dispose 로 갔는데, 이제 **최대 상한만큼 `finally` 안에 머무는 창**이
                #   생겼고 워커 종료·Ctrl-C 가 그 창에 떨어지면 누수가 그대로 돌아온다.
                #   (독립 적대검증이 실제 SIGINT 로 재현: dispose 0회)
                #   ★정리는 하고 **취소는 반드시 전파**한다 — 삼키면 종료가 지연된다.
                # ★**설명 가능한 생존**: 이 셋을 `except BaseException` 으로 **넓히는** 변이는
                #   테스트가 못 잡는다. 차이가 나는 유일한 형태가 `GeneratorExit` 인데,
                #   그건 `run_async_batch` 의 공개 경로로는 발생시킬 수 없다(`Task` 는 정지 중
                #   코루틴을 `close()` 하지 않는다). 잠그려면 `_runner` 를 모듈 스코프로 끌어내
                #   직접 `close()` 해야 하는데, **테스트를 위해 구현 구조를 바꾸는 것**이라
                #   하지 않는다. 좁히는 변이(셋 → CancelledError 만)는 잡힌다.
                # ★`BaseException` 을 통째로 잡지 **않는다**: `GeneratorExit` 까지 잡으면
                #   그 안에서 `await` 하는 순간 `RuntimeError: coroutine ignored GeneratorExit`
                #   가 되어 **깨끗한 코루틴 종료를 에러로 바꾼다**(3라운드 실측).
                #   그래서 종료 신호 셋만 명시한다.
                logger.warning("자식 배수가 취소됐다 — 정리는 계속한다", exc_info=True)
                await _dispose_engines()
                raise
            await _dispose_engines()

    return asyncio.run(_runner())
