"""스케줄 스냅샷 — **「경과」만으로는 정상과 정지를 못 가른다**를 잠근다.

★왜 이 파일이 있나 (실측 2026-09-12 13:11Z · 측정자가 곧 오독자다):
  `growth_last_run.learn` 이 **9,471분 전**이었고 나는 그것을 보고 *"6.6일째 멈췄다"* 고
  의심했다. `JOB_SPECS["learn"].period_minutes` 는 **10080(7일)** 이라 **정상**이었다.
  같은 「7일 전」이 `learn` 에겐 정상이고 `analyze`(60분)에겐 **대형 장애**다.
  ⇒ 이 파일의 중심 단언은 ***같은 경과값이 잡에 따라 다른 판정을 내는가*** 다.
    하나로 접히면 이 변경은 장식이다.
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.api.app.services.growth.schedule import (
    JOB_SPECS,
    SCHEDULE_SNAPSHOT_KEY,
    compute_due,
    schedule_snapshot_payload,
    watermark_key,
)

NOW = datetime(2026, 9, 12, 13, 11, 0, tzinfo=UTC)


def _jobs_map(payload):
    """`"analyze 7/60 heal 6/10"` → `{"analyze": (7, 60), ...}`."""
    out = {}
    for tok in str(payload["jobs"]).split():
        if "/" not in tok:
            out[tok] = None          # 잡 이름 토큰
            last = tok
            continue
        a, b = tok.split("/", 1)
        out[last] = (a, b)
    return out


def test_population_is_derived_from_job_specs_not_a_hand_list():
    """모집단을 손으로 적지 않는다 — 잡을 추가하면 자동으로 들어온다."""
    assert len(JOB_SPECS) >= 5, "잡 표가 줄었다 — 아래 검사들이 공허해진다"
    observed = [(j, NOW - timedelta(minutes=1)) for j in JOB_SPECS]
    got = _jobs_map(schedule_snapshot_payload(observed, NOW))
    assert set(got) == set(JOB_SPECS), f"스냅샷이 일부 잡을 뺐다: {set(JOB_SPECS) - set(got)}"


def test_same_elapsed_two_verdicts_learn_ok_analyze_overdue():
    """★두 모집단 — **같은 9,471분**이 `learn` 엔 정상이고 `analyze` 엔 지연이다.

    이 단언이 없으면 「경과만 싣는」 구현도 통과한다(그게 고치려는 결함이다).
    """
    elapsed = timedelta(minutes=9471)
    p = schedule_snapshot_payload(
        [("learn", NOW - elapsed), ("analyze", NOW - elapsed)], NOW,
    )
    overdue = str(p["overdue"]).split()
    assert "analyze" in overdue, f"analyze(60분)가 9471분 경과인데 지연이 아니다: {p}"
    assert "learn" not in overdue, f"learn(10080분)이 9471분 경과인데 지연으로 찍혔다: {p}"
    # ★그리고 **주기가 값에 실려야** 한다 — 없으면 사람이 다시 SSOT 를 찾아가야 한다.
    got = _jobs_map(p)
    assert got["learn"] == ("9471", "10080"), got
    assert got["analyze"] == ("9471", "60"), got


def test_never_seen_is_not_zero_elapsed():
    """워터마크를 본 적 없음(`-`)과 「방금 돌았음(0)」은 다른 사실이다."""
    p = schedule_snapshot_payload([("analyze", None), ("heal", NOW)], NOW)
    got = _jobs_map(p)
    assert got["analyze"] == ("-", "60"), got
    assert got["heal"] == ("0", "10"), got
    assert "analyze" not in str(p["overdue"]).split(), "본 적 없음을 지연으로 단정했다"


def test_clock_rollback_agrees_with_is_due():
    """시계가 뒤로 가면 `is_due` 는 참을 낸다 — 스냅샷도 같은 값이어야 한다.

    두 곳이 갈리면 계기판이 「돌 때가 됐다」의 **반대**를 말한다.
    """
    p = schedule_snapshot_payload([("analyze", NOW + timedelta(minutes=5))], NOW)
    assert "analyze" in str(p["overdue"]).split(), p


def test_value_is_not_a_list():
    """`routers/growth.py:452` 실측 — 활성 플래그 `value` 가 list 면 **HTTP 500** 이다."""
    p = schedule_snapshot_payload([("analyze", NOW)], NOW)
    assert isinstance(p, dict), type(p)
    for k, v in p.items():
        assert not isinstance(v, list), f"{k} 가 list 다 — 읽기가 500 으로 죽는다"


def test_job_names_are_not_truncated():
    """접두를 줄이면 접두가 겹치는 잡이 생기는 순간 **두 잡이 한 칸으로 뭉친다**."""
    observed = [(j, NOW) for j in JOB_SPECS]
    got = _jobs_map(schedule_snapshot_payload(observed, NOW))
    for j in JOB_SPECS:
        assert j in got, f"{j} 가 요약에 온전한 이름으로 없다: {got}"


class _FakeSettings:
    """`get_setting`/`set_setting` 만 흉내내는 가짜. 무엇이 쓰였는지 기록한다."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.writes: list[tuple[str, object]] = []

    async def get_setting(self, _db, key):
        return self.store.get(key)

    async def set_setting(self, _db, key, value, *, scope="global",
                          ttl_expires_at=None, updated_by=None):
        self.store[key] = value
        self.writes.append((key, value))
        return True


@pytest.mark.asyncio
async def test_compute_due_actually_publishes_the_snapshot():
    """★**배선**을 잠근다 — 순수 함수만 잠그면 부르는 곳을 지워도 초록이다.

    이 저장소가 반복해서 데인 *"배선 미변이"* 다(`compute_due` 독스트링이 그 사고를 적고 있다).
    """
    fake = _FakeSettings({watermark_key(j): NOW.isoformat() for j in JOB_SPECS})
    await compute_due(None, fake, NOW)
    keys = [k for k, _ in fake.writes]
    assert SCHEDULE_SNAPSHOT_KEY in keys, f"스냅샷을 발행하지 않았다: {keys}"
    payload = dict(fake.writes)[SCHEDULE_SNAPSHOT_KEY]
    assert set(_jobs_map(payload)) == set(JOB_SPECS), payload


@pytest.mark.asyncio
async def test_publishing_does_not_change_the_due_verdict():
    """관측만 추가한다 — 판정은 그대로여야 한다(회귀가 아님의 근거)."""
    stale = (NOW - timedelta(days=99)).isoformat()
    fake = _FakeSettings({watermark_key(j): stale for j in JOB_SPECS})
    due = await compute_due(None, fake, NOW)
    assert set(due) == set(JOB_SPECS)
    assert all(due.values()), f"99일 경과인데 발화하지 않는 잡이 있다: {due}"
