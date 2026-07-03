"""대형 서비스 커버리지 대량 테스트.

blockchain, avm, bim, jeonse, floor_plan_image, safety, parking,
construction, drone, chatbot, contractor, webhook, design 서비스의
순수 메서드 및 mock async 메서드 커버리지를 확보한다.
"""

import os
import sys
from datetime import UTC, datetime

UTC = UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000003")


# ═══════════════════════════════════════════
# BlockchainService (233 stmts, 183 missed)
# ═══════════════════════════════════════════


class TestBlockchainServiceConstants:
    def test_onchain_status_map(self):
        from apps.api.services.blockchain_service import _ONCHAIN_STATUS_MAP

        assert 0 in _ONCHAIN_STATUS_MAP
        assert 4 in _ONCHAIN_STATUS_MAP
        assert len(_ONCHAIN_STATUS_MAP) == 5

    def test_onchain_status_names(self):
        from apps.api.services.blockchain_service import _ONCHAIN_STATUS_NAMES

        assert _ONCHAIN_STATUS_NAMES[0] == "PendingFunding"
        assert _ONCHAIN_STATUS_NAMES[3] == "Released"

    def test_amoy_chain_id(self):
        from apps.api.services.blockchain_service import AMOY_CHAIN_ID

        assert AMOY_CHAIN_ID == 80002

    def test_abi_paths(self):
        from apps.api.services.blockchain_service import _ABI_PATH, _DEPLOYMENT_DIR

        assert "contracts" in str(_DEPLOYMENT_DIR)
        assert "PropAIEscrow" in str(_ABI_PATH)


class TestBlockchainServiceMethods:
    def test_init(self):
        from apps.api.services.blockchain_service import BlockchainService

        svc = BlockchainService(db=AsyncMock())
        assert svc._w3 is None
        assert svc._contract is None
        assert svc._abi is None

    def test_load_abi_no_files(self):
        from apps.api.services.blockchain_service import BlockchainService

        svc = BlockchainService(db=AsyncMock())
        # 파일이 없으면 빈 리스트 반환
        abi = svc._load_abi()
        assert isinstance(abi, list)

    def test_load_contract_no_abi(self):
        from apps.api.services.blockchain_service import BlockchainService

        svc = BlockchainService(db=AsyncMock())
        svc._abi = []
        result = svc._load_contract()
        assert result is None

    def test_load_contract_no_address(self):
        from apps.api.services.blockchain_service import BlockchainService

        svc = BlockchainService(db=AsyncMock())
        svc._abi = [{"name": "test"}]
        svc.settings = MagicMock()
        svc.settings.escrow_contract_address = ""
        result = svc._load_contract()
        assert result is None

    @pytest.mark.asyncio
    async def test_create_escrow_no_contract(self):
        from apps.api.services.blockchain_service import BlockchainService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        # refresh 시 id/created_at 설정
        async def set_attrs(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(tz=UTC)
        mock_db.refresh = AsyncMock(side_effect=set_attrs)

        svc = BlockchainService(db=mock_db)
        svc._abi = []  # contract 없음

        result = await svc.create_escrow(
            project_id=TEST_PROJECT_ID,
            tenant_id=TEST_TENANT_ID,
            payer_address="0x1234",
            payee_address="0x5678",
            subcontractor_address="0x9abc",
            expires_at=9999999999,
            condition_hash="0xdeadbeef",
        )
        assert result is not None
        mock_db.add.assert_called_once()


# ═══════════════════════════════════════════
# AVMService (209 stmts, 138 missed)
# ═══════════════════════════════════════════


class TestAVMServiceConstants:
    def test_model_stages(self):
        from apps.api.services.avm_service import _MODEL_STAGES

        assert len(_MODEL_STAGES) == 2
        assert _MODEL_STAGES[0][1] == "production"

    def test_base_confidence(self):
        from apps.api.services.avm_service import _BASE_CONFIDENCE

        assert _BASE_CONFIDENCE["production"] == 0.87
        assert _BASE_CONFIDENCE["fallback"] == 0.40


class TestAVMServiceMethods:
    def test_init(self):
        from apps.api.services.avm_service import AVMService

        svc = AVMService(db=AsyncMock())
        assert svc._model is None
        assert svc._model_stage == "fallback"

    @pytest.mark.asyncio
    async def test_load_model_fallback(self):
        from apps.api.services.avm_service import AVMService

        svc = AVMService(db=AsyncMock())
        await svc._load_model()
        assert svc._model_stage == "fallback"

    def test_estimate_poi_scores_도심(self):
        from apps.api.services.avm_service import AVMService

        scores = AVMService._estimate_poi_scores(37.5665, 126.9780)
        assert scores["distance_to_subway_m"] < 300
        assert scores["school_score"] > 80

    def test_estimate_poi_scores_외곽(self):
        from apps.api.services.avm_service import AVMService

        scores = AVMService._estimate_poi_scores(37.0, 127.5)
        assert scores["distance_to_subway_m"] > 500
        assert scores["school_score"] < 80

    @pytest.mark.asyncio
    async def test_fetch_spatial_data_no_pnu(self):
        from apps.api.services.avm_service import AVMService

        svc = AVMService(db=AsyncMock())
        result = await svc._fetch_spatial_data()
        assert result["land_official_price"] == 0
        assert result["floor_area_ratio"] == 0.0

    @pytest.mark.asyncio
    async def test_estimate_fallback(self):
        """폴백 모델로 시세 추정."""
        from apps.api.services.avm_service import AVMService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        async def set_attrs(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(tz=UTC)
        mock_db.refresh = AsyncMock(side_effect=set_attrs)

        svc = AVMService(db=mock_db)
        svc._model = None
        svc._model_stage = "fallback"

        # _fetch_comparables와 _fetch_spatial_data를 mock
        with patch.object(svc, "_fetch_comparables", return_value=[]), \
             patch.object(svc, "_fetch_spatial_data", return_value={
                 "land_official_price": 0,
                 "floor_area_ratio": 0.0,
                 "building_coverage_ratio": 0.0,
                 "distance_to_subway_m": 500.0,
                 "distance_to_school_m": 300.0,
                 "school_score": 75.0,
                 "noise_db": 55.0,
                 "view_score": 60.0,
             }):
            from packages.schemas.models import AVMRequest
            result = await svc.estimate(
                request=AVMRequest(
                    project_id=TEST_PROJECT_ID,
                    address="서울 강남구 역삼동 123-45",
                    area_sqm=84.0,
                    floor=10,
                ),
                tenant_id=TEST_TENANT_ID,
            )
        assert result.estimated_price > 0
        assert result.confidence_score > 0


# ═══════════════════════════════════════════
# JeonseRiskService (158 stmts, 109 missed)
# ═══════════════════════════════════════════


class TestJeonseRiskStaticMethods:
    def test_risk_level_critical(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        level, score = JeonseRiskService._calculate_risk_level(0.95)
        assert level == "CRITICAL"
        assert score == 0.95

    def test_risk_level_high(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        level, score = JeonseRiskService._calculate_risk_level(0.85)
        assert level == "HIGH"
        assert score == 0.80

    def test_risk_level_medium(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        level, score = JeonseRiskService._calculate_risk_level(0.75)
        assert level == "MEDIUM"
        assert score == 0.55

    def test_risk_level_low(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        level, score = JeonseRiskService._calculate_risk_level(0.65)
        assert level == "LOW"
        assert score == 0.30

    def test_risk_level_safe(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        level, score = JeonseRiskService._calculate_risk_level(0.50)
        assert level == "SAFE"
        assert score == 0.10

    def test_hug_eligible_수도권_이하(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        eligible, reason = JeonseRiskService._check_hug_eligibility(500_000_000, is_metropolitan=True)
        assert eligible is True
        assert "가입 가능" in reason

    def test_hug_not_eligible_수도권_초과(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        eligible, reason = JeonseRiskService._check_hug_eligibility(800_000_000, is_metropolitan=True)
        assert eligible is False
        assert "가입 불가" in reason

    def test_hug_eligible_지방(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        eligible, reason = JeonseRiskService._check_hug_eligibility(400_000_000, is_metropolitan=False)
        assert eligible is True

    def test_hug_not_eligible_지방(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        eligible, reason = JeonseRiskService._check_hug_eligibility(600_000_000, is_metropolitan=False)
        assert eligible is False


class TestJeonseFraudPatterns:
    def test_갭투자_패턴(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        # 전세가율 95% → 갭투자 + 깡통전세 모두 발생
        patterns = JeonseRiskService._detect_fraud_patterns(
            address="서울 강남구 역삼동",
            jeonse_price=950_000_000,
            market_data={"avg_sale_price": 1_000_000_000, "avg_jeonse_price": 500_000_000, "trade_count": 10},
        )
        factor_names = [p["factor"] for p in patterns]
        assert "갭투자 위험" in factor_names
        assert "깡통전세 위험" in factor_names

    def test_거래_희소성(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        patterns = JeonseRiskService._detect_fraud_patterns(
            address="서울 강남구 역삼동",
            jeonse_price=200_000_000,
            market_data={"avg_sale_price": 500_000_000, "avg_jeonse_price": 200_000_000, "trade_count": 1},
        )
        factor_names = [p["factor"] for p in patterns]
        assert "거래 희소성" in factor_names

    def test_신축_빌라(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        patterns = JeonseRiskService._detect_fraud_patterns(
            address="서울 빌라 ABC",
            jeonse_price=400_000_000,
            market_data={"avg_sale_price": 450_000_000, "avg_jeonse_price": 300_000_000, "trade_count": 10},
        )
        factor_names = [p["factor"] for p in patterns]
        assert "신축 빌라 전세사기 패턴" in factor_names

    def test_고액_보증금(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        patterns = JeonseRiskService._detect_fraud_patterns(
            address="서울 강남",
            jeonse_price=500_000_000,
            market_data={"avg_sale_price": 1_000_000_000, "avg_jeonse_price": 200_000_000, "trade_count": 10},
        )
        factor_names = [p["factor"] for p in patterns]
        assert "고액 보증금 — 시장 이상치" in factor_names

    def test_등기부_항상_포함(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskService

        patterns = JeonseRiskService._detect_fraud_patterns(
            address="서울",
            jeonse_price=100_000_000,
            market_data={"avg_sale_price": 500_000_000, "avg_jeonse_price": 200_000_000, "trade_count": 10},
        )
        factor_names = [p["factor"] for p in patterns]
        assert "등기부등본 확인 필요" in factor_names
        assert "전세금 반환 보증 미가입 위험" in factor_names


class TestJeonseRiskResult:
    def test_jeonse_risk_result(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskResult

        result = JeonseRiskResult(
            jeonse_ratio=0.85,
            risk_level="HIGH",
            risk_score=0.80,
            analysis="위험",
            factors=[{"factor": "test"}],
            hug_eligible=True,
            hug_reason="가입 가능",
        )
        assert result.jeonse_ratio == 0.85
        assert result.hug_eligible is True
        assert result.market_data == {}

    def test_jeonse_risk_result_with_market_data(self):
        from apps.api.services.jeonse_risk_service import JeonseRiskResult

        result = JeonseRiskResult(
            jeonse_ratio=0.5,
            risk_level="SAFE",
            risk_score=0.10,
            analysis="안전",
            factors=[],
            market_data={"test": 1},
        )
        assert result.market_data == {"test": 1}

    def test_metropolitan_codes(self):
        from apps.api.services.jeonse_risk_service import _METROPOLITAN_CODES

        assert "11" in _METROPOLITAN_CODES
        assert "41" in _METROPOLITAN_CODES
        assert "28" in _METROPOLITAN_CODES


# ═══════════════════════════════════════════
# ConstructionAIService (193 stmts, 58 missed)
# ═══════════════════════════════════════════


class TestConstructionSchedule:
    def test_generate_schedule_기본(self):
        from apps.api.services.construction_ai_service import ConstructionAIService

        svc = ConstructionAIService(db=AsyncMock())
        result = svc.generate_construction_schedule(
            total_area_sqm=5000,
            floors_above=10,
            floors_below=2,
            structure_type="RC",
        )
        assert result["total_duration_days"] > 0
        assert len(result["schedule"]) == 13
        assert len(result["critical_path"]) > 0
        assert len(result["milestones"]) == 4

    def test_generate_schedule_SRC(self):
        from apps.api.services.construction_ai_service import ConstructionAIService

        svc = ConstructionAIService(db=AsyncMock())
        result = svc.generate_construction_schedule(
            total_area_sqm=10000,
            floors_above=20,
            structure_type="SRC",
        )
        assert result["total_duration_days"] > 0
        # SRC는 RC보다 1.15배 오래 걸림
        rc_result = svc.generate_construction_schedule(
            total_area_sqm=10000,
            floors_above=20,
            structure_type="RC",
        )
        assert result["total_duration_days"] >= rc_result["total_duration_days"]

    def test_generate_schedule_SC(self):
        from apps.api.services.construction_ai_service import ConstructionAIService

        svc = ConstructionAIService(db=AsyncMock())
        result = svc.generate_construction_schedule(
            total_area_sqm=3000,
            structure_type="SC",
        )
        assert result["total_duration_days"] > 0

    def test_schedule_critical_path_includes_착공_준공(self):
        from apps.api.services.construction_ai_service import ConstructionAIService

        svc = ConstructionAIService(db=AsyncMock())
        result = svc.generate_construction_schedule(total_area_sqm=5000)
        milestones = [m["name"] for m in result["milestones"]]
        assert "착공" in milestones
        assert "준공" in milestones

    def test_schedule_small_area(self):
        """최소 면적 — 모든 공정이 최소 3일."""
        from apps.api.services.construction_ai_service import ConstructionAIService

        svc = ConstructionAIService(db=AsyncMock())
        result = svc.generate_construction_schedule(total_area_sqm=100)
        for phase in result["schedule"]:
            assert phase["duration_days"] >= 3


class TestZEBEnergy:
    def test_estimate_zeb_기본(self):
        from apps.api.services.construction_ai_service import ConstructionAIService

        svc = ConstructionAIService(db=AsyncMock())
        result = svc.estimate_zeb_energy(
            total_area_sqm=5000,
            floors=10,
            window_wall_ratio=0.35,
        )
        assert "annual_energy_demand_kwh" in result
        assert "annual_renewable_generation_kwh" in result
        assert "zeb_grade" in result
        assert "energy_independence_rate" in result
        assert "recommendations" in result
        assert result["annual_energy_demand_kwh"] > 0

    def test_estimate_zeb_높은_단열(self):
        from apps.api.services.construction_ai_service import ConstructionAIService

        svc = ConstructionAIService(db=AsyncMock())
        result_high = svc.estimate_zeb_energy(
            total_area_sqm=5000,
            insulation_grade="1등급",
        )
        result_low = svc.estimate_zeb_energy(
            total_area_sqm=5000,
            insulation_grade="3등급",
        )
        # 높은 단열 = 낮은 에너지 수요
        assert result_high["annual_energy_demand_kwh"] <= result_low["annual_energy_demand_kwh"]


class TestConstructionConstants:
    def test_construction_phases(self):
        from apps.api.services.construction_ai_service import _CONSTRUCTION_PHASES

        assert len(_CONSTRUCTION_PHASES) == 13
        assert _CONSTRUCTION_PHASES[0]["name"] == "가설공사"
        assert _CONSTRUCTION_PHASES[-1]["name"] == "준공청소/검사"

    def test_structure_factors(self):
        from apps.api.services.construction_ai_service import _STRUCTURE_FACTORS

        assert _STRUCTURE_FACTORS["RC"] == 1.0
        assert _STRUCTURE_FACTORS["SRC"] == 1.15

    def test_zeb_grades(self):
        from apps.api.services.construction_ai_service import _ZEB_GRADES

        assert len(_ZEB_GRADES) == 5
        assert _ZEB_GRADES[0][1] == "1등급"

    def test_defect_types(self):
        from apps.api.services.construction_ai_service import _DEFECT_TYPES

        assert "균열(크랙)" in _DEFECT_TYPES
        assert len(_DEFECT_TYPES) >= 9


# ═══════════════════════════════════════════
# FloorPlanImageService (109 stmts, 89 missed)
# ═══════════════════════════════════════════


class TestFloorPlanImageService:
    def test_build_prompt_기본(self):
        from apps.api.services.floor_plan_image_service import FloorPlanImageService

        svc = FloorPlanImageService(db=AsyncMock())
        prompt = svc._build_prompt(area_sqm=84.0, room_count=3)
        assert "84.0sqm" in prompt
        assert "3 bedrooms" in prompt
        assert "modern" in prompt

    def test_build_prompt_커스텀_스타일(self):
        from apps.api.services.floor_plan_image_service import FloorPlanImageService

        svc = FloorPlanImageService(db=AsyncMock())
        prompt = svc._build_prompt(area_sqm=120, room_count=4, style="minimalist", additional="balcony")
        assert "minimalist" in prompt
        assert "balcony" in prompt
        assert "4 bedrooms" in prompt


# ═══════════════════════════════════════════
# SafetyService (102 stmts, 78 missed)
# ═══════════════════════════════════════════


class TestSafetyServiceConstants:
    def test_frame_skip(self):
        from apps.api.services.safety_service import _FRAME_SKIP

        assert _FRAME_SKIP == 5

    def test_violation_classes(self):
        from apps.api.services.safety_service import _VIOLATION_CLASSES

        assert _VIOLATION_CLASSES[0] == "helmet_off"
        assert _VIOLATION_CLASSES[1] == "vest_off"

    def test_min_confidence(self):
        from apps.api.services.safety_service import _MIN_CONFIDENCE

        assert _MIN_CONFIDENCE == 0.45

    def test_sanitize_url(self):
        from apps.api.services.safety_service import _sanitize_url

        result = _sanitize_url("rtsp://user:password@host:554/stream")
        assert "password" not in result


# ═══════════════════════════════════════════
# ParkingService (87 stmts, 66 missed)
# ═══════════════════════════════════════════


class TestParkingServiceFunctions:
    def test_plate_pattern_유효(self):
        from apps.api.services.parking_service import _PLATE_PATTERN

        assert _PLATE_PATTERN.match("12가3456")
        assert _PLATE_PATTERN.match("123가4567")

    def test_plate_pattern_무효(self):
        from apps.api.services.parking_service import _PLATE_PATTERN

        assert not _PLATE_PATTERN.match("ABC1234")
        assert not _PLATE_PATTERN.match("1234")

    def test_validate_plate_number_유효(self):
        from apps.api.services.parking_service import validate_plate_number

        assert validate_plate_number("12가3456") == "12가3456"
        assert validate_plate_number("123가4567") == "123가4567"
        assert validate_plate_number("12-가-3456") == "12가3456"

    def test_validate_plate_number_무효(self):
        from apps.api.services.parking_service import validate_plate_number

        assert validate_plate_number("ABC1234") is None
        assert validate_plate_number("") is None


# ═══════════════════════════════════════════
# DroneIoTService (61 stmts, 33 missed)
# ═══════════════════════════════════════════


class TestDroneIoTServiceMethods:
    def test_classify_severity_emergency(self):
        from apps.api.services.drone_iot_service import DroneIoTService

        svc = DroneIoTService(db=AsyncMock())
        assert svc._classify_severity("structural_crack", 0.9) == "EMERGENCY"
        assert svc._classify_severity("collapse_risk", 0.7) == "EMERGENCY"

    def test_classify_severity_high(self):
        from apps.api.services.drone_iot_service import DroneIoTService

        svc = DroneIoTService(db=AsyncMock())
        assert svc._classify_severity("water_leak", 0.5) == "HIGH"
        assert svc._classify_severity("some_defect", 0.90) == "HIGH"

    def test_classify_severity_medium(self):
        from apps.api.services.drone_iot_service import DroneIoTService

        svc = DroneIoTService(db=AsyncMock())
        assert svc._classify_severity("minor_crack", 0.65) == "MEDIUM"

    def test_classify_severity_low(self):
        from apps.api.services.drone_iot_service import DroneIoTService

        svc = DroneIoTService(db=AsyncMock())
        assert svc._classify_severity("dust", 0.3) == "LOW"

    @pytest.mark.asyncio
    async def test_detect_defects_no_api_key(self):
        """현행 스펙(#7): 키 미설정 시 가짜 빈 리스트 대신 정직한 상태 dict 반환."""
        from apps.api.services.drone_iot_service import DroneIoTService

        svc = DroneIoTService(db=AsyncMock())
        svc.settings = MagicMock()
        svc.settings.roboflow_api_key = ""
        result = await svc._detect_defects("http://example.com/image.jpg")
        assert isinstance(result, dict)
        assert result["status"] == "service_not_configured"
        assert result["service_available"] is False
        assert result["detections"] == []


# ═══════════════════════════════════════════
# ChatbotService (57 stmts, 33 missed)
# ═══════════════════════════════════════════


class TestChatbotServiceStatic:
    def test_session_title(self):
        from apps.api.services.chatbot_service import ChatbotService

        assert ChatbotService._session_title("investment") == "Investment advisory"
        assert ChatbotService._session_title("construction") == "Construction advisory"

    def test_token_estimate(self):
        from apps.api.services.chatbot_service import ChatbotService

        assert ChatbotService._token_estimate("hello world") >= 3
        assert ChatbotService._token_estimate("") >= 1

    def test_reply_investment(self):
        from apps.api.services.chatbot_service import ChatbotService

        reply, actions = ChatbotService._reply("investment", "What is the current cap rate?")
        assert "investment" in reply
        assert len(actions) == 3

    def test_reply_general(self):
        from apps.api.services.chatbot_service import ChatbotService

        reply, actions = ChatbotService._reply("unknown_domain", "hello")
        assert "general" not in reply or "unknown_domain" in reply
        assert len(actions) == 3

    def test_reply_truncates_long_content(self):
        from apps.api.services.chatbot_service import ChatbotService

        long_content = "word " * 200
        reply, _ = ChatbotService._reply("design", long_content)
        assert len(reply) < len(long_content) * 2

    def test_domain_actions_keys(self):
        from apps.api.services.chatbot_service import _DOMAIN_ACTIONS

        assert "investment" in _DOMAIN_ACTIONS
        assert "construction" in _DOMAIN_ACTIONS
        assert "design" in _DOMAIN_ACTIONS
        assert "regulation" in _DOMAIN_ACTIONS
        assert "general" in _DOMAIN_ACTIONS


# ═══════════════════════════════════════════
# ContractorService (67 stmts, 34 missed)
# ═══════════════════════════════════════════


class TestContractorServiceScore:
    def _make_contractor(self, **kwargs) -> MagicMock:
        c = MagicMock()
        c.category = kwargs.get("category", "general_contractor")
        c.specialties_json = kwargs.get("specialties_json", [])
        c.address = kwargs.get("address", "")
        c.rating = kwargs.get("rating")
        return c

    def test_score_category_aligned(self):
        from apps.api.services.contractor_service import ContractorService

        contractor = self._make_contractor(category="plumbing", rating=4.5)
        score, reasons = ContractorService._score_candidate(
            category="plumbing",
            required_specialties=["pipe"],
            region_hint=None,
            contractor=contractor,
        )
        assert score > 45
        assert "category aligned" in reasons

    def test_score_general_contractor_fallback(self):
        from apps.api.services.contractor_service import ContractorService

        contractor = self._make_contractor(category="general_contractor", rating=3.0)
        score, reasons = ContractorService._score_candidate(
            category="electrical",
            required_specialties=[],
            region_hint=None,
            contractor=contractor,
        )
        assert "general contractor fallback" in reasons

    def test_score_specialty_overlap(self):
        from apps.api.services.contractor_service import ContractorService

        contractor = self._make_contractor(
            category="electrical",
            specialties_json=["wiring", "panel"],
            rating=4.0,
        )
        score, reasons = ContractorService._score_candidate(
            category="electrical",
            required_specialties=["wiring", "panel", "lighting"],
            region_hint=None,
            contractor=contractor,
        )
        assert score > 65
        overlap_reason = [r for r in reasons if "specialty overlap" in r]
        assert len(overlap_reason) == 1

    def test_score_regional_match(self):
        from apps.api.services.contractor_service import ContractorService

        contractor = self._make_contractor(
            category="plumbing",
            address="서울 강남구 역삼동",
            rating=4.0,
        )
        score, reasons = ContractorService._score_candidate(
            category="plumbing",
            required_specialties=[],
            region_hint="강남",
            contractor=contractor,
        )
        assert "regional coverage matched" in reasons

    def test_score_strong_rating(self):
        from apps.api.services.contractor_service import ContractorService

        contractor = self._make_contractor(rating=4.5)
        score, reasons = ContractorService._score_candidate(
            category="other",
            required_specialties=[],
            region_hint=None,
            contractor=contractor,
        )
        assert "strong rating" in reasons

    def test_score_clamped_to_100(self):
        from apps.api.services.contractor_service import ContractorService

        contractor = self._make_contractor(
            category="electrical",
            specialties_json=["a", "b", "c", "d"],
            address="서울 강남",
            rating=5.0,
        )
        score, _ = ContractorService._score_candidate(
            category="electrical",
            required_specialties=["a", "b", "c", "d"],
            region_hint="강남",
            contractor=contractor,
        )
        assert score <= 100.0


# ═══════════════════════════════════════════
# WebhookService (58 stmts, 35 missed)
# ═══════════════════════════════════════════


class TestWebhookSignPayload:
    def test_sign_payload_기본(self):
        from apps.api.services.webhook_service import sign_payload

        sig = sign_payload("secret123", {"key": "value"})
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex

    def test_sign_payload_일관성(self):
        from apps.api.services.webhook_service import sign_payload

        sig1 = sign_payload("secret", {"a": 1, "b": 2})
        sig2 = sign_payload("secret", {"b": 2, "a": 1})
        assert sig1 == sig2  # sort_keys=True이므로 동일

    def test_sign_payload_다른_시크릿(self):
        from apps.api.services.webhook_service import sign_payload

        sig1 = sign_payload("secret1", {"key": "value"})
        sig2 = sign_payload("secret2", {"key": "value"})
        assert sig1 != sig2

    def test_webhook_constants(self):
        from apps.api.services.webhook_service import _MAX_RETRIES, _TIMEOUT_SECONDS

        assert _MAX_RETRIES == 3
        assert _TIMEOUT_SECONDS == 10.0


# ═══════════════════════════════════════════
# DesignAIService (53 stmts, 38 missed)
# ═══════════════════════════════════════════


class TestDesignAIServiceConstants:
    def test_prompt_template(self):
        from apps.api.services.design_ai_service import _DESIGN_PROMPT_TEMPLATE

        assert "설계 개요" in _DESIGN_PROMPT_TEMPLATE
        assert "한국어" in _DESIGN_PROMPT_TEMPLATE

    def test_init(self):
        from apps.api.services.design_ai_service import DesignAIService

        svc = DesignAIService(db=AsyncMock())
        assert svc.db is not None


# ═══════════════════════════════════════════
# BIMIFCService (147 stmts, 130 missed)
# ═══════════════════════════════════════════


class TestBIMIFCServiceInit:
    def test_init(self):
        from apps.api.services.bim_ifc_service import BIMIFCService

        svc = BIMIFCService(db=AsyncMock())
        assert svc.db is not None
        assert svc.settings is not None
