"""**이벤트를 담는 프로세스는 반드시 비워야 한다** — 파생형 배선 락.

## 왜 이 파일이 필요한가 (실측 2026-08-28)

`capture_service._QUEUE` 는 **프로세스 로컬 deque**(`maxlen=10_000`)다. 그래서
*"어느 프로세스가 담느냐"* 와 *"어느 프로세스가 비우느냐"* 가 **각각 따로** 참이어야 한다.

`apps/worker`(arq)는 **담기만 하고 비우지 않았다**:

    apps/worker  flush_batch 호출        0건   ← 배수구 없음
    apps/api     flush_batch 호출        3건   ← 대조군(조회기 생존)
    arq 진입점 임포트 폐포               79파일
      그 안의 record_event/record_fallback  4파일  ← 담는다
      그 안의 flush_batch                   0건   ← ★안 비운다

**직접 호출은 0건이었다** — 그래서 종전 조사가 *"워커에는 없다"* 로 끝났다.
닿는 경로는 **전이 임포트**다(실런타임 사슬):

    etl_public_data(arq cron 매일 03:00) → tasks/etl_scheduled.py → MolitClient
      → BaseAPIClient._request 실패 → base_client._emit_growth_fallback → record_event

즉 워커가 담은 이벤트는 **컨테이너 재시작마다 통째로** 사라졌고, 그 안에는
회로차단기 폴백과 `ledger_broken`(severity=critical)이 포함된다.

## ★왜 「목록」이 아니라 「파생」인가

*"api 와 worker 를 검사한다"* 라고 **손으로 적으면 그 목록이 상한이 된다** — 새 프로세스가
생기면 조용히 감시 밖이다. 이 결함이 정확히 그렇게 태어났다(워커는 API 보다 나중에
성장루프에 닿았고, 아무도 그 축을 다시 세지 않았다).

→ **진입점을 `apps/*/main.py` 로 파생시키고, 폐포를 계산해 판정한다.**
"""

from __future__ import annotations

import ast
from pathlib import Path

_PLATFORM = Path(__file__).resolve().parents[3]        # …/propai-platform
_APPS = _PLATFORM / "apps"

_PRODUCERS = {"record_event", "record_fallback"}
_DRAINS = {"flush_batch", "drain_until_empty"}
#: 배수를 **위임하는** 헬퍼. 진입점이 루프를 직접 갖지 않고 이것을 부를 수 있다.
#: ★이름만 믿지 않는다 — `test_delegating_helpers_actually_do_what_their_names_claim`
#:   이 **그 함수들이 실제로 배수하는지**를 따로 태운다(이름 검사는 계약이 아니다).
_PERIODIC_DELEGATES = {"start_flush_loop"}
_SHUTDOWN_DELEGATES = {"stop_flush_loop_and_drain"}


def _module_file(dotted: str) -> Path | None:
    parts = dotted.split(".")
    for root in (_APPS / "api", _APPS / "worker", _PLATFORM):
        p = root.joinpath(*parts)
        for cand in (p.with_suffix(".py"), p / "__init__.py"):
            if cand.is_file():
                return cand
    return None


def _imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out: list[str] = []
    for n in ast.walk(tree):          # ★함수 본문 안의 **지연 임포트**도 걷는다
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.append(n.module)
            out += [f"{n.module}.{a.name}" for a in n.names]
    return out


def _calls(path: Path, names: set[str]) -> list[int]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    hits = []
    for n in ast.walk(tree):          # ★파서로 본다 — 주석·독스트링에 안 걸린다
        if isinstance(n, ast.Call):
            f = n.func
            nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            if nm in names:
                hits.append(n.lineno)
    return hits


def _closure(seed: Path) -> set[Path]:
    seen, stack = {seed}, [seed]
    while stack:
        for m in _imports(stack.pop()):
            p = _module_file(m)
            if p and p not in seen:
                seen.add(p)
                stack.append(p)
    return seen


def _entrypoints() -> list[Path]:
    """★파생형 — 손 목록이 아니다. 새 `apps/<x>/main.py` 는 자동으로 감시망에 든다."""
    return sorted(p for p in _APPS.glob("*/main.py") if p.is_file())


def test_scanner_is_alive_before_any_zero_is_believed() -> None:
    """★「0건」을 믿기 전에 **조회기 생존**부터 증명한다(대조군)."""
    eps = _entrypoints()
    assert len(eps) >= 2, f"★진입점을 {len(eps)}개만 찾았다 — 탐색이 죽었다(위반 아님)"
    names = {p.parent.name for p in eps}
    assert {"api", "worker"} <= names, f"★알려진 진입점이 빠졌다: {names}"

    api_main = _APPS / "api" / "main.py"
    # ★대조군의 **대상이 바뀌었다**: main.py 는 배수를 구현하지 않고 **위임**한다.
    assert _calls(api_main, _PERIODIC_DELEGATES | _SHUTDOWN_DELEGATES), \
        "★api/main.py 에서 배수 위임을 못 찾았다 — 추출기가 죽었다"

    # ★음성 대조군 — 존재하지 않는 이름은 0건이어야 한다(무엇이든 매치하는 조회기가 아님)
    assert not _calls(api_main, {"zzz_nope_no_such_call"}), "★조회기가 아무거나 매치한다"


def _definer_of_drains() -> Path | None:
    """배수 함수를 **정의한** 파일을 파생한다(손으로 적지 않는다)."""
    for f in (_APPS / "api").rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "drain_until_empty":
                return f
    return None


def test_every_entrypoint_that_produces_events_also_drains_them() -> None:
    """★**담는 프로세스는 비워야 한다.** 폐포로 판정한다 — 직접 호출만 보면 놓친다.

    되살리는 변이: `apps/worker/main.py` 의 `drain_until_empty` 호출을 지우면 이 테스트가 죽는다.
    """
    produced_by: dict[str, int] = {}
    drained_by: dict[str, int] = {}

    # ★★**구현 모듈은 배선으로 세지 않는다**(독립 적대 렌즈 실측).
    #   `drain_until_empty` 를 **정의한** 모듈은 `record_event` 도 정의하므로
    #   **모든 생산자의 폐포에 반드시 들어간다.** 그 안의 호출까지 세면
    #   `drained_by >= 1` 이 **누구에게나 참**이 되어 이 단언이 **공허**해진다 —
    #   실제로 워커 배선을 **통째로 지워도** 이 테스트가 초록이었다.
    #   → 세는 것은 **「배수를 배선했는가」**이지 「배수 코드가 폐포에 있는가」가 아니다.
    definer = _definer_of_drains()
    assert definer is not None, "★배수 정의 모듈을 못 찾았다 — 추출기가 죽었다(위반 아님)"

    for ep in _entrypoints():
        name = ep.parent.name
        clo = _closure(ep)
        produced_by[name] = sum(len(_calls(f, _PRODUCERS)) for f in clo)
        drained_by[name] = sum(
            len(_calls(f, _DRAINS | _PERIODIC_DELEGATES | _SHUTDOWN_DELEGATES))
            for f in clo
            if f != definer
        )

    # ★공허 진리 가드 — 「담는 진입점」이 하나도 없으면 아래 단언은 무의미하다.
    producers = {k: v for k, v in produced_by.items() if v > 0}
    assert producers, f"★담는 진입점이 0개 — 폐포 계산이 죽었다(위반 아님): {produced_by}"

    offenders = {k: produced_by[k] for k in producers if drained_by[k] == 0}
    assert not offenders, (
        f"★이벤트를 담기만 하고 **비우지 않는 프로세스**: {offenders}\n"
        f"   담는 곳={produced_by} · 비우는 곳={drained_by}\n"
        f"   큐는 프로세스 로컬이라 다른 프로세스의 flush 가 이 큐를 볼 수 없다 —\n"
        f"   그 프로세스가 담은 이벤트는 **재시작마다 통째로 사라진다.**"
    )


def _phase_bindings(tree: ast.AST) -> dict[str, str]:
    """`WorkerSettings.on_startup/on_shutdown = <함수>` 바인딩을 **파생**한다."""
    out: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            for st in n.body:
                if isinstance(st, ast.Assign):
                    tgt = getattr(st.targets[0], "id", "")
                    if tgt in ("on_startup", "on_shutdown"):
                        nm = getattr(st.value, "id", getattr(st.value, "attr", None))
                        if nm:
                            out[nm] = "startup" if tgt == "on_startup" else "shutdown"
    return out


def _drain_sites_by_position(path: Path) -> dict[str, list[int]]:
    """배수 호출을 **주기** 와 **종료** 로 가른다.

    ★★**이름만으로 가르지 않는다.** 종전 판은 `start_flush_loop` 이라는 **호출 이름**만 보고
      `periodic` 으로 넣었다. 그래서 **기동부와 종료부를 서로 맞바꿔도** 락 4건이 전부 초록이었다
      (독립 적대 렌즈 실측) — 즉 *"루프를 죽을 때 만들고, 마지막 배수를 빈 큐에 대고 한다"* 는
      **원래 결함을 그대로 되살려도** 통과했다.

    → **호출이 실제로 어느 단계에 있는지**를 구조로 판정하고, **이름과 단계가 일치할 때만** 센다.
      단계 판정은 두 형태를 모두 다룬다(둘 다 이 저장소에 실재한다):
        · arq 워커  — `WorkerSettings.on_startup/on_shutdown` 바인딩에서 **파생**
        · FastAPI   — `lifespan` 은 **한 함수 안**이라 이름으로는 못 가른다 →
                      **`yield` 앞이 기동 · 뒤가 종료**
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    bindings = _phase_bindings(tree)

    def enclosing_fn(n: ast.AST):
        cur = parent.get(n)
        while cur is not None:
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur
            cur = parent.get(cur)
        return None

    def phase_of(n: ast.AST) -> str | None:
        fn = enclosing_fn(n)
        while fn is not None:
            if fn.name in bindings:
                return bindings[fn.name]
            ylines = [y.lineno for y in ast.walk(fn) if isinstance(y, (ast.Yield, ast.YieldFrom))]
            if ylines:
                return "startup" if n.lineno < min(ylines) else "shutdown"
            fn = enclosing_fn(fn)
        return None

    def in_loop(n: ast.AST) -> bool:
        cur = parent.get(n)
        while cur is not None:
            if isinstance(cur, (ast.While, ast.For, ast.AsyncFor)):
                return True
            cur = parent.get(cur)
        return False

    out: dict[str, list[int]] = {"periodic": [], "shutdown": []}
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
        ph = phase_of(n)
        if nm in _PERIODIC_DELEGATES:
            # ★기동 단계에 있을 때만 「주기 배수」로 인정한다(맞바꾸기 방어).
            if ph == "startup":
                out["periodic"].append(n.lineno)
        elif nm in _SHUTDOWN_DELEGATES:
            if ph == "shutdown":
                out["shutdown"].append(n.lineno)
        elif nm in _DRAINS:
            out["periodic" if in_loop(n) else "shutdown"].append(n.lineno)
    return out


def test_delegating_helpers_actually_do_what_their_names_claim() -> None:
    """★위임 헬퍼를 **이름으로** 인정했으니, 그 이름이 **거짓이 아님**을 따로 태운다.

    이걸 안 하면 위 배선 락이 *"`start_flush_loop` 을 부른다"* 만 보는 **이름 검사**가 된다 —
    그 함수가 배수를 그만둬도 진입점 락은 초록이다.
    """
    src = (_APPS / "api" / "app/services/growth/capture_service.py").read_text(encoding="utf-8")
    fns = {n.name: n for n in ast.walk(ast.parse(src))
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    for name in _PERIODIC_DELEGATES | _SHUTDOWN_DELEGATES:
        assert name in fns, f"★위임 헬퍼 {name} 가 없다 — 추출기가 죽었거나 배선이 끊겼다"

    def _names(fn):
        return {getattr(c.func, "attr", getattr(c.func, "id", None))
                for c in ast.walk(fn) if isinstance(c, ast.Call)}

    start = fns["start_flush_loop"]
    assert _names(start) & _DRAINS, "★start_flush_loop 이 **배수를 하지 않는다** — 이름만 남았다"
    assert any(isinstance(n, ast.While) for n in ast.walk(start)), \
        "★start_flush_loop 에 **주기 루프가 없다** — 한 번만 비우고 끝난다"

    stop = fns["stop_flush_loop_and_drain"]
    assert _names(stop) & _DRAINS, "★stop_flush_loop_and_drain 이 **배수를 하지 않는다**"
    assert "cancel" in _names(stop), "★stop_flush_loop_and_drain 이 루프를 **안 멈춘다**"


def test_every_producing_entrypoint_drains_periodically_AND_on_shutdown() -> None:
    """★배수는 **두 자리 모두** 있어야 한다 — 파생형으로 전 진입점에 건다.

    종전 판은 워커만 손으로 검사해서 **API 의 주기 배수를 지워도 초록**이었다
    (변이 M3 가 생존했다 — 폐포에 종료 배수가 남아 있으면 「배수한다」가 참이 되어서).
    ★**「배수구가 있다」와 「제때 배수한다」는 다른 명제**다.

    되살리는 변이: `apps/api/main.py` 또는 `apps/worker/main.py` 의 **어느 쪽 한 자리**를
    지워도 이 테스트가 죽는다.
    """
    checked = 0
    for ep in _entrypoints():
        clo = _closure(ep)
        if not sum(len(_calls(f, _PRODUCERS)) for f in clo):
            continue                       # 담지 않는 진입점은 배수 의무가 없다
        sites = _drain_sites_by_position(ep)
        assert sites["periodic"], (
            f"★{ep.parent.name}: **주기 배수가 없다** — 큐가 프로세스 수명 내내 차올라 "
            f"maxlen 오버플로로 조용히 밀려난다. (발견된 배수: {sites})"
        )
        assert sites["shutdown"], (
            f"★{ep.parent.name}: **종료 배수가 없다** — 잔여가 통째로 사라진다. "
            f"(발견된 배수: {sites})"
        )
        checked += 1

    # ★공허 진리 가드 — 하나도 안 봤으면 위 단언은 전부 무의미하다.
    assert checked >= 2, f"★담는 진입점을 {checked}개만 검사했다 — 폐포 계산이 죽었다(위반 아님)"
