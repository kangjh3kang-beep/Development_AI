"""ComplianceService 단위 테스트.

AML 리스크 스코어링, KYC 상수 등을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.compliance_service import (
    _HIGH_RISK_COUNTRIES,
    _VERIFIED_DOCUMENT_KINDS,
    ComplianceService,
)


class TestConstants:
    """모듈 수준 상수 테스트."""

    def test_고위험국가_5개(self):
        assert len(_HIGH_RISK_COUNTRIES) == 5

    def test_IR_포함(self):
        assert "IR" in _HIGH_RISK_COUNTRIES

    def test_KP_포함(self):
        assert "KP" in _HIGH_RISK_COUNTRIES

    def test_검증_문서종류_4개(self):
        assert len(_VERIFIED_DOCUMENT_KINDS) == 4

    def test_passport_검증대상(self):
        assert "passport" in _VERIFIED_DOCUMENT_KINDS

    def test_id_card_검증대상(self):
        assert "id-card" in _VERIFIED_DOCUMENT_KINDS


class TestScoreAMLRisk:
    """_score_aml_risk 정적 메서드 테스트."""

    def _base_params(self, **overrides) -> dict:
        defaults = {
            "transaction_amount_krw": 500_000_000,
            "politically_exposed": False,
            "residency_countries": ["KR"],
            "document_count": 2,
        }
        defaults.update(overrides)
        return defaults

    def test_기본_저위험(self):
        """표준 케이스 → low 리스크."""
        score, level, status, lists, plan = ComplianceService._score_aml_risk(
            **self._base_params()
        )
        assert level == "low"
        assert status == "clear"

    def test_200억_이상_고위험(self):
        """거래액 200억 이상 → large-cashflow."""
        score, level, status, lists, _ = ComplianceService._score_aml_risk(
            **self._base_params(transaction_amount_krw=25_000_000_000)
        )
        assert "large-cashflow" in lists
        assert score >= 52  # 18 + 34

    def test_50억_이상_enhanced_dd(self):
        score, _, _, lists, _ = ComplianceService._score_aml_risk(
            **self._base_params(transaction_amount_krw=7_000_000_000)
        )
        assert "enhanced-dd" in lists

    def test_10억_이상_소폭_가산(self):
        low = ComplianceService._score_aml_risk(
            **self._base_params(transaction_amount_krw=500_000_000)
        )
        high = ComplianceService._score_aml_risk(
            **self._base_params(transaction_amount_krw=1_500_000_000)
        )
        assert high[0] > low[0]

    def test_PEP_24점_가산(self):
        non_pep = ComplianceService._score_aml_risk(**self._base_params(politically_exposed=False))
        pep = ComplianceService._score_aml_risk(**self._base_params(politically_exposed=True))
        assert pep[0] - non_pep[0] == pytest.approx(24, abs=0.1)
        assert "pep-screening" in pep[3]

    def test_고위험국가_가산(self):
        safe = ComplianceService._score_aml_risk(**self._base_params(residency_countries=["KR"]))
        risky = ComplianceService._score_aml_risk(**self._base_params(residency_countries=["IR", "KP"]))
        assert risky[0] > safe[0]
        matched = [item for item in risky[3] if item.startswith("country:")]
        assert len(matched) == 2

    def test_서류_없으면_18점_가산(self):
        with_docs = ComplianceService._score_aml_risk(**self._base_params(document_count=2))
        no_docs = ComplianceService._score_aml_risk(**self._base_params(document_count=0))
        assert no_docs[0] - with_docs[0] == pytest.approx(18, abs=0.1)
        assert "missing-docs" in no_docs[3]

    def test_서류_1개_8점_가산(self):
        two = ComplianceService._score_aml_risk(**self._base_params(document_count=2))
        one = ComplianceService._score_aml_risk(**self._base_params(document_count=1))
        assert one[0] - two[0] == pytest.approx(8, abs=0.1)

    def test_75이상_high_hit(self):
        """모든 위험 요소 → high/hit."""
        score, level, status, _, plan = ComplianceService._score_aml_risk(
            transaction_amount_krw=25_000_000_000,
            politically_exposed=True,
            residency_countries=["IR"],
            document_count=0,
        )
        assert level == "high"
        assert status == "hit"
        assert "Escalate" in plan

    def test_50_75_medium_review(self):
        """중간 위험 → medium/review."""
        score, level, status, _, plan = ComplianceService._score_aml_risk(
            transaction_amount_krw=7_000_000_000,
            politically_exposed=True,
            residency_countries=["KR"],
            document_count=2,
        )
        assert level == "medium"
        assert status == "review"

    def test_점수_0_100_범위(self):
        score, *_ = ComplianceService._score_aml_risk(**self._base_params())
        assert 0.0 <= score <= 100.0

    def test_극단_점수_캡(self):
        """모든 위험 요소 최대 → 100 이하."""
        score, *_ = ComplianceService._score_aml_risk(
            transaction_amount_krw=100_000_000_000,
            politically_exposed=True,
            residency_countries=["IR", "KP", "RU", "SY", "MM"],
            document_count=0,
        )
        assert score <= 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
