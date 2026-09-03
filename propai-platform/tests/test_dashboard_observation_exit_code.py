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


def test_observation_flag_is_not_forced_on_elsewhere() -> None:
    """★반대 방향 — `OBS=1` 이 무조건 켜지면 계기판이 **상시 4** 가 되어 3 과 같은 문제가 된다."""
    tops = [ln for ln in _code_lines() if ln.strip() == "OBS=1"]
    assert len(tops) == 1, f"OBS=1 이 여러 곳에서 켜진다(상시 4 위험): {tops}"
    init = [ln for ln in _code_lines() if ln.strip().startswith("OBS=0")]
    assert init, "OBS 초기화가 없다 — 미설정이면 `${OBS:-0}` 에 기대게 되어 배선이 조용히 죽는다"
