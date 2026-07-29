"""field_audit 불변식(pure fn 규칙) 모음 — 임포트 시 규칙이 rules_registry에 등록된다.

W1부터 계층 A 하드 불변식이 여기 등록된다(W1-1: cross_field.G1 protection_zone_severity).
이 패키지를 임포트하면 하위 모듈의 register_rules()가 실행돼 프로덕션 규칙이 활성화된다.
"""

from app.services.verification.field_audit.invariants import cross_field  # noqa: F401  임포트 부작용=규칙 등록

__all__ = ["cross_field"]
