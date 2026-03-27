"""오케스트레이터 + 인테그레이션 클라이언트 커버리지 테스트.

propai_orchestrator, molit_client, vworld_client,
asset_intelligence_service, auction_service 의
순수 메서드 + mock async 메서드를 커버한다.
"""

import os
import sys
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000003")


# ═══════════════════════════════════════════
# PropAIOrchestrator (215 stmts, 184 missed)
# ═══════════════════════════════════════════


class TestOrchestratorConstants:
    def test_steps_정의(self):
        from apps.api.agents.propai_orchestrator import STEPS

        assert len(STEPS) == 7
        assert "parcel_analysis" in STEPS
        assert "report" in STEPS


class TestOrchestratorCalcIRR:
    def test_irr_기본(self):
        from apps.api.agents.propai_orchestrator import PropAIOrchestrator

        irr = PropAIOrchestrator._calc_irr(
            investment=100_000_000,
            annual_income=15_000_000,
            terminal_value=120_000_000,
            years=5,
        )
        assert isinstance(irr, float)
        assert irr > 0

    def test_irr_투자없음(self):
        from apps.api.agents.propai_orchestrator import PropAIOrchestrator

        irr = PropAIOrchestrator._calc_irr(
            investment=0,
            annual_income=10_000_000,
            terminal_value=50_000_000,
            years=5,
        )
        assert isinstance(irr, float)

    def test_irr_음수수익(self):
        from apps.api.agents.propai_orchestrator import PropAIOrchestrator

        irr = PropAIOrchestrator._calc_irr(
            investment=100_000_000,
            annual_income=1_000_000,
            terminal_value=10_000_000,
            years=3,
        )
        assert isinstance(irr, float)

    def test_irr_장기(self):
        from apps.api.agents.propai_orchestrator import PropAIOrchestrator

        irr = PropAIOrchestrator._calc_irr(
            investment=500_000_000,
            annual_income=50_000_000,
            terminal_value=600_000_000,
            years=10,
        )
        assert irr > 0


class TestOrchestratorInvestmentGrade:
    def test_grade_A(self):
        from apps.api.agents.propai_orchestrator import PropAIOrchestrator

        grade = PropAIOrchestrator._determine_investment_grade(
            npv=1_000_000_000, irr=0.20, permit_ready=True, jeonse_risk="SAFE",
        )
        assert grade == "A"

    def test_grade_B(self):
        from apps.api.agents.propai_orchestrator import PropAIOrchestrator

        grade = PropAIOrchestrator._determine_investment_grade(
            npv=500_000_000, irr=0.12, permit_ready=True, jeonse_risk="LOW",
        )
        assert grade in {"A", "B"}

    def test_grade_저조한_지표(self):
        from apps.api.agents.propai_orchestrator import PropAIOrchestrator

        grade = PropAIOrchestrator._determine_investment_grade(
            npv=-100_000_000, irr=0.01, permit_ready=False, jeonse_risk="CRITICAL",
        )
        assert grade in {"D", "E", "F"}

    def test_grade_중간(self):
        from apps.api.agents.propai_orchestrator import PropAIOrchestrator

        grade = PropAIOrchestrator._determine_investment_grade(
            npv=100_000_000, irr=0.08, permit_ready=True, jeonse_risk="MEDIUM",
        )
        assert grade in {"B", "C", "D"}


class TestOrchestratorInit:
    def test_init(self):
        from apps.api.agents.propai_orchestrator import PropAIOrchestrator

        orc = PropAIOrchestrator(db=AsyncMock())
        assert orc is not None


# ═══════════════════════════════════════════
# MolitClient (127 stmts, 74 missed)
# ═══════════════════════════════════════════


class TestMolitClientConstants:
    def test_trade_endpoints(self):
        from apps.api.integrations.molit_client import _TRADE_ENDPOINTS

        assert "apt" in _TRADE_ENDPOINTS
        assert len(_TRADE_ENDPOINTS) >= 3

    def test_rent_endpoints(self):
        from apps.api.integrations.molit_client import _RENT_ENDPOINTS

        assert "apt" in _RENT_ENDPOINTS
        assert len(_RENT_ENDPOINTS) >= 3


class TestMolitClientParsing:
    def test_parse_xml_with_regex(self):
        from apps.api.integrations.molit_client import MolitClient

        xml = """<response><body><items>
        <item><name>test</name><price>100</price></item>
        </items></body></response>"""
        items = MolitClient._parse_xml_with_regex(xml)
        assert isinstance(items, list)

    def test_extract_items_정상(self):
        from apps.api.integrations.molit_client import MolitClient

        data = {
            "response": {
                "body": {
                    "items": {
                        "item": [{"name": "a"}, {"name": "b"}]
                    }
                }
            }
        }
        items = MolitClient._extract_items(data)
        assert len(items) == 2

    def test_extract_items_단일항목(self):
        from apps.api.integrations.molit_client import MolitClient

        data = {
            "response": {
                "body": {
                    "items": {
                        "item": {"name": "a"}
                    }
                }
            }
        }
        items = MolitClient._extract_items(data)
        assert len(items) == 1

    def test_extract_items_빈응답(self):
        from apps.api.integrations.molit_client import MolitClient

        data = {"response": {"body": {"items": None}}}
        items = MolitClient._extract_items(data)
        assert items == []

    def test_parse_trade_items(self):
        from apps.api.integrations.molit_client import MolitClient

        client = MolitClient()
        data = {
            "response": {
                "body": {
                    "items": {
                        "item": [
                            {
                                "거래금액": " 85,000",
                                "전용면적": "84.5",
                                "년": "2025",
                                "월": "6",
                                "일": "15",
                                "층": "10",
                                "아파트": "래미안",
                                "법정동": "역삼동",
                            }
                        ]
                    }
                }
            }
        }
        items = client._parse_trade_items(data, "apt")
        assert len(items) == 1
        assert items[0]["prop_type"] == "apt"

    def test_parse_rent_items(self):
        from apps.api.integrations.molit_client import MolitClient

        client = MolitClient()
        data = {
            "response": {
                "body": {
                    "items": {
                        "item": [
                            {
                                "보증금액": " 50,000",
                                "월세금액": "0",
                                "전용면적": "84.5",
                                "년": "2025",
                                "월": "6",
                                "일": "10",
                                "아파트": "래미안",
                                "법정동": "역삼동",
                            }
                        ]
                    }
                }
            }
        }
        items = client._parse_rent_items(data)
        assert len(items) == 1

    def test_parse_permit_items(self):
        from apps.api.integrations.molit_client import MolitClient

        items = MolitClient._parse_permit_items([
            {"crtnDay": "20250615", "bldNm": "테스트빌딩", "mainPurpsCdNm": "아파트"},
        ])
        assert len(items) == 1
        assert items[0]["permit_date"] == "20250615"


class TestMolitClientInit:
    def test_init(self):
        from apps.api.integrations.molit_client import MolitClient

        client = MolitClient()
        assert client is not None


# ═══════════════════════════════════════════
# VWorldClient (99 stmts, 68 missed)
# ═══════════════════════════════════════════


class TestVWorldClientConstants:
    def test_facility_type_map(self):
        from apps.api.integrations.vworld_client import _FACILITY_TYPE_MAP

        assert isinstance(_FACILITY_TYPE_MAP, dict)
        assert len(_FACILITY_TYPE_MAP) >= 5


class TestVWorldClientFallbacks:
    def test_parcel_fallback(self):
        from apps.api.integrations.vworld_client import VWorldClient

        result = VWorldClient._parcel_fallback("1168010300", "test reason")
        assert result["pnu"] == "1168010300"
        assert result["error"] == "test reason"

    def test_land_use_fallback(self):
        from apps.api.integrations.vworld_client import VWorldClient

        result = VWorldClient._land_use_fallback("1168010300")
        assert result["pnu"] == "1168010300"
        assert "far_limit" in result

    def test_geocode_fallback(self):
        from apps.api.integrations.vworld_client import VWorldClient

        result = VWorldClient._geocode_fallback("서울 강남구")
        assert result["lat"] == 0.0
        assert result["lon"] == 0.0
        assert result["address"] == "서울 강남구"


class TestVWorldClientParsing:
    def test_extract_features_정상(self):
        from apps.api.integrations.vworld_client import VWorldClient

        client = VWorldClient()
        data = {
            "response": {
                "result": {
                    "featureCollection": {
                        "features": [
                            {"properties": {"a": 1}},
                            {"properties": {"b": 2}},
                        ]
                    }
                }
            }
        }
        features = client._extract_features(data)
        assert len(features) == 2

    def test_extract_features_빈응답(self):
        from apps.api.integrations.vworld_client import VWorldClient

        client = VWorldClient()
        features = client._extract_features({})
        assert features == []

    def test_parse_parcel_response(self):
        from apps.api.integrations.vworld_client import VWorldClient

        client = VWorldClient()
        data = {
            "response": {
                "result": {
                    "featureCollection": {
                        "features": [
                            {
                                "properties": {
                                    "pnu": "1168010300",
                                    "addr": "서울 강남구",
                                    "jiga": "15000000",
                                    "jimok": "대",
                                },
                            }
                        ]
                    }
                }
            }
        }
        result = client._parse_parcel_response(data, "1168010300")
        assert result["pnu"] == "1168010300"

    def test_parse_geocode_response(self):
        from apps.api.integrations.vworld_client import VWorldClient

        client = VWorldClient()
        data = {
            "response": {
                "status": "OK",
                "result": {
                    "point": {"x": "127.0", "y": "37.5"},
                },
            }
        }
        result = client._parse_geocode_response(data, "서울 강남구")
        assert result["lat"] == 37.5
        assert result["lon"] == 127.0

    def test_parse_underground_response(self):
        from apps.api.integrations.vworld_client import VWorldClient

        client = VWorldClient()
        data = {
            "response": {
                "result": {
                    "featureCollection": {
                        "features": [
                            {
                                "properties": {
                                    "faci_type": "GAS",
                                    "depth": "1.5",
                                    "pipe_size": "200",
                                },
                            },
                        ]
                    }
                }
            }
        }
        result = client._parse_underground_response(data)
        assert len(result) >= 1

    def test_parse_land_use_response(self):
        from apps.api.integrations.vworld_client import VWorldClient

        client = VWorldClient()
        data = {
            "response": {
                "result": {
                    "featureCollection": {
                        "features": [
                            {
                                "properties": {
                                    "uname": "제1종일반주거지역",
                                    "far_limit": "200",
                                    "bcr_limit": "60",
                                },
                            },
                        ]
                    }
                }
            }
        }
        result = client._parse_land_use_response(data, "1168010300")
        assert result["pnu"] == "1168010300"


class TestVWorldClientInit:
    def test_init(self):
        from apps.api.integrations.vworld_client import VWorldClient

        client = VWorldClient()
        assert client is not None


# ═══════════════════════════════════════════
# AssetIntelligenceService (89 stmts, 50 missed)
# ═══════════════════════════════════════════


class TestAssetIntelligenceGrade:
    def test_grade_A(self):
        from apps.api.services.asset_intelligence_service import AssetIntelligenceService

        assert AssetIntelligenceService._grade(85.0) == "A"

    def test_grade_B(self):
        from apps.api.services.asset_intelligence_service import AssetIntelligenceService

        assert AssetIntelligenceService._grade(72.0) == "B"

    def test_grade_C(self):
        from apps.api.services.asset_intelligence_service import AssetIntelligenceService

        assert AssetIntelligenceService._grade(62.0) == "C"

    def test_grade_D(self):
        from apps.api.services.asset_intelligence_service import AssetIntelligenceService

        assert AssetIntelligenceService._grade(50.0) == "D"

    def test_grade_E(self):
        from apps.api.services.asset_intelligence_service import AssetIntelligenceService

        assert AssetIntelligenceService._grade(30.0) == "E"


class TestAssetIntelligenceCapex:
    def test_capex_plan_높은_점수(self):
        from apps.api.services.asset_intelligence_service import AssetIntelligenceService

        plan = AssetIntelligenceService._capex_plan({
            "maintenance": 90,
            "tenant": 85,
            "market": 80,
            "climate": 75,
        })
        assert isinstance(plan, list)
        assert len(plan) >= 1

    def test_capex_plan_낮은_점수(self):
        from apps.api.services.asset_intelligence_service import AssetIntelligenceService

        plan = AssetIntelligenceService._capex_plan({
            "maintenance": 30,
            "tenant": 25,
            "market": 20,
            "climate": 15,
        })
        assert isinstance(plan, list)
        # 낮은 점수 → 더 많은 투자 권장
        assert len(plan) >= 1


class TestAssetIntelligenceAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_기본(self):
        from apps.api.services.asset_intelligence_service import AssetIntelligenceService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # _latest_* 메서드 mock (모두 None → 기본값 사용)
        svc = AssetIntelligenceService(db=mock_db)
        with patch.object(svc, "_latest_alert", return_value=None), \
             patch.object(svc, "_latest_tenant_health", return_value=None), \
             patch.object(svc, "_latest_climate", return_value=None), \
             patch.object(svc, "_latest_avm", return_value=None):
            snapshot, capex_list = await svc.analyze(
                tenant_id=TEST_TENANT_ID,
                project_id=TEST_PROJECT_ID,
                base_value_krw=10_000_000_000,
                maintenance_score=75.0,
                tenant_score=80.0,
                market_score=70.0,
                climate_score=65.0,
            )
        assert snapshot is not None
        assert isinstance(capex_list, list)


# ═══════════════════════════════════════════
# AuctionService (70 stmts, 27 missed)
# ═══════════════════════════════════════════


class TestAuctionAnalysisSnapshot:
    def test_snapshot_기본(self):
        from apps.api.services.auction_service import AuctionService

        result = AuctionService._analysis_snapshot(
            appraised_value_krw=500_000_000,
            minimum_bid_krw=350_000_000,
            bid_count=3,
            occupancy_status="vacant",
            senior_lien_exists=False,
            expected_repair_cost_krw=10_000_000,
            nearby_market_price_krw=600_000_000,
        )
        assert "investment_score" in result
        assert "discount_ratio" in result
        assert "recommended_max_bid_krw" in result
        assert result["discount_ratio"] == 0.30  # (500M - 350M) / 500M

    def test_snapshot_선순위_있음(self):
        from apps.api.services.auction_service import AuctionService

        result = AuctionService._analysis_snapshot(
            appraised_value_krw=500_000_000,
            minimum_bid_krw=350_000_000,
            bid_count=5,
            occupancy_status="occupied",
            senior_lien_exists=True,
            expected_repair_cost_krw=50_000_000,
            nearby_market_price_krw=None,
        )
        assert result["investment_score"] < 100
        flags = result.get("diligence_flags", [])
        assert any("선순위" in str(f) or "lien" in str(f).lower() for f in flags)

    def test_snapshot_유찰_많음(self):
        from apps.api.services.auction_service import AuctionService

        result = AuctionService._analysis_snapshot(
            appraised_value_krw=300_000_000,
            minimum_bid_krw=150_000_000,
            bid_count=0,
            occupancy_status="vacant",
            senior_lien_exists=False,
            expected_repair_cost_krw=0,
            nearby_market_price_krw=350_000_000,
        )
        assert result["discount_ratio"] == 0.50  # 50% 할인

    def test_snapshot_점유상태_occupied(self):
        from apps.api.services.auction_service import AuctionService

        result = AuctionService._analysis_snapshot(
            appraised_value_krw=400_000_000,
            minimum_bid_krw=300_000_000,
            bid_count=2,
            occupancy_status="occupied",
            senior_lien_exists=False,
            expected_repair_cost_krw=5_000_000,
            nearby_market_price_krw=450_000_000,
        )
        assert result["investment_score"] >= 0


class TestAuctionServiceAsync:
    @pytest.mark.asyncio
    async def test_analyze_and_store(self):
        from apps.api.services.auction_service import AuctionService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        # 기존 listing 없음
        mock_db.scalar = AsyncMock(return_value=None)

        svc = AuctionService(db=mock_db)
        listing = await svc.analyze_and_store(
            tenant_id=TEST_TENANT_ID,
            project_id=TEST_PROJECT_ID,
            auction_type="forced",
            case_number="2025타경12345",
            court_name="서울중앙지방법원",
            address="서울 강남구 역삼동 123-45",
            property_type="apartment",
            appraised_value_krw=500_000_000,
            minimum_bid_krw=350_000_000,
            bid_count=2,
            auction_date=datetime(2025, 6, 15, 10, 0),
            occupancy_status="vacant",
            senior_lien_exists=False,
            expected_repair_cost_krw=10_000_000,
            nearby_market_price_krw=550_000_000,
        )
        assert listing is not None
        mock_db.add.assert_called()


# ═══════════════════════════════════════════
# WebRTC Router (113 stmts, 70 missed)
# ═══════════════════════════════════════════


class TestWebRTCConstants:
    def test_ice_constants(self):
        from apps.api.routers.webrtc import _ICE_BASE_DELAY_SEC, _ICE_MAX_RETRIES

        assert _ICE_MAX_RETRIES == 3
        assert _ICE_BASE_DELAY_SEC == 0.5
