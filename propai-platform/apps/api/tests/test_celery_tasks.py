"""v61 Celery 태스크 테스트.

celery 패키지 없이도 태스크 함수 자체는 실행 가능해야 한다.
"""

from app.tasks.celery_app import (
    BEAT_SCHEDULE_NAMES,
    OPERATIONAL_QUEUES,
    TASK_MODULES,
    TASK_NAMES,
)


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
            "flush-growth-events",
            "analyze-growth-hourly",
            "analyze-growth-daily",
            "evaluate-healing",
            "evaluate-correction",
            "evaluate-improvement-daily",
            "run-learning-weekly",
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
            "app.tasks.growth_tasks.flush_growth_events",
            "app.tasks.growth_tasks.analyze_growth",
            "app.tasks.growth_tasks.evaluate_healing",
            "app.tasks.growth_tasks.evaluate_correction",
            "app.tasks.growth_tasks.evaluate_improvement",
            "app.tasks.growth_pr_task.run_pr_bot",
            "app.tasks.growth_learning_task.run_learning",
            "app.tasks.parcel_batch_task.run_batch",
            "tasks.memory.ingest_experience",
            "tasks.specialists.run_for_analysis",
        }
        assert len(TASK_NAMES) == len(set(TASK_NAMES))  # 중복 금지

    def test_task_names_content(self):
        assert "app.tasks.rate_tasks.check_legal_rates" in TASK_NAMES
        assert "app.tasks.rate_tasks.check_standard_prices" in TASK_NAMES
        assert "app.tasks.rate_tasks.check_pension_increase" in TASK_NAMES
        assert "app.tasks.cost_tasks.recalculate_project_cost" in TASK_NAMES
        assert "app.tasks.parcel_batch_task.run_batch" in TASK_NAMES

    def test_task_modules_are_explicit(self):
        assert set(TASK_MODULES) == {
            "app.tasks.rate_tasks",
            "app.tasks.cost_tasks",
            "app.tasks.auction_sync_task",
            "app.tasks.growth_tasks",
            "app.tasks.growth_pr_task",
            "app.tasks.growth_learning_task",
            "app.tasks.parcel_batch_task",
            "app.tasks.memory_tasks",
            "app.tasks.specialist_tasks",
        }
        assert len(TASK_MODULES) == len(set(TASK_MODULES))

    def test_operational_queues_cover_beat_routes(self):
        assert OPERATIONAL_QUEUES == [
            "parcel_batch",
            "celery",
            "rates",
            "auction",
            "growth",
        ]


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

    def test_recalculate_project_cost_is_honest_stub(self):
        # W3-10: 미구현 스텁이 "recalculated" 허위 성공을 반환하지 않는지 게이트 —
        # 실제 재계산이 구현되면 이 테스트를 실동작 검증으로 교체할 것.
        from app.tasks.cost_tasks import recalculate_project_cost
        result = recalculate_project_cost("test-project-123")
        assert result["project_id"] == "test-project-123"
        assert result["status"] == "not_implemented"  # 성공 위장 금지(무날조)
        assert "재계산은 수행되지 않았습니다" in result["message"]
        assert result["calculator_version"] == "v61"
