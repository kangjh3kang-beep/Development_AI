"""`scripts/mutate_changed.py` 가 **`.sh` 를 기계 변이 모집단에 넣는다**.

★왜 이 락이 있나 (2026-09-12 파생 실측):
  이 저장소의 배포·롤백·감시·조율이 전부 셸이고 **그중 14개는 이미 pytest 락을 갖고 있다**.
  그런데 변이 도구가 확장자(`.py/.ts/.tsx`)로 걸러 온 탓에 그 락들은 **한 번도 기계 감사를
  받지 못했다** — 즉 *"도구를 돌렸다"* 가 그 축에서는 **보증이 아니었다**.

★이 파일의 규율: **판정식을 사본으로 갖지 않는다.**
  상수를 테스트가 복사해 자기 자신과 비교하면 아무것도 안 잠긴다(2026-09-12 `#1036` MAJOR-1).
  그래서 아래는 전부 **도구의 함수를 직접 불러 행위를 본다.**
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOL = _REPO_ROOT / "scripts" / "mutate_changed.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("_mutate_changed_under_test", _TOOL)
    assert spec and spec.loader, f"도구를 못 읽었다: {_TOOL}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mc = _load_tool()


# ── ① 모집단 — `.sh` 가 **실제로 들어온다** (대조군: `.md` 는 여전히 밖) ──────────
def test_changed_files_admits_shell_and_still_excludes_non_source(tmp_path, monkeypatch):
    """★두 모집단을 **같은 실행에서** 가른다 — 들어와야 할 것이 들어오고, 나가야 할 것이 나간다.

    차가 0인 픽스처는 잠금이 아니다: `.sh` 만 넣고 «통과» 하면 배제 규칙을 통째로 지워도 초록이다.
    """
    for name in ("deploy.sh", "svc.py", "notes.md", "app.tsx"):
        (tmp_path / name).write_text("x\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def _fake_run(cmd, *a, **kw):  # noqa: ARG001
        assert cmd[:3] == ["git", "diff", "--name-only"], f"호출 형태가 바뀌었다: {cmd}"
        return subprocess.CompletedProcess(
            cmd, 0, stdout="deploy.sh svc.py notes.md app.tsx\n", stderr="",
        )

    monkeypatch.setattr(mc.subprocess, "run", _fake_run)
    got = {p.name for p in mc._changed_files("BASE")}

    # ★공허 방지 — 아무것도 안 들어오면 아래 단언이 전부 공짜다.
    assert got, "변경 파일을 하나도 못 읽었다 — 조회기가 죽었다"
    assert "deploy.sh" in got, f"**`.sh` 가 모집단 밖이다** — 이 PR 이 고친 바로 그것: {got}"
    assert {"svc.py", "app.tsx"} <= got, f"기존 확장자가 회귀했다: {got}"
    assert "notes.md" not in got, f"소스가 아닌 것이 들어왔다 — 배제가 죽었다: {got}"


# ── ② 셸 조건 변이 — 발화하고, **파이썬 경로엔 안 샌다** ──────────────────────
def test_shell_condition_mutation_fires_and_does_not_leak_into_python():
    sh_line = 'if [ -z "$DEPLOY_HOST" ]; then'
    sh = mc._mutations_for_line(pathlib.Path("x.sh"), sh_line, 7)
    kinds = {m.kind: m.new for m in sh}
    assert "조건무력화" in kinds, f"셸 `if …; then` 이 변이되지 않는다: {kinds}"
    assert kinds["조건무력화"].strip() == "if false; then", kinds["조건무력화"]

    # ★대조군 — 같은 줄을 `.py` 로 주면 셸 규칙은 **안 걸려야** 한다(규칙이 언어를 안 가리면
    #   파이썬 파일에 `if false; then` 을 써 넣어 구문을 깬다).
    py = mc._mutations_for_line(pathlib.Path("x.py"), sh_line, 7)
    assert not any(m.new.strip() == "if false; then" for m in py), (
        f"셸 규칙이 파이썬 경로로 샜다: {[(m.kind, m.new) for m in py]}"
    )


def test_shell_if_false_is_not_mutated_into_itself():
    """★무변화 변이를 만들면 **항상 생존**해 신호를 더럽힌다."""
    out = mc._mutations_for_line(pathlib.Path("x.sh"), "if false; then", 1)
    assert not [m for m in out if m.kind == "조건무력화"], (
        f"`if false` 를 다시 `if false` 로 바꾸는 무변화 변이가 생겼다: {out}"
    )


# ── ③ 종료코드 — **두 모집단**(`exit 7` 은 변이, `exit 0` 은 불가침) ──────────
@pytest.mark.parametrize(
    ("line", "should_fire"),
    [("exit 7", True), ("    exit 1", True), ("exit 0", False)],
)
def test_exit_code_mutation_targets_only_failure_exits(line, should_fire):
    """게이트 스크립트의 계약은 «위반이면 0 이 아닌 코드로 죽는다» 이다.

    ★`exit 0` 을 변이 대상에 넣으면 **성공 경로를 실패로 만드는 파손**이라 계약 검증이 아니다.
    """
    got = [m for m in mc._mutations_for_line(pathlib.Path("g.sh"), line, 3) if m.kind == "종료코드무력화"]
    assert bool(got) is should_fire, f"{line!r} → {[(m.kind, m.new) for m in got]}"
    if should_fire:
        assert got[0].new.strip() == "exit 0", got[0].new


# ── ④ 구문 게이트 — 실재하고, **`sh -n` 이 아니라 `bash -n`** ────────────────
def test_syntax_gate_discriminates_broken_from_valid_shell(tmp_path):
    ok = tmp_path / "ok.sh"
    ok.write_text('set -e\nif [ -z "$X" ]; then\n  echo hi\nfi\n', encoding="utf-8")
    broken = tmp_path / "broken.sh"
    broken.write_text('if [ -z "$X" ]; then\n  echo hi\n', encoding="utf-8")  # `fi` 없음

    assert mc._mutant_broke_syntax(ok) == "", "정상 셸을 깨졌다고 신고한다(위양성)"
    assert mc._mutant_broke_syntax(broken), "구문이 깨진 셸을 **못 잡는다** — 거짓 CAUGHT 가 난다"


def test_syntax_gate_uses_bash_not_sh():
    """★`sh -n` 으로 짜면 **변이가 없어도** 실패하는 파일들이 전부 거짓 「판정 불가」가 된다.

    ★목록을 손으로 적지 않는다 — 저장소에서 **파생**시킨다.
      (2026-09-12 실측: `sh -n` 실패 6/35 · `bash -n` 실패 0/35)
    """
    tracked = subprocess.run(
        ["git", "ls-files", "*.sh"],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert tracked, "추적되는 `.sh` 가 0건 — 조회기가 죽었다"

    bashism_only = [
        f for f in tracked
        if (_REPO_ROOT / f).exists()
        and subprocess.run(["sh", "-n", str(_REPO_ROOT / f)],
                           capture_output=True, check=False).returncode != 0
    ]
    # ★공허 방지 선단언 — 이 집합이 비면 아래 «전부 통과» 가 공짜다.
    assert bashism_only, (
        "bash 확장을 쓰는 `.sh` 가 하나도 없다 — 이 락이 지키려는 상황이 사라졌거나 "
        "조회가 틀렸다. 사라졌다면 이 테스트를 지우지 말고 **왜 사라졌는지** 적어라."
    )
    for f in bashism_only:
        assert mc._mutant_broke_syntax(_REPO_ROOT / f) == "", (
            f"게이트가 `sh -n` 으로 되돌아갔다 — {f} 는 **변이가 없는데도** 깨졌다고 신고된다"
        )


def test_syntax_gate_catches_broken_python_too():
    """★처방 범위 = 결함 범위. 구문 파손은 `.py` 에서도 **거짓 CAUGHT** 를 만든다."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "m.py"
        p.write_text("def f():\n", encoding="utf-8")     # 본문 없음
        assert mc._mutant_broke_syntax(p), "구문이 깨진 파이썬을 못 잡는다"
        p.write_text("def f():\n    return 1\n", encoding="utf-8")
        assert mc._mutant_broke_syntax(p) == "", "정상 파이썬을 깨졌다고 신고한다"


# ── ⑤ 짝 테스트 탐색 = **참조 파생**(이름규칙 아님) ──────────────────────────
def test_shell_tests_are_found_by_reference_not_by_name(monkeypatch):
    """`safe-deploy.sh` 의 짝은 `test_safe-deploy.py` 가 **아니다**."""
    monkeypatch.chdir(_REPO_ROOT)   # 도구는 main() 에서 저장소 루트로 chdir 한다
    script = pathlib.Path("propai-platform/scripts/safe-deploy.sh")
    assert (_REPO_ROOT / script).exists(), f"대상 스크립트가 없어졌다: {script}"

    found = mc._tests_referencing(script)
    # ★공허 방지 — 비면 «못 찾았다» 와 «찾을 게 없다» 가 구별되지 않는다.
    assert found, "참조 파생이 0건 — `git grep` 이 죽었거나 축이 틀렸다"
    assert all(t.endswith(".py") for t in found), found
    # ★이름규칙으로는 **원리적으로** 못 찾는다는 것을 같이 잠근다.
    assert not (_REPO_ROOT / "propai-platform/apps/api/tests/test_safe-deploy.py").exists()

    # ★대조군 — 존재하지 않는 스크립트는 공집합이어야 한다(조회기가 아무거나 집지 않는다).
    assert mc._tests_referencing(pathlib.Path("no-such-script-zzz.sh")) == []


def test_guess_tests_routes_shell_through_reference_derivation(monkeypatch):
    monkeypatch.chdir(_REPO_ROOT)
    got = mc._guess_tests([pathlib.Path("propai-platform/scripts/safe-deploy.sh")])
    assert got, "`.sh` 가 `_guess_tests` 에서 0건 — EXIT=2 로 조용히 넘어간다"


# ── ⑥ 러너 경로 — 안 풀리는 것만 승격, **풀리는 것은 불변** ──────────────────
def test_rel_test_promotes_only_unresolvable_paths():
    cwd = pathlib.Path("propai-platform/apps/api")
    # 지금 동작하는 형태는 **건드리지 않는다**(회귀 방지).
    assert mc._rel_test("propai-platform/apps/api/tests/test_x.py", cwd) == "tests/test_x.py"
    assert mc._rel_test("/abs/tests/test_x.py", cwd) == "/abs/tests/test_x.py"
    # cwd 에서 안 풀리는 실재 경로는 절대경로로 승격된다 — 안 그러면 pytest 가
    # «file not found» 로 죽고 그것이 **기준선 실패**로 오독된다.
    rel = "propai-platform/tests/test_mutate_changed_sh_coverage.py"
    assert (_REPO_ROOT / rel).exists(), "이 테스트 파일 자신이 없어졌다"
    import os

    cur = os.getcwd()
    try:
        os.chdir(_REPO_ROOT)
        got = mc._rel_test(rel, cwd)
    finally:
        os.chdir(cur)
    assert pathlib.Path(got).is_absolute(), f"승격되지 않았다 — pytest 가 못 찾는다: {got}"


# ── ⑦ ★부채를 초록 안에 드러낸다 (커밋 메시지에만 적으면 안 드러난다) ────────
@pytest.mark.xfail(
    strict=True,
    reason="★부채: 저장소 루트 `scripts/` 5건(coord.sh · mutate_manual.sh 등)은 여전히 "
           "모집단 밖이다. 그 게이트의 사유(«도구 자신은 이 테스트들의 대상이 아니다»)가 "
           "지금도 참인지 **미측정**이다 — 이유는 「장치 부재」가 아니라 「안 쟀음」. "
           "재서 참이 아니면 이 xfail 이 **초록으로 뒤집히며** 알려 준다.",
)
def test_root_scripts_shell_also_enters_the_population(tmp_path, monkeypatch):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "coord.sh").write_text("x\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        mc.subprocess, "run",
        lambda cmd, *a, **kw: subprocess.CompletedProcess(cmd, 0, "scripts/coord.sh\n", ""),
    )
    assert [p.name for p in mc._changed_files("BASE")] == ["coord.sh"]


@pytest.mark.xfail(
    strict=True,
    reason="★부채: `.ts/.tsx` 에는 값싼 구문검사가 없어 **구문 파손 = 거짓 CAUGHT** 축이 "
           "닫히지 않는다(`tsc` 는 프로젝트 전체를 태워야 해 변이마다 못 돌린다). "
           "이 공백은 도구 독스트링에도 적혀 있다.",
)
def test_syntax_gate_covers_typescript_too(tmp_path):
    p = tmp_path / "m.ts"
    p.write_text("export const x = (\n", encoding="utf-8")
    assert mc._mutant_broke_syntax(p)
