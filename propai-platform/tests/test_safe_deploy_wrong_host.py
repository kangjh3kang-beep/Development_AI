"""`safe-deploy.sh` 가 **「기계가 틀렸다」와 「경로가 틀렸다」를 가르는지** 잠근다.

## 왜 (실측 2026-09-12 · 사고 직전까지 갔다)

종전 스크립트는 한 줄이었다::

    cd "$REPO" || { status "FAIL cd-repo"; exit 1; }

이 **한 문구**가 서로 다른 두 사건을 같은 모양으로 냈다:

==========================  ============================================
㉠ 경로 상수가 틀렸다        상수를 고치는 것이 옳다
㉡ **여기가 A1 이 아니다**   상수를 고치면 **프로덕션이 깨진다**
==========================  ============================================

★실증: 동료 세션이 개발 워크트리에서 돌려 ㉡ 을 만났고, 그것을 ㉠ 으로 읽어
*"Hardcoded ``$HOME/Development_AI`` vs Actual My_Projects Nested Path"* 를
**결함으로 인계**했다. 그 수정을 적용했다면 A1 에서 ``FAIL cd-repo`` 가 나서
**배포가 영구히 막혔을 것**이다.

A1 실측(2026-09-12)::

    ubuntu@A1: ls -d $HOME/Development_AI              → /home/ubuntu/Development_AI  (실재)
    ubuntu@A1: ls -d $HOME/My_Projects/Development_AI  → No such file or directory

⇒ **경로 상수는 옳다.** 틀린 것은 **문구**였다.
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


def test_repo_constant_is_the_a1_path() -> None:
    """★★**경로 상수를 고치지 못하게 한다** — 이 락의 존재 이유다.

    A1 에 실재하는 경로는 ``$HOME/Development_AI`` 다. 개발 워크트리의 중첩 경로로
    바꾸면 A1 에서 ``FAIL cd-repo`` 가 나서 배포가 영구히 막힌다.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r'^REPO="([^"]+)"', src, re.M)
    assert m, "REPO 선언을 못 찾았다 — 조회기가 죽었다(이름이 바뀌었나)"
    assert m.group(1) == "$HOME/Development_AI", (
        f"REPO 가 {m.group(1)!r} 로 바뀌었다. A1 에는 그 경로가 없다 — "
        "개발 워크트리에서 본 중첩 경로를 여기 적으면 프로덕션 배포가 막힌다."
    )


def test_detects_wrong_host_with_dedicated_code(tmp_path: Path) -> None:
    """★탐지 — A1 이 아닌 곳에서는 전용 종료코드와 `wrong-host` 상태를 낸다."""
    home = tmp_path / "home"
    (home / "My_Projects" / "Development_AI").mkdir(parents=True)
    r = _run(str(home), str(REPO_ROOT))
    assert r.returncode == 8, f"기대 8, 실제 {r.returncode}\nstderr={r.stderr[:400]}"
    assert "wrong-host" in Path("/tmp/deploy_status.txt").read_text(encoding="utf-8")


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
    assert r.returncode != 8, "A1 처럼 보이는데 wrong-host 로 막았다 — 위양성"
    status = Path("/tmp/deploy_status.txt").read_text(encoding="utf-8")
    assert "wrong-host" not in status, f"상태가 여전히 wrong-host 다: {status!r}"


def test_a1_with_missing_repo_is_a_different_event(tmp_path: Path) -> None:
    """★두 사건이 **다른 이름**을 갖는다 — 같은 이름이면 애초의 결함이 그대로다."""
    home = tmp_path / "home"
    home.mkdir()  # A1 도 아니고 중첩 경로도 없다 → 「진짜 경로 없음」
    r = _run(str(home), str(home))
    status = Path("/tmp/deploy_status.txt").read_text(encoding="utf-8")
    assert "wrong-host" not in status
    assert "repo-missing" in status, f"경로 부재가 따로 표시되지 않는다: {status!r}"


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
        "파일명이 `a1-` 접두로 기계를 스스로 말하고 헤더도 A1 을 명시한다. 또 REPO_DIR 이 "
        "환경변수로 덮이도록 돼 있어 경로 상수를 고칠 동기 자체가 약하다(실측: 헤더 A1 언급 2건).",
    "propai-platform/scripts/a1-backend-workers.sh":
        "같은 이유 — `a1-` 접두 + 헤더 A1 언급. ★단 `cd \"$REPO_DIR\"` 에 `||` 가드가 아예 "
        "없어 실패가 조용하다. 별건으로 상환한다(이 PR 은 실증된 두 자리만 고친다).",
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
