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
#: `capture_status()` 가 **반드시** 내는 키 — 응답 계약이다.
#:
#: ★파생형으로 만들 수 없다: 이 집합 **자체가** 계약이므로 구현에서 뽑으면
#:   무엇을 바꿔도 통과하는 순환이 된다(자기 상수를 단언하는 락). 그래서 **못 박는다**.
#:
#: ★★**종전 주석이 거짓이었다**(독립 적대 리뷰 실측 2026-08-27): *"프론트가 실제로 그리는
#:   값이라 지우면 화면에 `undefined` 가 뜬다"* 라고 `flush_limit`·`consecutive_failures`·
#:   `max_flush_retry` 를 지목했는데, **프론트는 그 셋을 안 읽는다**(14키 중 **6키**가 미소비).
#:   화면이 그리는 것은 `queue_depth`·`max_queue`·`max_sustained_per_sec`·`requeued`·
#:   `flush_failures`·`lost_total`·`loss_rate_pct`·`scope` 여덟이다.
#:   → 근거를 사실로 고친다: 나머지 여섯은 **화면이 아니라 운영자·조사자가 API 로 읽는**
#:     진단 필드다. 그래도 계약이므로 잠근다 — 다만 **이유를 바르게 적는다**(§C-10).
_CONTRACT_KEYS = frozenset({
    # 화면이 그리는 것
    "queue_depth", "max_queue", "max_sustained_per_sec",
    "requeued", "flush_failures", "lost_total", "loss_rate_pct", "scope",
    # API 로만 읽는 진단 필드
    "flush_limit", "dropped_overflow", "dropped_after_retry", "flushed",
    "consecutive_failures", "max_flush_retry", "cancelled_requeued",
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


@pytest.mark.asyncio
async def test_requeue_overflow_is_also_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    """★**되돌리기 경로 자체가 조용히 잃을 수 있다** — 기계 변이가 그 자리를 짚었다.

    `_drain` 이 빼낸 사이에 새 이벤트가 큐를 채우면, 되돌릴 때 `maxlen` 이
    가장 오래된 것을 밀어낸다. 그것을 안 세면 **이 PR 이 고치려던 결함이
    바로 그 수리 경로 안에서 재발**한다.

    실제 경로를 태운다: `execute` 가 **터지기 전에** 큐를 채워 그 상황을 만든다.
    """
    from collections import deque

    monkeypatch.setattr(cs, "_MAX_QUEUE", 5)
    q: deque = deque(maxlen=5)
    monkeypatch.setattr(cs, "_QUEUE", q)
    for i in range(5):
        q.append({"event_id": f"old{i}", "event_type": "t", "created_at": None})

    class _FillThenFail:
        async def execute(self, *a, **k):
            # ★drain 직후 새 이벤트가 들어온 상황을 만든다(큐가 다시 가득).
            for j in range(3):
                q.append({"event_id": f"new{j}", "event_type": "t", "created_at": None})
            raise RuntimeError("DB down")

        async def commit(self):  # pragma: no cover
            raise AssertionError("실패 경로")

        async def rollback(self):
            return None

    await cs.flush_batch(_FillThenFail(), limit=3)   # old0~2 를 빼고, new0~2 가 들어옴
    # 큐는 maxlen=5 이고 되돌릴 3건이 더 오므로 **밀려나는 것이 생긴다**.
    assert len(q) == 5
    assert cs._STATS["dropped_overflow"] > 0, (
        "★되돌리는 중에 밀려났는데 세지 않았다 — 수리 경로가 조용히 잃는다"
    )
    # ★그리고 그것은 **유실**로 집계돼야 한다(되돌림과 구별).
    st = cs.capture_status()
    assert st["lost_total"] == cs._STATS["dropped_overflow"]
    assert st["requeued"] == 3, "되돌린 건수는 별도로 남는다"


def test_stats_scope_is_declared_as_process_local() -> None:
    """★이 수치는 **하한**이다 — `_STATS` 가 프로세스 로컬이라 재시작하면 0 이 된다.

    `lost_total == 0` 은 *"이 프로세스가 시작한 뒤로는 못 봤다"* 이지
    *"유실이 없었다"* 가 아니다. 그 구분을 놓치면 화면의 「유실 없음」이 **거짓 안심**이 된다.

    ★계획서에 *"코드에 적었다"* 고 썼는데 **처음엔 안 적혀 있었다** — 선언과 산출물이
      갈리면 다음 사람이 이미 안전하다고 오독한다(§F-24). 그래서 락으로 잠근다.
    """
    import inspect

    doc = inspect.getdoc(cs.capture_status) or ""
    assert "하한" in doc, "★하한이라는 사실이 문서화돼 있지 않다"
    assert "프로세스 로컬" in doc
    # ★주석은 화면에 안 보인다 — **응답에도** 실려야 한다.
    assert cs.capture_status()["scope"] == "process_local"


# ═══════════════════════════════════════════════════════════════════════════
# ★독립 적대 리뷰 REVISE 봉합 (2026-08-27) — 리뷰가 뚫은 자리를 직접 태운다
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_cancellation_requeues_and_reraises() -> None:
    """★리뷰 #1(CRITICAL) — `except Exception` 은 `CancelledError` 를 **못 잡는다**.

    `asyncio.CancelledError` 는 `BaseException` 전용이라(실측 확인), 종료 시
    `main.py` 가 `cancel()` 을 걸면 `_drain` 이 이미 빼낸 배치가 **어떤 계수기에도
    안 잡힌 채 사라졌다** — 이 PR 의 논지가 **수리 안에서 재현**된 자리다.

    되살리는 변이: `except BaseException` → `except Exception` 이면 이 테스트가 죽는다.
    """
    import asyncio

    class _CancelDb:
        async def execute(self, *a, **k):
            raise asyncio.CancelledError()

        async def commit(self):  # pragma: no cover
            raise AssertionError("취소 경로")

        async def rollback(self):  # pragma: no cover
            return None

    _fill(50)
    with pytest.raises(asyncio.CancelledError):
        await cs.flush_batch(_CancelDb(), limit=50)

    # ★①한 건도 안 잃었다 ②그 사실이 **세어졌다** ③취소는 **삼키지 않았다**(위 raises)
    assert len(cs._QUEUE) == 50, f"★{50 - len(cs._QUEUE)}건이 취소로 사라졌다"
    assert cs._STATS["cancelled_requeued"] == 50
    assert cs.capture_status()["lost_total"] == 0


@pytest.mark.asyncio
async def test_cancellation_is_counted_separately_from_db_failure() -> None:
    """★두 모집단 — 취소와 DB 실패는 **다른 사실**이다(같은 계수기로 뭉개지 않는다)."""
    import asyncio

    class _CancelDb:
        async def execute(self, *a, **k):
            raise asyncio.CancelledError()

        async def commit(self):  # pragma: no cover
            raise AssertionError

        async def rollback(self):  # pragma: no cover
            return None

    _fill(10)
    with pytest.raises(asyncio.CancelledError):
        await cs.flush_batch(_CancelDb(), limit=10)
    assert cs._STATS["cancelled_requeued"] == 10
    # ★취소는 flush **실패**가 아니다 — 연속실패 카운터를 올리면 상한이 헛되이 소모된다.
    assert cs._STATS["flush_failures"] == 0
    assert cs._consecutive_failures == 0

    await cs.flush_batch(_FailingDb(), limit=10)
    assert cs._STATS["flush_failures"] == 1
    assert cs._STATS["cancelled_requeued"] == 10, "★DB 실패를 취소로 셌다"


def test_queue_maxlen_matches_the_constant() -> None:
    """★리뷰 #5-M1 — `deque(maxlen=…)` 과 `_MAX_QUEUE` 가 **갈릴 수 있었다**.

    갈리면 `dropped_overflow` 가 **일어나지 않은 유실**을 신고한다(위양성도 결함).
    옛 테스트는 둘 다 monkeypatch 해서 **검사 대상 자체를 갈아 끼웠다.**
    """
    assert cs._QUEUE.maxlen == cs._MAX_QUEUE


def test_flush_limit_matches_main_loop_literals() -> None:
    """★리뷰 #5-M3 — 주기는 잠갔는데 **상한은 안 잠갔다**(한쪽만 거는 단언).

    `main.py` 는 `_FLUSH_LIMIT` 을 **두 곳에 하드코딩**한다(`if n < 500`).
    갈리면 화면의 `max_sustained_per_sec` 이 거짓이 된다 — 그 값은 주기와 상한 **둘 다**에서
    나온다. 소스에서 **파생**해 대조한다.
    """
    src = (_API / "main.py").read_text(encoding="utf-8")
    lits = [int(m) for m in re.findall(r"if n < (\d+):", src)]
    assert lits, "★main.py 에서 배치 상한 비교를 못 찾았다 — 추출기가 죽었다(위반 아님)"
    assert len(lits) >= 2, f"★하드코딩 지점이 {len(lits)}곳 — 구조가 바뀌었다"
    assert set(lits) == {cs._FLUSH_LIMIT}, (
        f"★main.py 의 상한 {sorted(set(lits))} ≠ _FLUSH_LIMIT {cs._FLUSH_LIMIT}"
    )


def test_retry_cap_is_pinned_not_just_banded() -> None:
    """★리뷰 #5-M2 — 대역(`>=6 and <=120`)만 보면 12→6 이 **통과**한다.

    그 상수는 **무손실 창의 길이**를 정한다(상한 × 주기). 절반으로 줄이면 창도 절반이 된다.
    ★대역만 보면 상수가 장식이 된다(§A-5). 값을 못 박고 **창을 함께 단언**한다.
    """
    assert cs._MAX_FLUSH_RETRY == 12
    window_s = cs._MAX_FLUSH_RETRY * cs._FLUSH_INTERVAL_S
    assert window_s == 60, f"★무손실 창이 {window_s}초 — 60초가 아니다"


def test_loss_rate_precision_is_pinned() -> None:
    """★리뷰 #12 — `round(..., 3)` → `round(..., 0)` 이 생존했다(2.5% 가 2% 로 표시)."""
    cs._STATS["flushed"] = 1000
    cs._STATS["dropped_overflow"] = 25
    assert cs.capture_status()["loss_rate_pct"] == pytest.approx(2.439, abs=0.001)


# ═══════════════════════════════════════════════════════════════════════════
# ★독립 적대 렌즈 실측 봉합 (2026-08-28)
#
# 앞 PR 이 「7개 층에 변이를 넣었다」고 적고 착지 직전까지 갔는데, 독립 렌즈 셋을
# 돌리니 **확증 결함 2건**이 더 나왔다. 둘 다 이 파일이 고치겠다고 선언한 결함 클래스가
# **수리 안에서 재현**된 것이다.
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_cancellation_during_rollback_also_requeues_and_reraises() -> None:
    """★렌즈 실측 — **정리 경로에 같은 구멍이 하나 더** 있었다.

    위 `test_cancellation_requeues_and_reraises` 는 취소가 `db.execute()` 에서
    배달되는 경우만 태운다. 그런데 **평범한 DB 오류로 실패한 뒤 도는 정리용
    `await db.rollback()`** 은 `except Exception` 안에 있어서 `CancelledError` 를
    **안 잡는다**(`BaseException` 전용이므로). 그러면 취소가 거기서 전파돼
    **되돌림을 통째로 건너뛴다** — `_drain` 이 이미 빼낸 행이 사라진다.

    ★수리 전 실측(큐 300 · 배치 200): 사라진 행 **200** · `requeued` **0** ·
      화면 `lost_total` **0**. 계수기끼리는 일치하는데 **둘 다 틀렸다** —
      화면에 아무 이상이 안 보이므로 **계수기가 없는 것보다 나쁘다**.

    되살리는 변이: `except BaseException:` 절을 지우면(=종전 코드) 이 테스트가 죽는다.
    """
    import asyncio

    class _RollbackCancelDb:
        """execute 는 **평범한 예외** · rollback 에서 **취소**가 배달된다."""

        async def execute(self, *a, **k):
            raise RuntimeError("DB 장애(평범한 예외)")

        async def commit(self):  # pragma: no cover
            raise AssertionError("실패 경로")

        async def rollback(self):
            raise asyncio.CancelledError()

    _fill(300)
    with pytest.raises(asyncio.CancelledError):
        await cs.flush_batch(_RollbackCancelDb(), limit=200)

    # ★①한 건도 안 잃었다 ②그 사실이 **세어졌다** ③취소는 **삼키지 않았다**(위 raises)
    assert len(cs._QUEUE) == 300, f"★정리 중 취소로 {300 - len(cs._QUEUE)}건이 사라졌다"
    assert cs._STATS["requeued"] == 200
    assert cs._STATS["cancelled_requeued"] == 200, "★취소는 DB 실패와 **다른 사실**이다"


@pytest.mark.asyncio
async def test_every_flush_exit_either_inserts_or_requeues_or_counts() -> None:
    """★**두 모집단** — 되돌림 출구가 셋인데 하나만 새도 무성 유실이다.

    단일 케이스 단언은 *"올바른 구현"* 과 *"아무것도 안 하는 구현"* 을 구별하지 못한다.
    그래서 **같은 실행에서** 세 출구를 다 태우고, 매번 **행 보존**을 단언한다.

    ★이 테스트가 잠그는 불변식: `flush_batch` 의 **어떤 종료 경로에서도**
      (빠진 행) == (INSERT 된 행) + (되돌아온 행) + (세어진 유실). 무성 유실은 0.
    """
    import asyncio

    class _Db:
        def __init__(self, exc): self.exc = exc
        async def execute(self, *a, **k):
            if self.exc: raise self.exc
        async def commit(self): pass
        async def rollback(self): pass

    class _RollbackCancelDb(_Db):
        async def rollback(self): raise asyncio.CancelledError()

    cases = [
        ("정상 INSERT", _Db(None), None),
        ("평범한 DB 실패", _Db(RuntimeError("boom")), None),
        ("execute 취소", _Db(asyncio.CancelledError()), asyncio.CancelledError),
        ("정리 중 취소", _RollbackCancelDb(RuntimeError("boom")), asyncio.CancelledError),
    ]
    seen_flushed, seen_requeued = 0, 0
    for label, db, raises in cases:
        cs._reset_stats_for_test()
        _fill(120)
        before = len(cs._QUEUE)
        if raises:
            with pytest.raises(raises):
                await cs.flush_batch(db, limit=80)
        else:
            await cs.flush_batch(db, limit=80)
        after = len(cs._QUEUE)
        st = cs.capture_status()
        vanished = before - after - cs._STATS["flushed"] - st["lost_total"]
        assert vanished == 0, (
            f"★[{label}] 무성 유실 {vanished}건 — 빠졌는데 INSERT 도 되돌림도 계수도 아니다"
        )
        seen_flushed += cs._STATS["flushed"]
        seen_requeued += cs._STATS["requeued"]

    # ★대조군 — 위 루프가 **두 모집단을 실제로 태웠는지**. 한쪽만 돌았으면 공허한 초록이다.
    assert seen_flushed == 80, f"★INSERT 성공 경로가 안 돌았다(flushed={seen_flushed})"
    assert seen_requeued == 240, f"★되돌림 경로 3종이 다 안 돌았다(requeued={seen_requeued})"


@pytest.mark.asyncio
async def test_effectors_response_carries_the_capture_VALUE_not_just_the_key() -> None:
    """★렌즈 실측 — 배선 락이 **「이름이 있다」만 보고 「값이 실린다」를 안 봤다**.

    종전 락은 `assert "capture" in out` + 키 존재만 봤다. 렌즈가
    `_capture_status` 를 **상수 dict 로 갈아끼우는 변이**를 넣자 **44건 전부 초록**이었다.
    즉 *"계수가 0이 아닌데 화면에 도달하는가"* 를 **아무 층도 안 잠그고 있었다.**

    ★프론트도 이 구멍을 못 덮는다 — `EffectorFiring.test.tsx` 가 `@/lib/api-client` 를
      통째로 목킹하고 **자체 `capture` 픽스처**를 주므로 백엔드 계약을 전혀 안 태운다
      (*"스텁이 검증 대상 층을 우회한다"* 의 정확한 사례).

    되살리는 변이: `effector_firing.py` 의 `"capture": _capture_status()` 를 상수로
    바꾸면 이 테스트가 죽는다(종전 락은 안 죽었다).
    """
    from app.services.growth import effector_firing as ef

    class _Db:
        async def execute(self, *a, **k):
            class _R:
                @staticmethod
                def fetchall(): return []
            return _R()

    # ★두 모집단 — 같은 실행에서 **값이 갈려야** 한다. 한 값만 보면 상수 구현도 통과한다.
    cs._reset_stats_for_test()
    cs._STATS["dropped_after_retry"] = 777
    cs._QUEUE.append({"event_id": "x", "event_type": "t", "created_at": None})
    hot = (await ef.firing_status(_Db()))["capture"]

    cs._reset_stats_for_test()
    cold = (await ef.firing_status(_Db()))["capture"]

    assert hot["lost_total"] == 777, "★유실 계수가 응답까지 **도달하지 않는다**(상수·동결 의심)"
    assert cold["lost_total"] == 0, "★대조군이 0 이 아니다 — 상태가 안 갈렸다"
    assert hot["queue_depth"] == 1 and cold["queue_depth"] == 0, "★큐 깊이도 갈려야 한다"
    assert hot["lost_total"] != cold["lost_total"], "★두 모집단이 안 갈렸다 = 공허한 초록"
