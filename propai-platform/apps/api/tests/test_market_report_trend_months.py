"""시장조사보고서 시세 추이 기간 옵션(trend_months) 단위테스트.

배경: market_report_service._category_stats가 시세 추이(apt_trend) 조회 기간을 3개월로
하드코딩해, 프론트가 더 긴 추이를 요청할 방법이 없었다. options.trend_months(기본 3, 상한 24,
int 검증)를 build_report → _category_stats(months_n=...) 로 additive 배선한다.

검증 축:
  A. _resolve_trend_months — 기본값·정상 확장·상한 클램프·비정수 폴백(정직, raise 없음).
  B. _category_stats(months_n=...) — self._months(months_n) 로 그대로 스레딩(무회귀: 기본 3).
  C. build_report — options.trend_months 가 실제로 _category_stats에 전달됨(end-to-end 배선).
  D. apt_trend 월별 MOLIT 호출은 이미 asyncio.gather로 병렬(순차 아님) — 회귀 방지 스모크.
"""
from __future__ import annotations

import asyncio

import pytest

from app.services.market.market_report_service import (
    MarketReportService,
    _resolve_trend_months,
)

# ── A. _resolve_trend_months ───────────────────────────────────────────────

def test_resolve_trend_months_default_when_missing():
    assert _resolve_trend_months(None) == 3
    assert _resolve_trend_months({}) == 3


def test_resolve_trend_months_expands_within_range():
    assert _resolve_trend_months({"trend_months": 12}) == 12
    assert _resolve_trend_months({"trend_months": "6"}) == 6  # 문자열도 정수 변환


def test_resolve_trend_months_clamps_to_upper_bound():
    assert _resolve_trend_months({"trend_months": 25}) == 24
    assert _resolve_trend_months({"trend_months": 999}) == 24


def test_resolve_trend_months_clamps_to_lower_bound_and_rejects_garbage():
    assert _resolve_trend_months({"trend_months": 0}) == 1
    assert _resolve_trend_months({"trend_months": -5}) == 1
    assert _resolve_trend_months({"trend_months": "abc"}) == 3  # 비정수 → 정직 폴백(기본값)
    assert _resolve_trend_months({"trend_months": None}) == 3


# ── B. _category_stats months_n 스레딩(무회귀) ──────────────────────────────

@pytest.mark.asyncio
async def test_category_stats_default_months_n_is_three_no_regression(monkeypatch):
    svc = MarketReportService.__new__(MarketReportService)

    class _StubMolit:
        async def get_transactions(self, *_a, **_k):
            return []

        async def get_rent_transactions(self, *_a, **_k):
            return []

    svc.molit = _StubMolit()
    captured_months: dict = {}
    orig_months = MarketReportService._months

    def spy_months(self, n=3):
        captured_months["n"] = n
        return orig_months(self, n)

    monkeypatch.setattr(MarketReportService, "_months", spy_months)
    stats = await svc._category_stats("11680")  # months_n 미전달 → 기본 3
    assert captured_months["n"] == 3
    assert len(stats["months"]) == 3


@pytest.mark.asyncio
async def test_category_stats_months_n_expands_trend_window(monkeypatch):
    svc = MarketReportService.__new__(MarketReportService)

    class _StubMolit:
        async def get_transactions(self, *_a, **_k):
            return []

        async def get_rent_transactions(self, *_a, **_k):
            return []

    svc.molit = _StubMolit()
    stats = await svc._category_stats("11680", months_n=12)
    assert len(stats["months"]) == 12
    assert len(stats["apt_trend"]) == 12  # 추이 차트도 동일 창을 공유


# ── C. build_report end-to-end 배선 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_report_threads_options_trend_months_to_category_stats(monkeypatch):
    svc = MarketReportService()
    captured: dict = {}

    async def fake_cat(self, lawd_cd, months_n=3):
        captured["months_n"] = months_n
        return {"months": ["202606"], "trade": {}, "rent": {}, "apt_trend": []}

    async def fake_comp(self, address, pnu=None):
        return {"coordinates": {}, "land_register": {}, "local_ordinance": {},
                "official_prices": [], "infrastructure": {}}

    async def fake_comm(self, coords):
        return (None, "unavailable")

    async def fake_presale(self, lawd_cd, coords):
        return (None, "unavailable")

    monkeypatch.setattr(MarketReportService, "_category_stats", fake_cat)
    monkeypatch.setattr(
        "app.services.land_intelligence.land_info_service.LandInfoService.collect_comprehensive", fake_comp)
    monkeypatch.setattr(MarketReportService, "_commercial_area", fake_comm)
    monkeypatch.setattr(MarketReportService, "_nearby_presale_84_price", fake_presale)

    await svc.build_report("서울 강남구 역삼동", "11680", use_llm=False, options={"trend_months": 12})
    assert captured["months_n"] == 12

    await svc.build_report("서울 강남구 역삼동", "11680", use_llm=False, options=None)
    assert captured["months_n"] == 3  # 옵션 미전달 → 기존 3개월 무회귀

    await svc.build_report("서울 강남구 역삼동", "11680", use_llm=False, options={"trend_months": 999})
    assert captured["months_n"] == 24  # 상한 클램프


# ── D. 월별 MOLIT 호출 병렬 스모크(이미 asyncio.gather — 순차 아님을 확인) ──

@pytest.mark.asyncio
async def test_apt_trend_months_fetched_in_parallel_not_sequential():
    """apt_month(ym) 호출이 순차(for await)가 아니라 asyncio.gather 병렬임을 타이밍으로 확인.

    trend_months가 24까지 늘어날 수 있으므로, 이 루프가 순차라면 요청당 지연이 개월 수에
    비례해 커진다. 각 호출에 지연을 주입해 총 소요시간이 '개월 수 × 지연'이 아니라
    '지연 1회'에 가까운지 검증(병렬 확인).
    """
    svc = MarketReportService.__new__(MarketReportService)
    delay = 0.05
    months_n = 6

    class _DelayedMolit:
        async def get_transactions(self, lawd_cd, ym, prop_type="apt", num_rows=1000):
            await asyncio.sleep(delay)
            return []

        async def get_rent_transactions(self, *_a, **_k):
            await asyncio.sleep(delay)
            return []

    svc.molit = _DelayedMolit()
    start = asyncio.get_event_loop().time()
    await svc._category_stats("11680", months_n=months_n)
    elapsed = asyncio.get_event_loop().time() - start
    # 순차였다면 최소 (개월수 × delay) ≈ 0.3s 이상 걸린다. 병렬이면 delay 근방(~0.05~0.15s)에 그친다.
    assert elapsed < delay * months_n, (
        f"apt_month 월별 호출이 순차 실행되는 것으로 보임(elapsed={elapsed:.3f}s, "
        f"seq_lower_bound={delay * months_n:.3f}s)"
    )
