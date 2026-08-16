"""배선 락 — 라우터가 **실제로** 과금 멱등 가드를 태우는가.

`test_charge_idempotency.py` 는 모듈(선점·정산·충돌)을 잠근다. 그것만으로는 부족하다 —
이 저장소가 반복해서 데인 형태가 **"로직은 고쳤는데 요청 경로에서 안 불린다"** 이기 때문이다
(정의만 하고 소비처 0). 그래서 여기서는 **라우터 핸들러를 직접 태우고**, 과금 헬퍼가
몇 번 불렸는지를 센다. 실 Postgres 위에서 돈다.

★스텁을 쓰되 **검증 대상 층은 우회하지 않는다**: 스파이로 바꾸는 것은 `billing` 호출뿐이고,
  헤더 추출 → `reserve` → `guard.billable` → 과금 분기까지는 전부 진짜다.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

from app.core import charge_idempotency as ci

# ★게이트 조건은 `CI` 가 아니라 **`TEST_PG_DSN` 의 존재**다(형제 파일과 같은 이유):
#   `CI=true` 는 내가 확인하지 않은 전제이고, 틀리면 락이 조용히 skip 된다.
_EXPLICIT_DSN = os.environ.get("TEST_PG_DSN")
_DSN = _EXPLICIT_DSN or "postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5432/propai_db"


def _req(idem_key: str | None = None):
    """진짜 Request — 가짜 객체는 slowapi 가 거부한다(형제 테스트와 같은 이유)."""
    from starlette.requests import Request as _R

    headers = [(b"idempotency-key", idem_key.encode())] if idem_key else []
    return _R({
        "type": "http", "method": "POST", "path": "/",
        "headers": headers, "client": ("127.0.0.1", 0), "query_string": b"",
    })


class _User:
    """`CurrentUser` 계약 그대로 — 테스트마다 새 사용자라 키 공간이 겹치지 않는다."""

    def __init__(self) -> None:
        self.user_id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()


@pytest.fixture(autouse=True)
def _require_pg(monkeypatch: pytest.MonkeyPatch):
    """실 DB 가 없으면 이 락은 fail-open 으로 **아무것도 검증하지 않는다** → CI 에서는 fail."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def _probe() -> str | None:
        engine = create_async_engine(_DSN)
        try:
            async with async_sessionmaker(engine)() as s:
                await s.execute(text("SELECT 1"))
            return None
        except Exception as e:  # noqa: BLE001
            return str(e)[:200]
        finally:
            await engine.dispose()

    err = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_probe())
    if err:
        msg = f"Postgres 미가용({_DSN}): {err}"
        if _EXPLICIT_DSN:
            pytest.fail(f"TEST_PG_DSN 이 설정됐는데 붙지 못했다 — 배선 락이 fail-open 으로 공허해진다. {msg}")
        pytest.skip(msg)

    # ★라우터의 과금 헬퍼는 자체 세션을 열지만, 가드는 `async_session_factory` 를 쓴다.
    #   테스트 DSN 을 그 팩토리에 주입해 **가드가 실제 DB 를 태우게** 한다.
    from sqlalchemy.ext.asyncio import async_sessionmaker as _mk
    from sqlalchemy.ext.asyncio import create_async_engine as _mkeng

    import app.core.database as db_mod

    monkeypatch.setattr(db_mod, "async_session_factory", _mk(_mkeng(_DSN), expire_on_commit=False))
    ci._SCHEMA_READY = False


def _patch_charges(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """과금 호출을 세는 스파이 — 이 목록의 길이가 곧 청구 횟수다."""
    import routers.registry as rr

    calls: list[str] = []

    async def _issue(user_id: Any, result: Any, times: Any = None) -> None:
        if rr.issued_count(result):
            calls.append("issue")

    async def _analysis(user_id: Any, result: Any) -> Any:
        if rr.analysis_charged(result):
            calls.append("analysis")
        return None

    monkeypatch.setattr(rr, "_charge_registry_issue", _issue)
    monkeypatch.setattr(rr, "_charge_registry_analysis", _analysis)
    return calls


def _patch_bulk_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """발급 성공 1건을 내는 서비스 — 과금 대상이 실제로 존재하게 만든다(공허 진리 방지)."""
    import routers.registry as rr

    class _Svc:
        async def bulk(self, items: Any) -> dict[str, Any]:
            return {"results": [{"status": "ok", "origin": "hyphen"}]}

    monkeypatch.setattr(rr, "RegistryService", _Svc)


async def _call_bulk(key: str | None, user: _User, addresses: list[str]):
    import routers.registry as rr

    return await rr.registry_bulk(
        _req(key),
        rr.RegistryBulkRequest(addresses=addresses),
        current_user=user,
    )


@pytest.mark.asyncio
async def test_키_없으면_종전대로_과금한다(monkeypatch: pytest.MonkeyPatch):
    """하위호환 — 헤더를 안 보내는 기존 클라이언트의 동작이 바뀌면 안 된다."""
    calls = _patch_charges(monkeypatch)
    _patch_bulk_ok(monkeypatch)
    u = _User()

    await _call_bulk(None, u, ["서울특별시 강남구 역삼동 737"])
    await _call_bulk(None, u, ["서울특별시 강남구 역삼동 737"])

    assert calls == ["issue", "issue"], f"키가 없는데 과금이 줄었다: {calls}"


@pytest.mark.asyncio
async def test_같은_키_순차_2회는_한_번만_청구된다(monkeypatch: pytest.MonkeyPatch):
    """★이 PR 의 본론 — 재전송이 이중청구가 되지 않는다."""
    calls = _patch_charges(monkeypatch)
    _patch_bulk_ok(monkeypatch)
    u, key = _User(), f"k-{uuid.uuid4()}"

    await _call_bulk(key, u, ["서울특별시 강남구 역삼동 737"])
    await _call_bulk(key, u, ["서울특별시 강남구 역삼동 737"])

    assert calls == ["issue"], f"같은 키 2회에 {len(calls)}회 청구됐다 — 이중청구: {calls}"


@pytest.mark.asyncio
async def test_다른_키_2회는_두_번_청구된다(monkeypatch: pytest.MonkeyPatch):
    """★대조군 — 이게 없으면 '멱등성'과 '그냥 과금 안 함'을 구분할 수 없다.

    두 모집단이 **다른 값**을 내야 잠금이다(CLAUDE.md — 차가 0인 픽스처는 잠금이 아니다).
    """
    calls = _patch_charges(monkeypatch)
    _patch_bulk_ok(monkeypatch)
    u = _User()

    await _call_bulk(f"k-{uuid.uuid4()}", u, ["서울특별시 강남구 역삼동 737"])
    await _call_bulk(f"k-{uuid.uuid4()}", u, ["서울특별시 강남구 역삼동 737"])

    assert calls == ["issue", "issue"], f"다른 키인데 청구가 줄었다 — 매출 누수: {calls}"


@pytest.mark.asyncio
async def test_같은_키_다른_요청은_422(monkeypatch: pytest.MonkeyPatch):
    from fastapi import HTTPException

    _patch_charges(monkeypatch)
    _patch_bulk_ok(monkeypatch)
    u, key = _User(), f"k-{uuid.uuid4()}"

    await _call_bulk(key, u, ["서울특별시 강남구 역삼동 737"])
    with pytest.raises(HTTPException) as ei:
        await _call_bulk(key, u, ["서울특별시 강남구 역삼동 738"])
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_처리_중인_키가_또_오면_409(monkeypatch: pytest.MonkeyPatch):
    """★넷째 모집단 — 저장 기반 방식이 놓치는 동시 이중청구.

    첫 요청이 **아직 안 끝난** 상태를 만들기 위해, 서비스가 매달려 있는 동안 두 번째를 부른다.
    """
    import asyncio

    from fastapi import HTTPException

    calls = _patch_charges(monkeypatch)
    import routers.registry as rr

    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowSvc:
        async def bulk(self, items: Any) -> dict[str, Any]:
            started.set()
            await release.wait()
            return {"results": [{"status": "ok", "origin": "hyphen"}]}

    monkeypatch.setattr(rr, "RegistryService", _SlowSvc)
    u, key = _User(), f"k-{uuid.uuid4()}"

    first = asyncio.create_task(_call_bulk(key, u, ["서울특별시 강남구 역삼동 737"]))
    await asyncio.wait_for(started.wait(), timeout=5)

    # ★`wait_for` 로 감싼다 — 선점이 깨지면 두 번째 요청이 409 대신 `_SlowSvc` 안에서
    #   **영원히 매달린다**(변이 실측: 그 상태로 스위트가 통째로 멈췄다). 잠금이 hang 으로
    #   나타나면 CI 는 타임아웃까지 끌려가고 원인도 안 보인다 — 빠르게 빨개지게 만든다.
    try:
        with pytest.raises(HTTPException) as ei:
            await asyncio.wait_for(
                _call_bulk(key, u, ["서울특별시 강남구 역삼동 737"]), timeout=5
            )
    except TimeoutError:
        release.set()
        await first
        pytest.fail("두 번째 요청이 409 로 튕기지 않고 본작업에 진입했다 — 선점이 깨졌다")
    assert ei.value.status_code == 409, "처리 중인 키를 두 번째 요청이 그대로 실행했다"

    release.set()
    await first
    assert calls == ["issue"], f"동시 요청으로 {len(calls)}회 청구됐다: {calls}"


@pytest.mark.asyncio
async def test_실패한_요청은_키를_잠그지_않는다(monkeypatch: pytest.MonkeyPatch):
    """실패는 재시도의 가장 흔한 이유다 — 그 재시도를 우리가 409 로 막으면 안 된다."""
    calls = _patch_charges(monkeypatch)
    import routers.registry as rr

    class _Boom:
        async def bulk(self, items: Any) -> dict[str, Any]:
            raise RuntimeError("프로바이더 장애")

    monkeypatch.setattr(rr, "RegistryService", _Boom)
    u, key = _User(), f"k-{uuid.uuid4()}"

    with pytest.raises(RuntimeError):
        await _call_bulk(key, u, ["서울특별시 강남구 역삼동 737"])

    _patch_bulk_ok(monkeypatch)
    await _call_bulk(key, u, ["서울특별시 강남구 역삼동 737"])
    assert calls == ["issue"], f"실패 후 재시도가 청구되지 않았다: {calls}"
