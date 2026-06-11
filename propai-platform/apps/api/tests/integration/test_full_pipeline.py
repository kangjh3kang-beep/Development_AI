"""PropAI v58 전체 파이프라인 통합 테스트."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeAsyncDb:
    """raw SQL 순차 호출에 사전 정의된 행을 차례로 반환하는 AsyncSession 대역.

    project_dashboard 계열 엔드포인트는 raw SQL + .first()만 사용하므로
    실제 DB 없이 호출 순서대로 행을 주입해 결정론 테스트가 가능하다.
    """

    def __init__(self, rows):
        self._rows = list(rows)

    async def execute(self, *args, **kwargs):
        return _FakeResult(self._rows.pop(0) if self._rows else None)


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

    def test_orchestrator_canonical_only(self):
        """정본 오케스트레이터(propai_orchestrator)만 유지 — 스텁 3본 청산 (WP-11)."""
        import importlib.util
        import inspect

        from apps.api.agents.propai_orchestrator import PropAIOrchestrator

        assert hasattr(PropAIOrchestrator, "run")

        # 청산 대상 스텁 모듈 잔존 0건 (삭제 검증 계약)
        for mod in (
            "app.services.agents.orchestrator",        # '인허가 자동 신청 완료' 허위 스텁
            "app.routers.agents",                      # 미마운트 중복 라우터
            "apps.api.agents.langgraph_orchestrator",  # 하드코딩 결과 스텁 그래프
        ):
            assert importlib.util.find_spec(mod) is None, f"{mod} 미삭제 — 스텁 잔존"

        # project_dashboard가 스텁 오케스트레이터를 더 이상 참조하지 않음
        from app.routers import project_dashboard

        src = inspect.getsource(project_dashboard)
        assert "services.agents.orchestrator" not in src

    async def test_simulate_feasibility_project_not_found(self):
        """simulate-feasibility: 프로젝트 미존재 시 404 정직 응답 (WP-11)."""
        from fastapi import HTTPException
        from app.routers import project_dashboard as pd_router

        db = _FakeAsyncDb([None])
        with pytest.raises(HTTPException) as exc:
            await pd_router.run_feasibility_simulation("wp11-missing", db=db)
        assert exc.value.status_code == 404

    async def test_simulate_feasibility_no_overview_returns_no_data(self):
        """건축개요(연면적) 미확정 시 가짜 1.28B 폴백 대신 no_data 정직 응답 (WP-11)."""
        from app.routers import project_dashboard as pd_router

        proj_row = ("apartment", None, 0, 0, None)  # 연면적·설계 모두 없음
        db = _FakeAsyncDb([proj_row, None])
        res = await pd_router.run_feasibility_simulation("wp11-test-project", db=db)

        assert res["status"] == "no_data"
        assert res["results"] is None
        assert res["project_id"] == "wp11-test-project"

    async def test_simulate_feasibility_real_calculation(self, monkeypatch):
        """simulate-feasibility 실계산 계약 — 고정 시드 몬테카를로 + 출처 표기 (WP-11)."""
        from app.routers import project_dashboard as pd_router
        from app.services.cost.unit_price_repository import UnitPriceRepository
        from app.services.finance.monte_carlo_service import MonteCarloService

        async def _no_db_prices(self):
            return None  # DB 미접속 환경 — estimator가 동기 fallback 단가로 회귀

        monkeypatch.setattr(UnitPriceRepository, "get_prices", _no_db_prices)

        # GFA 10,000㎡ / 지상 10층·지하 2층 / 강남구 주소(시세 테이블 5,500만원/평)
        proj_row = ("apartment", 10000, 10, 2, "서울특별시 강남구 역삼동 123-45")
        db = _FakeAsyncDb([proj_row, None])
        res = await pd_router.run_feasibility_simulation("wp11-test-project", db=db)

        assert res["status"] == "success"
        r = res["results"]
        # 프론트 계약 키(FeasibilitySimulationWidget) + 구 응답 키 하위호환
        for key in ("npv_mean_krw", "var_5_krw", "profitability_index",
                    "roi_percent", "value_at_risk_5"):
            assert key in r
        # 구 스텁의 가짜 고정값(1.28B / 'LangGraph ... Persisted') 미사용
        assert r["npv_mean_krw"] != 1_280_000_000
        assert "LangGraph" not in r["message"]

        inputs = r["inputs"]
        # 분양가: 강남구 시세 테이블 고정값(regional_pricing 단일출처)
        assert inputs["sale_price_per_pyeong_won"] == 55_000_000
        assert inputs["sale_price_source"] == "regional_market_table"
        assert inputs["cost_source"] == "estimate_overview"
        assert inputs["efficiency_pct_assumed"] == 75.0
        # 수입 = GFA(평) × 전용률 75% × 평당 분양가 — 고정 수치
        expected_revenue = 10000 / 3.305785 * (75.0 / 100.0) * float(55_000_000)
        assert inputs["expected_revenue_krw"] == int(expected_revenue)
        # 표준공기: 6 + 10×0.55 + 2×1.0 = 13.5개월 → 반올림 14
        assert inputs["construction_period_months"] == 14
        assert inputs["total_cost_krw"] > 0

        # 결정론 재현: 동일 입력으로 실 MonteCarloService(시드 42) 재실행 결과와 일치
        mc = MonteCarloService().run_simulation(
            total_cost_krw=float(inputs["total_cost_krw"]),
            expected_revenue_krw=expected_revenue,
            construction_period_months=inputs["construction_period_months"],
        )
        assert r["npv_mean_krw"] == int(mc["npv_mean_krw"])
        assert r["npv_std_krw"] == int(mc["npv_std_krw"])
        assert r["probability_positive_npv"] == mc["probability_positive_npv"]
        # VaR(5%) = 평균 − 1.645σ (정규근사), 구 키와 동일값
        assert r["var_5_krw"] == int(int(mc["npv_mean_krw"]) - 1.645 * int(mc["npv_std_krw"]))
        assert r["value_at_risk_5"] == r["var_5_krw"]
        # PI = (NPV + 총공사비)/총공사비, ROI = NPV/총공사비 × 100
        cost = float(inputs["total_cost_krw"])
        assert r["profitability_index"] == round((r["npv_mean_krw"] + cost) / cost, 4)
        assert r["roi_percent"] == round(r["npv_mean_krw"] / cost * 100, 2)

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

