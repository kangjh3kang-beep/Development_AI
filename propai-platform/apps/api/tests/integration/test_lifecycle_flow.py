"""PropAI v58 라이프사이클 흐름 통합 테스트."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestLifecycleFlow:

    def test_asset_valuation_to_maintenance(self, sample_project):
        """자산 평가 -> 유지보수 계획 수립."""
        from app.services.lifecycle.asset.asset_service import AssetService
        from app.services.lifecycle.maintenance.maintenance_service import MaintenanceService

        asset = AssetService()
        valuation = asset.valuate_asset(
            {"area_sqm": 25000, "comparables": [{"price": 3000000}]},
            "comparison",
        )
        assert "value" in valuation
        assert valuation["method"] == "comparison"

        maint = MaintenanceService()
        plan = maint.create_plan(sample_project["project_id"])
        assert "components" in plan
        assert plan["total_components"] > 0

    def test_maintenance_to_operations(self, sample_project):
        """유지보수 -> 운영 관리 연동."""
        from app.services.lifecycle.maintenance.maintenance_service import MaintenanceService
        from app.services.lifecycle.operations.operations_service import OperationsService

        maint = MaintenanceService()
        plan = maint.create_plan(sample_project["project_id"])
        schedule = maint.schedule_maintenance(plan)
        assert isinstance(schedule, list)
        assert len(schedule) > 0

        ops = OperationsService()
        log = ops.log_operation(
            sample_project["project_id"],
            "maintenance",
            {"description": "엘리베이터 정기점검 완료", "cost": 2_000_000},
        )
        assert log["log_type"] == "maintenance"
        assert log["project_id"] == sample_project["project_id"]

    def test_occupancy_to_operations(self, sample_project):
        """입주 관리 -> 운영비 분석."""
        from app.services.lifecycle.occupancy.occupancy_service import OccupancyService
        from app.services.lifecycle.operations.operations_service import OperationsService

        occupancy = OccupancyService()
        tenant = occupancy.register_tenant(
            "UNIT-101",
            {"name": "테스트 임차인", "monthly_rent": 3_000_000, "deposit": 50_000_000},
        )
        assert "unit_id" in tenant
        assert tenant["unit_id"] == "UNIT-101"

        units = [
            {"status": "active"} for _ in range(120)
        ] + [{"status": "vacant"} for _ in range(30)]
        rate = occupancy.calculate_occupancy_rate(units)
        assert "occupancy_rate" in rate
        assert rate["occupancy_rate"] == pytest.approx(80.0, abs=0.1)

        ops = OperationsService()
        logs = [
            {"log_type": "maintenance", "cost": 2000000},
            {"log_type": "utility", "cost": 5000000},
        ]
        costs = ops.calculate_operating_costs(logs)
        assert "total_cost" in costs
        assert costs["total_cost"] == 7_000_000

    def test_operations_to_sales(self, sample_project):
        """운영 -> 매각/ROI 분석."""
        from app.services.lifecycle.operations.operations_service import OperationsService
        from app.services.lifecycle.sales.sales_service import SalesService

        ops = OperationsService()
        logs = [{"log_type": "maintenance", "cost": 500000}]
        report = ops.generate_operations_report(sample_project["project_id"], logs)
        assert "project_id" in report
        assert report["project_id"] == sample_project["project_id"]

        sales = SalesService()
        roi = sales.calculate_roi(
            purchase_price=80_000_000_000,
            sale_price=120_000_000_000,
            holding_years=5,
            total_costs=10_000_000_000,
        )
        assert "roi_pct" in roi
        assert roi["roi_pct"] > 0
        assert roi["net_profit"] == 30_000_000_000

    def test_special_project_evaluation(self):
        """특수 사업 (재건축/리모델링) 평가."""
        from app.services.lifecycle.special.special_project_service import SpecialProjectService

        special = SpecialProjectService()
        reconstruction = special.evaluate_reconstruction(
            {"age_years": 35, "safety_grade": "D"},
        )
        assert "reconstruction_eligible" in reconstruction
        assert reconstruction["reconstruction_eligible"] is True
        assert reconstruction["safety_grade"] == "D"

        remodeling = special.plan_remodeling(
            {"original_cost": 80_000_000_000, "area_sqm": 25000},
            "structural",
        )
        assert "estimated_cost" in remodeling
        assert remodeling["scope"] == "structural"

    def test_full_lifecycle_data_consistency(self, sample_project):
        """전체 라이프사이클 데이터 일관성 검증."""
        from app.services.lifecycle.asset.asset_service import AssetService
        from app.services.lifecycle.maintenance.maintenance_service import MaintenanceService
        from app.services.lifecycle.occupancy.occupancy_service import OccupancyService
        from app.services.lifecycle.operations.operations_service import OperationsService
        from app.services.lifecycle.sales.sales_service import SalesService
        from app.services.lifecycle.special.special_project_service import SpecialProjectService

        pid = sample_project["project_id"]

        asset_val = AssetService().valuate_asset(
            {"annual_income": 5_000_000_000, "cap_rate": 0.05}, "income"
        )
        assert asset_val["method"] == "income"
        assert asset_val["value"] > 0

        maint_plan = MaintenanceService().create_plan(pid)
        assert maint_plan["project_id"] == pid

        tenant = OccupancyService().register_tenant("U1", {"name": "A", "monthly_rent": 1000000})
        assert tenant["unit_id"] == "U1"

        ops_log = OperationsService().log_operation(pid, "inspection", {"description": "정기점검"})
        assert ops_log["project_id"] == pid

        sale = SalesService().record_sale(
            {"unit_id": "U1"},
            {"type": "resale", "price": 600000000, "buyer_type": "corporate"},
        )
        assert sale["unit_id"] == "U1"

        special_eval = SpecialProjectService().evaluate_reconstruction(
            {"age_years": 40, "safety_grade": "E"},
        )
        assert special_eval["reconstruction_eligible"] is True

    def test_depreciation_tracking(self):
        """감가상각 추적."""
        from app.services.lifecycle.asset.asset_service import AssetService

        asset = AssetService()
        depreciation = asset.track_depreciation("building", 80_000_000_000, 10)
        assert "accumulated_depreciation" in depreciation
        assert "book_value" in depreciation
        assert depreciation["book_value"] < 80_000_000_000
        expected = 80_000_000_000 * 0.025 * 10
        assert depreciation["accumulated_depreciation"] == expected

    def test_maintenance_cost_analysis(self):
        """유지보수 비용 분석."""
        from app.services.lifecycle.maintenance.maintenance_service import MaintenanceService

        maint = MaintenanceService()
        records = [
            {"cost": 2_000_000},
            {"cost": 3_000_000},
            {"cost": 1_500_000},
        ]
        costs = maint.calculate_costs(records, 12)
        assert "total_cost" in costs
        assert costs["total_cost"] == 6_500_000
        assert costs["period_months"] == 12

