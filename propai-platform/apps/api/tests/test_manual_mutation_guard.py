"""손 변이 하네스(`scripts/mutate_manual.sh`)가 **실제로 막는지** 실행으로 잠근다.

★왜 (2026-08-21):
    `scripts/mutate_changed.py` 는 기계적 변이를 뽑고 스냅샷 복원이라 안전하다.
    그런데 **의미를 아는 사람만 만들 수 있는 변이**(배선·계약·역할 바꿔치기)는 손으로 넣게 되고,
    그 손 경로에는 **안전장치가 하나도 없었다.** 실제로 사고가 났다:

      · 미커밋 상태에서 `git checkout -- <파일>` 로 되돌리다 **테스트 편집을 통째로 날렸다**
        (13 passed → 10 passed). CLAUDE.md §B7 을 **알면서** 밟았다.
      · `grep -c` 로 주입을 확인하다 동명의 다른 줄을 세어 주입 실패를 못 봤다(§B8).

    **규율이 문서에만 있으면 지켜지지 않는다.** 안전한 길을 더 쉽게 만들고, 그 길이 실제로
    안전한지는 **실행으로** 확인한다 — 문구를 grep 하는 것으로는 아무것도 보증하지 못한다.

★그리고 이 파일은 **CLAUDE.md 가 선언한 종료코드**(10·11)를 잠근다.
  문서와 구현이 갈리면 다음 사람이 문서를 근거로 잘못 판단한다.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[4]
_SCRIPT = _REPO / "scripts" / "mutate_manual.sh"


def _git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@pytest.fixture()
def sandbox():
    """★실저장소를 건드리지 않는다 — 일회용 git 저장소를 만들어 그 안에서만 돌린다."""
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        _git("init", "-q", cwd=root)
        _git("config", "user.email", "t@t", cwd=root)
        _git("config", "user.name", "t", cwd=root)
        (root / "scripts").mkdir()
        shutil.copy(_SCRIPT, root / "scripts" / "mutate_manual.sh")
        os.chmod(root / "scripts" / "mutate_manual.sh", 0o755)
        target = root / "target.txt"
        target.write_text("alpha\nbeta\n", encoding="utf-8")
        _git("add", "-A", cwd=root)
        _git("commit", "-qm", "init", cwd=root)
        yield root, target


def _run(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "scripts/mutate_manual.sh", *args], cwd=root, capture_output=True, text=True
    )


def test_전제_스크립트가_실재하고_실행가능하다() -> None:
    """★공허한 초록 방지 — 파일이 없으면 아래가 전부 무의미하다."""
    assert _SCRIPT.exists(), f"{_SCRIPT} 가 없다"
    assert os.access(_SCRIPT, os.X_OK), f"{_SCRIPT} 에 실행 권한이 없다"


def test_미커밋_변경이_있으면_거부한다_exit10(sandbox) -> None:
    """§B7 — 커밋 먼저. **CLAUDE.md 가 선언한 exit 10** 을 잠근다."""
    root, target = sandbox
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")   # 미커밋 편집
    r = _run(root, "target.txt", "s|alpha|ALPHA|", "true")
    assert r.returncode == 10, f"미커밋인데 거부하지 않았다(rc={r.returncode}): {r.stdout}{r.stderr}"
    assert "미커밋" in (r.stderr + r.stdout)
    # ★가장 중요 — 내 미커밋 편집이 **살아 있어야** 한다(이게 사고의 본체였다).
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\ngamma\n", "미커밋 편집이 날아갔다"


def test_주입이_안_되면_거부한다_exit11(sandbox) -> None:
    """§B8 — 주입 실패를 '통과'로 읽지 않는다. **exit 11** 을 잠근다."""
    root, _ = sandbox
    r = _run(root, "target.txt", "s|없는문자열ZZZ|X|", "true")
    assert r.returncode == 11, f"주입 실패인데 거부하지 않았다(rc={r.returncode}): {r.stdout}{r.stderr}"
    assert "주입되지 않았다" in (r.stderr + r.stdout)


def test_SURVIVED_와_CAUGHT_를_종료코드로_가른다(sandbox) -> None:
    root, _ = sandbox
    survived = _run(root, "target.txt", "s|alpha|ALPHA|", "true")
    assert survived.returncode == 0 and "SURVIVED" in survived.stdout, survived.stdout
    caught = _run(root, "target.txt", "s|alpha|ALPHA|", "false")
    assert caught.returncode != 0 and "CAUGHT" in caught.stdout, caught.stdout


def test_원복은_git_이_아니라_스냅샷에서_한다(sandbox) -> None:
    """★핵심 — **같은 파일의 다른 미커밋 편집을 건드리면 안 된다**.

    §B7 사고의 본체가 이것이다: `git checkout --` 는 파일 전체를 되돌려 내 편집까지 지운다.
    여기서는 커밋된 상태에서 변이를 돌리고, **파일이 원래 내용 그대로** 돌아오는지 본다.
    """
    root, target = sandbox
    before = target.read_text(encoding="utf-8")
    r = _run(root, "target.txt", "s|beta|BETA|", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    assert target.read_text(encoding="utf-8") == before, "원복이 원본과 다르다"
    assert _git("status", "--porcelain", cwd=root).stdout.strip() == "", "작업트리가 더럽다"


def test_테스트가_중간에_죽어도_원복한다(sandbox) -> None:
    """★`trap` — 끊겨도 오염된 소스를 남기지 않는다."""
    root, target = sandbox
    before = target.read_text(encoding="utf-8")
    r = _run(root, "target.txt", "s|alpha|ALPHA|", "bash", "-c", "kill -INT $$")
    assert target.read_text(encoding="utf-8") == before, f"중단 후 원복 실패: {r.stdout}{r.stderr}"


def test_CLAUDE_md_가_선언한_종료코드와_구현이_일치한다() -> None:
    """★문서와 구현이 갈리면 다음 사람이 **문서를 근거로** 잘못 판단한다.

    위 테스트들이 실행으로 확인한 값(10·11)이 CLAUDE.md 에도 그대로 적혀 있어야 한다.
    """
    doc = (_REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "mutate_manual.sh" in doc, "CLAUDE.md 가 이 도구를 안내하지 않는다 — 아무도 안 쓴다"
    assert "exit 10" in doc and "exit 11" in doc, (
        "CLAUDE.md 가 종료코드를 선언하지 않는다 — 실패를 어떻게 읽을지 알 수 없다"
    )


def test_셸_래퍼면_판정을_발행하지_않는다(sandbox) -> None:
    """★rc 를 못 믿는 층은 **셸 래퍼**다 — 파이프는 그 한 형태일 뿐이다.

    ## 종전 탐지가 **거꾸로**였다 (2026-09-02 실증)

    이 도구는 `"$@"` 로 **execvp 직접 실행**한다 — **셸을 거치지 않는다.**
    그런데 탐지는 **인자열 전체에서 문자 `|` 하나만** 봤다. 그래서 층이 섞였다:

        bash -c "pytest | tail"     → 잡힘        (맞다)
        bash -c "pytest; tail"      → **못 잡음**  ← 거짓 SURVIVED(격리 저장소 실증)
        bash -c "pytest && tail"    → **못 잡음**
        grep -qE 'a|b' file (직접)  → 잡힘        ← **리터럴인데 차단**(위양성)

    ★**같은 문자 하나로 성질이 다른 두 층을 판정**하고 있었다.

    ★★형태를 넓히는 것(`*[";|&"]*`)으로는 안 된다 —
      `set -o pipefail; pytest | tail` 은 **안전**하고 `pytest; tail` 은 **위험**한데
      **같은 `;`** 다. 못 가르는 것을 가르는 척하면 위양성과 위음성을 **동시에** 낸다.
      → 셸 스크립트 문자열은 **불투명**하다고 인정하고 그 층이면 판정을 발행하지 않는다.
    """
    root, _ = sandbox
    # ① 파이프 형태 — 종전에도 잡혔다(회귀 방지)
    r = _run(root, "target.txt", "s|alpha|ALPHA|", "bash", "-c", "false | tail -1")
    assert r.returncode == 12, f"파이프 래퍼가 판정 불가(12)가 아니다: rc={r.returncode}"
    # ② ★세미콜론 — **종전엔 못 잡았다**(거짓 SURVIVED 의 자리)
    r2 = _run(root, "target.txt", "s|alpha|ALPHA|", "bash", "-c", "false; true")
    assert r2.returncode == 12, f"';' 래퍼가 판정 불가가 아니다: rc={r2.returncode}"
    # ★판정어는 **줄 시작 앵커**로 본다. 부분문자열로 보면 판정 불가 **설명문 안의**
    #   "CAUGHT 가 SURVIVED 로 보고된다" 를 집어 **정상 동작을 위반으로 신고**한다
    #   (실제로 이 단언이 그렇게 한 번 빨개졌다 — 내가 쓴 문구가 내 검사를 무력화한 형태).
    assert not any(ln.startswith("SURVIVED") for ln in r2.stdout.splitlines()), (
        f"못 믿는 rc 로 판정을 발행했다: {r2.stdout}")
    # ③ ★`&&` — 같은 층
    r3 = _run(root, "target.txt", "s|alpha|ALPHA|", "bash", "-c", "false && true")
    assert r3.returncode == 12, f"'&&' 래퍼가 판정 불가가 아니다: rc={r3.returncode}"


def test_직접_argv_의_리터럴_파이프는_위험이_아니다(sandbox) -> None:
    """★**두 번째 모집단** — 이것이 없으면 「전부 차단」이 만점이 된다.

    `"$@"` 는 셸을 안 거치므로 인자 안의 `|`(예: `grep -E 'a|b'`)는 **파이프가 아니다**.
    종전엔 그것도 차단해 **정상 사용을 막았다**(위양성도 결함이다 · 규율 §A-6).
    """
    root, _ = sandbox
    # 변이가 들어가면 grep 이 실패한다 → 정상적으로 CAUGHT 판정이 나와야 한다.
    r = _run(root, "target.txt", "s|alpha|ALPHA|", "grep", "-qE", "alpha|zzz_nope", "target.txt")
    합본 = r.stdout + r.stderr
    assert r.returncode != 12, f"리터럴 '|' 를 판정 불가로 막았다(위양성): {합본}"
    assert any(ln.startswith("CAUGHT") for ln in r.stdout.splitlines()), (
        f"정상 판정이 안 나왔다: {합본}")
    # ★거짓 CAUGHT 가드 — 명령이 깨져서 rc≠0 이 된 것이 아님을 확인한다.
    assert not any(w in 합본 for w in ("usage:", "unrecognized", "Wrong expression")), (
        f"명령이 깨져서 CAUGHT 가 됐다(변이가 잡힌 게 아니다): {합본}")


def test_단일_단순_명령_래퍼는_신뢰한다(sandbox) -> None:
    """★**세 번째 모집단** — 래퍼라고 다 위험한 것이 아니다.

    `bash -c 'grep -q X f'` 처럼 **단일 단순 명령**이면 rc 는 그 명령의 것이다.
    ★이 저장소의 **기존 락**(`propai-platform/tests/test_mutate_manual_pipe_verdict.py`)이
      모든 호출을 `bash -c` 로 감싸므로, 래퍼를 통째로 막으면 **그 락 4건이 깨진다**
      (내 첫 설계가 실제로 그랬다 — **테스트 루트가 둘**이라 한쪽만 보고 초록으로 읽었다).
    """
    root, _ = sandbox
    r = _run(root, "target.txt", "s|alpha|ALPHA|", "bash", "-c", "grep -q alpha target.txt")
    assert r.returncode != 12, f"단일 명령 래퍼를 막았다(위양성): {r.stdout}{r.stderr}"
    assert any(ln.startswith(("CAUGHT", "SURVIVED")) for ln in r.stdout.splitlines()), (
        f"정상 판정이 안 나왔다: {r.stdout}")


def test_pipefail_접두는_걷어내고_판정한다(sandbox) -> None:
    """★같은 `;` 를 **위치로** 가른다 — 문자 하나로는 못 하던 것.

        set -o pipefail; cmd | tail   → 나머지에 ';' 없음 · '|' 는 pipefail 이 고침 → 신뢰
        set -o pipefail; cmd; tail    → 나머지에 ';' 있음                          → 판정 불가
    """
    root, _ = sandbox
    ok = _run(root, "target.txt", "s|alpha|ALPHA|",
              "bash", "-c", "set -o pipefail; grep -q alpha target.txt | cat")
    assert ok.returncode != 12, f"pipefail 로 막았는데 판정 불가다: {ok.stdout}"
    bad = _run(root, "target.txt", "s|alpha|ALPHA|",
               "bash", "-c", "set -o pipefail; grep -q alpha target.txt; true")
    assert bad.returncode == 12, (
        f"pipefail 접두가 ';' 위험까지 면제했다(종전 결함): rc={bad.returncode}")


def test_셸_래퍼_예외는_사유를_남기고_통과시킨다(sandbox) -> None:
    """★차단하되 **길을 준다** — 이 저장소 관행(`REVIEW_EXEMPT` 동형).

    사유 없는 탈출구는 곧 기본값이 되므로, **사유를 출력에 남긴다.**
    """
    import os

    root, _ = sandbox
    env = {**os.environ, "MUTATE_ALLOW_SHELL": "rc 보존 확인함"}
    r = subprocess.run(  # noqa: S603
        # ★`bash -c "false"` 는 **단일 단순 명령**이라 이제 정당하게 신뢰된다 —
        #   예외가 필요한 형태(명령을 잇는 것)로 써야 이 락이 공허하지 않다.
        ["bash", "scripts/mutate_manual.sh", "target.txt", "s|alpha|ALPHA|",
         "bash", "-c", "false; true"],
        cwd=root, capture_output=True, text=True, env=env,
    )
    assert r.returncode != 12, f"예외를 선언했는데 여전히 판정 불가다: {r.stdout}{r.stderr}"
    assert "rc 보존 확인함" in r.stdout, "예외 사유가 출력에 안 남는다(사유 없는 탈출구 금지)"
    # ★이 락의 축은 «예외가 통하고 **사유가 남는가**» 다 — 어느 판정이 나오는지가 아니다.
    #   `false; true` 의 rc 는 0 이라 **SURVIVED 가 정상**이다(예외는 «내가 책임진다» 는 뜻이고,
    #   그래서 못 믿는 rc 가 그대로 통과한다 — 그것이 탈출구의 대가다).
    assert any(ln.startswith(("CAUGHT", "SURVIVED")) for ln in r.stdout.splitlines()), (
        f"예외 후 판정이 아예 안 나왔다: {r.stdout}")


# ── 적대 리뷰 2회가 연 구멍 — **위험을 열거하는 방식이 매번 샜다** ──────────────────
#
# 1차 판정: 문자 `|` 하나          → `;`·`&&` 를 못 봤다
# 2차 판정: `; & && || 개행` 목록  → 롱옵션·명령치환·`!`·주석 안 pipefail 을 못 봤다
#   그 둘을 각각 **적대 리뷰가 8형태씩** 찾아냈다. **목록은 곧 상한이 된다.**
# 3차(현재): **뒤집었다** — 위험을 세지 않고 **「단일 단순 명령의 모양」만 신뢰**한다.
#   그래서 이 아래 표는 «막아야 할 것의 목록»이 아니라 **«설계가 이미 막는 것들의 증거»** 다.
#   새 형태가 나와도 화이트리스트가 자동으로 막는다 — 표에 없어도.

_판정불가_형태 = [
    # ★전부 그라운드 트루스상 rc=0 이 불가능하다(변이 후 `grep -q alpha` 는 반드시 실패).
    #   따라서 정답은 판정 불가(12)뿐이고 **rc=0/SURVIVED 는 어떤 경우에도 거짓**이다.
    # ── 1차 리뷰가 찾은 것(옵션 결합·접두 래퍼·구분자)
    ("bash -lc 옵션결합", ["bash", "-lc", "grep -q alpha target.txt | cat"]),
    ("bash -c -- 이중대시", ["bash", "-c", "--", "grep -q alpha target.txt | cat"]),
    ("env 접두", ["env", "bash", "-c", "grep -q alpha target.txt | cat"]),
    ("nohup 접두", ["nohup", "bash", "-c", "grep -q alpha target.txt | cat"]),
    ("env FOO=1 접두", ["env", "FOO=1", "bash", "-c", "grep -q alpha target.txt | cat"]),
    ("개행 구분자", ["bash", "-c", "grep -q alpha target.txt\ntrue"]),
    ("단일 & 백그라운드", ["bash", "-c", "grep -q alpha target.txt & wait"]),
    # ── 2차 리뷰가 찾은 것(★내 봉합이 새로 연 것들)
    ("★C1 --norc 롱옵션", ["bash", "--norc", "-c", "grep -q alpha target.txt | cat"]),
    ("★C1 --rcfile 롱옵션", ["bash", "--rcfile", "/dev/null", "-c",
                             "grep -q alpha target.txt | cat"]),
    ("★C1 --restricted 롱옵션", ["bash", "--restricted", "-c",
                                 "grep -q alpha target.txt; true"]),
    ("★C2 명령치환 $()", ["bash", "-c", "echo $(grep -q alpha target.txt)"]),
    ("★C2 백틱", ["bash", "-c", "echo `grep -q alpha target.txt`"]),
    ("★H1 ! 부정", ["bash", "-c", "! grep -q alpha target.txt"]),
    ("★M1 주석 안 pipefail", ["bash", "-c",
                              "set -e # pipefail; grep -q alpha target.txt | cat"]),
    ("★M1 스트립될 절 안의 치환", ["bash", "-c",
                                   "set -e $(grep -q alpha target.txt); true"]),
    ("★M2 timeout 은 rc 를 바꾼다", ["timeout", "60", "bash", "-c",
                                     "grep -q alpha target.txt"]),
    ("★L1 빈 스크립트", ["bash", "-c", ""]),
    # ── ★종전 xfail#1 — **닫혔다.** 명령이 환경변수에 실려도 스크립트에 `$` 가 남는다.
    ("★환경변수에 실린 명령", ["env", "T=grep -q alpha target.txt; true",
                               "bash", "-c", 'eval "$T"']),
]


@pytest.mark.parametrize("라벨,argv", _판정불가_형태, ids=[x[0] for x in _판정불가_형태])
def test_단일_단순_명령이_아니면_판정하지_않는다(sandbox, 라벨, argv) -> None:
    """★fail-closed — **모양이 아니면 판정을 발행하지 않는다.**"""
    root, _ = sandbox
    r = _run(root, "target.txt", "s|alpha|ALPHA|", *argv)
    assert r.returncode == 12, (
        f"[{라벨}] 판정을 발행했다: rc={r.returncode}\n{r.stdout}{r.stderr}")
    # ★판정어는 **줄 시작 앵커**로 본다(설명문 안의 낱말을 집지 않도록).
    assert not any(ln.startswith("SURVIVED") for ln in r.stdout.splitlines()), (
        f"[{라벨}] ★거짓 SURVIVED 를 발행했다: {r.stdout}")


def test_스크립트_파일을_받으면_내용을_못_보므로_판정하지_않는다(sandbox) -> None:
    """`bash runner.sh` — `-c` 가 없다. **파일 내용은 이 도구가 볼 수 없다.**"""
    root, _ = sandbox
    (root / "runner.sh").write_text(
        "#!/bin/bash\ngrep -q alpha target.txt\ntrue\n", encoding="utf-8")
    os.chmod(root / "runner.sh", 0o755)
    _git("add", "-A", cwd=root)
    _git("commit", "-qm", "runner", cwd=root)
    r = _run(root, "target.txt", "s|alpha|ALPHA|", "bash", "runner.sh")
    assert r.returncode == 12, f"스크립트 파일을 신뢰했다: rc={r.returncode}\n{r.stdout}"


# ★셸 목록(`sh|bash|zsh|dash|ksh`)은 **손 목록**이라 상한이 된다. 그래서 **호스트에 실재하는
#   셸에서 파생**시켜 태운다 — zsh/ksh 가 설치되면 그날부터 자동으로 감시망에 들어온다.
#   ★단 `bash` 는 다른 락이 이미 태우므로 여기서는 **나머지**만 본다(중복 방지).
_설치된_비bash_셸 = [x for x in ("sh", "dash", "zsh", "ksh") if shutil.which(x)]


@pytest.mark.parametrize("셸", _설치된_비bash_셸 or ["없음"])
def test_pipefail_은_그_셸이_지원할_때만_인정한다(sandbox, 셸) -> None:
    """★`sh`/`dash` 에는 `set -o pipefail` 이 **없다** — 인정하면 「명령이 깨져서 CAUGHT」다.

    dash 는 특수 빌트인 오류로 **즉시 종료**한다(rc=2). 그것을 「파이프를 고쳤다」로 인정하면
    **테스트가 돌지도 않았는데 CAUGHT** 가 된다.
    """
    if 셸 == "없음":
        pytest.skip("★비-bash 셸이 호스트에 없다 — 이 축은 미측정(계획서 §8-3)")
    root, _ = sandbox
    r = _run(root, "target.txt", "s|alpha|ALPHA|",
             셸, "-c", "set -o pipefail; grep -q alpha target.txt | cat")
    지원 = 셸 in ("bash", "zsh", "ksh")
    if 지원:
        assert r.returncode != 12, f"[{셸}] pipefail 을 지원하는데 막았다: {r.stdout}"
    else:
        assert r.returncode == 12, (
            f"[{셸}] pipefail 을 인정해 거짓 CAUGHT 를 냈다: rc={r.returncode}\n{r.stdout}{r.stderr}")


_정당_형태 = [
    # ★**두 번째 모집단** — 이것이 없으면 「전부 차단」이 만점이 된다. 정답은 CAUGHT.
    ("단일 단순 명령", ["bash", "-c", "grep -q alpha target.txt"]),
    ("-c -- 단일 명령", ["bash", "-c", "--", "grep -q alpha target.txt"]),
    ("env 접두 + 단일 명령", ["env", "bash", "-c", "grep -q alpha target.txt"]),
    ("다중 set 접두", ["bash", "-c", "set -e; set -o pipefail; grep -q alpha target.txt | cat"]),
    ("개행 경계 접두", ["bash", "-c", "set -o pipefail\ngrep -q alpha target.txt | cat"]),
    ("결합 접두", ["bash", "-c", "set -euo pipefail; grep -q alpha target.txt | cat"]),
    # ★`-o pipefail` 은 **명령줄**로 켜는 형태다(스크립트 접두가 아니다).
    ("-o pipefail 명령줄", ["bash", "-o", "pipefail", "-c",
                            "grep -q alpha target.txt | cat"]),
    # ★C1 의 짝 — 롱옵션 자체는 rc 를 바꾸지 않는다. 막으면 **위양성**이다.
    #   C1 을 고친 것은 `--*` 를 `-*c*` **앞에서** 보는 **순서**이지 차단이 아니었다.
    ("--norc + 단일 명령", ["bash", "--norc", "-c", "grep -q alpha target.txt"]),
]


@pytest.mark.parametrize("라벨,argv", _정당_형태, ids=[x[0] for x in _정당_형태])
def test_정당한_형태는_그대로_판정한다(sandbox, 라벨, argv) -> None:
    """★위양성 축 — 화이트리스트가 **정상까지 막으면** 그것도 결함이다."""
    root, _ = sandbox
    r = _run(root, "target.txt", "s|alpha|ALPHA|", *argv)
    합본 = r.stdout + r.stderr
    assert r.returncode != 12, f"[{라벨}] 정당한 형태를 막았다(위양성): {합본}"
    assert any(ln.startswith("CAUGHT") for ln in r.stdout.splitlines()), (
        f"[{라벨}] 정상 판정이 안 나왔다: {합본}")
    # ★거짓 CAUGHT 가드 — 셸이 깨져서 rc≠0 이 된 것이 아님을 확인한다.
    assert not any(w in 합본 for w in ("Illegal option", "unrecognized", "command not found")), (
        f"[{라벨}] 명령이 깨져서 CAUGHT 가 됐다: {합본}")


# ── ★잔존 구멍 — **부채를 초록 안에 보이게** 둔다 ──────────────────────────────────
#
# `xfail(strict=True)` 라서 **누가 이 구멍을 닫으면 XPASS 로 빨개진다**(래칫).
# ★종전에 여기 있던 «환경변수에 실린 명령»은 3차 설계가 **닫았다** — 위 파생형 표로 옮겼다.
#   그때 적었던 사유(*"닫으려면 설계를 바꿔야 한다"*)는 **틀렸다.** 설계를 바꾸니 닫혔다.


@pytest.mark.xfail(
    strict=True,
    reason="★미해소(실측 rc=0): argv[0] 이 **임의 실행파일**이면 그 안에서 무엇을 하는지 "
           "이 도구는 볼 수 없다. `./mywrap` 뿐 아니라 `sudo`·`xargs`·`make`·`npx`·"
           "`poetry run`·`uv run`·`python -m` 이 전부 이 구멍에 있고 훨씬 흔하다. "
           "닫으려면 '알려진 접두 래퍼' 목록을 넓혀야 하는데 **그것이 곧 손 목록**이라 "
           "상한이 된다 — 대신 MUTATE_ALLOW_SHELL 로 **사유를 선언**하게 한다.",
)
def test_부채_임의_실행파일_래퍼는_아직_못_본다(sandbox) -> None:
    root, _ = sandbox
    (root / "mywrap").write_text(
        "#!/bin/sh\ngrep -q alpha target.txt\ntrue\n", encoding="utf-8")
    os.chmod(root / "mywrap", 0o755)
    _git("add", "-A", cwd=root)
    _git("commit", "-qm", "wrap", cwd=root)
    r = _run(root, "target.txt", "s|alpha|ALPHA|", "./mywrap")
    assert r.returncode == 12, f"rc={r.returncode}"
