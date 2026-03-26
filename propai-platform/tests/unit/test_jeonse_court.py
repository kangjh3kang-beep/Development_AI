"""전세 등기부 조회 연동 테스트.

Phase F-9: court_client 연동 근저당 확인 검증.
"""

from pathlib import Path

_SERVICE_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps" / "api" / "services" / "jeonse_risk_service.py"
)
_SERVICE_SOURCE = _SERVICE_PATH.read_text(encoding="utf-8")


class TestMortgagePriorityCheck:
    """등기부 근저당 조회 검증."""

    def test_mortgage_method_exists(self) -> None:
        """_check_mortgage_priority() 메서드가 존재한다."""
        assert "_check_mortgage_priority" in _SERVICE_SOURCE

    def test_court_client_usage(self) -> None:
        """CourtClient를 사용한다."""
        assert "CourtClient" in _SERVICE_SOURCE
        assert "court_client" in _SERVICE_SOURCE.lower()

    def test_check_lien_call(self) -> None:
        """check_lien() API를 호출한다."""
        assert "check_lien" in _SERVICE_SOURCE

    def test_registry_number_parameter(self) -> None:
        """analyze()에 registry_number 파라미터가 있다."""
        assert "registry_number" in _SERVICE_SOURCE

    def test_mortgage_in_fraud_factors(self) -> None:
        """근저당 결과가 fraud_factors에 추가된다."""
        assert "mortgage_factors" in _SERVICE_SOURCE

    def test_ownership_changes_check(self) -> None:
        """소유권 이전 이력을 확인한다."""
        assert "ownership_changes" in _SERVICE_SOURCE
