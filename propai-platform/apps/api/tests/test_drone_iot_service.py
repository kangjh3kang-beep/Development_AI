"""DroneIoTService 단위 테스트.

하자 심각도 분류, 알림 이벤트 생성 등 순수 로직을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.drone_iot_service import DroneIoTService


class TestClassifySeverity:
    """_classify_severity 메서드 테스트."""

    def _make_svc(self) -> DroneIoTService:
        svc = object.__new__(DroneIoTService)
        return svc

    def test_구조균열_고신뢰_EMERGENCY(self):
        svc = self._make_svc()
        assert svc._classify_severity("structural_crack", 0.9) == "EMERGENCY"

    def test_구조균열_저신뢰_HIGH(self):
        """critical 유형이지만 신뢰도 < 0.7이면 EMERGENCY가 아님."""
        svc = self._make_svc()
        result = svc._classify_severity("structural_crack", 0.5)
        assert result != "EMERGENCY"

    def test_누수_HIGH(self):
        svc = self._make_svc()
        assert svc._classify_severity("water_leak", 0.5) == "HIGH"

    def test_일반_하자_고신뢰_HIGH(self):
        svc = self._make_svc()
        assert svc._classify_severity("surface_stain", 0.90) == "HIGH"

    def test_일반_하자_중신뢰_MEDIUM(self):
        svc = self._make_svc()
        assert svc._classify_severity("surface_stain", 0.70) == "MEDIUM"

    def test_일반_하자_저신뢰_LOW(self):
        svc = self._make_svc()
        assert svc._classify_severity("surface_stain", 0.40) == "LOW"

    def test_붕괴위험_EMERGENCY(self):
        svc = self._make_svc()
        assert svc._classify_severity("collapse_risk", 0.75) == "EMERGENCY"

    def test_철근노출_HIGH(self):
        svc = self._make_svc()
        assert svc._classify_severity("reinforcement_exposure", 0.5) == "HIGH"


class TestCreateAlertEvents:
    """create_alert_events 메서드 테스트."""

    def _make_svc(self) -> DroneIoTService:
        svc = object.__new__(DroneIoTService)
        return svc

    def test_EMERGENCY_하자_알림_생성(self):
        svc = self._make_svc()
        defects = [
            {"severity": "EMERGENCY", "defect_type": "structural_crack", "bbox": {}, "image_url": "test.jpg"},
        ]
        alerts = svc.create_alert_events("insp-001", defects)
        assert len(alerts) == 1
        assert alerts[0].severity == "EMERGENCY"

    def test_HIGH_하자_알림_생성(self):
        svc = self._make_svc()
        defects = [
            {"severity": "HIGH", "defect_type": "water_leak", "bbox": {}, "image_url": "test.jpg"},
        ]
        alerts = svc.create_alert_events("insp-001", defects)
        assert len(alerts) == 1

    def test_LOW_MEDIUM_하자_알림_미생성(self):
        svc = self._make_svc()
        defects = [
            {"severity": "LOW", "defect_type": "stain", "bbox": {}},
            {"severity": "MEDIUM", "defect_type": "crack", "bbox": {}},
        ]
        alerts = svc.create_alert_events("insp-001", defects)
        assert len(alerts) == 0

    def test_빈_하자_리스트(self):
        svc = self._make_svc()
        alerts = svc.create_alert_events("insp-001", [])
        assert len(alerts) == 0

    def test_혼합_심각도_필터링(self):
        svc = self._make_svc()
        defects = [
            {"severity": "EMERGENCY", "defect_type": "a", "bbox": {}, "image_url": "1.jpg"},
            {"severity": "LOW", "defect_type": "b", "bbox": {}},
            {"severity": "HIGH", "defect_type": "c", "bbox": {}, "image_url": "2.jpg"},
            {"severity": "MEDIUM", "defect_type": "d", "bbox": {}},
        ]
        alerts = svc.create_alert_events("insp-001", defects)
        assert len(alerts) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
