"""LLM 사용량 실계측 + 마진(50/40/30%) + 월기본/충전 코인분리 단위검증.

외부 LLM·실DB 미사용. AsyncSession을 페이크로 대체해 SQL/파라미터를 포착하고
지정한 행 결과만 돌려줘 차감순서·INSERT·집계 로직을 결정적으로 검증한다.
"""
import os
import sys
from datetime import UTC, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── 마진 50/40/30% + 비구독 1.5 ──
class TestTierMultiplier:
    def test_subscription_margins(self):
        from app.core.billing import tier_multiplier

        assert tier_multiplier("power") == 1.5      # +50%
        assert tier_multiplier("superpower") == 1.4  # +40%
        assert tier_multiplier("master") == 1.3      # +30%

    def test_non_subscription_margin(self):
        from app.core.billing import tier_multiplier

        assert tier_multiplier("free") == 1.5
        assert tier_multiplier("guest") == 1.5
        assert tier_multiplier("unknown") == 1.5

    def test_billed_krw_applies_margin_and_rate(self):
        from app.core.billing import billed_krw

        # $1 × 1300원 × 1.5(power) = 1950원
        assert billed_krw(1.0, "power", 1300.0) == pytest.approx(1950.0)
        # master 1.3 → 1690원
        assert billed_krw(1.0, "master", 1300.0) == pytest.approx(1690.0)


# ── 페이크 AsyncSession ──
class _FakeResult:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def first(self):
        return self._row

    def all(self):
        return self._rows


class FakeSession:
    """execute 호출을 큐 응답으로 매핑하는 페이크 세션.

    responses: SQL 본문 부분일치 → _FakeResult. INSERT/UPDATE는 캡처만.
    """

    def __init__(self, responses=None):
        self.responses = responses or []
        self.executed = []  # (sql_text, params)
        self.committed = 0

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.executed.append((sql, params or {}))
        for needle, result in self.responses:
            if needle in sql:
                return result
        return _FakeResult(row=None, rows=[])

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        pass


def _now():
    return datetime.now(UTC)


# ── 월기본 → 충전 차감순서 ──
class TestDeductionOrder:
    @pytest.fixture(autouse=True)
    def _reset_schema(self):
        # ensure_schema가 페이크 세션에서 일찍 종료되도록 ready 플래그를 켠다.
        import app.services.billing.billing_service as bs

        bs._SCHEMA_READY = True
        yield

    async def test_deduct_from_monthly_base_first(self, monkeypatch):
        import app.services.billing.billing_service as bs

        # 고정환율(외부호출 차단)
        async def fake_rate():
            return 1000.0

        monkeypatch.setattr(bs, "get_usd_krw_rate", fake_rate)

        now = _now()
        # tier=power, billed=0, budget=12250, cycle=now(같은달=리셋없음),
        # monthly_base=12250, topup=5000
        row = (
            "power", 0.0, 17250.0, now, 12250.0, 5000.0,
        )
        sess = FakeSession(responses=[("FROM public.users WHERE id", _FakeResult(row=row))])

        # $1 × 1000 × 1.5 = 1500원 → 전액 월기본에서 차감, topup 보존
        add = await bs.record_usage_usd(
            sess, "u1", 1.0, service="market", model="claude-sonnet",
            input_tokens=1000, output_tokens=500,
        )
        assert add == pytest.approx(1500.0)
        update = next(s for s in sess.executed if "UPDATE public.users SET llm_billed_krw" in s[0])
        # 원자 차감(:draw)으로 충전에서 0원만 차감 → topup 그대로 5000 보존
        #   (월기본 12250 > 1500이므로 초과 없음 → topup_draw=0)
        assert update[1]["draw"] == pytest.approx(0.0)
        assert 5000.0 - update[1]["draw"] == pytest.approx(5000.0)
        # llm_usage_log INSERT 발생 + service 귀속
        insert = next(s for s in sess.executed if "INSERT INTO llm_usage_log" in s[0])
        assert insert[1]["svc"] == "market"
        assert insert[1]["it"] == 1000 and insert[1]["ot"] == 500
        assert insert[1]["krw"] == pytest.approx(1500.0)

    async def test_overflow_draws_from_topup(self, monkeypatch):
        import app.services.billing.billing_service as bs

        async def fake_rate():
            return 1000.0

        monkeypatch.setattr(bs, "get_usd_krw_rate", fake_rate)

        now = _now()
        # 월기본 1000원만 남고(billed 11250, base 12250), topup 5000.
        row = ("power", 11250.0, 17250.0, now, 12250.0, 5000.0)
        sess = FakeSession(responses=[("FROM public.users WHERE id", _FakeResult(row=row))])

        # 가산 1500원: 월기본 잔여 1000 소진 → 초과 500을 충전에서 차감 → topup 4500
        add = await bs.record_usage_usd(sess, "u1", 1.0, service="feasibility")
        assert add == pytest.approx(1500.0)
        update = next(s for s in sess.executed if "UPDATE public.users SET llm_billed_krw" in s[0])
        # 월기본 잔여 1000 소진 → 초과 500을 충전에서 차감(:draw=500) → topup 5000-500=4500
        assert update[1]["draw"] == pytest.approx(500.0)
        assert 5000.0 - update[1]["draw"] == pytest.approx(4500.0)

    async def test_no_service_skips_usage_log(self, monkeypatch):
        import app.services.billing.billing_service as bs

        async def fake_rate():
            return 1000.0

        monkeypatch.setattr(bs, "get_usd_krw_rate", fake_rate)
        now = _now()
        row = ("power", 0.0, 12250.0, now, 12250.0, 0.0)
        sess = FakeSession(responses=[("FROM public.users WHERE id", _FakeResult(row=row))])
        await bs.record_usage_usd(sess, "u1", 1.0)  # service 미지정
        assert not any("INSERT INTO llm_usage_log" in s[0] for s in sess.executed)

    async def test_non_metered_tier_no_charge(self):
        import app.services.billing.billing_service as bs

        now = _now()
        row = ("free", 0.0, 0.0, now, 0.0, 0.0)
        sess = FakeSession(responses=[("FROM public.users WHERE id", _FakeResult(row=row))])
        add = await bs.record_usage_usd(sess, "u1", 1.0, service="market")
        assert add is None


# ── balance / token-usage 집계 ──
class TestUsageApis:
    @pytest.fixture(autouse=True)
    def _reset_schema(self):
        import app.services.billing.billing_service as bs

        bs._SCHEMA_READY = True
        yield

    async def test_balance_margin_and_coins(self, monkeypatch):
        import app.services.billing.billing_service as bs

        monkeypatch.setattr(bs, "load_config", _noop)

        async def fake_cycle(db, uid):
            return ("master", 3000.0, 15000.0, _now(), 10000.0, 5000.0)

        monkeypatch.setattr(bs, "ensure_cycle", fake_cycle)
        now = _now()
        row = ("master", 3000.0, 15000.0, now, 10000.0, 5000.0)
        sess = FakeSession(responses=[("FROM public.users WHERE id", _FakeResult(row=row))])
        bal = await bs.get_balance(sess, "u1")
        assert bal["tier"] == "master"
        # ★마진율(markup_pct)은 내부 정책 — 응답 비노출 스펙(billing_service.get_balance,
        #   개발자도구 노출 방지). 부재를 고정 단언한다(금액에는 이미 반영).
        assert "markup_pct" not in bal
        assert bal["monthly_base_krw"] == 10000
        assert bal["monthly_base_remaining"] == 7000  # 10000-3000
        assert bal["topup_krw"] == 5000
        assert bal["topup_remaining"] == 5000  # billed<base → 충전 미차감
        assert bal["used_this_cycle_krw"] == 3000

    async def test_token_usage_aggregation(self):
        import app.services.billing.billing_service as bs

        total = _FakeResult(row=(1500, 4200.0))
        by_service = _FakeResult(rows=[("market", 1000, 3000.0), ("esg", 500, 1200.0)])
        daily = _FakeResult(rows=[("2026-06-06", 1500, 4200.0)])
        sess = FakeSession(responses=[
            ("GROUP BY service", by_service),
            ("GROUP BY created_at::date", daily),
            ("FROM llm_usage_log WHERE user_id=:id AND created_at", total),
        ])
        out = await bs.token_usage(sess, "u1", days=30)
        assert out["total_tokens"] == 1500
        assert out["total_cost_krw"] == 4200
        assert out["by_service"][0] == {"service": "market", "tokens": 1000, "cost_krw": 3000}
        assert out["daily"][0] == {"date": "2026-06-06", "tokens": 1500, "cost_krw": 4200}


async def _noop(*a, **k):
    return None


# ── 월리셋: 월기본만 리셋, 충전 보존 ──
class TestMonthlyReset:
    @pytest.fixture(autouse=True)
    def _reset_schema(self):
        import app.services.billing.billing_service as bs

        bs._SCHEMA_READY = True
        yield

    async def test_rollover_resets_base_keeps_topup(self, monkeypatch):
        import app.services.billing.billing_service as bs
        from app.core.billing import tier_included_budget_krw

        # 지난달 사이클 → 리셋 트리거
        last_month = datetime(2026, 1, 1, tzinfo=UTC)
        row = ("power", 9999.0, 14999.0, last_month, 9999.0, 5000.0)
        sess = FakeSession(responses=[("FROM public.users WHERE id", _FakeResult(row=row))])
        result = await bs.ensure_cycle(sess, "u1")
        tier, billed, budget, monthly_base, topup = result
        assert billed == 0.0
        assert monthly_base == tier_included_budget_krw("power")  # 월기본 리셋
        assert topup == 5000.0  # 충전 보존
        update = next(s for s in sess.executed if "UPDATE public.users SET llm_billed_krw=0" in s[0])
        assert update[1]["m"] == tier_included_budget_krw("power")
        assert update[1]["b"] == tier_included_budget_krw("power") + 5000.0
