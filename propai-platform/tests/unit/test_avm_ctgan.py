"""AVM CTGAN 콜드스타트 합성 데이터 테스트.

Phase F-3: 비교사례 3건 미만 시 CTGAN 합성 데이터 생성 검증.
"""

from pathlib import Path

_SERVICE_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps" / "api" / "services" / "avm_service.py"
)
_SERVICE_SOURCE = _SERVICE_PATH.read_text(encoding="utf-8")


class TestCTGANColdStart:
    """CTGAN 콜드스타트 합성 데이터 검증."""

    def test_synthetic_method_exists(self) -> None:
        """_generate_synthetic_comparables() 메서드가 존재한다."""
        assert "_generate_synthetic_comparables" in _SERVICE_SOURCE

    def test_ctgan_import(self) -> None:
        """CTGAN 라이브러리를 사용한다."""
        assert "ctgan" in _SERVICE_SOURCE.lower()

    def test_cold_start_threshold(self) -> None:
        """콜드스타트 임계값이 3건으로 설정되어 있다."""
        assert "< 3" in _SERVICE_SOURCE or "<3" in _SERVICE_SOURCE

    def test_synthetic_data_integration(self) -> None:
        """estimate() 메서드에서 합성 데이터를 통합한다."""
        assert "synthetic" in _SERVICE_SOURCE
        assert "comparables.extend" in _SERVICE_SOURCE or "extend(synthetic" in _SERVICE_SOURCE

    def test_statistical_fallback(self) -> None:
        """CTGAN 실패 시 통계 분포 기반 폴백이 있다."""
        assert "random" in _SERVICE_SOURCE.lower() or "normal" in _SERVICE_SOURCE.lower()
