"""법정요율 서비스 테스트."""

from app.services.cost.legal_rate_service import (
    PENSION_SCHEDULE,
    LegalRateService,
)


class TestLegalRateService:

    def test_get_current_rates(self):
        svc = LegalRateService()
        result = svc.get_current_rates()
        assert result["year"] == 2026
        assert len(result["rates"]) == 12
        assert "pension_note" in result
        assert "pension_schedule" in result

    def test_rate_values(self):
        svc = LegalRateService()
        rates = svc.get_current_rates()["rates"]
        assert rates["vat"] == 0.10
        assert rates["industrial_accident"] == 0.035
        assert rates["national_pension_emp"] == 0.04750

    def test_get_rate_history_all(self):
        svc = LegalRateService()
        history = svc.get_rate_history()
        assert len(history) == 12
        for entry in history:
            assert "rate_category" in entry
            assert "rate_value" in entry
            assert "effective_from" in entry

    def test_get_rate_history_filter(self):
        svc = LegalRateService()
        history = svc.get_rate_history("vat")
        assert len(history) == 1
        assert history[0]["rate_category"] == "vat"
        assert history[0]["rate_value"] == 0.10

    def test_refresh_rates(self):
        svc = LegalRateService()
        result = svc.refresh_rates()
        assert result["status"] == "no_changes"
        assert "current_rates" in result


class TestPensionSchedule:

    def test_schedule_count(self):
        assert len(PENSION_SCHEDULE) == 8

    def test_2026_rate(self):
        assert PENSION_SCHEDULE[2026] == 0.04750

    def test_2033_rate(self):
        assert PENSION_SCHEDULE[2033] == 0.06500

    def test_annual_increase(self):
        """매년 0.5%p(0.0025) 증가."""
        years = sorted(PENSION_SCHEDULE.keys())
        for i in range(1, len(years)):
            diff = PENSION_SCHEDULE[years[i]] - PENSION_SCHEDULE[years[i - 1]]
            assert abs(diff - 0.0025) < 0.0001

    def test_get_pension_for_year(self):
        svc = LegalRateService()
        assert svc.get_pension_for_year(2026) == 0.04750
        assert svc.get_pension_for_year(2033) == 0.06500
        assert svc.get_pension_for_year(2025) == 0.04500  # 이전
        assert svc.get_pension_for_year(2040) == 0.06500  # 이후 최종
