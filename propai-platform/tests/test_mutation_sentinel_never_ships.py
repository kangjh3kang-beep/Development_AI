"""★변이 표식(`__MUTATED__`)이 **출하 소스에 실려 있는지** — 저장소 전수, 파생형.

## 왜 이 파일이 새로 필요한가 (2026-09-08)

이미 형제 락이 있었다 — `apps/api/tests/test_toss_payment_locks.py` 의
`test_no_mutation_sentinel_survives_into_shipped_source()`. 2026-09-06 에 결제 파일이
`__MUTATED__` 인 채로 커밋·푸시된 사고(`db9c155e0`) 뒤에 만든 것이다.

**그런데 그 락의 모집단이 손으로 고른 목록이었다**::

    list((_API / "app/services/billing").glob("*.py")) + [_API / "routers/billing.py"]

그래서 **48시간 뒤 프론트에서 같은 결함이 그대로 재발했다** —
`apps/web/components/sales-app/PlatformReturnLink.tsx:44` 가 `className="__MUTATED__"` 로
HEAD 에 실렸다(2026-09-08, 적대 리뷰가 잡음). 그 링크는 「같은 탭으로 들어와 갇힌」 사용자의
**유일한 탈출 버튼**이고, 존재하지 않는 클래스라 터치 타깃까지 잃는다.

> **처방을 적용한 범위 = 결함이 사는 범위인지 확인하라.**
> 결함은 «결제 코드에 표식이 남는다» 가 아니라 **«어디든 표식이 남는다»** 였다.

★그리고 이건 **산문이 못 막은 실패**다. 저장소 메모리에
*「변이가 도는 중에 커밋하면 `__MUTATED__` 가 출하된다」* 가 **이미 적혀 있었고**,
그것을 쓴 사람이 이틀 뒤 같은 일을 했다. **산문은 「다음에 조심」, 락은 「다음에 불가능」이다.**

## 축

**`git ls-files` 로 추적 중인 런타임 소스 전수**(테스트·픽스처 제외).
새 파일이 생기면 **내가 이 락을 고치지 않아도 자동으로 들어온다.**

## 왜 워킹트리가 아니라 `git show HEAD:` 인가

변이 도구는 실행이 끝나면 워킹트리를 **스냅샷에서 복원**한다. 그래서 워킹트리는 깨끗한데
**HEAD 에만 표식이 남는** 상태가 성립한다 — 실제로 그렇게 났다(워킹트리에 정답, HEAD 에 변이).
워킹트리를 보는 검사는 **바로 그 형태를 못 잡는다.**
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# 변이 도구가 심는 표식. ★리터럴을 쪼개 둔다 — 이 파일 자신이 검사에 걸리지 않게.
SENTINEL = "__MUT" + "ATED__"

_HERE = Path(__file__).resolve()


def _repo_root() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=_HERE.parent, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _tracked_runtime_sources(repo: str) -> list[str]:
    """추적 중인 런타임 소스 — **파생형**(손으로 열거하지 않는다)."""
    out = subprocess.run(
        ["git", "ls-files", "--", "*.py", "*.ts", "*.tsx", "*.js", "*.jsx"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    def is_runtime(p: str) -> bool:
        # 테스트·픽스처는 표식을 **정당하게** 담을 수 있다(이 파일처럼).
        if "/tests/" in p or "/__tests__/" in p or "/e2e/" in p:
            return False
        if any(seg in p for seg in (".test.", ".spec.", "/fixtures/", "/node_modules/")):
            return False
        # 변이 도구 자신은 표식을 정의한다.
        if p.startswith("scripts/"):
            return False
        return True

    return [p for p in out if is_runtime(p)]


def _head_blob(repo: str, path: str) -> str | None:
    r = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    return r.stdout if r.returncode == 0 else None


@pytest.fixture(scope="module")
def repo() -> str:
    return _repo_root()


@pytest.fixture(scope="module")
def sources(repo: str) -> list[str]:
    return _tracked_runtime_sources(repo)


def test_population_is_not_empty(sources: list[str]) -> None:
    """★공허 진리 가드 — 모집단이 비면 아래 «표식 0건» 이 무의미하다."""
    assert len(sources) > 500, f"런타임 소스 수집이 비정상적으로 적다: {len(sources)}"
    # 두 생태계가 **모두** 들어왔는지 — 한쪽만 세면 그 미러가 무잠금이 된다.
    assert any(p.endswith(".py") for p in sources), "백엔드가 모집단에 없다"
    assert any(p.endswith((".ts", ".tsx")) for p in sources), "프론트가 모집단에 없다"


def test_scanner_is_alive(repo: str, sources: list[str]) -> None:
    """★대조군 — 조회기가 실제로 파일 내용을 읽고 있음을 증명한다.

    이 검사가 없으면 «표식 0건» 이 «파일을 하나도 못 읽었다» 와 구별되지 않는다.
    반드시 있어야 할 문자열(`import`)이 모집단에서 검출되는지 본다.
    """
    hits = 0
    for path in sources[:40]:
        blob = _head_blob(repo, path)
        if blob and "import" in blob:
            hits += 1
    assert hits > 10, f"조회기가 HEAD 블롭을 못 읽는다(히트 {hits})"


def test_no_mutation_sentinel_in_head(repo: str, sources: list[str]) -> None:
    """★본판정 — **HEAD 에 커밋된** 런타임 소스에 변이 표식이 없다.

    워킹트리가 아니라 HEAD 를 보는 이유는 모듈 독스트링에 적었다:
    변이 도구가 워킹트리를 복원하므로 **워킹트리는 깨끗한데 HEAD 에만 남는** 상태가 실재한다.
    """
    offenders: list[str] = []
    for path in sources:
        blob = _head_blob(repo, path)
        if blob and SENTINEL in blob:
            offenders.append(path)

    assert not offenders, (
        "변이 표식이 커밋된 소스에 남아 있다 — 변이 실행 중에 커밋한 것이다.\n"
        "  ★워킹트리에 정답이 있을 수 있다. `git diff` 로 **방향을 확인**하고 워킹트리를 커밋하라.\n"
        "  ★`git checkout --` 는 거꾸로 간다(깨진 쪽으로 되돌린다).\n"
        + "\n".join(f"  - {p}" for p in offenders)
    )
