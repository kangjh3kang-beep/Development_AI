"""AI 권고 테스트 — 6규칙 트리거."""

import pytest
from app.services.feasibility.ai_recommendation import diagnose, Recommendation


class TestDiagnose:
    def test_healthy_project(self):
        """건전한 프로젝트 — 권고 없음."""
        recs = diagnose(
            profit_rate_pct=20.0,
            roi_pct=25.0,
            finance_cost_ratio_pct=10.0,
            construction_cost_ratio_pct=50.0,
            tax_cost_ratio_pct=5.0,
            grade="A",
        )
        assert len(recs) == 0

    def test_r001_warning(self):
        recs = diagnose(profit_rate_pct=8.0, roi_pct=20.0, grade="C")
        r001 = [r for r in recs if r.rule_code == "R001"]
        assert len(r001) == 1
        assert r001[0].severity == "warning"

    def test_r001_critical(self):
        recs = diagnose(profit_rate_pct=3.0, roi_pct=5.0, grade="D")
        r001 = [r for r in recs if r.rule_code == "R001"]
        assert len(r001) == 1
        assert r001[0].severity == "critical"

    def test_r002_roi(self):
        recs = diagnose(profit_rate_pct=15.0, roi_pct=10.0, grade="B")
        r002 = [r for r in recs if r.rule_code == "R002"]
        assert len(r002) == 1

    def test_r003_finance(self):
        recs = diagnose(
            profit_rate_pct=15.0, roi_pct=20.0,
            finance_cost_ratio_pct=20.0, grade="B",
        )
        r003 = [r for r in recs if r.rule_code == "R003"]
        assert len(r003) == 1

    def test_r004_construction(self):
        recs = diagnose(
            profit_rate_pct=15.0, roi_pct=20.0,
            construction_cost_ratio_pct=65.0, grade="B",
        )
        r004 = [r for r in recs if r.rule_code == "R004"]
        assert len(r004) == 1

    def test_r005_tax(self):
        recs = diagnose(
            profit_rate_pct=15.0, roi_pct=20.0,
            tax_cost_ratio_pct=12.0, grade="B",
        )
        r005 = [r for r in recs if r.rule_code == "R005"]
        assert len(r005) == 1

    def test_r006_grade_f(self):
        recs = diagnose(profit_rate_pct=-5.0, roi_pct=-10.0, grade="F")
        r006 = [r for r in recs if r.rule_code == "R006"]
        assert len(r006) == 1
        assert r006[0].severity == "critical"

    def test_multiple_triggers(self):
        """복합 문제 — 다수 규칙 동시 트리거."""
        recs = diagnose(
            profit_rate_pct=3.0,
            roi_pct=5.0,
            finance_cost_ratio_pct=25.0,
            construction_cost_ratio_pct=70.0,
            tax_cost_ratio_pct=15.0,
            grade="F",
        )
        codes = {r.rule_code for r in recs}
        assert "R001" in codes
        assert "R002" in codes
        assert "R003" in codes
        assert "R004" in codes
        assert "R005" in codes
        assert "R006" in codes
