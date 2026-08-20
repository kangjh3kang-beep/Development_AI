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
