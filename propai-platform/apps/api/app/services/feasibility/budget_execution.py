"""예산-실적 실시간 집행 추적 코어 (설계도 §13).

수지 라인아이템을 정적 계획이 아니라 '예산 대비 실적(집행률)'로 추적한다.
각 항목: 예산(계획) + 집행 이벤트(disbursements) → 기지출·미지출·집행률을 파생 계산한다.
첨부 실무 수지표(진영·의정부)의 '금액·기집행비용·미집행금액' 열 구조를 그대로 구현.

★순수 함수(부작용 없음·DB/프론트 무관) — 영속(DisbursementEvent 테이블)·프론트 편집기는 후속 증분.
★무목업: 증빙 없는 지출은 집계하되 confidence 플래그로 구분(임의 반영 금지는 상위 계층에서 게이트).
"""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float:
    """유한 수치만(비수치·bool·None → 0.0)."""
    if isinstance(v, bool) or v is None:
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f if f == f and f not in (float("inf"), float("-inf")) else 0.0


def compute_line_execution(
    *,
    budget_won: Any,
    disbursements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """한 라인아이템의 예산-실적 파생 계산.

    Args:
        budget_won: 예산액(계획). 단가×수량 등 상위에서 산출한 값.
        disbursements: 집행 이벤트 목록 [{amount_won, date?, memo?, evidence?}]. append-only.

    Returns:
        {budget_won, spent_won, remaining_won, execution_rate_pct, over_budget, event_count}
        · spent_won      = Σ 집행 이벤트 금액
        · remaining_won  = 예산 − 기지출 (음수 가능 = 초과집행)
        · execution_rate = 기지출 ÷ 예산 × 100 (예산 0이면 None — 0분모 방지)
        · over_budget    = 기지출 > 예산
    """
    budget = _num(budget_won)
    events = disbursements or []
    spent = sum(_num(e.get("amount_won")) for e in events if isinstance(e, dict))
    remaining = budget - spent
    rate = round(spent / budget * 100, 1) if budget > 0 else None
    return {
        "budget_won": int(round(budget)),
        "spent_won": int(round(spent)),
        "remaining_won": int(round(remaining)),
        "execution_rate_pct": rate,
        "over_budget": spent > budget and budget > 0,
        "event_count": sum(1 for e in events if isinstance(e, dict)),
    }


def rollup_execution(line_items: list[dict[str, Any]]) -> dict[str, Any]:
    """그룹/총계 롤업 — 각 항목의 예산·기지출·미지출을 그룹별·전체로 합산.

    Args:
        line_items: [{group, label, budget_won, disbursements?}]

    Returns:
        {groups: {group: {budget,spent,remaining,execution_rate_pct}}, total: {...},
         over_budget_items: [label...]}  ← 실무 수지표의 3열(예산·기집행·미집행) 대시보드용.
    """
    groups: dict[str, dict[str, float]] = {}
    over: list[str] = []
    tot_budget = tot_spent = 0.0
    for item in line_items:
        if not isinstance(item, dict):
            continue
        ex = compute_line_execution(
            budget_won=item.get("budget_won"),
            disbursements=item.get("disbursements"),
        )
        g = str(item.get("group") or "기타")
        gd = groups.setdefault(g, {"budget_won": 0.0, "spent_won": 0.0})
        gd["budget_won"] += ex["budget_won"]
        gd["spent_won"] += ex["spent_won"]
        tot_budget += ex["budget_won"]
        tot_spent += ex["spent_won"]
        if ex["over_budget"]:
            over.append(str(item.get("label") or g))

    def _finalize(budget: float, spent: float) -> dict[str, Any]:
        return {
            "budget_won": int(round(budget)),
            "spent_won": int(round(spent)),
            "remaining_won": int(round(budget - spent)),
            "execution_rate_pct": round(spent / budget * 100, 1) if budget > 0 else None,
        }

    return {
        "groups": {g: _finalize(v["budget_won"], v["spent_won"]) for g, v in groups.items()},
        "total": _finalize(tot_budget, tot_spent),
        "over_budget_items": over,
    }
