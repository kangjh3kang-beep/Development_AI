"""드론 IoT 하자 탐지 서비스 단위 테스트.

순수 로직 검증:
1. _classify_severity() — 하자 유형 + 신뢰도 → 심각도 분류
2. create_alert_events() — EMERGENCY/HIGH 하자만 알림 생성
"""

from unittest.mock import AsyncMock

from apps.api.services.drone_iot_service import DroneIoTService


def _make_service() -> DroneIoTService:
    """Mock DB 세션으로 서비스 생성."""
    return DroneIoTService(AsyncMock())


# ──────────────────────────────────────
# _classify_severity 검증
# ──────────────────────────────────────


class TestClassifySeverity:
    """하자 유형 + 신뢰도 기반 심각도 분류 검증."""

    def test_structural_crack_high_confidence_emergency(self) -> None:
        """구조 균열 + 신뢰도 0.9 → EMERGENCY."""
        svc = _make_service()
        assert svc._classify_severity("structural_crack", 0.9) == "EMERGENCY"

    def test_collapse_risk_high_confidence_emergency(self) -> None:
        """붕괴 위험 + 신뢰도 0.7 → EMERGENCY."""
        svc = _make_service()
        assert svc._classify_severity("collapse_risk", 0.7) == "EMERGENCY"

    def test_foundation_damage_high_confidence_emergency(self) -> None:
        """기초 손상 + 신뢰도 0.75 → EMERGENCY."""
        svc = _make_service()
        assert svc._classify_severity("foundation_damage", 0.75) == "EMERGENCY"

    def test_structural_crack_low_confidence_not_emergency(self) -> None:
        """구조 균열이라도 신뢰도 0.5 미만이면 EMERGENCY 아님."""
        svc = _make_service()
        result = svc._classify_severity("structural_crack", 0.5)
        assert result != "EMERGENCY"

    def test_water_leak_returns_high(self) -> None:
        """누수 → HIGH."""
        svc = _make_service()
        assert svc._classify_severity("water_leak", 0.5) == "HIGH"

    def test_reinforcement_exposure_returns_high(self) -> None:
        """철근 노출 → HIGH."""
        svc = _make_service()
        assert svc._classify_severity("reinforcement_exposure", 0.5) == "HIGH"

    def test_concrete_spalling_returns_high(self) -> None:
        """콘크리트 박리 → HIGH."""
        svc = _make_service()
        assert svc._classify_severity("concrete_spalling", 0.5) == "HIGH"

    def test_unknown_type_very_high_conf_returns_high(self) -> None:
        """미정의 유형 + 신뢰도 0.90 → HIGH."""
        svc = _make_service()
        assert svc._classify_severity("unknown", 0.90) == "HIGH"

    def test_medium_confidence_returns_medium(self) -> None:
        """일반 유형 + 신뢰도 0.65 → MEDIUM."""
        svc = _make_service()
        assert svc._classify_severity("generic_defect", 0.65) == "MEDIUM"

    def test_low_confidence_returns_low(self) -> None:
        """신뢰도 0.3 → LOW."""
        svc = _make_service()
        assert svc._classify_severity("generic_defect", 0.3) == "LOW"

    def test_boundary_confidence_060(self) -> None:
        """경계값 0.60 → MEDIUM."""
        svc = _make_service()
        assert svc._classify_severity("generic_defect", 0.60) == "MEDIUM"

    def test_boundary_confidence_059(self) -> None:
        """경계값 0.59 → LOW."""
        svc = _make_service()
        assert svc._classify_severity("generic_defect", 0.59) == "LOW"


# ──────────────────────────────────────
# create_alert_events 검증
# ──────────────────────────────────────


class TestCreateAlertEvents:
    """EMERGENCY/HIGH 하자만 알림 이벤트 생성 검증."""

    def test_emergency_generates_alert(self) -> None:
        """EMERGENCY 하자 → 알림 생성."""
        svc = _make_service()
        defects = [
            {"severity": "EMERGENCY", "defect_type": "structural_crack",
             "bbox": {"x": 10, "y": 20}, "image_url": "https://example.com/img.jpg"},
        ]
        alerts = svc.create_alert_events("insp-001", defects)
        assert len(alerts) == 1
        assert alerts[0].severity == "EMERGENCY"

    def test_high_generates_alert(self) -> None:
        """HIGH 하자 → 알림 생성."""
        svc = _make_service()
        defects = [
            {"severity": "HIGH", "defect_type": "water_leak",
             "bbox": {}, "image_url": "https://example.com/img.jpg"},
        ]
        alerts = svc.create_alert_events("insp-002", defects)
        assert len(alerts) == 1
        assert alerts[0].severity == "HIGH"

    def test_medium_no_alert(self) -> None:
        """MEDIUM 하자 → 알림 미생성."""
        svc = _make_service()
        defects = [{"severity": "MEDIUM", "defect_type": "minor_crack"}]
        alerts = svc.create_alert_events("insp-003", defects)
        assert len(alerts) == 0

    def test_low_no_alert(self) -> None:
        """LOW 하자 → 알림 미생성."""
        svc = _make_service()
        defects = [{"severity": "LOW", "defect_type": "surface_stain"}]
        alerts = svc.create_alert_events("insp-004", defects)
        assert len(alerts) == 0

    def test_mixed_severities(self) -> None:
        """혼합 심각도 → EMERGENCY/HIGH만 알림."""
        svc = _make_service()
        defects = [
            {"severity": "EMERGENCY", "defect_type": "structural_crack",
             "bbox": {}, "image_url": "img1.jpg"},
            {"severity": "MEDIUM", "defect_type": "minor_crack"},
            {"severity": "HIGH", "defect_type": "water_leak",
             "bbox": {}, "image_url": "img2.jpg"},
            {"severity": "LOW", "defect_type": "stain"},
        ]
        alerts = svc.create_alert_events("insp-005", defects)
        assert len(alerts) == 2

    def test_empty_defects(self) -> None:
        """빈 하자 목록 → 빈 결과."""
        svc = _make_service()
        alerts = svc.create_alert_events("insp-006", [])
        assert len(alerts) == 0

    def test_alert_inspection_id(self) -> None:
        """알림 이벤트에 inspection_id가 포함된다."""
        svc = _make_service()
        defects = [
            {"severity": "EMERGENCY", "defect_type": "collapse_risk",
             "bbox": {}, "image_url": "img.jpg"},
        ]
        alerts = svc.create_alert_events("my-inspection", defects)
        assert alerts[0].inspection_id == "my-inspection"
