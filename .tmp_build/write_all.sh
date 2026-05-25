#!/bin/bash
set -e

BASE="/home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/api/tests/integration"

cat > "/test_full_pipeline.py" << 'PYEOF1'
"""PropAI v58 전체 파이프라인 통합 테스트.

프로젝트 생성 → AVM 평가 → 사업성 분석 → 설계 → 인허가 → 시공 → 입주
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestProjectLifecyclePipeline:
    """프로젝트 전주기 파이프라인 통합 테스트."""

    def test_avm_to_feasibility_flow(self, sample_project):
        """AVM 평가 → 사업 타당성 분석 연동."""
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
        """설계 AI → CAD 파라메트릭 편집 연동."""
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
        """인허가 → 착공 연동."""
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
        """BIM 모델 → 에너지 시뮬레이션 연동."""
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
            "insulation_grade": "중",
        })
        assert "annual_energy_kwh" in simulation
        assert simulation["annual_energy_kwh"] > 0
