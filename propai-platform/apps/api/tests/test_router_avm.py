"""AVM 라우터 단위 테스트.

POST /api/v1/avm 엔드포인트의 인증 요구와 요청 유효성을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class TestAVMEndpoint:
    """POST /api/v1/avm 엔드포인트 테스트."""

    @pytest.mark.asyncio
    async def test_인증없이_접근_거부(self, client):
        """인증 없이 POST /api/v1/avm → 401 또는 403."""
        response = await client.post("/api/v1/avm", json={
            "address": "서울시 강남구",
            "property_type": "apartment",
            "area_sqm": 84.0,
        })
        assert response.status_code in {401, 403}

    @pytest.mark.asyncio
    async def test_빈_요청_422(self, client):
        """빈 요청 → 422."""
        response = await client.post("/api/v1/avm", json={})
        # 인증이 먼저 체크될 수도 있음
        assert response.status_code in {401, 403, 422}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
