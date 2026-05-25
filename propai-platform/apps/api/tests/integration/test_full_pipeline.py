"""PropAI v58 전체 파이프라인 통합 테스트."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestProjectLifecyclePipeline:

    def test_avm_to_feasibility_flow(self, sample_project):
        """AVM 평가 -> 사업 타당성 분석 연동."""
        from app.services.avm.avm_service import AVMService
        from app.services.planning.feasibility_service import FeasibilityService

        avm = AVMService()
        comparables = [
            {"lat": 37.5665, "lon": 126.9780, "price_per_sqm": 12000000},
            {"lat": 37.5700, "lon": 126.9800, "price_per_sqm": 11500000},
            {"lat": 37.5630, "lon": 126.9750, "price_per_sqm": 12500000},
        ]
        features = {"latitude": 37.5665, "longitude": 126.978, "area_sqm": 100}
        avm_result = avm.estimate_value(features, comparables)
        assert "estimated_value_per_sqm" in avm_result
        estimated_price = avm_result["estimated_value_per_sqm"]
        assert estimated_price > 0

        feasibility = FeasibilityService()
        study = feasibility.run_feasibility_study(
            sample_project["project_id"],
            {
                "total_investment": sample_project["budget_krw"],
                "expected_revenue": estimated_price * sample_project["total_floor_area_sqm"],
                "discount_rate": 0.08,
                "period_years": 5,
            },
        )
        assert "irr" in study
        assert "npv" in study
        assert "payback_years" in study
        assert study["project_id"] == sample_project["project_id"]

    def test_design_to_cad_flow(self, sample_project):
        """설계 AI -> CAD 파라메트릭 편집 연동."""
        from app.services.design.cnn_design_service import CNNDesignService
        from app.services.cad.parametric_cad_service import ParametricCADService

        design = CNNDesignService()
        features = design.extract_features(b"fake_image_bytes")
        assert "dominant_style" in features
        assert "feature_vector" in features

        cad = ParametricCADService()
        dxf_bytes = cad.create_floor_plan_dxf(
            building_width_m=40.0,
            building_depth_m=20.0,
            floor_count=sample_project["floors_above"],
        )
        assert isinstance(dxf_bytes, bytes)
        assert len(dxf_bytes) > 0

    def test_permit_to_construction_flow(self, sample_project):
        """인허가 -> 착공 연동."""
        from app.services.permit.permit_service import PermitService
        from app.services.lifecycle.construction.construction_start_service import ConstructionStartService

        permit = PermitService()
        requirements = permit.check_requirements("building")
        assert "missing" in requirements
        assert requirements["required_count"] > 0

        construction = ConstructionStartService()
        checklist = construction.generate_checklist(
            sample_project["project_type"],
            sample_project["budget_krw"],
        )
        assert "required_items" in checklist
        assert checklist["safety_plan_required"] is True

    def test_bim_to_energy_flow(self, sample_project):
        """BIM 모델 -> 에너지 시뮬레이션 연동."""
        from app.services.bim.bim_service import BIMService
        from app.services.energy.energy_service import EnergyService

        bim = BIMService()
        metadata = bim.parse_ifc_metadata("/fake/path/model.ifc")
        assert "schema" in metadata

        quantities = bim.extract_quantities([
            {"element_type": "wall", "quantity": 500},
            {"element_type": "slab", "quantity": 300},
        ])
        assert "quantities" in quantities
        assert quantities["element_count"] == 2

        energy = EnergyService()
        simulation = energy.simulate_energy({
            "total_area_sqm": sample_project["total_floor_area_sqm"],
            "floors": sample_project["floors_above"],
        })
        assert "annual_energy_kwh" in simulation
        assert simulation["annual_energy_kwh"] > 0

    def test_housing_to_sales_flow(self, sample_project):
        """분양 -> 매각 연동."""
        from app.services.housing.housing_service import HousingService
        from app.services.lifecycle.sales.sales_service import SalesService

        housing = HousingService()
        units = housing.create_units(
            sample_project["project_id"],
            {"59A": 100, "84A": 50},
        )
        assert isinstance(units, list)
        assert len(units) == 150

        sales = SalesService()
        sale_record = sales.record_sale(
            {"unit_id": "UNIT-001"},
            {"type": "initial", "price": 500_000_000, "buyer_type": "individual"},
        )
        assert "unit_id" in sale_record
        assert sale_record["sale_price"] == 500_000_000

    def test_contract_to_payment_flow(self, sample_project):
        """계약 -> 기성금 지급 연동."""
        from app.services.contract.contract_service import ContractService

        contract = ContractService()
        new_contract = contract.create_contract(
            sample_project["project_id"],
            "construction",
            {
                "contractor_name": "테스트건설(주)",
                "amount": 60_000_000_000,
            },
        )
        assert "contract_type" in new_contract
        assert new_contract["contractor_name"] == "테스트건설(주)"

        payments = contract.schedule_payments(
            60_000_000_000,
            [
                {"name": "착공금", "pct": 10, "due_date": "2026-04-01"},
                {"name": "1차기성", "pct": 30, "due_date": "2026-10-01"},
                {"name": "2차기성", "pct": 30, "due_date": "2027-04-01"},
                {"name": "잔금", "pct": 30, "due_date": "2027-10-01"},
            ],
        )
        assert isinstance(payments, list)
        assert len(payments) == 4
        assert payments[0]["amount"] == 6_000_000_000

    def test_orchestrator_multi_node_pipeline(self):
        """오케스트레이터 다중 노드 파이프라인."""
        from app.services.agents.orchestrator import OrchestratorService

        orch = OrchestratorService()
        assert hasattr(orch, "run_pipeline") or hasattr(orch, "execute")

    def test_regulation_monitoring_flow(self, sample_project):
        """법규 모니터링 -> 영향 분석."""
        from app.services.regulation_monitor.regulation_monitor import RegulationMonitorService

        monitor = RegulationMonitorService()
        changes = monitor.check_for_changes()
        assert isinstance(changes, list)
        assert len(changes) >= 1

        impact = monitor.assess_impact(
            {"project_id": sample_project["project_id"]},
            changes,
        )
        assert "changes_detected" in impact
        assert "impacts" in impact
        assert impact["changes_detected"] == len(changes)

    def test_spatial_to_avm_flow(self, sample_project):
        """공간 쿼리 -> AVM 연동."""
        from app.services.spatial.spatial_service import SpatialService
        from app.services.avm.avm_service import AVMService

        spatial = SpatialService()
        lat = sample_project["location"]["latitude"]
        lon = sample_project["location"]["longitude"]
        nearby = spatial.find_nearby_projects(lat, lon, 2.0, [
            {"project_id": "P1", "lat": 37.568, "lon": 126.979, "name": "A"},
            {"project_id": "P2", "lat": 37.600, "lon": 127.000, "name": "B"},
        ])
        assert len(nearby) >= 1

        avm = AVMService()
        result = avm.estimate_value(
            {"latitude": lat, "longitude": lon, "area_sqm": 100},
            [{"lat": 37.568, "lon": 126.979, "price_per_sqm": 12000000}],
        )
        assert "estimated_value_per_sqm" in result

    def test_end_to_end_pipeline_completeness(self):
        """전체 파이프라인 서비스 임포트 및 초기화 검증."""
        from app.services.avm.avm_service import AVMService
        from app.services.legal.alris_service import ALRISService
        from app.services.design.cnn_design_service import CNNDesignService
        from app.services.cad.parametric_cad_service import ParametricCADService
        from app.services.finance.monte_carlo_service import MonteCarloService
        from app.services.esg.lca.lca_service import LCAService
        from app.services.esg.lcc.lcc_service import LCCService
        from app.services.bim.bim_service import BIMService
        from app.services.permit.permit_service import PermitService
        from app.services.energy.energy_service import EnergyService
        from app.services.contract.contract_service import ContractService
        from app.services.planning.feasibility_service import FeasibilityService
        from app.services.housing.housing_service import HousingService
        from app.services.esg.re100.re100_service import RE100Service
        from app.services.esg.zeb.zeb_service import ZEBService
        from app.services.lifecycle.asset.asset_service import AssetService
        from app.services.lifecycle.maintenance.maintenance_service import MaintenanceService
        from app.services.lifecycle.occupancy.occupancy_service import OccupancyService
        from app.services.lifecycle.operations.operations_service import OperationsService
        from app.services.lifecycle.sales.sales_service import SalesService
        from app.services.lifecycle.special.special_project_service import SpecialProjectService

        services = [
            AVMService(), ALRISService(), CNNDesignService(), ParametricCADService(),
            MonteCarloService(), LCAService(), LCCService(), BIMService(),
            PermitService(), EnergyService(), ContractService(), FeasibilityService(),
            HousingService(), RE100Service(), ZEBService(), AssetService(),
            MaintenanceService(), OccupancyService(), OperationsService(),
            SalesService(), SpecialProjectService(),
        ]
        assert len(services) == 21
        for svc in services:
            assert svc is not None

