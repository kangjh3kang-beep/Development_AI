"""`mutate_manual.sh` 의 **변이 후** 게이트 락 — 「변이 자신이 원인인 것」을 판정하지 않는다.

## 무엇이 결함이었나 (제보 `development-ai-88` · 재현 2026-09-03)

동료가 **도구를 실사용하다** 밟았다. `sed` 가 대상 파일의 구문을 깨면:

    구문 깬 변이 → "CAUGHT — 변이가 잡혔다(rc=2)"
    정상 변이    → "CAUGHT — 변이가 잡혔다(rc=1)"   ← **형태가 같아 사람이 구별 못 한다**

**테스트가 돌지도 않았는데 CAUGHT** 다 = 변이 점수 부풀림 = 「없는 락이 있다」고 믿게 된다.

★`#924` 의 **기준선** 게이트로는 **원리적으로 못 잡는다** — 기준선은 초록이었고
**원인이 변이 자신**이다. 「전」에 거는 판별은 「후」에도 같은 뜻을 갖는다.

## 두 번째 축 — 러너마다 「수집 0건」 신호가 다르다

동료 `development-ai-23` 실측: **vitest 에는 pytest `rc=5` 등가물이 없다.**
`-t` 필터가 아무것도 못 골라도 `4 passed | 4 skipped` 로 **조용히 rc=0** 이다.
→ `#924` 의 **개수 축**을 변이 후에도 대칭으로 건다.

## ★픽스처 규율 (`#924` 가 남긴 교훈)

가짜 러너(`bash -c "exit N"`)는 **출력이 없어** 개수 축을 통째로 우회한다 —
**실제 러너는 언제나 개수를 찍는다.** 그래서 이 파일의 가짜 러너도 **개수를 찍는다.**
그리고 구문 축은 **진짜 파일을 진짜로 깨서** 태운다(스텁으로 대신하지 않는다).
"""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[2] / "scripts" / "mutate_manual.sh"

# ★88 이 실제로 쓰는 스크레이퍼. **원문 그대로** 두 개를 태운다 —
#   「호환」은 두 모집단(구·신)으로만 증명된다.
_구_스크레이퍼 = r"grep -oE '^(CAUGHT|SURVIVED)' %s | tail -1"
_신_스크레이퍼 = r"grep -oE '^::VERDICT=[A-Z]+' %s | tail -1"


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    sh = lambda *a: subprocess.run(a, cwd=repo, check=True, capture_output=True)
    sh("git", "init", "-q")
    sh("git", "config", "user.email", "t@t")
    sh("git", "config", "user.name", "t")
    return repo, sh


def _긁기(out: str) -> tuple[str, str]:
    """구·신 스크레이퍼를 **같은 출력**에 적용한다.

    ★`${v:-?}` 에 해당하는 처리를 여기서 한다 — **빈 값을 `?` 로** 표시해야
      「판정 없음」과 「스크레이퍼 고장」이 구별된다(88 이 실제로 그 자리에서 헤맸다).
    """
    구 = [ln for ln in out.splitlines() if ln.startswith(("CAUGHT", "SURVIVED"))]
    신 = [ln for ln in out.splitlines() if ln.startswith("::VERDICT=")]
    return (구[-1].split(" ")[0] if 구 else "?"), (신[-1] if 신 else "?")


# ── ① 구문 파손 축 — **진짜 파일을 진짜로 깬다** ──────────────────────────────

def test_구문을_깬_변이는_CAUGHT_로_세지_않는다(tmp_path):
    """★이 파일이 존재하는 이유. 정답은 **판정 불가**이지 CAUGHT 가 아니다."""
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text('def f():\n    return "big"\n', encoding="utf-8")
    (repo / "test_mod.py").write_text(
        "from mod import f\ndef test_f(): assert f() == 'big'\n", encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    r = subprocess.run(
        ["bash", str(_TOOL), "mod.py", 's|return "big"|return "big|',
         "python3", "-m", "pytest", "test_mod.py", "-q"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    합 = r.stdout + r.stderr
    assert r.returncode == 16, f"구문 깬 변이를 판정했다: rc={r.returncode}\n{합}"
    구, 신 = _긁기(r.stdout)
    assert 구 == "?", f"구 스크레이퍼가 판정을 읽었다(구문 깨진 변이인데): {구}"
    assert 신 == "::VERDICT=UNDECIDED", f"신 토큰이 판정 불가가 아니다: {신}"
    assert "구문 검사" in 합, "구문 검사 결과를 출력하지 않는다(조용한 건너뜀 금지)"


def test_정상_변이는_그대로_판정한다(tmp_path):
    """★**두 번째 모집단** — 이것이 없으면 「전부 판정 불가」가 만점이 된다."""
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text("def f(x):\n    return x > 5\n", encoding="utf-8")
    (repo / "test_mod.py").write_text(
        "from mod import f\ndef test_f(): assert f(10) is True\n", encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    r = subprocess.run(
        ["bash", str(_TOOL), "mod.py", "s|x > 5|x > 999|",
         "python3", "-m", "pytest", "test_mod.py", "-q"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    합 = r.stdout + r.stderr
    assert r.returncode == 1, f"정상 변이를 판정하지 못했다: rc={r.returncode}\n{합}"
    구, 신 = _긁기(r.stdout)
    assert 구 == "CAUGHT", f"구 스크레이퍼 호환이 깨졌다: {구}"
    assert 신 == "::VERDICT=CAUGHT", f"신 토큰이 틀렸다: {신}"


# ── ② 개수 축 — 러너가 「빈 선택도 rc=0」일 때 ────────────────────────────────
#
# ★pytest 로는 이 분기에 **도달할 수 없다**(`-k` 가 0건이면 rc=5 라 기준선 게이트가 먼저 잡는다).
#   그래서 **개수를 찍는 가짜 러너**로 태운다 — vitest 의 «빈 선택도 rc=0» 을 재현한다.
#   ★`#924` 교훈: 출력이 없는 가짜 러너는 개수 축을 통째로 우회한다. 이 러너는 **찍는다.**

_러너 = r"""
import sys, pathlib
src = pathlib.Path("mod.py").read_text()
# 변이 전에는 2건 통과, 변이 후에는 **0건 통과인데 rc=0** (vitest 빈 선택 재현)
print("2 passed in 0.01s" if "MARKER" in src else "0 passed in 0.01s")
sys.exit(0)
"""


def test_통과_0건인데_rc0_이면_판정하지_않는다(tmp_path):
    """★vitest 축(`development-ai-23` 실측) — rc 만 보면 «전부 SURVIVED» 로 샌다."""
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text("MARKER = 1\n", encoding="utf-8")
    (repo / "runner.py").write_text(_러너, encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    r = subprocess.run(
        ["bash", str(_TOOL), "mod.py", "s|MARKER|GONE|", "python3", "runner.py"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    합 = r.stdout + r.stderr
    assert r.returncode == 16, f"통과 0건 + rc=0 을 SURVIVED 로 판정했다: rc={r.returncode}\n{합}"
    구, 신 = _긁기(r.stdout)
    assert 구 == "?", f"구 스크레이퍼가 판정을 읽었다: {구}"
    assert 신 == "::VERDICT=UNDECIDED", f"신 토큰이 판정 불가가 아니다: {신}"


def test_통과가_유지되면_정상_SURVIVED_다(tmp_path):
    """★**두 번째 모집단** — 개수 축이 정상 SURVIVED 를 막으면 그것도 결함이다."""
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text("MARKER = 1\n", encoding="utf-8")
    (repo / "runner.py").write_text(_러너, encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    # ★MARKER 를 **남기는** 변이 → 러너는 계속 "2 passed" → 정답은 SURVIVED
    r = subprocess.run(
        ["bash", str(_TOOL), "mod.py", "s|MARKER = 1|MARKER = 2|", "python3", "runner.py"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    합 = r.stdout + r.stderr
    assert r.returncode == 0, f"정상 SURVIVED 를 막았다: rc={r.returncode}\n{합}"
    구, 신 = _긁기(r.stdout)
    assert 구 == "SURVIVED", f"구 스크레이퍼 호환이 깨졌다: {구}"
    assert 신 == "::VERDICT=SURVIVED", f"신 토큰이 틀렸다: {신}"


# ── ③ 토큰과 rc 를 **짝으로** (88 지적) ──────────────────────────────────────

def test_판정불가_경로는_모두_토큰과_rc_가_짝을_이룬다(tmp_path):
    """★둘 중 하나만 바꾸면 **한쪽 소비자가 조용히 틀린다**.

    기준선 게이트(13)로 들어가는 경로에서도 신 토큰이 `UNDECIDED` 여야 한다.
    """
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text("VALUE = 5000\n", encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    e = dict(os.environ)
    e.setdefault("MUTATE_ALLOW_SHELL",
                 "픽스처가 rc 를 고정한다(마지막 명령이 exit N) — 토큰↔rc 짝을 시험한다")
    r = subprocess.run(
        ["bash", str(_TOOL), "mod.py", "s|5000|5_000|",
         "bash", "-c", f"printf '%s\\n' {shlex.quote('3 passed in 0.1s')}; exit 1"],
        cwd=repo, capture_output=True, text=True, env=e, check=False,
    )
    assert r.returncode == 13, f"빨간 기준선이 13 이 아니다: {r.returncode}\n{r.stdout}{r.stderr}"
    구, 신 = _긁기(r.stdout + r.stderr)
    assert 구 == "?", f"빨간 기준선인데 구 스크레이퍼가 판정을 읽었다: {구}"
    assert 신 == "::VERDICT=UNDECIDED", (
        f"판정 불가 경로에 토큰이 안 붙었다(rc={r.returncode}) — 토큰과 rc 가 짝이 아니다: {신}")


def test_판정어를_안내문에서_집지_않는다(tmp_path):
    """★`::VERDICT=` 는 **본문에 절대 안 쓰이는 형태**여야 한다.

    88 과 내가 **각각** 자기 설명문을 자기 검사기가 집는 사고를 냈다.
    도구의 안내문에는 `CAUGHT`/`SURVIVED` 가 여러 번 나오는데(그게 정상이다),
    **`::VERDICT=` 는 판정 줄에만** 나와야 한다.
    """
    본문 = _TOOL.read_text(encoding="utf-8")
    발행 = [ln for ln in 본문.splitlines()
            if "::VERDICT=" in ln and ln.strip().startswith("echo")]
    언급 = [ln for ln in 본문.splitlines()
            if "::VERDICT=" in ln and not ln.strip().startswith("echo")]
    # ★종전엔 `>= 4` 였다 — **손으로 고른 하한이 상한이 됐다.** 실제 발행은 6개라
    #   **두 개를 지워도 초록**이었고, 적대 리뷰가 그 둘(exit 14·15 경로)을 정확히 지웠다.
    # ★★그렇다고 «발행 수 == 예약 수 + 2» 도 틀렸다 — 12 와 16 은 **한 블록을 공유**한다.
    #   **소스 개수로는 이 성질을 표현할 수 없다.** 그래서 여기서는 «오염 없음»만 보고,
    #   «모든 경로가 토큰을 낸다»는 아래 `test_모든_판정불가_경로가_토큰을_낸다` 가
    #   **실행으로** 잠근다(행위 락이 소스 락보다 이 축에 맞다).
    assert len(발행) >= 3, f"판정 토큰 발행 지점이 너무 적다 — 추출기 의심: {len(발행)}"
    assert not 언급, (
        "안내문·주석에 `::VERDICT=` 가 있다 — 그 순간 이 토큰도 오염된다:\n"
        + "\n".join(언급))


def _예약_종료코드() -> set[str]:
    """도구가 **한 줄에서 선언한** 예약 코드 집합을 파생한다.

    ★손으로 세지 않는다 — 종전 락의 하한 4가 **상한이 되어** 두 경로가 무잠금이었다.
    """
    import re as _re

    본문 = _TOOL.read_text(encoding="utf-8")
    m = _re.search(r'^RESERVED_EXITS="([0-9 ]+)"', 본문, _re.MULTILINE)
    assert m, "도구가 `RESERVED_EXITS` 를 선언하지 않는다 — 파생 불가"
    코드 = set(m.group(1).split())
    assert len(코드) >= 4, f"예약 코드가 너무 적다 — 추출기 의심: {코드}"
    return 코드


def test_예약_종료코드는_문서와_구현이_일치한다() -> None:
    """★`CLAUDE.md` 가 선언하지 않은 예약 코드가 있으면 **비영 종료가 CAUGHT 로 오독**된다.

    종전 계약 테스트는 `"exit 10"`·`"exit 11"`·`"exit 12"` **세 문자열만** 요구했다 —
    목록형이라 **새 코드가 문서 없이 통과**했다(16 이 그 통로로 들어왔다).
    """
    repo = _TOOL.resolve().parents[1]
    doc = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    빠진 = sorted(c for c in _예약_종료코드() if f"exit {c}" not in doc)
    assert not 빠진, (
        f"`CLAUDE.md` 가 예약 코드를 선언하지 않는다: {빠진} — "
        "종료코드만 읽는 호출자가 그 값을 **판정으로 오독**한다")


def test_테스트가_예약코드를_내면_판정과_겹치지_않게_옮긴다(tmp_path):
    """★**파생형**으로 전수를 태운다 — 종전엔 12 만 옮겼고 13·14·15·16 은 충돌했다."""
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text("MARKER = 1\n", encoding="utf-8")
    (repo / "runner.py").write_text(
        "import sys, pathlib\n"
        'src = pathlib.Path("mod.py").read_text()\n'
        'print("3 passed in 0.01s")\n'
        'sys.exit(0 if "MARKER = 1" in src else int(sys.argv[1]))\n',
        encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    for 코드 in sorted(_예약_종료코드()):
        if 코드 == "5":
            continue
        r = subprocess.run(
            ["bash", str(_TOOL), "mod.py", "s|MARKER = 1|MARKER = 2|",
             "python3", "runner.py", 코드],
            cwd=repo, capture_output=True, text=True, check=False,
        )
        구, 신 = _긁기(r.stdout)
        assert 신 == "::VERDICT=CAUGHT", f"[rc={코드}] 판정이 CAUGHT 가 아니다: {신}"
        # ★구 스크레이퍼도 같은 판정을 읽어야 한다(호환은 두 모집단으로만 증명된다)
        assert 구 == "CAUGHT", f"[rc={코드}] 구 스크레이퍼 호환이 깨졌다: {구}"
        assert str(r.returncode) not in _예약_종료코드(), (
            f"[테스트 rc={코드}] 도구가 **예약 코드 {r.returncode}** 를 그대로 냈다 — "
            "진짜 CAUGHT 가 판정 불가로 오독된다")


def test_구문검사는_변이_전에도_잰다(tmp_path):
    """★**검사기가 원래 못 읽는 대상**과 **변이가 깬 것**을 가른다(적대 리뷰 CRITICAL-2).

    두 모집단을 같은 실행 형태로 태운다 — 이것이 없으면 「전부 판정 불가」가 만점이 된다.
    """
    repo, sh = _repo(tmp_path)
    # ★변이 전에도 bash -n 이 실패하는 파일 → **축을 끄고 정상 판정**해야 한다
    (repo / "bad.sh").write_text(
        "#!/bin/bash\nVAL=1\nif [[ $VAL -eq 1 ; then :; fi\n", encoding="utf-8")
    (repo / "test_bad.py").write_text(
        "import subprocess\n"
        'def test_x(): assert subprocess.run(["grep","-q","VAL=1","bad.sh"]).returncode == 0\n',
        encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    r = subprocess.run(
        ["bash", str(_TOOL), "bad.sh", "s|VAL=1|VAL=2|",
         "python3", "-m", "pytest", "test_bad.py", "-q"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    합 = r.stdout + r.stderr
    assert "축을 끈다" in 합, f"변이 전에도 실패했는데 축을 안 껐다:\n{합}"
    assert r.returncode != 16, f"검사기가 못 읽는 대상을 「변이가 깼다」로 판정했다: rc={r.returncode}"
    구, 신 = _긁기(r.stdout)
    assert 신 in ("::VERDICT=CAUGHT", "::VERDICT=SURVIVED"), f"정상 판정이 안 나왔다: {신}"
    # ★축을 껐어도 **판정은 나와야** 한다 — 구 스크레이퍼가 빈 값이면 그 자체가 회귀다
    assert 구 in ("CAUGHT", "SURVIVED"), f"축을 껐는데 구 스크레이퍼가 판정을 못 읽었다: {구}"


def test_기준선을_건너뛰어도_개수_축은_산다(tmp_path):
    """★`MUTATE_SKIP_BASELINE` 에서 **같은 입력이 정반대 판정**으로 뒤집혔다(리뷰 HIGH-1)."""
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text("MARKER = 1\n", encoding="utf-8")
    (repo / "runner.py").write_text(_러너, encoding="utf-8")
    (repo / "nocount.py").write_text("import sys\nprint('done')\nsys.exit(0)\n", encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    e = dict(os.environ, MUTATE_SKIP_BASELINE="락이 기준선 없이도 축이 사는지 시험한다")
    r = subprocess.run(
        ["bash", str(_TOOL), "mod.py", "s|MARKER|GONE|", "python3", "runner.py"],
        cwd=repo, capture_output=True, text=True, env=e, check=False,
    )
    _, 신 = _긁기(r.stdout)
    assert 신 == "::VERDICT=UNDECIDED", f"기준선을 건너뛰자 축이 꺼졌다: {신} (rc={r.returncode})"
    # ★**두 번째 모집단** — 개수를 **안 찍는** 러너까지 막으면 그것도 결함이다
    r2 = subprocess.run(
        ["bash", str(_TOOL), "mod.py", "s|MARKER|GONE|", "python3", "nocount.py"],
        cwd=repo, capture_output=True, text=True, env=e, check=False,
    )
    _, 신2 = _긁기(r2.stdout)
    assert 신2 == "::VERDICT=SURVIVED", (
        f"개수를 안 찍는 러너까지 막았다(위양성): {신2} (rc={r2.returncode})")


def _판정불가_유발(repo, sh, 코드: str, env=None):
    """예약 코드 `코드` 경로를 **실제로 유발**한다. (경로마다 조건이 다르다)"""
    (repo / "mod.py").write_text("MARKER = 1\n", encoding="utf-8")
    if 코드 == "16":   # 변이가 구문을 깬다
        (repo / "mod.py").write_text('V = "x"\n', encoding="utf-8")
        (repo / "t.py").write_text("from mod import V\ndef test_v(): assert V == 'x'\n",
                                   encoding="utf-8")
        argv, sedx, tgt = ["python3", "-m", "pytest", "t.py", "-q"], 's|V = "x"|V = "x|', "mod.py"
    elif 코드 == "12":  # 셸 래퍼라 rc 를 못 믿는다
        (repo / "t.py").write_text("from mod import MARKER\ndef test_m(): assert MARKER == 1\n",
                                   encoding="utf-8")
        argv, sedx, tgt = ["bash", "-c", "python3 -m pytest t.py -q; true"], "s|1|2|", "mod.py"
    elif 코드 == "14":  # 기준선에서 수집 0건(pytest rc=5)
        (repo / "t.py").write_text("def test_m(): assert True\n", encoding="utf-8")
        argv, sedx, tgt = ["python3", "-m", "pytest", "t.py", "-q", "-k", "zzz_none"], "s|1|2|", "mod.py"
    elif 코드 == "13":  # 기준선이 이미 빨갛다
        (repo / "t.py").write_text("def test_m(): assert False\n", encoding="utf-8")
        argv, sedx, tgt = ["python3", "-m", "pytest", "t.py", "-q"], "s|1|2|", "mod.py"
    else:              # 15: 기준선 rc=0 인데 통과 0건
        (repo / "runner15.py").write_text(
            "import sys\nprint('0 passed in 0.01s')\nsys.exit(0)\n", encoding="utf-8")
        argv, sedx, tgt = ["python3", "runner15.py"], "s|1|2|", "mod.py"
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", f"case{코드}")
    return subprocess.run(
        ["bash", str(_TOOL), tgt, sedx, *argv],
        cwd=repo, capture_output=True, text=True,
        env=dict(os.environ, **(env or {})), check=False,
    )


def test_모든_판정불가_경로가_토큰을_낸다(tmp_path):
    """★**행위 락** — 「5경로 전부 짝지었다」는 선언을 실행으로 태운다.

    종전 락은 **소스 개수 하한**이라 두 경로(14·15)의 토큰을 지워도 초록이었다
    (적대 리뷰 M7·M8 이 정확히 그 둘을 지웠다). 소스 개수로는 «12 와 16 이 한 블록을
    공유한다» 를 표현할 수 없으므로, **각 경로를 실제로 유발**해서 본다.
    """
    미달 = []
    for 코드 in sorted(_예약_종료코드()):
        repo, sh = _repo(tmp_path / f"c{코드}")
        r = _판정불가_유발(repo, sh, 코드)
        _, 신 = _긁기(r.stdout + r.stderr)
        if str(r.returncode) != 코드 or 신 != "::VERDICT=UNDECIDED":
            미달.append(f"exit {코드}: 실제 rc={r.returncode} 토큰={신}")
    assert not 미달, "판정 불가 경로가 토큰·rc 짝을 안 이룬다:\n  " + "\n  ".join(미달)
