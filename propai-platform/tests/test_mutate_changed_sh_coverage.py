"""`scripts/mutate_changed.py` 가 **`.sh` 를 기계 변이 모집단에 넣는다**.

★왜 이 락이 있나 (2026-09-12 파생 실측):
  이 저장소의 배포·롤백·감시·조율이 전부 셸이고 **여럿이 이미 pytest 락을 갖고 있다**
  (base `cd942c6ec` 에서 17/39 — ★**수를 인용할 때 기준 sha 를 같이 적는다.** 처음엔
   «14/35» 라 적었는데 **45커밋 뒤처진 워크트리**에서 잰 값이었다).
  그런데 변이 도구가 확장자(`.py/.ts/.tsx`)로 걸러 온 탓에 그 락들은 **한 번도 기계 감사를
  받지 못했다** — 즉 *"도구를 돌렸다"* 가 그 축에서는 **보증이 아니었다**.

★이 파일의 규율: **판정식을 사본으로 갖지 않는다.**
  상수를 테스트가 복사해 자기 자신과 비교하면 아무것도 안 잠긴다(2026-09-12 `#1036` MAJOR-1).
  그래서 아래는 전부 **도구의 함수를 직접 불러 행위를 본다.**
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess
import sys
import uuid

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

    def _fake_run(cmd, *a, **kw):
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
      (2026-09-12 실측 · base `cd942c6ec`: `sh -n` 실패 **6/39** · `bash -n` 실패 **0/39**)
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
    #   ★★이름을 **런타임에 만든다**. 처음엔 리터럴을 적었다가 이 단언이 빨개졌다:
    #     `git grep -F` 가 **내가 방금 쓴 그 리터럴을 이 파일에서** 찾았기 때문이다.
    #     (CLAUDE.md §검증규율 8 — *"주석에 예시를 적으면 그 예시가 다음 검사의 위양성이 된다"*.)
    #   ★그리고 그 실패는 **커밋한 뒤에야** 났다 — `git grep` 은 **추적 파일만** 본다.
    #     미추적 상태에서 초록이던 락이 추적되는 순간 뒤집힌다(9조 §3 의 형제).
    absent = pathlib.Path(f"zz-{uuid.uuid4().hex}.sh")
    assert mc._tests_referencing(absent) == [], (
        f"존재하지 않는 스크립트에 참조가 잡혔다 — 조회기가 아무거나 집는다: {absent}"
    )


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
    reason="★부채: 저장소 루트 `scripts/` 의 셸은 여전히 모집단 밖이다(개수는 테스트가 "
           "`git ls-files` 로 파생해 메시지에 싣는다 — 손으로 세지 않는다). 그 게이트의 "
           "사유(«도구 자신은 이 테스트들의 대상이 아니다»)가 지금도 참인지 **미측정**이며 "
           "이유는 「장치 부재」가 아니라 「안 쟀음」. 재서 참이 아니면 초록으로 뒤집힌다.",
)
def test_root_scripts_shell_also_enters_the_population(tmp_path, monkeypatch):
    derived = subprocess.run(
        ["git", "ls-files", "scripts/*.sh"], cwd=_REPO_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.split()
    # ★사유에 개수를 **적지 않고** 여기서 파생시킨다 — 손으로 센 수는 곧 상한이 된다.
    #   (종전 사유는 «테스트가 파생해 메시지에 싣는다» 고 **주장만** 하고 본문엔 없었다.)
    assert derived, "루트 scripts/ 의 셸이 0건 — 조회기가 죽었다"
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "coord.sh").write_text("x\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        mc.subprocess, "run",
        lambda cmd, *a, **kw: subprocess.CompletedProcess(cmd, 0, "scripts/coord.sh\n", ""),
    )
    assert [p.name for p in mc._changed_files("BASE")] == ["coord.sh"], (
        f"루트 scripts/ 의 셸 {len(derived)}건이 여전히 모집단 밖이다"
    )


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


# ── ⑧ ★종단 — 「판정 불가」가 **판정 루프에 실제로 배선**됐는가 ────────────────
#    함수를 잠그는 것과 **그 함수가 불리는 것**은 다르다(존재를 잠그면 행위는 안 잠긴다).
#    `_mutant_broke_syntax` 를 단위로만 잠그면, 루프에서 그 호출을 지워도 전부 초록이다.
#    ⇒ **합성 저장소에 도구를 통째로 태워** 출력으로 확인한다.
def _git(*args: str, cwd: pathlib.Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _verdicts(out: str) -> dict[str, str]:
    """출력에서 **변이 인덱스별 판정**을 파싱한다 — `{"1": "판정불가", ...}`.

    ★산문을 줄 단위로 훑지 않는다. 종전 락은 «판정불가 줄 안에 kill 이 없다» 만 봤는데
      `kill` 은 **다음 줄**에 찍히므로, 같은 변이가 **두 통에 동시에** 들어가도 초록이었다
      (독립 리뷰 MEDIUM-3 — `continue` 한 줄을 지우면 거짓 CAUGHT 가 그대로 부활했다).
    """
    out_map: dict[str, list[str]] = {}
    for mm in re.finditer(r"^\s*\[\s*(\d+)/\s*\d+\]\s*(판정불가|kill|★생존|skip\S*)", out, re.MULTILINE):
        out_map.setdefault(mm.group(1), []).append(mm.group(2))
    dupes = {k: v for k, v in out_map.items() if len(v) != 1}
    assert not dupes, f"★같은 변이가 **여러 번 판정**됐다(두 통 동시 계수): {dupes}"
    return {k: v[0] for k, v in out_map.items()}


def test_end_to_end_reports_syntax_broken_mutant_as_undecided(tmp_path):
    """★구문을 깼고 **그래서 실패한** 변이는 CAUGHT 도 SURVIVED 도 아니다.

    합성 셸: `then` 블록의 유일한 문장이 대입이라, 그 줄을 지우면 `if …; then / fi` 가
    남아 **bash 구문이 깨진다**. 종전 도구라면 테스트가 실패해 `kill`(=CAUGHT)로 세어져
    **변이 점수가 거짓으로 부풀었다.**
    ★그리고 그 사실이 **rc 에 실려야** 한다 — 기계는 rc 만 본다(독립 리뷰 MAJOR-1).
    """
    repo = tmp_path / "synthrepo"
    (repo / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    _git("config", "user.email", "t@t", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)

    # base 커밋 — 아직 대상 셸이 없다(그래야 이후 줄이 전부 "추가된 줄"이 된다).
    # ★이 테스트는 g.sh 를 **실제로 태운다**(내용 단언). 그래야 변이가 실패를 만들고,
    #   «깨졌고 그래서 실패한» 경우 = 판정 불가가 성립한다.
    #   ★조건 변이도 **잡히게** 해 둔다 — 그래야 이 락이 재는 것이 「판정 불가 하나」로
    #     좁혀진다. 안 그러면 생존이 섞여 rc 가 1 이 되고, 이 테스트가 보려는 축이 흐려진다
    #     (두 사건을 한 픽스처에 섞지 않는다).
    (repo / "tests" / "test_g.py").write_text(
        "import pathlib\n"
        "def test_body_and_condition_are_present():\n"
        "    src = pathlib.Path('g.sh').read_text(encoding='utf-8')\n"
        "    assert 'Y=1' in src\n"
        "    assert '-z \"$X\"' in src\n",
        encoding="utf-8",
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "base", cwd=repo)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()

    (repo / "g.sh").write_text(
        '#!/usr/bin/env bash\nif [ -z "$X" ]; then\n  Y=1\nfi\n', encoding="utf-8"
    )
    # ★스테이징한다 — `git diff` 는 **미추적 파일을 안 본다**. 안 하면 변이 대상 0건이
    #   되어 이 락이 «아무것도 안 본 채» 초록이 된다(9조 §3 · 실제로 여기서 한 번 겪었다).
    _git("add", "g.sh", cwd=repo)

    r = subprocess.run(
        [sys.executable, str(_TOOL), "--base", base,
         "--tests", "tests/test_g.py", "--cwd", ".", "--max", "50"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    out = r.stdout + r.stderr

    # ★공허 방지 선단언 — 변이가 0건이면 아래 판정이 전부 공짜다.
    assert "변이 " in out and "변이 0건" not in out, f"변이를 만들지 못했다:\n{out}"

    verdicts = _verdicts(out)          # ★인덱스별로 **정확히 한 번**임을 그 안에서 단언한다
    assert "판정불가" in verdicts.values(), (
        f"★구문을 깬 변이가 판정 불가로 갈라지지 않았다 — 루프 배선이 끊겼다.\n{out}"
    )

    # ★요약 블록이 **실제로 찍히는가**(개별 줄과 다른 문자열이라 판별력이 있다).
    #   이것이 없으면 «분모가 작아졌다»를 아무도 못 본다.
    assert "★판정 불가" in out, f"판정 불가 **요약 경고**가 통째로 사라졌다:\n{out}"

    # ★★기계 판독 줄 — 산문이 아니라 이 줄이 계약이다.
    audit = re.search(r"^::AUDIT=(.+)$", out, re.MULTILINE)
    assert audit, f"::AUDIT= 기계 줄이 없다:\n{out}"
    assert "undecided=0" not in audit.group(1), audit.group(1)

    # ★★rc 축 — 「판정 불가만 있고 생존 0」이 EXIT=0 이면 호출자에겐 «전수 CAUGHT» 와
    #   완전히 같은 신호다. 그래서 3 이어야 한다(모듈 독스트링의 종료코드 계약).
    assert r.returncode == 3, f"rc={r.returncode} · 기대 3\n{out}"


def test_end_to_end_still_reports_ordinary_verdicts(tmp_path):
    """★대조군 — 구문을 **안 깨는** 변이는 평소대로 `kill`/`생존` 으로 판정된다.

    이게 없으면 «전부 판정 불가로 도망가는» 퇴화가 초록으로 통과한다.
    """
    repo = tmp_path / "synthrepo2"
    (repo / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    _git("config", "user.email", "t@t", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    (repo / "tests" / "test_g.py").write_text(
        "import pathlib\n"
        "def test_guard_exits_nonzero():\n"
        "    src = pathlib.Path('g.sh').read_text(encoding='utf-8')\n"
        "    assert 'exit 9' in src\n",
        encoding="utf-8",
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "base", cwd=repo)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()

    # 구문을 깨지 않는 변이만 나오는 셸(`exit 9` 단독 줄).
    (repo / "g.sh").write_text('#!/usr/bin/env bash\nexit 9\n', encoding="utf-8")
    _git("add", "g.sh", cwd=repo)   # ★9조 §3 — 미추적은 변이 대상 0건

    r = subprocess.run(
        [sys.executable, str(_TOOL), "--base", base,
         "--tests", "tests/test_g.py", "--cwd", ".", "--max", "50"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    out = r.stdout + r.stderr
    verdicts = _verdicts(out)
    assert "kill" in verdicts.values(), (
        f"★정상 변이가 판정되지 않았다 — 전부 판정 불가로 도망갔나:\n{out}"
    )
    assert "판정불가" not in verdicts.values(), f"정상 변이를 판정 불가로 신고한다:\n{out}"
    assert "★판정 불가" not in out, f"판정 불가가 0건인데 요약을 찍는다:\n{out}"
    assert r.returncode == 0, f"전부 걸렸는데 rc={r.returncode}\n{out}"


# ── ⑨ MAJOR-3 — **깨졌는데 테스트가 통과하면 그건 진짜 「생존」이다** ────────────
def test_syntax_broken_mutant_that_still_passes_is_survival_not_undecided(tmp_path):
    """★판정 불가는 **«깨졌고 그래서 실패한»** 경우로 좁힌다.

    깨진 변이에서 테스트가 **통과**했다면 정보가 하나도 안 줄었다 — «그 파일을 아무도
    태우지 않는다»는 뜻이고, 그것이 정확히 **잠기지 않았다는 신호**다.
    여기서 판정을 접으면 이 도구는 *거짓 CAUGHT* 뿐 아니라 **진짜 SURVIVED 까지** 같은
    통에 넣어 초록으로 만든다(독립 리뷰 MAJOR-3 — base 판이 `★생존`+rc=1 로 내던 신호).
    """
    repo = tmp_path / "synthrepo3"
    (repo / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    _git("config", "user.email", "t@t", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    # ★g.sh 를 **전혀 태우지 않는** 테스트 — 그래서 무엇을 하든 통과한다.
    (repo / "tests" / "test_g.py").write_text(
        "def test_unrelated():\n    assert 1 + 1 == 2\n", encoding="utf-8"
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "base", cwd=repo)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()

    (repo / "g.sh").write_text(
        '#!/usr/bin/env bash\nif [ -z "$X" ]; then\n  Y=1\nfi\n', encoding="utf-8"
    )
    _git("add", "g.sh", cwd=repo)

    r = subprocess.run(
        [sys.executable, str(_TOOL), "--base", base,
         "--tests", "tests/test_g.py", "--cwd", ".", "--max", "50"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    out = r.stdout + r.stderr
    verdicts = _verdicts(out)
    assert "★생존" in verdicts.values(), (
        "★깨진 변이에서 테스트가 통과했는데 **생존으로 안 세었다** — 진짜 신호를 숨긴다.\n"
        f"{out}"
    )
    assert "판정불가" not in verdicts.values(), f"통과했는데 판정 불가로 접었다:\n{out}"
    assert r.returncode == 1, f"생존이 있는데 rc={r.returncode}\n{out}"


# ── ⑩ MAJOR-2 — 같은 줄이 여러 번 나와도 **버리지 않는다**(줄번호 치환) ────────
def test_duplicate_lines_are_mutated_at_their_own_line_not_dropped():
    """★종전엔 `original.count(old) != 1` 이면 통째로 버렸다.

    셸에서 그 손실이 크다 — `exit 1` 은 배포 게이트의 **표준 실패코드**라 한 파일에 여러 번
    나온다(실측: 종료코드 규칙 생성분의 **40%** 가 그렇게 버려졌다).
    """
    src = "a() {\n  exit 1\n}\nb() {\n  exit 1\n}\n"
    m2 = mc.Mutation("종료코드무력화", pathlib.Path("g.sh"), "  exit 1", "  exit 0", 2)
    m5 = mc.Mutation("종료코드무력화", pathlib.Path("g.sh"), "  exit 1", "  exit 0", 5)

    got2 = mc._apply_at_line(src, m2)
    got5 = mc._apply_at_line(src, m5)
    assert got2 is not None and got5 is not None, "중복 줄이라고 버렸다"
    # ★두 모집단 — **서로 다른 줄**이 바뀌어야 한다(같으면 줄번호를 안 쓰는 것이다).
    assert got2 != got5, "줄 번호를 무시하고 같은 자리를 바꿨다"
    assert got2.splitlines()[1].strip() == "exit 0" and got2.splitlines()[4].strip() == "exit 1"
    assert got5.splitlines()[4].strip() == "exit 0" and got5.splitlines()[1].strip() == "exit 1"

    # ★대조군 — 줄이 기대와 다르면 **조용히 엉뚱한 데를 바꾸지 않고** None 을 준다.
    bad = mc.Mutation("종료코드무력화", pathlib.Path("g.sh"), "  exit 1", "  exit 0", 3)
    assert mc._apply_at_line(src, bad) is None, "줄이 안 맞는데 주입했다"


# ── ⑪ MEDIUM-1 — **한 줄 가드**를 본다. 그리고 꼬리를 안 버린다 ────────────────
def test_one_line_guard_is_reachable_and_keeps_its_tail():
    """이 저장소의 배포 가드는 `if …; then …; exit N; fi` 한 줄 관용구를 쓴다.

    ★꼬리(`fi`)를 버리면 **구문이 깨진다** — 그건 변이가 아니라 파손이다.
    """
    line = '  if [ "$ok" != "1" ]; then echo bad; exit 1; fi'
    kinds = {m.kind: m.new for m in mc._mutations_for_line(pathlib.Path("d.sh"), line, 4)}
    assert "조건무력화" in kinds, f"한 줄 가드의 조건이 안 잡힌다: {kinds}"
    assert "종료코드무력화" in kinds, f"한 줄 가드의 exit 이 안 잡힌다: {kinds}"
    assert kinds["조건무력화"].rstrip().endswith("fi"), (
        f"꼬리를 버렸다 — fi 가 사라져 구문이 깨진다: {kinds['조건무력화']!r}"
    )
    assert "exit 0" in kinds["종료코드무력화"] and "echo bad" in kinds["종료코드무력화"]


def test_shell_condition_and_exit_mutations_do_not_break_syntax_across_the_repo(tmp_path):
    """★위양성도 결함이다 — 넓힌 규칙이 **정상 셸의 구문을 깨면** 안 된다.

    목록이 아니라 **저장소 전수**에서 파생시킨다.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "*.sh"], cwd=_REPO_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.split()
    checked = broken = 0
    for rel in tracked:
        f = _REPO_ROOT / rel
        if not f.exists():
            continue
        src = f.read_text(encoding="utf-8", errors="replace")
        if subprocess.run(["bash", "-n", str(f)], capture_output=True, check=False).returncode:
            continue                      # 기준선이 이미 깨진 파일은 모집단 밖
        for i, ln in enumerate(src.splitlines(), 1):
            for m in mc._mutations_for_line(f, ln, i):
                if m.kind not in ("조건무력화", "종료코드무력화"):
                    continue
                mutated = mc._apply_at_line(src, m)
                assert mutated is not None, f"{rel}:{i} 주입 실패"
                checked += 1
                tmp = tmp_path / "probe.sh"
                tmp.write_text(mutated, encoding="utf-8")
                if subprocess.run(["bash", "-n", str(tmp)],
                                  capture_output=True, check=False).returncode:
                    broken += 1
    # ★공허 방지 — 0건이면 아래 «파손 0» 이 공짜다.
    assert checked > 50, f"검사한 변이가 너무 적다({checked}) — 규칙이 죽었나"
    assert broken == 0, f"조건·종료코드 변이가 정상 셸의 구문을 깬다: {broken}/{checked}"


# ── ⑫ MEDIUM-2 — 나머지 두 규칙도 **두 모집단**으로 잠근다 ────────────────────
@pytest.mark.parametrize(
    ("line", "should_fire"),
    [
        ("VAR=1", True),
        ("export TOKEN=abc", True),
        ("  local x=2", True),
        ('if [ "$a" = "$b" ]; then', False),      # ★비교는 대입이 아니다
        ("echo hi", False),
    ],
)
def test_shell_assignment_rule_has_two_populations(line, should_fire):
    got = [m for m in mc._mutations_for_line(pathlib.Path("x.sh"), line, 1) if m.kind == "줄삭제"]
    assert bool(got) is should_fire, f"{line!r} → {[m.kind for m in got]}"


@pytest.mark.parametrize(
    ("line", "should_fire"),
    [
        ('echo "가드 라이브러리를 읽지 못했습니다"', True),
        ('echo "ab"', False),                      # ★8자 미만 리터럴은 대상이 아니다
    ],
)
def test_shell_string_rule_has_two_populations(line, should_fire):
    got = [
        m for m in mc._mutations_for_line(pathlib.Path("x.sh"), line, 1)
        if m.kind == "문자열변경"
    ]
    assert bool(got) is should_fire, f"{line!r} → {[(m.kind, m.new) for m in got]}"
    if should_fire:
        assert "__MUTATED__" in got[0].new


# ── ⑬ 계수와 rc — **순수 함수로 잠근다**(산수는 잠글 수 있어야 한다) ──────────
@pytest.mark.parametrize(
    ("gen", "surv", "und", "skip", "trunc", "want_judged", "want_caught"),
    [
        (10, 0, 0, 0, 0, 10, 10),
        (10, 3, 0, 0, 0, 10, 7),
        (10, 0, 4, 0, 0, 6, 6),     # ★판정 불가는 분모에서 빠진다
        (10, 0, 0, 2, 0, 8, 8),     # ★★건너뜀도 분모에서 빠진다(종전엔 안 뺐다 — 거짓 수)
        (10, 0, 0, 0, 7, 3, 3),     # ★★★`--max` 절단도 — 기본 60 인데 셸 전수는 2,441건이다
        (10, 1, 4, 2, 1, 3, 2),
    ],
)
def test_audit_counts_removes_unaudited_from_the_denominator(
    gen, surv, und, skip, trunc, want_judged, want_caught,
):
    c = mc._audit_counts(gen, surv, und, skip, trunc)
    assert c["judged"] == want_judged, c
    assert c["caught"] == want_caught, c
    # ★항등식 — 분자들의 합이 분모를 넘지 않는다(계수가 서로 모순되지 않는다).
    assert c["caught"] + c["survived"] == c["judged"], c
    assert (
        c["judged"] + c["undecided"] + c["skipped"] + c["truncated"] == c["generated"]
    ), c
    # ★`*_files` 는 **단위가 다르다**(파일 수) — 위 항등식(변이 수)에 섞이면 안 된다.
    assert "scoped_out_files" in c and "only_out_files" in c, c


@pytest.mark.parametrize(
    ("surv", "und", "skip", "trunc", "scoped", "only", "want_rc"),
    [
        (0, 0, 0, 0, 0, 0, 0),   # 전부 걸렸고 감사 안 된 것 없음 → 초록
        (2, 0, 0, 0, 0, 0, 1),   # 생존 있음
        (0, 1, 0, 0, 0, 0, 3),   # ★판정 불가만 → **0 이면 안 된다**(전수 CAUGHT 와 같은 신호)
        (0, 0, 1, 0, 0, 0, 3),   # ★건너뜀만
        (0, 0, 0, 1, 0, 0, 3),   # ★★`--max` 절단만 → **기본 사용 경로**가 여기 걸린다
        (0, 0, 0, 0, 1, 0, 3),   # ★★★**범위 불일치로 조용히 빠진 파일** — 네 번째 얼굴
        (0, 0, 0, 0, 0, 1, 0),   # ★`--only` 는 **선언된 좁히기**라 rc 에 안 싣는다(두 모집단)
        (2, 5, 5, 5, 5, 5, 1),   # 생존이 우선(가장 시끄러운 신호)
    ],
)
def test_audit_exit_puts_unaudited_work_on_the_return_code(
    surv, und, skip, trunc, scoped, only, want_rc,
):
    """★«감사되지 않은 일」은 **얼굴이 넷**이다 — 판정 불가 · 건너뜀 · 상한 절단 ·
    **범위 불일치**. 하나를 rc 에 실었으면 나머지를 **같은 함수에서** 파생시켜야 한다.

    ★네 번째(범위 불일치)는 R1→R2→R3 세 판을 거쳐서야 나왔다: 매번 «지적된 자리」만
      고치고 형제 축을 남긴 것이다. 그래서 이 표가 **네 얼굴을 한 자리에** 세운다.
    ★`only_out_files` 만 예외다 — 사용자가 `--only` 로 **의도를 선언**했다.
    """
    counts = mc._audit_counts(10, surv, und, skip, trunc, scoped, only)
    assert mc._audit_exit(counts) == want_rc, counts


@pytest.mark.xfail(
    strict=True,
    reason="★부채(대칭 표기): 셸에는 `.py` 의 `_docstring_line_nos` 에 해당하는 장치가 없어 "
           "**heredoc 내부 줄이 변이 대상으로 들어온다**(실행 파일 기준 **83줄이 87변이**를 낳는다 — 줄 수와 변이 수는 다른 단위다). "
           "구문 게이트가 일부를 잡고 전체 판정불가율은 5%로 낮아 **당장의 소음은 작지만**, "
           "부채를 산문으로만 두면 드러나지 않으므로 초록 안에 세워 둔다.",
)
def test_heredoc_body_is_not_mutated(tmp_path):
    """heredoc 본문은 **코드가 아니라 데이터**다 — 거기 변이를 넣어도 의미가 없다.

    ★이 락의 초판은 `cfg = 1` 한 줄을 줬다가 **XPASS** 로 뒤집혔다: 그 줄은 셸 대입 형태가
      아니라 **애초에 변이 대상이 아니었다.** 부채는 실재하는데(실행 파일 87줄) 내 픽스처가
      그것을 재현하지 못한 것이다 — *«부채가 있다»와 «내 예시가 부채를 가리킨다»는 다르다.*
      그래서 **파일 문맥**으로 바꾼다(heredoc 은 한 줄만 봐서는 알 수 없다).
    """
    f = tmp_path / "h.sh"
    f.write_text(
        "#!/usr/bin/env bash\n"
        "python3 - <<'PY'\n"
        'print("이 문장은 heredoc 안의 데이터다")\n'
        "PY\n",
        encoding="utf-8",
    )
    lines = f.read_text(encoding="utf-8").splitlines()
    inside = [
        m for i, ln in enumerate(lines, 1) if i == 3
        for m in mc._mutations_for_line(f, ln, i)
    ]
    assert not inside, f"heredoc 본문이 변이 대상으로 들어왔다: {[(m.kind, m.new) for m in inside]}"


# ── ⑭ MAJOR-A — **`--max` 절단**도 감사되지 않은 일이다(rc 와 분모에 실린다) ──────
def _synth_repo(tmp_path, name, sh_body, test_body):
    repo = tmp_path / name
    (repo / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    _git("config", "user.email", "t@t", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    (repo / "tests" / "test_g.py").write_text(test_body, encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "base", cwd=repo)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()
    target = "g.sh" if sh_body.startswith("#!") else "m.py"
    (repo / target).write_text(sh_body, encoding="utf-8")
    _git("add", target, cwd=repo)          # ★9조 §3 — 미추적은 변이 대상 0건
    return repo, base


def _run_tool(repo, base, *extra):
    return subprocess.run(
        [sys.executable, str(_TOOL), "--base", base,
         "--tests", "tests/test_g.py", "--cwd", ".", *extra],
        cwd=repo, capture_output=True, text=True, check=False,
    )


_ALL_EXITS_LOCKED = (
    "import pathlib\n"
    "def test_all_exits_present():\n"
    "    src = pathlib.Path('g.sh').read_text(encoding='utf-8')\n"
    "    for n in ('1', '2', '3', '9'):\n"
    "        assert 'exit ' + n in src\n"
)
_FOUR_EXITS = "#!/usr/bin/env bash\nexit 1\nexit 2\nexit 3\nexit 9\n"


def test_max_truncation_is_counted_and_lands_on_the_return_code(tmp_path):
    """★`--max` 로 버린 변이는 **감사되지 않았다** — 그런데 종전엔 어느 통에도 안 들어갔다.

    ★★실해가 크다: 기본값은 `--max 60` 인데 이 저장소 `.sh` 전수 생성은 **2,441건**이다.
      즉 **정상 사용 경로에서 97.5% 가 감사되지 않은 채 `rc=0`** 이 나갔다. 도구는
      «전수가 아니다» 를 **산문으로** 찍고 있었고, **기계는 산문을 안 읽는다**(리뷰 R2 MAJOR-A).
    """
    repo, base = _synth_repo(tmp_path, "trunc", _FOUR_EXITS, _ALL_EXITS_LOCKED)

    cut = _run_tool(repo, base, "--max", "2")
    out = cut.stdout + cut.stderr
    audit = re.search(r"^::AUDIT=(.+)$", out, re.MULTILINE)
    assert audit, f"::AUDIT= 가 없다:\n{out}"
    fields = dict(kv.split("=", 1) for kv in audit.group(1).split())
    # ★분모는 **자르기 전 수**여야 한다 — 잘린 리스트를 세면 기계 줄이 거짓말을 한다.
    assert fields["generated"] == "4", f"거짓 분모: {fields}"
    assert fields["truncated"] == "2", fields
    assert cut.returncode == 3, f"절단됐는데 rc={cut.returncode}\n{out}"

    # ★대조군 — **같은 저장소·같은 변이**인데 절단만 없애면 `rc=0`. 차가 0인 픽스처가 아니다.
    full = _run_tool(repo, base, "--max", "50")
    fout = full.stdout + full.stderr
    faudit = re.search(r"^::AUDIT=(.+)$", fout, re.MULTILINE)
    assert faudit and "truncated=0" in faudit.group(1), fout
    assert full.returncode == 0, f"절단이 없는데 rc={full.returncode}\n{fout}"


# ── ⑮ MAJOR-B — 판정 불가 배선이 **`.py` 축에서도** 살아 있는가 ──────────────────
def test_undecided_wiring_is_alive_for_python_too(tmp_path):
    """★처방 범위 = 결함 범위. 종단 락이 **셋 다 `.sh`** 라, 배선을 `.py` 에서만 되돌려도
    전부 초록이었다(리뷰 R2 MAJOR-B — `and m.path.suffix != ".py"` 한 줄로 거짓 CAUGHT 복원).

    ★이 저장소는 **압도적 다수 변이가 `.py`** 라 무잠금 면적이 셸보다 넓다.
    """
    # ★블록의 **유일한 문장**이어야 그 줄을 지우면 IndentationError 가 난다.
    #   `return x` 를 남기면 지워도 **구문이 유효**해서 이 락이 재려는 상황이 안 만들어진다
    #   (처음에 그렇게 썼다 — 픽스처가 부채를 안 가리면 락은 장식이다).
    body = "def f():\n    x = 5\n"
    test_body = (
        "import pathlib\n"
        "def test_body_present():\n"
        "    assert 'x = 5' in pathlib.Path('m.py').read_text(encoding='utf-8')\n"
    )
    repo, base = _synth_repo(tmp_path, "pyrepo", body, test_body)
    r = _run_tool(repo, base, "--max", "50")
    out = r.stdout + r.stderr
    verdicts = _verdicts(out)
    assert "판정불가" in verdicts.values(), (
        f"★`.py` 에서 구문 파손 변이가 **거짓 CAUGHT 로 되돌아갔다**:\n{out}"
    )
    assert r.returncode == 3, f"rc={r.returncode} · 기대 3\n{out}"


# ── ⑯ MEDIUM-D — 셸 `case` 기본절 `*)` 은 **주석이 아니다** ──────────────────────
@pytest.mark.parametrize(
    ("line", "should_fire"),
    [
        ('*) status "FAIL unknown"; exit 1 ;;', True),   # ★배포 게이트의 **거부 경로**
        ("z) exit 1 ;;", True),                          # 대조군(원래 잡히던 모양)
        ("# exit 1", False),                             # 셸 주석은 `#` 뿐이다
    ],
)
def test_shell_case_default_is_not_treated_as_a_comment(line, should_fire):
    got = [
        m for m in mc._mutations_for_line(pathlib.Path("d.sh"), line, 1)
        if m.kind == "종료코드무력화"
    ]
    assert bool(got) is should_fire, f"{line!r} → {[(m.kind, m.new) for m in got]}"


def test_jsdoc_continuation_is_still_a_comment_outside_shell():
    """★대조군 — 셸을 먼저 가른다고 해서 **다른 언어의 주석 판정이 느슨해지면** 안 된다."""
    assert not mc._mutations_for_line(pathlib.Path("a.ts"), " * 이것은 JSDoc 이어짐이다", 1)


# ── ⑰ MEDIUM-E — 한 줄에 `exit` 이 둘이면 **변이도 둘** ────────────────────────
def test_each_exit_token_gets_its_own_mutation():
    """★한 변이로 둘을 같이 죽이면 테스트가 **둘 중 하나만 봐도 CAUGHT** 라, 나머지 한쪽의
    무잠금이 **가려진다**. 이 PR 이 `safe-deploy.sh` 에서 찾아낸 `or` 결함과 같은 기제다.
    """
    line = "both) a || exit 1; b || exit 2 ;;"
    got = [
        m for m in mc._mutations_for_line(pathlib.Path("d.sh"), line, 1)
        if m.kind == "종료코드무력화"
    ]
    assert len(got) == 2, f"토큰 2개인데 변이 {len(got)}건: {[m.new for m in got]}"
    news = {m.new for m in got}
    assert len(news) == 2, f"두 변이가 같다(뭉쳤다): {news}"
    # ★각 변이는 **정확히 한쪽만** 죽인다.
    assert "both) a || exit 0; b || exit 2 ;;" in news, news
    assert "both) a || exit 1; b || exit 0 ;;" in news, news


# ── ⑱ MINOR — 저자가 「…한다」고 쓴 동작 주장에 각각 변이를 넣을 자리 ─────────────
def test_tests_referencing_uses_fixed_string_not_regex(tmp_path, monkeypatch):
    """독스트링이 *"고정문자열(`-F`)로 찾는다"* 고 **주장**한다 — 그 주장을 잠근다(§G-30).

    정규식으로 읽히면 `a-b.sh` 의 `.` 이 임의 문자가 되어 `a-bXsh` 를 집는다.
    """
    monkeypatch.chdir(_REPO_ROOT)
    captured: list[list[str]] = []
    real = mc.subprocess.run

    def spy(cmd, *a, **kw):
        if cmd and cmd[0] == "git" and "grep" in cmd:
            captured.append(list(cmd))
        return real(cmd, *a, **kw)

    monkeypatch.setattr(mc.subprocess, "run", spy)
    mc._tests_referencing(pathlib.Path("propai-platform/scripts/safe-deploy.sh"))
    assert captured, "git grep 을 부르지 않았다 — 조회 축이 바뀌었다"
    assert "-F" in captured[0], f"고정문자열 플래그가 없다(정규식으로 읽힌다): {captured[0]}"


def test_rel_test_does_not_fabricate_paths_that_do_not_exist():
    """★없는 경로를 **날조 절대경로**로 바꾸면 pytest 의 «file not found» 가 엉뚱한 곳을
    가리켜 「기준선 실패」 진단이 틀린다.
    """
    cwd = pathlib.Path("propai-platform/apps/api")
    ghost = f"zz-{uuid.uuid4().hex}/test_nope.py"
    assert mc._rel_test(ghost, cwd) == ghost, "존재하지 않는 경로를 절대경로로 날조했다"


@pytest.mark.parametrize(
    ("src", "line_no", "new", "want"),
    [
        ("a\r\nb\r\n", 1, "Z", "Z\r\nb\r\n"),   # ★CRLF 보존
        ("a\nb", 2, "Z", "a\nZ"),                # ★마지막 줄 개행 없음 — 만들어 내지 않는다
        ("a\nb\n", 2, "", "a\n\n"),              # 줄삭제는 **빈 줄**을 남긴다
    ],
)
def test_apply_at_line_preserves_line_endings(src, line_no, new, want):
    body = src.splitlines()[line_no - 1]
    m = mc.Mutation("줄삭제", pathlib.Path("x.sh"), body, new, line_no)
    assert mc._apply_at_line(src, m) == want


# ── ⑲ R3 — **범위 불일치로 조용히 빠진 파일**도 rc 에 실린다(네 번째 얼굴) ──────
def test_files_dropped_by_test_scope_are_not_silently_green(tmp_path):
    """★변경 파일이 지정 테스트와 종류가 안 맞으면 **조용히 배제**되고, 그 변경은 이 실행에서
    **한 번도 변이되지 않는다**. 그런데 종전엔 `rc` 에도 `::AUDIT=` 에도 안 실려
    **「전부 감사됨」과 구별되지 않는 신호**가 나갔다(리뷰 R3).

    ★이 PR 은 §6 에서 *«감사 안 된 일은 rc 에 반드시 실린다»* 를 **스스로 선언**했다 —
      그 선언을 자기 안에서 어긴 자리다. 그리고 `.sh` 를 그 스코핑 경로에 **새로 편입**시켰다.
    """
    repo = tmp_path / "scoped"
    (repo / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    _git("config", "user.email", "t@t", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    # ★파일명은 `_run_tool` 이 `--tests` 로 주는 것과 **같아야** 한다 — 처음에 `test_c.py` 로
    #   만들었다가 기준선이 깨져 도구가 일찍 종료했다(내 픽스처가 틀렸고 도구는 옳았다).
    (repo / "tests" / "test_g.py").write_text(
        "import pathlib\n"
        "def test_g():\n"
        "    assert 'exit 7' in pathlib.Path('g.sh').read_text(encoding='utf-8')\n",
        encoding="utf-8",
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "base", cwd=repo)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()

    (repo / "g.sh").write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
    (repo / "a.ts").write_text("export const A = 1;\n", encoding="utf-8")
    _git("add", "g.sh", "a.ts", cwd=repo)

    # ★본판정 — `.ts` 변경이 통째로 빠졌는데 초록이면 안 된다.
    r = _run_tool(repo, base, "--max", "50")
    out = r.stdout + r.stderr
    audit = re.search(r"^::AUDIT=(.+)$", out, re.MULTILINE)
    assert audit, out
    fields = dict(kv.split("=", 1) for kv in audit.group(1).split())
    assert fields["scoped_out_files"] == "1", f"조용히 빠진 파일이 계수에 없다: {fields}"
    assert r.returncode == 3, f"범위 배제가 있는데 rc={r.returncode}\n{out}"

    # ★대조군 — **같은 저장소**에서 `.ts` 만 없애면 배제 0 · rc=0. 차가 0인 픽스처가 아니다.
    (repo / "a.ts").unlink()
    _git("rm", "-q", "--cached", "a.ts", cwd=repo)
    r2 = _run_tool(repo, base, "--max", "50")
    out2 = r2.stdout + r2.stderr
    a2 = re.search(r"^::AUDIT=(.+)$", out2, re.MULTILINE)
    assert a2 and "scoped_out_files=0" in a2.group(1), out2
    assert r2.returncode == 0, f"배제가 없는데 rc={r2.returncode}\n{out2}"
