"""L4 — 의결유형 분포 + 보완패턴 + 성숙도 게이팅(INV-22). thin-data 통계 날조 금지.

유형별 사례수 N < 임계(param) → status=INSUFFICIENT, distribution/common_conditions=None.
"""
from __future__ import annotations

from collections import Counter

from app.contracts.precedent import PrecedentCase, PrecedentStat, StatStatus
from app.core.parameters import param


class StatAggregator:
    def __init__(self, threshold: int | None = None) -> None:
        self.threshold = threshold if threshold is not None else int(param("precedent_min_cases"))

    def aggregate(self, issue: str, corpus: list[PrecedentCase]) -> PrecedentStat:
        relevant = [c for c in corpus if issue in c.issue_labels]
        n = len(relevant)

        if n < self.threshold:
            # 사례 부족 — 통계 비제시(날조 금지).
            return PrecedentStat(
                issue=issue, status=StatStatus.INSUFFICIENT, n=n,
                distribution=None, common_conditions=None,
            )

        distribution = dict(
            Counter(c.decision_type.value for c in relevant if c.decision_type is not None)
        )
        condition_counts: Counter = Counter()
        for c in relevant:
            for cond in set(c.conditions):
                condition_counts[cond] += 1
        majority = (n + 1) // 2
        common = [cond for cond, cnt in condition_counts.items() if cnt >= majority]

        return PrecedentStat(
            issue=issue, status=StatStatus.SUFFICIENT, n=n,
            distribution=distribution, common_conditions=common,
        )
