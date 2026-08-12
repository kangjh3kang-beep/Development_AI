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
from collections.abc import Iterator
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
def spy_engines(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[_SpyEngine]]:
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
    yield engines
    # ★가짜 모듈을 `sys.modules` 에 남기지 않는다 — `monkeypatch` 는 `_ENGINES` 만 되돌린다.
    #   같은 파일의 실제엔진 케이스는 정리하는데 여기만 안 하는 **규율 비대칭**이었다.
    for mod_name, _attr in entries:
        sys.modules.pop(mod_name, None)


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
_LOOP_MAKERS: set[str] = {
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
_THIRD_PARTY_LOOP_RUNNERS: set[tuple[str, str]] = {
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
    # ★재바인딩은 **고정점까지 반복**한다 — 한 번만 훑으면 `_b = _a` 가 `_a = asyncio` 보다
    #   앞줄에 있을 때 놓친다(순서 의존). 형태도 셋을 본다: 일반 대입 · 애노테이션 대입 ·
    #   튜플 대입. 전부 독립 적대검증이 통과시킨 우회다.
    # ★진짜 **고정점**까지 돈다. 종전 `range(len(names)+8)` 은 초기 1개 기준 9회 상한이라
    #   역순 사슬 10링크에서 뚫렸다(3라운드 실측) — 주석은 "고정점"이라 적어 놓고 상한이었다.
    #   종료는 `len(names)` 이 단조 증가하고 파일의 이름 수가 유한하므로 보장된다.
    while True:
        before = len(names)
        for node in ast.walk(tree):
            value = getattr(node, "value", None)
            if isinstance(node, ast.Assign | ast.AnnAssign) and isinstance(value, ast.Name):
                if value.id not in names:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names.update(t.id for t in targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.Assign) and isinstance(value, ast.Tuple):
                # `_a, _b = asyncio, None` — 위치가 맞는 것만 별칭이 된다.
                for target in node.targets:
                    if not isinstance(target, ast.Tuple):
                        continue
                    for tgt, val in zip(target.elts, value.elts, strict=False):
                        if isinstance(tgt, ast.Name) and isinstance(val, ast.Name) and val.id in names:
                            names.add(tgt.id)
            elif isinstance(node, ast.NamedExpr) and isinstance(node.value, ast.Name):
                # `(_a := asyncio).run(x)` — 월러스 재바인딩.
                if node.value.id in names and isinstance(node.target, ast.Name):
                    names.add(node.target.id)
        if len(names) == before:
            break
    return names


def _aliased_loop_makers(tree: ast.AST, aliases: set[str]) -> set[str]:
    """`_run = asyncio.run` 처럼 **함수 자체를 별칭으로 묶은** 이름을 모은다.

    ★독립 적대검증이 꼽은 **가장 현실적인 우회**다(적대적 표기가 아니라 평범한 리팩토링처럼
      보인다). 이 이름으로 호출하면 `ast.Attribute` 가 아니라 `ast.Name` 호출이라
      속성 검사만 하는 락은 통째로 빠져나간다.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        value = getattr(node, "value", None)
        if not isinstance(node, ast.Assign | ast.AnnAssign) or not isinstance(value, ast.Attribute):
            continue
        if value.attr not in _LOOP_MAKERS:
            continue
        if _attr_root(value) not in aliases:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        bound.update(t.id for t in targets if isinstance(t, ast.Name))
    return bound


def _attr_root(node: ast.AST) -> str | None:
    """`a.b.c.d` 의 **뿌리 이름** `a` 를 돌려준다(중간 속성이 몇 겹이든).

    ★종전 락은 소유자가 `ast.Name` 일 때만 봤다 — 그래서 `asyncio.runners.Runner()` 처럼
      **한 겹만 깊어져도 통째로 빠져나갔다**(실측 확인된 우회).
    """
    while isinstance(node, ast.Attribute | ast.NamedExpr):
        # ★`(_a := asyncio).run(x)` — 월러스가 중간에 끼면 `Attribute` 만 벗겨서는 뿌리에
        #   닿지 못한다(적대검증이 통과시킨 형태). 대입식은 **대입되는 값**으로 내려간다.
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
      ⑥ `_a = asyncio` 재바인딩(일반·애노테이션·튜플·월러스, 고정점까지)
      ⑦ `_run = asyncio.run` 후 `_run(x)`             — 함수 자체를 별칭으로 묶는 형태

    ★여전히 못 본다(정직 — 실측으로 확인한 목록이다):
      · `getattr(asyncio, "run")(...)`        — 동적 속성 접근
      · `exec("asyncio.run(...)")`            — 문자열 실행
      정적 AST 로는 원리적으로 불가하다.
      **이 목록 밖도 있을 수 있다** — "어떤 형태로든 잡힌다"고 단정하지 않는다(§C-11).

    ★★`functools.partial(asyncio.run)` 은 **잡는다**(⑧이 덮는다). 종전 이 목록에 "못 본다"고
      적혀 있었는데 **같은 함수 안 ⑧ 주석과 모순**이었고, 실측하니 잡혔다 — 다음 사람이
      "partial 은 알려진 탈출구"로 오독할 문장이었다(§C-10 "주석에 쓴 근거도 검증 대상").
    """
    found: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    aliases = _asyncio_aliases(tree)
    bound_makers = _aliased_loop_makers(tree, aliases)
    loop_names = _loop_valued_names(tree)

    # ⑧ ★**루프 생성자를 "값으로" 넘기는 것 자체**를 위반으로 본다 — 호출되는 자리(`Call.func`)가
    #   아닌 곳에 나타난 `asyncio.run` 등. 이 한 규칙이 `functools.partial(asyncio.run)`,
    #   데코레이터·딕셔너리 등록·콜백 전달 같은 **고차 함수 우회를 형태별 열거 없이** 덮는다
    #   (목록형 금지의 같은 정신). `_run = asyncio.run` 도 여기 걸리지만, 그쪽은 ⑦이 호출
    #   지점까지 알려 주므로 둘 다 남긴다.
    called_funcs = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    # ★**타입 위치는 제외**한다 — `def f(r: asyncio.Runner)` · `isinstance(x, asyncio.Runner)` 는
    #   루프를 만들지 않는다. 넣었다가 정상 코드를 막았다(3라운드 실측·CLAUDE.md §A-6).
    type_positions: set[int] = set()

    def _mark(sub: ast.AST | None) -> None:
        if sub is not None:
            type_positions.update(id(n) for n in ast.walk(sub))

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            _mark(node.annotation)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _mark(node.returns)
            for arg in [*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs]:
                _mark(arg.annotation)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"isinstance", "issubclass"} and len(node.args) > 1:
                _mark(node.args[1])

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr not in _LOOP_MAKERS:
            continue
        if id(node) in called_funcs or id(node) in type_positions:
            continue  # 직접 호출은 아래 ①③⑥ 이 다루고, 타입 위치는 위반이 아니다
        if _attr_root(node) in aliases:
            found.append(f"{path.name}:{node.lineno} {node.attr} 를 값으로 전달")

    for node in ast.walk(tree):
        # ⑦ `_run(x)` — 별칭으로 묶인 이름의 **직접 호출**(Attribute 가 아니라 Name 호출).
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in bound_makers:
                found.append(f"{path.name}:{node.lineno} {node.func.id}() ← 루프 생성자 별칭")
            continue
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
        # ④ 루프 객체를 어디서 얻었든 **직접 돌리면** 같은 결함이다.
        #   ★단 "소유자 무관"은 너무 넓었다: `class Consumer: def run_forever(self)` 의
        #     `self.run_forever()` 처럼 **루프가 아닌 객체**까지 신고했다(3라운드 실측).
        #     `run_forever` 는 서드파티(websocket-client 등)에 흔한 메서드명이라
        #     잠재 위양성이 아니라 시간 문제였다. **루프처럼 보이는 소유자**로 좁힌다.
        elif node.func.attr in {"run_until_complete", "run_forever"} and _looks_like_loop(
            owner, aliases, loop_names
        ):
            found.append(f"{path.name}:{node.lineno} <loop>.{node.func.attr}")
    return found


def _detect(source: str, tmp_path: Path) -> bool:
    """소스 한 조각을 탐지기에 먹여 위반 여부를 돌려준다(대조표 전용 헬퍼)."""
    probe = tmp_path / "meta_probe.py"
    probe.write_text(source, encoding="utf-8")
    return bool(_loop_makers_in(probe))


def _loop_valued_names(tree: ast.AST) -> set[str]:
    """**루프를 담은 변수 이름**을 모은다 — 소유자 뿌리가 asyncio 가 아니어도 잡기 위해.

    ★4라운드 실측 우회(둘 다 교과서적 형태다):
      · `policy = asyncio.get_event_loop_policy()` → `lp = policy.new_event_loop()`
        → `lp.run_until_complete(...)`  — 뿌리가 `policy` 라 별칭이 아니고 `lp` 에 'loop' 도 없다
      · `ev = uvloop.new_event_loop()` → `ev.run_until_complete(...)`
    ★고정점까지 돈다 — `a = mk_loop()` · `b = a` 사슬도 따라간다.
    """
    names: set[str] = set()
    while True:
        before = len(names)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign | ast.AnnAssign):
                continue
            value = node.value
            hit = False
            if isinstance(value, ast.Call):
                fn = value.func
                attr = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                hit = attr in _LOOP_MAKERS
            elif isinstance(value, ast.Name):
                hit = value.id in names
            if not hit:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(t.id for t in targets if isinstance(t, ast.Name))
        if len(names) == before:
            return names


def _looks_like_loop(owner: ast.expr, aliases: set[str], loop_names: set[str]) -> bool:
    """소유자가 **이벤트 루프일 법한가** — ④의 위양성을 줄이되 실제 형태는 놓치지 않는다.

    참: 호출 결과(`asyncio.get_event_loop()....`) · asyncio 별칭 뿌리 · 이름에 `loop` 포함.
    거짓: `self` · 임의 도메인 객체.
    """
    root = _attr_root(owner)
    if root is not None and (root in aliases or root in loop_names):
        return True
    name = owner.attr if isinstance(owner, ast.Attribute) else getattr(owner, "id", "")
    if isinstance(owner, ast.Call):
        # ★호출 결과를 **무조건 참**으로 두면 `make_client().run_forever()` 같은 평범한 코드를
        #   막는다(4라운드 실측 위양성). 호출 대상이 루프를 만드는 것일 때만 참으로 본다.
        fn = owner.func
        callee = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        return callee in _LOOP_MAKERS or "event_loop" in str(callee)
    # ★`self.render_loop.run_forever()` · `game_loop.run_forever()` 는 루프가 **아닌** 도메인
    #   객체일 수 있다(렌더 루프·게임 루프). 이름에 'loop' 가 들었다는 것만으로는 부족하므로
    #   **asyncio 문맥**(별칭·루프 변수)과 함께일 때만 본다 — 위 두 검사가 그 역할이다.
    return str(name).lower() in {"loop", "event_loop", "_loop"}


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
      그 **밖**에는 `asyncio.run` 이 **6파일**에 있다(실측: `database/migrations/env.py` ·
      `database/seeds/seed_data.py` · `ml/avm/train.py` · `scripts/` 3개).
      전부 1회성 CLI·alembic 이라 프로세스가 끝나며 죽으므로
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
    # ★하한을 **실측치에 붙인다**. 100 은 7.75배 느슨했고, 600 도 22.5% 붕괴를 허용했다
    #   (3라운드 지적 — "실측치에 붙였다"고 써 놓고 안 붙였다). `app/` 실측 775개.
    #   740 은 신규 파일 추가·삭제의 정상 변동은 흡수하고, 경로가 어긋난 붕괴는 잡는 폭이다.
    assert scanned >= 740, f"`app/` 를 {scanned}개만 훑었다 — 경로가 어긋났다(실측 775개)"
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

    # ★시그니처를 실제와 맞춘다 — 안 맞추면 `close=False` 변이가 계약 위반이 아니라
    #   **TypeError** 로 "잡혀" 우연한 적발이 된다(같은 파일이 그걸 제거했다고 선언했는데
    #   같은 커밋의 신규 코드에서 재발했다 — 3라운드 실증).
    async def _recording_dispose(self: _SpyEngine, close: bool = True) -> None:
        seen_at_dispose.append(bool(child_done))
        await original(self, close)

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

    # ★시그니처를 실제와 맞춘다 — 안 맞추면 `close=False` 변이가 계약 위반이 아니라
    #   **TypeError** 로 "잡혀" 우연한 적발이 된다(같은 파일이 그걸 제거했다고 선언했는데
    #   같은 커밋의 신규 코드에서 재발했다 — 3라운드 실증).
    async def _recording_dispose(self: _SpyEngine, close: bool = True) -> None:
        seen_at_dispose.append(bool(grandchild_done))
        await original(self, close)

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


def _tightest_beat_seconds(celery_app_path: Path) -> float | None:
    """`celery_app.py` 소스에서 **가장 촘촘한 숫자 beat 주기**(초)를 뽑는다.

    ★목록형 금지 — 주기를 손으로 적지 않고 **코드에서 파생**한다. `crontab(...)` 은 초 단위
      비교가 불가하므로 제외하고, 숫자 주기만 본다(적체가 문제되는 것도 그쪽이다).
    """
    tree = ast.parse(celery_app_path.read_text(encoding="utf-8"))
    values: list[float] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if not isinstance(key, ast.Constant) or key.value != "schedule":
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, (int, float)):
                values.append(float(value.value))
    return min(values) if values else None


def test_상한은_가용성_범위_안에_있다() -> None:
    """★상수를 만들었으면 **그 상수에 결속**시킨다(CLAUDE.md §A-5). 종전에는 무잠금이라
    `30.0 → 3600.0` 변이가 통과했다.

    ★단, `== 30.0` 은 상수를 복창하는 **동어반복 락**이라 두지 않는다. 이 상수가 지키는 것은
      *안전*이 아니라 **가용성**이므로, 그 계약인 **범위**를 잠근다 —
      3600 이면 beat 5초 주기 `flush_growth_events` 가 한 시간 매달려 큐가 적체된다.
    """
    # ★★상대 비교만으로는 **두 값을 함께 올리는 2단 편집**이 통과한다(3라운드 실증:
    #   MAX 3600 → SEC 3600 둘 다 생존). 상한을 **외부 사실**에 묶는다 — 가용성 계약은
    #   상수 자신이 아니라 **가장 촘촘한 beat 주기**에서 온다. 파생형이라 새 beat 가
    #   촘촘해지면 자동 반영되고, 상수를 복창하는 동어반복도 아니다(§A-4·§A-5).
    # ★런타임(`celery_app.app.conf`)에서 읽으면 **테스트 환경에서 app 이 None** 이라
    #   파생이 공허해진다(실측 — 공허 진리 가드가 잡았다). 그래서 **소스를 AST 로** 읽는다:
    #   환경 의존이 없고, 새 beat 가 추가되면 자동으로 반영된다.
    tightest = _tightest_beat_seconds(
        Path(_async_batch.__file__).resolve().parent / "celery_app.py"
    )
    assert tightest is not None, "beat 스케줄에서 숫자 주기를 하나도 못 찾았다 — 파생이 깨졌다"
    assert 12 * tightest >= _async_batch._CHILD_DRAIN_TIMEOUT_MAX_SEC, (
        f"배수 상한 최대치 {_async_batch._CHILD_DRAIN_TIMEOUT_MAX_SEC}s 가 가장 촘촘한 beat "
        f"주기({tightest}s)의 12배를 넘는다 — 그 배치가 매달리면 큐가 적체된다"
    )
    assert 0 < _async_batch._CHILD_DRAIN_TIMEOUT_SEC <= _async_batch._CHILD_DRAIN_TIMEOUT_MAX_SEC, (
        f"배수 상한 {_async_batch._CHILD_DRAIN_TIMEOUT_SEC}s 가 가용성 범위를 벗어났다 "
        f"(0 초과 ~ {_async_batch._CHILD_DRAIN_TIMEOUT_MAX_SEC}s 이하). "
        "너무 크면 촘촘한 beat 주기 배치가 매달려 큐가 적체되고, 0 이면 배수가 없는 것과 같다."
    )


def _module_scope_stmts(body: list[ast.stmt]) -> list[ast.stmt]:
    """**모듈 스코프에서 실행되는** 문장을 전부 모은다.

    ★`tree.body` 만 보면 **과소**다: `try:` 안(배포 형태별 조건부 임포트)·`if flag:` 안(기능
      플래그)의 모듈 전역 대입을 놓친다 — 둘 다 이 저장소에 흔하고, 독립 적대검증이 그 형태로
      새 엔진을 넣어 **통과시켰다**.
    ★`ast.walk` 는 **과대**다: 함수·클래스 body 까지 들어가 일회용 엔진을 위반으로 신고한다.
      그래서 `If`/`Try`/`With` 만 내려가고 `FunctionDef`/`ClassDef` 에서는 멈춘다.
    """
    out: list[ast.stmt] = []
    # ★블록 종류를 **열거하지 않는다** — `for`/`while`/`match` 를 빠뜨려 새 이름 엔진이
    #   통과했다(3라운드 실증). 함수·클래스 **만** 배제하고 나머지는 전부 내려간다.
    #   목록형 금지를 여기에도 적용한다(CLAUDE.md §A-4).
    for node in body:
        out.append(node)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            continue  # 여기서 만드는 엔진은 일회용 — 자기 루프에서 dispose 된다
        for field in ("body", "orelse", "finalbody"):
            sub = getattr(node, field, None)
            if isinstance(sub, list) and sub and isinstance(sub[0], ast.stmt):
                out.extend(_module_scope_stmts(sub))
        for handler in getattr(node, "handlers", []) or []:
            out.extend(_module_scope_stmts(handler.body))
        for case in getattr(node, "cases", []) or []:  # match 문
            out.extend(_module_scope_stmts(case.body))
    return out


def _engine_ctor_names(tree: ast.AST) -> set[str]:
    """이 파일에서 `create_async_engine` 을 가리키는 **모든 이름**(별칭 포함).

    ★`from ... import create_async_engine as _mk` 하나로 엔진 전수수집이 통째로 우회된다
      (3라운드 실측). `asyncio` 쪽에는 별칭 추적기를 두고 여기엔 안 둔 비대칭이었다.
    """
    names = {"create_async_engine"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "create_async_engine":
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            if node.value.id in names:
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _dotted(path: Path, api_root: Path) -> str:
    """파일 경로를 점 표기 모듈 경로로 — `app/core/database.py` → `app.core.database`."""
    return ".".join(path.relative_to(api_root).with_suffix("").parts)


def _normalize_contract_module(module: str) -> str:
    """`_ENGINES` 의 모듈명을 `apps/api` 기준으로 정규화한다.

    저장소는 같은 파일을 두 이름으로 부른다(`apps.api.database.session` ↔ `database.session`) —
    실행 위치에 따라 sys.path 가 다르기 때문이다. 대조 전에 한쪽으로 모은다.
    """
    prefix = "apps.api."
    return module[len(prefix):] if module.startswith(prefix) else module


def _module_scope_engines(api_root: Path) -> list[tuple[str, str, str]]:
    """`apps/api` 전체에서 **모듈 스코프** `X = create_async_engine(...)` 를 전수 수집한다.

    반환: (점표기 모듈, 속성명, 표시용 위치). 함수 안에서 만드는 일회용 엔진은 **제외**한다 —
    그건 자기 루프에서 dispose 되므로 이 계약의 대상이 아니다(`reconcile_tasks.py` 선례).

    ★**못 보는 것(정직)** — 형제 함수 `_loop_makers_in` 에는 이 목록이 있는데 여기엔 없어서
      **반쪽 비대칭**이었다(3라운드 지적). 실측으로 확인한 미탐 형태:
        · 팩토리/래퍼 경유 — `def _make(): return create_async_engine(...)` → `e = _make()`
        · 튜플 타깃 — `a, b = create_async_engine(...), None`
        · `async_engine_from_config(...)` — 이 저장소에 실재(`database/migrations/env.py`)
        · `globals()[...] = ...` 동적 대입
      구문이 아니라 **런타임 판정**(모듈 임포트 후 `isinstance(obj, AsyncEngine)`)으로 옮기면
      생성 형태와 무관해진다 — 범위가 커서 별건으로 둔다.
    """
    found: list[tuple[str, str, str]] = []
    for path in sorted(api_root.rglob("*.py")):
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # noqa: PERF203
            continue
        module = _dotted(path, api_root)
        for node in _module_scope_stmts(tree.body):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign) and node.target is not None:
                targets = [node.target]
            else:
                continue
            value = node.value
            if not isinstance(value, ast.Call):
                continue
            fn = value.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            # ★★생성자를 **별칭으로 들여온 경우**도 본다:
            #   `from ... import create_async_engine as _mk` → `_mk(...)`.
            #   같은 파일이 `asyncio` 에는 고정점 별칭 추적기를 만들고 여기엔 안 만든
            #   **규율 비대칭**이었다 — "비대칭을 맞춘다"고 선언한 커밋에 남아 있었다.
            if name not in _engine_ctor_names(tree):
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    found.append((module, target.id, f"{module}:{node.lineno}"))
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

    # ★★**(모듈, 속성) 쌍**으로 대조한다. 종전에는 속성명만 봤는데, `_ENGINES` 4항목이 쓰는
    #   구별되는 이름은 **2개뿐**(`engine`·`timescale_engine`)이고 실제 엔진 4개 중 **3개가
    #   `engine`** 이다. 즉 그 단언은 "전부 계약에 있다"가 아니라 **"이름이 engine 이거나
    #   timescale_engine 이다"** 라는 명명규약 검사였다 — 저장소 관례가 바로 `engine` 이므로
    #   **재발 확률이 가장 높은 형태**(새 모듈 + 관례 이름)가 정확히 통과했다(적대검증 실증).
    contracted = {(_normalize_contract_module(mod), attr) for mod, attr in _async_batch._ENGINES}
    missing = [where for mod, attr, where in discovered if (mod, attr) not in contracted]
    assert missing == [], (
        "모듈 전역 엔진이 `_ENGINES` 계약에서 빠졌다 — 그 엔진의 연결만 조용히 새어 나간다:\n"
        + "\n".join(missing)
        + f"\n계약(정규화): {sorted(contracted)}"
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


def test_배수가_취소돼도_엔진은_정리한다(
    spy_engines: list[_SpyEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    """★`CancelledError` 는 **`BaseException` 계열**이라 `except Exception` 을 통과한다 —
    그러면 `finally` 를 그대로 빠져나가 **정리에 도달하지 못한다**.

    ★★이건 잔존 결함이 아니라 **배수가 만든 노출면**이다: 배수 도입 전에는 `finally` 가 즉시
      dispose 로 갔는데, 이제 **최대 상한만큼 `finally` 안에 머무는 창**이 생겼다.
      워커 종료·Ctrl-C 가 그 창에 떨어지면 막으려던 누수가 그대로 돌아온다
      (독립 적대검증이 실제 SIGINT 로 재현 — dispose 0회).

    ★취소는 **삼키지 않고 전파**해야 한다 — 삼키면 종료가 지연된다. 두 축을 함께 단언한다.
    """

    async def _cancelled(*_a: object, **_k: object) -> int:
        raise asyncio.CancelledError

    monkeypatch.setattr(_async_batch, "_drain_child_tasks", _cancelled)

    async def _body() -> str:
        return "ok"

    with pytest.raises(asyncio.CancelledError):
        run_async_batch(lambda: _body())

    assert all(e.disposed == 1 for e in spy_engines), (
        "배수가 취소되자 정리에 도달하지 못했다 — 2026-08-08 장애 기전이 종료 경로로 돌아온다"
    )


def test_상한_인자도_최대치로_클램프된다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★종전 범위 락은 **기본 상수만** 봤다 — `_drain_child_tasks(timeout=3600)` 인자 경로는
    범위 밖이었고, `_CHILD_DRAIN_TIMEOUT_MAX_SEC` 는 **프로덕션 소비처 0**이라 두 상수를
    차례로 키우는 2단 편집이 통과했다(적대검증 실증).

    ★이제 런타임에 클램프하므로 인자로도 상한을 넘을 수 없다. **경과 시간으로** 확인한다 —
      상수를 복창하는 대신 실제 동작을 본다.

    ★★`wait_for` 로 **바깥에서 한 번 더** 상한을 건다. 안 걸면 클램프를 없앤 변이가 이 케이스를
      실패시키는 게 아니라 **3600초 멈추게** 한다 — 같은 파일에서 이미 한 번 당한 함정이고
      (변이 도구가 SIGTERM 으로 죽어 결과를 통째로 잃었다), 여기서 그대로 재생산했었다.
    """
    # ★`monkeypatch` 로 되돌린다 — 직접 대입은 `try:` 밖이라 그 사이 예외가 나면 복원되지 않고,
    #   그 구간 동안 `_CHILD_DRAIN_TIMEOUT_SEC(30) > MAX(0.05)` 로 모듈 불변식이 깨진다.
    #   같은 파일의 다른 케이스는 전부 monkeypatch 를 쓴다(규율 비대칭이었다).
    monkeypatch.setattr(_async_batch, "_CHILD_DRAIN_TIMEOUT_MAX_SEC", 0.05)

    async def _never() -> None:
        await asyncio.sleep(3600)

    async def _body() -> float:
        task = asyncio.ensure_future(_never())
        task.set_name("클램프-확인용")
        started = asyncio.get_running_loop().time()
        # ★바깥 상한 2초 — 클램프가 살아 있으면 0.05초에 끝나고, 죽었으면 여기서 잘린다.
        await asyncio.wait_for(_async_batch._drain_child_tasks(timeout=3600.0), timeout=2.0)
        return asyncio.get_running_loop().time() - started

    try:
        elapsed = asyncio.run(_body())
    except TimeoutError:
        pytest.fail("인자 3600s 가 클램프되지 않았다 — 상한 계약이 인자 경로에 안 걸려 있다")

    assert elapsed < 1.0, (
        f"클램프는 됐지만 {elapsed:.2f}초 걸렸다 — 상한이 인자 경로에 제대로 안 걸렸다"
    )


# ── ★★탐지기를 **직접 태우는** 양성·음성 대조 ────────────────────────────
# 독립 적대검증 3라운드가 실증한 것: `_loop_makers_in` 을 **`return []` 로 바꿔도 전 케이스가
# 초록**이었다. 유일한 소비처가 `offenders == []` 만 단언하는데 저장소에 위반이 0이라
# **탐지기가 탐지하는지는 아무도 보지 않았다**. R1·R2 두 라운드가 고쳐 온 AST 로직 ~70줄이
# 통째로 무잠금이었다 — CLAUDE.md §A-2(공허 진리 가드를 단언 **앞에**)의 정면 위반이다.
#
# ★그래서 **위반 코드를 만들어 탐지기에 먹인다**. 이 표가 곧 "무엇을 잡는다"는 주장의 근거다.
_LOOP_VIOLATIONS: tuple[tuple[str, str], ...] = (
    ("직접 호출", "import asyncio\nasyncio.run(x())"),
    ("from import", "from asyncio import run\nrun(x())"),
    ("별칭", "import asyncio as aio\naio.run(x())"),
    ("루프 변수 직접 구동", "loop = get()\nloop.run_until_complete(x())"),
    ("get_event_loop 체인", "import asyncio\nasyncio.get_event_loop().run_until_complete(x())"),
    ("속성 체인", "import asyncio\nasyncio.runners.Runner().run(x())"),
    ("서브모듈 별칭", "import asyncio.runners as r\nr.Runner().run(x())"),
    ("서브모듈 from", "from asyncio.runners import Runner\nRunner().run(x())"),
    ("재바인딩", "import asyncio\n_a = asyncio\n_a.run(x())"),
    ("애노테이션 재바인딩", "import asyncio\n_a: object = asyncio\n_a.run(x())"),
    ("튜플 재바인딩", "import asyncio\n_a, _b = asyncio, None\n_a.run(x())"),
    ("월러스", "import asyncio\n(_a := asyncio).run(x())"),
    ("함수 별칭", "import asyncio\n_run = asyncio.run\n_run(x())"),
    ("고차 함수 전달", "import asyncio, functools\nfunctools.partial(asyncio.run)(x())"),
    ("콜백 등록", "import asyncio\nHANDLERS = {'go': asyncio.run}"),
    ("새 루프 생성", "import asyncio\nl = asyncio.new_event_loop()"),
    ("서드파티 실행기", "import anyio\nanyio.run(x)"),
    # ★아래 4건은 **파생 검증이 찾아낸 무잠금**이다 — `_LOOP_MAKERS` 에 이름은 있는데
    #   양성 표에 표본이 없어 그 규칙들이 잠기지 않고 있었다(대조표 자체를 잠그자 즉시 드러남).
    ("루프 교체", "import asyncio\nasyncio.set_event_loop(l)"),
    ("루프 영구 구동", "loop = get()\nloop.run_forever()"),
    ("Selector 루프 생성", "import asyncio\nl = asyncio.SelectorEventLoop()"),
    ("Proactor 루프 생성", "import asyncio\nl = asyncio.ProactorEventLoop()"),
    ("uvloop 실행", "import uvloop\nuvloop.run(x)"),
    ("uvloop 설치", "import uvloop\nuvloop.install()"),
    ("asgiref 동기변환", "import asgiref.sync\nasgiref.sync.async_to_sync(x)()"),
    ("nest_asyncio 패치", "import nest_asyncio\nnest_asyncio.apply()"),
    # ★4라운드 실측 우회 — 둘 다 **교과서적 형태**라 적대적 표기가 아니다.
    ("policy 경유 루프", "import asyncio\np = asyncio.get_event_loop_policy()\nlp = p.new_event_loop()\nlp.run_until_complete(x())"),
    ("서드파티 루프 생성", "import uvloop\nev = uvloop.new_event_loop()\nev.run_until_complete(x())"),
    ("서드파티 from-import", "from uvloop import run\nrun(x)"),
    ("루프 변수 사슬", "import asyncio\na = asyncio.new_event_loop()\nb = a\nb.run_forever()"),
)

# ★위양성 대조 — 이게 없으면 "전부 위반"이라고 답하는 탐지기도 위 표를 통과한다.
_LOOP_ALLOWED: tuple[tuple[str, str], ...] = (
    ("스레드 오프로드", "import anyio\nasync def w():\n    await anyio.to_thread.run_sync(f)"),
    ("시계 읽기", "import asyncio\nasync def w():\n    return asyncio.get_event_loop().time()"),
    ("동명의 지역 함수", "def run(x):\n    return x\nrun(1)"),
    ("일반 asyncio 사용", "import asyncio\nasync def w():\n    await asyncio.sleep(1)"),
    ("문자열 언급", 'logger.info("asyncio.run 을 쓰지 마라")'),
    ("타입 애노테이션", "import asyncio\ndef f(r: asyncio.Runner) -> None:\n    pass"),
    ("isinstance 검사", "import asyncio\nx = isinstance(o, asyncio.Runner)"),
    ("플랫폼 종류 확인", "import asyncio\nx = isinstance(l, asyncio.SelectorEventLoop)"),
    ("루프 아닌 객체의 run_forever", "class C:\n    def run_forever(self):\n        pass\n    def go(self):\n        self.run_forever()"),
    ("애노테이션 유니온", "import asyncio\ndef d(r: asyncio.Runner | None) -> None:\n    pass"),
    # ★4라운드 실측 위양성 — `run_forever` 는 서드파티·도메인 객체에 흔한 메서드명이다.
    ("팩토리 호출 결과", "def go():\n    make_client().run_forever()"),
    ("도메인 루프 객체", "game_loop.run_forever()"),
    ("속성 루프 객체", "class C:\n    def go(self):\n        self.render_loop.run_forever()"),
    ("반환 애노테이션", "import asyncio\ndef mk() -> asyncio.Runner:\n    raise NotImplementedError"),
    ("키워드전용 애노테이션", "import asyncio\ndef f(*, r: asyncio.Runner) -> None:\n    pass"),
)


@pytest.mark.parametrize(("label", "source"), _LOOP_VIOLATIONS, ids=[v[0] for v in _LOOP_VIOLATIONS])
def test_배선_탐지기가_우회를_실제로_잡는다(
    label: str, source: str, tmp_path: Path
) -> None:
    """★양성 대조 — 탐지기가 `return []` 로 퇴화하면 **여기서 전부 실패**한다."""
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    assert _loop_makers_in(probe), f"우회 형태 '{label}' 를 놓쳤다:\n{source}"


@pytest.mark.parametrize(("label", "source"), _LOOP_ALLOWED, ids=[v[0] for v in _LOOP_ALLOWED])
def test_배선_탐지기가_정상_코드를_막지_않는다(
    label: str, source: str, tmp_path: Path
) -> None:
    """★음성 대조 — 없으면 "무조건 위반"이라 답하는 탐지기도 양성 대조를 통과한다.
    가드의 **위양성도 결함**이다(CLAUDE.md §A-6)."""
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    assert _loop_makers_in(probe) == [], f"정상 형태 '{label}' 를 위반으로 신고했다:\n{source}"


_ENGINE_SCOPES: tuple[tuple[str, str, bool], ...] = (
    ("평문 모듈 스코프", "e = create_async_engine(U)", True),
    ("try 블록", "try:\n    e = create_async_engine(U)\nexcept Exception:\n    e = None", True),
    ("if 블록", "if FLAG:\n    e = create_async_engine(U)", True),
    ("else 블록", "if FLAG:\n    pass\nelse:\n    e = create_async_engine(U)", True),
    ("with 블록", "with ctx():\n    e = create_async_engine(U)", True),
    ("for 블록", "for _ in R:\n    e = create_async_engine(U)", True),
    ("while 블록", "while F:\n    e = create_async_engine(U)\n    break", True),
    ("애노테이션 대입", "e: object = create_async_engine(U)", True),
    ("함수 안(일회용)", "async def go():\n    e = create_async_engine(U)\n    await e.dispose()", False),
    ("클래스 안", "class C:\n    e = create_async_engine(U)", False),
    # ★4라운드 실측 무잠금 — 이 커밋이 추가한 하강인데 태우는 표본이 없었다.
    ("except 핸들러 안", "try:\n    pass\nexcept Exception:\n    e = create_async_engine(U)", True),
    ("finally 안", "try:\n    pass\nfinally:\n    e = create_async_engine(U)", True),
    ("match case 안", "match V:\n    case 1:\n        e = create_async_engine(U)", True),
)


@pytest.mark.parametrize(
    ("label", "body", "should_find"), _ENGINE_SCOPES, ids=[s[0] for s in _ENGINE_SCOPES]
)
def test_엔진_수집기가_모듈_스코프만_정확히_본다(
    label: str, body: str, should_find: bool, tmp_path: Path
) -> None:
    """★`_module_scope_stmts` 도 같은 이유로 무잠금이었다 — `return list(body)` 로 퇴화시켜도
    전 케이스가 초록이었다(저장소 엔진 4개가 전부 평문 모듈 스코프라 하강이 안 걸린다).

    ★**함수·클래스 안은 잡으면 안 된다**(일회용 엔진은 자기 루프에서 dispose 된다) —
      과대·과소 양쪽을 한 표에서 본다.
    """
    (tmp_path / "m.py").write_text(
        "from sqlalchemy.ext.asyncio import create_async_engine\n" + body, encoding="utf-8"
    )
    found = _module_scope_engines(tmp_path)
    assert bool(found) is should_find, (
        f"'{label}' 를 {'놓쳤다' if should_find else '잘못 신고했다'}: {found}\n{body}"
    )


def test_계약의_모든_항목이_실제로_import_되고_속성이_있다() -> None:
    """★★검사는 **정규화한 이름**을 대조하는데 `_dispose_engines` 는 **원문**으로
    `importlib.import_module` 한다. 접두가 하나 더 붙은 이름은 정규화 후 발견 집합과 일치해
    검사를 통과하지만, 런타임엔 `ModuleNotFoundError` → `except Exception: continue` →
    **영영 dispose 되지 않는다**(3라운드가 재현: 계약에 있고 검사 통과, 풀 교체 안 됨).

    ★`test_계약에_풀드_엔진이_최소_하나_실재한다` 는 백스톱이 못 된다 — **기존** 풀드 엔진
      하나로 통과해 버려서, 두 번째 풀드 엔진이 추가되는 순간 조용히 샌다.
      그래서 **항목별로** 원문 import 가능성과 속성 존재를 단언한다.
    """
    import importlib

    broken: list[str] = []
    for module_name, attr in _async_batch._ENGINES:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001
            broken.append(f"{module_name}.{attr} — import 실패: {type(exc).__name__}")
            continue
        if getattr(module, attr, None) is None:
            broken.append(f"{module_name}.{attr} — 모듈은 있으나 속성이 없다")

    assert broken == [], (
        "계약 항목이 런타임에 도달하지 못한다 — `_dispose_engines` 가 조용히 건너뛰어 "
        "그 엔진은 **영영 정리되지 않는다**:\n" + "\n".join(broken)
    )


def test_한_엔진의_취소가_나머지_정리를_막지_않는다(
    spy_engines: list[_SpyEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    """★`_dispose_engines` 의 엔진별 핸들러도 `except Exception` 이라 **취소를 안 잡았다** —
    첫 엔진에서 끊기면 나머지는 정리 시도조차 못 한다.

    ★★호출부(`_runner`)에서 같은 결함을 고쳐 놓고 **한 겹 아래에 그대로 남아 있었다.**
      "처방을 적용한 범위 = 결함이 사는 범위인가"(CLAUDE.md §D-20)의 실례다.
      취소는 **삼키지 않고 전파**해야 하므로 두 축을 함께 단언한다.
    """

    async def _cancelled(close: bool = True) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(spy_engines[0], "dispose", _cancelled)

    async def work() -> int:
        return 7

    with pytest.raises(asyncio.CancelledError):
        run_async_batch(work)

    assert spy_engines[1].disposed == 1, (
        "첫 엔진이 취소되자 나머지 엔진의 정리가 통째로 건너뛰어졌다 — 그 엔진은 영영 샌다"
    )


def test_별칭_사슬이_길어도_고정점까지_따라간다(tmp_path: Path) -> None:
    """★주석은 "고정점까지 반복"이라 적었는데 실제는 `range(len(names)+8)` **상한**이었고,
    역순 사슬 10링크에서 뚫렸다(3라운드 실측). 주석이 코드보다 넓게 주장한 형태다.

    ★역순으로 쓴다 — 정순이면 1패스로 풀려 상한이 있어도 통과한다(두 모집단을 가른다).
    """
    depth = 30
    lines = ["import asyncio", f"_n{depth}.run(x())"]
    lines += [f"_n{i + 1} = _n{i}" for i in range(depth - 1, -1, -1)]
    lines.append("_n0 = asyncio")
    probe = tmp_path / "chain.py"
    probe.write_text("\n".join(lines), encoding="utf-8")

    assert _loop_makers_in(probe), f"{depth}링크 별칭 사슬을 놓쳤다 — '고정점'이 아니라 상한이다"


def test_계약_항목이_import_불가하면_잡는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★검사는 **정규화한 이름**을 대조하는데 `_dispose_engines` 는 **원문**으로 import 한다 —
    접두가 붙은 이름은 검사를 통과하고 런타임엔 `ModuleNotFoundError` 로 조용히 건너뛰어져
    **영영 정리되지 않는다**(3라운드 재현).

    ★실제로 존재하지 않는 모듈을 계약에 넣어 **그 락이 발화하는지** 확인한다 —
      락을 만들어 놓고 태우지 않는 실수를 이 파일에서 이미 두 번 했다.
    """
    monkeypatch.setattr(
        _async_batch,
        "_ENGINES",
        (*_async_batch._ENGINES, ("절대_없는_모듈_이름_xyz", "engine")),
    )
    with pytest.raises(AssertionError, match="import 실패"):
        test_계약의_모든_항목이_실제로_import_되고_속성이_있다()


def test_양성_대조표가_구현의_모든_루프생성자를_덮는다(tmp_path: Path) -> None:
    """★대조표는 **손으로 쓴 목록**이라 그 자체가 §A-4 위험이다 — 새 규칙을 추가하고 표에
    안 넣으면 그 규칙은 다시 무잠금이 된다(자가점검에서 표를 축소해도 조용히 통과함을 확인).

    ★그래서 표를 **구현의 상수에서 파생 검증**한다: `_LOOP_MAKERS` 와
      `_THIRD_PARTY_LOOP_RUNNERS` 의 **모든 이름**이 양성 표의 어느 표본엔가 등장해야 한다.
      이름을 추가하고 표본을 안 넣으면 여기서 빨개진다.
    """
    # ★★**부분문자열 매칭은 잠금이 아니다**(4라운드 실증): `"get_event_loop" in covered` 는
    #   `get_event_loop_policy` 표본 때문에 참이 되고, 서드파티 쪽 `import {mod}` 탈출구는
    #   `("uvloop","new_event_loop")` 를 **표본 0건으로** 통과시켰다.
    #   대신 **규칙별로 파생 검증**한다: 그 이름을 `_LOOP_MAKERS` 에서 빼면 **어떤 표본이
    #   깨끗해지는가**. 깨끗해지는 표본이 없으면 그 규칙은 아무 표본도 태우지 않는 것이다.
    original = set(_LOOP_MAKERS)
    unexercised: list[str] = []
    for name in sorted(original):
        _LOOP_MAKERS.discard(name)
        try:
            weakened = any(
                not _detect(source, tmp_path) for _label, source in _LOOP_VIOLATIONS
            )
        finally:
            _LOOP_MAKERS.add(name)
        if not weakened:
            unexercised.append(name)
    assert unexercised == [], (
        f"`_LOOP_MAKERS` 의 이름이 **아무 표본도 태우지 않는다** — 그 규칙은 무잠금이다: {unexercised}"
    )

    original_tp = set(_THIRD_PARTY_LOOP_RUNNERS)
    unexercised_tp: list[str] = []
    for pair in sorted(original_tp):
        _THIRD_PARTY_LOOP_RUNNERS.discard(pair)
        try:
            weakened = any(
                not _detect(source, tmp_path) for _label, source in _LOOP_VIOLATIONS
            )
        finally:
            _THIRD_PARTY_LOOP_RUNNERS.add(pair)
        if not weakened:
            unexercised_tp.append(f"{pair[0]}.{pair[1]}")
    assert unexercised_tp == [], (
        f"서드파티 실행기가 아무 표본도 태우지 않는다: {unexercised_tp}"
    )


def test_음성_대조표가_조용히_줄지_않는다() -> None:
    """★음성 표는 **파생할 수 없다**(정상 코드의 형태는 구현 상수에서 나오지 않는다).
    그래서 **개수 하한**으로 조용한 축소만 막는다 — 이것이 이 표의 정직한 한계다.

    ★이 하한은 계약이 아니라 **회귀 방지선**이다: 위양성 형태를 하나 발견할 때마다 표에
      넣고 하한을 올린다. 지금까지 발견분 = 3라운드까지의 실측 위양성 전부.
    """
    assert len(_LOOP_ALLOWED) >= 10, (
        f"음성 대조표가 {len(_LOOP_ALLOWED)}건으로 줄었다 — 위양성 방지선이 조용히 약해졌다. "
        "항목을 지우려면 그 형태가 더는 위양성이 아님을 먼저 보여라."
    )
    assert len(_LOOP_VIOLATIONS) >= 16, (
        f"양성 대조표가 {len(_LOOP_VIOLATIONS)}건으로 줄었다 — 탐지력 방지선이 약해졌다."
    )


# ── 종료 신호 3종을 **각각** 태운다 ──────────────────────────────────────
# ★4라운드 지적: `except (CancelledError, KeyboardInterrupt, SystemExit)` 로 좁힌 것이
#   이 커밋의 **유일한 프로덕션 변경**인데, 되돌려도(`except BaseException`) 테스트가 하나도
#   안 죽었다. 테스트 파일에 `KeyboardInterrupt`·`SystemExit` 토큰이 **0회**였기 때문 —
#   튜플의 뒤 두 이름이 **장식**이었다. "탐지력을 하나도 잠그지 않았다"는 제목의 커밋이
#   자기 변경에서 같은 형태를 재발시킨 것이다(CLAUDE.md §1·§A-5).
_TERMINATION_SIGNALS = (
    ("취소", asyncio.CancelledError),
    ("인터럽트", KeyboardInterrupt),
    ("종료요청", SystemExit),
)


@pytest.mark.parametrize(
    ("label", "exc_type"), _TERMINATION_SIGNALS, ids=[s[0] for s in _TERMINATION_SIGNALS]
)
def test_배수가_어떤_종료신호로_끊겨도_엔진은_정리한다(
    label: str,
    exc_type: type[BaseException],
    spy_engines: list[_SpyEngine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★세 신호를 **각각** 태운다 — 하나만 태우면 나머지 둘은 튜플 안의 장식이 된다."""

    async def _signal(*_a: object, **_k: object) -> int:
        raise exc_type

    monkeypatch.setattr(_async_batch, "_drain_child_tasks", _signal)

    async def _body() -> str:
        return "ok"

    with pytest.raises(exc_type):
        run_async_batch(lambda: _body())

    assert all(e.disposed == 1 for e in spy_engines), (
        f"배수가 {label}으로 끊기자 정리에 도달하지 못했다 — 장애 기전이 종료 경로로 돌아온다"
    )


@pytest.mark.parametrize(
    ("label", "exc_type"), _TERMINATION_SIGNALS, ids=[s[0] for s in _TERMINATION_SIGNALS]
)
def test_한_엔진이_어떤_종료신호로_끊겨도_나머지는_정리한다(
    label: str,
    exc_type: type[BaseException],
    spy_engines: list[_SpyEngine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★`_dispose_engines` 의 엔진별 핸들러도 같은 셋을 잡아야 한다 — 한 겹 위에서만 좁히고
    여기엔 적용하지 않았던 것이 4라운드 지적이다(§D-20)."""

    async def _signal(close: bool = True) -> None:
        raise exc_type

    monkeypatch.setattr(spy_engines[0], "dispose", _signal)

    async def work() -> int:
        return 7

    with pytest.raises(exc_type):
        run_async_batch(work)

    assert spy_engines[1].disposed == 1, (
        f"첫 엔진이 {label}으로 끊기자 나머지 엔진 정리가 통째로 건너뛰어졌다"
    )


def test_종료신호가_취소보다_우선_전파된다(
    spy_engines: list[_SpyEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    """★마지막 것만 보관하면 앞선 `KeyboardInterrupt` 가 뒤따르는 `CancelledError` 에 덮여
    **Ctrl-C 가 먹힌다** — 코드가 "취소를 먹으면 워커 종료가 지연된다"고 쓴 그 일이다."""

    async def _interrupt(close: bool = True) -> None:
        raise KeyboardInterrupt

    async def _cancel(close: bool = True) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(spy_engines[0], "dispose", _interrupt)  # 먼저
    monkeypatch.setattr(spy_engines[1], "dispose", _cancel)  # 나중

    async def work() -> int:
        return 1

    with pytest.raises(KeyboardInterrupt):
        run_async_batch(work)


# ★무의미한 값만 폴백 대상이다. **양수는 존중**한다(호출부가 일부러 짧게 주는 것은 의도).
_CLAMP_CASES: tuple[tuple[str, float], ...] = (
    ("0", 0.0),
    ("음수", -5.0),
)


@pytest.mark.parametrize(("label", "bad"), _CLAMP_CASES, ids=[c[0] for c in _CLAMP_CASES])
def test_상한_인자의_하한도_클램프된다(label: str, bad: float) -> None:
    """★"경계는 양방향(§D-19)"이라고 **주석에만 적고** 런타임엔 `min()` 만 있었다 —
    `timeout=0`·음수면 배수가 **통째로 건너뛰어졌다**(4라운드 실측 drained=0·elapsed=0.000s).
    `max-h` 만 걸고 `min-h` 를 안 걸어 프로덕션이 0px 이 된 그 사고와 같은 형태다."""

    async def _child() -> None:
        await asyncio.sleep(0.02)

    async def _body() -> int:
        asyncio.ensure_future(_child())  # noqa: RUF006
        return await _async_batch._drain_child_tasks(timeout=bad)

    drained = asyncio.run(_body())
    assert drained >= 1, (
        f"timeout={label} 에서 배수가 건너뛰어졌다(drained={drained}) — "
        "무의미한 값은 기본값으로 돌아가야 한다"
    )


def test_NaN_상한이_상한을_무력화하지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★`min(nan, 60)` 은 **`nan`** 을 돌려줘 상한마저 무력화된다(4라운드 실측: NaN + 3600초
    자식이 5초 뒤에도 대기 중). `max()` 를 앞에 두는 형태로는 NaN 을 못 잡는다 —
    `not (timeout >= MIN)` 이어야 NaN 이 하한으로 떨어진다."""
    import math

    async def _never() -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(_async_batch, "_CHILD_DRAIN_TIMEOUT_SEC", 0.05)

    async def _body() -> float:
        task = asyncio.ensure_future(_never())
        task.set_name("NaN-확인용")
        started = asyncio.get_running_loop().time()
        await asyncio.wait_for(_async_batch._drain_child_tasks(timeout=math.nan), timeout=3.0)
        return asyncio.get_running_loop().time() - started

    try:
        elapsed = asyncio.run(_body())
    except TimeoutError:
        pytest.fail("NaN 상한이 클램프되지 않아 무한 대기했다 — 상한이 무력화된다")
    assert elapsed < 1.0, f"NaN 이 하한으로 떨어지지 않았다({elapsed:.2f}초)"


# ★R3 커밋 메시지가 "별칭 추적 + **그걸 태우는 케이스**"라고 선언했는데 **산출물에 케이스가
#   없었다**(4라운드 지적으로 발각 — `_CTOR_FORMS` 가 저장소 어디에도 없었다).
#   §F-24: 선언과 산출물이 갈리면 리뷰어·다음 세션이 이미 된 것으로 오독한다.
_CTOR_FORMS: tuple[tuple[str, str, bool], ...] = (
    ("평문 생성자", "from sqlalchemy.ext.asyncio import create_async_engine\ne = create_async_engine(U)", True),
    ("생성자 별칭 임포트", "from sqlalchemy.ext.asyncio import create_async_engine as _mk\ne = _mk(U)", True),
    ("생성자 재바인딩", "from sqlalchemy.ext.asyncio import create_async_engine\n_mk = create_async_engine\ne = _mk(U)", True),
    ("모듈 경유 호출", "import sqlalchemy.ext.asyncio as sa\ne = sa.create_async_engine(U)", True),
    ("★위양성 다른 함수", "from x import create_sync_engine\ne = create_sync_engine(U)", False),
)


@pytest.mark.parametrize(
    ("label", "source", "should_find"), _CTOR_FORMS, ids=[c[0] for c in _CTOR_FORMS]
)
def test_엔진_수집기가_생성자_별칭도_본다(
    label: str, source: str, should_find: bool, tmp_path: Path
) -> None:
    """★`from ... import create_async_engine as _mk` 한 줄로 엔진 전수수집이 통째로 우회된다."""
    (tmp_path / "m.py").write_text(source, encoding="utf-8")
    found = _module_scope_engines(tmp_path)
    assert bool(found) is should_find, (
        f"'{label}' 를 {'놓쳤다' if should_find else '잘못 신고했다'}: {found}\n{source}"
    )
