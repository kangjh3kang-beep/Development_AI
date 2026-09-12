"""스케줄 축 — ★**「잡만 죽음」과 「틱 루프 죽음」을 가른다.**

종전에는 둘이 **같은 모양**이었다(어느 표면에도 안 나왔다):
  ① 틱은 도는데 어떤 잡의 실행만 죽음 → 그 잡 워터마크만 영구 지연 · 스냅샷은 **신선**
  ② 틱 루프 자체가 죽음               → 스냅샷도 **같이 낡음**

★이 파일이 생긴 계기는 **내가 오독한 사건**이다(2026-09-12 13:11Z):
  `growth_last_run.learn` 9,471분 전을 보고 「6.6일째 멈췄다」고 의심했는데
  `JOB_SPECS["learn"]` 주기가 **10080분(7일)** 이라 정상이었다.
  ***측정자가 곧 오독자였다 — 경과만으로는 못 가른다.***
"""

import ast
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]            # …/propai-platform
_PROBE = _ROOT / "scripts" / "monitor" / "growth_stale_producer_probe.py"
_DASH = _ROOT / "scripts" / "monitor" / "integrator_dashboard.sh"

_spec = importlib.util.spec_from_file_location("_probe_sched", _PROBE)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

NOW = datetime(2026, 9, 12, 13, 11, tzinfo=timezone.utc)
LIVE_JOBS = "analyze_7/60_heal_6/10_correct_6/15_improve_268/1440_learn_9471/10080"


def _iso(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


def test_five_populations_give_five_distinct_verdicts():
    """★하나로 접히면 이 변경은 장식이다 — 다섯 입력이 **서로 다른 사유**를 낸다."""
    cases = {
        "정상": (_iso(1), LIVE_JOBS, "-"),
        "잡만죽음": (_iso(1), LIVE_JOBS, "improve"),
        "틱죽음": (_iso(30), LIVE_JOBS, "improve"),
        "스냅샷없음": ("-", "-", "-"),
        "at불가": ("zzz", LIVE_JOBS, "-"),
    }
    out = {k: probe.schedule_verdict(*v, NOW) for k, v in cases.items()}
    kinds = {k: v[0] for k, v in out.items()}
    assert kinds["정상"] == "ok"
    assert kinds["잡만죽음"] == "obs"
    assert kinds["틱죽음"] == "obs"
    assert kinds["스냅샷없음"] == "unknown"
    assert kinds["at불가"] == "unknown"
    reasons = [v[1] for v in out.values()]
    assert len(set(reasons)) == len(reasons), (
        f"사유가 겹친다 — 사람을 같은 곳으로 보낸다: {reasons}"
    )


def test_job_dead_and_tick_dead_are_different_reasons():
    """★핵심 판별 — 같은 `overdue` 인데 **스냅샷 나이**가 둘을 가른다."""
    _, why_job = probe.schedule_verdict(_iso(1), LIVE_JOBS, "improve", NOW)
    _, why_tick = probe.schedule_verdict(_iso(30), LIVE_JOBS, "improve", NOW)
    assert why_job != why_tick
    assert "틱은 돌고" in why_job, why_job
    assert "틱 루프" in why_tick, why_tick
    # 공허 방지: 두 문장이 실제로 다른 곳을 가리키는가
    assert "지연된 잡" in why_job and "지연된 잡" not in why_tick


def test_learn_at_6_6_days_is_not_flagged_when_producer_says_so():
    """라이브 그대로(`learn 9471/10080`)면 **정상**이다 — 내가 오독한 그 값."""
    kind, why = probe.schedule_verdict(_iso(1), LIVE_JOBS, "-", NOW)
    assert kind == "ok", why
    assert "9471/10080" in why, "경과/주기를 사유에 싣지 않으면 사람이 또 SSOT 를 찾아간다"


def test_missing_snapshot_is_unknown_not_ok():
    """발행이 끊기면 **초록이 아니라 「확인 불가」** 여야 한다(조용한 초록 금지)."""
    kind, _ = probe.schedule_verdict("-", "-", "-", NOW)
    assert kind == "unknown"


def test_stale_tolerance_is_not_a_copy_of_an_ssot():
    """관용치는 **프로브 로컬** 상수다 — SSOT 사본이 아님을 값으로 못 박는다."""
    assert probe.SCHEDULE_STALE_MIN == 10


def test_probe_actually_reads_the_schedule_key():
    """★**배선** — 순수 함수만 있고 부르는 곳이 없으면 그게 「소비처 0」이다."""
    tree = ast.parse(_PROBE.read_text(encoding="utf-8"))
    names = {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
    } | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    for need in ("SCHEDULE_SETTING_KEY", "schedule_fields", "schedule_verdict"):
        assert need in names, f"{need} 가 실행 경로에서 안 불린다(소비처 0)"


def test_dashboard_burns_the_probe_verdict_not_a_copy():
    """★셸이 규칙을 **다시 구현하지 않는다** — 프로브가 낸 `skind` 를 그대로 쓴다.

    산문으로 주면 받는 쪽마다 다르게 구현한다(이 저장소가 이미 값을 치른 형태다).
    """
    src = _DASH.read_text(encoding="utf-8")
    code = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "skind=" in code, "계기판이 프로브 판정을 안 읽는다"
    # ★셸이 자체 판정을 만들지 않았는가(재구현 금지)
    assert "SCHEDULE_STALE_MIN" not in code, "셸이 관용치를 다시 들고 있다 — 두 곳이 갈린다"
    for forbidden in ('case "$SJOBS"', 'case "$SKIND"'):
        assert forbidden not in code, f"셸이 자체 분기를 만들었다: {forbidden}"
    # 공허 방지 대조군 — 이 파일이 실제로 계기판인가
    assert "통합자 계기판" in src


def test_only_obs_raises_observation_unknown_does_not():
    """★**`obs` 만 관측으로 올린다 — `unknown` 은 안 올린다.**

    `unknown` 의 지배적 원인은 «API 가 아직 스냅샷을 발행 안 하는 버전» 이라,
    그걸 올리면 **상시 빨강**이 된다(이 저장소가 `#868` 에서 기각한 형태).
    ★대신 **진짜 고장 둘은 `obs`** 로 온다(틱 사망=낡음 · 잡 사망=overdue) —
      이 완화가 고장을 가리지 않는다는 것을 아래에서 **값으로** 확인한다.
    """
    code = "\n".join(
        ln for ln in _DASH.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#")
    )
    assert 'if [ "${SKIND:-unknown}" = "obs" ]; then OBS=1; fi' in code, code[-400:]
    assert '!= "ok"' not in code, "unknown 까지 올리면 배포 전 상시 빨강이 된다"
    # ★핵심 — 완화가 **고장을 가리지 않는가**(두 고장이 obs 로 오는가)
    assert probe.schedule_verdict(_iso(30), LIVE_JOBS, "-", NOW)[0] == "obs"       # 틱 사망
    assert probe.schedule_verdict(_iso(1), LIVE_JOBS, "improve", NOW)[0] == "obs"  # 잡 사망
    # 그리고 배포 전(스냅샷 없음)은 unknown 이라 조용하다 — 그러나 화면에는 찍힌다
    assert probe.schedule_verdict("-", "-", "-", NOW)[0] == "unknown"
    assert "SKIND" in code and "스케줄:" in _DASH.read_text(encoding="utf-8")


@pytest.mark.parametrize("bad", [None, "", 123, [], {"jobs": None}])
def test_schedule_fields_never_raises_on_junk(bad):
    """스냅샷이 깨져도 **터지지 않고** 부재로 떨어진다(계기판 전체가 죽으면 안 된다)."""
    sat, sjobs, soverdue = probe.schedule_fields(bad)
    assert (sat, sjobs, soverdue) == ("-", "-", "-") or sjobs == "-"
