"""설계 라우터 단위 테스트.

요청 모델 유효성 및 인증 요구를 검증한다.
"""

import os
import sys
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.routers.design import FloorPlanRequest, IFCAnalyzeRequest


class TestFloorPlanRequest:
    """FloorPlanRequest Pydantic 모델 테스트."""

    def test_기본값_style_modern(self):
        req = FloorPlanRequest(
            project_id=uuid4(),
            area_sqm=100.0,
            room_count=3,
        )
        assert req.style == "modern"

    def test_전체_필드(self):
        req = FloorPlanRequest(
            project_id=uuid4(),
            area_sqm=200.0,
            room_count=5,
            style="classic",
        )
        assert req.area_sqm == 200.0
        assert req.room_count == 5
        assert req.style == "classic"


class TestIFCAnalyzeRequest:
    """IFCAnalyzeRequest Pydantic 모델 테스트."""

    def test_필수_필드(self):
        req = IFCAnalyzeRequest(
            project_id=uuid4(),
            file_url="http://minio:9000/bim/test.ifc",
        )
        assert req.file_url.startswith("http")


class TestDesignEndpoints:
    """설계 엔드포인트 인증 테스트."""

    @pytest.mark.asyncio
    async def test_floor_plan_인증없이_거부(self, client):
        response = await client.post("/api/v1/design/floor-plan", json={
            "project_id": str(uuid4()),
            "area_sqm": 100,
            "room_count": 3,
        })
        assert response.status_code in {401, 403}

    @pytest.mark.asyncio
    async def test_bim_analyze_인증없이_거부(self, client):
        response = await client.post("/api/v1/design/bim/analyze", json={
            "project_id": str(uuid4()),
            "file_url": "http://minio:9000/bim/test.ifc",
        })
        assert response.status_code in {401, 403}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
