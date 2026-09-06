"""미확정·가상계좌 결제의 **자동 복구** 잠금 (2026-09-06).

## 이 파일이 지키는 것

`reconcile_order` 의 소비처는 **웹훅과 관리자 버튼 둘뿐**이었다. 스케줄러는 0건이라
「돈은 나갔는데 코인이 없다」가 **사람이 눈으로 찾을 때까지** 남았다.

★이 파일은 **정의가 아니라 배선**을 잠근다 — 「함수가 있다」가 아니라
  「beat 가 그것을 부르고, 그것이 `reconcile_order` 를 태우고, 그 결과가 상태를 바꾼다」.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import UTC, datetime, timedelta

import pytest

import app.services.billing.toss_orders_service as _tos

_API = pathlib.Path(__file__).resolve().parents[1]


def _iso(minutes_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()


def _receipt(order_id: str, minutes_ago: float, **over):
    r = {
        "receipt_id": f"rc-{order_id}", "order_id": order_id, "order_no": f"CO-{order_id}",
        "user_id": "u1", "payment_key": f"pk-{order_id}", "event": "unknown",
        "amount_krw": 10000.0, "toss_code": None, "toss_message": None,
        "created_at": _iso(minutes_ago),
    }
    r.update(over)
    return r


@pytest.fixture
def _env(monkeypatch: pytest.MonkeyPatch):
    """미해결 목록·재조회·영수증을 가로챈다. 반환: (호출된 order_id, 기록된 영수증)."""
    called: list[str] = []
    receipts: list[dict] = []
    outcomes: dict[str, str] = {}

    async def fake_list(db, *, limit=100):
        return fake_list.rows  # type: ignore[attr-defined]

    async def fake_reconcile(db, *, order_id, actor_id):
        called.append(order_id)
        if outcomes.get(order_id) == "__boom__":
            raise RuntimeError("벤더 장애")
        return {"order_id": order_id, "action": outcomes.get(order_id, "already_consistent")}

    async def fake_record(**kw):
        receipts.append(kw)
        return "r"

    monkeypatch.setattr(_tos.payment_receipts, "list_unresolved", fake_list)
    monkeypatch.setattr(_tos, "reconcile_order", fake_reconcile)
    monkeypatch.setattr(_tos.payment_receipts, "record", fake_record)
    fake_list.rows = []  # type: ignore[attr-defined]
    return fake_list, called, receipts, outcomes


class _NullDb:
    async def execute(self, *a, **k):
        raise AssertionError("이 테스트는 DB 를 태우지 않는다")


@pytest.mark.asyncio
async def test_scheduler_actually_calls_reconcile(_env) -> None:
    """★배선 — 「함수가 있다」가 아니라 **재조회가 실제로 불린다**."""
    lst, called, _, _ = _env
    lst.rows = [_receipt("o1", 60)]
    out = await _tos.reconcile_stale_payments(_NullDb(), limit=10)
    assert called == ["o1"], "재조회가 불리지 않았다(정의만 있고 배선 0)"
    assert out["attempted"] == 1


@pytest.mark.asyncio
async def test_age_window_has_both_ends(_env) -> None:
    """★**두 모집단** — 너무 이른 것과 너무 늦은 것을 **모두** 건너뛴다.

    한쪽만 걸면 반대쪽이 무제한이 된다(상한만 걸었다가 하한이 0으로 붕괴한 전례가 있다).
    · 너무 이르면 **우리가 우리를 방해한다**(정상 confirm 이 진행 중일 수 있다)
    · 너무 늦으면 **좀비를 영원히 폴링**해 벤더 쿼터가 샌다
    """
    lst, called, _, _ = _env
    too_new = _tos.RECONCILE_MIN_AGE_MINUTES / 2
    too_old = _tos.RECONCILE_MAX_AGE_HOURS * 60 + 60
    in_window = _tos.RECONCILE_MIN_AGE_MINUTES * 2
    lst.rows = [_receipt("young", too_new), _receipt("old", too_old), _receipt("ok", in_window)]

    out = await _tos.reconcile_stale_payments(_NullDb(), limit=10)
    assert called == ["ok"], f"창 판정이 틀렸다: {called}"
    assert out["skipped_age"] == 2
    # ★대조군 — 창 안의 건은 실제로 처리됐다(전부 건너뛰는 구현이 만점을 받지 않게).
    assert out["attempted"] == 1


@pytest.mark.asyncio
async def test_terminal_consistent_leaves_the_queue_but_human_cases_stay(_env) -> None:
    """★**두 모집단** — 정합 종결은 해소 이벤트로 큐에서 빼고,
    사람이 봐야 하는 것은 **남긴다**.

    이것이 없으면 스케줄러가 같은 건을 영원히 다시 묻고(쿼터 누수),
    관리자 목록도 좀비로 차서 `LIMIT` 안에 진짜 사고가 안 들어온다.
    """
    lst, called, receipts, outcomes = _env
    lst.rows = [
        _receipt("consistent", 60), _receipt("nopay", 60),
        _receipt("mismatch", 60), _receipt("conflict", 60),
    ]
    outcomes.update({
        "consistent": "already_consistent", "nopay": "no_payment_at_vendor",
        "mismatch": "amount_mismatch", "conflict": "apply_conflict",
    })
    out = await _tos.reconcile_stale_payments(_NullDb(), limit=10)

    resolved_ids = {r["order_id"] for r in receipts}
    assert resolved_ids == {"consistent", "nopay"}, f"해소 대상이 틀렸다: {resolved_ids}"
    assert out["resolved"] == 2
    assert out["left_open"] == 2, "사람이 봐야 하는 건을 조용히 해소했다"
    assert all(r["event"] == _tos.payment_receipts.EVENT_RECONCILED for r in receipts)


@pytest.mark.asyncio
async def test_grant_and_clawback_do_not_double_write_receipts(_env) -> None:
    """`granted`·`clawed_back` 은 `reconcile_order` 가 **이미** 영수증을 쓴다 — 중복 금지."""
    lst, _, receipts, outcomes = _env
    lst.rows = [_receipt("g", 60), _receipt("c", 60)]
    outcomes.update({"g": "granted", "c": "clawed_back"})
    out = await _tos.reconcile_stale_payments(_NullDb(), limit=10)
    assert receipts == [], "이미 기록된 결과에 영수증을 또 썼다"
    assert out["granted"] == 1 and out["clawed_back"] == 1


@pytest.mark.asyncio
async def test_one_failure_does_not_kill_the_batch(_env) -> None:
    """★한 건의 벤더 장애가 배치를 죽이면 **나머지 복구가 전부 밀린다**."""
    lst, called, _, outcomes = _env
    lst.rows = [_receipt("bad", 60), _receipt("good", 60)]
    outcomes["bad"] = "__boom__"
    out = await _tos.reconcile_stale_payments(_NullDb(), limit=10)
    assert called == ["bad", "good"], "첫 실패에서 멈췄다"
    assert out["left_open"] >= 1


@pytest.mark.asyncio
async def test_batch_limit_is_respected(_env) -> None:
    """벤더 호출이 건당 최대 2회다 — 상한이 없으면 한 번에 쿼터를 태운다."""
    lst, called, _, _ = _env
    lst.rows = [_receipt(f"o{i}", 60) for i in range(20)]
    await _tos.reconcile_stale_payments(_NullDb(), limit=5)
    assert len(called) == 5, f"상한을 넘겼다: {len(called)}"


def test_scheduler_is_registered_in_beat_and_reaches_reconcile() -> None:
    """★**배선 전수** — beat 등록 · 태스크 모듈 · 서비스 호출이 실제로 이어지는가.

    셋 중 하나만 빠져도 배치는 **조용히 안 돈다**(beat 가 이름을 부르는데 워커가
    그 이름을 모르면 메시지가 버려지고 아무도 실패를 보지 못한다).
    """
    src = (_API / "app/tasks/celery_app.py").read_text(encoding="utf-8")
    assert "reconcile-stale-payments-hourly" in src, "beat 에 등록되지 않았다"
    assert "app.tasks.billing_tasks" in src, "태스크 모듈이 임포트 목록에 없다"

    task_src = (_API / "app/tasks/billing_tasks.py").read_text(encoding="utf-8")
    tree = ast.parse(task_src)
    names = {
        n.attr if isinstance(n, ast.Attribute) else getattr(n, "id", "")
        for n in ast.walk(tree)
    }
    assert "reconcile_stale_payments" in names or "reconcile_stale_payments" in task_src, \
        "태스크가 서비스 함수를 부르지 않는다"
    # ★대조군 — 이 파일을 실제로 읽었다(빈 문자열이라 통과한 것이 아니다).
    assert "run_async_batch" in task_src
