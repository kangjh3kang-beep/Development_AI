"""심의엔진(deliberation-review)의 공급(supply) 파이프라인 **도달성 락**.

## 왜 이 파일이 있나

`#420` 이 HITL 승인에 SoD(직무분리 — 승인자 신원 필수·자기승인 차단)를 넣었다.
그 뒤 여러 세션이 반복해서 *"SoD 통제가 프로덕션에 없다"* 를 **보안 P0 티켓**으로 올렸다.

그런데 실제로 재 보면 그것은 배포 문제가 아니다. `HITLQueue` 는 **어떤 실행 경로에서도
불리지 않는다.** 상류(파싱·추출·후보생성)와 하류(미러쓰기)도 같이 죽어 있다. 즉 배포해도
아무 요청이 그 코드를 지나가지 않으므로, **재배포로 닫히는 공격 경로가 없다.**

이 사실은 `hitl_queue.py` 모듈 독스트링이 이미 정직하게 적어 두었다
("author 를 채우는 생성 경로가 아직 없어 … **배선 미완료**"). 그런데 그 문장이 코드 주석에만
있어서, 다음 세션이 **다시** 보안 결함으로 오독했다. 그래서 **테스트로 고정**한다.

## 이 락이 하는 일 (양방향)

진입점(`app.main`, `app.tasks.*`)에서 import 를 따라가 **도달 가능한 모듈 집합**을 구하고,
`app.supply.*` 중 도달하지 못하는 것이 아래 선언과 **정확히 일치**하는지 본다.

- 새 모듈이 미도달로 늘면 → 실패(죽은 코드가 조용히 늘지 않게)
- 선언된 것이 도달하게 되면 → 실패(**부채가 해소된 것이니 선언을 지우라**는 뜻)

한쪽만 걸면 반대쪽이 무제한이 된다(저장소 규율 D.19 — 경계는 한 쌍).

## 왜 grep 이 아니라 AST 인가

소스를 정규식으로 훑으면 **주석·문자열에 뚫린다**(이 저장소에서 두 번 실증됐다).
`ast` 는 주석·문자열을 애초에 토큰으로 보지 않으므로 그 변이에 원리적으로 면역이다.
함수 안쪽의 지연 import(`supply_tasks.py` 가 그렇게 쓴다)도 `ast.walk` 가 같이 잡는다.

## 기준·유효시각

`origin/main` **6e5d445b**(2026-08-16) 기준 실측. 총 모듈 241 · 도달 159 · supply 미도달 6/11.
**뒤집힘 조건**: 누군가 공급 파이프라인을 배선하면 이 락이 실패하며 그 사실을 알린다 —
그때가 SoD 를 실제 승인 경로에 붙일 시점이다(그 전까지 SoD 재배포는 보안 티켓이 아니다).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

# 심의엔진 앱 루트. 이 파일 기준 상대경로로만 찾는다(CWD 에 의존하지 않음 —
# CI 는 propai-platform 에서 돌지만 로컬은 어디서든 돌 수 있다).
_APP_ROOT = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "deliberation-review"
    / "apps"
    / "api"
    / "app"
)

# 진입점 = 실제로 프로세스가 시작되는 곳.
#   app.main        → uvicorn 이 띄우는 FastAPI 앱(ops/run_engine.sh)
#   app.tasks.*     → celery 워커가 등록하는 태스크(ops/run_worker.sh)
_ENTRY_PREFIXES = ("app.main", "app.tasks.")

# ★선언: 진입점에서 **도달하지 못하는** supply 모듈과 그 이유.
#   목록을 늘리는 것이 목적이 아니다 — 코드에서 파생한 실측과 **정확히** 맞아야 통과한다.
_DECLARED_UNREACHABLE: dict[str, str] = {
    "app.supply.parser.pdf_parser": "hwp_parser 만 부르는데 그 hwp_parser 가 미도달 — 전이적으로 죽음",
    "app.supply.parser.hwp_parser": "수집 문서를 파싱하는 경로가 배선되지 않음",
    "app.supply.extractor.rule_extractor": "파싱 결과에서 RuleCandidate 를 뽑는 경로가 배선되지 않음",
    "app.supply.hitl.hitl_queue": "후보 승인 큐. #420 SoD 가 여기 있으나 생성·승인 경로가 둘 다 없음",
    "app.supply.mirror.mirror_writer": "승인된 후보를 미러에 쓰는 경로가 배선되지 않음",
    "app.supply.harvester.tier2_site_harvester": "harvester 가 tier1·tier3 만 부르고 tier2 는 부르지 않음",
}


def _module_name(path: Path) -> str:
    """파일 경로를 파이썬 모듈 이름으로 바꾼다(app/supply/x.py → app.supply.x)."""
    rel = path.relative_to(_APP_ROOT.parent)
    name = str(rel.with_suffix("")).replace(os.sep, ".")
    return name.removesuffix(".__init__")


def _imported_names(path: Path, module: str) -> set[str]:
    """그 파일이 import 하는 이름들. 상대 import 와 `from x import y` 의 y 까지 펼친다."""
    found: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 상대 import(from . import x)
                parts = package.split(".")
                if node.level > 1:
                    parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join(parts + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            found.add(base)
            # `from app.supply.hitl import hitl_queue` 처럼 모듈을 이름으로 가져오는 형태.
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


@pytest.fixture(scope="module")
def reachability() -> tuple[set[str], set[str], set[str]]:
    """(전체 모듈, 진입점에서 도달 가능한 모듈, 패키지 모듈) 을 돌려준다.

    패키지(`__init__.py`)를 따로 돌려주는 이유: 모듈 이름에서 `.__init__` 을 떼기 때문에
    이름만 봐서는 `app.supply.hitl`(패키지)과 실제 모듈을 가릴 수 없다. 파일로 판별해야 한다.
    """
    assert _APP_ROOT.is_dir(), f"심의엔진 앱 경로를 찾지 못했다: {_APP_ROOT}"

    modules: dict[str, Path] = {}
    for dirpath, _dirnames, filenames in os.walk(_APP_ROOT):
        for filename in filenames:
            if filename.endswith(".py"):
                path = Path(dirpath) / filename
                modules[_module_name(path)] = path

    packages = {name for name, path in modules.items() if path.name == "__init__.py"}
    graph = {name: _imported_names(path, name) for name, path in modules.items()}

    reached: set[str] = set()
    stack = [m for m in modules if m.startswith(_ENTRY_PREFIXES)]
    while stack:
        current = stack.pop()
        if current in reached:
            continue
        reached.add(current)
        stack.extend(t for t in graph[current] if t in modules and t not in reached)

    return set(modules), reached, packages


def test_analyzer_is_alive(reachability: tuple[set[str], set[str], set[str]]) -> None:
    """공허한 초록 방지 — 분석기가 죽으면 아래 도달성 단언이 **거저** 통과한다.

    대조군 두 겹:
      ① 모듈을 실제로 여러 개 찾았는가(경로가 어긋나면 0개가 되고 모든 집합이 공집합)
      ② **진입점에서 라우트가 전부 도달하는가** — main.py 가 include 하므로 반드시 참이다.
         하나라도 미도달이면 그래프 구성이 깨진 것이지 코드가 바뀐 것이 아니다.
    """
    modules, reached, packages = reachability

    assert len(modules) >= 200, f"모듈을 너무 적게 찾았다({len(modules)}개) — 경로/파서 점검 필요"
    assert len(reached) >= 100, f"도달 모듈이 너무 적다({len(reached)}개) — 진입점 탐색 점검 필요"

    routes = {m for m in modules if m.startswith("app.api.routes.") and m not in packages}
    assert len(routes) >= 8, f"라우트 모듈을 너무 적게 찾았다({len(routes)}개)"
    unreached_routes = sorted(routes - reached)
    assert not unreached_routes, (
        "대조군 실패 — main.py 가 include 하는 라우트가 미도달로 나왔다. "
        f"코드 변화가 아니라 분석기 결함이다: {unreached_routes}"
    )


def test_supply_pipeline_reachability_matches_declaration(
    reachability: tuple[set[str], set[str], set[str]],
) -> None:
    """supply 층의 **미도달 집합**이 선언과 정확히 일치해야 한다(양방향).

    이 단언이 지키는 사실: **심의엔진의 HITL 승인 통제(SoD)는 실행 경로에 없다.**
    따라서 "SoD 가 프로덕션에 없다"는 배포로 고칠 문제가 아니라 **배선 부채**다.
    """
    modules, reached, packages = reachability

    supply = {m for m in modules if m.startswith("app.supply.") and m not in packages}
    assert len(supply) >= 10, f"supply 모듈을 너무 적게 찾았다({len(supply)}개)"

    unreachable = supply - reached

    newly_dead = sorted(unreachable - set(_DECLARED_UNREACHABLE))
    assert not newly_dead, (
        "진입점에서 닿지 않는 supply 모듈이 새로 생겼다. 배선하거나, 죽은 코드임을 "
        f"_DECLARED_UNREACHABLE 에 이유와 함께 적어라: {newly_dead}"
    )

    revived = sorted(set(_DECLARED_UNREACHABLE) - unreachable)
    assert not revived, (
        "★배선 부채가 해소됐다 — 아래 모듈이 이제 실행 경로에서 도달한다. "
        "_DECLARED_UNREACHABLE 에서 지우고, hitl_queue 가 포함됐다면 "
        "**SoD 를 실제 승인 경로에 붙일 시점**이다(그전까지는 재배포가 보안 조치가 아니었다): "
        f"{revived}"
    )


def test_sod_control_has_no_caller(reachability: tuple[set[str], set[str], set[str]]) -> None:
    """#420 SoD 가 사는 모듈이 실행 경로에 없다는 사실을 **따로** 못박는다.

    위 테스트는 집합 전체를 보므로, 선언을 통째로 고치면 이 사실이 조용히 빠져나갈 수 있다.
    보안 판단이 걸린 항목이라 단독 단언을 하나 더 둔다.
    """
    modules, reached, _packages = reachability

    sod_module = "app.supply.hitl.hitl_queue"
    assert sod_module in modules, f"{sod_module} 가 사라졌다 — 이 락의 전제를 다시 세워라"
    assert sod_module not in reached, (
        "★상태가 바뀌었다 — SoD 큐가 이제 실행 경로에서 도달한다. "
        "이 테스트의 전제(재배포는 보안 조치가 아니다)가 뒤집혔으니, "
        "승인 경로의 신원 계약(승인자 위조 가능성)과 큐 영속성을 함께 점검하라."
    )
