"""의존처 점검 공용 통로 — **헬스체크는 의존처보다 먼저 끝나야 한다**.

헬스체크의 일은 의존처를 끝까지 기다리는 게 아니라 "느리다/죽었다"를 제때 보고하는
것이다. 그런데 종전에는 각 점검에 상한이 없어, 의존처 하나가 매달리면 헬스체크가 그만큼
통째로 매달렸다.

★왜 만들었나 (2026-08-11 프로덕션 실측):
    Supabase 풀러(``...pooler.supabase.com:6543``)가 신규 연결을 60초 매달았다가
    ``connection was closed in the middle of operation`` 으로 끊는 상태가 이어졌다.
    그동안 ``/health`` 는 **재는 족족 60.08~60.13초**였다(2시간 표본 136건의 최소·최대).
    같은 앱의 ``/api/...`` 는 7ms 로 멀쩡했으므로 이벤트 루프 문제가 아니라
    **핸들러가 의존처를 무제한으로 기다린 것**이다.

    파장(근거 강도를 구분해 적는다):
      · **실측** — ``deploy.sh`` 는 신앱 기동을 ``curl -sf .../health`` 로 기다리고(36행),
        컷오버 뒤 한 번 더 본다(52행). 그 구간에 배포했다면 두 지점에서 각 60초를 더 썼다.
        ★단 ``/health`` 는 degraded 여도 **200** 이라 ``curl -sf`` 는 성공한다 →
        **배포가 막히는 게 아니라 느려진다**(처음에 "막힌다"고 적었다가 실측 후 정정).
      · **추론** — 컨테이너 ``HEALTHCHECK`` 는 Timeout 30초인데 핸들러가 60초였으니 그동안
        계속 실패했을 것이다. 도커는 헬스 로그를 최근 5건만 남겨 사건 구간이 이미 밀려나
        **실측으로 확인하지는 못했다**(사후 조회 시점엔 healthy·FailingStreak=0).

★변이 감사에서 **설명되는 생존**(``scripts/mutate_changed.py`` · 29건 중 11건 생존.
  3건은 진짜 구멍이라 락을 추가했고, 아래 8건은 성질상 잠글 수 없거나 잠그면 안 된다):
    · 로그 **문구** 변경 3건 — 문구는 계약이 아니다. 잠그면 다음 사람이 메시지를 못 고친다.
      잠글 것은 문구가 아니라 **어떤 상태에서 무엇을 반환하는가** 다.
    · ``if services["postgres"] != HEALTHY:`` 조건 무력화와 그 안의 2줄 — **로그 전용 분기**라
      반환값이 바뀌지 않는다. 값에 영향이 없는 것을 값 테스트로 잡을 수는 없다.
    · ``sa.text("SELECT 1")`` 문구 변경 — 위조 엔진은 설계상 SQL 을 무시한다. 실제 DB
      픽스처 없이는 쿼리문을 잠글 수 없다(없는 것을 있는 척하지 않는다).
    · ``settings``/``aioredis.from_url`` 줄 삭제 — 죽으면 redis 가 unhealthy 로 떨어지는데
      CI 에는 redis 가 없어 어차피 unhealthy 라 **구분되지 않는다**. 값 단언은 실제 서비스
      픽스처가 생겨야 의미가 있다. 대신 **세 키가 모두 실려 오는지**는 잠갔다.

★남는 한계(고치지 않고 적어 둔다): qdrant 점검은 동기 구현을 스레드로 빼므로, 상한을
  넘겨 돌아온 뒤에도 **그 스레드는 계속 돈다**. 기본 실행기 워커가 유한하므로 qdrant 가
  오래 매달리면 스레드가 쌓일 수 있다. 다만 지금 관측된 사고는 postgres 쪽이었고,
  qdrant 는 0.00초였다 — 실제로 겪지 않은 위험을 추정으로 선제 설계하지 않는다.

★공용화한 이유: 같은 로직이 ``main.py`` 의 ``/health`` 와 ``routers/system.py`` 의
  ``/api/v1/system/health/full`` 두 곳에 복제돼 있었고, **둘 다** 무제한으로 기다렸다.
  한 곳만 고치면 미러가 남는다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from apps.api.logging_config import get_logger

logger = get_logger(__name__)

# 의존처 하나당 상한. 점검은 순차라 최악은 (의존처 수 × 이 값) 이다.
PROBE_TIMEOUT_S = 3.0

# 점검 결과 기호. ★'느림'과 '죽음'을 같은 기호로 쓰지 않는다 — 운영자가 취할 대응이 다르다
# (느림=의존처 지연/포화, 죽음=연결 거부·인증 실패). 뭉치면 원인 분류가 사라진다.
HEALTHY = "healthy"
UNHEALTHY = "unhealthy"
TIMEOUT = "timeout"


async def probe(
    name: str,
    coro: Coroutine[Any, Any, Any],
    timeout: float | None = None,
) -> str:
    """의존처 하나를 상한 안에서 잰다. 결과는 ``healthy`` / ``timeout`` / ``unhealthy``."""
    limit = PROBE_TIMEOUT_S if timeout is None else timeout
    try:
        await asyncio.wait_for(coro, timeout=limit)
        return HEALTHY
    # ★타임아웃을 **별도 분기로** 잡는다 — 아래 `except Exception` 으로 흘려보내면
    #   '느림'이 '죽음'으로 뭉개진다. 이 저장소는 3.12 타깃이라 `asyncio.TimeoutError` 는
    #   내장 `TimeoutError` 의 별칭이다(3.10 에서는 별개 클래스라 이 코드가 오동작한다 —
    #   그래서 테스트는 3.12 로 돌려야 한다. 로컬 3.10 으로 돌리고 오판할 뻔했다).
    except TimeoutError:
        logger.warning("헬스체크 의존처 타임아웃", service=name, timeout_s=limit)
        return TIMEOUT
    except Exception as e:
        logger.error("헬스체크 의존처 실패", service=name, error=str(e)[:200])
        return UNHEALTHY


async def collect_service_health(timeout: float | None = None) -> dict[str, str]:
    """postgres·redis·qdrant 를 각각 상한 안에서 점검한다."""
    # ★함수 안에서 임포트한다 — 모듈 로드 시점이 아니라 **호출 시점**의 engine 을 본다.
    #   (테스트가 engine 을 위조해 느린 의존처를 실제로 태울 수 있어야 한다.)
    import sqlalchemy as sa

    from apps.api.config import get_settings
    from apps.api.database import session as session_mod
    from apps.api.database.init_qdrant import check_qdrant_health

    settings = get_settings()
    services: dict[str, str] = {}

    async def _postgres() -> None:
        async with session_mod.engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))

    services["postgres"] = await probe("postgres", _postgres(), timeout)
    if services["postgres"] != HEALTHY:
        db_url = str(session_mod.engine.url)
        masked = db_url.split("@")[-1] if "@" in db_url else db_url
        logger.error("PostgreSQL health check failed", host=masked, state=services["postgres"])

    async def _redis() -> None:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url)
        try:
            await client.ping()
        finally:
            await client.aclose()

    services["redis"] = await probe("redis", _redis(), timeout)

    # ★check_qdrant_health 는 내부 동기 호출을 스레드로 뺀다(init_qdrant.py 참조).
    #   동기 호출을 이벤트 루프에 그대로 올리면 wait_for 가 **취소하지 못해** 상한이 장식이 된다.
    #
    # ★★반환값을 반드시 본다. probe() 는 '예외 없이 끝났는가'만 보므로, 예외를 안에서
    #   삼키고 False 를 돌려주는 함수를 그냥 넘기면 **무조건 healthy 로 보고**된다.
    #   실제로 이 리팩터링에서 그 회귀를 넣었고(종전 코드는 불리언을 봤다), 위조 지점을
    #   직접 태워 보고 나서야 잡았다 — 헬스체크가 거짓말을 하게 되는 결함이다.
    async def _qdrant() -> None:
        if not await check_qdrant_health():
            raise RuntimeError("qdrant 응답 없음")

    services["qdrant"] = await probe("qdrant", _qdrant(), timeout)

    return services


def overall_status(services: dict[str, str]) -> str:
    """전체 상태. 하나라도 정상이 아니면 ``degraded``."""
    return HEALTHY if all(v == HEALTHY for v in services.values()) else "degraded"
