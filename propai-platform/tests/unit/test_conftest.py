"""conftest.py 구조 단위 테스트.

테스트 인프라 설정이 올바르게 구성되어 있는지 검증.
"""

from pathlib import Path

_CONFTEST_PATH = Path(__file__).resolve().parents[1] / "conftest.py"
_CONFTEST_SOURCE = _CONFTEST_PATH.read_text(encoding="utf-8")


class TestConftestExists:
    """conftest.py 파일 존재 및 구조 검증."""

    def test_conftest_file_exists(self) -> None:
        """tests/conftest.py 파일이 존재한다."""
        assert _CONFTEST_PATH.exists()

    def test_markers_registered(self) -> None:
        """unit/integration 마커가 등록되어 있다."""
        assert "unit" in _CONFTEST_SOURCE
        assert "integration" in _CONFTEST_SOURCE

    def test_sample_tenant_fixture(self) -> None:
        """sample_tenant_id fixture가 정의되어 있다."""
        assert "sample_tenant_id" in _CONFTEST_SOURCE

    def test_sample_project_fixture(self) -> None:
        """sample_project_id fixture가 정의되어 있다."""
        assert "sample_project_id" in _CONFTEST_SOURCE

    def test_anyio_backend(self) -> None:
        """anyio_backend fixture가 정의되어 있다."""
        assert "anyio_backend" in _CONFTEST_SOURCE
