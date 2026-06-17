"""R0 — 정규 변수 사전(canonical_vars). 정량 변수의 단일 정의 출처.

미등록 변수를 참조하는 룰은 등록 거부(RuleContractError, INV-4). 단위는 Unit enum으로 고정.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.enums import Method, Unit
from app.core.errors import RuleContractError


class CanonicalVariable(BaseModel):
    """정량 변수 1건의 정규 정의."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    definition: str = ""
    unit: Unit
    basis_article: str | None = None
    allowed_sources: list[Method] = Field(default_factory=list)
    required_for_rules: list[str] = Field(default_factory=list)
    required: bool = False


class VariableRegistry:
    """변수 등록/조회 + 룰 바인딩 계약 강제."""

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
