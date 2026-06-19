"""다중출처 교차검증 로직 — 출처별 값 → 합의 판정(만장일치/과반/불일치/단일/결손).

결정론(동일 입력 동일 결과). 합의는 정규화된 값 기준(부동소수 허용오차·문자열 정규화).
불일치/단일/결손은 무음 없이 status로 표면화(무음 오판 0). 합의값과 출처별 값을 모두 보존.
★P4 차용(대량필지 auto_zoning 토지대장 vs 지적도 ±임계): 수치 사실에 한해 per-fact rel_tol(상대오차) 클러스터링
 — 실측 출처가 ±tol 내면 합의로 인정(면적 500 vs 502 같은 정상 측정차를 거짓 CONFLICT로 만들지 않음). rel_tol=0은
 기존 정확일치(무회귀). 비수치/혼합 사실은 항상 정확일치(일괄 tol의 거짓합의 위험 차단).
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import date

from app.contracts.cross_validation import CrossStatus, CrossValidation, SourceValue

_FLOAT_TOL = 1e-6
_REL_EPS = 1e-9    # 0 기준값 division-guard(상대오차 분모) — 법정 파라미터 아님
_MAX_REL_TOL = 1.0  # 상대오차 상한(>100%는 사실상 거짓합의) — 초과/비유한 입력은 0.0(정확일치)로 방어


def _norm(value: object) -> str:
    """합의 비교용 정규화 — 수치는 반올림 키, 문자열은 trim/lower."""
    if isinstance(value, bool):
        return f"b:{value}"
    if isinstance(value, (int, float)):
        return f"n:{round(float(value), 6)}"
    return f"s:{str(value).strip().lower()}"


def _is_number(v: object) -> bool:
    """유한 수치만(bool·nan·inf 제외). ★비유한 값은 클러스터 정렬 비결정·거짓합의 원인이라 수치경로 배제→정확일치 경로."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _cluster_numeric(present: list[SourceValue], rel_tol: float) -> list[list[SourceValue]]:
    """수치 출처를 상대오차 rel_tol 내로 그리디 클러스터(정렬 후 anchor 기준, 결정론). 동일측정차 흡수."""
    clusters: list[list[SourceValue]] = []
    for v in sorted(present, key=lambda s: float(s.value)):  # type: ignore[arg-type]
        x = float(v.value)  # type: ignore[arg-type]
        for c in clusters:
            anchor = float(c[0].value)  # type: ignore[arg-type]
            if abs(x - anchor) <= rel_tol * max(abs(x), abs(anchor), _REL_EPS):
                c.append(v)
                break
        else:
            clusters.append([v])
    return clusters


class CrossSourceValidator:
    def validate(self, fact_key: str, values: list[SourceValue],
                 as_of: date | None = None, rel_tol: float = 0.0) -> CrossValidation:
        # ★방어 clamp(전 호출자 불변식): 비유한·음수·상한초과 rel_tol은 0.0(정확일치)로 — inf/거대값이
        # 무관 수치를 한 클러스터로 흡수해 거짓 UNANIMOUS(실 차이 은폐)를 만드는 경로 차단(무음0).
        if not (isinstance(rel_tol, (int, float)) and not isinstance(rel_tol, bool)
                and math.isfinite(rel_tol) and 0.0 <= rel_tol <= _MAX_REL_TOL):
            rel_tol = 0.0
        present = [v for v in values if v.value is not None]
        by_source = {v.source: v.value for v in present}
        n = len(present)
        # INC-12 신선도 게이트 — as_of 대비 노후 출처를 합의 직전 표면화(무음0, 결정론). as_of None이면 미평가.
        stale_sources = sorted(v.source for v in present if v.is_stale(as_of))

        if n == 0:
            return CrossValidation(fact_key=fact_key, status=CrossStatus.ABSENT,
                                   confidence=0.0, sources_present=0, by_source={}, sources=values,
                                   stale_sources=stale_sources)
        if n == 1:
            # 단일 출처 — 교차검증 불가(보수). 값은 제시하되 확신 낮음.
            return CrossValidation(fact_key=fact_key, status=CrossStatus.SINGLE,
                                   agreed_value=present[0].value, confidence=0.5,
                                   sources_present=1, by_source=by_source, sources=values,
                                   stale_sources=stale_sources)

        # P4: rel_tol>0 + 전 출처 수치 → 상대오차 클러스터(실측 동일 흡수). 그 외(혼합/비수치/rel_tol 0)는 정확일치.
        if rel_tol > 0 and all(_is_number(v.value) for v in present):
            top = max(_cluster_numeric(present, rel_tol), key=len)  # 동률 → 최소 anchor 클러스터(결정론)
            top_n = len(top)
            top_ids = {id(v) for v in top}
            agreed = next(v.value for v in present if id(v) in top_ids)  # 클러스터 내 첫 원시값(합성 아님)
            dissent = sorted(v.source for v in present if id(v) not in top_ids)
        else:
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
            sources_present=n, by_source=by_source, sources=values, dissent=dissent,
            stale_sources=stale_sources,
        )
