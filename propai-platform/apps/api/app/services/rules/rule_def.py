"""RuleDef — 법규·계산 규칙 1건의 선언적 계약(심의엔진 CalcRule 파일럿 필드명 승격).

심의엔진 ``CalcRule``(rule_id·target_variable·params·basis_article·effective_date)의
필드를 그대로 계승하되, 그 파일럿은 산식 자체는 갖지 않고(값은 외부 Python 함수가
계산, params는 그 함수의 임계치 주입용) 본 승격판은 ``formula``/``limit`` 구조화
산식을 더해 "선언만으로 평가 가능"하게 일반화한다(계약+대표 규칙 승격 — 전면 이관은
이월).
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.services.rules.contracts import Comparator, Unit
from app.services.rules.expr import Expr


class RuleDef(BaseModel):
    """법규 판정/산정 규칙 1건.

    - ``inputs``: 참조하는 입력 변수명(VariableRegistry에 전부 등록돼 있어야 바인딩 허용).
    - ``formula``: target_variable 산출 산식(없으면 inputs[target_variable]을 측정값으로 간주).
    - ``limit``/``comparator``: 준수판정용 한도 산식 + 비교연산자(measured comparator limit).
    - ``params``: 임계치 하드코딩 금지 주입처(심의엔진 CalcRule INV-11 계승).
    - ``effective_date``: 유효 시행일(기준일보다 미래면 미시행 — UNKNOWN 취급).
    """

    rule_id: str
    target_variable: str
    basis_article: str
    inputs: list[str] = Field(default_factory=list)
    formula: Expr | None = None
    limit: Expr | None = None
    comparator: Comparator | None = None
    unit: Unit
    params: dict[str, float] = Field(default_factory=dict)
    effective_date: date | None = None


__all__ = ["RuleDef"]
