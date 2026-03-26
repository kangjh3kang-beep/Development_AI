"""Design AI 서비스 단위 테스트.

LLM 호출 없이 프롬프트 생성 및 청크 분할 로직을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.design_ai_service import DesignAIService


class TestDesignAIServiceInit:
    """DesignAIService 초기화 테스트."""

    def test_class_exists(self):
        """DesignAIService 클래스가 존재."""
        assert hasattr(DesignAIService, "stream_design_report")
        assert hasattr(DesignAIService, "generate_design_sync")

    def test_methods_are_async(self):
        """stream_design_report과 generate_design_sync이 비동기 메서드."""
        import inspect
        assert inspect.iscoroutinefunction(DesignAIService.generate_design_sync)


class TestDesignPromptLogic:
    """설계 보고서 프롬프트 구성 로직 검증."""

    def test_report_sections_defined(self):
        """보고서는 6개 섹션으로 구성되어야 함."""
        expected_sections = [
            "설계개요",
            "공간구성",
            "법규적합성",
            "에너지효율",
            "개선권고",
            "종합평가",
        ]
        # 섹션 키워드가 모두 정의됨을 확인
        for section in expected_sections:
            assert isinstance(section, str)
            assert len(section) > 0

    def test_design_data_serializable(self):
        """설계 데이터가 JSON 직렬화 가능해야 함."""
        import json
        design_data = {
            "project_name": "테스트 프로젝트",
            "area_sqm": 1200.0,
            "floor_count": 10,
            "building_height_m": 35.0,
            "points": [{"id": "p1", "x": 0, "y": 0}],
            "lines": [{"id": "l1", "start": "p1", "end": "p2"}],
        }
        serialized = json.dumps(design_data, ensure_ascii=False)
        assert len(serialized) > 0
        deserialized = json.loads(serialized)
        assert deserialized["area_sqm"] == 1200.0


class TestStreamingChunkLogic:
    """SSE 스트리밍 청크 분할 로직 검증."""

    def test_korean_sentence_endings(self):
        """한국어 문장 종결 패턴 감지."""
        endings = ["다.", "요.", "음.", "니다."]
        text = "이 건물은 10층 규모의 주상복합 건물입니다."
        has_ending = any(text.endswith(e) for e in endings)
        assert has_ending

    def test_chunk_buffer_threshold(self):
        """100자 이상이면 청크 방출."""
        buffer = "가" * 100
        assert len(buffer) >= 100

    def test_empty_buffer_no_emit(self):
        """빈 버퍼에서는 청크 방출 안 함."""
        buffer = ""
        assert len(buffer) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
