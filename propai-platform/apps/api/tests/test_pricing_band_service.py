"""M3 적정 분양가 엔진(pricing_band_service.compute_fair_price) 결정론 회귀 테스트.

핵심 검증: 거래사례비교(주변 실거래+분양가)가 1차 헤드라인, 지불여력(PIR/DSR/LTV)이 2차 검증.
가짜값 금지·정직 표기 포함.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.market.pricing_band_service import (  # noqa: E402
    compute_fair_price,
    _loan_from_payment,
    W_PRESALE,
    W_TRADE,
)


class TestLoanReversal:
    def test_연금현가_역산_정답값(self):
        loan = _loan_from_payment(2400.0, 0.055, 30)  # 연 2,400만 상환,5.5%,30년
        assert 34000 <= loan <= 36500

    def test_이자율0_단순합(self):
        assert _loan_from_payment(1200.0, 0.0, 30) == 36000.0


class TestFairPriceMarketCore:
    def test_실거래만_있으면_실거래가_헤드라인(self):
        r = compute_fair_price(comparable_trade_10k=50000.0, trade_source="live")
        assert r["fair_price_10k"] == 50000
        assert "실거래" in r["market_reference"]["method"]
        assert r["data_source"] == "live"

    def test_분양가_실거래_둘다면_분양가_우선가중(self):
        # 분양가 60000, 실거래 50000 → 60000*0.6 + 50000*0.4 = 56000
        r = compute_fair_price(comparable_trade_10k=50000.0, nearby_presale_10k=60000.0)
        assert r["fair_price_10k"] == round(60000 * W_PRESALE + 50000 * W_TRADE)
        assert r["market_reference"]["nearby_presale_10k"] == 60000
        assert r["market_reference"]["comparable_trade_10k"] == 50000

    def test_비교데이터_없으면_정직_unavailable(self):
        r = compute_fair_price(annual_income_10k=6000.0)  # 소득만 있고 시장비교 없음
        assert r["data_source"] == "unavailable"
        assert "fair_price_10k" not in r  # 가짜 분양가 만들지 않음
        # 소득이 있어도 시장비교가 없으면 분양가 산출 불가(지불여력은 보조)
        assert r["affordability"]["band_10k"]


class TestAffordabilitySecondary:
    def test_시장가가_지불여력_보수상한_이내(self):
        # 소득 6000→보수상한 PIR6.3*6000=37800. 시장가 30000 → within_conservative
        r = compute_fair_price(comparable_trade_10k=30000.0, annual_income_10k=6000.0)
        assert r["affordability_verdict"] == "within_conservative"

    def test_시장가_지불여력_초과시_미분양위험(self):
        # 소득 4000, 시장가 매우 높음 → over_band
        r = compute_fair_price(comparable_trade_10k=200000.0, annual_income_10k=4000.0)
        assert r["affordability_verdict"] == "over_band"

    def test_소득없으면_검증_unavailable(self):
        r = compute_fair_price(comparable_trade_10k=50000.0)
        assert r["affordability_verdict"] == "unavailable"
        assert r["affordability"]["data_source"] == "unavailable"

    def test_소득출처_전파(self):
        r = compute_fair_price(comparable_trade_10k=50000.0, annual_income_10k=5000.0, income_source="fallback")
        assert r["affordability"]["data_source"] == "fallback"


class TestHonesty:
    def test_basis_근거_명시(self):
        r = compute_fair_price(comparable_trade_10k=50000.0, annual_income_10k=7000.0)
        assert "거래사례비교" in r["basis"] and "DSR" in r["basis"]
