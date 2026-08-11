"""`run_async_batch` 계약 — 배치가 끝나면 커넥션 풀이 반드시 정리된다.

★2026-08-08 프로덕션 장애의 회귀 락이다. Celery 태스크가 `asyncio.run()` 으로 루프를 만들고
  닫는데 엔진 풀은 모듈 전역이라, 정리 없이 끝나면 **닫힌 루프에 묶인 연결**이 남아 서버에
  `idle in transaction`(마지막 쿼리 `BEGIN;`)으로 고착됐다. 매일 1건씩 16~17일 누적되어
  Supabase 트랜잭션 풀러 슬롯을 고갈시켰고 로그인 불가로 이어졌다.

  그래서 여기서 잠그는 것은 "코드가 예쁘게 생겼는가"가 아니라 **dispose 가 실제로 불렸는가**다.
"""

from __future__ import annotations

import sys
import types

import pytest

from app.tasks import _async_batch
from app.tasks._async_batch import run_async_batch


class _SpyEngine:
    def __init__(self) -> None:
        self.disposed = 0

    async def dispose(self) -> None:
        self.disposed += 1


@pytest.fixture
def spy_engines(monkeypatch: pytest.MonkeyPatch) -> list[_SpyEngine]:
    """`_ENGINES` 가 가리키는 자리에 스파이 엔진을 꽂는다."""
    engines: list[_SpyEngine] = []
    entries: list[tuple[str, str]] = []
    for i in range(2):
        mod_name = f"_spy_engine_mod_{i}"
        module = types.ModuleType(mod_name)
        engine = _SpyEngine()
        module.engine = engine  # type: ignore[attr-defined]
        sys.modules[mod_name] = module
        engines.append(engine)
        entries.append((mod_name, "engine"))
    monkeypatch.setattr(_async_batch, "_ENGINES", tuple(entries))
    return engines


def test_배치가_성공하면_엔진이_정리된다(spy_engines: list[_SpyEngine]) -> None:
    async def work() -> str:
        return "done"

    assert run_async_batch(work) == "done"
    assert [e.disposed for e in spy_engines] == [1, 1]


def test_배치가_실패해도_엔진이_정리된다(spy_engines: list[_SpyEngine]) -> None:
    """★예외 경로가 오히려 더 잘 샌다 — 실제 사고도 조용한 실패에서 누적됐다."""

    async def boom() -> None:
        raise ValueError("배치 실패")

    with pytest.raises(ValueError, match="배치 실패"):
        run_async_batch(boom)
    assert [e.disposed for e in spy_engines] == [1, 1]


def test_dispose_가_실패해도_배치_결과를_덮지_않는다(
    monkeypatch: pytest.MonkeyPatch, spy_engines: list[_SpyEngine]
) -> None:
    """정리 실패가 성공한 배치를 실패로 둔갑시키면 안 된다(운영 중 오탐 방지)."""

    async def explode() -> None:
        raise RuntimeError("dispose 불가")

    monkeypatch.setattr(spy_engines[0], "dispose", explode)

    async def work() -> int:
        return 42

    assert run_async_batch(work) == 42
    # 첫 엔진이 터져도 **나머지 엔진은 계속 정리**해야 한다(하나 실패로 전체가 새면 안 된다).
    assert spy_engines[1].disposed == 1


def test_팩토리는_매번_새_코루틴을_만든다() -> None:
    """코루틴 객체가 아니라 **팩토리**를 받는다 — 재시도 경로에서 두 번 await 하는 사고 방지."""
    calls: list[int] = []

    async def work() -> int:
        calls.append(1)
        return len(calls)

    assert run_async_batch(work) == 1
    assert run_async_batch(work) == 2


def test_계약이_가리키는_엔진들이_실제로_존재한다() -> None:
    """★목록형 상수의 공허화 방지 — `_ENGINES` 가 실재하지 않는 모듈만 가리키면
    dispose 는 늘 0회이고 이 파일의 다른 테스트는 스파이라서 그걸 못 본다."""
    import importlib

    found = 0
    for module_name, attr in _async_batch._ENGINES:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 — 배포 형태에 따라 없을 수 있다
            continue
        if getattr(module, attr, None) is not None:
            found += 1
    assert found >= 1, f"_ENGINES 가 실제 엔진을 하나도 못 찾는다: {_async_batch._ENGINES}"
