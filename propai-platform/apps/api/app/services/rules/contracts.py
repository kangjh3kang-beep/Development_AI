"""Rule DSL 공용 계약 — 단위/비교연산자/변수사전(심의엔진 CalcRule 파일럿 승격).

필드명·시맨틱은 심의엔진(services/deliberation-review) 파일럿을 최대한 보존한다(단,
"동형"은 정확한 표현이 아니라 아래처럼 일치/불일치 범위를 명시한다):
- ``Unit``/``Comparator``: services/deliberation-review/.../app/contracts/enums.py와
  멤버(값 목록) 동일·기반클래스는 StrEnum로 현대화(원본 대비 구현이 갱신됨).
- ``CanonicalVariable``/``VariableRegistry``: .../app/contracts/canonical_vars.py와
  멤버 동일(register/lookup/bind_rule — 미등록 변수 참조는 등록 거부, INV-4 동일 원칙).
  단 allowed_sources/required_for_rules 2필드는 apps/api 문맥상 미승계(원본 전용 필드,
  이 승격 사본 범위 밖).

심의엔진은 독립 마이크로서비스라 import 불가(W3-6 재확증) — 이 파일은 그 설계의
"동형 재구현"이 아니라 apps/api 전용 승격 사본이다(필드 형태 일치, 코드는 별개).
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class RuleContractError(Exception):
    """Rule DSL 계약 위반(미등록 변수 참조 등). 심의엔진 RuleContractError와 동형(표준 예외)."""


class Unit(StrEnum):
    """정량 변수 단위(고정). 단위 불일치는 거부한다(심의엔진 enums.Unit과 동형)."""

    M = "m"
    M2 = "m2"
    PERCENT = "percent"
    COUNT = "count"
    M_ABOVE_GROUND = "m_above_ground"
    RATIO = "ratio"
    NONE = "none"


class Comparator(StrEnum):
    """판정 비교연산자(고정). measured (comparator) limit → compliant.

    free-form str 오타의 무음 동등성(!=) 폴백을 차단(심의엔진 enums.Comparator와 동형).
    """

    LE = "<="
    GE = ">="
    LT = "<"
    GT = ">"
    EQ = "=="


class CanonicalVariable(BaseModel):
    """정량 변수 1건의 정규 정의(심의엔진 canonical_vars.CanonicalVariable과 동형)."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    definition: str = ""
    unit: Unit
    basis_article: str | None = None
    required: bool = False


class VariableRegistry:
    """변수 등록/조회 + 룰 바인딩 계약 강제(심의엔진 VariableRegistry와 동형 API)."""

    def __init__(self) -> None:
        self._by_name: dict[str, CanonicalVariable] = {}

    def register(self, var: CanonicalVariable) -> CanonicalVariable:
        self._by_name[var.name] = var
        return var

    def is_registered(self, name: str) -> bool:
        return name in self._by_name

    def lookup(self, name: str) -> CanonicalVariable:
        if name not in self._by_name:
            raise RuleContractError(f"undefined variable reference: {name}")
        return self._by_name[name]

    def bind_rule(self, refs: list[str]) -> bool:
        """룰이 참조하는 변수들이 전부 등록돼 있어야 바인딩 허용. 아니면 등록 거부."""
        missing = [r for r in refs if r not in self._by_name]
        if missing:
            raise RuleContractError(f"rule references undefined variables: {missing}")
        return True


def build_default_registry(variables: list[CanonicalVariable]) -> VariableRegistry:
    """CanonicalVariable 목록으로 레지스트리를 시드(심의엔진 variable_seed.py 패턴)."""
    reg = VariableRegistry()
    for v in variables:
        reg.register(v)
    return reg


__all__ = [
    "CanonicalVariable",
    "Comparator",
    "RuleContractError",
    "Unit",
    "VariableRegistry",
    "build_default_registry",
]
