"""계기판 분석 판정 — **사유가 참인가**와 **애초에 불리는가**.

★이 파일이 잠그는 것은 **문구가 아니라 주장↔관측의 일치**다.
  문구를 단언하면 다듬을 때마다 깨지는 취약한 락이 되고(§G-30),
  포함만 단언하면 **거짓을 말해도 통과**한다(§「포함은 「거짓을 말하지 않는가」를 함의하지 않는다」).

★**이 락이 잡는 실제 결함**(2026-09-14 · 라이브 실측이 증거):
  ① 사유가 「입력이 0인 축 **3개**(fal 0/0 lat 0/0 **pay 0/1** qua 0/0)」 — 4개를 열거하고
     그 안에 **입력이 있는 축**을 넣었다. 개수는 부분집합, 열거는 전체였다.
  ② 모든 축에 입력이 있어도 「입력이 0인 축 **0개**(lat 1/9 pay 2/3)」 — 0개라며 2개 열거.
  ③ 그 판정 자체가 `ctrl==0` 게이트 안이라 **라이브에서 한 번도 안 불렸다**(24h ctrl=6).

★**이 락이 원리적으로 못 보는 것**: ③의 «화면에 실제로 출력되는가». 락은 함수/배선을 태울 뿐이라
  별도로 `test_analysis_section_is_called_outside_the_ctrl_gate` 를 둔다.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = _ROOT / "scripts" / "monitor" / "integrator_dashboard.sh"
PROBE = _ROOT / "scripts" / "monitor" / "growth_stale_producer_probe.py"

#: 사유가 「입력 0 축」을 주장하는 모양. ★테스트가 **독립적으로** 파싱한다 —
#  프로덕션 포매터를 부르면 「String.format 이 동작한다」를 단언하는 꼴이 된다(사본 금지의 반대편).
_CLAIM = re.compile(r"입력이 0인 축 (\d+)개\(([^)]*)\)")

#: 라이브 실측 형태(2026-09-13T12:11:29Z). **혼합**이라 ①을 태운다.
AX_MIXED = "fal 0/0 lat 0/0 pay 0/1 qua 0/0"
#: 모든 축에 입력이 있다 → 그 절이 **아예 없어야** 한다(특이도 · ②를 태운다).
AX_ALL_INPUT = "lat 1/9 pay 2/3"


def _probe():
    spec = importlib.util.spec_from_file_location("_probe_truth", PROBE)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _claim(why: str):
    """사유에서 (주장한 개수, 열거한 축 이름 집합) 을 뽑는다. 절이 없으면 None."""
    m = _CLAIM.search(why)
    if m is None:
        return None
    return int(m.group(1)), {a[0] for a in _probe().parse_axes(m.group(2))}


def _zero_axes(aaxes: str) -> set[str]:
    return {a[0] for a in _probe().parse_axes(aaxes) if a[2] == 0}


# ── ① 주장 ↔ 관측 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("astate", ["starved", "judged"])
def test_reason_enumerates_only_zero_input_axes(astate: str) -> None:
    """★열거 집합 == 입력 0 집합 · 개수 == 열거 수 · **입력 있는 축은 열거에 없다**.

    ★현행(고치기 전) 코드는 여기서 **3 vs 4** 로 죽는다 — 즉 이 락은 탐지력이 있다.
    """
    m = _probe()
    why = m.analysis_verdict(astate, "0", AX_MIXED)[1]
    claim = _claim(why)
    assert claim is not None, f"★조회기 사망 — 사유가 이 모양을 더는 안 쓴다(락이 낡았다): {why!r}"
    n, listed = claim
    truth = _zero_axes(AX_MIXED)

    assert truth, "★공허 방지 — 픽스처에 입력 0 축이 하나도 없다"
    assert listed == truth, f"열거({sorted(listed)}) != 입력0집합({sorted(truth)}) · 사유={why!r}"
    assert n == len(listed) == len(truth), f"개수 {n} · 열거 {len(listed)} · 진리 {len(truth)}"
    assert "pay" not in listed, f"★입력이 있는 축(pay 0/1)이 「입력이 0인 축」에 열거됐다: {why!r}"


@pytest.mark.parametrize("astate", ["starved", "judged"])
def test_no_zero_input_clause_when_every_axis_has_input(astate: str) -> None:
    """★특이도 — 모든 축에 입력이 있으면 그 절이 **아예 없어야** 한다.

    위양성도 결함이다: 「입력이 0인 축 **0개**(lat 1/9 pay 2/3)」는 **없는 사실을 암시**한다.
    """
    m = _probe()
    assert not _zero_axes(AX_ALL_INPUT), "★공허 방지 — 픽스처에 입력 0 축이 있으면 이 검사는 무의미"
    why = m.analysis_verdict(astate, "0", AX_ALL_INPUT)[1]
    assert _claim(why) is None, f"★입력 0 축이 없는데 그 절이 나왔다: {why!r}"


def test_judged_and_starved_both_surface_starving_axes() -> None:
    """★같은 사실을 **두 분기가 모두** 말한다 — 「축을 절반에만 걸었다」 재발 방지."""
    m = _probe()
    for astate in ("starved", "judged"):
        why = m.analysis_verdict(astate, "3", AX_MIXED)[1]
        assert _claim(why) is not None, f"{astate} 분기가 입력 0 축을 말하지 않는다: {why!r}"


def test_kind_is_not_escalated_by_starving_axes() -> None:
    """★`kind` 는 **안 올린다**. 올리면 상시 경보가 된다(이 저장소가 실측으로 기각한 길).

    ★이것이 **위양성 대조군**이다 — 사유가 늘어도 종료코드 빈도는 불변이어야 한다.
    """
    m = _probe()
    assert m.analysis_verdict("judged", "3", AX_MIXED)[0] == "ok"
    assert m.analysis_verdict("judged", "0", AX_MIXED)[0] == "obs"
    assert m.analysis_verdict("judged", "3", AX_ALL_INPUT)[0] == "ok"
    # 기존 락과 같은 픽스처(두 축 다 입력 있음) — 값이 안 바뀌어야 한다
    assert m.analysis_verdict("judged", "0", "lat 0/19 pay 0/1")[0] == "obs"
    assert m.analysis_verdict("judged", "3", "lat 0/19 pay 0/1")[0] == "ok"


def test_six_inputs_give_six_distinct_reasons() -> None:
    """★두 모집단이 아니라 **여섯**이 서로 다른 사유를 내는가(하나로 접히면 이 함수는 장식)."""
    m = _probe()
    reasons = {
        m.analysis_verdict("judged", ins, ax)[1]
        for ax in (AX_MIXED, AX_ALL_INPUT, "fal 0/0 lat 0/0")
        for ins in ("3", "0")
    }
    assert len(reasons) == 6, f"사유가 접혔다({len(reasons)}/6): {sorted(reasons)}"


# ── ② 배선 — 락이 원리적으로 못 보는 자리라 **따로** 둔다 ──────────────────────

def test_analysis_section_is_callable_outside_the_ctrl_gate() -> None:
    """★판정 절이 **함수로 분리**돼 `ctrl` 게이트 밖에서 불릴 수 있는가.

    종전엔 `elif [ "${ctrl:-0}" -eq 0 ]` **안**에 있어 라이브(`ctrl=6`)에서 **한 번도 안 불렸다**.
    """
    out = subprocess.run(
        ["bash", "-c", f". '{SCRIPT}' --verdict-lib >/dev/null 2>&1; type -t analysis_and_schedule_section"],
        capture_output=True, text=True, timeout=60,
    )
    assert out.stdout.strip() == "function", (
        "★분석/스케줄 절이 함수로 분리돼 있지 않다(게이트 안으로 되돌아갔을 수 있다): "
        f"{out.stdout!r} {out.stderr[:200]!r}"
    )
    src = SCRIPT.read_text(encoding="utf-8")
    # ★호출이 `fi` **뒤**(게이트 밖)에 있는가 — 정의 줄은 제외하고 센다.
    calls = [i for i, ln in enumerate(src.splitlines())
             if ln.strip() == "analysis_and_schedule_section"]
    assert calls, "★함수는 정의됐는데 **부르는 곳이 없다**(소비처 0)"


def test_verdict_receives_total_insights_not_one_type() -> None:
    """★호출부가 넘기는 인자 — `ctrl`(한 유형)이 아니라 `AINS`(전체)여야 한다.

    `ctrl` 은 `latency_regression` 24h 수이고 커버리지 축은 넷이다. 라이브 24h 는
    `latency_baseline` 40 : `latency_regression` 6 이라 **judged + ctrl=0 이 도달 가능**했고,
    그때 「판정했다는데 24h 창이 비었다」를 냈다 — **바로 윗줄이 인사이트 수를 찍는데도.**
    """
    src = SCRIPT.read_text(encoding="utf-8")
    call = [ln for ln in src.splitlines() if "analysis_verdict_of" in ln and "AV=" in ln]
    assert call, "★조회기 사망 — 호출부를 못 찾았다"
    assert 'AINS' in call[0], f"★호출부가 전체 인사이트 수를 안 넘긴다: {call[0].strip()!r}"
    assert '${ctrl' not in call[0], f"★호출부가 아직 ctrl 을 넘긴다: {call[0].strip()!r}"


# ── ③ 남은 부채 — 초록 안에 드러낸다 ──────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason=(
    "★부채 — 「입력이 0인 축」과 「하한 미달 축」을 사유가 **구분해 말하지만**, "
    "그것이 얼마나 오래 지속됐는지(지속 시간)는 말하지 못한다. "
    "`analysis_verdict` 는 지속 시간을 받지 않고, 프로브는 TTL 을 못 읽는다. "
    "★`starved` 전용이던 이 부채가 `judged` 에도 그대로 있다 — 같은 커밋에 적는다."
))
def test_reason_says_how_long_the_axis_has_been_starving() -> None:
    m = _probe()
    why = m.analysis_verdict("judged", "3", AX_MIXED)[1]
    assert re.search(r"\d+\s*(분|시간|일)", why), why
