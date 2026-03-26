"""v2 API 라우터 등록 확인 테스트.

Phase F-5: v2 라우터 스텁 (auth, projects, design) 검증.
"""

from pathlib import Path

_MAIN_PATH = Path(__file__).resolve().parents[2] / "apps" / "api" / "main.py"
_MAIN_SOURCE = _MAIN_PATH.read_text(encoding="utf-8")

_V2_DIR = Path(__file__).resolve().parents[2] / "apps" / "api" / "routers" / "v2"


class TestV2RouterRegistration:
    """v2 라우터가 main.py에 등록되어 있는지 검증."""

    def test_v2_auth_registered(self) -> None:
        """v2 auth 라우터가 등록되어 있다."""
        assert "/api/v2/auth" in _MAIN_SOURCE

    def test_v2_projects_registered(self) -> None:
        """v2 projects 라우터가 등록되어 있다."""
        assert "/api/v2/projects" in _MAIN_SOURCE

    def test_v2_design_registered(self) -> None:
        """v2 design 라우터가 등록되어 있다."""
        assert "/api/v2/design" in _MAIN_SOURCE


class TestV2RouterFiles:
    """v2 라우터 파일 존재 검증."""

    def test_v2_init_exists(self) -> None:
        """v2/__init__.py 파일이 존재한다."""
        assert (_V2_DIR / "__init__.py").exists()

    def test_v2_auth_file_exists(self) -> None:
        """v2/auth.py 파일이 존재한다."""
        assert (_V2_DIR / "auth.py").exists()

    def test_v2_projects_file_exists(self) -> None:
        """v2/projects.py 파일이 존재한다."""
        assert (_V2_DIR / "projects.py").exists()

    def test_v2_design_file_exists(self) -> None:
        """v2/design.py 파일이 존재한다."""
        assert (_V2_DIR / "design.py").exists()
