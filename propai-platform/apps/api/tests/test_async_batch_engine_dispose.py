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
import threading
import types
from pathlib import Path

import pytest

from app.tasks import _async_batch
from app.tasks._async_batch import run_async_batch


class _SpyEngine:
    """정리 시점의 **루프 정체**와 **`close` 인자**까지 기록한다 — 횟수만으로는 틀린 처방을 못 가른다.

    ★시그니처는 실제 `AsyncEngine.dispose(close=True)` 와 **같아야** 한다. 종전 스파이는
      `close` 를 안 받아서 `dispose(close=False)` 변이를 **엉뚱한 이유로** 잡았다:
      TypeError 가 `_dispose_engines` 의 except 에 삼켜져 카운터가 0이 됐을 뿐이다.
      **우연한 적발은 잠금이 아니다** — 스파이 시그니처를 실제와 맞추는 순간 그 변이는
      전부 생존한다(실측). 그래서 시그니처를 맞추고 **`close` 값 자체를 단언**한다.
    """

    def __init__(self) -> None:
        self.disposed = 0
        self.loop: asyncio.AbstractEventLoop | None = None
        self.loop_was_open: bool | None = None
        self.close_arg: bool | None = None
        self.pool = types.SimpleNamespace(checkedout=lambda: 0)

    async def dispose(self, close: bool = True) -> None:
        self.disposed += 1
        self.close_arg = close
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
        # ★`dispose(close=False)` 는 풀만 갈아치우고 **소켓을 닫지 않는다**(fork 용 옵션).
        #   그러면 죽은 루프에 묶인 연결이 서버 쪽에 그대로 남아 사고가 안 고쳐진다.
        #   실제 엔진 케이스는 이걸 **못 잡는다**(풀 교체는 close 와 무관하게 일어난다) —
        #   그래서 여기서 인자 자체를 잠근다.
        assert engine.close_arg is True, (
            "정리가 `close=False` 로 불렸다 — 풀은 갈리지만 **연결은 닫히지 않아** "
            "죽은 루프에 묶인 소켓이 서버에 그대로 남는다"
        )


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
# ★`run_until_complete` 를 빠뜨리면 안 된다 — R1 이 제거한 폴백이 쓰던 바로 그 API 다.
_LOOP_MAKERS = {
    "run", "new_event_loop", "run_until_complete", "run_forever", "Runner", "set_event_loop",
    # ★독립 적대검증이 실측한 우회 — 루프 객체를 직접 만든다.
    "SelectorEventLoop", "ProactorEventLoop",
}

# ★`get_event_loop` 는 **일부러 뺐다** — 위양성이 실측됐다(CLAUDE.md §A-6 "가드의 위양성도
#   결함이다"). `photoreal_render_service.py:312·337` 은 async 함수 안에서
#   `asyncio.get_event_loop().time()` 로 **시계만 읽는다** — 러닝 루프가 있으면 그것을 돌려줄
#   뿐 새 루프를 만들지 않는다. 진짜 위험한 형태(`get_event_loop().run_until_complete(...)`)는
#   아래 ④ 분기가 **소유자와 무관하게** 이미 잡는다. 넣었다가 정상 코드 2곳을 막았다.

# 새 루프를 만들어 코루틴을 **돌리는** 서드파티 진입점 — (모듈 뿌리, 호출명) 쌍.
# ★임포트 자체를 위반으로 보면 안 된다(위양성 실측): `termination_cert.py` 는 `anyio` 를
#   `anyio.to_thread.run_sync` 로만 쓴다 — 그건 스레드 오프로드지 루프 생성이 아니다.
#   같은 이유로 `asgiref` 의 `sync_to_async` 도 무해하다. **호출 이름으로 가른다.**
_THIRD_PARTY_LOOP_RUNNERS = {
    ("anyio", "run"),
    ("uvloop", "run"),
    ("uvloop", "install"),
    ("asgiref", "async_to_sync"),
    ("nest_asyncio", "apply"),
}


def _asyncio_aliases(tree: ast.AST) -> set[str]:
    """asyncio 를 가리키는 **모든 이름**을 모은다 — 이름 하나로 락을 우회할 수 있다.

    ★세 형태를 본다(전부 독립 적대검증이 우회로 실증한 것):
      · `import asyncio as aio`                 → aio
      · `import asyncio.runners as r`           → r        (서브모듈 별칭)
      · `from asyncio import runners`           → runners  (서브모듈 직접 임포트)
      · `_a = asyncio`                          → _a       (모듈 재바인딩)
    """
    names = {"asyncio"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "asyncio" or alias.name.startswith("asyncio."):
                    names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "asyncio":
            for alias in node.names:
                # `from asyncio import runners` — 이름 자체가 asyncio 서브모듈이다.
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            # `_a = asyncio` — 재바인딩. 오른쪽이 이미 별칭이면 왼쪽도 별칭이 된다.
            if node.value.id in names:
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _attr_root(node: ast.AST) -> str | None:
    """`a.b.c.d` 의 **뿌리 이름** `a` 를 돌려준다(중간 속성이 몇 겹이든).

    ★종전 락은 소유자가 `ast.Name` 일 때만 봤다 — 그래서 `asyncio.runners.Runner()` 처럼
      **한 겹만 깊어져도 통째로 빠져나갔다**(실측 확인된 우회).
    """
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _loop_makers_in(path: Path) -> list[str]:
    """파일이 **직접 루프를 만들거나 돌리는** 자리를 돌려준다.

    ★★이 함수의 커버리지를 **과대 주장하지 않는다**(CLAUDE.md §C-11 "면역을 거짓 주장하지
      마라"). 종전 주석은 "어느 파일이 어떤 형태로 되돌리든 잡힌다"고 단정했는데 **거짓이었다** —
      독립 적대검증이 17형태 중 11개를 통과시켰다. 아래는 지금 **실제로** 보는 것과
      **여전히 못 보는 것**이다.

    본다:
      ① `asyncio.run(...)` · `aio.run(...)`            — 별칭 포함
      ② `from asyncio import run`                      — 직접 임포트
      ③ `asyncio.runners.Runner().run(...)`            — 속성 체인(뿌리까지 평탄화)
      ④ `<무엇이든>().run_until_complete/run_forever`   — 루프 객체를 받아 직접 돌리는 형태
      ⑤ `anyio.run` · `uvloop.run/install` · `asgiref…async_to_sync` · `nest_asyncio.apply`
         — 서드파티 루프 실행기. ★**호출 이름으로 가른다**(임포트로 가르면 위양성).
      ⑥ `_a = asyncio` 재바인딩

    ★여전히 못 본다(정직):
      · `getattr(asyncio, "run")(...)` — 동적 속성 접근
      · `exec("asyncio.run(...)")`     — 문자열 실행
      정적 AST 로는 원리적으로 불가하다. 이 두 형태를 쓰는 우회는 이 락으로 못 막는다.
    """
    found: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    aliases = _asyncio_aliases(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # ★`node.module == "asyncio"` 로만 비교하면 `from asyncio.runners import Runner` 가
            #   통과한다 — 뿌리로 비교한다.
            if module.split(".")[0] == "asyncio":
                for alias in node.names:
                    if alias.name in _LOOP_MAKERS:
                        found.append(
                            f"{path.name}:{node.lineno} from {module} import {alias.name}"
                        )
                continue
            # ⑤ `from anyio import run` 처럼 **실행기 이름을 직접** 들여오는 형태만 잡는다.
            root = module.split(".")[0]
            for alias in node.names:
                if (root, alias.name) in _THIRD_PARTY_LOOP_RUNNERS:
                    found.append(f"{path.name}:{node.lineno} from {module} import {alias.name}")
            continue
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        root = _attr_root(owner)
        # ⑤ 서드파티 실행기 — (뿌리 모듈, 호출명) 쌍으로 판정한다.
        if root is not None and (root, node.func.attr) in _THIRD_PARTY_LOOP_RUNNERS:
            found.append(f"{path.name}:{node.lineno} {root}.{node.func.attr}")
            continue
        if node.func.attr not in _LOOP_MAKERS:
            continue
        # ①③⑥ 뿌리가 asyncio 별칭이면 몇 겹이든 잡는다.
        if root is not None and root in aliases:
            found.append(f"{path.name}:{node.lineno} {root}….{node.func.attr}")
        # ④ 루프 객체를 어디서 얻었든 **직접 돌리면** 같은 결함이다(소유자 무관).
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
      성립한다.

    ★★**범위를 정직하게 적는다**(CLAUDE.md §D-20). 이 락의 모집단은 `apps/api/app/` 이고,
      그 **밖**(`database/migrations/env.py`·`database/seeds/`·`ml/`·`scripts/`)에는
      `asyncio.run` 이 7곳 있다. 전부 1회성 CLI·alembic 이라 프로세스가 끝나며 죽으므로
      이 결함 클래스가 아니다 — 하지만 "전역에 하나뿐"이라는 문장이 그 밖까지 뜻하지는 않는다.
      못 잡는 형태(동적 `getattr`·`exec`)는 `_loop_makers_in` 주석에 적었다.
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
    # ★하한 100 은 **7.75배 느슨했다** — `app/` 실제 파일은 775개다. 스캔이 87% 붕괴해도
    #   통과하는 하한은 잠금이 아니다(독립 적대검증 지적). 실측치에 붙여 다시 건다.
    assert scanned >= 600, f"`app/` 를 {scanned}개만 훑었다 — 경로가 어긋났다(실측 775개)"
    assert offenders == [], (
        "공용 진입점을 우회해 루프를 직접 만든다 — 커넥션 누수가 돌아온다:\n"
        + "\n".join(offenders)
    )


# ── 정리 前 자식 태스크 배수 ──────────────────────────────────────────────
# ★이 두 케이스가 잠그는 것: `dispose()` 는 **풀에 반납된** 연결만 닫는다. 배치가
#   `create_task` 로 띄운 자식이 DB 를 쥔 채 남아 있으면 정리는 그것을 못 닫고, 곧이어
#   `asyncio.run` 이 루프를 닫으며 **쿼리 도중 취소**한다 = 서버에 트랜잭션이 남는다.
#   종전 이 모듈은 그 상황을 **경고로 알리기만 했다**(탐지≠교정).


def test_배치가_띄운_자식_태스크를_정리_전에_기다린다(spy_engines: list[_SpyEngine]) -> None:
    """★정리 시점에 자식이 **이미 끝나 있어야** 한다 — "끝났는지"를 dispose 안에서 기록한다.

    ★"자식이 결국 끝났다"를 배치 밖에서 확인하는 것으로는 부족하다: 배수를 없애도
      취소 전에 우연히 끝날 수 있다. 순서를 잠그려면 **정리 시점의 상태**를 봐야 한다.
    """
    child_done: list[bool] = []

    async def _child() -> None:
        await asyncio.sleep(0.05)
        child_done.append(True)

    async def _body() -> str:
        asyncio.ensure_future(_child())  # noqa: RUF006 — 참조 보관은 이 테스트의 관심이 아니다
        return "ok"

    # dispose 가 불리는 **그 순간** 자식이 끝나 있었는지 기록한다.
    seen_at_dispose: list[bool] = []
    original = _SpyEngine.dispose

    async def _recording_dispose(self: _SpyEngine) -> None:
        seen_at_dispose.append(bool(child_done))
        await original(self)

    _SpyEngine.dispose = _recording_dispose  # type: ignore[method-assign]
    try:
        assert run_async_batch(lambda: _body()) == "ok"
    finally:
        _SpyEngine.dispose = original  # type: ignore[method-assign]

    assert seen_at_dispose, "dispose 가 불리지 않았다 — 이 케이스가 공허해졌다"
    assert all(seen_at_dispose), (
        "정리 시점에 자식 태스크가 아직 살아 있었다 — 루프가 닫히며 취소되고,"
        " DB 를 쥐고 있었다면 서버에 트랜잭션이 남는다"
    )


def test_자식이_상한을_넘으면_포기하고_경고한다(
    spy_engines: list[_SpyEngine], caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★상한이 없으면 "누수를 막으려다 배치를 멈추는" 새 결함이 된다 — 포기 경로를 잠근다.

    ★상한은 **호출 시점에** 읽어야 한다: 기본 인자로 굳히면 이 monkeypatch 가 무시돼
      테스트가 실제 경로를 못 태운다(값이 장식이 되는 형태).

    ★★**별도 스레드에서 돌려 join 으로 판정한다.** 여기서 그냥 호출하면, 상한을 잃은 변이가
      이 케이스를 **실패시키는 게 아니라 영원히 멈추게** 한다(`asyncio.wait(timeout=None)`).
      실제로 변이 도구가 이 형태에서 900초 상한에 걸려 **결과 없이 SIGTERM** 으로 죽었다 —
      멈추는 테스트는 CI 를 세우고, 무엇보다 **변이가 잡혔는지 알 수 없게 만든다**.
      daemon 스레드라 설령 멈춰도 pytest 종료를 막지 않는다.
    """
    monkeypatch.setattr(_async_batch, "_CHILD_DRAIN_TIMEOUT_SEC", 0.01)

    async def _never() -> None:
        await asyncio.sleep(3600)

    async def _body() -> str:
        task = asyncio.ensure_future(_never())
        task.set_name("느린-자식")
        return "ok"

    outcome: dict[str, object] = {}

    def _run() -> None:
        try:
            outcome["value"] = run_async_batch(lambda: _body())
        except BaseException as exc:  # noqa: BLE001 — 스레드 밖으로 그대로 옮겨 판정한다
            outcome["error"] = exc

    with caplog.at_level("WARNING", logger=_async_batch.__name__):
        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=10.0)

    assert not worker.is_alive(), (
        "상한이 무시돼 배치가 자식을 무한정 기다린다 — 누수를 막으려다 배치를 멈추는 결함이다"
    )
    assert "error" not in outcome, f"배치가 예외로 끝났다: {outcome.get('error')!r}"
    assert outcome.get("value") == "ok"  # ★포기하되 배치 결과는 그대로 돌려준다

    # ★`getMessage()` 로 **최종 문구**를 본다 — 포맷 인자에 담긴 태스크 이름이 실제로 문구에
    #   들어갔는지까지 봐야, "경고는 찍는데 무엇이 남았는지 안 알려주는" 형태가 걸린다.
    messages = [r.getMessage() for r in caplog.records]
    assert any("느린-자식" in m for m in messages), (
        f"상한 초과를 조용히 넘겼다 — 막지 못한 것은 드러나야 한다: {messages}"
    )
    # 포기해도 정리 자체는 반드시 한다.
    assert all(e.disposed == 1 for e in spy_engines)


def test_손자_태스크도_정리_전에_기다린다(spy_engines: list[_SpyEngine]) -> None:
    """★한 번만 스냅샷하면 **손자가 빠져나간다** — 자식이 끝나며 또 자식을 띄우는 형태다.

    ★자식이 **끝난 뒤에** 손자를 띄우게 만든다: 자식과 동시에 존재하면 첫 스냅샷에 함께
      잡혀, 재스냅샷이 없어도 통과한다(공허해진다).
    """
    grandchild_done: list[bool] = []

    async def _grandchild() -> None:
        await asyncio.sleep(0.05)
        grandchild_done.append(True)

    async def _child() -> None:
        await asyncio.sleep(0.05)
        asyncio.ensure_future(_grandchild())  # noqa: RUF006 — 첫 스냅샷 **이후**에 태어난다

    async def _body() -> str:
        asyncio.ensure_future(_child())  # noqa: RUF006
        return "ok"

    seen_at_dispose: list[bool] = []
    original = _SpyEngine.dispose

    async def _recording_dispose(self: _SpyEngine) -> None:
        seen_at_dispose.append(bool(grandchild_done))
        await original(self)

    _SpyEngine.dispose = _recording_dispose  # type: ignore[method-assign]
    try:
        assert run_async_batch(lambda: _body()) == "ok"
    finally:
        _SpyEngine.dispose = original  # type: ignore[method-assign]

    assert seen_at_dispose, "dispose 가 불리지 않았다 — 이 케이스가 공허해졌다"
    assert all(seen_at_dispose), (
        "정리 시점에 **손자** 태스크가 아직 살아 있었다 — 한 겹 아래로 같은 누수가 새어 나간다"
    )


# ── 독립 적대검증이 적발한 무잠금 4건 ────────────────────────────────────
# ★이 파일은 한때 "설명할 수 없는 변이 생존 0건"을 주장했다. **거짓이었다** —
#   도구가 만든 18개만 감사하고 그것을 자기 커버리지로 착각한 형태다
#   (CLAUDE.md §5 가 경고한 바로 그 착각). 아래는 손으로 찾아낸 생존들의 락이다.


def test_배수가_실패해도_엔진은_정리한다(
    spy_engines: list[_SpyEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    """★`finally` 안에서 배수가 던지면 `_dispose_engines()` 에 **도달조차 못 한다** —
    이 모듈이 막으려던 누수가 그대로 돌아오고, 원래 배치 예외까지 가려진다.

    `_dispose_engines` 는 엔진별 try/except 로 그 대칭을 갖고 있었는데 **앞에 끼워 넣은
    배수에는 없었다**. 재현으로 적발됐다(배수 OSError → dispose 0회 · ValueError 가 OSError 로 뒤바뀜).
    """

    async def _explode(*_a: object, **_k: object) -> int:
        raise OSError("배수 중 사고")

    monkeypatch.setattr(_async_batch, "_drain_child_tasks", _explode)

    async def _body() -> str:
        return "ok"

    assert run_async_batch(lambda: _body()) == "ok"
    assert all(e.disposed == 1 for e in spy_engines), (
        "배수가 던지자 정리가 건너뛰어졌다 — 누수가 그대로 돌아온다"
    )


def test_배수_실패가_원래_배치_예외를_덮지_않는다(
    spy_engines: list[_SpyEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    """★진짜 실패 원인이 배수 예외로 **뒤바뀌면** 진단을 잃는다. 두 축을 따로 잠근다."""

    async def _explode(*_a: object, **_k: object) -> int:
        raise OSError("배수 중 사고")

    monkeypatch.setattr(_async_batch, "_drain_child_tasks", _explode)

    async def _body() -> str:
        raise ValueError("진짜 배치 실패")

    with pytest.raises(ValueError, match="진짜 배치 실패"):
        run_async_batch(lambda: _body())
    assert all(e.disposed == 1 for e in spy_engines)


def test_취소된_자식이_있어도_정리는_끝까지_간다(spy_engines: list[_SpyEngine]) -> None:
    """★`task.exception()` 은 **취소된 태스크에서 CancelledError 를 던진다**. 그래서 배수는
    `if not task.cancelled()` 로 거르는데, 그 가드가 **아무 케이스에도 안 걸려 있었다**
    (지우면 dispose 0회 + 배치 결과 파괴 — 독립 적대검증이 재현).

    ★픽스처가 두 모집단을 갈라야 한다: 종전 케이스들의 `done` 집합에는 **취소된 태스크가
      한 번도 들어오지 않아** 이 분기의 False 경로가 영영 실행되지 않았다.
    """

    async def _body() -> str:
        task = asyncio.ensure_future(asyncio.sleep(3600))
        task.set_name("취소될-자식")
        task.cancel()  # ★취소된 채로 `done` 에 들어간다 — 이 케이스의 두 번째 모집단이다
        return "ok"

    assert run_async_batch(lambda: _body()) == "ok", "취소된 자식이 배치 결과를 파괴했다"
    assert all(e.disposed == 1 for e in spy_engines), (
        "취소된 자식 때문에 정리에 도달하지 못했다 — 2026-08-08 장애 기전이 돌아온다"
    )


def test_상한은_가용성_범위_안에_있다() -> None:
    """★상수를 만들었으면 **그 상수에 결속**시킨다(CLAUDE.md §A-5). 종전에는 무잠금이라
    `30.0 → 3600.0` 변이가 통과했다.

    ★단, `== 30.0` 은 상수를 복창하는 **동어반복 락**이라 두지 않는다. 이 상수가 지키는 것은
      *안전*이 아니라 **가용성**이므로, 그 계약인 **범위**를 잠근다 —
      3600 이면 beat 5초 주기 `flush_growth_events` 가 한 시간 매달려 큐가 적체된다.
    """
    assert 0 < _async_batch._CHILD_DRAIN_TIMEOUT_SEC <= _async_batch._CHILD_DRAIN_TIMEOUT_MAX_SEC, (
        f"배수 상한 {_async_batch._CHILD_DRAIN_TIMEOUT_SEC}s 가 가용성 범위를 벗어났다 "
        f"(0 초과 ~ {_async_batch._CHILD_DRAIN_TIMEOUT_MAX_SEC}s 이하). "
        "너무 크면 촘촘한 beat 주기 배치가 매달려 큐가 적체되고, 0 이면 배수가 없는 것과 같다."
    )


def _module_scope_engines(api_root: Path) -> list[tuple[str, str, str]]:
    """`apps/api` 전체에서 **모듈 스코프** `X = create_async_engine(...)` 를 전수 수집한다.

    반환: (파일경로, 속성명, 표시용 위치). 함수 안에서 만드는 일회용 엔진은 **제외**한다 —
    그건 자기 루프에서 dispose 되므로 이 계약의 대상이 아니다(`reconcile_tasks.py` 선례).
    """
    found: list[tuple[str, str, str]] = []
    for path in sorted(api_root.rglob("*.py")):
        if "/tests/" in str(path) or path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # noqa: PERF203
            continue
        for node in tree.body:  # ★`tree.body` 만 본다 = 모듈 스코프(walk 하면 함수 안까지 샌다)
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            fn = node.value.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name != "create_async_engine":
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.append((str(path), target.id, f"{path.name}:{node.lineno}"))
    return found


def test_모듈_전역_엔진은_전수가_계약에_들어있다() -> None:
    """★`_ENGINES` 는 **목록형이었다** — 새 모듈 전역 엔진을 추가해도 전 케이스가 초록이었다
    (독립 적대검증 실증). 모듈 자신이 "새 엔진을 만들면 여기 추가한다"고 적어 놓고 그 **빠짐**을
    잡는 장치가 없었다.

    ★★같은 파일 안에서 규율이 **비대칭**이었다: 루프 생성 모집단은 `app/` 전역 AST 파생인데,
      엔진 모집단은 손으로 쓴 4줄 튜플이었다. 여기서 대칭을 맞춘다 — 모집단을 **코드에서 파생**해
      새 엔진이 자동으로 감시망에 들어오게 한다(CLAUDE.md §A-4 목록형 금지).
    """
    api_root = Path(_async_batch.__file__).resolve().parents[2]  # .../apps/api
    discovered = _module_scope_engines(api_root)

    # 공허 진리 방지 — 스캔이 비면 "위반 0"이 무의미해진다.
    assert len(discovered) >= 3, (
        f"모듈 전역 엔진을 {len(discovered)}개만 찾았다 — 경로가 어긋났거나 파생이 깨졌다"
    )

    contracted = {attr for _mod, attr in _async_batch._ENGINES}
    missing = [where for _p, attr, where in discovered if attr not in contracted]
    assert missing == [], (
        "모듈 전역 엔진이 `_ENGINES` 계약에서 빠졌다 — 그 엔진의 연결만 조용히 새어 나간다:\n"
        + "\n".join(missing)
        + f"\n계약: {_async_batch._ENGINES}"
    )


def test_실제_엔진의_풀이_배치_루프_안에서_교체된다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★J3 봉합 — 여기까지의 모든 케이스는 `_SpyEngine`(스텁)을 태운다. 즉 잠근 것은
    **"살아 있는 같은 루프에서 dispose 를 불렀다"** 이지 **"그래서 풀이 실제로 갈린다"** 가
    아니었다. 스텁이 실제 층을 우회하면 그 층을 지워도 초록이다(CLAUDE.md §검증 규율).

    ★이 케이스는 **진짜 `AsyncEngine`** 을 태운다. DB 접속은 필요 없다 —
      SQLAlchemy 의 `dispose()` 는 **풀 객체 자체를 새것으로 교체**하고, 그 교체는 연결 없이도
      관측된다(실측 확인). 죽은 루프에 묶인 연결이 남지 않는 이유가 바로 이 교체다.

    ★잠그는 것: `_ENGINES` 가 가리키는 대상이 **그 실제 효과를 내는 객체**여야 하고,
      우리가 의존하는 SQLAlchemy 의미(=dispose 는 풀을 교체한다)가 **여전히 참**이어야 한다.
      라이브러리 업그레이드가 그 의미를 바꾸면 여기서 먼저 빨개진다.

    ★★**안 잠그는 것(정직)**: "연결이 실제로 닫혔는가"는 여기서 못 본다 —
      `dispose(close=False)` 를 주입해도 **이 케이스는 통과한다**(실측). 풀 교체는 `close` 와
      무관하게 일어나기 때문이다. 그 축은 `_SpyEngine.close_arg` 단언이 잠근다.
      소켓이 정말 닫혔는지는 DB 가 필요해 **통합 테스트의 몫**이다(여기 없다).
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    # ★접속하지 않는다 — 포트 1 은 의도적으로 닿지 않는 주소다(엔진 생성은 지연 평가).
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/db", pool_pre_ping=True)
    module = types.ModuleType("_real_engine_mod")
    module.engine = engine  # type: ignore[attr-defined]
    sys.modules["_real_engine_mod"] = module
    monkeypatch.setattr(_async_batch, "_ENGINES", (("_real_engine_mod", "engine"),))

    pool_before = engine.pool
    seen: dict[str, object] = {}

    async def work() -> str:
        seen["loop"] = asyncio.get_running_loop()
        seen["pool_during_body"] = engine.pool
        return "ok"

    try:
        assert run_async_batch(work) == "ok"

        # 공허 진리 방지 — 본문이 실제로 돌았고, 그 시점 풀이 원래 풀이었음을 먼저 못박는다.
        assert seen.get("pool_during_body") is pool_before, "본문 실행 전에 이미 풀이 갈렸다"
        assert engine.pool is not pool_before, (
            "실제 엔진의 풀이 갈리지 않았다 — dispose 가 호출은 됐어도 **실효가 없다**. "
            "죽은 루프에 묶인 연결이 그대로 남는다."
        )
    finally:
        sys.modules.pop("_real_engine_mod", None)
