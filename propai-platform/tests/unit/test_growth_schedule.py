"""자가성장 스케줄러의 실행 시점 판정 계약.

## 왜 이 테스트가 있나

종전 스케줄러는 `tick % N` 이라는 **인메모리 카운터**로 주기를 셌다. 컨테이너가 새로 뜨면
0으로 돌아가고 밀린 잡을 따라잡지도 못해서, `learn`(7일)·`improve`(24h)는 **컨테이너가
그만큼 연속으로 살아 있어야** 발화했다. 이 저장소는 배포마다 컨테이너를 새로 만든다.

그 결함이 **오래 안 보였던 이유**는 판정이 스케줄러 루프 안에 인라인으로 박혀 있어
아무도 그 판정만 따로 태울 수 없었기 때문이다. 그래서 판정을 순수 함수로 꺼냈고,
이 파일이 그것을 **직접** 태운다.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from apps.api.app.services.growth.schedule import (
    JOB_SPECS,
    compute_due,
    is_due,
    parse_watermark,
    should_seed,
    watermark_key,
)

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)


def test_job_table_is_not_empty():
    """★공허 진리 가드 — 표가 비면 아래 파라미터 테스트가 통째로 사라진다."""
    assert len(JOB_SPECS) >= 5, "잡 표가 줄었다 — 아래 검사들이 공허해진다"
    assert {"analyze", "heal", "correct", "improve", "learn"} <= set(JOB_SPECS)


@pytest.mark.parametrize("job", sorted(JOB_SPECS))
def test_runs_when_period_elapsed(job):
    period = JOB_SPECS[job].period_minutes
    last = NOW - timedelta(minutes=period)
    assert is_due(job, last, NOW) is True, f"{job}: 주기가 꼭 찼는데 안 돈다"


@pytest.mark.parametrize("job", sorted(JOB_SPECS))
def test_does_not_run_before_period(job):
    """★부재 단언에는 짝이 있어야 한다 — 위 양성과 같은 축에서 음성을 본다."""
    period = JOB_SPECS[job].period_minutes
    last = NOW - timedelta(minutes=period - 1)
    assert is_due(job, last, NOW) is False, f"{job}: 주기 전인데 돈다"


def test_survives_restart_and_catches_up():
    """이 커밋의 핵심 — 종전 `tick` 방식이 **원리적으로 못 하던 것**.

    7일 주기 잡이 30일 전에 마지막으로 돌았다면, 컨테이너가 방금 떴더라도 **즉시** 돌아야
    한다. 종전에는 tick 이 0부터 다시 세서 **또 7일을 기다렸다**(그리고 그 전에 재배포되면
    영영 안 돈다).
    """
    long_ago = NOW - timedelta(days=30)
    assert is_due("learn", long_ago, NOW) is True, "밀린 주간 잡을 따라잡지 못한다"
    assert is_due("improve", long_ago, NOW) is True, "밀린 일배치를 따라잡지 못한다"


def test_unseen_watermark_splits_short_and_long_periods():
    """두 모집단이 **다른 값**을 내야 이 분기가 잠긴다.

    둘이 같은 값을 내면 `run_when_unseen` 배선을 끊어도 결과가 같아 변이가 살아남는다.
    """
    # 워터마크가 없을 때(첫 기동·DB 초기화)
    assert is_due("heal", None, NOW) is True, "짧은 주기가 첫 기동에 안 돈다"
    assert is_due("analyze", None, NOW) is True
    assert is_due("learn", None, NOW) is False, "주간 배치가 배포할 때마다 돈다"
    assert is_due("improve", None, NOW) is False

    # 그리고 긴 주기만 **기준점 찍기** 대상이다.
    assert should_seed("learn", None) is True
    assert should_seed("improve", None) is True
    assert should_seed("heal", None) is False, "짧은 주기까지 기준점만 찍으면 영영 안 돈다"

    # 워터마크가 있으면 기준점을 다시 찍지 않는다(음성대조).
    assert should_seed("learn", NOW) is False


def test_clock_going_backwards_does_not_stall():
    """경과가 음수여도 실행한다.

    NTP 보정 등으로 시계가 뒤로 가면, `elapsed >= period` 만 보는 구현은 **영원히 False**
    가 되어 잡이 멈춘다. 다시 도는 비용보다 멈추는 비용이 크다.
    """
    future = NOW + timedelta(days=3)
    assert is_due("learn", future, NOW) is True, "시계 보정 한 번에 잡이 멈춘다"


@pytest.mark.parametrize(
    "raw,expected_none",
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("깨진값", True),
        ("2026-08-22T12:00:00+00:00", False),
        ("2026-08-22T12:00:00Z", False),
        ("2026-08-22T12:00:00", False),  # tz 없으면 UTC 로 본다
    ],
)
def test_watermark_parsing_rejects_broken_values(raw, expected_none):
    got = parse_watermark(raw)
    assert (got is None) is expected_none, f"{raw!r} 파싱 결과가 기대와 다르다"
    if got is not None:
        assert got.tzinfo is not None, "naive datetime 이 새어나간다 — 비교가 터진다"


def test_watermark_keys_are_distinct_per_job():
    """한 잡의 기록 실패가 다른 잡을 막지 않으려면 키가 달라야 한다."""
    keys = {watermark_key(j) for j in JOB_SPECS}
    assert len(keys) == len(JOB_SPECS), "잡 키가 겹친다 — 서로의 워터마크를 덮어쓴다"
    assert watermark_key("learn") == "growth_last_run.learn"


def test_unknown_job_raises():
    """오타가 '안 도는 잡'으로 조용히 굳는 것을 막는다."""
    with pytest.raises(KeyError):
        is_due("존재하지않는잡", None, NOW)


def test_periods_match_previous_tick_design():
    """★동작을 바꾸지 않았다는 증거 — 종전 `tick % N` 의 N 을 그대로 옮겼다."""
    assert JOB_SPECS["analyze"].period_minutes == 60
    assert JOB_SPECS["heal"].period_minutes == 10
    assert JOB_SPECS["correct"].period_minutes == 15
    assert JOB_SPECS["improve"].period_minutes == 1440
    assert JOB_SPECS["learn"].period_minutes == 10080


# ── 배선 ────────────────────────────────────────────────────────────────────
#  ★순수 함수만 잠그면 **그걸 부르는 연결**이 통째로 뚫린다. 실측: 첫 시도에서 변이 검증이
#    `main.py` 의 읽기·판정 배선 **15줄 생존**을 보고했다(지워도 아무 테스트가 안 죽었다).
#    그래서 읽기·쓰기까지 `compute_due` 로 옮기고, 아래에서 **가짜 설정 API** 로 직접 태운다.


class _FakeSettings:
    """`get_setting`/`set_setting` 만 흉내내는 가짜. 무엇이 쓰였는지 기록한다."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.writes = []

    async def get_setting(self, _db, key, scope="global"):
        return self.store.get(key)

    async def set_setting(self, _db, key, value, *, scope="global",
                          ttl_expires_at=None, updated_by=None):
        self.store[key] = value
        self.writes.append((key, value, updated_by))
        return True


@pytest.mark.asyncio
async def test_compute_due_seeds_long_jobs_and_runs_short_ones_on_first_boot():
    """첫 기동 — 짧은 주기는 돌고, 긴 주기는 **기준점만** 찍힌다(두 모집단이 갈린다)."""
    fake = _FakeSettings()
    due = await compute_due(object(), fake, NOW)

    assert due["heal"] is True and due["analyze"] is True and due["correct"] is True
    assert due["learn"] is False and due["improve"] is False

    seeded = {k for k, _v, _u in fake.writes}
    assert seeded == {watermark_key("learn"), watermark_key("improve")}, (
        "긴 주기만 씨드해야 한다 — 짧은 주기까지 씨드하면 영영 안 돈다"
    )
    assert all(u and "seed" in u for _k, _v, u in fake.writes), "씨드 출처가 안 남는다"


@pytest.mark.asyncio
async def test_compute_due_reads_watermark_and_catches_up():
    """저장된 워터마크를 **실제로 읽어** 밀린 잡을 따라잡는다."""
    old = (NOW - timedelta(days=30)).isoformat()
    fresh = (NOW - timedelta(minutes=1)).isoformat()
    fake = _FakeSettings({
        watermark_key("learn"): old,      # 30일 전 → 따라잡아야
        watermark_key("heal"): fresh,     # 1분 전 → 아직
    })
    due = await compute_due(object(), fake, NOW)

    assert due["learn"] is True, "밀린 주간 잡을 못 따라잡는다 — 워터마크를 안 읽는다"
    assert due["heal"] is False, "1분 전에 돌았는데 또 돈다"
    # ★이미 워터마크가 있으면 씨드를 다시 쓰지 않는다(음성대조).
    assert watermark_key("learn") not in {k for k, _v, _u in fake.writes}


@pytest.mark.asyncio
async def test_compute_due_covers_every_job():
    """★공허 방지 — 표의 잡을 하나라도 빠뜨리면 그 잡은 영영 안 돈다."""
    due = await compute_due(object(), _FakeSettings(), NOW)
    assert set(due) == set(JOB_SPECS), "일부 잡이 판정에서 빠졌다"


def test_main_wiring_consumes_compute_due():
    """★`main.py` 가 실제로 `compute_due` 를 **호출**하고 그 결과로 잡을 고르는지.

    위 테스트들은 `compute_due` 를 직접 부르므로, `main.py` 가 그걸 안 쓰고 옛 `tick` 방식으로
    되돌아가도 전부 초록이다. 그 연결을 여기서 본다(임포트 줄이 아니라 **호출 형태**로).
    """
    main_py = Path(__file__).resolve().parents[2] / "apps" / "api" / "main.py"
    src = main_py.read_text(encoding="utf-8")
    # 주석/문자열을 제외하진 못하지만, 아래는 **호출 형태**라 주석 처리되면 사라진다.
    assert "sched.compute_due(" in src, "main.py 가 compute_due 를 호출하지 않는다"
    # ★`"_growth_due_map("` 만 보면 **`async def _growth_due_map(` 정의 줄**에 걸려,
    #   루프에서 호출을 통째로 지워도 통과한다(실측: 변이 검증에서 그 줄삭제가 생존했다).
    #   이 저장소가 반복해 데인 형태다 — 소스 가드는 **호출 형태**를 봐야 한다.
    assert "await _growth_due_map(" in src, "판정 헬퍼가 루프에서 **호출**되지 않는다"
    for job in JOB_SPECS:
        assert f'due.get("{job}"' in src, f"{job} 이 판정 결과에서 읽히지 않는다"
    # ★음성대조 — 옛 tick 방식이 되살아나면 잡는다.
    assert "tick % " not in src, "인메모리 tick 판정이 되살아났다"
