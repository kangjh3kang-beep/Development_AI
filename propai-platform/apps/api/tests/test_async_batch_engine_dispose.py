"""`run_async_batch` 계약 — 2026-08-08 프로덕션 장애의 회귀 락.

★사고 기전(재현으로 확인): Celery 배치가 `asyncio.run()` 으로 루프를 만들고 닫으면, 모듈
  전역 엔진 풀에 **죽은 루프에 묶인 연결**이 남는다. 다음 실행이 그 연결을 꺼내면
  `pool_pre_ping` 이 생사 검사를 위해 **`BEGIN` 을 서버로 보내고**, 응답 future 가 죽은
  루프라 끊긴다 → 서버에 **끝나지 않는 트랜잭션**(`idle in transaction`, 마지막 쿼리 `BEGIN;`)이
  고착. 누적되어 Supabase 트랜잭션 풀러 슬롯을 고갈시켰다.

★★이 파일이 잠그는 것은 "dispose 가 몇 번 불렸나"가 **아니다**. 적대검증이 실증했듯,
  횟수만 세면 **루프가 닫힌 뒤 새 루프에서 dispose 하는 틀린 처방도 통과한다**(죽은 루프에
  묶인 연결은 새 루프의 dispose 로 정리되지 않으므로 사고가 그대로다).
  진짜 불변식은 **"배치 본문과 같은, 아직 살아 있는 루프에서 정리했는가"** 다.
"""

from __future__ import annotations

import ast
import asyncio
import sys
import types
from pathlib import Path

import pytest

from app.tasks import _async_batch
from app.tasks._async_batch import run_async_batch


class _SpyEngine:
    """정리 시점의 **루프 정체**까지 기록한다 — 횟수만으로는 틀린 처방을 못 가른다."""

    def __init__(self) -> None:
        self.disposed = 0
        self.loop: asyncio.AbstractEventLoop | None = None
        self.loop_was_open: bool | None = None
        self.pool = types.SimpleNamespace(checkedout=lambda: 0)

    async def dispose(self) -> None:
        self.disposed += 1
        self.loop = asyncio.get_running_loop()
        self.loop_was_open = not self.loop.is_closed()


@pytest.fixture
def spy_engines(monkeypatch: pytest.MonkeyPatch) -> list[_SpyEngine]:
    engines: list[_SpyEngine] = []
    entries: list[tuple[str, str]] = []
    # ★속성명을 **일부러 다르게** 둔다 — 전부 `engine` 이면 구현이 `getattr(module, "engine")`
    #   으로 하드코딩돼도 통과한다(실제 저장소의 `timescale_engine` 이 영구 미정리가 된다).
    for i, attr in enumerate(("engine", "timescale_engine")):
        mod_name = f"_spy_engine_mod_{i}"
        module = types.ModuleType(mod_name)
        engine = _SpyEngine()
        setattr(module, attr, engine)
        sys.modules[mod_name] = module
        engines.append(engine)
        entries.append((mod_name, attr))
    monkeypatch.setattr(_async_batch, "_ENGINES", tuple(entries))
    return engines


def test_배치_본문과_같은_살아있는_루프에서_정리한다(spy_engines: list[_SpyEngine]) -> None:
    """★핵심 불변식 — 횟수가 아니라 **루프 동일성**이다."""
    seen: dict[str, asyncio.AbstractEventLoop] = {}

    async def work() -> str:
        seen["body"] = asyncio.get_running_loop()
        return "done"

    assert run_async_batch(work) == "done"
    for engine in spy_engines:
        assert engine.disposed == 1
        assert engine.loop is seen["body"], "배치 본문과 **다른 루프**에서 정리했다 — 사고가 안 고쳐진다"
        assert engine.loop_was_open is True, "**이미 닫힌 루프**에서 정리했다 — 사고가 안 고쳐진다"


def test_배치가_실패해도_정리한다(spy_engines: list[_SpyEngine]) -> None:
    """★예외 경로가 오히려 더 잘 샌다 — 실제 사고도 조용한 실패에서 누적됐다."""

    async def boom() -> None:
        raise ValueError("배치 실패")

    with pytest.raises(ValueError, match="배치 실패"):
        run_async_batch(boom)
    assert [e.disposed for e in spy_engines] == [1, 1]


def test_정리_실패가_배치_결과를_덮지_않는다(
    monkeypatch: pytest.MonkeyPatch, spy_engines: list[_SpyEngine]
) -> None:
    async def explode() -> None:
        raise RuntimeError("dispose 불가")

    monkeypatch.setattr(spy_engines[0], "dispose", explode)

    async def work() -> int:
        return 42

    assert run_async_batch(work) == 42
    # 하나가 터져도 **나머지는 계속 정리**해야 한다.
    assert spy_engines[1].disposed == 1


def test_본문이_RuntimeError_를_던져도_두_번_실행하지_않는다(spy_engines: list[_SpyEngine]) -> None:
    """★종전 `except RuntimeError` 폴백이 배치를 **재실행**했다. 경공매 전국 수집·대량필지
    배치(과금 게이트)·append-only 원장이 두 번 도는 위험이었다."""
    calls: list[int] = []

    async def boom() -> None:
        calls.append(1)
        raise RuntimeError("업무 로직이 던진 RuntimeError")

    with pytest.raises(RuntimeError, match="업무 로직"):
        run_async_batch(boom)
    assert len(calls) == 1, f"배치가 {len(calls)}회 실행됐다 — 재실행 위험이 살아 있다"


def test_러닝_루프_안에서는_시끄럽게_거절한다() -> None:
    """★종전 폴백은 이 상황에서 **작동조차 못 하면서**(러닝 루프 안 run_until_complete 불가)
    미-await 코루틴 경고까지 남겼다. 조용한 오작동 대신 명시적 거절로 바꿨다."""

    async def outer() -> None:
        async def work() -> int:
            return 1

        with pytest.raises(RuntimeError, match="동기 컨텍스트 전용"):
            run_async_batch(work)

    asyncio.run(outer())


def test_팩토리는_매번_새_코루틴을_만든다() -> None:
    calls: list[int] = []

    async def work() -> int:
        calls.append(1)
        return len(calls)

    assert run_async_batch(work) == 1
    assert run_async_batch(work) == 2


def test_반납되지_않은_연결이_있으면_경고로_드러난다(
    spy_engines: list[_SpyEngine], caplog: pytest.LogCaptureFixture
) -> None:
    """★`dispose()` 는 **체크아웃 중인 연결을 닫지 않는다** — 배치가 연결을 쥔 채 끝나거나
    백그라운드 태스크가 남으면 그 연결은 여전히 샌다. 막지 못하는 경로를 **조용히 두면**
    다음 사고도 사용자 신고로 알게 된다(이번이 그랬다). 그래서 경고 자체를 잠근다."""
    spy_engines[0].pool = types.SimpleNamespace(checkedout=lambda: 2)

    async def work() -> None:
        return None

    with caplog.at_level("WARNING"):
        run_async_batch(work)

    warned = [r for r in caplog.records if "반납되지 않은 연결" in r.getMessage()]
    assert warned, "체크아웃 잔여를 경고하지 않는다 — 누수가 다시 조용해진다"
    assert "2" in warned[0].getMessage(), "잔여 **개수**를 알려주지 않으면 심각도를 못 잰다"


def test_계약에_풀드_엔진이_최소_하나_실재한다() -> None:
    """★"엔진을 하나 이상 찾았다"로는 부족하다 — 이 저장소 엔진 4개 중 **3개가 `NullPool`**
    이고 `NullPool.dispose()` 는 문자 그대로 `pass` 다. 즉 **유일한 풀드 엔진이 목록에서
    이탈해도** 그런 검사는 통과하고 프로덕션 누수는 그대로 돌아온다(적대검증 실증)."""
    import importlib

    from sqlalchemy.pool import NullPool

    pooled: list[str] = []
    for module_name, attr in _async_batch._ENGINES:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 — 배포 형태에 따라 없을 수 있다
            continue
        engine = getattr(module, attr, None)
        if engine is None:
            continue
        # ★`not isinstance(None, NullPool)` 는 **참**이다 — `.pool` 이 없는 객체(엔진이
        #   아닌 것)가 "풀드"로 계수돼, 실효 엔진을 빼도 통과했다(적대검증 실증).
        pool = getattr(engine, "pool", None)
        if pool is not None and not isinstance(pool, NullPool):
            pooled.append(f"{module_name}.{attr}")

    assert pooled, (
        "_ENGINES 에 **풀드 엔진이 하나도 없다** — dispose 가 전부 no-op 이라 "
        f"정리가 실효를 잃었다: {_async_batch._ENGINES}"
    )


# 루프를 **직접 만들거나 직접 돌리는** API 이름.
# ★`run_until_complete` 를 빠뜨리면 안 된다 — R1 이 방금 제거한 폴백이 쓰던 바로 그 API 다.
#   그 이름을 안 보는 락은 "고친 것을 되돌리는 형태"를 못 잡는다.
_LOOP_MAKERS = {"run", "new_event_loop", "run_until_complete", "Runner", "set_event_loop"}


def _asyncio_aliases(tree: ast.AST) -> set[str]:
    """`import asyncio as aio` 같은 **별칭**을 모은다 — 별칭 하나로 락을 우회할 수 있다."""
    names = {"asyncio"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "asyncio" and alias.asname:
                    names.add(alias.asname)
    return names


def _loop_makers_in(path: Path) -> list[str]:
    """파일이 **직접 루프를 만들거나 돌리는** 자리를 돌려준다.

    ★네 형태를 모두 본다(각각 실측으로 우회가 확인된 것들이다):
      ① `asyncio.run(...)`                    — 속성 호출
      ② `from asyncio import run`             — 직접 임포트(임포트 한 줄로 우회)
      ③ `import asyncio as aio` → `aio.run()` — 별칭
      ④ `asyncio.get_event_loop().run_until_complete(...)` — 호출 결과에 대한 속성 호출
    """
    found: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    aliases = _asyncio_aliases(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "asyncio":
            for alias in node.names:
                if alias.name in _LOOP_MAKERS:
                    found.append(f"{path.name}:{node.lineno} from asyncio import {alias.name}")
            continue
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _LOOP_MAKERS:
            continue
        owner = node.func.value
        # ①③ `asyncio.run` / `aio.run`
        if isinstance(owner, ast.Name) and owner.id in aliases:
            found.append(f"{path.name}:{node.lineno} {owner.id}.{node.func.attr}")
        # ④ `<무엇이든>().run_until_complete(...)` — 루프 객체를 받아 직접 돌리는 형태.
        #   소유자를 특정하지 않는다: 루프를 어디서 얻었든 직접 돌리면 같은 결함이다.
        elif node.func.attr in {"run_until_complete", "run_forever"}:
            found.append(f"{path.name}:{node.lineno} <loop>.{node.func.attr}")
    return found


def test_루프_생성은_공용_진입점에서만_한다() -> None:
    """★배선 락 — `app/` **전역**에서 루프를 만들거나 직접 돌리는 곳은 `_async_batch.py`
    하나뿐이어야 한다.

    ★종전에는 "`run_async_batch` 를 임포트한 파일"로 소비처를 **파생**했는데, 그 모집단은
      **자기배제로 뚫린다**: 되돌리는 사람은 ruff `F401`(unused import) 때문에 그 임포트를
      **반드시 지우게 되고**, 지우는 순간 모집단에서 빠져나간다. lint 가 우회를 강제하는
      구조였다(적대검증 실증 — import 를 남긴 변종만 잡히고 지운 변종은 생존).

    ★그래서 모집단을 **소비처가 아니라 `app/` 전체**로 바꾼다. 실측상 루프를 만드는 파일은
      진입점 하나뿐이므로(측정이 설계를 정했다), 목록도 파생도 필요 없이 **전역 불변식**이
      성립한다. 어느 파일이 어떤 형태로 되돌리든, 임포트가 있든 없든 잡힌다.
    """
    app_root = Path(_async_batch.__file__).resolve().parent.parent  # .../apps/api/app
    offenders: list[str] = []
    scanned = 0

    for path in sorted(app_root.rglob("*.py")):
        if path.resolve() == Path(_async_batch.__file__).resolve():
            continue
        scanned += 1
        try:
            offenders.extend(_loop_makers_in(path))
        except SyntaxError:  # noqa: PERF203 — 파싱 불가 파일은 이 계약의 대상이 아니다
            continue

    # 공허 진리 방지 — 경로가 어긋나 0개를 훑고 통과하는 것을 막는다.
    # (실제로 `.resolve()` 누락으로 스캔이 통째로 비었던 적이 있다.)
    assert scanned >= 100, f"`app/` 를 {scanned}개만 훑었다 — 경로가 어긋났다"
    assert offenders == [], (
        "공용 진입점을 우회해 루프를 직접 만든다 — 커넥션 누수가 돌아온다:\n"
        + "\n".join(offenders)
    )
