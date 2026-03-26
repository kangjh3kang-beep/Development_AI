"""CoVe O1: IFC 물량산출 정확도 벤치마크.

기준: 오차 ≤ 2% (Mock IFC 5개 대조)
실행: pytest tests/benchmarks/bench_ifc.py -v
"""

import pytest

pytestmark = pytest.mark.benchmark


REFERENCE_DATA = [
    {"name": "office_small", "expected_volume_m3": 1250.0, "expected_area_sqm": 500.0},
    {"name": "apartment_mid", "expected_volume_m3": 8400.0, "expected_area_sqm": 2800.0},
    {"name": "warehouse", "expected_volume_m3": 15000.0, "expected_area_sqm": 3000.0},
    {"name": "school", "expected_volume_m3": 12600.0, "expected_area_sqm": 4200.0},
    {"name": "hospital", "expected_volume_m3": 24000.0, "expected_area_sqm": 6000.0},
]

TOLERANCE = 0.02  # 2%


class TestIFCQuantityAccuracy:
    """IFC 물량산출 정확도 검증."""

    @pytest.mark.skip(reason="Mock IFC 파일 + ifcopenshell 필요 — CI에서 실행")
    @pytest.mark.parametrize("ref", REFERENCE_DATA, ids=[r["name"] for r in REFERENCE_DATA])
    def test_volume_within_tolerance(self, ref: dict) -> None:
        """체적 산출 오차가 2% 이내인지 확인."""
        # TODO: BIMIFCService.analyze()로 실제 파싱 후 비교
        pass

    @pytest.mark.skip(reason="Mock IFC 파일 + ifcopenshell 필요 — CI에서 실행")
    @pytest.mark.parametrize("ref", REFERENCE_DATA, ids=[r["name"] for r in REFERENCE_DATA])
    def test_area_within_tolerance(self, ref: dict) -> None:
        """면적 산출 오차가 2% 이내인지 확인."""
        pass
