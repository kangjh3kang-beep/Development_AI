"""평면도 이미지 생성 서비스 단위 테스트.

순수 로직 검증:
1. _build_prompt() — SDXL용 프롬프트 생성
"""

from unittest.mock import AsyncMock

from apps.api.services.floor_plan_image_service import FloorPlanImageService


def _make_service() -> FloorPlanImageService:
    """Mock DB 세션으로 서비스 생성."""
    return FloorPlanImageService(AsyncMock())


# ──────────────────────────────────────
# _build_prompt 검증
# ──────────────────────────────────────


class TestBuildPrompt:
    """SDXL 프롬프트 생성 검증."""

    def test_default_style(self) -> None:
        """기본 스타일 'modern' 포함."""
        svc = _make_service()
        prompt = svc._build_prompt(84.0, 3)
        assert "modern" in prompt

    def test_custom_style(self) -> None:
        """사용자 지정 스타일 반영."""
        svc = _make_service()
        prompt = svc._build_prompt(84.0, 3, style="minimalist")
        assert "minimalist" in prompt

    def test_room_count_in_prompt(self) -> None:
        """방 개수가 프롬프트에 포함."""
        svc = _make_service()
        prompt = svc._build_prompt(84.0, 3)
        assert "3 bedrooms" in prompt

    def test_area_in_prompt(self) -> None:
        """면적이 프롬프트에 포함."""
        svc = _make_service()
        prompt = svc._build_prompt(84.0, 3)
        assert "84.0sqm" in prompt or "84sqm" in prompt

    def test_additional_text(self) -> None:
        """추가 텍스트가 프롬프트에 반영."""
        svc = _make_service()
        prompt = svc._build_prompt(84.0, 3, additional="with balcony")
        assert "with balcony" in prompt

    def test_architectural_keywords(self) -> None:
        """건축 관련 키워드 포함."""
        svc = _make_service()
        prompt = svc._build_prompt(100.0, 4)
        assert "floor plan" in prompt
        assert "architectural" in prompt

    def test_different_room_counts(self) -> None:
        """다양한 방 개수가 정확히 반영."""
        svc = _make_service()
        prompt_1 = svc._build_prompt(60.0, 1)
        prompt_5 = svc._build_prompt(150.0, 5)
        assert "1 bedrooms" in prompt_1 or "1 bedroom" in prompt_1
        assert "5 bedrooms" in prompt_5

    def test_korean_label_in_prompt(self) -> None:
        """한국어 라벨 요청이 프롬프트에 포함."""
        svc = _make_service()
        prompt = svc._build_prompt(84.0, 3)
        assert "Korean" in prompt

    def test_empty_additional(self) -> None:
        """추가 텍스트 없이도 정상 동작."""
        svc = _make_service()
        prompt = svc._build_prompt(84.0, 3, additional="")
        assert "floor plan" in prompt
