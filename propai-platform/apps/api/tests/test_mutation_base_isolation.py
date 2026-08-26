"""변이 도구가 **내 변경만** 대상으로 삼는지 실행으로 잠근다.

★왜 (2026-08-27 · SESSION-H 실측 → 이 세션 재현):
    `scripts/mutate_changed.py` 의 `_changed_files` 는 **두-점** diff 다. 워킹트리의
    미커밋 변경을 봐야 해서 그렇게 골랐는데(그 함수 주석), 두-점은 **양방향** 차이라
    `origin/main` 이 내 HEAD 보다 앞서면 **남이 머지한 파일까지** 변이 대상이 된다.

      · SESSION-H 실측: 26변이·생존 9 중 **5건이 남이 머지한 파일**
        (`propai-platform/scripts/monitor/growth_stale_producer_probe.py` · #868).
        공통 조상으로 낮추니 21변이·**생존 4**.
      · 이 세션 대조군(같은 저장소 · `HEAD~5`=ef8ff4ee 를 가상 HEAD 로):
        두-점 `origin/main` → **10파일**(전부 남의 머지분) ↔ 공통 조상 → **0파일**.

    이 도구의 출력은 **"생존 N건"이라는 증거로 인용된다.** 대상이 오염되면 그 증거가
    통째로 오염된다 — 이 도구가 없애려는 상태(진짜 신호가 소음에 묻히는 것)를 이 도구가
    스스로 만든다.

★이 파일이 잠그는 것은 **두 모집단이 갈리는가**이다.
    남의 파일은 **빠지고**, 내 파일은 **남아야** 한다. 한쪽만 단언하면 무의미하다 —
    "아무것도 대상으로 안 삼는" 구현도 남의 파일 부재는 만족한다.

★그리고 **과잉교정도 잠근다.** 두-점을 세-점으로 바꾸면 남의 커밋은 빠지지만
    **미커밋 워킹트리가 통째로 사라진다**(커밋 전에 돌리는 것이 이 도구의 정상 사용법).
    상한만 걸고 하한을 안 거는 실수를 여기서 막는다(CLAUDE.md §D19).
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[4]
_SCRIPT = _REPO / "scripts" / "mutate_changed.py"


_MODNAME = "_mutate_changed_under_test"


def _load_tool():
    """★도구를 **소스에서 직접** 불러 태운다 — 복제본이 아니라 실물이어야 잠긴다.

    `sys.modules` 등록은 선택이 아니다: 도구가 `@dataclass` 를 쓰는데, dataclass 는
    어노테이션 해석에 `sys.modules[cls.__module__]` 를 본다. 등록 없이 exec 하면
    `AttributeError: 'NoneType' object has no attribute '__dict__'` 로 죽는다(실측).
    """
    if _MODNAME in sys.modules:
        return sys.modules[_MODNAME]
    spec = importlib.util.spec_from_file_location(_MODNAME, _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_MODNAME] = mod
    spec.loader.exec_module(mod)
    return mod


def _git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, f"git {args} 실패: {r.stderr}"
    return r


@pytest.fixture()
def forked_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """**갈라진** 저장소를 만든다 — 남의 브랜치가 앞서고, 내 브랜치는 따로 나아갔다.

        A0 ─── A1 ─── A ──── (theirs)  shared_module.py 수정 · both_module.py 의 keep_me 삭제
        (ancient.py 를 A1 이 수정 — **분기점보다 앞선** 변경)
         │                                                   ← base ref 가 가리키는 곳
         └──── (mine)    my_module.py 추가 · both_module.py 의 value 수정
                         common.py 수정(미커밋)

    ★**남의 파일은 "수정"이어야 한다 — "추가"로 만들면 이 테스트가 공허해진다.**
      `_changed_files` 는 `p.exists()` 로 거르므로, 남의 브랜치에만 있는 **새 파일**은
      내 워킹트리에 없어서 어차피 빠진다. 그렇게 픽스처를 짜면 배선을 끊어도 초록이다.
      실제 오염 사례(`growth_stale_producer_probe.py` · #868)도 **이미 있던 파일을
      남이 수정한** 형태였다 — 그것이 이 결함이 사는 자리다. (첫 픽스처가 '추가'였고
      아래 전제 가드가 그것을 잡았다.)

    ★미커밋 변경도 **추적 파일의 수정**이어야 한다 — `git diff` 는 untracked 를 안 본다
      (그 한계는 아래 별도 테스트로 초록 안에 드러내 둔다).
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git("init", "-q", "-b", "theirs", cwd=root)
    _git("config", "user.email", "t@t", cwd=root)
    _git("config", "user.name", "t", cwd=root)

    # ★★`ancient.py` — **분기점보다 앞선** 남의 변경. 상한(과잉포함) 축을 가르는 유일한 축이다.
    #   이것이 없으면 base 를 merge-base 보다 **더 낮게** 해석하는 오구현(루트커밋·HEAD~N)이
    #   정답과 구별되지 않는다 — 락 전부가 초록인 채 실저장소 대상이 4파일 → 3,989파일이 된다
    #   (독립 리뷰 실측). 하한만 파생형으로 걸고 상한을 목록형 한 지점에 두면 이렇게 뚫린다.
    (root / "ancient.py").write_text("ancient_value = 0\n", encoding="utf-8")
    _git("add", "-A", cwd=root)
    _git("commit", "-qm", "A0 — 아주 오래된 커밋", cwd=root)
    (root / "ancient.py").write_text("ancient_value = 9\n", encoding="utf-8")
    _git("commit", "-qam", "A1 — 분기점보다 앞선 남의 변경", cwd=root)

    (root / "common.py").write_text("x = 1\n", encoding="utf-8")
    (root / "shared_module.py").write_text("shared_value = 0\n", encoding="utf-8")
    # ★`both_module.py` — 남도 나도 고친 파일. **오염이 '없는 줄'을 만들어 내는** 자리다.
    (root / "both_module.py").write_text("keep_me = 1\nvalue = 0\n", encoding="utf-8")
    _git("add", "-A", cwd=root)
    _git("commit", "-qm", "A", cwd=root)
    fork_point = _git("rev-parse", "HEAD", cwd=root).stdout.strip()

    # 남의 커밋 — base ref(`theirs`)만 앞서게 한다. **이미 있던 파일을 수정**한다.
    (root / "shared_module.py").write_text("shared_value = 111\n", encoding="utf-8")
    # ★그들이 `keep_me` 줄을 **지웠다**. 나는 그대로 두었다 — 그래서 오염된 base 로 재면
    #   내가 그 줄을 **새로 추가한 것처럼** 보인다(내가 건드린 적 없는 줄이다).
    (root / "both_module.py").write_text("value = 111\n", encoding="utf-8")
    _git("commit", "-qam", "그들의 머지", cwd=root)

    # 내 브랜치 — 공통 조상에서 갈라져 나온다
    _git("checkout", "-q", "-b", "mine", fork_point, cwd=root)
    (root / "my_module.py").write_text("my_value = 222\n", encoding="utf-8")
    (root / "both_module.py").write_text("keep_me = 1\nvalue = 222\n", encoding="utf-8")
    _git("add", "-A", cwd=root)
    _git("commit", "-qm", "내 커밋", cwd=root)

    # 미커밋 워킹트리 수정 — 두-점을 고른 **원래 이유**
    (root / "common.py").write_text("x = 1\ndraft = 333\n", encoding="utf-8")
    return root


def test_전제_도구가_실재한다() -> None:
    """★공허한 초록 방지 — 스크립트가 없으면 아래가 전부 무의미하다."""
    assert _SCRIPT.exists(), f"{_SCRIPT} 가 없다"
    assert hasattr(_load_tool(), "_resolve_base"), "_resolve_base 가 없다"


def test_전제_픽스처가_실제로_갈라져_있다(forked_repo, monkeypatch) -> None:
    """★두 모집단이 **실제로 다른지** 먼저 증명한다.

    갈라져 있지 않으면(남의 커밋이 조상이면) 아래 단언이 **원리적으로 위반 불가**가 되어
    배선을 끊어도 초록이다 — CLAUDE.md §회귀망 2(공허 진리 가드).
    """
    monkeypatch.chdir(forked_repo)
    tool = _load_tool()
    raw = {p.name for p in tool._changed_files("theirs")}
    resolved = {p.name for p in tool._changed_files(tool._resolve_base("theirs"))}
    assert raw != resolved, (
        "픽스처가 두 모집단을 가르지 못한다 — 갈린 이력이 아니라 이 테스트가 무의미하다. "
        f"두-점={sorted(raw)} 공통조상={sorted(resolved)}"
    )
    assert "shared_module.py" in raw, (
        "두-점이 남의 파일을 안 집는다 — 결함이 이미 없거나 픽스처가 틀렸다. "
        f"두-점={sorted(raw)}"
    )


def test_남의_커밋은_변이_대상에서_빠진다(forked_repo, monkeypatch) -> None:
    """모집단 A — **빠져야 하는 것.** 이것만 단언하면 무의미하다(아래 짝을 함께 볼 것)."""
    monkeypatch.chdir(forked_repo)
    tool = _load_tool()
    names = {p.name for p in tool._changed_files(tool._resolve_base("theirs"))}
    assert "shared_module.py" not in names, (
        f"남이 머지한 파일이 변이 대상에 들어왔다 — 생존 판정이 오염된다. 대상={sorted(names)}"
    )
    # ★★상한 — base 를 **너무 낮게** 해석해도 안 된다. 이 단언이 없으면 루트커밋으로
    #   내려가는 오구현이 위 단언까지 만족하며 통과한다(대상이 저장소 전체가 된다).
    assert "ancient.py" not in names, (
        "분기점보다 **앞선** 변경이 대상에 들어왔다 — base 를 merge-base 보다 더 낮게 "
        f"해석한다. 대상={sorted(names)}"
    )


def test_내_커밋과_미커밋_변경은_남는다(forked_repo, monkeypatch) -> None:
    """모집단 B — **남아야 하는 것.** 하한을 안 걸면 '아무것도 안 봄'이 만점을 받는다.

    ★`common.py`(미커밋 수정)가 이 단언의 핵심이다 — 세-점으로 '고치면' 이 줄이 빨개진다.
    """
    monkeypatch.chdir(forked_repo)
    tool = _load_tool()
    names = {p.name for p in tool._changed_files(tool._resolve_base("theirs"))}
    assert "my_module.py" in names, f"내 커밋이 대상에서 빠졌다. 대상={sorted(names)}"
    assert "common.py" in names, (
        "미커밋 워킹트리 수정이 빠졌다 — 두-점을 고른 원래 이유가 깨졌다(세-점 과잉교정). "
        f"대상={sorted(names)}"
    )


def test_이미_조상인_base_는_그대로_둔다(forked_repo, monkeypatch) -> None:
    """★기존 사용법을 안 깬다 — `--base HEAD~1` 은 이미 조상이라 낮출 것이 없다."""
    monkeypatch.chdir(forked_repo)
    tool = _load_tool()
    want = subprocess.run(
        ["git", "rev-parse", "HEAD~1"], cwd=forked_repo, capture_output=True, text=True,
    ).stdout.strip()
    assert tool._resolve_base("HEAD~1") == want


def test_배선_main_의_변이_건수가_해석된_base_와_일치한다(forked_repo) -> None:
    """★★두 번째 배선 락 — `_added_lines` **호출부**를 잠근다.

    첫 배선 락(위)은 `_changed_files` 호출부만 본다. `_added_lines` 를 `args.base` 로
    되돌리는 변이는 그것을 통과했다(실측 SURVIVED). 파일 목록이 옳아도 **변이할 줄**을
    오염된 base 로 뽑으면, 내가 건드린 적 없는 줄(`keep_me`)이 변이 대상이 된다.

    ★기대값을 **숫자로 박지 않는다** — 도구 자신의 함수로 계산해서 대조한다.
      계획서 문장에서 추론한 기대값은 그 자체가 위양성이 된다(CLAUDE.md §8).
    """
    monkeypatch = None  # noqa: F841  (이 테스트는 chdir 하지 않는다 — 하위 프로세스로 돈다)
    tool = _load_tool()
    probe = forked_repo / "probe_test.py"
    # ★probe 는 **통과해야 한다.** 실패시키면 도구가 기준선 검사에서 멈춰 변이 라벨을
    #   한 줄도 찍지 않는다 — 아래 `keep_me` 단언이 **공허한 참**이 된다(독립 리뷰가 적발).
    probe.write_text("def test_probe():\n    assert True\n", encoding="utf-8")

    out = _run_tool(
        forked_repo, "--base", "theirs", "--tests", "probe_test.py", "--cwd", ".",
    )
    m = re.search(r"변이 (\d+)건", out)
    assert m, f"변이 건수를 못 읽었다 — 출력 형태가 바뀌었나.\n{out}"
    got = int(m.group(1))

    # 도구 자신의 함수로 **정답을 파생**시킨다
    import os
    prev = os.getcwd()
    os.chdir(forked_repo)
    try:
        base = tool._resolve_base("theirs")
        want = 0
        for f in tool._changed_files(base):
            skip = tool._docstring_line_nos(f)
            for no, line in tool._added_lines(base, f):
                if no in skip:
                    continue
                want += len(tool._mutations_for_line(f, line, no))
    finally:
        os.chdir(prev)

    assert got == want, (
        f"main() 이 만든 변이 {got}건 ≠ 해석된 base 기준 {want}건 — `_added_lines` 호출부가 "
        f"오염된 base 를 쓴다.\n{out}"
    )
    assert "생존" in out or "kill" in out, (
        f"변이 루프가 돌지 않았다 — 아래 `keep_me` 단언이 공허해진다.\n{out}"
    )
    assert "keep_me" not in out, (
        "내가 건드린 적 없는 줄(`keep_me`)이 변이 대상에 들어왔다 — 오염된 base 가 "
        f"**없는 변경을 만들어 냈다**.\n{out}"
    )


def test_변이_줄도_같은_base_를_본다(forked_repo, monkeypatch) -> None:
    """★배선 락 — 파일 목록만 낮추고 변이 줄을 안 낮추면 **남의 코드 줄**이 변이된다.

    `_added_lines` 는 `+` 줄을 모은다. 남의 파일을 두-점으로 보면 **되돌리는 방향**의
    줄이 잡힌다 — 그것을 변이해 봐야 아무 의미가 없다.
    """
    monkeypatch.chdir(forked_repo)
    tool = _load_tool()
    base = tool._resolve_base("theirs")
    lines = tool._added_lines(base, pathlib.Path("my_module.py"))
    assert any("my_value" in ln for _, ln in lines), (
        f"내 파일의 추가 줄을 못 읽었다 — base 배선이 어긋났다. 읽은 줄={lines}"
    )
    both = tool._added_lines(base, pathlib.Path("both_module.py"))
    assert any("value = 222" in ln for _, ln in both), (
        f"내가 고친 줄을 못 읽었다. 읽은 줄={both}"
    )
    assert not any("keep_me" in ln for _, ln in both), (
        "내가 건드린 적 없는 줄이 '추가된 줄'로 잡혔다 — 오염된 base 는 **없는 변경을 "
        f"만들어 낸다**. 읽은 줄={both}"
    )


def test_해석된_base_sha_가_실행_출력에_찍힌다(forked_repo) -> None:
    """★증거에 base 가 안 적히는 것이 이번 오염이 **조용했던** 근본이다.

    "생존 N건"만 인용되고 *무엇을 대상으로 쟀는지* 는 인용되지 않았다. 그래서 남의 파일이
    섞인 실행과 안 섞인 실행이 **출력만 봐서는 구별되지 않았다.**

    ★이 테스트는 함수 반환값이 아니라 **실제 실행의 stdout** 을 본다 — 문자열을 만드는
      함수만 잠그면 `main` 이 그것을 **부르지 않게** 바뀌어도 초록이다(배선 무잠금).
      도구를 하위 프로세스로 진짜 돌린다.

    ★문구가 아니라 **sha 가 실려 있는가**를 단언한다. 산문을 잠그면 다듬을 때마다 깨지는
      취약한 락이 된다(CLAUDE.md §G-30).
    """
    expect = subprocess.run(
        ["git", "merge-base", "theirs", "HEAD"],
        cwd=forked_repo, capture_output=True, text=True,
    ).stdout.strip()
    assert expect, "전제 실패 — 공통 조상을 못 구했다"

    out = _run_tool(forked_repo, "--base", "theirs")
    assert expect[:12] in out, (
        "해석된 base sha 가 실행 출력에 없다 — 다음 사람이 '무엇을 대상으로 쟀는지' 를 "
        f"알 수 없다. 기대 sha={expect[:12]} 실제 출력=\n{out}"
    )
    assert "theirs" in out, (
        f"원래 준 base ref 가 출력에 없다 — 무엇이 무엇으로 낮춰졌는지 못 읽는다.\n{out}"
    )


def _run_tool(root: pathlib.Path, *args: str) -> str:
    """도구를 **하위 프로세스로 진짜 돌리고** stdout 을 준다.

    `--tests` 를 주지 않으면 도구는 대상 목록을 찍고 exit 2 로 멈춘다 — 그 목록이
    `main()` 이 **실제로** 고른 모집단이다. 우리가 보려는 것이 정확히 그것이다.
    """
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), *args], cwd=root, capture_output=True, text=True,
    )
    return r.stdout + r.stderr


def test_배선_main_이_고른_대상에서_남의_파일이_빠진다(forked_repo) -> None:
    """★★배선 락 — **이 파일에서 가장 중요한 단언이다.**

    처음 이 파일을 썼을 때 나는 `_changed_files(_resolve_base(...))` 를 **직접** 불러
    단언했다. 함수는 잠겼지만 `main()` 이 그 함수를 **무엇으로** 부르는지는 아무도 안 봤다.
    변이로 확인하니 `files = _changed_files(base)` 를 **원래 결함인 `args.base` 로
    되돌려도 7개 테스트가 전부 초록**이었다(SURVIVED).

    즉 **결함이 살던 자리는 함수가 아니라 호출부**였고, 함수만 잠근 락은 그 자리를
    비워 둔다. 그래서 여기서는 도구를 **끝에서 끝까지 실행**해 그 출력을 본다.
    """
    out = _run_tool(forked_repo, "--base", "theirs")
    assert "변경 파일:" in out, f"대상 목록을 못 읽었다 — 출력 형태가 바뀌었나.\n{out}"
    listed = out.split("변경 파일:", 1)[1]

    assert "shared_module.py" not in listed, (
        "main() 이 남이 수정한 파일을 대상으로 골랐다 — 호출부가 해석된 base 를 안 쓴다. "
        f"목록={listed.strip()}"
    )
    # ★짝 단언 — 하한이 없으면 "아무것도 안 고르는" 구현이 위 단언을 만족한다
    assert "my_module.py" in listed, f"내 커밋이 대상에서 빠졌다. 목록={listed.strip()}"
    assert "common.py" in listed, (
        "미커밋 수정이 대상에서 빠졌다 — 3-dot 과잉교정. "
        f"목록={listed.strip()}"
    )
    assert "ancient.py" not in listed, (
        "main() 이 분기점보다 **앞선** 변경까지 대상으로 골랐다 — base 가 너무 낮다. "
        f"목록={listed.strip()}"
    )


@pytest.mark.xfail(
    strict=True,
    reason="★부채(미수정) — `git diff` 는 untracked 를 안 본다. `git add` 하지 않은 "
           "**새 소스 파일은 변이 대상이 0건**인데 도구는 그 사실을 말하지 않는다. "
           "'생존 0'이 '감사 완료'로 읽히는 이 저장소의 단골 형태다. "
           "고치는 사람은 이 xfail 을 지우고 초록으로 바꿔라(strict 라 통과하면 시끄럽게 실패한다).",
)
def test_부채_untracked_새_파일도_변이_대상이어야_한다(forked_repo, monkeypatch) -> None:
    monkeypatch.chdir(forked_repo)
    tool = _load_tool()
    (forked_repo / "brand_new.py").write_text("fresh = 444\n", encoding="utf-8")
    names = {p.name for p in tool._changed_files(tool._resolve_base("theirs"))}
    assert "brand_new.py" in names


def test_공통조상을_못_찾으면_base_를_그대로_두고_시끄럽게_알린다(
    forked_repo, monkeypatch, capfd
) -> None:
    """★폴백 분기 — 여기가 조용하면 **틀린 대상을 감사하고도 초록**이다.

    `merge-base` 는 없는 ref·무관한 히스토리에서 실패한다. 그때:
      · **base 를 그대로 둔다** — 임의로 `HEAD` 같은 것으로 갈아치우면 대상이 통째로
        달라지는데 아무도 모른다(변이로 확인: 그 자리가 잠겨 있지 않았다).
      · **그 사실을 출력한다** — 침묵하면 다음 사람이 오염 가능성을 못 읽는다.
    """
    monkeypatch.chdir(forked_repo)
    tool = _load_tool()
    capfd.readouterr()

    got = tool._resolve_base("존재하지-않는-ref")

    assert got == "존재하지-않는-ref", (
        f"공통 조상 실패 시 base 가 조용히 바뀌었다 — 대상이 통째로 달라진다. 받은 값={got!r}"
    )
    out = capfd.readouterr().out
    assert "존재하지-않는-ref" in out, f"실패를 알리지 않았다(침묵). 출력={out!r}"


def test_정상_경로에서는_그_경고가_나오지_않는다(forked_repo, monkeypatch, capfd) -> None:
    """★특이도 — 항상 경고하는 구현이 위 테스트를 만족하면 안 된다(음성 대조군)."""
    monkeypatch.chdir(forked_repo)
    tool = _load_tool()
    capfd.readouterr()
    tool._resolve_base("theirs")
    out = capfd.readouterr().out
    assert "공통 조상을 찾지 못했다" not in out, (
        f"정상 경로인데 실패 경고가 나온다 — 위양성. 출력={out!r}"
    )
