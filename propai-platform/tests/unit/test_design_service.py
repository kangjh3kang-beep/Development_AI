"""설계 AI 보고서 서비스 단위 테스트.

inspect.getsource() 패턴 + 상수/프롬프트 검증.
외부 의존성(ChatAnthropic)이 필요하므로 소스 코드 분석 중심.
"""

import inspect

from apps.api.services.design_ai_service import (
    _DESIGN_PROMPT_TEMPLATE,
    DesignAIService,
)


class TestDesignPromptTemplate:
    """설계 보고서 프롬프트 템플릿 검증."""

    def test_has_6_sections(self) -> None:
        """보고서 구성이 6개 섹션을 포함한다."""
        for section in ["설계 개요", "공간 구성 분석", "법규 적합성", "에너지 효율", "개선 권고", "종합 평가"]:
            assert section in _DESIGN_PROMPT_TEMPLATE

    def test_korean_instruction(self) -> None:
        """한국어 작성 지시가 포함된다."""
        assert "한국어" in _DESIGN_PROMPT_TEMPLATE

    def test_design_data_placeholder(self) -> None:
        """design_data 플레이스홀더가 있다."""
        assert "{design_data}" in _DESIGN_PROMPT_TEMPLATE

    def test_markdown_format_requested(self) -> None:
        """마크다운 형식 요청이 포함된다."""
        assert "마크다운" in _DESIGN_PROMPT_TEMPLATE


class TestDesignAIServiceCode:
    """DesignAIService 소스 코드 검증."""

    def test_stream_uses_anthropic(self) -> None:
        """stream_design_report()에서 ChatAnthropic을 사용한다."""
        src = inspect.getsource(DesignAIService.stream_design_report)
        assert "ChatAnthropic" in src

    def test_stream_uses_streaming(self) -> None:
        """stream_design_report()에서 streaming=True를 설정한다."""
        src = inspect.getsource(DesignAIService.stream_design_report)
        assert "streaming=True" in src

    def test_stream_uses_astream(self) -> None:
        """stream_design_report()에서 astream을 사용한다."""
        src = inspect.getsource(DesignAIService.stream_design_report)
        assert "astream" in src

    def test_streaming_yields_events(self) -> None:
        """stream_design_report()에서 StreamingReportEvent를 yield한다."""
        src = inspect.getsource(DesignAIService.stream_design_report)
        assert "StreamingReportEvent" in src
        assert "yield" in src

    def test_streaming_sends_final_event(self) -> None:
        """stream_design_report()에서 is_final=True 이벤트를 전송한다."""
        src = inspect.getsource(DesignAIService.stream_design_report)
        assert "is_final=True" in src

    def test_sync_uses_ainvoke(self) -> None:
        """generate_design_sync()에서 ainvoke를 사용한다."""
        src = inspect.getsource(DesignAIService.generate_design_sync)
        assert "ainvoke" in src

    def test_sync_fallback_message(self) -> None:
        """generate_design_sync() 실패 시 한국어 안내 메시지를 반환한다."""
        src = inspect.getsource(DesignAIService.generate_design_sync)
        assert "생성할 수 없습니다" in src

    def test_tracks_ai_usage(self) -> None:
        """AI 비용을 track_ai_usage로 기록한다."""
        src = inspect.getsource(DesignAIService.stream_design_report)
        assert "track_ai_usage" in src

    def test_sync_tracks_ai_usage(self) -> None:
        """동기 생성에서도 AI 비용을 기록한다."""
        src = inspect.getsource(DesignAIService.generate_design_sync)
        assert "track_ai_usage" in src
