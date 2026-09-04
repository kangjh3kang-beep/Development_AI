"""field_audit 규칙 레지스트리 — @register_audit_rule 데코레이터 + 순회 기전.

규칙 = **pure fn** `(payload: dict, ctx: dict) -> list[AuditFinding]`. 값을 생산하지 않고
이미 계산된 payload(result)를 '규칙에 맞는가'로만 판정한다(symbolic dispose). 부작용·I/O·
LLM 호출 금지(불변식은 pure O(n) — on-path 지연 무시 조건).

W0(Phase0)는 **규칙 0건 등록** — 기전(데코레이터·레지스트리·iterate)만 고정한다. 실제
불변식(G1 protection_zone_severity 등)은 W1부터 이 데코레이터로 붙는다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from app.services.verification.field_audit.contracts import AuditFinding, Tier

logger = structlog.get_logger(__name__)

# 규칙 시그니처: (payload, ctx) -> list[AuditFinding]. pure fn.
AuditRule = Callable[[dict[str, Any], dict[str, Any]], list[AuditFinding]]


class RegisteredRule:
    """등록된 규칙 1건 — id·tier·fn 번들."""

    __slots__ = ("rule_id", "tier", "fn")

    def __init__(self, rule_id: str, tier: Tier, fn: AuditRule) -> None:
        self.rule_id = rule_id
        self.tier = tier
        self.fn = fn


# 프로세스 전역 레지스트리(모듈 임포트 시 데코레이터가 채운다). W0에서는 빈 채로 유지.
_REGISTRY: list[RegisteredRule] = []
_SEEN_IDS: set[str] = set()


def register_audit_rule(rule_id: str, tier: Tier) -> Callable[[AuditRule], AuditRule]:
    """감사 규칙 등록 데코레이터.

    사용:
        @register_audit_rule("G1_PROTECTION_ZONE_RISK_FLOOR", tier="A")
        def rule(payload: dict, ctx: dict) -> list[AuditFinding]:
            ...

    rule_id 중복은 **무시**(경고 로그)하여 모듈 이중 임포트가 규칙을 중복 실행하지 않게 한다
    (멱등). 데코레이터는 fn을 변형 없이 반환한다(직접 호출·단위테스트 가능).
    """

    def _decorator(fn: AuditRule) -> AuditRule:
        if rule_id in _SEEN_IDS:
            logger.warning("field_audit 규칙 중복 등록 무시", rule_id=rule_id)
            return fn
        _SEEN_IDS.add(rule_id)
        _REGISTRY.append(RegisteredRule(rule_id=rule_id, tier=tier, fn=fn))
        return fn

    return _decorator


def iter_rules() -> list[RegisteredRule]:
    """등록된 규칙을 등록순으로 반환(복사본 — 외부 변형이 레지스트리를 오염 못 하게)."""
    return list(_REGISTRY)


def registered_rule_ids() -> list[str]:
    """등록된 규칙 id 목록(관측·테스트용)."""
    return [r.rule_id for r in _REGISTRY]


def rule_count() -> int:
    """등록된 규칙 수(W0=0)."""
    return len(_REGISTRY)


def clear_registry() -> None:
    """레지스트리 초기화 — **테스트 전용**(런타임 호출 금지). 격리 테스트가 규칙을
    등록/해제할 때 상태 누수를 막는다.
    """
    _REGISTRY.clear()
    _SEEN_IDS.clear()
