"""`safe-deploy.sh` 가 **「기계가 틀렸다」와 「경로가 틀렸다」를 가르는지** 잠근다.

## 왜 (실측 2026-09-12 · 사고 직전까지 갔다)

종전 스크립트는 한 줄이었다::

    cd "$REPO" || { status "FAIL cd-repo"; exit 1; }

이 **한 문구**가 서로 다른 두 사건을 같은 모양으로 냈다:

==========================  ============================================
㉠ 경로 상수가 틀렸다        상수를 고치는 것이 옳다
㉡ **여기가 A1 이 아니다**   상수를 고치면 **프로덕션이 깨진다**
==========================  ============================================

★실증: 통합자 세션이 개발 워크트리에서 돌려 ㉡ 을 만났고 **그것을 정확히 그렇게 적었다**
(*"그 스크립트는 158 에서 도는 것입니다"* — 원문은 옳다). 그런데 그 진술이 **자동 요약을
거치며 뒤집혀** *"Path Resolution Error — Hardcoded ``$HOME/Development_AI`` vs My_Projects"*
라는 라벨로 인계됐고, **세 세션이 그 뒤집힌 라벨 위에서 각자 판단했다.**
그 라벨대로 고쳤다면 A1 에서 ``FAIL cd-repo`` 가 나서 **배포가 영구히 막혔을 것**이다.

⇒ ***옳게 쓴 사람의 진술조차, 실패 문구가 모호하면 요약 한 단계에서 뒤집힌다.***
  고칠 것은 사람이 아니라 **문구**다.

A1 실측(2026-09-12)::

    ubuntu@A1: ls -d $HOME/Development_AI              → /home/ubuntu/Development_AI  (실재)
    ubuntu@A1: ls -d $HOME/My_Projects/Development_AI  → No such file or directory

⇒ **경로 상수는 옳다.** 틀린 것은 **문구**였다.
★그리고 그 값은 **호스트 의존**이다(동료 4e 실측: 개발 머신은 정반대). 어느 한쪽 리터럴로
「고치면」 **반대쪽이 영구히 막힌다** — 그래서 아래 락은 상수를 **양방향으로** 못 박는다.
***사유가 넷인데 문구가 하나면 사람을 틀린 곳으로 보낸다.***

## 이 락이 지키는 것

1. **탐지** — A1 이 아닌 곳에서 돌리면 전용 종료코드(8)와 `wrong-host` 상태를 낸다.
2. **특이도** — A1 처럼 보이는 곳에서는 이 가드가 **발화하지 않는다**(위양성도 결함이다).
3. **경로 상수 불변** — 누군가 「고치려」 하면 여기서 빨개진다. ★이것이 핵심이다.
4. **안내가 실제로 말린다** — 문구가 「고치지 마라」를 담는지.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "propai-platform" / "scripts" / "safe-deploy.sh"


def _run(home: str, cwd: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HOME"] = home
    # 상태 파일이 전역 경로(/tmp)라 다른 세션과 겹치지 않게 격리한다.
    return subprocess.run(
        ["bash", str(SCRIPT), "web"],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )


def test_script_exists_and_parses() -> None:
    """[조회기 생존] 대상 파일이 실재하고 문법이 옳다 — 아니면 아래 전부가 공허하다."""
    assert SCRIPT.is_file(), f"{SCRIPT} 가 없다 — 경로가 낡았다"
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


#: A1 저장소 경로 선언의 **허용된 두 모양**. 값은 하나뿐이고, 기본값 형태만 다르다.
#: ``REPO="$HOME/Development_AI"``  /  ``REPO="${REPO:-$HOME/Development_AI}"``
_REPO_DECL = re.compile(r'^REPO(?:_DIR)?="(?:\$\{[A-Z_]+:-)?(\$HOME/[^"}]+)\}?"', re.M)

#: A1 의 저장소 루트. ★이 리터럴을 **양방향으로** 못 박는다 — 이 값은 **호스트 의존**이라
#: 어느 쪽(A1 / 개발 머신)으로 고쳐도 반대쪽이 영구히 막힌다.
A1_REPO_ROOT = "$HOME/Development_AI"

#: 가드 전용 종료코드. ★**소스에서 파생**한다 — 여기에 숫자를 손으로 적으면 그 사본이
#: 프로덕션과 갈리고, 그때 이 락은 «자기 상수를 자기 자신과 비교»하는 장식이 된다.
def _guard_exit_code() -> int:
    lib = (REPO_ROOT / "propai-platform/scripts/lib/assert-a1-host.sh").read_text(encoding="utf-8")
    m = re.findall(r"^\s*exit (\d+)", lib, re.M)
    assert len(m) == 1, f"가드의 exit 코드가 {len(m)}개다 — 유일해야 한다: {m}"
    return int(m[0])


GUARD_EXIT = _guard_exit_code()


def test_repo_constant_is_the_a1_path() -> None:
    """★★**경로 상수를 고치지 못하게 한다** — 이 락의 존재 이유다.

    ★★2026-09-12 R1(독립 리뷰 MAJOR-2) — **초판은 `safe-deploy.sh` 한 파일만 봤다.**
    형제 ``rollback-web.sh`` 는 ``REPO="${REPO:-$HOME/Development_AI}"`` 형태라
    초판 정규식 ``^REPO="([^"]+)"`` 이 **기본값 표현식 통째로** 잡아 비교가 무의미했고,
    애초에 **그 파일을 읽지도 않았다**. 즉 ***더 위험한 쪽***(장애 중에 집는 스크립트)이
    **무잠금**이었다. ***손으로 고른 파일 하나는 곧 상한이 된다.***

    → 모집단을 **파생**하고, 선언의 **두 모양**을 다 받는다.
    """
    scripts = _a1_repo_scripts()
    assert scripts, "모집단이 비었다 — 조회기가 죽었다"
    checked, bad = 0, []
    for rel in scripts:
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        m = _REPO_DECL.search(src)
        if m is None:
            continue  # 선언 없이 문자열만 언급하는 파일(아래 공허 가드가 수를 지킨다)
        checked += 1
        # ★불변식은 「같다」가 아니라 **「A1 루트에 뿌리내린다」**이다.
        #   `REPO_DIR="$HOME/Development_AI/propai-platform"` 은 **정당한 다른 변수**다
        #   (저장소 루트가 아니라 compose 디렉토리를 가리킨다). 「같다」로 걸면 **위양성**이고,
        #   ★위양성도 결함이다 — 정상 코드를 막는 락은 곧 꺼진다.
        declared = m.group(1)
        if declared != A1_REPO_ROOT and not declared.startswith(A1_REPO_ROOT + "/"):
            bad.append(f"{rel}: {declared!r}")
    # 공허 진리 가드 — 선언을 하나도 못 찾으면 「위반 0」이 무의미하다.
    assert checked >= 3, f"선언을 {checked}건만 파싱했다(실측 하한 3) — 정규식이 낡았다: {scripts}"
    assert not bad, (
        "A1 저장소 경로 상수가 바뀌었다. 그 값은 **호스트 의존**이라 어느 쪽으로 고쳐도 "
        f"반대쪽이 영구히 막힌다:\n" + "\n".join(bad)
    )


def test_constant_lock_sees_both_declaration_shapes() -> None:
    """[판별력] 정규식이 **두 모양을 다 읽는다** — 한쪽만 읽으면 다른 쪽이 무잠금이다.

    ★초판이 정확히 그래서 뚫렸다. 픽스처로 **양쪽을 실제로 태운다**(모집단 하나 금지).
    """
    plain = _REPO_DECL.search('REPO="$HOME/Development_AI"\n')
    defaulted = _REPO_DECL.search('REPO="${REPO:-$HOME/Development_AI}"\n')
    assert plain and plain.group(1) == A1_REPO_ROOT, "직접 선언형을 못 읽는다"
    assert defaulted and defaulted.group(1) == A1_REPO_ROOT, "기본값 선언형을 못 읽는다"
    # 음성 대조 — 개발 머신 경로는 **위반으로 잡혀야** 한다(안 잡히면 락이 장식이다).
    wrong = _REPO_DECL.search('REPO="${REPO:-$HOME/My_Projects/Development_AI}"\n')
    assert wrong and wrong.group(1) != A1_REPO_ROOT, "틀린 경로가 통과한다"

    # ★「뿌리내림」 판정의 두 모집단을 갈라 태운다 — 한쪽만 보면 위양성/위음성이 남는다.
    def rooted(v: str) -> bool:
        return v == A1_REPO_ROOT or v.startswith(A1_REPO_ROOT + "/")

    assert rooted("$HOME/Development_AI"), "루트 자신이 위반으로 잡힌다"
    assert rooted("$HOME/Development_AI/propai-platform"), (
        "하위 디렉토리를 가리키는 정당한 변수가 위반으로 잡힌다 — 위양성도 결함이다"
    )
    assert not rooted("$HOME/My_Projects/Development_AI"), "개발 머신 경로가 통과한다"
    # ★접두사 함정 — 이름이 비슷한 **다른** 디렉토리가 통과하면 안 된다.
    assert not rooted("$HOME/Development_AI_bizfooter"), (
        "접두사만 같은 다른 저장소가 통과한다 — `/` 경계를 안 본 것이다"
    )


def test_detects_wrong_host_with_dedicated_code(tmp_path: Path) -> None:
    """★탐지 — A1 이 아닌 곳에서는 전용 종료코드와 `wrong-host` 상태를 낸다."""
    home = tmp_path / "home"
    (home / "My_Projects" / "Development_AI").mkdir(parents=True)
    r = _run(str(home), str(REPO_ROOT))
    assert r.returncode == GUARD_EXIT, f"기대 {GUARD_EXIT}, 실제 {r.returncode}\nstderr={r.stderr[:400]}"
    assert "wrong-checkout" in Path("/tmp/deploy_status.txt").read_text(encoding="utf-8")


def test_guidance_actually_discourages_editing_the_constant(tmp_path: Path) -> None:
    """★안내가 **말리는가** — 「기계가 틀렸다」만 말하고 끝나면 다음 사람이 또 상수를 고친다.

    ★산문 전체를 단언하지 않는다(다듬을 때마다 깨지는 취약한 락이 된다). **두 명제**만 본다:
    ①상수를 고치지 말라고 말한다 ②A1 에서 실행하라고 말한다.
    """
    home = tmp_path / "home"
    (home / "My_Projects" / "Development_AI").mkdir(parents=True)
    r = _run(str(home), str(REPO_ROOT))
    assert "고치지" in r.stderr, "「고치지 마라」가 없다 — 안내가 다음 사람을 안 말린다"
    assert "A1" in r.stderr, "어디서 돌려야 하는지를 안 말한다"


def test_specificity_does_not_fire_on_an_a1_like_host(tmp_path: Path) -> None:
    """★특이도 — A1 처럼 보이면 이 가드는 **발화하지 않는다**(위양성도 결함이다).

    ★「exit != 8」만 보면 「아무것도 안 하는 가드」도 만족한다. 그래서 **상태 파일이
    wrong-host 가 아닌 다른 사건**을 가리키는지까지 본다(가드를 지나 뒤 단계로 갔다는 뜻).
    """
    home = tmp_path / "home"
    (home / "Development_AI" / "propai-platform").mkdir(parents=True)
    r = _run(str(home), str(home))
    assert r.returncode != GUARD_EXIT, "A1 처럼 보이는데 막았다 — 위양성"
    status = Path("/tmp/deploy_status.txt").read_text(encoding="utf-8")
    assert "wrong-checkout" not in status, f"상태가 여전히 wrong-checkout 다: {status!r}"


def test_marker_less_host_is_not_called_a1(tmp_path: Path) -> None:
    """★★**부재로부터 A1 을 유도하지 않는다**(독립 리뷰 MAJOR-1 의 잠금).

    초판은 개발 표식이 **없으면** 「그러므로 A1」로 유도해, 표식이 둘 다 없는 기계에서
    *"★중단 — **A1 로 보이는데** …"* 를 냈다. **A1 인지 한 번도 재지 않고** 말한 것이다.
    ⇒ 이제는 **양쪽을 재서 비교**한다. 이 테스트가 그 유도를 다시 못 하게 막는다.
    """
    home = tmp_path / "home"
    home.mkdir()  # 표식 없음: A1 경로도, 개발 중첩 경로도 없다
    r = _run(str(home), str(home))
    assert r.returncode == GUARD_EXIT, f"기대 {GUARD_EXIT}, 실제 {r.returncode}"
    assert "A1 로 보이는데" not in r.stderr, (
        "표식이 없을 뿐인데 「A1 로 보인다」고 단정한다 — 부재로부터 유도하고 있다"
    )
    # ★양쪽 **관측값**이 실제로 실려 있어야 한다(둘 다 없으면 사람이 판단할 수 없다).
    assert str(home) in r.stderr, "기대한 $REPO 를 안 보여 준다"
    assert str(REPO_ROOT) in r.stderr, "지금 실행 중인 저장소를 안 보여 준다"


def test_status_names_the_measured_event(tmp_path: Path) -> None:
    """★상태 문구가 **잰 것**을 말한다 — 「호스트」라고 단정하지 않는다(잰 것은 체크아웃이다)."""
    home = tmp_path / "home"
    (home / "My_Projects" / "Development_AI").mkdir(parents=True)
    _run(str(home), str(REPO_ROOT))
    status = Path("/tmp/deploy_status.txt").read_text(encoding="utf-8")
    assert "wrong-checkout" in status, f"상태가 잰 것을 말하지 않는다: {status!r}"


# ─────────────────────────────────────────────────────────────────────────────
# ★파생형 — **새 스크립트가 자동으로 감시망에 들어온다**
#
# 위 락들은 `safe-deploy.sh` 한 파일만 본다. 그런데 형제 스윕(2026-09-12)에서 같은 경로
# 상수를 쓰는 스크립트가 **셋 더** 나왔고, 그중 `rollback-web.sh` 는 같은 모호한 실패를
# 갖고 있었다(게다가 **장애 중에 집는** 스크립트라 더 위험하다).
#
# ***손으로 센 목록은 곧 상한이 된다.*** 그래서 모집단을 **파일에서 파생**한다:
#   「A1 저장소 경로를 쓰는 셸 스크립트」는 전부 가드를 갖거나, **사유와 함께 면제**돼야 한다.
# ─────────────────────────────────────────────────────────────────────────────

#: 면제 — **사유를 적는다**(부채를 초록 안에 보이게). 죽은 면제는 아래 테스트가 실패시킨다.
A1_GUARD_EXEMPT = {
    "propai-platform/scripts/a1-arq-worker.sh":
        "★2026-09-12 R2 정정 — 종전 사유의 «헤더가 A1 을 명시한다(실측 2건)» 는 **거짓**이었다. "
        "다시 재니 대문자 `A1` 은 **0건**이고, 내 스윕이 `grep -ciE` 로 대소문자·대안을 섞어 "
        "`a1-`(파일명)을 A1 언급으로 센 것이었다. **실제 근거는 다르다**: 헤더의 「환경변수」 "
        "절이 `REPO_DIR` 을 **재정의 가능**하다고 명문화했고 소스도 `${REPO_DIR:-…}` 형태라, "
        "경로가 안 맞으면 **상수를 고치는 대신 환경변수를 주는 길**이 이미 열려 있다.",
    "propai-platform/scripts/a1-backend-workers.sh":
        "★2026-09-12 R2 정정 — 종전 사유(`cd` 에 `||` 가드가 없어 **조용히 실패**한다)는 "
        "**틀렸다**. 실측: 3행이 `set -euo pipefail` 이라 `-e` 가 있고, `cd` 실패는 조용하지 "
        "않고 **즉시 rc=1 로 죽으며 진짜 원인을 이름 짓는다**(대조군: `-e` 를 빼면 흘러가서 "
        "`ERROR: .env not found` 라는 **틀린 원인**을 말한다 — 내가 우려한 모양은 그쪽이다). "
        "면제는 유지하되 사유를 **측정된 것**으로 바꾼다. ★`a1-` 접두 + 헤더 A1 언급 1건.",
}


def _a1_repo_scripts() -> list[str]:
    """A1 저장소 경로를 쓰는 셸 스크립트를 **파일에서 파생**한다."""
    out = subprocess.run(
        ["git", "ls-files", "*.sh"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    hits = []
    for rel in out:
        if "/tests/" in rel or "/lib/" in rel:
            continue
        try:
            src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "$HOME/Development_AI" in src:
            hits.append(rel)
    return sorted(hits)


def test_population_is_alive() -> None:
    """[공허 진리 가드] 모집단을 실제로 모았다 — 0건이면 아래 판정이 무의미하다."""
    scripts = _a1_repo_scripts()
    assert len(scripts) >= 3, f"수집 {len(scripts)}건 — 조회기가 죽었다: {scripts}"
    assert "propai-platform/scripts/safe-deploy.sh" in scripts, "대조군이 빠졌다"


def test_every_a1_script_guards_or_is_exempt_with_a_reason() -> None:
    """★A1 경로를 쓰는 스크립트는 **가드를 갖거나 사유와 함께 면제**돼야 한다."""
    missing = []
    for rel in _a1_repo_scripts():
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if "assert_a1_host" in src or rel in A1_GUARD_EXEMPT:
            continue
        missing.append(rel)
    assert not missing, (
        "A1 경로를 쓰는데 가드도 사유도 없다 — 「기계가 틀렸다」가 "
        f"「경로가 틀렸다」로 읽힌다:\n" + "\n".join(missing)
    )


def test_exemptions_are_alive_and_reasoned() -> None:
    """★죽은 면제를 남기지 않는다 — 고쳐졌는데 면제가 남으면 다음 사람이 「끝났다」고 읽는다."""
    scripts = set(_a1_repo_scripts())
    for rel, reason in A1_GUARD_EXEMPT.items():
        assert rel in scripts, f"{rel} 는 더는 A1 경로를 쓰지 않는다 — 면제를 지워라"
        assert len(reason) > 40, f"{rel} 의 사유가 너무 짧다"
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "assert_a1_host" not in src, f"{rel} 는 이미 가드를 갖는다 — 면제를 지워라"


def test_shared_helper_is_used_not_copied() -> None:
    """★블록을 복붙하지 않았다 — 복붙하면 한쪽만 고쳐지는 발산이 생긴다.

    가드를 가진 스크립트는 **전부 공용 함수를 source** 해야 한다(자기 안에 조건을 복제하지 않는다).
    """
    users = [r for r in _a1_repo_scripts() if "assert_a1_host" in (REPO_ROOT / r).read_text(encoding="utf-8")]
    assert len(users) >= 2, f"공용 함수 사용처가 {len(users)}건 — 형제에 안 퍼졌다: {users}"
    for rel in users:
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "lib/assert-a1-host.sh" in src, f"{rel} 가 공용 함수를 source 하지 않는다(복제했나)"



def test_guard_exit_code_is_unique_in_every_caller() -> None:
    """★★**종료코드가 사건마다 유일해야 한다** — 기계는 rc 만 본다(독립 리뷰 MAJOR-A).

    초판 가드는 `exit 8` 이었는데 `safe-deploy.sh:93` 이 **이미** 그 코드를 쓰고 있었다::

        status "ABORT prune-진행중 — 잠시 후 재시도"; exit 8

    **두 사건의 다음 행동이 정반대다** — 「기다렸다 재시도」 vs 「재시도해도 영원히 실패」.
    권장 실행법이 ``setsid … >/dev/null 2>&1 &`` 라 **문구를 아무도 안 본다**.
    ⇒ ***이 PR 의 명제를 rc 축에서 그대로 반복한 것이다*** — 매체만 문구에서 종료코드로 바뀌었다.
    """
    lib = (REPO_ROOT / "propai-platform/scripts/lib/assert-a1-host.sh").read_text(encoding="utf-8")
    codes = re.findall(r"^\s*exit (\d+)", lib, re.M)
    assert codes, "가드의 exit 코드를 못 찾았다 — 조회기가 죽었다"
    guard_codes = set(codes)
    assert str(GUARD_EXIT) in guard_codes, "파생 상수와 소스가 갈렸다"

    users = [r for r in _a1_repo_scripts() if "assert_a1_host" in (REPO_ROOT / r).read_text(encoding="utf-8")]
    assert len(users) >= 2, f"사용처가 {len(users)}건 — 공허하다"
    for rel in users:
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        # 그 스크립트 **자신이** 쓰는 종료코드(가드 source 줄은 제외한다)
        own = set(re.findall(r"(?<!guard-lib-missing\n)^\s*(?:[^#\n]*;\s*)?exit (\d+)", src, re.M))
        own.discard("12")  # 가드 라이브러리 부재 — 이 PR 이 도입한 전용 코드
        clash = guard_codes & own
        assert not clash, (
            f"{rel}: 가드 종료코드 {sorted(clash)} 가 그 스크립트의 **다른 사건**과 겹친다. "
            "기계는 rc 만 보므로 두 사건이 구별되지 않는다."
        )


def test_guard_library_absence_is_not_fail_open() -> None:
    """★★가드가 **자기 의존에 fail-open** 이면 안 된다(독립 리뷰 MAJOR-B).

    두 스크립트에 ``set -e`` 가 없어, ``.`` source 실패가 그냥 흘러가
    ``cd "$REPO"`` 로 도달해 **``FAIL cd-repo``** 를 냈다 — ***이 PR 이 없애려는 그 문구다.***
    """
    for rel in ["propai-platform/scripts/safe-deploy.sh", "propai-platform/scripts/rollback-web.sh"]:
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "if ! . " in src, f"{rel}: source 실패를 검사하지 않는다(fail-open)"
        assert "guard-lib" in src or "exit 12" in src, f"{rel}: source 실패에 전용 처리가 없다"



def test_exemption_premises_are_true_not_just_written() -> None:
    """★★면제 사유가 **기대는 사실**을 잠근다 — 문구가 아니라 전제를.

    2026-09-12 R2: `a1-backend-workers.sh` 면제 사유가 *"`cd` 실패가 **조용하다**"* 였는데
    **거짓**이었다(3행이 ``set -euo pipefail``). 독립 리뷰가 잡았다.

    ★산문을 단언하면 다듬을 때마다 깨지는 **취약한 락**이 된다(저장소 §C-30). 그래서
    **문구가 아니라 전제**를 잰다 — 그 전제가 뒤집히면 사유도 뒤집혀야 하므로 여기서 빨개진다.
    ★변이 M11(사유 문구를 되돌림)이 SURVIVED 한 것은 **구멍이 아니다**: 그 축은 의도적으로
    안 잠갔고, 대신 아래가 **그 사유를 참으로 만드는 조건**을 잠근다.
    """
    #: 각 면제가 기대는 **측정 가능한 전제**. 사유를 바꿀 거면 이 전제부터 다시 재라.
    premises = {
        # `-e` 가 있으므로 cd 실패가 즉시·구체적으로 죽는다 → 별도 가드 불필요
        "propai-platform/scripts/a1-backend-workers.sh": ("set -euo pipefail", True),
        # 상수를 고치지 않고 **환경변수로 덮는 길**이 문서화돼 있다 → 오인해도 상수를 안 건드린다
        "propai-platform/scripts/a1-arq-worker.sh": ("${REPO_DIR:-", True),
    }
    for rel, (needle, expected) in premises.items():
        assert rel in A1_GUARD_EXEMPT, f"{rel} 는 면제 목록에 없다 — 전제표가 낡았다"
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert (needle in src) is expected, (
            f"{rel}: 면제 사유가 기대는 전제({needle!r})가 더는 참이 아니다 — "
            "사유를 다시 재고 고쳐라(면제가 거짓 위에 서 있다)"
        )
    # [판별력] 전제 검사가 실제로 갈라야 한다 — 아무 파일이나 통과하면 장식이다.
    other = (REPO_ROOT / "propai-platform/scripts/safe-deploy.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" not in other, (
        "대조군이 죽었다 — safe-deploy.sh 도 `-e` 를 갖게 됐다면 이 판별식은 무의미하다"
    )
