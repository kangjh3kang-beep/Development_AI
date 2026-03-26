"""블록체인 라우터 단위 테스트.

에스크로 엔드포인트 인증 요구 및 요청 검증을 테스트한다.
"""

import os
import sys
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class TestEscrowEndpoints:
    """블록체인 에스크로 엔드포인트 인증 테스트."""

    @pytest.mark.asyncio
    async def test_create_escrow_인증없이_거부(self, client):
        response = await client.post("/api/v1/blockchain/escrow", json={
            "project_id": str(uuid4()),
            "payer_address": "0x" + "a" * 40,
            "payee_address": "0x" + "b" * 40,
        })
        assert response.status_code in {401, 403}

    @pytest.mark.asyncio
    async def test_fund_escrow_인증없이_거부(self, client):
        response = await client.post(
            f"/api/v1/blockchain/escrow/fund?escrow_db_id={uuid4()}",
            json={"amount_wei": "1000000000000000000"},
        )
        assert response.status_code in {401, 403, 422}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
