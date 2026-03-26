"""설정 정규화 단위 테스트.

환경 변수에서 들어오는 문자열 기반 DEBUG 값이 Settings 초기화를
깨뜨리지 않도록 보장한다.
"""

from apps.api.config import Settings


def _base_settings(**kwargs: object) -> Settings:
    """테스트용 최소 설정."""
    return Settings(
        database_url="postgresql+asyncpg://x:x@localhost/test",
        redis_url="redis://localhost:6379/0",
        _env_file=None,
        **kwargs,
    )


class TestDebugNormalization:
    """DEBUG 값 정규화 검증."""

    def test_release_string_maps_to_false(self, monkeypatch) -> None:
        monkeypatch.setenv("DEBUG", "release")
        settings = _base_settings()
        assert settings.debug is False

    def test_development_string_maps_to_true(self, monkeypatch) -> None:
        monkeypatch.setenv("DEBUG", "development")
        settings = _base_settings()
        assert settings.debug is True

    def test_explicit_bool_like_init_value_is_supported(self) -> None:
        settings = _base_settings(debug="false")
        assert settings.debug is False

    def test_explicit_init_value_overrides_environment(self, monkeypatch) -> None:
        monkeypatch.setenv("DEBUG", "release")
        settings = _base_settings(debug=True)
        assert settings.debug is True
