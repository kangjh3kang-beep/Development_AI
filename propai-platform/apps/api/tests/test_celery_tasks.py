"""v61 Celery 태스크 테스트.

celery 패키지 없이도 태스크 함수 자체는 실행 가능해야 한다.
"""

from app.tasks.celery_app import (
    BEAT_SCHEDULE_NAMES,
    OPERATIONAL_QUEUES,
    TASK_MODULES,
    TASK_NAMES,
)


def _schedule_from_source() -> dict[str, str]:
    """`celery_app.py` 의 `beat_schedule` 를 **AST 로** 읽어 {이름: task} 를 만든다.

    ★왜 `_create_app()` 을 부르지 않나: celery 는 `requirements.txt` 에 있지만
      **로컬 개발 환경에는 없을 수 있다**(실측 2026-09-06). 그러면 이 검사가 조용히
      `skip` 되어 **발화한 적 없는 안전망**이 된다 — 잠금은 그것이 도는 환경에서
      실제로 발화해야 한다. AST 는 celery 없이도 원천을 읽는다.
    """
    import ast
    import pathlib as _p

    src = (_p.Path(__file__).resolve().parents[1] / "app/tasks/celery_app.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        tgt = node.targets[0]
        if not (isinstance(tgt, ast.Attribute) and tgt.attr == "beat_schedule"):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        out: dict[str, str] = {}
        for k, v in zip(node.value.keys, node.value.values, strict=True):
            if not (isinstance(k, ast.Constant) and isinstance(v, ast.Dict)):
                continue
            task = ""
            for kk, vv in zip(v.keys, v.values, strict=True):
                if isinstance(kk, ast.Constant) and kk.value == "task" and isinstance(vv, ast.Constant):
                    task = str(vv.value)
            out[str(k.value)] = task
        return out
    return {}


class TestCeleryAppMeta:
    """Celery 앱 메타 정보 검증."""

    def test_beat_schedule_names_are_derived_from_the_schedule(self):
        """★손으로 쓴 집합끼리 비교하면 **원천과 갈라져도 초록**이다.

        종전 이 테스트는 `set(BEAT_SCHEDULE_NAMES) == {손으로 쓴 집합}` 이었다.
        그러면 `beat_schedule` 에만 항목을 추가하고 메타 목록을 안 고쳐도 통과하고,
        `BEAT_SCHEDULE_NAMES` 는 **조용히 거짓말**이 된다(자기지시적 기대값).
        원천은 `_create_app()` 이 만드는 **실제 스케줄**이다 — 거기서 파생시킨다.
        """
        actual = set(_schedule_from_source())
        assert actual, "beat_schedule 이 비었다 — 공허한 초록 방지"
        assert set(BEAT_SCHEDULE_NAMES) == actual, (
            "메타 목록이 실제 스케줄과 갈렸다 "
            f"(목록에만: {set(BEAT_SCHEDULE_NAMES) - actual} · 스케줄에만: {actual - set(BEAT_SCHEDULE_NAMES)})"
        )
        assert len(BEAT_SCHEDULE_NAMES) == len(set(BEAT_SCHEDULE_NAMES))  # 중복 금지

    def test_beat_schedule_names(self):
        assert "check-legal-rates-daily" in BEAT_SCHEDULE_NAMES
        assert "check-standard-prices-weekly" in BEAT_SCHEDULE_NAMES
        assert "check-pension-increase-monthly" in BEAT_SCHEDULE_NAMES

    def test_task_names_have_no_duplicates_and_cover_beat(self):
        """★집합 **동등**을 요구하면 태스크를 하나 추가할 때마다 이 목록이 상한이 된다.

        중요한 것은 「목록이 정확히 이 값이다」가 아니라 **「beat 가 부르는 태스크가
        전부 등록돼 있다」** 이다 — 그것을 파생형으로 본다.
        """
        assert len(TASK_NAMES) == len(set(TASK_NAMES))  # 중복 금지
        scheduled = {t for t in _schedule_from_source().values() if t}
        assert scheduled, "스케줄이 비었다 — 공허한 초록 방지"
        missing = scheduled - set(TASK_NAMES)
        assert not missing, f"beat 가 부르는데 TASK_NAMES 에 없다: {missing}"

    def test_task_names_content(self):
        assert "app.tasks.rate_tasks.check_legal_rates" in TASK_NAMES
        assert "app.tasks.rate_tasks.check_standard_prices" in TASK_NAMES
        assert "app.tasks.rate_tasks.check_pension_increase" in TASK_NAMES
        assert "app.tasks.cost_tasks.recalculate_project_cost" in TASK_NAMES
        assert "app.tasks.parcel_batch_task.run_batch" in TASK_NAMES

    def test_task_modules_cover_every_scheduled_task(self):
        """★모듈 목록도 **파생**으로 — 모듈을 빠뜨리면 태스크가 **등록조차 안 된다**.

        그 상태는 조용하다: beat 가 이름을 부르는데 워커가 그 이름을 모르면
        메시지가 버려지고, 아무도 실패를 보지 못한다.
        """
        assert len(TASK_MODULES) == len(set(TASK_MODULES))
        scheduled = {t for t in _schedule_from_source().values() if t}
        assert scheduled, "스케줄이 비었다"
        for t in scheduled:
            # "app.tasks.x.y" → 모듈은 "app.tasks.x". 커스텀 이름(`tasks.*`)은 제외.
            if not t.startswith("app.tasks."):
                continue
            mod = t.rsplit(".", 1)[0]
            assert mod in TASK_MODULES, f"스케줄된 {t} 의 모듈 {mod} 가 TASK_MODULES 에 없다"

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
