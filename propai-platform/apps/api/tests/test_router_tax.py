"""세금 라우터 단위 테스트.

POST /api/v1/tax/calculate 엔드포인트의 인증/유효성을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class TestTaxCalculateEndpoint:
    """POST /api/v1/tax/calculate 테스트."""

    @pytest.mark.asyncio
    async def test_인증없이_접근_거부(self, client):
        response = await client.post("/api/v1/tax/calculate", json={
            "project_id": "00000000-0000-0000-0000-000000000003",
            "tax_type": "transfer",
            "taxable_value": 1000000000,
        })
        assert response.status_code in {401, 403}

    @pytest.mark.asyncio
    async def test_빈_요청_검증(self, client):
        response = await client.post("/api/v1/tax/calculate", json={})
        assert response.status_code in {401, 403, 422}


class TestTaxRequestModel:
    """TaxCalculateRequest Pydantic 모델 테스트."""

    def test_기본값_검증(self):
        from uuid import uuid4

        from apps.api.routers.tax import TaxCalculateRequest

        req = TaxCalculateRequest(
            project_id=uuid4(),
            tax_type="transfer",
            taxable_value=1_000_000_000,
        )
        assert req.is_first_home is False
        assert req.holding_years == 5

    def test_전체_필드_설정(self):
        from uuid import uuid4

        from apps.api.routers.tax import TaxCalculateRequest

        req = TaxCalculateRequest(
            project_id=uuid4(),
            tax_type="capital_gains",
            taxable_value=500_000_000,
            is_first_home=True,
            holding_years=10,
        )
        assert req.is_first_home is True
        assert req.holding_years == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
