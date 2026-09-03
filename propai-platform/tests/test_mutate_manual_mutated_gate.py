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
    repo.mkdir()
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
    assert len(발행) >= 4, f"판정 토큰 발행 지점이 너무 적다 — 추출기 의심: {len(발행)}"
    assert not 언급, (
        "안내문·주석에 `::VERDICT=` 가 있다 — 그 순간 이 토큰도 오염된다:\n"
        + "\n".join(언급))
