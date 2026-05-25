"""AI 사용량 추적기 테스트."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestUsageRecord:
    """UsageRecord 테스트."""

    def test_cost_calculation_gpt4o(self):
        from app.services.audit.ai_usage_tracker import UsageRecord

        record = UsageRecord("gpt-4o", 1000, 500)
        expected = (1000 * 5.0 + 500 * 15.0) / 1_000_000
        assert abs(record.cost_usd - expected) < 1e-9

    def test_cost_calculation_unknown_model(self):
        from app.services.audit.ai_usage_tracker import UsageRecord

        record = UsageRecord("unknown-model", 1000, 1000)
        expected = (1000 * 1.0 + 1000 * 1.0) / 1_000_000
        assert abs(record.cost_usd - expected) < 1e-9

    def test_to_dict(self):
        from app.services.audit.ai_usage_tracker import UsageRecord

        record = UsageRecord("gpt-4o-mini", 500, 200, user_id="user1", purpose="test")
        d = record.to_dict()
        assert d["model"] == "gpt-4o-mini"
        assert d["user_id"] == "user1"
        assert "timestamp" in d


class TestAIUsageTracker:
    """AIUsageTracker 테스트."""

    def test_track_adds_record(self):
        from app.services.audit.ai_usage_tracker import AIUsageTracker

        tracker = AIUsageTracker()
        tracker.track("gpt-4o", 100, 50)
        assert tracker.total_records == 1

    def test_total_cost(self):
        from app.services.audit.ai_usage_tracker import AIUsageTracker

        tracker = AIUsageTracker()
        tracker.track("gpt-4o", 1000, 500)
        tracker.track("gpt-4o-mini", 2000, 1000)
        total = tracker.get_total_cost()
        assert total > 0

    def test_total_tokens(self):
        from app.services.audit.ai_usage_tracker import AIUsageTracker

        tracker = AIUsageTracker()
        tracker.track("gpt-4o", 1000, 500)
        tracker.track("gpt-4o-mini", 2000, 1000)
        assert tracker.get_total_tokens() == 4500

    def test_get_by_model(self):
        from app.services.audit.ai_usage_tracker import AIUsageTracker

        tracker = AIUsageTracker()
        tracker.track("gpt-4o", 1000, 500)
        tracker.track("gpt-4o", 2000, 1000)
        tracker.track("gpt-4o-mini", 500, 200)
        by_model = tracker.get_by_model()
        assert by_model["gpt-4o"]["count"] == 2
        assert by_model["gpt-4o"]["input_tokens"] == 3000
        assert by_model["gpt-4o-mini"]["count"] == 1

    def test_daily_summary(self):
        from app.services.audit.ai_usage_tracker import AIUsageTracker

        tracker = AIUsageTracker(daily_budget_usd=50.0)
        tracker.track("gpt-4o", 1000, 500)
        summary = tracker.get_daily_summary()
        assert summary["record_count"] == 1
        assert summary["budget_usd"] == 50.0
        assert summary["over_budget"] is False

    def test_check_budget_within(self):
        from app.services.audit.ai_usage_tracker import AIUsageTracker

        tracker = AIUsageTracker(daily_budget_usd=100.0)
        tracker.track("gpt-4o-mini", 100, 50)
        assert tracker.check_budget() is True

    def test_check_budget_exceeded(self):
        from app.services.audit.ai_usage_tracker import AIUsageTracker

        tracker = AIUsageTracker(daily_budget_usd=0.0001)
        tracker.track("claude-opus-4-6", 100000, 50000)
        assert tracker.check_budget() is False

    def test_empty_tracker(self):
        from app.services.audit.ai_usage_tracker import AIUsageTracker

        tracker = AIUsageTracker()
        assert tracker.total_records == 0
        assert tracker.get_total_cost() == 0
        assert tracker.get_total_tokens() == 0
        assert tracker.check_budget() is True
