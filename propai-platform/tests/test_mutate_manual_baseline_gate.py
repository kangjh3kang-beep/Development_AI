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
import shlex
import subprocess
import textwrap
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[2] / "scripts" / "mutate_manual.sh"


def _run(tmp_path, *, test_rc: int, env=None, summary: str = "47 passed in 0.31s"):
    """대상 파일 하나 + 종료코드를 지정할 수 있는 테스트 명령으로 도구를 돌린다.

    ★`summary` 는 **가짜 러너의 요약 줄**이다. 종전 픽스처는 아무것도 출력하지
    않았는데, **실제 러너는 언제나 개수를 찍는다** — 그 차이가 개수 축을 통째로
    우회시켰다(내 개수 게이트를 넣자 기존 2건이 깨져서 드러났다).
    스텁이 검증 대상 층을 비껴가면 그 층은 영원히 무잠금이다.
    """
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
         "bash", "-c", f"printf '%s\\n' {shlex.quote(summary)}; exit {test_rc}"],
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
        # ★실제 러너처럼 **개수를 찍는다** — 개수 축 게이트가 이것을 읽는다.
        #   출력이 없으면 "통과 0건"으로 판정 불가가 되고, 그건 옳은 판정이다.
        if grep -q 'VALUE = 5000' target.py; then echo "1 passed"; exit 0; fi
        echo "1 failed"; exit 1
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


# ══════════════════════════════════════════════════════════════
# ★2축 — 「수집 0건」은 「빨간 기준선」과 **처방이 다르다**
# ══════════════════════════════════════════════════════════════
#
# 동료 세션(`development-ai-ca`) 실측: `-k` 오타 하나로 pytest 가 **rc=5**(수집 0건)를
# 주는데, 도구는 `rc≠0` 을 CAUGHT 로 찍는다. 즉 **테스트가 한 건도 안 돌았는데 CAUGHT**.
#
# ★기준선 게이트가 그것을 **잡기는 하지만**, 메시지가 *"기준선이 빨갛다"* 라서
#   **있지도 않은 실패를 찾으러 가게 만든다.** 처방이 다르다 —
#   전자는 **러너**(`-k`·경로)를 고치고, 후자는 **코드/환경**을 고친다.


def test_empty_selection_is_distinguished_from_red_baseline(tmp_path):
    """★rc=5(수집 0건)는 **다른 종료코드와 다른 문구**로 갈린다."""
    r = _run(tmp_path, test_rc=5)
    assert r.returncode == 14, (r.returncode, r.stdout, r.stderr)
    out = r.stdout + r.stderr
    assert "0건 수집" in out
    assert "러너가 아무것도 안 고른 것" in out
    # ★두 모집단 — 빨간 기준선과 **다른** 안내가 나와야 한다
    assert "기준선이 이미 빨갛다" not in out, "두 원인을 뭉쳐서 안내했다"
    assert "CAUGHT" not in r.stdout


def test_red_baseline_keeps_its_own_message(tmp_path):
    """★대조군 — 진짜 빨간 기준선(rc=1)은 **여전히 13** 이고 자기 문구를 낸다."""
    r = _run(tmp_path, test_rc=1)
    assert r.returncode == 13
    out = r.stdout + r.stderr
    assert "기준선이 이미 빨갛다" in out
    assert "0건 수집" not in out, "수집 0건 문구가 새어 들어갔다"


def test_guidance_text_survives_the_shell(tmp_path):
    """★★안내문이 **셸에서 잘리지 않는가** — 내 종전 판이 여기서 죽었다.

    안내문에 백틱을 쓰면 `echo "…"` 안에서 **명령 치환**이 일어나
    `command not found` 가 찍히고 **문구가 소실된다**. 실제로 났다(2026-08-27).
    ★이 저장소가 반복해 데인 함정이다(`coord.sh note` 의 백틱 치환 전례).
    """
    r = _run(tmp_path, test_rc=1)
    out = r.stdout + r.stderr
    assert "command not found" not in out, f"안내문이 셸에서 실행됐다:\n{out}"
    # ★소실되면 안 되는 실증 수치가 온전히 나온다
    assert "5000" in out and "5_000" in out, f"안내문 일부가 소실됐다:\n{out}"


# ══════════════════════════════════════════════════════════════
# ★3축 — 「rc 는 초록인데 아무것도 안 돌았다」
# ══════════════════════════════════════════════════════════════
#
# 실측 2026-08-28(내가 재확인 · 동료 development-ai-ca/-32 가 먼저 짚었다):
#
#   러너    오타 종류   기준선 rc   rc축     틀리는 방향
#   pytest  -k 이름         5       걸림     거짓 CAUGHT
#   pytest  파일 경로       4       걸림     거짓 CAUGHT
#   vitest  파일 경로       1       걸림     거짓 CAUGHT
#   vitest  -t 이름       ★0     ★통과     ★거짓 SURVIVED
#
# ★네 번째 칸은 **rc 로는 원리적으로 못 잡는다.** 개수를 봐야만 갈린다.

# 실제 vitest 요약(전부 skip · rc=0). Test Files 줄이 **먼저** 온다.
_VITEST_ALL_SKIPPED = " Test Files  1 skipped (1)\n      Tests  15 skipped (15)"
_VITEST_GREEN = " Test Files  1 passed (1)\n      Tests  15 passed (15)"


def test_green_rc_with_zero_passed_refuses_to_judge(tmp_path):
    """★★rc=0 인데 **통과 0건** → 판정을 발행하지 않는다(exit 15).

    vitest 는 `-t` 가 아무것도 안 골라도 rc=0 이다. rc 기반 게이트는 통과시키고,
    변이 후에도 rc 가 안 변하므로 **거짓 SURVIVED** 가 된다 — 가장 조용한 오판이다.
    """
    r = _run(tmp_path, test_rc=0, summary=_VITEST_ALL_SKIPPED)
    assert r.returncode == 15, (r.returncode, r.stdout, r.stderr)
    out = r.stdout + r.stderr
    assert "통과한 케이스가 0건" in out
    assert "거짓 SURVIVED" in out
    # ★판정을 내지 않았다 — 이것이 핵심이다
    assert "SURVIVED" not in r.stdout.replace("거짓 SURVIVED", "")
    assert "CAUGHT" not in r.stdout


def test_vitest_shaped_green_baseline_is_not_falsely_blocked(tmp_path):
    """★특이도 — **정상 vitest 초록**은 막히지 않는다(위양성도 결함이다).

    ★그리고 이 케이스가 **추출 함정**을 잠근다: vitest 는 `Test Files  1 passed (1)`
    가 `Tests  15 passed (15)` 보다 **먼저** 나온다. 첫 매치를 집으면 1 을 읽는다.
    여기서는 둘 다 0 이 아니라 통과하지만, **아래 테스트가 그 축을 직접 잠근다.**
    """
    r = _run(tmp_path, test_rc=0, summary=_VITEST_GREEN)
    assert r.returncode != 15, (r.returncode, r.stdout, r.stderr)
    assert "통과 15 건" in r.stdout, f"요약이 아니라 첫 줄(1)을 읽었다:\n{r.stdout}"


def test_count_is_read_from_the_largest_match_not_the_first_line(tmp_path):
    """★★추출이 **줄 위치를 가정하지 않는가** — 동료가 경고한 새 서식지.

    `grep -oE '[0-9]+ passed' | head -1` 은 요약이 아니라 **본문 줄**을 집는다.
    작은 수가 **먼저** 오는 출력으로 그 차이를 강제한다.
    """
    r = _run(tmp_path, test_rc=0,
             summary=" tests/a.spec.ts (2 tests | 2 passed)\n      Tests  99 passed (99)")
    assert "통과 99 건" in r.stdout, f"첫 매치(2)를 읽었다:\n{r.stdout}"


def test_zero_passed_gate_has_an_escape_hatch(tmp_path):
    """★차단하되 길을 준다 — 정말 전부 xfail 인 대상도 있다."""
    r = _run(tmp_path, test_rc=0, summary=_VITEST_ALL_SKIPPED,
             env={"MUTATE_SKIP_BASELINE": "대상이 전부 xfail 이다"})
    assert r.returncode != 15
    assert "근거로 인용하지 말 것" in r.stdout


def test_gate_judges_rather_than_crashing_on_zero_matches(tmp_path):
    """★★게이트가 **판정을 내는가, 죽는가** — 내 첫 구현이 여기서 죽었다.

    `grep` 은 0건일 때 exit 1 이고, 명령치환 대입의 종료코드는 파이프 마지막
    명령의 것이라 `set -e` 가 **판정 대신 스크립트를 죽였다**(rc=1).
    ★rc=1 은 「테스트 실패」와 **구별되지 않는다** — 그럴듯해서 더 나쁘다.
    """
    r = _run(tmp_path, test_rc=0, summary="아무 개수도 없는 출력")
    assert r.returncode == 15, f"판정(15)이 아니라 {r.returncode} 로 끝났다"
    assert r.returncode != 1, "테스트 실패와 구별되지 않는 종료코드"
