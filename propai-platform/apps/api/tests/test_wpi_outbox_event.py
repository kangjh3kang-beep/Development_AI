"""WP-I 게이트 — 전역 아웃박스(outbox_event) at-least-once·컨슈머 멱등·스키마 진화·발행 원자성.

DB 없이(순수 도메인 함수+인프로세스 컨슈머) CI 에서 그대로 도는 픽스처다. DB SQL 헬퍼
(ensure_schema/emit_event/fetch_publishable/mark_published/mark_failed)의 계약은 여기서 검증하는
순수 함수(claim_publish/register_failure/should_retry)와 **동일 불변식**(WHERE published_at IS NULL,
attempts=attempts+1)을 SQL 로 집행한다 — 따라서 순수 함수 테스트가 곧 발행 계약의 검증이다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.events import outbox_consumer as oc
from app.services.events import outbox_event as ox


@pytest.fixture(autouse=True)
def _isolate_registries():
    """각 테스트마다 마이그레이션·소비처·기본 dedup 가드를 초기화(전역 상태 격리)."""
    ox.clear_migrations()
    oc.clear_consumers()
    oc.default_guard = oc.IdempotencyGuard()
    yield
    ox.clear_migrations()
    oc.clear_consumers()


# ── 1. 이벤트 생성 계약 ────────────────────────────────────────────────────
def test_new_event_assigns_event_id_and_defaults():
    ev = ox.new_event("agg-1", "project", "ProjectCreated")
    assert ev.event_id  # uuid 자동 발급
    assert ev.schema_version == ox.DEFAULT_SCHEMA_VERSION == 1
    assert ev.aggregate_id == "agg-1" and ev.aggregate_type == "project"
    assert ev.payload == {}


def test_new_event_preserves_explicit_id_version_and_normalizes():
    ev = ox.new_event(
        "  agg-2  ", " design_run ", " DesignRunCompleted ",
        {"units": 100}, schema_version=3, event_id="fixed-key-1",
    )
    assert ev.event_id == "fixed-key-1"  # 결정적 멱등 키 보존
    assert ev.schema_version == 3
    assert ev.aggregate_id == "agg-2"  # strip
    assert ev.event_type == "DesignRunCompleted"
    assert ev.to_dict()["payload"] == {"units": 100}


# ── 2. 재시도 판단(0-falsy 포함) ──────────────────────────────────────────
def test_should_retry_boundaries_including_zero_falsy():
    assert ox.should_retry(0) is True  # ★0=아직 시도 안 함 → 재시도 대상
    assert ox.should_retry(ox.DEFAULT_MAX_ATTEMPTS - 1) is True
    assert ox.should_retry(ox.DEFAULT_MAX_ATTEMPTS) is False
    assert ox.should_retry(ox.DEFAULT_MAX_ATTEMPTS + 5) is False
    assert ox.should_retry(2, max_attempts=2) is False


def test_next_backoff_is_monotonic_and_capped():
    b1 = ox.next_backoff_seconds(1)
    b2 = ox.next_backoff_seconds(2)
    b3 = ox.next_backoff_seconds(3)
    assert b1 < b2 < b3  # 지수 증가
    assert b1 == ox._BACKOFF_BASE_SEC
    # 아주 큰 attempts 는 cap 에서 포화.
    assert ox.next_backoff_seconds(999) == ox._BACKOFF_CAP_SEC


# ── 3. 페이로드 스키마 진화 ───────────────────────────────────────────────
def test_migrate_payload_applies_registered_upcaster():
    ox.register_migration("E", 1, lambda p: {**p, "v2_field": True})
    out = ox.migrate_payload("E", {"a": 1}, from_version=1, to_version=2)
    assert out == {"a": 1, "v2_field": True}


def test_migrate_payload_noop_when_target_not_higher():
    ox.register_migration("E", 1, lambda p: {**p, "should_not_apply": 1})
    # to_version <= from_version → 원본 그대로(다운캐스트 안 함).
    assert ox.migrate_payload("E", {"a": 1}, 2, 2) == {"a": 1}
    assert ox.migrate_payload("E", {"a": 1}, 3, 1) == {"a": 1}


def test_migrate_payload_chains_versions_in_order():
    ox.register_migration("E", 1, lambda p: {**p, "step": 1})
    ox.register_migration("E", 2, lambda p: {**p, "step": p["step"] + 1})
    out = ox.migrate_payload("E", {}, from_version=1, to_version=3)
    assert out["step"] == 2  # v1→v2(step=1)→v3(step=2) 순차


def test_migrate_payload_missing_step_is_identity():
    # v1 업캐스터만 있고 v2 업캐스터가 없으면 v2→v3 단계는 항등(형태 불변).
    ox.register_migration("E", 1, lambda p: {**p, "one": 1})
    out = ox.migrate_payload("E", {}, from_version=1, to_version=3)
    assert out == {"one": 1}


# ── 4. 발행 원자성(claim_publish — WHERE published_at IS NULL 계약) ─────────
def test_claim_publish_is_atomic_first_wins():
    st = ox.OutboxRowState(event_id="e1")
    now = datetime.now(UTC)
    assert ox.claim_publish(st, now) is True  # 최초 발행 확정
    assert st.published_at == now and st.status == "PUBLISHED"
    # 두 번째(경쟁 워커) 는 아무 것도 못 바꾸고 False — published_at 원자 가드.
    assert ox.claim_publish(st, now + timedelta(seconds=10)) is False
    assert st.published_at == now  # 불변


# ── 5. 실패 기록·재시도 상태 전이 ─────────────────────────────────────────
def test_register_failure_increments_and_sets_backoff():
    st = ox.OutboxRowState(event_id="e2")
    ox.register_failure(st, "boom", datetime.now(UTC))
    assert st.attempts == 1
    assert st.last_error == "boom"
    assert st.next_attempt_at is not None
    assert st.status == "PENDING"  # 아직 재시도 여력


def test_register_failure_marks_dead_at_max():
    st = ox.OutboxRowState(event_id="e3", attempts=ox.DEFAULT_MAX_ATTEMPTS - 1)
    ox.register_failure(st, "boom")
    assert st.attempts == ox.DEFAULT_MAX_ATTEMPTS
    assert st.status == "DEAD"  # 재시도 소진 → 데드레터


def test_register_failure_does_not_touch_published_row():
    st = ox.OutboxRowState(event_id="e4")
    ox.claim_publish(st)  # 이미 발행됨
    ox.register_failure(st, "late error")
    assert st.attempts == 0 and st.status == "PUBLISHED"  # 발행 취소/재시도 안 함


# ── 6. 컨슈머 멱등(동기) ──────────────────────────────────────────────────
def test_process_once_runs_handler_only_first_time():
    calls = []
    guard = oc.IdempotencyGuard()
    r1 = oc.process_once("evt-1", lambda: calls.append(1), guard)
    r2 = oc.process_once("evt-1", lambda: calls.append(1), guard)
    assert r1 == oc.PROCESSED
    assert r2 == oc.SKIPPED_DUPLICATE  # 중복 이벤트는 1회만 처리
    assert len(calls) == 1


def test_process_once_handler_error_allows_reprocess():
    """★at-least-once: 핸들러 실패 시 기억하지 않아 재전달 때 다시 처리된다."""
    calls = []
    guard = oc.IdempotencyGuard()

    def failing():
        calls.append("try")
        raise RuntimeError("consumer down")

    with pytest.raises(RuntimeError):
        oc.process_once("evt-2", failing, guard)
    assert guard.seen("evt-2") is False  # 실패는 기억 안 함

    # 재전달 — 이번엔 성공.
    oc.process_once("evt-2", lambda: calls.append("ok"), guard)
    assert calls == ["try", "ok"]
    assert guard.seen("evt-2") is True


# ── 7. dedup 가드 용량 상한(무한 증식 방지) ───────────────────────────────
def test_idempotency_guard_is_bounded_lru():
    guard = oc.IdempotencyGuard(capacity=3)
    for i in range(5):
        guard.remember(f"e{i}")
    assert len(guard) == 3  # 용량 상한
    assert guard.seen("e0") is False and guard.seen("e1") is False  # 최老 축출
    assert guard.seen("e4") is True and guard.seen("e3") is True  # 최근 보존


# ── 8. 컨슈머 멱등(비동기) ────────────────────────────────────────────────
async def test_process_once_async_dedup():
    calls = []
    guard = oc.IdempotencyGuard()

    async def handler():
        calls.append(1)

    r1 = await oc.process_once_async("aevt-1", handler, guard)
    r2 = await oc.process_once_async("aevt-1", handler, guard)
    assert r1 == oc.PROCESSED and r2 == oc.SKIPPED_DUPLICATE
    assert len(calls) == 1


# ── 9. 소비처 레지스트리 전달 계약 ────────────────────────────────────────
async def test_deliver_no_consumers_is_success():
    # 등록 소비처 없음 → 발행 성공(이벤트는 outbox_event 에 내구 기록되어 있음).
    assert await oc.deliver({"event_type": "X", "event_id": "1"}) is True


async def test_deliver_reports_failure_when_consumer_raises():
    seen = []

    async def good(ev):
        seen.append(ev["event_id"])

    async def bad(ev):
        raise RuntimeError("handler boom")

    oc.register_consumer("Y", good)
    oc.register_consumer("Y", bad)
    ok = await oc.deliver({"event_type": "Y", "event_id": "42"})
    assert ok is False  # 하나라도 실패 → 재시도 대상
    assert seen == ["42"]  # 성공 소비처는 그래도 호출됨
    assert oc.consumer_count("Y") == 2


# ── 9b. 회귀(코디네이터 리뷰 MEDIUM 2건) ──────────────────────────────────
async def test_deliver_partial_success_replay_does_not_rerun_succeeded_consumer():
    """부분성공 재전달 시 이미 성공한 소비처는 재실행되지 않고 실패했던 소비처만 재시도된다.

    소비처 A는 항상 성공. 소비처 B는 1회차에 실패, 2회차(재전달)에 성공. 같은 event_id로
    deliver를 두 번 호출했을 때 A의 호출 횟수는 여전히 1(재실행 안 됨)이어야 하고, B는 2
    (실패 시도 + 성공 시도)여야 한다. — 소비처별 전용 가드 + 네임스페이스 키(consumer_name:
    event_id)가 이 계약을 보장한다.
    """
    calls_a: list[str] = []
    calls_b: list[str] = []
    attempt = {"n": 0}

    async def consumer_a(ev):
        calls_a.append(ev["event_id"])

    async def consumer_b(ev):
        attempt["n"] += 1
        if attempt["n"] == 1:
            raise RuntimeError("consumer_b 일시 실패")
        calls_b.append(ev["event_id"])

    oc.register_consumer("Z", consumer_a, name="consumer_a")
    oc.register_consumer("Z", consumer_b, name="consumer_b")

    event = {"event_type": "Z", "event_id": "99"}
    ok1 = await oc.deliver(event)
    assert ok1 is False  # consumer_b 실패 → 재시도 대상
    assert calls_a == ["99"]  # A는 1회 처리
    assert calls_b == []  # B는 이번엔 실패(아직 기록 안 됨)

    # 재전달(동일 event_id) — A는 이미 성공했으므로(자기 가드가 기억) 재실행되면 안 된다.
    ok2 = await oc.deliver(event)
    assert ok2 is True  # 이번엔 B도 성공 → 전체 성공
    assert calls_a == ["99"]  # ★핵심 회귀 포인트: A는 여전히 1회(재실행 안 됨)
    assert calls_b == ["99"]  # B는 재시도로 1회 성공 기록
    assert attempt["n"] == 2  # B 자체는 실패+성공으로 2번 시도됨


async def test_deliver_two_consumers_same_event_id_no_cross_suppression():
    """두 소비처가 동일 event_id 이벤트를 각자 독립적으로 처리한다(교차억제 0).

    공유 default_guard 를 소비처끼리 나눠 쓰던 구 설계라면, 먼저 성공한 소비처의
    remember(event_id) 때문에 두 번째 소비처가 seen=True 로 오판해 **전혀 호출되지 않는다**
    (영구 소실). 소비처별 전용 가드로 이 교차억제를 원천 차단했는지 검증한다.
    """
    calls_a: list[str] = []
    calls_b: list[str] = []

    async def consumer_a(ev):
        calls_a.append(ev["event_id"])

    async def consumer_b(ev):
        calls_b.append(ev["event_id"])

    oc.register_consumer("W", consumer_a, name="consumer_a")
    oc.register_consumer("W", consumer_b, name="consumer_b")

    ok = await oc.deliver({"event_type": "W", "event_id": "7"})
    assert ok is True
    # ★두 소비처 모두 독립적으로 동일 event_id를 처리했어야 한다(한쪽이 스킵되면 실패).
    assert calls_a == ["7"]
    assert calls_b == ["7"]


def test_register_consumer_returns_name_and_auto_assigns_when_missing():
    oc.clear_consumers()
    named = oc.register_consumer("V", lambda ev: None, name="explicit-name")
    auto = oc.register_consumer("V", lambda ev: None)
    assert named == "explicit-name"
    assert auto == "V#1"  # 순번 기반 자동 이름(두 번째 등록 = index 1)
    assert oc.consumer_count("V") == 2


# ── 10. sales 원형 → 전역 어댑터(무회귀·미배선) ───────────────────────────
def test_outbox_event_from_sales_maps_fields():
    ev = ox.outbox_event_from_sales("site-99", "ContractSigned", {"unit_id": "u1", "amount": 500})
    assert ev.aggregate_type == "sales_site"
    assert ev.aggregate_id == "site-99"
    assert ev.event_type == "ContractSigned"
    assert ev.payload == {"unit_id": "u1", "amount": 500}
    assert ev.event_id  # 멱등 키 발급됨
