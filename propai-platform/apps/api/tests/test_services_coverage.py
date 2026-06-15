"""서비스 계층 대규모 커버리지 보강 테스트.

저커버리지 서비스의 순수 메서드, static 메서드, 초기화 코드를
집중적으로 테스트하여 80% 커버리지 달성을 목표로 한다.
"""

import os
import re
import sys
from datetime import datetime, timedelta, timezone, UTC
UTC = UTC
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import UUID, uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ── TenantExperienceService ──


class TestTenantExperienceSentiment:
    """_analyze_sentiment static 메서드 테스트."""

    def test_긍정_피드백(self):
        from apps.api.services.tenant_experience_service import TenantExperienceService

        score, label, reply = TenantExperienceService._analyze_sentiment(
            "The service was great and the staff was very helpful", 5,
        )
        assert label == "positive"
        assert score > 0.3
        assert "preserve" in reply.lower() or "thank" in reply.lower()

    def test_부정_피드백(self):
        from apps.api.services.tenant_experience_service import TenantExperienceService

        score, label, reply = TenantExperienceService._analyze_sentiment(
            "There is a leak and broken pipe, noise is unbearable, I feel unsafe and angry", 1,
        )
        assert label == "negative"
        assert score < -0.3
        assert "logged" in reply.lower() or "follow" in reply.lower()

    def test_중립_피드백(self):
        from apps.api.services.tenant_experience_service import TenantExperienceService

        score, label, reply = TenantExperienceService._analyze_sentiment("Everything is okay", 3)
        assert label == "neutral"
        assert -0.3 <= score <= 0.3

    def test_점수_범위_바운딩(self):
        from apps.api.services.tenant_experience_service import TenantExperienceService

        score, _, _ = TenantExperienceService._analyze_sentiment(
            "great helpful quick clean comfortable resolved great helpful", 5,
        )
        assert -1.0 <= score <= 1.0


class TestTenantExperienceHealth:
    """_calculate_health static 메서드 테스트."""

    def test_등급_A(self):
        from apps.api.services.tenant_experience_service import TenantExperienceService

        nps, churn, grade = TenantExperienceService._calculate_health(
            promoter_count=80, passive_count=10, detractor_count=10,
            occupancy_rate=0.98, arrears_ratio=0.01,
        )
        assert grade == "A"
        assert nps > 50

    def test_등급_B(self):
        from apps.api.services.tenant_experience_service import TenantExperienceService

        nps, churn, grade = TenantExperienceService._calculate_health(
            promoter_count=50, passive_count=30, detractor_count=20,
            occupancy_rate=0.85, arrears_ratio=0.05,
        )
        assert grade in {"A", "B"}

    def test_등급_하위(self):
        from apps.api.services.tenant_experience_service import TenantExperienceService

        nps, churn, grade = TenantExperienceService._calculate_health(
            promoter_count=5, passive_count=10, detractor_count=85,
            occupancy_rate=0.40, arrears_ratio=0.30,
        )
        assert grade in {"D", "E"}
        assert churn > 0.3

    def test_총계_제로(self):
        from apps.api.services.tenant_experience_service import TenantExperienceService

        nps, churn, grade = TenantExperienceService._calculate_health(
            promoter_count=0, passive_count=0, detractor_count=0,
            occupancy_rate=0.50, arrears_ratio=0.50,
        )
        assert nps == 0.0


# ── CarbonCalculationService ──


class TestCarbonCalculation:
    def test_내재_탄소_계산(self):
        from apps.api.services.carbon_calculation_service import CarbonCalculationService

        svc = CarbonCalculationService(db=AsyncMock())
        materials = [
            {"type": "IfcWall", "volume_m3": 100},
            {"type": "IfcSlab", "volume_m3": 200},
            {"type": "IfcWindow", "area_sqm": 50},
        ]
        total, breakdown = svc._calculate_embodied_carbon(materials)
        assert total > 0
        assert len(breakdown) == 3
        # IfcWall: 100 * 120 = 12000
        assert breakdown[0]["carbon_kgco2e"] == 12000.0

    def test_내재_탄소_미지원_자재(self):
        from apps.api.services.carbon_calculation_service import CarbonCalculationService

        svc = CarbonCalculationService(db=AsyncMock())
        materials = [{"type": "UnknownElement", "volume_m3": 50}]
        total, breakdown = svc._calculate_embodied_carbon(materials)
        assert total == 0.0
        assert len(breakdown) == 0

    def test_운영_탄소_추정(self):
        from apps.api.services.carbon_calculation_service import CarbonCalculationService

        svc = CarbonCalculationService(db=AsyncMock())
        result = svc._estimate_operational_carbon(1000.0, lifespan_years=60)
        # 1000 * 120 * 0.46 * 60 = 3,312,000
        assert result == pytest.approx(3_312_000.0)

    def test_결과_클래스(self):
        from apps.api.services.carbon_calculation_service import CarbonCalculationResult

        r = CarbonCalculationResult(
            total_embodied_carbon=1000.0,
            total_operational_carbon=2000.0,
            breakdown=[],
            reduction_tips=["tip1"],
        )
        assert r.total_carbon == 3000.0


# ── InvestorReportService ──


class TestInvestorReport:
    def test_compose_source_text_기본(self):
        from apps.api.services.investor_report_service import InvestorReportService

        text = InvestorReportService._compose_source_text(
            project_name="테스트 프로젝트",
            asset_type="아파트",
            include_sections=["executive-summary"],
            investment_highlights=["high demand"],
            risks=["interest rate"],
            underwriting=None,
            esg_report=None,
            climate_report=None,
            asset_snapshot=None,
        )
        assert "테스트 프로젝트" in text
        assert "high demand" in text
        assert "interest rate" in text

    def test_compose_source_text_전체_섹션(self):
        from apps.api.services.investor_report_service import InvestorReportService

        mock_uw = MagicMock()
        mock_uw.recommendation = "proceed"
        mock_uw.profit_margin_ratio = 0.15
        mock_uw.risk_level = "low"

        mock_esg = MagicMock()
        mock_esg.environmental_score = 85
        mock_esg.social_score = 80
        mock_esg.governance_score = 90

        mock_climate = MagicMock()
        mock_climate.flood_risk_score = 0.12
        mock_climate.heat_risk_score = 0.08
        mock_climate.annual_expected_loss_krw = 50_000_000

        mock_asset = MagicMock()
        mock_asset.composite_score = 92
        mock_asset.grade = "A"
        mock_asset.adjusted_value_krw = 1_000_000_000

        text = InvestorReportService._compose_source_text(
            project_name="P", asset_type="office",
            include_sections=["executive-summary", "financials", "esg", "risks", "market"],
            investment_highlights=[], risks=["macro"],
            underwriting=mock_uw, esg_report=mock_esg,
            climate_report=mock_climate, asset_snapshot=mock_asset,
        )
        assert "proceed" in text
        assert "ESG" in text
        assert "Climate" in text
        assert "Asset intelligence" in text

    def test_translate(self):
        from apps.api.services.investor_report_service import InvestorReportService

        title, translated, quality = InvestorReportService._translate("Test", "ko", "src text")
        assert "KO" in translated
        assert quality == 0.93

        title_ja, _, quality_ja = InvestorReportService._translate("T", "ja", "src")
        assert quality_ja == 0.88


# ── EnergyService ──


class TestEnergyGrade:
    def test_등급_A_plus(self):
        from apps.api.services.energy_service import EnergyService

        assert EnergyService.energy_grade(50) == "A+"

    def test_등급_A(self):
        from apps.api.services.energy_service import EnergyService

        assert EnergyService.energy_grade(80) == "A"

    def test_등급_B(self):
        from apps.api.services.energy_service import EnergyService

        assert EnergyService.energy_grade(120) == "B"

    def test_등급_C(self):
        from apps.api.services.energy_service import EnergyService

        assert EnergyService.energy_grade(160) == "C"

    def test_등급_D(self):
        from apps.api.services.energy_service import EnergyService

        assert EnergyService.energy_grade(200) == "D"


# ── DomainAgentsService ──


class TestDomainAgentsScore:
    def test_기본_점수(self):
        from apps.api.services.domain_agents_service import DomainAgentsService

        score, rec, findings = DomainAgentsService._score("analyze asset", {})
        assert 0.35 <= score <= 0.95
        assert rec in {"proceed", "proceed-with-conditions", "escalate"}

    def test_리스크_질문(self):
        from apps.api.services.domain_agents_service import DomainAgentsService

        score, rec, findings = DomainAgentsService._score(
            "what is the risk and downside?",
            {"occupancy_rate": 0.5, "ltv": 0.8},
        )
        assert score < 0.7  # risk 감점
        assert any(f["factor"] == "risk-focus" for f in findings)
        assert any(f["factor"] == "ltv" for f in findings)

    def test_긍정_컨텍스트(self):
        from apps.api.services.domain_agents_service import DomainAgentsService

        score, rec, findings = DomainAgentsService._score(
            "proceed with development",
            {"occupancy_rate": 0.95, "schedule_buffer_months": 6, "pre_leasing_ratio": 0.7},
        )
        assert score >= 0.8
        assert rec == "proceed"


# ── KDXIntegrationService ──


class TestKDXStaticMethods:
    def test_connection_status_idle(self):
        from apps.api.services.kdx_integration_service import KDXIntegrationService

        assert KDXIntegrationService._connection_status(latest_seen_at=None) == "idle"

    def test_connection_status_stable(self):
        from apps.api.services.kdx_integration_service import KDXIntegrationService

        recent = datetime.now(UTC) - timedelta(seconds=60)
        assert KDXIntegrationService._connection_status(latest_seen_at=recent) == "stable"

    def test_connection_status_degraded(self):
        from apps.api.services.kdx_integration_service import KDXIntegrationService

        old = datetime.now(UTC) - timedelta(seconds=600)
        assert KDXIntegrationService._connection_status(latest_seen_at=old) == "degraded"

    def test_connection_status_stale(self):
        from apps.api.services.kdx_integration_service import KDXIntegrationService

        very_old = datetime.now(UTC) - timedelta(seconds=3600)
        assert KDXIntegrationService._connection_status(latest_seen_at=very_old) == "stale"

    def test_throughput_tps(self):
        from apps.api.services.kdx_integration_service import KDXIntegrationService

        assert KDXIntegrationService._throughput_tps(recent_log_count=10, recent_metric_count=5) == 80

    def test_latency_ms_none(self):
        from apps.api.services.kdx_integration_service import KDXIntegrationService

        assert KDXIntegrationService._latency_ms(latest_seen_at=None) == 0

    def test_latency_ms_최근(self):
        from apps.api.services.kdx_integration_service import KDXIntegrationService

        recent = datetime.now(UTC) - timedelta(seconds=1)
        ms = KDXIntegrationService._latency_ms(latest_seen_at=recent)
        assert ms >= 900  # 약 1000ms


# ── UnionManagementService ──


class TestUnionManagement:
    def test_비례율_계산(self):
        from apps.api.services.union_management_service import UnionManagementService

        svc = UnionManagementService(db=AsyncMock())
        assert svc._calculate_proportional_rate(100_000, 200_000) == 0.5

    def test_비례율_제로_감정가(self):
        from apps.api.services.union_management_service import UnionManagementService

        svc = UnionManagementService(db=AsyncMock())
        assert svc._calculate_proportional_rate(100_000, 0) == 1.0

    def test_개인_분담금_계산(self):
        from apps.api.services.union_management_service import UnionManagementService

        svc = UnionManagementService(db=AsyncMock())
        result = svc._calculate_contribution(
            target_area_sqm=84.0,
            avg_sale_price_per_sqm=20_000_000,
            individual_appraised_value=500_000_000,
            proportional_rate=0.8,
        )
        # 84 * 20M = 1,680M, credit = 500M * 0.8 = 400M, contribution = 1,280M
        assert result == pytest.approx(1_280_000_000)

    def test_분담금_음수_방지(self):
        from apps.api.services.union_management_service import UnionManagementService

        svc = UnionManagementService(db=AsyncMock())
        result = svc._calculate_contribution(
            target_area_sqm=50.0,
            avg_sale_price_per_sqm=10_000,
            individual_appraised_value=10_000_000,
            proportional_rate=1.0,
        )
        assert result == 0.0  # max(0, 500000 - 10000000) = 0

    def test_결과_클래스(self):
        from apps.api.services.union_management_service import UnionContributionResult

        r = UnionContributionResult(
            proportional_rate=0.8,
            individual_contribution=1_000_000,
            total_project_cost=10_000_000,
            breakdown={"a": 1},
            scenarios=[{"scenario": "base"}],
        )
        assert r.proportional_rate == 0.8
        assert len(r.scenarios) == 1


# ── CircuitBreaker (base_client.py) ──


class TestCircuitBreaker:
    def test_초기_상태_CLOSED(self):
        from apps.api.integrations.base_client import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute()

    def test_실패_누적_후_OPEN(self):
        from apps.api.integrations.base_client import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.can_execute()

    def test_복구_시간_후_HALF_OPEN(self):
        from apps.api.integrations.base_client import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        import time
        time.sleep(0.02)
        assert cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN

    def test_HALF_OPEN_성공_후_CLOSED(self):
        from apps.api.integrations.base_client import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01, half_open_max=2)
        cb.record_failure()
        cb.record_failure()

        import time
        time.sleep(0.02)
        cb.can_execute()  # → HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_HALF_OPEN_최대_호출_제한(self):
        from apps.api.integrations.base_client import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01, half_open_max=1)
        cb.record_failure()
        cb.record_failure()

        import time
        time.sleep(0.02)
        assert cb.can_execute()  # → HALF_OPEN, calls=0
        cb.half_open_calls = 1  # 이미 1회 호출
        assert not cb.can_execute()  # half_open_max=1 초과


# ── BaseAPIClient ──


class TestBaseAPIClient:
    def test_기본_속성(self):
        from apps.api.integrations.base_client import BaseAPIClient

        client = BaseAPIClient()
        assert client.service_name == "unknown"
        assert client.timeout == 30.0

    def test_기본_헤더(self):
        from apps.api.integrations.base_client import BaseAPIClient

        client = BaseAPIClient()
        headers = client._default_headers()
        assert "PropAI" in headers.get("User-Agent", "")


# ── BlockchainService ──


class TestBlockchainServiceInit:
    def test_모듈_상수(self):
        from apps.api.services.blockchain_service import (
            AMOY_CHAIN_ID,
            _ONCHAIN_STATUS_MAP,
            _ONCHAIN_STATUS_NAMES,
        )

        assert AMOY_CHAIN_ID == 80002
        assert len(_ONCHAIN_STATUS_MAP) == 5
        assert len(_ONCHAIN_STATUS_NAMES) == 5

    def test_인스턴스_생성(self):
        from apps.api.services.blockchain_service import BlockchainService

        svc = BlockchainService(db=AsyncMock())
        assert svc._w3 is None
        assert svc._abi is None


# ── AVMService ──


class TestAVMServiceInit:
    def test_모듈_상수(self):
        from apps.api.services.avm_service import _BASE_CONFIDENCE, _MODEL_STAGES

        assert "production" in _BASE_CONFIDENCE
        assert _BASE_CONFIDENCE["fallback"] == 0.40
        assert len(_MODEL_STAGES) == 2

    def test_인스턴스_생성(self):
        from apps.api.services.avm_service import AVMService

        svc = AVMService(db=AsyncMock())
        assert svc._model_stage == "fallback"
        assert svc._model is None


# ── FloorPlanImageService ──


class TestFloorPlanImageService:
    def test_build_prompt(self):
        from apps.api.services.floor_plan_image_service import FloorPlanImageService

        svc = FloorPlanImageService(db=AsyncMock())
        prompt = svc._build_prompt(area_sqm=84.0, room_count=3, style="modern")
        assert "84.0sqm" in prompt
        assert "3 bedrooms" in prompt
        assert "modern" in prompt

    def test_build_prompt_추가_정보(self):
        from apps.api.services.floor_plan_image_service import FloorPlanImageService

        svc = FloorPlanImageService(db=AsyncMock())
        prompt = svc._build_prompt(84, 2, "minimalist", "south facing")
        assert "south facing" in prompt


# ── SafetyService ──


class TestSafetyServiceHelpers:
    def test_sanitize_url(self):
        from apps.api.services.safety_service import _sanitize_url

        assert _sanitize_url("rtsp://user:pass@camera.local/stream") == "rtsp://***@camera.local/stream"

    def test_sanitize_url_무인증(self):
        from apps.api.services.safety_service import _sanitize_url

        assert _sanitize_url("rtsp://camera.local/stream") == "rtsp://camera.local/stream"

    def test_모듈_상수(self):
        from apps.api.services.safety_service import _FRAME_SKIP, _MIN_CONFIDENCE, _VIOLATION_CLASSES

        assert _FRAME_SKIP == 5
        assert _MIN_CONFIDENCE == 0.45
        assert 0 in _VIOLATION_CLASSES
        assert _VIOLATION_CLASSES[0] == "helmet_off"


# ── ParkingService ──


class TestParkingServiceHelpers:
    def test_번호판_정규식_유효(self):
        from apps.api.services.parking_service import _PLATE_PATTERN

        assert _PLATE_PATTERN.match("123가4567")
        assert _PLATE_PATTERN.match("12가3456")

    def test_번호판_정규식_무효(self):
        from apps.api.services.parking_service import _PLATE_PATTERN

        assert not _PLATE_PATTERN.match("ABC1234")
        assert not _PLATE_PATTERN.match("1234")
        assert not _PLATE_PATTERN.match("")


# ── BIMIFCService ──


class TestBIMIFCServiceInit:
    def test_인스턴스_생성(self):
        from apps.api.services.bim_ifc_service import BIMIFCService

        svc = BIMIFCService(db=AsyncMock())
        assert svc.db is not None


# ── JeonseRiskService ──


class TestJeonseRiskService:
    def test_결과_클래스(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskResult

        r = JeonseRiskResult(
            jeonse_ratio=0.75,
            risk_level="medium",
            risk_score=0.5,
            analysis="test",
            factors=[{"factor": "ratio", "impact": "medium"}],
            hug_eligible=True,
            hug_reason="적격",
        )
        assert r.jeonse_ratio == 0.75
        assert r.hug_eligible
        assert r.market_data == {}

    def test_인스턴스_생성(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        svc = JeonseRiskService(db=AsyncMock())
        assert svc.db is not None

    def test_수도권_코드(self):
        from apps.api.services.jeonse_risk_service import _METROPOLITAN_CODES

        assert "11" in _METROPOLITAN_CODES
        assert "41" in _METROPOLITAN_CODES


# ── FacilityReservationService ──


class TestFacilityReservation:
    @pytest.mark.asyncio
    async def test_시작_종료_검증(self):
        from apps.api.services.facility_reservation_service import FacilityReservationService

        svc = FacilityReservationService(db=AsyncMock())
        with pytest.raises(ValueError, match="시작 시간"):
            await svc.create_reservation(
                tenant_id=uuid4(),
                project_id=uuid4(),
                facility_name="회의실A",
                reserved_by=uuid4(),
                start_time=datetime(2025, 1, 1, 12, 0),
                end_time=datetime(2025, 1, 1, 10, 0),
            )


# ── DigitalTwinService (B06 패치 경로) ──


class TestDigitalTwinServiceAnomalyDetection:
    @pytest.mark.asyncio
    async def test_데이터_부족_시_건너뜀(self):
        from apps.api.services.digital_twin_service import DigitalTwinService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        svc = DigitalTwinService(db=mock_db)
        result = await svc.detect_anomaly(
            tenant_id=uuid4(),
            project_id=uuid4(),
            sensor_type="temperature",
            current_features=[25.0, 60.0],
            historical_data=[[24.0, 55.0]] * 10,  # 10 < 100 최소 요건
        )
        assert result.is_anomaly is False
        assert result.severity == "info"
        mock_db.add.assert_called_once()


# ── exceptions.py ──


class TestExceptions:
    def test_ExternalServiceError(self):
        from apps.api.exceptions import ExternalServiceError

        err = ExternalServiceError("test_service", "connection refused")
        assert "test_service" in str(err)

    def test_register_exception_handlers(self):
        from apps.api.exceptions import register_exception_handlers

        mock_app = MagicMock()
        register_exception_handlers(mock_app)
        # @app.exception_handler 데코레이터를 사용하므로 exception_handler가 호출됨
        assert mock_app.exception_handler.called

    def test_PropAIError(self):
        from apps.api.exceptions import PropAIError

        err = PropAIError("CODE", "msg", 400, {"key": "val"})
        assert err.error_code == "CODE"
        assert err.status_code == 400

    def test_NotFoundError(self):
        from apps.api.exceptions import NotFoundError

        err = NotFoundError("Project", "123")
        assert err.status_code == 404

    def test_AuthenticationError(self):
        from apps.api.exceptions import AuthenticationError

        err = AuthenticationError()
        assert err.status_code == 401

    def test_PermissionDeniedError(self):
        from apps.api.exceptions import PermissionDeniedError

        err = PermissionDeniedError()
        assert err.status_code == 403

    def test_TenantIsolationError(self):
        from apps.api.exceptions import TenantIsolationError

        err = TenantIsolationError()
        assert err.status_code == 403


# ── versioning.py ──


class TestVersioningMiddleware:
    def test_미들웨어_초기화(self):
        from apps.api.versioning import VersionHeaderMiddleware

        mock_app = MagicMock()
        mw = VersionHeaderMiddleware(mock_app)
        assert mw is not None


# ── rate_limit.py ──


class TestRateLimit:
    def test_limiter_생성(self):
        from apps.api.rate_limit import ai_limiter, limiter

        assert limiter is not None
        assert isinstance(ai_limiter, str)


# ── metrics.py ──


class TestMetrics:
    def test_메트릭_정의(self):
        from apps.api.metrics import (
            AGENT_COMPLETION,
            AGENT_STEP_DURATION,
            AI_COST_TOTAL,
            AI_TOKEN_TOTAL,
            AVM_ESTIMATES,
            DB_POOL_CHECKED_OUT,
            DB_POOL_SIZE,
            PROJECT_CREATED,
            WEBHOOK_DELIVERIES,
        )

        assert AI_COST_TOTAL is not None
        assert AI_TOKEN_TOTAL is not None
        assert AGENT_STEP_DURATION is not None
        assert AGENT_COMPLETION is not None
        assert PROJECT_CREATED is not None
        assert AVM_ESTIMATES is not None
        assert WEBHOOK_DELIVERIES is not None
        assert DB_POOL_SIZE is not None
        assert DB_POOL_CHECKED_OUT is not None
