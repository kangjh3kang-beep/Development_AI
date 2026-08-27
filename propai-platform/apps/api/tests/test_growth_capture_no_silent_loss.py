"""성장루프 **입력**이 조용히 사라지던 것을 잠근다.

## 왜 필요한가 (소스 실측 2026-08-27)

`flush_batch` 는 `_drain(limit)` 으로 큐에서 **`popleft()` 해서 빼낸 뒤** INSERT 한다.
실패하면 **되돌리지 않았다** — 코드가 스스로 그렇게 적어 뒀다:

    logger.warning("growth flush_batch 실패(%d건 유실): %s", len(params), ...)

flush 는 **5초마다 최대 500건**(지속 천장 100건/초)이고 **DB 가 죽으면 아예 안 빠진다.**
10분 장애면 **120회 시도 × 최대 500건**이다. 이 저장소는 그 길이의 DB 버스트를 기록했다.

★그리고 **드롭·유실을 세는 것이 하나도 없었다**(전수 확인 — 그 파일에 계수기 0건.
대조군: 다른 계수기도 없으므로 조회기 사망이 아니라 **진짜 부재**).
그래서 *"성장루프 데이터가 얼마나 사라졌나"* 에 **아무도 답할 수 없었다** —
하류 전체(인사이트·자가치유·효과기 발화 표면)가 `platform_events` 완전성을 가정하는데.

## ★이 파일이 태우는 **층** (변이를 한 층에만 넣지 않기 위해 먼저 적는다)

| # | 층 | 락 |
|---|---|---|
| 1 | 순수 계수 산출 | `test_loss_rate_is_none_when_nothing_flushed` 외 |
| 2 | `record_event` 오버플로 계수 | `test_overflow_is_counted_not_silent` |
| 3 | **`flush_batch` 실패 → 되돌림** | `test_failed_flush_requeues_instead_of_losing` |
| 4 | 재시도 상한 → 포기 계수 | `test_gives_up_after_cap_and_counts_it` |
| 5 | 상수 짝(`_FLUSH_INTERVAL_S` ↔ `main.py`) | `test_flush_interval_matches_the_actual_loop` |
| 6 | 응답 배선(`/growth/effectors`) | `test_effectors_response_carries_capture_health` |
| 7 | 렌더 | (프론트 `EffectorFiring.test.tsx`) |

★저장소 교훈: *"N/N CAUGHT 전에 **몇 개 층에** 넣었나를 물어라."* 바로 앞 PR 에서
여섯 변이가 전부 한 층 안이라 독립 리뷰가 **25중 20 생존**을 보였다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.growth import capture_service as cs

_API = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean():
    cs._reset_stats_for_test()
    yield
    cs._reset_stats_for_test()


class _FailingDb:
    """INSERT 가 항상 실패하는 세션(장애 재현)."""

    def __init__(self):
        self.rollbacks = 0

    async def execute(self, *a, **k):
        raise RuntimeError("DB down")

    async def commit(self):  # pragma: no cover - 도달하면 테스트가 틀린 것
        raise AssertionError("실패 경로인데 commit 이 불렸다")

    async def rollback(self):
        self.rollbacks += 1


class _OkDb:
    async def execute(self, *a, **k):
        return None

    async def commit(self):
        return None

    async def rollback(self):  # pragma: no cover
        return None


def _fill(n: int) -> None:
    for i in range(n):
        cs._QUEUE.append({"event_id": f"e{i}", "event_type": "t", "created_at": None})


# ═══════════════════════════════════════════════════════════════════════════
# 층 3 — ★핵심: 실패해도 **잃지 않는다**
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_failed_flush_requeues_instead_of_losing() -> None:
    """★일시 장애에서 **한 건도 잃지 않는다.**

    되살리는 변이: `appendleft` 되돌리기를 지우면 종전처럼 `_drain` 이 빼낸 것이
    그대로 사라진다 — 코드가 *"%d건 유실"* 이라 적던 그 동작.
    """
    _fill(300)
    db = _FailingDb()
    n = await cs.flush_batch(db, limit=200)

    assert n == 0, "실패인데 적재 건수를 돌려줬다"
    # ★큐가 원래대로다 — 이게 이 PR 의 전부다.
    assert len(cs._QUEUE) == 300, f"★{300 - len(cs._QUEUE)}건이 사라졌다"
    assert cs._STATS["requeued"] == 200
    assert cs._STATS["flush_failures"] == 1
    # ★되돌린 것은 **유실이 아니다** — 뭉개지 않는다.
    assert cs._STATS["dropped_after_retry"] == 0
    assert cs.capture_status()["lost_total"] == 0
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_requeue_preserves_fifo_order() -> None:
    """★되돌릴 때 **순서를 지킨다** — 뒤집으면 오래된 것이 뒤로 밀려 굶는다."""
    _fill(5)
    before = [r["event_id"] for r in cs._QUEUE]
    await cs.flush_batch(_FailingDb(), limit=3)
    after = [r["event_id"] for r in cs._QUEUE]
    assert after == before, f"★순서가 바뀌었다: {before} → {after}"


@pytest.mark.asyncio
async def test_success_clears_failure_streak_and_counts() -> None:
    """★두 모집단 — 성공과 실패가 **다른 값**을 남긴다."""
    _fill(10)
    await cs.flush_batch(_FailingDb(), limit=10)
    assert cs._consecutive_failures == 1
    ok = await cs.flush_batch(_OkDb(), limit=10)
    assert ok == 10
    assert cs._consecutive_failures == 0, "★성공했는데 연속실패가 안 풀렸다"
    assert cs._STATS["flushed"] == 10
    assert len(cs._QUEUE) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 층 4 — 상한에서 포기하되 **센다**
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_gives_up_after_cap_and_counts_it() -> None:
    """★한 배치가 영원히 실패하면 큐 앞을 막아 **새 이벤트가 영영 못 들어간다.**

    그래서 상한을 두되 **버린 사실을 센다**. 무한 재시도도, 조용한 폐기도 아니다.
    """
    _fill(10)
    db = _FailingDb()
    for _ in range(cs._MAX_FLUSH_RETRY):
        await cs.flush_batch(db, limit=10)
    # 아직 포기 전 — 전부 되돌아와 있다.
    assert len(cs._QUEUE) == 10
    assert cs._STATS["dropped_after_retry"] == 0

    await cs.flush_batch(db, limit=10)  # 상한 초과
    assert cs._STATS["dropped_after_retry"] == 10, "★포기했는데 세지 않았다"
    assert len(cs._QUEUE) == 0
    # ★포기 후 연속실패는 초기화된다 — 다음 배치가 즉시 포기되면 안 된다.
    assert cs._consecutive_failures == 0
    assert cs.capture_status()["lost_total"] == 10


def test_retry_cap_is_not_one() -> None:
    """★상한을 1 로 내리면 **종전과 같아진다**(일시 장애에 즉시 유실).

    이 상수는 되돌리기의 값어치를 정하는 값이다. 방향을 양쪽으로 건다.
    """
    assert cs._MAX_FLUSH_RETRY >= 6, (
        f"★{cs._MAX_FLUSH_RETRY} 회 — 5초 주기이므로 최소 30초는 버텨야 "
        "일시적 DB 장애에서 되돌리기가 의미를 갖는다"
    )
    assert cs._MAX_FLUSH_RETRY <= 120, "★너무 크면 잘못된 배치가 큐를 오래 막는다"


# ═══════════════════════════════════════════════════════════════════════════
# 층 2 — 오버플로도 **센다**
# ═══════════════════════════════════════════════════════════════════════════
def test_overflow_is_counted_not_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """★`deque(maxlen=)` 은 **조용히** 가장 오래된 것을 버린다 — 그것을 센다.

    되살리는 변이: 계수 분기를 지우면 종전처럼 유실이 **관측 불가**가 된다.
    """
    from collections import deque

    monkeypatch.setattr(cs, "_MAX_QUEUE", 3)
    monkeypatch.setattr(cs, "_QUEUE", deque(maxlen=3))
    for i in range(5):
        cs.record_event("page_view", {"event_id": f"x{i}"})
    assert len(cs._QUEUE) == 3
    assert cs._STATS["dropped_overflow"] == 2, (
        f"★2건이 밀려났는데 {cs._STATS['dropped_overflow']} 로 셌다"
    )
    assert cs.capture_status()["lost_total"] >= 2


# ═══════════════════════════════════════════════════════════════════════════
# 층 1 — 계수 산출
# ═══════════════════════════════════════════════════════════════════════════
def test_loss_rate_is_none_when_nothing_flushed() -> None:
    """★분모가 0 이면 `None` 이다 — **0.0 이 아니다.**

    "잃은 게 없다"와 "아직 아무것도 안 실었다"는 **다른 말**이다. 0.0 으로 내면
    화면이 *"유실률 0%"* 라고 **거짓 안심**을 준다.
    """
    st = cs.capture_status()
    assert st["loss_rate_pct"] is None
    assert st["lost_total"] == 0


@pytest.mark.asyncio
async def test_loss_rate_uses_lost_over_lost_plus_flushed() -> None:
    """★유실률의 **분모**가 맞는가 — 두 모집단으로 가른다."""
    _fill(10)
    await cs.flush_batch(_OkDb(), limit=10)      # flushed 10
    cs._STATS["dropped_overflow"] = 10           # lost 10
    st = cs.capture_status()
    assert st["lost_total"] == 10
    assert st["loss_rate_pct"] == pytest.approx(50.0), st["loss_rate_pct"]
    # 대조군: 유실이 없으면 0.0(=None 이 아니다 — 분모가 있으므로)
    cs._STATS["dropped_overflow"] = 0
    assert cs.capture_status()["loss_rate_pct"] == 0.0


def test_requeued_is_not_counted_as_loss() -> None:
    """★되돌린 것을 유실에 섞으면 **정상 복구가 장애로 보인다**(위양성도 결함)."""
    cs._STATS["requeued"] = 1000
    st = cs.capture_status()
    assert st["lost_total"] == 0, "★되돌린 것을 유실로 셌다"
    assert st["requeued"] == 1000


# ═══════════════════════════════════════════════════════════════════════════
# 층 5 — 상수 짝: 천장 계산이 거짓이 되지 않게
# ═══════════════════════════════════════════════════════════════════════════
def test_flush_interval_matches_the_actual_loop() -> None:
    """★`max_sustained_per_sec` 은 **`main.py` 의 실제 주기**에 의존한다.

    둘이 갈리면 화면이 *"천장 100건/초"* 라고 **거짓**을 말한다.
    소스에서 **파생**해 대조한다(손으로 옮겨 적지 않는다).
    """
    src = (_API / "main.py").read_text(encoding="utf-8")
    # 성장 flush 루프 안의 sleep 을 구조로 집는다(주석·다른 루프에 걸리지 않게).
    i = src.find("_growth_flush_loop")
    assert i > 0, "★flush 루프를 못 찾았다 — 추출기가 죽었다(위반 아님)"
    seg = src[i : i + 1200]
    m = re.search(r"sleep\((\d+(?:\.\d+)?)\)", seg)
    assert m, f"★루프에서 sleep 을 못 찾았다: {seg[:200]!r}"
    assert float(m.group(1)) == float(cs._FLUSH_INTERVAL_S), (
        f"★main.py 주기 {m.group(1)}초 ≠ 상수 {cs._FLUSH_INTERVAL_S}초 — "
        "천장 계산이 거짓이 된다"
    )
    assert cs.capture_status()["max_sustained_per_sec"] == (
        cs._FLUSH_LIMIT // cs._FLUSH_INTERVAL_S
    )


# ═══════════════════════════════════════════════════════════════════════════
# 층 6 — 응답 배선
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_effectors_response_carries_capture_health() -> None:
    """★수집 건강이 **효과기 표면과 같은 응답에** 실린다.

    따로 두면 아무도 대조하지 않는다 — 그 표의 모든 결론이 `platform_events`
    완전성을 가정하는데, 유실이 있으면 `never_fired` 도 `dormant` 도 못 믿는다.

    되살리는 변이: `"capture"` 키를 지우면 화면이 그 사실을 말할 수 없게 된다.
    """
    from app.services.growth import effector_firing as ef

    class _Db:
        async def execute(self, *a, **k):
            class _R:
                @staticmethod
                def fetchall():
                    return []

            return _R()

    out = await ef.firing_status(_Db())
    assert "capture" in out, "★수집 건강이 응답에 없다"
    cap = out["capture"]
    for k in ("queue_depth", "lost_total", "loss_rate_pct", "max_sustained_per_sec"):
        assert k in cap, f"★{k} 가 빠졌다"
    # ★#917 이 넣은 키도 **같이** 살아 있어야 한다(머지에서 한쪽을 고르지 않았는지).
    assert "telemetry_since" in out


# ═══════════════════════════════════════════════════════════════════════════
# ★기계적 변이(`scripts/mutate_changed.py`) 생존분 봉합
#
# 손으로 고른 9종(7개 층)을 전부 잡은 **뒤에도** 도구가 진단 필드 4개의 생존을 찾았다:
# `max_queue` · `flush_limit` · `consecutive_failures` · `max_flush_retry`.
# 프론트가 **실제로 그리는 값**인데(「큐 12/10000 · 천장 100건/초」) 백엔드는
# 하나도 단언하지 않았다 — 지우면 화면에 `undefined` 가 뜬다.
# ═══════════════════════════════════════════════════════════════════════════
#: `capture_status()` 가 **반드시** 내는 키 — 프론트가 소비하는 계약이다.
#:
#: ★파생형으로 만들 수 없다: 이 집합 **자체가** 계약이므로 구현에서 뽑으면
#:   무엇을 바꿔도 통과하는 순환이 된다(자기 상수를 단언하는 락). 그래서 **못 박는다**.
_CONTRACT_KEYS = frozenset({
    "queue_depth", "max_queue", "flush_limit", "max_sustained_per_sec",
    "dropped_overflow", "dropped_after_retry", "requeued",
    "flush_failures", "flushed",
    "consecutive_failures", "max_flush_retry",
    "lost_total", "loss_rate_pct",
})


def test_capture_status_contract_keys() -> None:
    """★응답 계약을 못 박는다 — 필드가 사라지면 화면이 `undefined` 를 그린다."""
    got = set(cs.capture_status())
    missing = _CONTRACT_KEYS - got
    extra = got - _CONTRACT_KEYS
    assert not missing, f"★계약 필드가 사라졌다(화면이 깨진다): {sorted(missing)}"
    assert not extra, f"★계약에 없는 필드가 늘었다 — 계약을 갱신하라: {sorted(extra)}"


def test_diagnostic_fields_carry_real_values_not_placeholders() -> None:
    """★필드가 **있는 것**과 **맞는 값인 것**은 다른 명제다.

    기계 변이는 `"max_queue": _MAX_QUEUE` → `"max_queue": "x"` 같은 값 바꿔치기도 넣는다.
    키 존재만 보면 그것이 통과한다.
    """
    st = cs.capture_status()
    assert st["max_queue"] == cs._MAX_QUEUE
    assert st["flush_limit"] == cs._FLUSH_LIMIT
    assert st["max_flush_retry"] == cs._MAX_FLUSH_RETRY
    assert st["consecutive_failures"] == cs._consecutive_failures
    # ★두 모집단 — 값이 바뀌면 응답도 바뀐다(상수 복사가 아니라 실값을 읽는지).
    cs._consecutive_failures = 7
    assert cs.capture_status()["consecutive_failures"] == 7
    cs._consecutive_failures = 0
    assert cs.capture_status()["consecutive_failures"] == 0
