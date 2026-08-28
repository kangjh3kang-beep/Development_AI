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
    assert _calls(api_main, _DRAINS), "★api/main.py 에서 배수 호출을 못 찾았다 — 추출기가 죽었다"

    # ★음성 대조군 — 존재하지 않는 이름은 0건이어야 한다(무엇이든 매치하는 조회기가 아님)
    assert not _calls(api_main, {"zzz_nope_no_such_call"}), "★조회기가 아무거나 매치한다"


def test_every_entrypoint_that_produces_events_also_drains_them() -> None:
    """★**담는 프로세스는 비워야 한다.** 폐포로 판정한다 — 직접 호출만 보면 놓친다.

    되살리는 변이: `apps/worker/main.py` 의 `drain_until_empty` 호출을 지우면 이 테스트가 죽는다.
    """
    produced_by: dict[str, int] = {}
    drained_by: dict[str, int] = {}

    for ep in _entrypoints():
        name = ep.parent.name
        clo = _closure(ep)
        produced_by[name] = sum(len(_calls(f, _PRODUCERS)) for f in clo)
        drained_by[name] = sum(len(_calls(f, _DRAINS)) for f in clo)

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


def _drain_sites_by_position(path: Path) -> dict[str, list[int]]:
    """배수 호출을 **주기(while 안)** 와 **종료(while 밖)** 로 가른다.

    ★두 자리는 **다른 일을 한다**: 주기 배수가 없으면 큐가 프로세스 수명 내내 차올라
      `maxlen` 오버플로로 **조용히 밀려나고**, 종료 배수가 없으면 **잔여가 통째로** 사라진다.
      한쪽만 단언하면 반대쪽을 지워도 초록이다(한쪽만 거는 단언).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    def in_loop(n: ast.AST) -> bool:
        cur = parent.get(n)
        while cur is not None:
            if isinstance(cur, (ast.While, ast.For, ast.AsyncFor)):
                return True
            cur = parent.get(cur)
        return False

    out: dict[str, list[int]] = {"periodic": [], "shutdown": []}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            if nm in _PERIODIC_DELEGATES:
                out["periodic"].append(n.lineno)
            elif nm in _SHUTDOWN_DELEGATES:
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
