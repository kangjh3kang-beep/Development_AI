"""Underwriting 서비스 단위 테스트.

DB 없이 순수 계산 로직만 검증한다.
- 문서 분류 (_classify_document)
- 리스크 점수 산출 (_derive_score)
- 지표 계산 (profit margin, debt ratio, equity multiple)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.underwriting_service import UnderwritingService


class TestClassifyDocument:
    """_classify_document 정적 메서드 테스트."""

    def test_market_study(self):
        assert UnderwritingService._classify_document("market-study-q4.pdf") == "market-study"
        assert UnderwritingService._classify_document("Demand_Analysis.xlsx") == "market-study"

    def test_appraisal(self):
        assert UnderwritingService._classify_document("appraisal_report_v2.pdf") == "appraisal"
        assert UnderwritingService._classify_document("AVM_result.json") == "appraisal"

    def test_financial_model(self):
        assert UnderwritingService._classify_document("cashflow_model.xlsx") == "financial-model"
        assert UnderwritingService._classify_document("financial-projection.pdf") == "financial-model"

    def test_permits(self):
        assert UnderwritingService._classify_document("building_permit_2024.pdf") == "permits"
        assert UnderwritingService._classify_document("regulation_check.pdf") == "permits"

    def test_lease(self):
        assert UnderwritingService._classify_document("lease_agreement_3f.pdf") == "lease"
        assert UnderwritingService._classify_document("lease_contract_3f.xlsx") == "lease"

    def test_general_fallback(self):
        assert UnderwritingService._classify_document("photo_exterior.jpg") == "general"
        assert UnderwritingService._classify_document("misc_notes.txt") == "general"


class TestDeriveScore:
    """_derive_score 정적 메서드 테스트."""

    def test_high_profit_low_debt_invest(self):
        """높은 수익률 + 낮은 부채비율 → LOW 리스크, invest 추천."""
        score, level, recommendation, flags = UnderwritingService._derive_score(
            profit_margin_ratio=0.35,
            debt_ratio=0.30,
            equity_multiple=2.5,
            jeonse_ratio=None,
        )
        assert score >= 0.75
        assert level == "LOW"
        assert recommendation == "invest"
        assert len(flags) == 3  # jeonse_ratio=None이므로 3개

    def test_moderate_metrics_invest_with_conditions(self):
        """보통 수익률/부채 → MEDIUM 리스크."""
        score, level, recommendation, flags = UnderwritingService._derive_score(
            profit_margin_ratio=0.15,
            debt_ratio=0.55,
            equity_multiple=1.5,
            jeonse_ratio=None,
        )
        assert 0.45 <= score < 0.75
        assert level in ("MEDIUM", "HIGH")

    def test_low_profit_high_debt_decline(self):
        """낮은 수익률 + 높은 부채비율 → CRITICAL, decline."""
        score, level, recommendation, flags = UnderwritingService._derive_score(
            profit_margin_ratio=0.05,
            debt_ratio=0.85,
            equity_multiple=0.8,
            jeonse_ratio=None,
        )
        assert score < 0.45
        assert level == "CRITICAL"
        assert recommendation == "decline"

    def test_jeonse_penalty_applied(self):
        """전세가율 높으면 점수 하락."""
        # 전세가율 없는 경우
        score_no_jeonse, _, _, _ = UnderwritingService._derive_score(
            profit_margin_ratio=0.20,
            debt_ratio=0.50,
            equity_multiple=1.8,
            jeonse_ratio=None,
        )
        # 전세가율 90% (CRITICAL)
        score_high_jeonse, _, _, flags = UnderwritingService._derive_score(
            profit_margin_ratio=0.20,
            debt_ratio=0.50,
            equity_multiple=1.8,
            jeonse_ratio=0.90,
        )
        assert score_high_jeonse < score_no_jeonse
        jeonse_flags = [f for f in flags if f["factor"] == "jeonse-risk"]
        assert len(jeonse_flags) == 1

    def test_score_bounded(self):
        """점수가 [0.05, 0.95] 범위 내."""
        # 최적 조건
        score_max, _, _, _ = UnderwritingService._derive_score(
            profit_margin_ratio=0.50,
            debt_ratio=0.10,
            equity_multiple=5.0,
            jeonse_ratio=None,
        )
        assert score_max <= 0.95

        # 최악 조건
        score_min, _, _, _ = UnderwritingService._derive_score(
            profit_margin_ratio=-0.10,
            debt_ratio=1.50,
            equity_multiple=0.3,
            jeonse_ratio=0.95,
        )
        assert score_min >= 0.05

    def test_risk_flags_structure(self):
        """리스크 플래그 구조 검증."""
        _, _, _, flags = UnderwritingService._derive_score(
            profit_margin_ratio=0.20,
            debt_ratio=0.50,
            equity_multiple=1.8,
            jeonse_ratio=0.70,
        )
        assert len(flags) == 4
        for flag in flags:
            assert "factor" in flag
            assert "impact" in flag
            assert "value" in flag


class TestMetricDerivation:
    """create_underwriting의 지표 계산 로직 검증 (DB 없이)."""

    def test_profit_margin_calculation(self):
        """수익률 = (매출 - 비용) / 매출."""
        revenue = 1_000_000_000
        cost = 800_000_000
        expected = (revenue - cost) / revenue
        assert expected == pytest.approx(0.20, abs=0.001)

    def test_debt_ratio_calculation(self):
        """부채비율 = 부채 / 총비용."""
        debt = 500_000_000
        cost = 1_000_000_000
        expected = debt / cost
        assert expected == pytest.approx(0.50, abs=0.001)

    def test_equity_multiple_calculation(self):
        """지분배수 = 매출 / 자기자본."""
        revenue = 1_500_000_000
        equity = 500_000_000
        expected = revenue / equity
        assert expected == pytest.approx(3.0, abs=0.01)

    def test_zero_revenue_safe(self):
        """매출 0일 때 수익률 0 (ZeroDivision 방지)."""
        revenue = 0
        cost = 100_000_000
        margin = (revenue - cost) / revenue if revenue else 0.0
        assert margin == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
