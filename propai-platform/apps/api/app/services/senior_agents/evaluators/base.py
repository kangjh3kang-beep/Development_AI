"""정량 평가 공용 구조체·헬퍼 — RuleEvaluation·방어적 수치 파싱."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

PASS = "PASS"     # 기준 충족
WARN = "WARN"     # 경고(보수 가정·조건부)
BLOCK = "BLOCK"   # 차단(비경제·요건 미달)

_SEVERITY = {PASS: 0, WARN: 1, BLOCK: 2}


@dataclass(frozen=True)
class RuleEvaluation:
    """decision_rule 1건의 실측 판정(근거 동반)."""

    rule_id: str
    label: str
    value: float | None      # 산출 지표값(없으면 None)
    unit: str                # 단위(배수 'x'·'%'·'bp' 등)
    verdict: str             # PASS/WARN/BLOCK
    threshold: str           # 적용 기준(텍스트)
    basis: str               # 근거(법조문/기준 — citation)
    detail: str              # 산식·해석

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id, "label": self.label, "value": self.value,
            "unit": self.unit, "verdict": self.verdict, "threshold": self.threshold,
            "basis": self.basis, "detail": self.detail,
        }


def num(inputs: dict[str, Any], key: str) -> float | None:
    """입력에서 유한 수치만 안전 추출(비수치·NaN/inf·None → None=평가 생략, 무목업)."""
    if not isinstance(inputs, dict) or key not in inputs:
        return None
    v = inputs[key]
    if isinstance(v, bool):  # bool은 수치로 취급하지 않음
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def num_or(inputs: dict[str, Any], key: str, default: float) -> float:
    """num()이되 결측만 default(명시된 0 등 falsy 유효값은 보존 — `or DEFAULT` falsy버그 차단)."""
    v = num(inputs, key)
    return default if v is None else v


def worst_verdict(evaluations: list[RuleEvaluation]) -> str | None:
    """평가 집합의 최악 판정(없으면 None) — 종합 게이트 표기용."""
    if not evaluations:
        return None
    return max((e.verdict for e in evaluations), key=lambda v: _SEVERITY.get(v, 0))
