"""에너지 라우터 단위 테스트.

에너지 엔드포인트 인증 요구를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class TestEnergyEndpoints:
    """에너지 엔드포인트 인증 테스트."""

    @pytest.mark.asyncio
    async def test_kepco_bill_인증없이_거부(self, client):
        response = await client.post("/api/v1/energy/kepco/calculate", json={})
        assert response.status_code in {401, 403, 422}

    @pytest.mark.asyncio
    async def test_certify_인증없이_거부(self, client):
        response = await client.post("/api/v1/energy/certification", json={})
        assert response.status_code in {401, 403, 422}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
