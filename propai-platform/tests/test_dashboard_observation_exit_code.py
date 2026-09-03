"""계기판 종료코드 — **관측 이상(4)** 이 「이상 없음(0)」과 뭉치지 않는가.

★왜 이 파일이 있나 (2026-08-28 · 독립 리뷰 development-ai-8d)
  `integrator_dashboard.sh` 는 자기 머리말에 *"「검사기가 죽었다」와 「깨끗하다」를 다른
  종료코드로 가른다 — 뭉치면 죽은 검사기가 초록으로 읽힌다"* 고 적어 두고,
  **관측된 지연 버스트는 `0` 에 뭉쳐 두고 있었다.** 92,238ms 짜리 동시다발 버스트가
  도는 중에도 `exit 0` 이었다. 처방을 적용한 범위가 결함이 사는 범위보다 좁았다(§D-20).

  ★그리고 이것은 가설이 아니다 — 이 계기판을 읽는 통합자 세션이 실제로 `EXIT=0` 을
    **35회 완료신호로 인용**했다(전사 실측). 사람이 소비자였고, 그 사람이 오독했다.

★락의 형태는 **파티션형**이다(§한쪽만 거는 단언 금지).
  네 모집단이 **서로 다른 답**을 내야 한다:
      (DEAD,VIOL,OBS) = (1,*,*) → 3   (0,1,*) → 2   (0,0,1) → 4   (0,0,0) → 0
  하나라도 같은 답으로 뭉치면 이 파일이 빨개진다.
"""
from __future__ import annotations

import subprocess
import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "monitor" / "integrator_dashboard.sh"


def _verdict(dead: int, viol: int, obs: int) -> tuple[int, str]:
    """★스크립트의 **실제 판정 함수**를 태운다(문자열 검사가 아니다).

    `--verdict-lib` 로 source 하면 프로브·SSH·DB 를 하나도 타지 않고 판정만 돌아온다.
    그렇게 꺼내지 않으면 이 결정은 **원리적으로 테스트 불가**다(그래서 아무도 안 태웠다).
    """
    r = subprocess.run(
        ["bash", "-c", f'. "{SCRIPT}" --verdict-lib; DEAD={dead} VIOL={viol} OBS={obs} verdict_exit'],
        capture_output=True, text=True, timeout=30, check=False,
    )
    return r.returncode, r.stdout + r.stderr


def test_the_script_exists_and_parses() -> None:
    """★생존 단언 — 아래 파티션이 「검사기 사망」으로 공허하게 초록이 되는 것을 막는다."""
    assert SCRIPT.is_file(), f"계기판이 없다: {SCRIPT}"
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=30, check=False
    )
    assert r.returncode == 0, f"구문 오류로 이 락 전체가 무의미하다:\n{r.stderr}"


@pytest.mark.parametrize(
    ("dead", "viol", "obs", "want"),
    [
        (0, 0, 0, 0),   # 청결
        (0, 0, 1, 4),   # ★관측 이상 — 이 줄이 이번 수정의 전부다
        (0, 1, 0, 2),   # 진짜 위반
        (0, 1, 1, 2),   # ★위반이 관측이상을 **이긴다**(2 의 희소성 보존)
        (1, 0, 0, 3),   # 검사기 사망
        (1, 1, 1, 3),   # ★사망이 전부를 이긴다(못 잰 것을 판정으로 덮지 않는다)
    ],
)
def test_verdict_is_a_partition(dead: int, viol: int, obs: int, want: int) -> None:
    rc, out = _verdict(dead, viol, obs)
    assert rc == want, f"(DEAD={dead},VIOL={viol},OBS={obs}) → {rc}, 기대 {want}\n{out}"


def test_the_four_verdicts_are_all_distinct() -> None:
    """★뭉침 자체를 금지한다.

    개별 케이스만 단언하면 *"둘을 같은 코드로 합치는"* 변이가 개별 단언 몇 개만
    빨갛게 하고 지나갈 수 있다. **네 답이 서로 달라야 한다**를 직접 건다.
    """
    codes = {
        "청결": _verdict(0, 0, 0)[0],
        "관측이상": _verdict(0, 0, 1)[0],
        "위반": _verdict(0, 1, 0)[0],
        "사망": _verdict(1, 0, 0)[0],
    }
    assert len(set(codes.values())) == 4, f"종료코드가 뭉쳤다: {codes}"


def test_clean_verdict_does_not_claim_clean_when_observed() -> None:
    """★사람이 읽는 줄도 뭉치면 안 된다 — 35회 오독은 **문장**을 읽고 난 것이다."""
    rc0, out0 = _verdict(0, 0, 0)
    rc4, out4 = _verdict(0, 0, 1)
    assert rc0 == 0 and "이상 없음 — 모든 프로브 생존" in out0, out0
    # 음성 대조군: 관측이상일 때 그 문장이 **나오면 안 된다**
    assert "이상 없음 — 모든 프로브 생존" not in out4, \
        f"관측이상인데 청결 문장을 찍는다(사람이 오독한 바로 그 문장):\n{out4}"
    assert rc4 == 4 and "관측 이상" in out4, out4


def _code_lines() -> list[str]:
    """★주석을 걷어낸다 — 이 저장소는 소스 문자열 검사가 주석에 뚫린 전례가 많다.

    ★★오늘 나 자신이 `"ESCALATION_WINDOW_HOURS" in getsource(...)` 로 같은 결함을 냈다
      (그것을 고친 지 몇 분 뒤에). 문자열 검사를 쓸 때마다 물어야 한다:
      **「이 이름이 내 주석에도 있나」**
    """
    out = []
    for ln in SCRIPT.read_text(encoding="utf-8").splitlines():
        body = ln.split("#", 1)[0]
        if body.strip():
            out.append(body)
    return out


def test_multi_route_burst_is_wired_to_the_observation_flag() -> None:
    """★배선 락 — 판정 함수만 잠그면 **아무도 OBS 를 켜지 않아도** 위 전부가 초록이다.

    (오늘의 반복 실측: 함수 안에만 변이를 넣으면 5/5 CAUGHT 인데 배선은 무잠금이었다.)
    동시다발(`MR`) 분기 **안에서** `OBS=1` 이 켜지는지를 구조로 본다.
    """
    lines = _code_lines()
    starts = [i for i, ln in enumerate(lines) if "MR:-0" in ln and "-gt 0" in ln]
    assert len(starts) == 1, f"동시다발 분기를 특정하지 못했다(수집기 사망): {starts}"
    i = starts[0]
    # 그 `if` 의 `fi` 까지만 본다 — ★범위를 안 닫으면 **파일 어딘가의** OBS=1 로 통과한다
    depth, block = 0, []
    for ln in lines[i:]:
        block.append(ln)
        t = ln.strip()
        if t.startswith("if "):
            depth += 1
        if t == "fi" or t.endswith("; fi"):
            depth -= 1
            if depth <= 0:
                break
    assert depth <= 0, "동시다발 분기의 끝(fi)을 못 찾았다 — 수집기 사망"
    assert any("OBS=1" in ln for ln in block), \
        "동시다발 버스트가 관측 플래그를 켜지 않는다 — 판정 함수는 잠겼지만 배선이 없다:\n" + "\n".join(block)


# ★수집기와 판정기를 **같은 축**으로 맞춘다.
#   종전 수집기는 `ln.strip() == "OBS=1"` 이라 **한 줄 결합**(`OBS=1; MR=3`)을 못 봤다.
#   그러면 이 락이 막으려는 **바로 그 방향**(무조건 설정)이 표기 하나로 새고, 공허 방지 가드
#   (`assert tops`)도 **같은 맹점을 공유**한다 — "필터의 절단이 수집기의 절단보다 조용하다".
_OBS_SET = "OBS=1"
# 조건부로 인정하는 여는 줄: if / elif / else / case 분기 패턴(`a)`).
#   ★`while`·`for`·함수 본문은 **인정하지 않는다** — 조건이 아니라 반복·호출이다.
_COND_OPEN = re.compile(r"^(if|elif|else)\b|^[^()\s]+\)\s*$")


def _obs_set_lines(lines: list[str]) -> list[tuple[int, str]]:
    """`OBS=1` 을 **실행하는** 줄 전부. 한 줄 결합(`;`·`&&`·`||`)도 센다."""
    out = []
    for i, ln in enumerate(lines):
        if any(seg.strip() == _OBS_SET for seg in re.split(r"[;&|]+", ln)):
            out.append((i, ln))
    return out


def _unconditional_obs_lines(lines: list[str]) -> list[str]:
    """`OBS=1` 중 **조건 블록 안에 있지 않은** 것을 고른다.

    판정: 그 줄보다 **들여쓰기가 작은 가장 가까운 윗줄**이 조건을 여는가
    (`if`/`elif`/`else`/`case` 분기). 셸에서 조건부 실행의 실제 구조가 그것이다.
    ★`else` 와 `case` 분기를 빠뜨리면 **정상 코드를 위반으로 신고**한다(가드의 위양성도 결함이다).
    """
    bad = []
    for i, ln in _obs_set_lines(lines):
        ind = len(ln) - len(ln.lstrip())
        if ind == 0:
            bad.append(ln)
            continue
        for prev in reversed(lines[:i]):
            if not prev.strip():
                continue
            pind = len(prev) - len(prev.lstrip())
            if pind < ind:
                if not _COND_OPEN.match(prev.strip()):
                    bad.append(ln)
                break
        else:
            bad.append(ln)
    return bad


def test_observation_flag_is_not_forced_on_elsewhere() -> None:
    """★반대 방향 — `OBS=1` 이 무조건 켜지면 계기판이 **상시 4** 가 되어 3 과 같은 문제가 된다.

    ★★**대리 변수를 잠그면 속성은 안 잠긴다.** 종전 단언은 `len(tops) == 1` 로 **개수**를 셌는데,
    그것은 "무조건 켜지지 않는다"의 **대리 변수**일 뿐이다. 2026-09-03 합성으로 실측하니
    **양방향으로 틀렸다**:

        무조건 `OBS=1` 이 **단 1개**       → 종전 락 **통과**  (의도를 못 잡는다 · 위음성)
        조건부 `OBS=1` 이 **2개**          → 종전 락 **실패**  (정상 코드를 막는다 · 위양성)

    실제로 위양성이 발생했다 — 성장루프 **유휴**(판정 불가)와 동시다발 **버스트**(외부 원인)는
    서로 다른 관측 이상이고 **둘 다 조건부**인데, 개수 단언이 둘의 공존을 막았다.
    → **속성 자체**를 단언한다: 모든 `OBS=1` 은 `if`/`elif` 블록 안에 있다.
    """
    lines = _code_lines()
    tops = _obs_set_lines(lines)   # ★가드도 판정기와 **같은 수집기**를 쓴다
    assert tops, "★OBS=1 이 하나도 없다 — 관측 이상 축이 통째로 죽었다(공허한 초록 방지)"
    bad = _unconditional_obs_lines(lines)
    assert not bad, f"★OBS=1 이 조건 없이 켜진다(상시 4 위험): {bad}"
    init = [ln for ln in lines if ln.strip().startswith("OBS=0")]
    assert init, "OBS 초기화가 없다 — 미설정이면 `${OBS:-0}` 에 기대게 되어 배선이 조용히 죽는다"


def test_the_unconditional_detector_actually_discriminates() -> None:
    """★판정기의 **양성·음성 대조군** — 없으면 "항상 []" 를 반환해도 초록이다.

    ★아래 A·B·G·E2 는 **동료 세션(development-ai-62)이 실측해 알려 준 갭**이고, 내가 직접
    재현해 확인했다. 종전 판정기는 `else`·`case` 분기를 **위반으로 오신고**했고(위양성 3종),
    한 줄 결합 `OBS=1; MR=3` 은 **놓쳤다**(위음성 — 막으려는 방향이 표기 하나로 샜다).
    ★넷 다 당시 실제 스크립트에는 **0건인 잠복 결함**이었다. 잠복이라고 안 고치면 다음 사람이 밟는다.
    """
    # ── 위반이어야 하는 것(양성) ──
    assert _unconditional_obs_lines(["OBS=1"]), "★최상위 무조건 OBS=1 을 못 잡는다"
    assert _unconditional_obs_lines(["OBS=1; MR=3"]), \
        "★E2 한 줄 결합 무조건 OBS=1 을 못 잡는다(수집기가 판정기보다 좁다)"
    assert _unconditional_obs_lines(["  while x; do", "    OBS=1", "  done"]), \
        "★조건이 아닌 블록(루프) 안의 OBS=1 을 못 잡는다"
    # ── 정상이어야 하는 것(음성 — 가드의 위양성도 결함이다) ──
    for name, lines in {
        "if/elif 두 곳": ["  if x; then", "    OBS=1", "  fi", "  elif y; then", "    OBS=1", "  fi"],
        "A) else 안":    ["  if x; then", "    :", "  else", "    OBS=1", "  fi"],
        "B) elif→else":  ["  if x; then", "    :", "  elif y; then", "    :", "  else",
                          "    OBS=1", "  fi"],
        "G) case 분기":  ["  case $v in", "    a)", "      OBS=1", "      ;;", "  esac"],
        "E) 조건부 한줄결합": ["  if x; then", "    OBS=1; MR=3", "  fi"],
    }.items():
        assert _unconditional_obs_lines(lines) == [], f"★{name} 을 위반으로 오신고한다(위양성)"