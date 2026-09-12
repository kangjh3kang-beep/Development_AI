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
import shlex
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DASH = _ROOT / "scripts" / "monitor" / "integrator_dashboard.sh"
_PROBE = _ROOT / "scripts" / "monitor" / "growth_stale_producer_probe.py"


def _classify(alltime: int, h24: int, probe_line: str = "") -> str:
    """계기판 ③ 분기를 **셸에서 그대로 실행해** 판정한다.

    ★사본을 태우지 않는다 — 파싱 논리를 여기 다시 쓰면 프로덕션 분기를 통째로
      되돌려도 이 락이 초록이다(2026-08-28 `#905` 에서 실측한 형태).
      그래서 **실제 파일에서 분기 블록을 꺼내** `bash` 에 먹인다.

    ★★2026-09-12 — **이 하네스가 의존성을 안 주고 있었다.** 블록만 떼어 돌리니
      ③ 이 부르는 판정 함수가 **정의되지 않았고**, 그 자리에서 사유가 **빈 문자열**인
      경보가 나왔다(«★ — **0 으로 읽지 마라**»). 락이 그 결함을 잡아 준 것은 옳지만,
      **프로덕션에 없는 구성**을 재는 하네스이기도 했다.
      → 이제 실제 스크립트를 `--verdict-lib` 로 **소스해** 함수를 갖춘 뒤 블록을 태운다.
        그리고 «함수가 없는 구성» 은 별도 케이스로 **따로** 잠근다(아래).

    `probe_line`: 프로브 출력 한 줄(`$G`). 비우면 «분석상태 필드 없음» 모집단이 된다.
    """
    src = _DASH.read_text(encoding="utf-8")
    m = re.search(
        r'\n(  if \[ "\$\{ctrl:-0\}" -eq 0 \].*?\n  else\n)', src, re.DOTALL)
    assert m, "★③ 분기 블록을 못 찾았다 — 락이 낡았다(공허한 초록 방지)"
    block = m.group(1)
    # `else` 이후 본문은 판정에 무관하므로 닫아 준다.
    script = (
        f". '{_DASH}' --verdict-lib\n"
        f'G={shlex.quote(probe_line)}\nctrl={h24}\nctrl_all={alltime}\n'
        'DEAD=0\nOBS=0\nVIOL=0\n'
        + block
        + '    echo "   판정진행"\n  fi\n'
        + 'echo "DEAD=$DEAD"\necho "OBS=$OBS"\n'
    )
    out = subprocess.run(["bash", "-c", script], capture_output=True,
                         text=True, check=False)
    assert out.returncode == 0, f"★분기 실행 실패: {out.stderr[:200]}"
    return out.stdout


#: 분석기가 «돌았고 표본이 없다» 고 말하는 프로브 줄(라이브 실측 형태 2026-09-12).
_G_STARVED = ("PROBE now=2026-09-12 10:05 ctrl_type_total=0 ctrl_type_alltime=2408 "
              "astate=starved aat=2026-09-12T10:05:00Z aaxes=lat_0/19_pay_0/1 ains=0 "
              "alast=2026-09-12T10:02:57Z")
#: 설정 행 자체가 없다 = TTL 산수상 **3회 연속 미실행**.
_G_ABSENT = _G_STARVED.replace("astate=starved", "astate=(행없음)")


def test_the_three_populations_give_three_different_answers():
    """★파티션형 — 개별 케이스만 걸면 **둘을 합치는 변이**가 샌다.

    ★2026-09-12 문구 갱신: 유휴 칸이 «판정 불가» 라고만 말하던 것을 **실제로 판정**하게
      바꿨다(분석기가 발행하는 `growth_analysis` 를 읽는다). 그래서 문구 핀을 옮겼다.
      ***바뀐 것은 「무엇을 말하는가」이고, 이 락이 지키는 「셋이 서로 다르다」는 그대로다.***
      단언을 **약화시키지 않았다** — 아래에 두 모집단(행 부재·판정기 부재)을 **추가**했다.
    """
    dead = _classify(alltime=0, h24=0)
    idle = _classify(alltime=2348, h24=0, probe_line=_G_STARVED)
    judging = _classify(alltime=2348, h24=52)

    assert "DEAD=1" in dead, "전 역사 0 인데 검사기 사망으로 안 본다"
    assert "DEAD=0" in idle, "★유휴를 검사기 사망으로 읽는다(이 PR 이 고치는 그것)"
    assert "DEAD=0" in judging, "정상 판정 경로가 죽었다"

    # ★세 답이 **서로 다른 문구**여야 한다 — 같으면 읽는 사람이 못 가른다.
    assert "전 역사에서 아무것도 못 집었다" in dead
    assert "하한 미달" in idle
    assert "판정진행" in judging
    assert dead != idle != judging, "두 모집단이 같은 출력을 낸다"


def test_absent_status_row_is_not_read_as_idle_normality():
    """★«설정 행 없음» 은 TTL 산수상 **3회 연속 미실행**이다 — 유휴와 **다른 답**이어야 한다."""
    idle = _classify(alltime=2348, h24=0, probe_line=_G_STARVED)
    absent = _classify(alltime=2348, h24=0, probe_line=_G_ABSENT)
    assert "OBS=0" in idle, "★설명된 유휴가 관측이상으로 올라갔다(상시 4 는 곧 무시된다)"
    assert "OBS=1" in absent, "★3회 연속 미실행이 아무 플래그도 안 세운다"
    assert idle != absent, "두 모집단이 같은 출력을 낸다"


def test_missing_judge_is_loud_and_never_silent():
    """★★판정기가 **없을 때**가 가장 위험하다 — 그때 사유가 비면 «사유 없는 경보» 가 된다.

    실측(2026-09-12): 이 파일의 하네스가 블록만 떼어 돌려 판정 함수가 미정의였고,
    계기판이 «★ — **0 으로 읽지 마라**» 라는 **빈 사유**를 찍었다. **이 락이 잡았다.**
    ***경보의 사유가 비면 읽는 사람은 무엇을 볼지 모른다 — 침묵과 같다.***
    """
    out = subprocess.run(
        ["bash", "-c",
         f'G=""\nctrl=0\nctrl_all=2348\nDEAD=0\nOBS=0\nVIOL=0\n'
         + re.search(r'\n(  if \[ "\$\{ctrl:-0\}" -eq 0 \].*?\n  else\n)',
                     _DASH.read_text(encoding="utf-8"), re.DOTALL).group(1)
         + '    echo "   판정진행"\n  fi\necho "DEAD=$DEAD"\n'],
        capture_output=True, text=True, check=False)
    body = out.stdout
    assert "DEAD=1" in body, "★판정기가 없는데 사망으로 안 본다(0 으로 읽힌다)"
    star = [ln for ln in body.splitlines() if ln.strip().startswith("★")]
    assert star, "★경보 줄 자체가 없다"
    for ln in star:
        # 「★」 와 장식(— **0 으로 읽지 마라**)을 걷어낸 **알맹이**가 있어야 한다
        core = ln.strip().lstrip("★").split("—")[0].strip()
        assert len(core) >= 8, f"★사유가 비었다(사유 없는 경보): {ln!r}"


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
    idle = _classify(alltime=2348, h24=0, probe_line=_G_STARVED)
    assert idle.strip(), "유휴 칸이 침묵한다 — 침묵은 '이상 없음'으로 읽힌다"
    # ★2026-09-12: «판정 불가» 라고 **말만 하던 것**을 실제 판정으로 바꿨다.
    #   그러므로 요구는 «못 했다고 말하라» 가 아니라 **«근거를 대고 말하라»** 다.
    #   유휴 칸은 ①분석기 상태와 ②그 판정 사유를 **둘 다** 실어야 한다.
    assert "분석기 상태:" in idle, "무엇을 근거로 유휴라 하는지 안 적는다"
    assert "state=" in idle and "워터마크" in idle, "근거 값이 빠졌다"
    assert "하한 미달" in idle, "판정 사유를 말하지 않는다"
    # ★구조: 유휴는 어떤 플래그도 세우지 않는다(사망도 위반도 아니다)
    assert "DEAD=0" in idle and "VIOL=1" not in idle


def test_idle_does_not_fall_through_to_exit_zero():
    """★★유휴가 `DEAD=0` 이면 **마지막 줄의 `exit 0`("모든 프로브 생존")로 떨어진다.**

    첫 판이 정확히 그랬다 — 독립 리뷰(`development-ai-3c`)가 짚었다:
    *"`exit 2` 를 안 내는 근거가 `exit 0` 을 내는 근거는 아니다."*

    ★이 저장소가 `3` 을 `0` 에서 가른 이유(*"뭉치면 죽은 검사기가 초록으로 읽힌다"*)와
      **같은 형태**이고, 나는 그 지적을 **다른 PR 에 하고 내 PR 에 넣었다**
      (처방 범위 < 결함 범위). → 유휴는 `OBS=1` 로 **exit 4** 를 낸다.
    """
    src = _DASH.read_text(encoding="utf-8")
    # ① 유휴 분기가 플래그를 세운다
    idle_block = re.search(
        'elif \\[ "\\$\\{ctrl:-0\\}" -eq 0 \\]; then(.*?)\\n  else\\n', src, re.DOTALL)
    assert idle_block, "★유휴 분기를 못 찾았다 — 락이 낡았다"
    assert "OBS=1" in idle_block.group(1),         "★유휴가 플래그를 안 세운다 → exit 0('모든 프로브 생존')로 떨어진다"
    # ② 최종 판정이 그 플래그를 **exit 0 보다 먼저** 읽는다
    #
    # ★**모양이 아니라 위치로 찾는다.** 첫 판은 `src.rindex('if [ "$DEAD"')` 로 **리터럴 모양**을
    #   집었는데, 그 사이 main 이 판정부를 `verdict_exit()` 함수로 추출하면서 그 줄이
    #   `if [ "${DEAD:-0}" -eq 1 ]` 로 바뀌어 **락이 ValueError 로 터졌다**(2026-09-03 실측).
    #   락이 지키려는 것은 «판정 순서» 이지 «그 줄의 철자» 가 아니다 — 리팩토링이 계약을
    #   바꾸지 않았는데 락이 깨지면 그것은 락의 결함이다. 그래서 두 형태를 다 받는다.
    dead_tests = list(re.finditer(r'if \[ "\$\{?DEAD(?::-0)?\}?"', src))
    assert dead_tests, "★최종 판정 블록을 못 찾았다 — 락이 낡았다(공허한 초록 방지)"
    tail = src[dead_tests[-1].start():]
    m_obs = re.search(r'"\$\{?OBS(?::-0)?\}?"', tail)
    i_zero = tail.find('exit 0')
    assert m_obs, "★최종 판정이 OBS 를 안 읽는다(플래그가 장식이 된다)"
    assert i_zero != -1, "★판정부에 exit 0 이 없다 — 락이 낡았다"
    assert m_obs.start() < i_zero, "★OBS 판정이 exit 0 뒤에 있다 — 도달 불가"
    assert "exit 4" in tail, "★관측 이상 종료코드가 없다"
    # ③ ★양성 대조군 — 기존 두 코드가 살아 있어야 한다(내가 갈아엎지 않았다)
    assert "exit 3" in tail and "exit 2" in tail


def test_idle_branch_does_not_invent_a_violation():
    """★`exit 2` 를 만들지 않는다 — `#868`(상시 빨강) 기각을 존중한다."""
    for g in (_G_STARVED, _G_ABSENT, ""):
        idle = _classify(alltime=2348, h24=0, probe_line=g)
        assert "VIOL=1" not in idle, f"유휴를 위반으로 승격했다: {g[:40]!r}"


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
