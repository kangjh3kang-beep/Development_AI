"""설계 AI Vision 확장 테스트 (Phase 8 강화).

DesignInput/DesignOutput Pydantic 모델, Vision 분석, 구조화 보고서 테스트.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.design_ai_service import (
    DesignAIService,
    DesignInput,
    DesignOutput,
)


# ── Pydantic 모델 테스트 ──


class TestDesignModels:
    """DesignInput / DesignOutput 모델 테스트."""

    def test_design_input_serialization(self):
        """DesignInput 직렬화/역직렬화."""
        pid = uuid4()
        tid = uuid4()
        inp = DesignInput(
            project_id=pid,
            tenant_id=tid,
            design_data={"floor_count": 5},
            image_urls=["https://example.com/img.jpg"],
        )
        data = inp.model_dump()
        assert data["project_id"] == pid
        assert len(data["image_urls"]) == 1

    def test_design_input_defaults(self):
        """image_urls 기본값은 빈 리스트."""
        inp = DesignInput(
            project_id=uuid4(),
            tenant_id=uuid4(),
            design_data={},
        )
        assert inp.image_urls == []

    def test_design_output_serialization(self):
        """DesignOutput 직렬화."""
        out = DesignOutput(
            report_text="테스트 보고서",
            sections=[{"title": "개요", "content": "내용"}],
            image_analysis={"analysis": "분석 결과"},
            recommendations=["추천 1"],
        )
        data = out.model_dump()
        assert data["report_text"] == "테스트 보고서"
        assert len(data["sections"]) == 1
        assert data["image_analysis"]["analysis"] == "분석 결과"

    def test_design_output_none_image_analysis(self):
        """image_analysis가 None일 수 있음."""
        out = DesignOutput(report_text="test")
        assert out.image_analysis is None
        assert out.sections == []
        assert out.recommendations == []


# ── analyze_design_image 테스트 ──


class TestAnalyzeDesignImage:
    """Vision 분석 메서드 테스트."""

    def _make_svc(self):
        svc = object.__new__(DesignAIService)
        svc.settings = MagicMock()
        svc.settings.anthropic_api_key = "test-key"
        return svc

    @pytest.mark.asyncio
    async def test_url_input(self):
        """URL 입력은 url 타입으로 처리."""
        svc = self._make_svc()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="건축 스타일 분석 결과")]

        mock_anthropic = MagicMock()
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)
        mock_anthropic.AsyncAnthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = await svc.analyze_design_image("https://example.com/img.jpg")
            assert result["analysis"] == "건축 스타일 분석 결과"
            assert result["model"] == "claude-sonnet-4-5-20250929"

    @pytest.mark.asyncio
    async def test_base64_input(self):
        """base64 입력 (500자 초과) 처리."""
        svc = self._make_svc()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="base64 분석")]

        mock_anthropic = MagicMock()
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)
        mock_anthropic.AsyncAnthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            long_b64 = "data:image/jpeg;base64," + "A" * 600
            result = await svc.analyze_design_image(long_b64)
            assert result["analysis"] == "base64 분석"

    @pytest.mark.asyncio
    async def test_vision_failure_fallback(self):
        """API 실패 시 폴백 응답 (anthropic 미설치)."""
        svc = self._make_svc()
        # anthropic 모듈이 없으면 ImportError -> except에서 폴백
        result = await svc.analyze_design_image("https://example.com/img.jpg")
        assert "분석을 수행할 수 없습니다" in result["analysis"]
        assert "error" in result


# ── generate_design_structured 테스트 ──


class TestGenerateDesignStructured:
    """구조화된 설계 보고서 생성 테스트."""

    def _make_svc(self):
        svc = object.__new__(DesignAIService)
        svc.settings = MagicMock()
        svc.settings.anthropic_api_key = "test-key"
        return svc

    @pytest.mark.asyncio
    async def test_structured_without_image(self):
        """이미지 없이 구조화 보고서 생성."""
        svc = self._make_svc()
        svc.generate_design_sync = AsyncMock(
            return_value="## 설계 개요\n내용1\n## 개선 권고\n추천 사항"
        )

        inp = DesignInput(
            project_id=uuid4(),
            tenant_id=uuid4(),
            design_data={"floor_count": 3},
        )
        result = await svc.generate_design_structured(inp)
        assert isinstance(result, DesignOutput)
        assert len(result.sections) >= 2
        assert result.image_analysis is None

    @pytest.mark.asyncio
    async def test_structured_with_image(self):
        """이미지 포함 구조화 보고서 생성."""
        svc = self._make_svc()
        svc.generate_design_sync = AsyncMock(return_value="## 개요\n내용")
        svc.analyze_design_image = AsyncMock(
            return_value={"analysis": "모던 건축", "model": "test"}
        )

        inp = DesignInput(
            project_id=uuid4(),
            tenant_id=uuid4(),
            design_data={},
            image_urls=["https://example.com/img.jpg"],
        )
        result = await svc.generate_design_structured(inp)
        assert result.image_analysis is not None
        assert result.image_analysis["analysis"] == "모던 건축"

    @pytest.mark.asyncio
    async def test_sections_parsing(self):
        """## 기준 섹션 파싱."""
        svc = self._make_svc()
        svc.generate_design_sync = AsyncMock(
            return_value="## 설계 개요\n개요 내용\n## 법규 적합성\n법규 내용\n## 개선 권고\n권고 내용"
        )

        inp = DesignInput(project_id=uuid4(), tenant_id=uuid4(), design_data={})
        result = await svc.generate_design_structured(inp)
        titles = [s["title"] for s in result.sections]
        assert "설계 개요" in titles
        assert "법규 적합성" in titles

    @pytest.mark.asyncio
    async def test_recommendations_extraction(self):
        """권고/개선 섹션에서 recommendations 추출."""
        svc = self._make_svc()
        svc.generate_design_sync = AsyncMock(
            return_value="## 설계 개요\n개요\n## 개선 권고\n에너지 절감을 위해 단열재 교체 필요"
        )

        inp = DesignInput(project_id=uuid4(), tenant_id=uuid4(), design_data={})
        result = await svc.generate_design_structured(inp)
        assert len(result.recommendations) >= 1
        assert "단열재" in result.recommendations[0]
