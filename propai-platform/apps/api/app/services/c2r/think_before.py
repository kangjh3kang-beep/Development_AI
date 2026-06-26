"""Think-Before 게이팅 — 렌더 직전, 브리프가 충분·정합한지 결정론적으로 판정.

Karpathy 원칙 1(Think-Before): 불확실하면 먼저 묻고, 모순이면 진행하지 않는다.
이 모듈은 LLM 없이(결정론) 브리프를 점검해 ambiguous/proceed 를 판정한다.

진행 차단(proceed=False) 조건:
 - success_criteria 가 비어 있음(무엇을 만족해야 성공인지 미정의) → ambiguous.
 - 핵심 인벨로프 제약(건폐율/용적률)이 모두 미확보(value=None) → 근거 부재.
 - 매스가 인벨로프를 초과(target_floors > max_floors 등) → 모순.
"""

from __future__ import annotations

from typing import Any


def _value(constraint: Any) -> Any:
    """근거계약 {value,...} 또는 raw 값에서 value 추출."""
    if isinstance(constraint, dict):
        return constraint.get("value")
    return constraint


def evaluate(brief: dict[str, Any]) -> dict[str, Any]:
    """렌더 브리프를 점검해 진행 가능 여부를 판정(결정론).

    Returns:
        {
          "ambiguous": bool,           # 명료화가 필요한가
          "open_questions": [...],     # 사용자에게 되물을 질문(불확실 항목)
          "missing_criteria": [...],   # 비어있는 성공/제약 항목
          "proceed": bool,             # 렌더로 진행해도 되는가
        }
    """
    open_questions: list[str] = []
    missing: list[str] = []

    ec = brief.get("envelope_constraints") or {}
    program = brief.get("program") or {}
    success = brief.get("success_criteria") or []

    # 1) success_criteria 부재 → 목표 미정의(Goal-Driven 미충족).
    if not success:
        missing.append("success_criteria")
        open_questions.append("렌더 성공 기준이 정의되지 않았습니다 — 무엇을 만족해야 합니까?")

    # 2) 핵심 제약(건폐율/용적률) 미확보 → 근거 부재.
    bcr = _value(ec.get("building_coverage_ratio_pct"))
    far = _value(ec.get("floor_area_ratio_pct"))
    if bcr is None:
        missing.append("building_coverage_ratio_pct")
    if far is None:
        missing.append("floor_area_ratio_pct")
    if bcr is None and far is None:
        open_questions.append(
            "건폐율·용적률 제약을 모두 확보하지 못했습니다 — 용도지역을 확인할 수 있습니까?"
        )

    # 3) 모순: 매스(목표 층수)가 인벨로프(권장 상한)를 초과.
    target_floors = program.get("target_floors")
    max_floors = _value(ec.get("max_floors"))
    if (
        isinstance(target_floors, (int, float))
        and isinstance(max_floors, (int, float))
        and target_floors > max_floors
    ):
        open_questions.append(
            f"목표 층수({target_floors})가 인벨로프 권장 상한({max_floors})을 초과합니다 — "
            "층수를 낮추거나 용적률 인센티브 근거가 있습니까?"
        )

    ambiguous = bool(open_questions)
    # 진행 가능: 모순/명료화 필요가 없고, 성공기준이 정의되어 있을 때만.
    proceed = (not ambiguous) and bool(success)

    return {
        "ambiguous": ambiguous,
        "open_questions": open_questions,
        "missing_criteria": missing,
        "proceed": proceed,
    }
