"""계기판 ③ 이 **「술어 사망」과 「시스템 유휴」를 뭉쳐** 매 실행 `exit 3` 을 냈다.

## 관측 (라이브 2026-09-02)

    bash scripts/monitor/integrator_dashboard.sh; echo $?   → **EXIT=3**
      ③ "★대조군 0 — 같은 술어가 아무것도 못 집었다"
    그런데 같은 술어를 컨테이너에서 전수로 세면:
      latency_regression  전체 **2,348건** · 최신 2026-08-28 17:30
      창별  24h **0** · 3일 **0** · 7일 **52** · 30일 **965**

→ **술어는 살아 있고 시스템이 유휴**였다. 리터럴·스키마 문제가 아니다.

## 왜 위험한가

유휴가 지속되는 동안 계기판은 **영구히 `exit 3`** 을 낸다. 상시 3 은 곧 무시되고,
그때 **진짜 검사기 사망이 묻힌다** — 이 파일의 형제(`integrator_dashboard.sh`)가
`#868` 에서 *"상시 빨간 계기판은 곧 무시된다"* 로 이미 값을 치른 형태다.

★그리고 같은 파일이 `3` 을 `0` 에서 가른 이유가 *"뭉치면 죽은 검사기가 초록으로 읽힌다"* 였다.
**같은 원칙을 한 축 더 적용**하는 것이지 새 설계가 아니다.

## 이 파일이 잠그는 것 — **세 모집단**

    alltime=0 · h24=0  → 술어 사망   (DEAD · exit 3)
    alltime>0 · h24=0  → 시스템 유휴 (NOT DEAD)   ← 이 변경이 만드는 칸
    alltime>0 · h24>0  → 판정 진행   (NOT DEAD)

★**둘로 만들면 「검사기 사망」이 「유휴」로 읽히거나 그 반대가 된다.** 셋째 칸이 요점이다.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DASH = _ROOT / "scripts" / "monitor" / "integrator_dashboard.sh"
_PROBE = _ROOT / "scripts" / "monitor" / "growth_stale_producer_probe.py"


def _classify(alltime: int, h24: int) -> str:
    """계기판 ③ 분기를 **셸에서 그대로 실행해** 판정한다.

    ★사본을 태우지 않는다 — 파싱 논리를 여기 다시 쓰면 프로덕션 분기를 통째로
      되돌려도 이 락이 초록이다(2026-08-28 `#905` 에서 실측한 형태).
      그래서 **실제 파일에서 분기 블록을 꺼내** `bash` 에 먹인다.
    """
    src = _DASH.read_text(encoding="utf-8")
    m = re.search(
        r'\n(  if \[ "\$\{ctrl:-0\}" -eq 0 \].*?\n  else\n)', src, re.DOTALL)
    assert m, "★③ 분기 블록을 못 찾았다 — 락이 낡았다(공허한 초록 방지)"
    block = m.group(1)
    # `else` 이후 본문은 판정에 무관하므로 닫아 준다.
    script = (
        f'ctrl={h24}\nctrl_all={alltime}\nDEAD=0\n'
        + block
        + '    echo "   판정진행"\n  fi\n'
        + 'echo "DEAD=$DEAD"\n'
    )
    out = subprocess.run(["bash", "-c", script], capture_output=True,
                         text=True, check=False)
    assert out.returncode == 0, f"★분기 실행 실패: {out.stderr[:200]}"
    return out.stdout


def test_the_three_populations_give_three_different_answers():
    """★파티션형 — 개별 케이스만 걸면 **둘을 합치는 변이**가 샌다."""
    dead = _classify(alltime=0, h24=0)
    idle = _classify(alltime=2348, h24=0)
    judging = _classify(alltime=2348, h24=52)

    assert "DEAD=1" in dead, "전 역사 0 인데 검사기 사망으로 안 본다"
    assert "DEAD=0" in idle, "★유휴를 검사기 사망으로 읽는다(이 PR 이 고치는 그것)"
    assert "DEAD=0" in judging, "정상 판정 경로가 죽었다"

    # ★세 답이 **서로 다른 문구**여야 한다 — 같으면 읽는 사람이 못 가른다.
    assert "전 역사에서 아무것도 못 집었다" in dead
    assert "판정 불가" in idle and "시스템 유휴" in idle
    assert "판정진행" in judging
    assert dead != idle != judging, "두 모집단이 같은 출력을 낸다"


def test_idle_is_not_reported_as_all_clear_either():
    """★「검사기 사망이 아니다」가 「이상 없음」을 뜻하지 않는다.

    이 저장소가 반복해 데인 형태다 — *"경보를 안 냄 ≠ 이상 없음"*.
    유휴 칸은 **판정을 못 했다고 말해야** 한다.

    ★**첫 판은 `assert "이상 없음" not in idle` 이었고 실패했다** — 내가 그 분기에
      *"이 줄은 '검사기 사망'도 '이상 없음'도 아니다"* 라고 **써 넣었기 때문**이다.
      즉 **내가 쓴 안내문이 내 단언을 거짓으로 만들었다**(이 저장소의 알려진 형태).
      → 단언을 **문자열 부재**가 아니라 **구조**로 옮긴다: 유휴 칸은 ①비어 있지 않고
      ②판정 불가를 **명시**하며 ③플래그를 **하나도 세우지 않는다**.
    """
    idle = _classify(alltime=2348, h24=0)
    assert idle.strip(), "유휴 칸이 침묵한다 — 침묵은 '이상 없음'으로 읽힌다"
    assert "판정 불가" in idle, "판정을 못 했다는 사실을 말하지 않는다"
    # ★구조: 유휴는 어떤 플래그도 세우지 않는다(사망도 위반도 아니다)
    assert "DEAD=0" in idle and "VIOL=1" not in idle


def test_idle_branch_does_not_invent_a_violation():
    """★`exit 2` 를 만들지 않는다 — `#868`(상시 빨강) 기각을 존중한다."""
    idle = _classify(alltime=2348, h24=0)
    assert "VIOL=1" not in idle, "유휴를 위반으로 승격했다"


def test_probe_actually_emits_the_key_the_dashboard_reads():
    """★계기판만 고치면 `ctrl_all` 이 **영원히 빈 문자열**이 되고
    `${ctrl_all:-0}` 이 0 으로 떨어져 **전부 「술어 사망」**이 된다.

    즉 이 락이 없으면 이 PR 은 **아무것도 안 고친 것과 같은 출력**을 낸다.
    """
    probe = _PROBE.read_text(encoding="utf-8")
    dash = _DASH.read_text(encoding="utf-8")
    assert "ctrl_type_alltime=%s" in probe, "프로브가 그 키를 안 내보낸다"
    assert "ctrl_type_alltime=[0-9]+" in dash, "계기판이 그 키를 안 읽는다"
    # ★양성 대조군 — 종전 키는 **이름·의미가 그대로**여야 한다(다른 소비처 보호)
    assert "ctrl_type_total=%s" in probe and "ctrl_type_total=[0-9]+" in dash


def test_alltime_query_has_no_window():
    """★`ctrl_all` 이 창을 갖고 있으면 유휴에서 또 0 이 되어 이 수정이 무의미해진다."""
    probe = _PROBE.read_text(encoding="utf-8")
    m = re.search(r"ctrl_all = \(await s\.execute\(text\(\s*(.*?)\)\)\)\.scalar\(\)",
                  probe, re.DOTALL)
    assert m, "★alltime 질의를 못 찾았다 — 락이 낡았다"
    q = m.group(1)
    assert "latency_regression" in q, "같은 술어가 아니다 — 대조군 자격 없음"
    assert "interval" not in q, "★alltime 에 창이 걸려 있다(유휴에서 또 0 이 된다)"
