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


def test_파이프가_있으면_경고한다(sandbox) -> None:
    """★이 저장소가 반복해서 데인 함정 — `cmd | tail` 은 **끝 명령의 종료코드**를 준다.

    그러면 테스트가 실패해도 rc=0 이라 이 하네스가 **CAUGHT 를 SURVIVED 로 보고**한다.
    실제로 이 도구의 **첫 실사용에서 그 일이 났다**(2026-08-21) — 도구는 정확했고 호출이 틀렸다.
    도구가 호출자의 셸 문자열을 다 알 수는 없으니 **보이면 시끄럽게 경고**한다.
    """
    root, _ = sandbox
    r = _run(root, "target.txt", "s|alpha|ALPHA|", "bash", "-c", "false | tail -1")
    합본 = r.stdout + r.stderr
    assert "파이프" in 합본, f"파이프 경고가 없다: {합본}"
    # ★음성 대조군 — 파이프가 없으면 경고하지 않아야 한다(위양성 방지).
    r2 = _run(root, "target.txt", "s|alpha|ALPHA|", "true")
    assert "파이프" not in (r2.stdout + r2.stderr), "파이프가 없는데 경고한다(위양성)"


# ══════════════════════════════════════════════════════════════════════
# ⑤파이프 판정 오염 — **경고가 아니라 하드 스톱** (2026-08-27 추가)
# ══════════════════════════════════════════════════════════════════════
#
# 종전엔 테스트 명령에 파이프가 있으면 **경고만 stderr 로 찍고** 그대로 진행해,
# 오염된 종료코드로 판정을 **발행**했다. 곧 도구가 *"이 값은 못 믿는다"* 를 알면서
# **그 값으로 판정을 냈다.** 다음 사람은 경고가 아니라 **마지막 줄**을 읽는다.
#
# ★이 파일의 대상 스크립트 주석이 그 사고를 **이미 적어 두었다**(첫 실사용 2026-08-21:
#   테스트는 `1 failed` 인데 `| tail -1` 때문에 통과로 찍혔다). 처방이 **산문**이었다.
#   **경고는 산문이고 판정이 산출물이다.**
#
# ★이 락이 **못 보는** 것: `MUTATE_ALLOW_PIPE` 우회는 **틀린 판정을 낼 수 있다**
#   (진짜 파이프인데 무해하다고 주장하면 그대로 통과한다). 그것이 탈출구의 값이고,
#   그래서 **사유를 출력에 남긴다** — 자동으로 막지 않고 **사람이 되짚을 수 있게** 한다.

_EXIT_PIPE_UNJUDGEABLE = 12


def test_파이프가_있으면_판정을_내지_않는다_exit12(sandbox) -> None:
    """★핵심 — 오염된 종료코드로 판정을 **발행하지 않는다**."""
    root, target = sandbox
    r = _run(root, "target.txt", "s|alpha|ALPHA|", "sh", "-c", "false | true")
    assert r.returncode == _EXIT_PIPE_UNJUDGEABLE, (r.returncode, r.stdout, r.stderr)
    assert "판정 불가" in r.stderr, r.stderr


def test_하드스톱은_대상_파일을_건드리지_않는다(sandbox) -> None:
    """판정을 안 낼 거면 **변이도 넣지 않는다**(파일을 건드리고 죽으면 더 나쁘다)."""
    root, target = sandbox
    before = target.read_bytes()
    _run(root, "target.txt", "s|alpha|ALPHA|", "sh", "-c", "false | true")
    assert target.read_bytes() == before
    assert _git("diff", "--quiet", cwd=root).returncode == 0


def test_안내문에_판정어_리터럴이_없다(sandbox) -> None:
    """★자기 텍스트 함정 — 안내문에 판정어가 있으면 출력에서 판정을 찾는 사람이 오독한다.

    실측(2026-08-27): 첫 구현의 안내문이 *"…가 …로 오보된다"* 를 **영문 판정어로** 써서,
    내 자신의 검사기가 그 문장을 판정으로 집었다.
    """
    root, target = sandbox
    r = _run(root, "target.txt", "s|alpha|ALPHA|", "sh", "-c", "false | true")
    blob = r.stdout + r.stderr
    for token in ("SURVIVED", "CAUGHT"):
        assert token not in blob, f"안내문에 판정어 {token} 가 남아 있다:\n{blob}"


def test_pipefail_이_있으면_판정을_낸다(sandbox) -> None:
    """★길 ① — 도구가 스스로 권한 처방을 쓰면 통과해야 한다(위양성 방지)."""
    root, target = sandbox
    r = _run(root, "target.txt", "s|alpha|ALPHA|",
             "sh", "-c", "set -o pipefail; false | true")
    assert r.returncode != _EXIT_PIPE_UNJUDGEABLE, (r.returncode, r.stdout, r.stderr)
    assert "CAUGHT" in r.stdout, r.stdout


def test_명시적_우회는_사유를_출력에_남긴다(sandbox) -> None:
    """★길 ② — 차단하되 길을 준다. 다만 **사유가 남는다**(`REVIEW_EXEMPT` 어법)."""
    root, target = sandbox
    env = {**os.environ, "MUTATE_ALLOW_PIPE": "리터럴 파이프 — 무해"}
    r = subprocess.run(
        ["bash", "scripts/mutate_manual.sh", "target.txt", "s|alpha|ALPHA|", "sh", "-c", "true | true"],
        cwd=root, capture_output=True, text=True, env=env,
    )
    assert r.returncode != _EXIT_PIPE_UNJUDGEABLE, (r.returncode, r.stdout, r.stderr)
    assert "리터럴 파이프 — 무해" in r.stdout, r.stdout


def test_파이프가_없으면_종전대로_판정한다(sandbox) -> None:
    """★특이도 — 정상 호출을 막으면 그것도 결함이다(두 모집단이 갈려야 한다)."""
    root, target = sandbox
    survived = _run(root, "target.txt", "s|alpha|ALPHA|", "true")
    caught = _run(root, "target.txt", "s|alpha|ALPHA|", "false")
    assert survived.returncode == 0 and "SURVIVED" in survived.stdout
    assert caught.returncode not in (0, _EXIT_PIPE_UNJUDGEABLE)
    assert "CAUGHT" in caught.stdout
