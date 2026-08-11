"""헬스체크가 **의존처보다 먼저 끝나는지** 잠근다.

왜 이 테스트가 있나 (2026-08-11 프로덕션 실측):
    Supabase 풀러가 신규 연결을 60초 매달았다가
    ``connection was closed in the middle of operation`` 으로 끊는 상태가 이어졌다.
    그동안 ``/health`` 는 **재는 족족 60.08~60.13초**였다(2시간 표본 136건의 최소·최대).
    같은 앱의 ``/api/...`` 는 7ms 로 멀쩡했으니 이벤트 루프 문제가 아니라 **핸들러가
    의존처를 무제한으로 기다린 것**이다.

    파장: 컨테이너 ``HEALTHCHECK`` Timeout 은 30초라 그동안 계속 실패했고, ``deploy.sh``
    도 신앱 기동을 이 경로로 기다리므로 **외부 의존처가 느리면 배포가 막힌다**.

같은 로직이 ``/health`` 와 ``/api/v1/system/health/full`` 두 곳에 복제돼 있었다 →
``app/core/health_probe.py`` 로 일원화했고, 여기서는 그 **공용 통로를 직접 태운다**.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from apps.api.app.core import health_probe


class _HangingEngine:
    """연결이 매달리는 엔진 — 풀러가 60초 물고 있던 상황의 축소판."""

    url = "postgresql+asyncpg://u:p@hidden-host:6543/postgres"

    def connect(self):  # noqa: ANN201 - async context manager 흉내
        class _Conn:
            async def execute(self, *_a: object, **_k: object) -> None:
                await asyncio.sleep(30)

        class _Ctx:
            async def __aenter__(self) -> _Conn:
                return _Conn()

            async def __aexit__(self, *_a: object) -> bool:
                return False

        return _Ctx()


class _RefusingEngine:
    """연결이 **즉시 거부**되는 엔진 — '느림'과 구분돼야 한다."""

    url = "postgresql+asyncpg://u:p@hidden-host:6543/postgres"

    def connect(self):  # noqa: ANN201
        class _Ctx:
            async def __aenter__(self) -> object:
                raise RuntimeError("연결 거부")

            async def __aexit__(self, *_a: object) -> bool:
                return False

        return _Ctx()


@pytest.mark.asyncio
async def test_느린_의존처가_있어도_상한_안에_끝난다(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.api.database import session as session_mod

    monkeypatch.setattr(session_mod, "engine", _HangingEngine())

    started = time.monotonic()
    services = await health_probe.collect_service_health(timeout=0.2)
    elapsed = time.monotonic() - started

    # ★공허진리 방지 — 진짜로 느린 의존처를 태웠는지부터 확인한다. healthy 로 나오면
    #   위조가 안 먹은 것이고, 그러면 아래 시간 단언은 "빠른 경로가 빨랐다"는 공허한 참이 된다.
    assert services["postgres"] == health_probe.TIMEOUT, (
        f"느린 의존처를 태우지 못했다(postgres={services['postgres']}) — 위조가 안 먹었다"
    )
    # 종전 구조라면 여기서 30초를 통째로 기다린다.
    assert elapsed < 5.0, f"헬스체크가 상한을 넘겼다: {elapsed:.2f}초"
    assert health_probe.overall_status(services) == "degraded"


@pytest.mark.asyncio
async def test_느림과_죽음을_다른_기호로_쓴다(monkeypatch: pytest.MonkeyPatch) -> None:
    """운영자가 취할 대응이 다르다 — 뭉치면 원인 분류가 사라진다."""
    from apps.api.database import session as session_mod

    monkeypatch.setattr(session_mod, "engine", _RefusingEngine())
    refused = await health_probe.collect_service_health(timeout=0.2)

    monkeypatch.setattr(session_mod, "engine", _HangingEngine())
    hanging = await health_probe.collect_service_health(timeout=0.2)

    assert refused["postgres"] == health_probe.UNHEALTHY, (
        f"즉시 거부는 unhealthy 여야 한다(실제 {refused['postgres']})"
    )
    assert hanging["postgres"] == health_probe.TIMEOUT, (
        f"매달림은 timeout 이어야 한다(실제 {hanging['postgres']})"
    )
    # ★두 기호가 실제로 갈리는지 — 같으면 위 두 단언이 동시에 참일 수 없다는 사실을 명시한다.
    assert refused["postgres"] != hanging["postgres"], "느림과 죽음이 같은 기호로 뭉쳤다"


@pytest.mark.asyncio
async def test_동기_블로킹_의존처도_상한에_걸린다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★타임아웃이 장식이 되는 함정을 **동작으로** 잠근다.

    ``check_qdrant_health`` 가 ``async def`` 이면서 내부가 동기 블로킹이면,
    ``asyncio.wait_for`` 로 감싸도 **취소되지 않는다** — 이벤트 루프에 올라탄 동기 호출은
    타임아웃이 지나도 끝날 때까지 돌아오지 않는다. 스레드로 빼야 비로소 상한이 산다.

    그래서 동기 구현을 **실제로 매달리게** 만들고 상한 안에 돌아오는지 본다
    (소스에 to_thread 가 있는지 보는 검사는 주석·문자열에 뚫린다).
    """
    from apps.api.database import init_qdrant

    def _slow_sync() -> bool:
        time.sleep(10)  # 동기 블로킹 — 이벤트 루프에 그대로 올리면 취소 불가
        return True

    monkeypatch.setattr(init_qdrant, "check_qdrant_health_sync", _slow_sync)

    started = time.monotonic()
    state = await health_probe.probe("qdrant", init_qdrant.check_qdrant_health(), timeout=0.3)
    elapsed = time.monotonic() - started

    assert state == health_probe.TIMEOUT, f"동기 블로킹이 상한에 안 걸렸다(state={state})"
    assert elapsed < 3.0, (
        f"상한을 넘겼다({elapsed:.2f}초) — 동기 호출이 이벤트 루프에 올라타 취소가 안 된 것이다"
    )


# ── 아래 셋은 `scripts/mutate_changed.py` 가 잡아낸 **실제 구멍**을 메운 것이다 ──
#    (도구를 돌리기 전 나는 위 세 테스트로 충분하다고 여겼다. 아니었다.)


@pytest.mark.asyncio
async def test_인자를_안_주면_기본_상한이_쓰인다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★변이 적발: ``PROBE_TIMEOUT_S`` 줄을 지워도 위 테스트들이 전부 통과했다.

    위 테스트가 전부 ``timeout=`` 을 **명시**해서 넘겼기 때문이다. 즉 **프로덕션이 실제로
    타는 기본값 경로**는 한 번도 검증되지 않았다. 상수가 장식이 될 수 있었다.
    """
    assert isinstance(health_probe.PROBE_TIMEOUT_S, (int, float))
    assert 0 < health_probe.PROBE_TIMEOUT_S <= 10, (
        f"기본 상한이 비현실적이다({health_probe.PROBE_TIMEOUT_S}초) — "
        "너무 짧으면 멀쩡한 의존처를 timeout 으로 신고하고, 너무 길면 상한의 의미가 없다"
    )

    # 기본값을 짧게 갈아끼우고 **인자 없이** 호출한다 → 기본 경로가 실제로 상한을 건다.
    monkeypatch.setattr(health_probe, "PROBE_TIMEOUT_S", 0.2)

    async def _hang() -> None:
        await asyncio.sleep(30)

    started = time.monotonic()
    state = await health_probe.probe("dep", _hang())  # ← timeout 인자 없음(프로덕션과 같은 호출)
    elapsed = time.monotonic() - started

    assert state == health_probe.TIMEOUT, f"기본 상한이 안 걸렸다(state={state})"
    assert elapsed < 3.0, f"기본 경로가 상한을 넘겼다: {elapsed:.2f}초"


@pytest.mark.asyncio
async def test_불리언을_돌려주는_점검은_그_값을_봐야_한다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★리팩터링에서 실제로 넣었던 회귀 — 헬스체크가 거짓말을 하게 된다.

    ``probe()`` 는 '예외 없이 끝났는가'만 본다. 그런데 ``check_qdrant_health`` 는 예외를
    **안에서 삼키고 False 를 돌려준다**. 그래서 그 코루틴을 그냥 넘기면 qdrant 가 죽어도
    ``healthy`` 로 보고된다 — 종전 코드는 불리언을 봤는데 공용 통로로 옮기며 빠뜨렸다.

    위조 지점(``init_qdrant.check_qdrant_health``)을 직접 태워서야 잡혔다. 단위 테스트가
    타임아웃만 보고 있었기 때문이다.
    """
    from unittest.mock import AsyncMock

    from apps.api.database import init_qdrant

    monkeypatch.setattr(
        init_qdrant, "check_qdrant_health", AsyncMock(return_value=False)
    )
    services = await health_probe.collect_service_health(timeout=0.5)
    assert services["qdrant"] == health_probe.UNHEALTHY, (
        f"qdrant 점검이 False 를 돌려줬는데 {services['qdrant']} 로 보고됐다 — 헬스체크가 거짓말한다"
    )

    monkeypatch.setattr(
        init_qdrant, "check_qdrant_health", AsyncMock(return_value=True)
    )
    services = await health_probe.collect_service_health(timeout=0.5)
    assert services["qdrant"] == health_probe.HEALTHY, (
        "정상인데 healthy 로 보고되지 않았다 — 위양성 가드도 결함이다"
    )


def test_상태_기호의_문자열이_계약이다() -> None:
    """★변이 적발: ``UNHEALTHY = "unhealthy"`` 의 **문자열만** 바꿔도 아무 테스트가 안 죽었다.

    위 테스트들이 리터럴이 아니라 상수 심볼로 비교하기 때문이다. 그런데 이 문자열은
    응답 본문에 그대로 실려 **소비처(모니터링·운영자)가 읽는 계약**이다. 심볼로만 비교하면
    값이 조용히 바뀌어도 안에서는 아무도 모르고 밖에서만 깨진다 → 값 자체를 잠근다.
    """
    assert health_probe.HEALTHY == "healthy"
    assert health_probe.UNHEALTHY == "unhealthy"
    assert health_probe.TIMEOUT == "timeout"
    assert health_probe.overall_status({"a": "healthy"}) == "healthy"
    assert health_probe.overall_status({"a": "healthy", "b": "timeout"}) == "degraded"


@pytest.mark.asyncio
async def test_한_의존처가_죽어도_나머지를_계속_점검한다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★변이 적발: postgres 경로가 죽어도(예: 이름 오류) 나머지가 안 불리는지 확인이 없었다.

    헬스체크는 "무엇이 문제인지"를 알려주는 도구다. 앞의 하나가 넘어졌다고 뒤를 건너뛰면
    보고가 반쪽이 된다 → 세 키가 **모두** 실려 오는지 잠근다.

    ★정직한 한계: redis·qdrant 의 **값**은 여기서 단언하지 않는다. CI 에는 두 서비스가
      없어 어차피 실패 상태이고, 그걸 healthy 로 단언하면 거짓 초록이 된다. 값 단언은
      실제 서비스 픽스처가 생기면 그때 추가할 몫이다.
    """
    from apps.api.database import session as session_mod

    monkeypatch.setattr(session_mod, "engine", _HangingEngine())
    services = await health_probe.collect_service_health(timeout=0.2)

    assert set(services) == {"postgres", "redis", "qdrant"}, (
        f"의존처 하나가 넘어지자 나머지 점검이 빠졌다: {sorted(services)}"
    )
    assert services["postgres"] == health_probe.TIMEOUT  # 공허진리 방지 — 실제로 태웠는지
