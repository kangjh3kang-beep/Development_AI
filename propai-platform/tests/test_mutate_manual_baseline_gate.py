"""`mutate_manual.sh` 의 **기준선 게이트** 락 — 빨간 기준선에서 판정을 발행하지 않는다.

## 무엇이 결함이었나 (실증 2026-08-27T23:3xZ)

일부러 실패하는 테스트를 기준선으로 두고 **의미가 완전히 동일한 변이**를 넣었다:

    LATENCY_ABSOLUTE_DEVIATION_MS = 5000  →  = 5_000     (파이썬에서 같은 값)
    → 도구가 **CAUGHT** 를 발행했다

빨간 기준선에서는 **변이와 무관하게 rc≠0** 이므로 **모든 변이가 거짓 CAUGHT** 다.
도구는 파이프 오염(exit 12)·미커밋(10)·주입실패(11)를 이미 막고 있었는데
**이 축만 비어 있었다** — 그리고 **가장 조용하다**(빨간 기준선은 로그를 안 남긴다).

★동료 세션이 인계에서 지적했고 저자가 재현했다.

## ★세 축을 따로 잠근다 (CLAUDE.md — 탐지·특이도·배선)

- **탐지**: 빨간 기준선이면 `exit 13` 이고 판정 문구를 **안 찍는다**
- **특이도**: 초록 기준선에서는 **정상 판정이 나온다**(항상 거부하는 가드는 곧 꺼진다)
- **배선**: 탈출구(`MUTATE_SKIP_BASELINE`)가 **실제로 통하고**, 그때 **경고를 남긴다**
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[2] / "scripts" / "mutate_manual.sh"


def _run(tmp_path, *, test_rc: int, env=None):
    """대상 파일 하나 + 종료코드를 지정할 수 있는 테스트 명령으로 도구를 돌린다."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sh = lambda *a: subprocess.run(a, cwd=repo, check=True, capture_output=True)
    sh("git", "init", "-q")
    sh("git", "config", "user.email", "t@t")
    sh("git", "config", "user.name", "t")
    target = repo / "target.py"
    target.write_text("VALUE = 5000\n", encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")

    e = dict(os.environ)
    if env:
        e.update(env)
    # ★테스트 명령은 파이프 없이 고정 종료코드만 돌려준다(파이프 축과 섞이지 않게)
    return subprocess.run(
        ["bash", str(_TOOL), "target.py", "s|VALUE = 5000|VALUE = 5_000|",
         "bash", "-c", f"exit {test_rc}"],
        cwd=repo, capture_output=True, text=True, env=e,
    )


# ── 탐지 ────────────────────────────────────────────────────────────────────

def test_red_baseline_refuses_to_judge(tmp_path):
    """★빨간 기준선 → `exit 13` 이고 **CAUGHT 를 찍지 않는다**."""
    r = _run(tmp_path, test_rc=1)
    assert r.returncode == 13, (r.returncode, r.stdout, r.stderr)
    out = r.stdout + r.stderr
    assert "판정 불가" in out
    # ★핵심 — 못 믿는 값으로 판정을 **발행하지 않는다**
    assert "CAUGHT" not in r.stdout, f"빨간 기준선인데 판정을 찍었다:\n{r.stdout}"
    assert "SURVIVED" not in r.stdout


# ── 특이도 ──────────────────────────────────────────────────────────────────

def test_green_baseline_still_judges(tmp_path):
    """★★항상 거부하는 가드는 곧 꺼진다 — 초록 기준선에서는 **판정이 나와야** 한다.

    ★이 케이스가 없으면 `exit 13` 을 무조건 반환하는 구현이 탐지 테스트를 통과한다.
    """
    r = _run(tmp_path, test_rc=0)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "SURVIVED" in r.stdout, r.stdout          # 명령이 항상 0 이므로 생존이 정상
    assert "기준선 초록" in r.stdout


def test_green_baseline_can_still_report_caught(tmp_path):
    """★두 모집단 — 같은 게이트를 통과하고도 **CAUGHT 가 나올 수 있어야** 한다.

    기준선은 초록인데 변이 후에는 빨간 상황을 만든다(파일 내용으로 갈린다).
    """
    repo = tmp_path / "r2"; repo.mkdir()
    sh = lambda *a: subprocess.run(a, cwd=repo, check=True, capture_output=True)
    sh("git", "init", "-q"); sh("git", "config", "user.email", "t@t"); sh("git", "config", "user.name", "t")
    (repo / "target.py").write_text("VALUE = 5000\n", encoding="utf-8")
    sh("git", "add", "-A"); sh("git", "commit", "-q", "-m", "init")
    # ★변이 후에만 실패하는 명령 — 파일을 읽어 판정한다
    checker = repo / "check.sh"
    checker.write_text(textwrap.dedent("""\
        #!/usr/bin/env bash
        grep -q 'VALUE = 5000' target.py && exit 0 || exit 1
    """), encoding="utf-8")
    checker.chmod(0o755)
    sh("git", "add", "-A"); sh("git", "commit", "-q", "-m", "checker")

    r = subprocess.run(
        ["bash", str(_TOOL), "target.py", "s|VALUE = 5000|VALUE = 9999|", "./check.sh"],
        cwd=repo, capture_output=True, text=True,
    )
    assert "기준선 초록" in r.stdout, r.stdout
    assert "CAUGHT" in r.stdout, f"게이트가 CAUGHT 를 막았다:\n{r.stdout}"
    assert r.returncode == 1


# ── 배선(탈출구) ────────────────────────────────────────────────────────────

def test_escape_hatch_works_and_warns(tmp_path):
    """★차단하되 길을 준다 — 다만 **그 길에 경고를 남긴다**."""
    r = _run(tmp_path, test_rc=1, env={"MUTATE_SKIP_BASELINE": "의도한 빨간 기준선"})
    assert r.returncode == 1, (r.returncode, r.stdout)   # 게이트를 건너뛰고 판정까지 감
    assert "건너뜀" in r.stdout
    assert "의도한 빨간 기준선" in r.stdout
    # ★경고가 없으면 다음 사람이 그 CAUGHT 를 근거로 쓴다
    assert "근거로 인용하지 말 것" in r.stdout


def test_escape_hatch_requires_a_reason(tmp_path):
    """★빈 값으로는 못 빠져나간다 — 사유 없는 탈출구는 곧 기본값이 된다."""
    r = _run(tmp_path, test_rc=1, env={"MUTATE_SKIP_BASELINE": ""})
    assert r.returncode == 13, (r.returncode, r.stdout, r.stderr)
