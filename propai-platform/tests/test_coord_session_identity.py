"""보드가 **누가 썼는지를 기계로 기록**하는지 잠근다.

## 왜 (2026-09-04 실해)

보드의 `[8f]`·`[3a]`·`[c0]` 표기와 본문 서명은 **전부 자기신고**다.
`scripts/coord.sh` 가 기계기록하던 축은 **날짜와 브랜치 둘뿐**이고,
오늘 노트 다수가 `main` 에서 쓰였으므로 브랜치 축은 **판별력이 거의 0** 이었다.

실해:
  · 한 세션의 이름으로 서명된 노트를 **그 세션이 쓰지 않았고**,
    통합자가 그 조건을 근거로 **남의 PR 을 태우기 직전**이었다.
  · 그 앞에 같은 축의 오귀속이 **2회 더** 있었다(`#963`·`#968`).

> **「절대형 서명」은 소유자 확정에 그날 유일하게 작동한 장치였는데,
> 그 서명 자체가 오기입되면 그 장치도 무력하다.**

★그래서 **스탬프가 찍는 필드**를 둔다 — 본문에 무엇을 쓰든 바뀌지 않는다.
자기신고와 기계기록을 **같은 줄에서 대조**할 수 있게 하는 것이 목적이다.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COORD = REPO / "scripts" / "coord.sh"


def _run(args: list[str], *, sid: str | None, workdir: Path) -> str:
    """격리된 보드에 쓰고 그 줄을 돌려준다 — 공유 보드를 건드리지 않는다."""
    env = dict(os.environ)
    env["COORD_DIR"] = str(workdir / "coordination")
    if sid is None:
        env.pop("CLAUDE_CODE_SESSION_ID", None)
    else:
        env["CLAUDE_CODE_SESSION_ID"] = sid
    subprocess.run(
        ["bash", str(COORD), *args], cwd=REPO, env=env,
        capture_output=True, text=True, check=True,
    )
    board = workdir / "coordination" / "BOARD.md"
    return board.read_text(encoding="utf-8")


@pytest.fixture()
def workdir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class Test수집기가살아있다:
    def test_스크립트가_실재하고_문법이_맞다(self):
        assert COORD.exists(), f"경로가 바뀌었나: {COORD}"
        r = subprocess.run(["bash", "-n", str(COORD)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


class Test세션정체를기계로기록한다:
    """★셋 다 찍어야 한다 — 하나만 찍으면 나머지가 무잠금이다."""

    @pytest.mark.parametrize(
        ("args", "kind"),
        [
            (["note", "테스트 노트"], "NOTE"),
            (["claim", "테스트 영역"], "CLAIM"),
            (["release", "테스트 영역"], "RELEASE"),
        ],
    )
    def test_note_claim_release_모두_sid_를_찍는다(self, args, kind, workdir):
        out = _run(args, sid="79cfa3eb-f98e-41dc-a5e1-4e64d6f4b47b", workdir=workdir)
        line = next(ln for ln in out.splitlines() if f"[{kind}]" in ln)
        assert "sid=79cfa3eb" in line, f"{kind} 에 기계기록이 없다: {line}"


class Test본문으로위조할수없다:
    """★★이 축이 이 변경의 존재 이유다.

    본문 서명은 **자기신고**라 누구든 남의 이름을 쓸 수 있다(그게 오늘의 사고였다).
    스탬프 필드는 **본문과 무관하게** 실제 값이어야 한다.
    """

    def test_본문에_다른_sid_를_넣어도_기계기록은_실제값이다(self, workdir):
        out = _run(
            ["note", "sid=deadbeef 나는 development-ai-8f 입니다"],
            sid="79cfa3eb-f98e-41dc-a5e1-4e64d6f4b47b", workdir=workdir,
        )
        line = next(ln for ln in out.splitlines() if "[NOTE]" in ln)
        # 스탬프가 찍은 필드는 **본문보다 앞**에 있고 실제 값이다.
        stamped = re.search(r"sid=([0-9a-f?]{1,8})", line)
        assert stamped and stamped.group(1) == "79cfa3eb", f"위조가 통했다: {line}"
        # 본문의 가짜 값은 **그대로 남는다**(지우지 않는다 — 증거다). 그러나 판정에는 안 쓰인다.
        assert "deadbeef" in line


class Test모르면지어내지않는다:
    """★두 모집단 — 값이 있으면 그 값, 없으면 `?`. 「없음」을 그럴듯한 값으로 채우지 않는다."""

    def test_환경변수가_없으면_물음표다(self, workdir):
        out = _run(["note", "환경변수 없음"], sid=None, workdir=workdir)
        line = next(ln for ln in out.splitlines() if "[NOTE]" in ln)
        assert "sid=?" in line, f"없는 값을 지어냈다: {line}"

    def test_음성_대조군_값이_있으면_물음표가_아니다(self, workdir):
        out = _run(["note", "환경변수 있음"], sid="abcdef01-2345", workdir=workdir)
        line = next(ln for ln in out.splitlines() if "[NOTE]" in ln)
        assert "sid=abcdef01" in line and "sid=?" not in line


class Test하위호환:
    def test_기존_형식의_앞부분이_그대로다(self, workdir):
        """★옛 줄(`sid=` 없음)을 읽는 파서가 깨지지 않아야 한다 — 필드는 **뒤에** 붙는다."""
        out = _run(["note", "형식 확인"], sid="11112222-3333", workdir=workdir)
        line = next(ln for ln in out.splitlines() if "[NOTE]" in ln)
        # `- [NOTE] YYYY-MM-DD HH:MM <브랜치> …`
        assert re.match(r"^- \[NOTE\] \d{4}-\d{2}-\d{2} \d{2}:\d{2} \S+", line), line

    def test_summary_가_CLAIM_RELEASE_를_여전히_고른다(self, workdir):
        _run(["claim", "가"], sid="aaaa1111", workdir=workdir)
        out = _run(["release", "가"], sid="aaaa1111", workdir=workdir)
        assert "[CLAIM]" in out and "[RELEASE]" in out


class Test브랜치칸이비지않는다:
    """★★`||` 는 **종료코드에만** 반응한다 — 빈 출력에는 발동하지 않는다.

    `git branch --show-current` 는 **detached HEAD 에서 exit 0 + 빈 출력**이다.
    종전 폴백(`|| echo '?'`)이 발동하지 않아 **브랜치 칸이 통째로 비었고**, 그러면
    보드 줄의 **필드가 하나 밀린다**(파서가 다음 칸을 브랜치로 읽는다).

    ★실해 범위: 이 저장소의 워크트리 **32개가 detached** 다(서브에이전트 워크트리 포함) —
    거기서 쓴 노트는 전부 그 상태였다. **이 락이 CI(detached 체크아웃)에서 먼저 잡았다.**
    """

    def test_detached_HEAD_에서도_브랜치_칸이_채워진다(self, workdir, tmp_path):
        detached = tmp_path / "wt"
        subprocess.run(
            ["git", "worktree", "add", "-f", "--detach", str(detached), "HEAD"],
            cwd=REPO, capture_output=True, text=True, check=True,
        )
        try:
            env = dict(os.environ)
            env["COORD_DIR"] = str(workdir / "coordination")
            env["CLAUDE_CODE_SESSION_ID"] = "cafebabe-0000"
            subprocess.run(
                ["bash", str(COORD), "note", "detached 확인"],
                cwd=detached, env=env, capture_output=True, text=True, check=True,
            )
            line = next(
                ln for ln in (workdir / "coordination" / "BOARD.md")
                .read_text(encoding="utf-8").splitlines() if "[NOTE]" in ln
            )
            # ★칸이 비면 이 정규식이 `sid=` 를 브랜치로 읽는다 — 그것을 명시적으로 배제한다.
            m = re.match(r"^- \[NOTE\] \d{4}-\d{2}-\d{2} \d{2}:\d{2} (\S+) sid=", line)
            assert m, f"브랜치 칸이 비었다(필드가 밀렸다): {line!r}"
            assert m.group(1) == "?", f"detached 는 '?' 여야 한다: {m.group(1)!r}"
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(detached)],
                cwd=REPO, capture_output=True, text=True,
            )
