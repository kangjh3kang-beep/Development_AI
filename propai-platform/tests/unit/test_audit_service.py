"""감사 추적 서비스 단위 테스트.

record_audit() 함수 구조 및 INSERT-ONLY 패턴 검증.
"""

import inspect

from apps.api.database.models.legal_audit_trail import LegalAuditTrail
from apps.api.services.audit_service import record_audit


class TestRecordAuditCode:
    """record_audit() 코드 구조 검증."""

    def test_creates_legal_audit_trail(self) -> None:
        """record_audit가 LegalAuditTrail을 생성한다."""
        source = inspect.getsource(record_audit)
        assert "LegalAuditTrail" in source

    def test_insert_only_pattern(self) -> None:
        """record_audit가 INSERT-ONLY 패턴을 따른다 (db.add + db.flush만 호출)."""
        source = inspect.getsource(record_audit)
        assert "db.add" in source
        assert "db.flush" in source
        # 삭제/수정 코드가 없어야 함
        assert "db.delete" not in source

    def test_accepts_required_fields(self) -> None:
        """record_audit가 필수 매개변수를 받는다."""
        sig = inspect.signature(record_audit)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "tenant_id" in params
        assert "entity_type" in params
        assert "entity_id" in params
        assert "action" in params
        assert "actor_id" in params

    def test_accepts_optional_fields(self) -> None:
        """record_audit가 선택적 매개변수를 받는다."""
        sig = inspect.signature(record_audit)
        params = sig.parameters
        assert params["before_state"].default is None
        assert params["after_state"].default is None
        assert params["reason"].default is None
        assert params["ip_address"].default is None

    def test_returns_type_annotation(self) -> None:
        """record_audit가 LegalAuditTrail을 반환 타입으로 명시한다."""
        sig = inspect.signature(record_audit)
        assert sig.return_annotation is LegalAuditTrail


class TestLegalAuditTrailModel:
    """LegalAuditTrail 모델 구조 검증."""

    def test_tablename(self) -> None:
        """테이블명이 legal_audit_trail이다."""
        assert LegalAuditTrail.__tablename__ == "legal_audit_trail"

    def test_has_entity_type_column(self) -> None:
        """entity_type 컬럼이 존재한다."""
        columns = [c.name for c in LegalAuditTrail.__table__.columns]
        assert "entity_type" in columns

    def test_has_action_column(self) -> None:
        """action 컬럼이 존재한다."""
        columns = [c.name for c in LegalAuditTrail.__table__.columns]
        assert "action" in columns

    def test_has_before_after_state(self) -> None:
        """before_state/after_state 컬럼이 존재한다."""
        columns = [c.name for c in LegalAuditTrail.__table__.columns]
        assert "before_state" in columns
        assert "after_state" in columns

    def test_has_ip_address(self) -> None:
        """ip_address 컬럼이 존재한다."""
        columns = [c.name for c in LegalAuditTrail.__table__.columns]
        assert "ip_address" in columns

    def test_action_values_documented(self) -> None:
        """action 컬럼 코멘트에 동작 목록이 명시되어 있다."""
        action_col = LegalAuditTrail.__table__.c.action
        assert action_col.comment is not None
        assert "create" in action_col.comment
        assert "update" in action_col.comment
        assert "delete" in action_col.comment
