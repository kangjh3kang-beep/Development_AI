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


def test_worker_drains_on_both_startup_loop_and_shutdown() -> None:
    """★두 자리 **모두** 필요하다 — 주기 배수만 있으면 **종료 시 잔여**가 사라진다.

    한쪽만 단언하면 반대쪽을 지워도 초록이다(한쪽만 거는 단언).
    """
    src = (_APPS / "worker" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    where: dict[str, list[int]] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.AsyncFunctionDef) and fn.name in ("startup", "shutdown"):
            where[fn.name] = [
                n.lineno for n in ast.walk(fn)
                if isinstance(n, ast.Call)
                and getattr(n.func, "attr", getattr(n.func, "id", None)) in _DRAINS
            ]
    assert set(where) == {"startup", "shutdown"}, f"★훅을 못 찾았다: {sorted(where)}"
    assert where["startup"], "★startup 에 배수 루프가 없다 — 워커가 담기만 한다"
    assert where["shutdown"], "★shutdown 에 마지막 배수가 없다 — 종료 시 잔여가 사라진다"
