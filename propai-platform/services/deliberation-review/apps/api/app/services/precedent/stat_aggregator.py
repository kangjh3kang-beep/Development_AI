"""L4 — 의결유형 분포 + 보완패턴 + 성숙도 게이팅(INV-22). thin-data 통계 날조 금지.

유형별 사례수 N < 임계(param) → status=INSUFFICIENT, distribution/common_conditions=None.
"""
from __future__ import annotations

from collections import Counter

from app.contracts.precedent import PrecedentCase, PrecedentStat, StatStatus
from app.contracts.rationale import Rationale, RationaleInput
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
                rationale=Rationale(
                    summary=f"'{issue}' 매칭 사례 {n}건 < 성숙도 임계 {self.threshold}건 → 통계 비제시(날조 금지, INV-22)",
                    formula="N(issue 매칭) < precedent_min_cases → INSUFFICIENT(분포/패턴 None)",
                    inputs=[RationaleInput(name="표본수 n", value=n),
                            RationaleInput(name="성숙도 임계", value=self.threshold, source="param:precedent_min_cases")],
                    caveats=["사례 부족 — 분포/반복패턴 비제시(통계적 의미 없음)"]),
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
            rationale=Rationale(
                summary=(f"'{issue}' 관련 {n}건 의결유형 분포 {distribution}; "
                         f"과반({majority}건↑) 반복 보완조건 {common or '없음'}"),
                formula="distribution=Counter(decision_type); common_conditions=조건별 빈도≥(n+1)//2",
                inputs=[RationaleInput(name="표본수 n", value=n),
                        RationaleInput(name="과반 임계(건)", value=majority),
                        RationaleInput(name="성숙도 임계", value=self.threshold, source="param:precedent_min_cases")],
                caveats=[
                    "관측 빈도일 뿐 규범적 구속력 없음(후보 참고 — INV-24)",
                    "표본편향 가능(코퍼스 수집 범위 의존)",
                    f"common_conditions는 과반({majority}건) 단순임계 — 인과 아님",
                    "의결 통계 — 법령근거 산출 아님(legal_basis N/A)",
                ]),
        )
