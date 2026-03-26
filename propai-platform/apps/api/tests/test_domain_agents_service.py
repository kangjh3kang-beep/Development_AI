"""DomainAgentsService 단위 테스트.

도메인 에이전트 스코어링, 상수를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.domain_agents_service import _DOMAIN_LABELS, DomainAgentsService


class TestDomainLabels:
    """_DOMAIN_LABELS 상수 테스트."""

    def test_4개_도메인(self):
        assert len(_DOMAIN_LABELS) == 4

    def test_asset_레이블(self):
        assert _DOMAIN_LABELS["asset"] == "asset management"

    def test_development_레이블(self):
        assert _DOMAIN_LABELS["development"] == "development execution"

    def test_transaction_레이블(self):
        assert _DOMAIN_LABELS["transaction"] == "transaction strategy"

    def test_finance_레이블(self):
        assert _DOMAIN_LABELS["finance"] == "capital structure"


class TestScore:
    """_score 정적 메서드 테스트."""

    def test_기본점수_07(self):
        """아무 조건 없을 때 기본 0.7."""
        score, rec, findings = DomainAgentsService._score("투자 분석", {})
        assert score == pytest.approx(0.7, abs=0.01)

    def test_risk키워드_감점(self):
        score, _, findings = DomainAgentsService._score("risk 분석 요청", {})
        assert score < 0.7
        factors = [f["factor"] for f in findings]
        assert "risk-focus" in factors

    def test_downside키워드_감점(self):
        score, _, _ = DomainAgentsService._score("downside scenario", {})
        assert score < 0.7

    def test_높은_입주율_가점(self):
        """occupancy_rate ≥ 0.9 → +0.08."""
        score, _, findings = DomainAgentsService._score(
            "분석", {"occupancy_rate": 0.95}
        )
        assert score > 0.7
        factors = [f["factor"] for f in findings]
        assert "occupancy" in factors

    def test_높은_LTV_감점(self):
        """ltv ≥ 0.7 → -0.1."""
        score, _, findings = DomainAgentsService._score(
            "분석", {"ltv": 0.8}
        )
        assert score < 0.7
        factors = [f["factor"] for f in findings]
        assert "ltv" in factors

    def test_스케줄_버퍼_가점(self):
        """schedule_buffer_months ≥ 3 → +0.05."""
        score, _, _ = DomainAgentsService._score(
            "분석", {"schedule_buffer_months": 4}
        )
        assert score > 0.7

    def test_사전임대_가점(self):
        """pre_leasing_ratio ≥ 0.5 → +0.06."""
        score, _, findings = DomainAgentsService._score(
            "분석", {"pre_leasing_ratio": 0.6}
        )
        assert score > 0.7
        factors = [f["factor"] for f in findings]
        assert "pre-leasing" in factors

    def test_점수_035_095_범위(self):
        """bounded 범위 [0.35, 0.95]."""
        # 최악 케이스
        score_low, _, _ = DomainAgentsService._score(
            "risk downside", {"ltv": 0.9}
        )
        assert score_low >= 0.35

        # 최상 케이스
        score_high, _, _ = DomainAgentsService._score(
            "분석", {
                "occupancy_rate": 0.99,
                "schedule_buffer_months": 6,
                "pre_leasing_ratio": 0.8,
            }
        )
        assert score_high <= 0.95

    def test_08이상_proceed(self):
        score, rec, _ = DomainAgentsService._score(
            "분석", {
                "occupancy_rate": 0.95,
                "schedule_buffer_months": 5,
                "pre_leasing_ratio": 0.7,
            }
        )
        assert score >= 0.8
        assert rec == "proceed"

    def test_065_080_proceed_with_conditions(self):
        score, rec, _ = DomainAgentsService._score("일반 분석", {})
        assert 0.65 <= score < 0.80
        assert rec == "proceed-with-conditions"

    def test_065미만_escalate(self):
        score, rec, _ = DomainAgentsService._score(
            "risk downside", {"ltv": 0.85}
        )
        if score < 0.65:
            assert rec == "escalate"

    def test_복합_조건(self):
        """risk + 높은 LTV + 높은 입주율 = 혼합 영향."""
        score, _, findings = DomainAgentsService._score(
            "risk 분석", {"ltv": 0.8, "occupancy_rate": 0.95}
        )
        factors = [f["factor"] for f in findings]
        assert "risk-focus" in factors
        assert "ltv" in factors
        assert "occupancy" in factors


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
