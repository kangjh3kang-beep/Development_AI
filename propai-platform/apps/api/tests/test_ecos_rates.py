"""ECOS 실 기준금리 배선 계약 테스트 — get_pf_rate가 실금리+스프레드, 미가용시 폴백.

원칙(무날조): ECOS 캐시 콜드/미설정이면 기존 하드코딩 전액금리로 폴백(동작 보존).
실 기준금리(ECOS)면 기준금리+등급 스프레드로 금리환경을 반영.
"""
from __future__ import annotations

import time

from app.services.external_api import ecos_service as ecos
from app.services.feasibility.finance_cost_engine import get_pf_rate


def _warm(base_rate: float) -> dict:
    return {"rates": {"base_rate": base_rate, "source": "test"}, "fetched_at": time.time()}


# ── DATA_VALUE(연%) → 소수 파싱 ──


def test_to_decimal_parses_percent():
    assert ecos._to_decimal("2.5") == 0.025
    assert ecos._to_decimal("3") == 0.03
    assert ecos._to_decimal("3.50") == 0.035


def test_to_decimal_bad_value_none():
    assert ecos._to_decimal("N/A") is None
    assert ecos._to_decimal(None) is None


# ── 동기 캐시 읽기: 콜드/스테일 → None ──


def test_cold_cache_returns_none(monkeypatch):
    monkeypatch.setattr(ecos, "_CACHE", {"rates": None, "fetched_at": 0.0})
    assert ecos.base_rate() is None
    assert ecos.get_rates() is None
    assert ecos.base_rate_evidence() is None


def test_stale_cache_returns_none(monkeypatch):
    old = time.time() - (ecos._TTL_SEC + 10)
    monkeypatch.setattr(ecos, "_CACHE", {"rates": {"base_rate": 0.025}, "fetched_at": old})
    assert ecos.get_rates() is None  # TTL 초과 → 폴백


# ── get_pf_rate: ECOS 미가용 → 폴백(기존 동작 정확 보존) ──


def test_pf_rate_fallback_when_ecos_cold(monkeypatch):
    # presale_ratio=0.8 = 중립(0.7~0.9, 조정 없음)으로 순수 폴백 금리 검증.
    monkeypatch.setattr(ecos, "_CACHE", {"rates": None, "fetched_at": 0.0})
    assert get_pf_rate("AAA", 0.8) == 0.038
    assert get_pf_rate("A", 0.8) == 0.048
    assert get_pf_rate("BB", 0.8) == 0.065
    assert get_pf_rate("UNKNOWN", 0.8) == 0.055  # 미상 등급 폴백


# ── get_pf_rate: ECOS 실 기준금리 → 기준금리+스프레드 ──


def test_pf_rate_uses_ecos_base(monkeypatch):
    monkeypatch.setattr(ecos, "_CACHE", _warm(0.025))  # 기준금리 2.5%
    assert abs(get_pf_rate("AAA", 0.8) - (0.025 + 0.008)) < 1e-9  # 3.3%
    assert abs(get_pf_rate("A", 0.8) - (0.025 + 0.018)) < 1e-9    # 4.3%
    assert abs(get_pf_rate("BB", 0.8) - (0.025 + 0.035)) < 1e-9   # 6.0%


def test_pf_rate_tracks_base_change(monkeypatch):
    # 기준금리가 3.5%로 오르면 A등급 PF도 자동 상승(5.3%).
    monkeypatch.setattr(ecos, "_CACHE", _warm(0.035))
    assert abs(get_pf_rate("A", 0.8) - (0.035 + 0.018)) < 1e-9


# ── 분양률 조정은 실금리·폴백 양쪽에서 동일 적용 ──


def test_presale_adjustment(monkeypatch):
    monkeypatch.setattr(ecos, "_CACHE", _warm(0.025))
    base = 0.025 + 0.018  # A = 4.3%
    assert abs(get_pf_rate("A", 0.95) - (base - 0.002)) < 1e-9  # 90%+ 할인
    assert abs(get_pf_rate("A", 0.5) - (base + 0.005)) < 1e-9   # <70% 가산


# ── refresh: 키 미설정 → graceful None(캐시 미변경) ──


async def test_refresh_no_key_graceful(monkeypatch):
    monkeypatch.setattr(ecos, "_CACHE", {"rates": None, "fetched_at": 0.0})
    monkeypatch.setattr(ecos, "ecos_key", lambda: "")
    assert await ecos.refresh() is None
    assert ecos._CACHE["rates"] is None  # 미변경


# ── 실제 ECOS JSON 파싱(_fetch_latest) — MockTransport로 응답 스텁 ──


def _mock_client(handler):
    import httpx
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_fetch_latest_normal(monkeypatch):
    import httpx
    monkeypatch.setattr(ecos, "ecos_key", lambda: "TESTKEY")
    payload = {"StatisticSearch": {"row": [
        {"TIME": "202605", "DATA_VALUE": "2.75", "UNIT_NAME": "연%"},
        {"TIME": "202606", "DATA_VALUE": "2.5", "UNIT_NAME": "연%"},
    ]}}
    async with _mock_client(lambda req: httpx.Response(200, json=payload)) as c:
        got = await ecos._fetch_latest(c, "722Y001", "0101000", "M", "202401", "202612")
    assert got == ("202606", 0.025)  # TIME 최대 = 최신


async def test_fetch_latest_skips_blank_picks_max_time(monkeypatch):
    import httpx
    monkeypatch.setattr(ecos, "ecos_key", lambda: "K")
    payload = {"StatisticSearch": {"row": [
        {"TIME": "202606", "DATA_VALUE": ""},      # 미공표 공란 → 스킵
        {"TIME": "202604", "DATA_VALUE": "3.0"},
        {"TIME": "202605", "DATA_VALUE": "2.75"},  # 순서 무관·유효 최신
    ]}}
    async with _mock_client(lambda req: httpx.Response(200, json=payload)) as c:
        got = await ecos._fetch_latest(c, "722Y001", "0101000", "M", "s", "e")
    assert got == ("202605", 0.0275)


async def test_fetch_latest_error_response(monkeypatch):
    import httpx
    monkeypatch.setattr(ecos, "ecos_key", lambda: "K")
    payload = {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}
    async with _mock_client(lambda req: httpx.Response(200, json=payload)) as c:
        assert await ecos._fetch_latest(c, "722Y001", "0101000", "M", "s", "e") is None


async def test_fetch_latest_empty_rows(monkeypatch):
    import httpx
    monkeypatch.setattr(ecos, "ecos_key", lambda: "K")
    async with _mock_client(lambda req: httpx.Response(200, json={"StatisticSearch": {"row": []}})) as c:
        assert await ecos._fetch_latest(c, "722Y001", "0101000", "M", "s", "e") is None


async def test_refresh_populates_cache(monkeypatch):
    import httpx
    monkeypatch.setattr(ecos, "_CACHE", {"rates": None, "fetched_at": 0.0})
    monkeypatch.setattr(ecos, "ecos_key", lambda: "K")
    base_p = {"StatisticSearch": {"row": [{"TIME": "202606", "DATA_VALUE": "2.5"}]}}
    mkt_p = {"StatisticSearch": {"row": [{"TIME": "20260701", "DATA_VALUE": "3.1"}]}}

    def handler(req):
        return httpx.Response(200, json=base_p if "722Y001" in str(req.url) else mkt_p)

    _orig = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: _orig(transport=httpx.MockTransport(handler)))
    r = await ecos.refresh()
    assert r is not None and r["base_rate"] == 0.025 and r["base_rate_as_of"] == "202606"
    assert ecos.base_rate() == 0.025  # 캐시 반영
    assert "market_rates" in r  # 시장금리도 수집
