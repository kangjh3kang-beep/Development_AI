"""RegulationService 단위 테스트.

법규 RAG 검토 서비스의 인터페이스 및 LLM 분석 실패 시 폴백을 테스트한다.
외부 API(Qdrant, OpenAI, Claude) 없이 Mock으로 검증.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.regulation_service import RegulationService


class TestRegulationServiceInit:
    """서비스 초기화 테스트."""

    def test_인스턴스_생성(self):
        mock_db = AsyncMock()
        with patch("apps.api.services.regulation_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            svc = RegulationService(mock_db)
            assert svc.db is mock_db


class TestAnalyzeComplianceFallback:
    """LLM 분석 실패 시 폴백 테스트."""

    @pytest.mark.asyncio
    async def test_LLM_실패시_기본_응답_반환(self):
        mock_db = AsyncMock()
        with patch("apps.api.services.regulation_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test")
            svc = RegulationService(mock_db)

            # LLM 호출 실패를 시뮬레이션
            result = await svc._analyze_compliance(
                regulation_type="zoning",
                project_info={"address": "서울시"},
                retrieved_docs=[],
            )
            # 실패 시 기본값 반환
            assert result["is_compliant"] is True
            assert result["confidence"] == 0.3
            assert "수동 검토" in result["recommendations"][0]

    @pytest.mark.asyncio
    async def test_Qdrant_실패시_빈_결과(self):
        mock_db = AsyncMock()
        with patch("apps.api.services.regulation_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                qdrant_host="localhost",
                qdrant_port=6333,
            )
            svc = RegulationService(mock_db)

            # Qdrant 연결 실패 시 내장 법규 DB 폴백
            results = await svc._search_regulations([0.1] * 1536)
            assert len(results) >= 7  # BUILTIN_REGULATION_DB 7개 용도지역
            assert all("id" in r and "payload" in r for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
