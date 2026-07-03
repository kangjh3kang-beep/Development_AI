"""RegulationService 단위 테스트.

법규 RAG 검토 서비스의 인터페이스 및 LLM 분석 실패 시 폴백을 테스트한다.
외부 API(Qdrant, OpenAI, Claude) 없이 Mock으로 검증.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from datetime import UTC

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
            # ★fail-open 제거(회귀잠금): 자동 분석 실패는 '적합(True)'을 단정하면 안 된다.
            # 과거엔 is_compliant=True/confidence=0.3을 반환하는 fail-open 버그였다 —
            # 이제 fail-closed(False=적합 아님, confidence=0.0)로 잠근다.
            assert result["is_compliant"] is False
            assert result["confidence"] == 0.0
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


class TestCheckRegulationFailClosed:
    """check_regulation — 분석에 is_compliant 키가 없으면 '적합(True)'으로 저장하면 안 된다.

    ★회귀잠금(라이브 검증 확인): regulation_service:279 의 기본값이 True로 되돌아가면
    '검토되지 않은 결과'가 DB에 is_compliant=True(적합)로 저장돼 사용자에게 흘러간다(fail-open).
    이 테스트는 그 회귀를 잠근다 — :279 를 True로 되돌리면 반드시 실패(red)한다.
    """

    @pytest.mark.asyncio
    async def test_is_compliant_키_없으면_False로_저장(self):
        from datetime import datetime

        mock_db = AsyncMock()

        # db.refresh(regulation)은 실제 DB처럼 id·created_at을 채워준다(응답 검증 통과용).
        # 이때 채워진 뒤에도 is_compliant 값은 check_regulation이 세팅한 값 그대로 남는다.
        async def _fake_refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=_fake_refresh)

        with patch("apps.api.services.regulation_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test")
            svc = RegulationService(mock_db)

            # 임베딩·검색·LLM분석을 모두 목킹(외부 의존 제거). 분석 결과에는
            # ★일부러 is_compliant 키를 넣지 않는다 — 코드의 .get(..., 기본값) 분기를 태운다.
            svc._embed_query = AsyncMock(return_value=[0.1] * 1536)
            svc._search_regulations = AsyncMock(
                return_value=[{"id": "doc-1", "payload": {}}]
            )
            svc._analyze_compliance = AsyncMock(
                return_value={
                    "confidence": 0.8,
                    "violations": [],
                    "recommendations": [],
                    "summary": "x",
                    # is_compliant 키 없음(의도적) — fail-closed 기본값이 False여야 한다.
                }
            )

            await svc.check_regulation(
                project_id=uuid4(),
                tenant_id=uuid4(),
                regulation_type="zoning",
                project_info={"address": "서울시"},
            )

            # db.add(regulation)에 전달된 ORM 객체를 캡처해 is_compliant를 직접 확인.
            assert mock_db.add.call_count == 1
            saved_regulation = mock_db.add.call_args[0][0]
            # ★fail-open 잠금: is_compliant 키가 없을 때 절대 True가 아님(fail-closed=False).
            # :279 를 analysis.get("is_compliant", True)로 되돌리면 이 단언에서 실패(red)한다.
            assert saved_regulation.is_compliant is not True
            assert saved_regulation.is_compliant is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
