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

# ★★**지어낸 상수가 결함을 비껴갔다**(적대 리뷰 2차 CRITICAL-1).
#   나는 빈 선택 출력을 `"0 passed"` 라고 **지어냈는데**, 진짜 vitest 는 `passed` 를
#   **한 번도 안 찍는다**. 그 실측은 `#924` 가 이미 해 뒀고
#   (*"빈 선택 출력에 `N passed` 가 있나 → **관측 0건**"*),
#   **문자열까지 형제 락 `test_mutate_manual_baseline_gate.py:208` 에 들어 있었다.**
#   → 그 실측값을 **그대로 가져다 쓴다.** 형제를 먼저 보라(CLAUDE.md §29).
_VITEST_GREEN = " Test Files  1 passed (1)\n      Tests  15 passed (15)"
_VITEST_ALL_SKIPPED = " Test Files  1 skipped (1)\n      Tests  15 skipped (15)"
_러너 = (
    "import sys, pathlib\n"
    'src = pathlib.Path("mod.py").read_text()\n'
    f'print({_VITEST_GREEN!r} if "MARKER" in src else {_VITEST_ALL_SKIPPED!r})\n'
    "sys.exit(0)\n"
)


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
    # ★`>= 4` 는 **손으로 쓴 하한**이었고 집합은 5개다 — 정확히 하나를 조용히 지울 수 있었다
    #   (「하한이 상한이 된다」가 **한 층 위에서 재발**했다 · 적대 리뷰 2차 HIGH-1).
    #   → 하한을 **스크립트에서 파생**시킨다.
    실제 = _판정불가_exit_코드(본문)
    assert 코드 == 실제, (
        f"선언({sorted(코드)})과 **실제 판정 불가 경로**({sorted(실제)})가 다르다 — "
        "경로를 늘리고 선언을 안 늘리면 재배치·문서·락이 **전부** 그 코드를 놓친다")
    return 코드


def _판정불가_exit_코드(본문: str) -> set[str]:
    """★**역방향 파생** — 스크립트에서 «`::VERDICT=UNDECIDED` 를 내고 exit 하는» 코드를 긁는다.

    종전 단언은 전부 **선언 → (문서·행위)** 한 방향이었다. 그래서 선언을 줄이거나
    새 경로를 선언 없이 추가해도 **초록**이었다(리뷰 변이 M2·M3 생존).
    """
    import re as _re

    코드 = set()
    줄 = 본문.splitlines()
    for k, ln in enumerate(줄):
        m = _re.match(r"\s*exit ([0-9]+)\s*$", ln)
        if not m:
            continue
        # 그 exit **직전 몇 줄** 안에 UNDECIDED 토큰을 내는 곳이 있으면 판정 불가 경로다
        앞 = "\n".join(줄[max(0, k - 6):k])
        if "::VERDICT=UNDECIDED" in 앞:
            코드.add(m.group(1))
    # 공유 블록(12·16)은 토큰이 한 곳이라 위 스캔으로 안 잡힌다 — 그 둘은 재배치 루프에서 파생
    m2 = _re.search(r'if \[ "\$\{MUT_INVALID:-0\}" -eq 1 \]; then\n\s*exit ([0-9]+)', 본문)
    if m2:
        코드.add(m2.group(1))
    m3 = _re.search(r'if \[ "\$\{PIPE_INVALID:-0\}" -eq 1 \]; then\n\s*exit ([0-9]+)', 본문)
    if m3:
        코드.add(m3.group(1))
    assert len(코드) >= 3, f"판정 불가 경로를 못 찾았다 — 추출기 의심: {코드}"
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
    # ★충돌이 사는 모집단은 **「도구가 내는 모든 코드」** 다 — 「판정 불가」 부분집합이 아니다
    #   (리뷰 2차 MEDIUM-1: 10·11·64·70·71 이 그대로 새어 나갔다. 70/71 은 「원복 실패」라
    #    깨끗한 트리를 두고 사람을 수색시킨다).
    for 코드 in sorted(_도구_종료코드(), key=int):
        r = subprocess.run(
            ["bash", str(_TOOL), "mod.py", "s|MARKER = 1|MARKER = 2|",
             "python3", "runner.py", 코드],
            cwd=repo, capture_output=True, text=True, check=False,
        )
        구, 신 = _긁기(r.stdout)
        assert 신 == "::VERDICT=CAUGHT", f"[rc={코드}] 판정이 CAUGHT 가 아니다: {신}"
        # ★구 스크레이퍼도 같은 판정을 읽어야 한다(호환은 두 모집단으로만 증명된다)
        assert 구 == "CAUGHT", f"[rc={코드}] 구 스크레이퍼 호환이 깨졌다: {구}"
        assert str(r.returncode) not in _도구_종료코드(), (
            f"[테스트 rc={코드}] 도구가 **도구 코드 {r.returncode}** 를 그대로 냈다 — "
            "호출자가 그것을 도구 신호로 오독한다")


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


def test_개수_축의_경계를_세_모집단으로_잠근다(tmp_path):
    """★이 축은 **원리적 한계**가 있다 — 그것까지 잠근다.

    종전 이 테스트는 *"기준선을 건너뛰어도 개수 축은 산다"* 였고 **초록이었다.**
    그런데 그것은 **내가 지어낸 픽스처**(`"0 passed"`) 덕이었다 — 진짜 vitest 빈 선택은
    `passed` 를 **한 번도 안 찍는다**(형제 락 `baseline_gate.py:208` 의 실측값).
    실측값을 넣으니 **B 는 원리적으로 못 고친다**는 것이 드러났다.

    세 모집단:
      A 기준선 측정 + vitest 빈 선택   → **UNDECIDED**(주 경로 · 이것이 이 축의 표적)
      B SKIP_BASELINE + vitest 빈 선택 → **SURVIVED**(가를 정보가 없다 · 도구가 **말해야** 한다)
      C SKIP_BASELINE + 개수 안 찍는 러너 → **SURVIVED**(위양성 축)
    """
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text("MARKER = 1\n", encoding="utf-8")
    (repo / "runner.py").write_text(_러너, encoding="utf-8")
    (repo / "nocount.py").write_text("import sys\nprint('done')\nsys.exit(0)\n", encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")

    def _go(argv, env=None):
        return subprocess.run(
            ["bash", str(_TOOL), "mod.py", "s|MARKER|GONE|", "python3", argv],
            cwd=repo, capture_output=True, text=True, check=False,
            env=dict(os.environ, **(env or {})),
        )

    # ── A: 주 경로. ★`MUT_HAS_COUNT` 만 게이트로 쓰면 **여기가 죽는다**(리뷰 2차 CRITICAL-1)
    a = _go("runner.py")
    _, 신a = _긁기(a.stdout)
    assert 신a == "::VERDICT=UNDECIDED", (
        f"[A 주 경로] 기준선을 쟀는데 개수 축이 안 돌았다: {신a} (rc={a.returncode})\n"
        "★진짜 vitest 빈 선택엔 `passed` 가 없다 — `MUT_HAS_COUNT` 만 보면 여기가 샌다")

    # ── B: ★원리적 한계. 판정은 SURVIVED 지만 **도구가 그 한계를 말해야** 한다
    b = _go("runner.py", {"MUTATE_SKIP_BASELINE": "락이 경계를 잠근다"})
    _, 신b = _긁기(b.stdout)
    assert 신b == "::VERDICT=SURVIVED", f"[B] 예상 밖 판정: {신b}"
    assert "개수 축이 약해진다" in (b.stdout + b.stderr), (
        "기준선을 건너뛰면 개수 축이 약해지는데 **말하지 않는다** — "
        "그 실행의 SURVIVED 를 근거로 쓰게 된다")

    # ── C: 위양성 축. 개수를 **안 찍는** 러너까지 막으면 그것도 결함이다
    c = _go("nocount.py", {"MUTATE_SKIP_BASELINE": "위양성 축"})
    _, 신c = _긁기(c.stdout)
    assert 신c == "::VERDICT=SURVIVED", f"[C] 개수를 안 찍는 러너를 막았다(위양성): {신c}"



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
            f"import sys\nprint({_VITEST_ALL_SKIPPED!r})\nsys.exit(0)\n", encoding="utf-8")
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


def test_sh_는_bash_구문으로_검사한다(tmp_path):
    """★M1 봉합 — 「검사기가 못 읽음」과 「변이가 깸」을 **가르는 입력**이 필요하다.

    종전 락(`test_구문검사는_변이_전에도_잰다`)은 **변이 전에도 실패하는** 파일만 썼다.
    그러면 «항상 깨졌다고 답하는 검사기» 변이가 **같은 결과**(축 꺼짐)를 내서 생존한다.
    → **변이 전 통과 · 변이 후 실패**인 `.sh` 를 태운다.

    ★그리고 이 케이스는 `sh -n`(dash)로는 **잡히지 않는다** — dash 는 `[[ … ]` 를
      명령어로 읽어 통과시킨다. `bash -n` 이어야 잡힌다(적대 리뷰 CRITICAL-1).
    """
    repo, sh = _repo(tmp_path)
    (repo / "tool.sh").write_text(
        "#!/usr/bin/env bash\nX=1\nif [[ $X -gt 0 ]]; then :; fi\n", encoding="utf-8")
    (repo / "t.py").write_text(
        "import subprocess\n"
        'def test_x(): assert subprocess.run(["bash","-n","tool.sh"]).returncode == 0\n',
        encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    r = subprocess.run(
        ["bash", str(_TOOL), "tool.sh", 's|-gt 0 ]]|-gt 0 ]|',
         "python3", "-m", "pytest", "t.py", "-q"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    합 = r.stdout + r.stderr
    assert "축을 끈다" not in 합, f"변이 전엔 통과했는데 축을 껐다:\n{합}"
    assert r.returncode == 16, (
        f"bash 구문을 깬 변이를 판정했다: rc={r.returncode}\n{합}\n"
        "★`sh -n`(dash)은 이걸 놓친다 — `bash -n` 이어야 한다")
    _, 신 = _긁기(r.stdout)
    assert 신 == "::VERDICT=UNDECIDED", f"토큰이 판정 불가가 아니다: {신}"


def test_요약이_stderr_로_나와도_개수를_읽는다(tmp_path):
    """★M5 봉합 — 변이 실행에서 `2>&1` 을 지우면 **stderr 러너의 개수를 못 읽는다.**

    그러면 개수 축이 조용히 꺼져 «통과 0건인데 rc=0» 이 `SURVIVED` 로 샌다.
    """
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text("MARKER = 1\n", encoding="utf-8")
    (repo / "runner.py").write_text(
        "import sys, pathlib\n"
        'src = pathlib.Path("mod.py").read_text()\n'
        '# ★요약을 **stderr** 로 낸다(실제 러너 중에 그런 것이 있다)\n'
        f'print({_VITEST_GREEN!r} if "MARKER" in src else {_VITEST_ALL_SKIPPED!r},'
        ' file=sys.stderr)\n'
        "sys.exit(0)\n", encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    r = subprocess.run(
        ["bash", str(_TOOL), "mod.py", "s|MARKER|GONE|", "python3", "runner.py"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    _, 신 = _긁기(r.stdout)
    assert 신 == "::VERDICT=UNDECIDED", (
        f"stderr 요약을 못 읽어 개수 축이 꺼졌다: {신} (rc={r.returncode})")


def test_개수는_모든_매치의_최대값으로_읽는다(tmp_path):
    """★M2 봉합 — `sort -rn`(최대)과 `sort -n`(최소)을 **가르는 입력**.

    러너가 범주를 나눠 찍으면 «0 passed» 줄이 함께 나올 수 있다
    (예: 파일 단위 요약과 케이스 단위 요약). 그때 **최소값을 쓰면 정상 실행을 막는다.**
    ★이 락은 「최대값이 옳다」를 고정한다 — 최소값으로 바꾸면 이 케이스가 빨개진다.
    """
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text("MARKER = 1\n", encoding="utf-8")
    (repo / "runner.py").write_text(
        "import sys\n"
        '# ★두 범주를 찍는다: 한쪽은 0, 다른 쪽은 3 — **실제로 3건이 통과**했다\n'
        'print("0 passed in 0.00s")\n'
        'print("3 passed in 0.01s")\n'
        "sys.exit(0)\n", encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    r = subprocess.run(
        ["bash", str(_TOOL), "mod.py", "s|MARKER = 1|MARKER = 2|", "python3", "runner.py"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    _, 신 = _긁기(r.stdout)
    assert 신 == "::VERDICT=SURVIVED", (
        f"통과가 3건 있는데 개수 축이 발화했다(최소값을 쓰면 이렇게 된다): {신} "
        f"(rc={r.returncode})")


def test_변이_후_수집0건도_판정하지_않는다(tmp_path):
    """★HIGH-2 — 계획서 §2-1 (b) 축이 **통째로 무잠금**이었다(그 6줄을 지워도 초록).

    변이가 **수집을 깨면** pytest 는 rc=5 를 낸다. 그건 «잡힌 것»이 아니라 «못 돈 것»이다.
    origin/main 은 이것을 **CAUGHT(rc=5)** 로 찍는다 = 변이 점수 부풀림.
    """
    repo, sh = _repo(tmp_path)
    (repo / "mod.py").write_text("SKIP = 0\n", encoding="utf-8")
    # ★변이가 `SKIP = 1` 로 만들면 모듈레벨 skip 이 발화해 **수집 0건**이 된다
    (repo / "test_mod.py").write_text(
        "import pytest\nfrom mod import SKIP\n"
        "if SKIP:\n    pytest.skip('전부 건너뜀', allow_module_level=True)\n"
        "def test_a(): assert True\n", encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", "init")
    r = subprocess.run(
        ["bash", str(_TOOL), "mod.py", "s|SKIP = 0|SKIP = 1|",
         "python3", "-m", "pytest", "test_mod.py", "-q"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    합 = r.stdout + r.stderr
    _, 신 = _긁기(r.stdout)
    assert 신 == "::VERDICT=UNDECIDED", (
        f"변이가 수집을 깼는데 판정을 발행했다: {신} (rc={r.returncode})\n{합}")
    assert r.returncode == 16, f"rc 가 16 이 아니다: {r.returncode}"


def _도구_종료코드() -> set[str]:
    """도구가 선언한 `TOOL_EXITS` 를 파생하고, **스크립트의 실제 `exit` 와 집합 동일**을 단언한다.

    ★역방향까지 봐야 «코드를 늘리고 선언을 안 늘림» 이 잡힌다(리뷰 2차 HIGH-1 의 형태).
    """
    import re as _re

    본문 = _TOOL.read_text(encoding="utf-8")
    m = _re.search(r'^TOOL_EXITS="([0-9 ]+)"', 본문, _re.MULTILINE)
    assert m, "도구가 `TOOL_EXITS` 를 선언하지 않는다 — 파생 불가"
    선언 = set(m.group(1).split())
    실제 = {c for c in _re.findall(r"^\s*exit ([0-9]+)\s*$", 본문, _re.MULTILINE)} - {"0", "1"}
    assert 선언 == 실제, (
        f"선언({sorted(선언, key=int)})과 스크립트의 실제 exit({sorted(실제, key=int)})가 다르다 — "
        "코드를 늘리고 선언을 안 늘리면 재배치가 그 코드를 놓친다")
    return 선언
