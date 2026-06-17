"""다중출처 교차검증 로직 — 출처별 값 → 합의 판정(만장일치/과반/불일치/단일/결손).

결정론(동일 입력 동일 결과). 합의는 정규화된 값 기준(부동소수 허용오차·문자열 정규화).
불일치/단일/결손은 무음 없이 status로 표면화(무음 오판 0). 합의값과 출처별 값을 모두 보존.
"""
from __future__ import annotations

from collections import Counter

from app.contracts.cross_validation import CrossStatus, CrossValidation, SourceValue

_FLOAT_TOL = 1e-6


def _norm(value: object) -> str:
    """합의 비교용 정규화 — 수치는 반올림 키, 문자열은 trim/lower."""
    if isinstance(value, bool):
        return f"b:{value}"
    if isinstance(value, (int, float)):
        return f"n:{round(float(value), 6)}"
    return f"s:{str(value).strip().lower()}"


class CrossSourceValidator:
    def validate(self, fact_key: str, values: list[SourceValue]) -> CrossValidation:
        present = [v for v in values if v.value is not None]
        by_source = {v.source: v.value for v in present}
        n = len(present)

        if n == 0:
            return CrossValidation(fact_key=fact_key, status=CrossStatus.ABSENT,
                                   confidence=0.0, sources_present=0, by_source={})
        if n == 1:
            # 단일 출처 — 교차검증 불가(보수). 값은 제시하되 확신 낮음.
            return CrossValidation(fact_key=fact_key, status=CrossStatus.SINGLE,
                                   agreed_value=present[0].value, confidence=0.5,
                                   sources_present=1, by_source=by_source)

        counts = Counter(_norm(v.value) for v in present)
        top_norm, top_n = counts.most_common(1)[0]
        agreed = next(v.value for v in present if _norm(v.value) == top_norm)
        dissent = sorted(v.source for v in present if _norm(v.value) != top_norm)

        if top_n == n:
            status, conf = CrossStatus.UNANIMOUS, 1.0
        elif top_n * 2 > n:  # 과반(엄격 다수)
            status, conf = CrossStatus.MAJORITY, top_n / n
        else:  # 동수/분산 — 합의 실패
            status, conf = CrossStatus.CONFLICT, top_n / n

        return CrossValidation(
            fact_key=fact_key, status=status, agreed_value=agreed, confidence=conf,
            sources_present=n, by_source=by_source, dissent=dissent,
        )
