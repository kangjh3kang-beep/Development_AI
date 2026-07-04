"""디지털 트윈 + 탄소 산출 확장 테스트 (Phase 16 강화).

parse_ifc_metadata, ingest_sensor_reading, calculate_operational_carbon,
calculate_realtime_carbon 테스트.
"""

import os
import sys
from datetime import UTC, datetime

UTC = UTC
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.carbon_calculation_service import CarbonCalculationService
from apps.api.services.digital_twin_service import DigitalTwinService

# ── parse_ifc_metadata 테스트 ──


class TestParseIfcMetadata:
    """IFC 메타데이터 파싱 테스트."""

    def test_full_metadata(self):
        """전체 메타데이터 파싱."""
        ifc_data = {
            "name": "PropAI Tower",
            "site_area_sqm": 2000,
            "gross_floor_area_sqm": 15000,
            "num_floors": 20,
            "materials": ["콘크리트", "철근", "유리"],
            "building_height_m": 70.0,
        }
        result = DigitalTwinService.parse_ifc_metadata(ifc_data)
        assert result["building_name"] == "PropAI Tower"
        assert result["site_area"] == 2000
        assert result["gross_area"] == 15000
        assert result["num_floors"] == 20
        assert len(result["materials"]) == 3
        assert result["height"] == 70.0

    def test_empty_dict(self):
        """빈 dict → 기본값 반환."""
        result = DigitalTwinService.parse_ifc_metadata({})
        assert result["building_name"] == "Unknown"
        assert result["site_area"] == 0
        assert result["gross_area"] == 0
        assert result["num_floors"] == 0
        assert result["materials"] == []
        assert result["height"] == 0

    def test_partial_metadata(self):
        """일부 필드만 존재."""
        result = DigitalTwinService.parse_ifc_metadata({"name": "Test", "num_floors": 5})
        assert result["building_name"] == "Test"
        assert result["num_floors"] == 5
        assert result["height"] == 0


# ── ingest_sensor_reading 테스트 ──


class TestIngestSensorReading:
    """센서 데이터 수집 테스트."""

    def _make_svc(self):
        svc = object.__new__(DigitalTwinService)
        svc.db = AsyncMock()
        svc.settings = MagicMock()
        return svc

    @pytest.mark.asyncio
    async def test_ingest_temperature(self):
        """온도 센서 데이터 수집."""
        svc = self._make_svc()
        result = await svc.ingest_sensor_reading(
            tenant_id=uuid4(),
            project_id=uuid4(),
            sensor_type="temperature",
            value=23.5,
        )
        assert result["sensor_type"] == "temperature"
        assert result["value"] == 23.5
        assert result["stored"] is True
        svc.db.add.assert_called_once()
        svc.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_with_timestamp(self):
        """타임스탬프 지정."""
        svc = self._make_svc()
        ts = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = await svc.ingest_sensor_reading(
            tenant_id=uuid4(),
            project_id=uuid4(),
            sensor_type="humidity",
            value=65.0,
            timestamp=ts,
        )
        assert result["timestamp"] == ts.isoformat()


# ── calculate_operational_carbon 테스트 ──


class TestCalculateOperationalCarbon:
    """운영 탄소 배출량 산출 테스트."""

    def test_monthly_calculation(self):
        """월별 탄소 배출량 산출."""
        readings = [
            {"month": "2026-01", "kwh": 10000},
            {"month": "2026-02", "kwh": 9000},
            {"month": "2026-03", "kwh": 8000},
        ]
        result = DigitalTwinService.calculate_operational_carbon(readings)
        assert result["total_carbon_kg"] == pytest.approx(
            (10000 + 9000 + 8000) * 0.4629, abs=1.0
        )
        assert len(result["monthly"]) == 3
        assert result["monthly"][0]["carbon_kg"] == pytest.approx(10000 * 0.4629, abs=0.01)

    def test_trend_stable(self):
        """6개월 미만 → stable."""
        readings = [
            {"month": "2026-01", "kwh": 10000},
            {"month": "2026-02", "kwh": 10000},
        ]
        result = DigitalTwinService.calculate_operational_carbon(readings)
        assert result["trend"] == "stable"

    def test_trend_increasing(self):
        """최근 3개월이 이전 3개월보다 5% 이상 증가 → increasing."""
        readings = [
            {"month": "2026-01", "kwh": 10000},
            {"month": "2026-02", "kwh": 10000},
            {"month": "2026-03", "kwh": 10000},
            {"month": "2026-04", "kwh": 12000},
            {"month": "2026-05", "kwh": 12000},
            {"month": "2026-06", "kwh": 12000},
        ]
        result = DigitalTwinService.calculate_operational_carbon(readings)
        assert result["trend"] == "increasing"

    def test_trend_decreasing(self):
        """최근 3개월이 이전 3개월보다 5% 이상 감소 → decreasing."""
        readings = [
            {"month": "2026-01", "kwh": 12000},
            {"month": "2026-02", "kwh": 12000},
            {"month": "2026-03", "kwh": 12000},
            {"month": "2026-04", "kwh": 8000},
            {"month": "2026-05", "kwh": 8000},
            {"month": "2026-06", "kwh": 8000},
        ]
        result = DigitalTwinService.calculate_operational_carbon(readings)
        assert result["trend"] == "decreasing"

    def test_custom_grid_ef(self):
        """커스텀 전력배출계수."""
        readings = [{"month": "2026-01", "kwh": 1000}]
        result = DigitalTwinService.calculate_operational_carbon(readings, grid_ef=0.5)
        assert result["total_carbon_kg"] == pytest.approx(500.0, abs=0.01)


# ── calculate_realtime_carbon 테스트 ──


class TestCalculateRealtimeCarbon:
    """실시간 탄소 배출량 산출 테스트."""

    def test_basic(self):
        """기본 산출."""
        result = CarbonCalculationService.calculate_realtime_carbon([1000.0, 2000.0, 3000.0])
        expected_total = (1000 + 2000 + 3000) * 0.4629
        assert result["total_carbon_kg"] == pytest.approx(expected_total, abs=0.01)
        assert result["avg_carbon_per_reading_kg"] == pytest.approx(expected_total / 3, abs=0.01)
        assert result["grid_ef"] == 0.4629

    def test_empty_list(self):
        """빈 리스트 → 0."""
        result = CarbonCalculationService.calculate_realtime_carbon([])
        assert result["total_carbon_kg"] == 0.0
        assert result["avg_carbon_per_reading_kg"] == 0.0

    def test_custom_grid_ef(self):
        """커스텀 전력배출계수."""
        result = CarbonCalculationService.calculate_realtime_carbon([1000.0], grid_ef=1.0)
        assert result["total_carbon_kg"] == pytest.approx(1000.0, abs=0.01)
        assert result["grid_ef"] == 1.0
