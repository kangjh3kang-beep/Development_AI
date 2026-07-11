"""예산-실적 집행 추적 코어 회귀가드 (설계도 §13).

미지출 = 예산 − 기지출, 집행률 = 기지출/예산, 초과집행 경고, 그룹/총계 롤업 — 실무 수지표의
'금액·기집행·미집행' 3열 구조가 실시간 재계산되는지 고정한다.
"""
from __future__ import annotations

from app.services.feasibility.budget_execution import (
    compute_line_execution,
    rollup_execution,
)


def test_line_spent_remaining_rate():
    r = compute_line_execution(
        budget_won=28_000_000_000,
        disbursements=[{"amount_won": 20_000_000_000}, {"amount_won": 4_000_000_000}],
    )
    assert r["spent_won"] == 24_000_000_000
    assert r["remaining_won"] == 4_000_000_000  # 예산 − 기지출
    assert r["execution_rate_pct"] == 85.7      # 24/28
    assert r["over_budget"] is False
    assert r["event_count"] == 2


def test_over_budget_flag():
    r = compute_line_execution(
        budget_won=1_000_000_000,
        disbursements=[{"amount_won": 1_200_000_000}],
    )
    assert r["remaining_won"] == -200_000_000  # 초과집행(음수)
    assert r["over_budget"] is True


def test_zero_budget_rate_is_none():
    """예산 0 → 집행률 None (0분모 방지·무목업)."""
    r = compute_line_execution(budget_won=0, disbursements=[{"amount_won": 5_000_000}])
    assert r["execution_rate_pct"] is None
    assert r["over_budget"] is False


def test_no_disbursement_is_full_remaining():
    r = compute_line_execution(budget_won=3_000_000_000, disbursements=[])
    assert r["spent_won"] == 0
    assert r["remaining_won"] == 3_000_000_000
    assert r["execution_rate_pct"] == 0.0


def test_rollup_groups_and_total():
    items = [
        {"group": "토지비", "label": "토지매입", "budget_won": 28_000_000_000,
         "disbursements": [{"amount_won": 24_000_000_000}]},
        {"group": "공사비", "label": "아파트공사", "budget_won": 171_000_000_000,
         "disbursements": [{"amount_won": 22_100_000_000}]},
        {"group": "공사비", "label": "철거", "budget_won": 1_000_000_000,
         "disbursements": [{"amount_won": 1_500_000_000}]},  # 초과
    ]
    roll = rollup_execution(items)
    assert roll["groups"]["토지비"]["remaining_won"] == 4_000_000_000
    assert roll["groups"]["공사비"]["budget_won"] == 172_000_000_000
    assert roll["total"]["budget_won"] == 200_000_000_000
    assert roll["total"]["spent_won"] == 47_600_000_000
    assert roll["total"]["remaining_won"] == 152_400_000_000
    assert "철거" in roll["over_budget_items"]
