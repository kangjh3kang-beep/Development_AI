"""AuditService(record_audit) 단위 테스트.

INSERT-ONLY 감사 추적 기록 함수의 인터페이스를 검증한다.
AsyncMock DB로 DB 커밋 없이 테스트.
"""

import os
import sys
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.audit_service import record_audit


@pytest.mark.asyncio
async def test_감사_레코드_DB에_추가():
    """record_audit 호출 시 db.add + db.flush 호출."""
    mock_db = AsyncMock()
    mock_db.add = lambda x: None
    mock_db.flush = AsyncMock()

    result = await record_audit(
        mock_db,
        tenant_id=uuid4(),
        entity_type="project",
        entity_id=uuid4(),
        action="create",
        actor_id=uuid4(),
    )
    assert result is not None
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_before_after_state_저장():
    """변경 전/후 상태가 레코드에 포함."""
    mock_db = AsyncMock()
    mock_db.add = lambda x: None
    mock_db.flush = AsyncMock()

    before = {"name": "old"}
    after = {"name": "new"}
    result = await record_audit(
        mock_db,
        tenant_id=uuid4(),
        entity_type="project",
        entity_id=uuid4(),
        action="update",
        actor_id=uuid4(),
        before_state=before,
        after_state=after,
    )
    assert result.before_state == before
    assert result.after_state == after


@pytest.mark.asyncio
async def test_IP_주소_기록():
    mock_db = AsyncMock()
    mock_db.add = lambda x: None
    mock_db.flush = AsyncMock()

    result = await record_audit(
        mock_db,
        tenant_id=uuid4(),
        entity_type="user",
        entity_id=uuid4(),
        action="login",
        actor_id=uuid4(),
        ip_address="192.168.1.1",
    )
    assert result.ip_address == "192.168.1.1"


@pytest.mark.asyncio
async def test_사유_기록():
    mock_db = AsyncMock()
    mock_db.add = lambda x: None
    mock_db.flush = AsyncMock()

    result = await record_audit(
        mock_db,
        tenant_id=uuid4(),
        entity_type="escrow",
        entity_id=uuid4(),
        action="dispute",
        actor_id=uuid4(),
        reason="시공 하자 발견",
    )
    assert result.reason == "시공 하자 발견"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
