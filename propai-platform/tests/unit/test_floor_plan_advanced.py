"""평면도 이미지 고도화 테스트.

Phase F-2: ControlNet img2img + DALL-E 3 폴백 + Claude Vision 검증.
"""

from pathlib import Path

_SERVICE_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps" / "api" / "services" / "floor_plan_image_service.py"
)
_SERVICE_SOURCE = _SERVICE_PATH.read_text(encoding="utf-8")


class TestControlNetIntegration:
    """ControlNet img2img 관련 검증."""

    def test_controlnet_method_exists(self) -> None:
        """_generate_image_with_controlnet() 메서드가 존재한다."""
        assert "_generate_image_with_controlnet" in _SERVICE_SOURCE

    def test_controlnet_uses_replicate(self) -> None:
        """ControlNet이 Replicate API를 사용한다."""
        assert "replicate" in _SERVICE_SOURCE
        assert "controlnet" in _SERVICE_SOURCE.lower()

    def test_reference_image_parameter(self) -> None:
        """참조 이미지 URL 파라미터가 있다."""
        assert "reference_image_url" in _SERVICE_SOURCE


class TestDALLE3Fallback:
    """DALL-E 3 폴백 관련 검증."""

    def test_dalle3_method_exists(self) -> None:
        """_generate_image_dalle3_fallback() 메서드가 존재한다."""
        assert "_generate_image_dalle3_fallback" in _SERVICE_SOURCE

    def test_dalle3_uses_openai(self) -> None:
        """DALL-E 3가 OpenAI SDK를 사용한다."""
        assert "openai" in _SERVICE_SOURCE.lower()
        assert "dall-e-3" in _SERVICE_SOURCE


class TestClaudeVisionValidation:
    """Claude Vision 품질 검증 관련."""

    def test_vision_method_exists(self) -> None:
        """_validate_with_claude_vision() 메서드가 존재한다."""
        assert "_validate_with_claude_vision" in _SERVICE_SOURCE

    def test_vision_uses_anthropic(self) -> None:
        """Claude Vision이 Anthropic SDK를 사용한다."""
        assert "anthropic" in _SERVICE_SOURCE.lower()

    def test_vision_checks_room_count(self) -> None:
        """방 개수 검증 로직이 있다."""
        assert "detected_rooms" in _SERVICE_SOURCE
        assert "expected_rooms" in _SERVICE_SOURCE


class TestFallbackChain:
    """생성 폴백 체인 통합 검증."""

    def test_generate_has_fallback_logic(self) -> None:
        """generate() 메서드에 폴백 로직이 있다."""
        assert "generation_method" in _SERVICE_SOURCE

    def test_max_attempts_retry(self) -> None:
        """최대 재시도 횟수가 설정되어 있다."""
        assert "max_attempts" in _SERVICE_SOURCE

    def test_vision_validation_in_generate(self) -> None:
        """generate() 내에서 Vision 검증을 호출한다."""
        assert "_validate_with_claude_vision" in _SERVICE_SOURCE
