"""변이 도구가 **못 믿는 값으로 판정을 발행하지 않는가**.

## 무엇이 결함이었나 (2026-08-27 · 동료 세션 제보 → 원문 확증 → 재현)

`scripts/mutate_manual.sh` 는 테스트 명령에 파이프가 있으면 **경고를 찍었다**(그 파일 주석이
*"이 도구의 첫 실사용에서 그 일이 났다(2026-08-21)"* 라고 스스로 적어 두었다). 그런데
경고는 `stderr` 로 나가고 **판정은 오염된 `RC` 로 그대로 발행**됐다.

    bash mutate_manual.sh t.py '...' bash -c 'grep -q "VALUE = 1" t.py | cat'
      → ★경고: … (stderr)
      → SURVIVED — …            ← **거짓**(grep 은 실패했다 · 파이프 끝 cat 이 0 을 준다)

즉 도구가 *"이 값은 못 믿는다"* 를 **알면서 그 값으로 판정을 찍었다.** 다음 사람은 경고가
아니라 **마지막 줄**을 읽는다(동료 세션이 실제로 오보를 읽었다).

★**경고는 산문이고 판정이 산출물이다.** 이 저장소 `CLAUDE.md` §검증 규율 9
(*"`cmd | tail` 은 파이프 끝의 종료코드를 준다"*)가 **도구 안에서** 재발한 형태다.

## 처방

파이프가 보이면 `SURVIVED`/`CAUGHT` 를 **발행하지 않고** `판정 불가(무효)` + **exit 12**.
차단하되 길을 준다 — `set -o pipefail` 이 있으면 `RC` 를 믿을 수 있으므로 정상 판정하고,
정당한 리터럴 `|`(예: `-k 'a|b'` 정규식)는 `MUTATE_ALLOW_PIPE="사유"` 로 통과시키되
**사유를 출력에 남긴다**(위양성도 결함이다).

## ★이 락이 **못 보는** 것

- 파이프 탐지는 **인자 문자열**만 본다. 호출자의 셸이 이미 소비한 파이프
  (`bash mutate_manual.sh … | tail`)는 도구에 **도달하지 않으므로** 여기서 못 막는다.
  그 형태는 도구의 *출력*을 자르는 것이라 판정 자체는 오염되지 않는다.
- `MUTATE_ALLOW_PIPE` 사유의 **타당성**은 검사하지 않는다(사람이 거짓 사유를 댈 수 있다).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "scripts/mutate_manual.sh"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """변이 대상이 담긴 최소 git 저장소(도구가 커밋 상태를 요구한다)."""
    (tmp_path / "t.py").write_text("VALUE = 1\n", encoding="utf-8")
    for cmd in (["git", "init", "-q", "."], ["git", "add", "-A"],
                ["git", "-c", "user.email=a@b", "-c", "user.name=a",
                 "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _run(repo: Path, test_cmd: str, env_extra: dict | None = None):
    """도구를 돌린다.

    ★**기준선 게이트를 명시적으로 건너뛴다.** 이 파일의 락은 «변이 후 rc 를 어떻게
    판정하는가» 를 시험하므로 **기준선이 빨간 것이 정상**이다(예: `grep -q "VALUE = 2"`
    는 변이 **전에는 당연히 실패**한다). 게이트를 그냥 두면 판정 자체가 발행되지 않아
    이 파일 전체가 «판정 줄 없음» 으로 죽는다 — 결함이 아니라 **두 규율이 만난 자리**다.

    ★건너뛴 실행의 CAUGHT 를 «변이를 잡았다» 의 근거로 인용하면 안 되는데, 이 파일은
    그렇게 쓰지 않는다 — **판정 문자열의 형태**만 본다(`SURVIVED —`/`CAUGHT —`/`판정 불가`).
    호출자가 `MUTATE_SKIP_BASELINE` 을 덮어쓰면 그 의도를 따른다.
    """
    import os
    env = {**os.environ,
           "MUTATE_SKIP_BASELINE": "락이 의도한 빨간 기준선(이 파일은 판정 형태만 본다)",
           **(env_extra or {})}
    return subprocess.run(
        ["bash", str(TOOL), "t.py", "s/VALUE = 1/VALUE = 2/", "bash", "-c", test_cmd],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def _verdict_lines(out: str) -> list[str]:
    """판정 **줄**만 고른다.

    ★맨 문자열 `in` 으로 보면 안내문구에 걸린다 — 실제로 걸렸다: `판정 불가` 메시지가
      *"CAUGHT 가 SURVIVED 로 보고된다"* 라고 **설명**하기 때문이다.
      이 저장소가 문서화한 「내 패턴이 내 텍스트를 집는다」 그대로다.
      판정은 **줄 시작**으로 발행되므로 그 형태에 결속한다.
    """
    return [ln for ln in out.splitlines()
            if ln.startswith(("SURVIVED —", "CAUGHT —", "판정 불가"))]


def test_tool_exists():
    """★공허한 초록 방지 — 도구가 없으면 아래가 전부 무의미하다."""
    assert TOOL.is_file(), TOOL


# ── 탐지 ────────────────────────────────────────────────────────────────
def test_pipe_suppresses_the_verdict_entirely(repo: Path):
    """★핵심 — 못 믿는 값으로 SURVIVED/CAUGHT 를 **찍지 않는다**."""
    r = _run(repo, 'grep -q "VALUE = 1" t.py | cat')
    lines = _verdict_lines(r.stdout)
    assert lines, f"판정 줄을 하나도 못 찾았다 — 추출기 의심: {r.stdout!r}"
    assert all(ln.startswith("판정 불가") for ln in lines), (
        f"오염된 rc 로 판정을 발행했다: {lines}"
    )
    assert r.returncode == 12, f"판정 불가는 성공도 실패도 아니어야 한다: {r.returncode}"


# ── 특이도(위양성 방지) — 두 모집단이 **다른 결과**를 내야 한다 ──────────
def test_no_pipe_and_failing_test_reports_caught(repo: Path):
    r = _run(repo, 'grep -q "VALUE = 1" t.py')
    assert _verdict_lines(r.stdout)[0].startswith("CAUGHT —"), r.stdout
    assert r.returncode == 1


def test_no_pipe_and_passing_test_reports_survived(repo: Path):
    r = _run(repo, 'grep -q "VALUE = 2" t.py')
    assert _verdict_lines(r.stdout)[0].startswith("SURVIVED —"), r.stdout
    assert r.returncode == 0


def test_the_two_populations_actually_differ(repo: Path):
    """★차가 0인 픽스처는 잠금이 아니다 — 위 둘이 실제로 갈리는지 확인한다."""
    a = _run(repo, 'grep -q "VALUE = 1" t.py').returncode
    b = _run(repo, 'grep -q "VALUE = 2" t.py').returncode
    assert a != b, (a, b)


# ── 탈출구(차단하되 길을 준다) ──────────────────────────────────────────
def test_pipefail_makes_the_code_trustworthy_again(repo: Path):
    """호출자가 `set -o pipefail` 로 막았으면 rc 를 믿을 수 있다."""
    r = _run(repo, 'set -o pipefail; grep -q "VALUE = 1" t.py | cat')
    assert _verdict_lines(r.stdout)[0].startswith("CAUGHT —"), r.stdout
    assert r.returncode == 1


def test_literal_pipe_can_be_declared_and_the_reason_is_printed(repo: Path):
    """정당한 리터럴 `|`(정규식)까지 막으면 그것도 결함이다 — 단, **사유를 남긴다**."""
    r = _run(repo, 'grep -qE "VALUE = 1|NOPE" t.py',
             {"MUTATE_ALLOW_PIPE": "정규식 리터럴"})
    assert _verdict_lines(r.stdout)[0].startswith("CAUGHT —"), r.stdout
    assert "정규식 리터럴" in r.stdout, "예외를 썼는데 사유가 출력에 없다"
    assert r.returncode == 1
