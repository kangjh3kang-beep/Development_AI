"""v61 Celery 태스크 테스트.

celery 패키지 없이도 태스크 함수 자체는 실행 가능해야 한다.
"""

from app.tasks.celery_app import BEAT_SCHEDULE_NAMES, TASK_NAMES


class TestCeleryAppMeta:
    """Celery 앱 메타 정보 검증."""

    def test_beat_schedule_count(self):
        # 카운트 단언은 신규 태스크 추가마다 드리프트(안티패턴) →
        # 현행 celery_app.py beat_schedule 이름 집합 동등 단언으로 고정.
        assert set(BEAT_SCHEDULE_NAMES) == {
            "check-legal-rates-daily",
            "check-standard-prices-weekly",
            "check-pension-increase-monthly",
            "sync-onbid-auctions-daily",
        }
        assert len(BEAT_SCHEDULE_NAMES) == len(set(BEAT_SCHEDULE_NAMES))  # 중복 금지

    def test_beat_schedule_names(self):
        assert "check-legal-rates-daily" in BEAT_SCHEDULE_NAMES
        assert "check-standard-prices-weekly" in BEAT_SCHEDULE_NAMES
        assert "check-pension-increase-monthly" in BEAT_SCHEDULE_NAMES

    def test_task_names_count(self):
        # 카운트 → 이름 집합 동등 단언 (sync_onbid_auctions 신규 태스크 반영).
        assert set(TASK_NAMES) == {
            "app.tasks.rate_tasks.check_legal_rates",
            "app.tasks.rate_tasks.check_standard_prices",
            "app.tasks.rate_tasks.check_pension_increase",
            "app.tasks.cost_tasks.recalculate_project_cost",
            "app.tasks.auction_sync_task.sync_onbid_auctions",
        }
        assert len(TASK_NAMES) == len(set(TASK_NAMES))  # 중복 금지

    def test_task_names_content(self):
        assert "app.tasks.rate_tasks.check_legal_rates" in TASK_NAMES
        assert "app.tasks.rate_tasks.check_standard_prices" in TASK_NAMES
        assert "app.tasks.rate_tasks.check_pension_increase" in TASK_NAMES
        assert "app.tasks.cost_tasks.recalculate_project_cost" in TASK_NAMES


class TestRateTasks:
    """법정요율 태스크 함수 직접 실행 테스트."""

    def test_check_legal_rates(self):
        from app.tasks.rate_tasks import check_legal_rates
        result = check_legal_rates()
        assert "status" in result

    def test_check_standard_prices(self):
        from app.tasks.rate_tasks import check_standard_prices
        result = check_standard_prices()
        assert result["status"] == "no_changes"
        assert result["source"] == "CODIL"

    def test_check_pension_increase(self):
        from app.tasks.rate_tasks import check_pension_increase
        result = check_pension_increase()
        assert "year" in result
        assert "pension_rate" in result
        assert result["status"] == "applied"
        assert result["pension_rate"] > 0


class TestCostTasks:
    """공사비 재계산 태스크 테스트."""

    def test_recalculate_project_cost(self):
        from app.tasks.cost_tasks import recalculate_project_cost
        result = recalculate_project_cost("test-project-123")
        assert result["project_id"] == "test-project-123"
        assert result["status"] == "recalculated"
        assert result["calculator_version"] == "v61"
