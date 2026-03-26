"""Dockerfile 보안 및 구조 테스트.

Phase F-7: API 서비스 Dockerfile non-root + 보안 강화 검증.
"""

from pathlib import Path

_DOCKERFILE_PATH = (
    Path(__file__).resolve().parents[2] / "apps" / "api" / "Dockerfile"
)
_DOCKERFILE_SOURCE = _DOCKERFILE_PATH.read_text(encoding="utf-8")


class TestDockerfileStructure:
    """Dockerfile 구조 검증."""

    def test_dockerfile_exists(self) -> None:
        """apps/api/Dockerfile 파일이 존재한다."""
        assert _DOCKERFILE_PATH.exists()

    def test_python312_base(self) -> None:
        """Python 3.12-slim 기반 이미지를 사용한다."""
        assert "python:3.12-slim" in _DOCKERFILE_SOURCE

    def test_non_root_user(self) -> None:
        """non-root 사용자 (propai)로 실행한다."""
        assert "propai" in _DOCKERFILE_SOURCE
        assert "USER propai" in _DOCKERFILE_SOURCE

    def test_uid_1001(self) -> None:
        """UID 1001로 설정한다."""
        assert "1001" in _DOCKERFILE_SOURCE

    def test_expose_8000(self) -> None:
        """포트 8000을 노출한다."""
        assert "EXPOSE 8000" in _DOCKERFILE_SOURCE

    def test_healthcheck(self) -> None:
        """HEALTHCHECK가 설정되어 있다."""
        assert "HEALTHCHECK" in _DOCKERFILE_SOURCE

    def test_uvicorn_cmd(self) -> None:
        """uvicorn으로 실행한다."""
        assert "uvicorn" in _DOCKERFILE_SOURCE
