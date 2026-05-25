"""PropAI v58 ESG 통합 흐름 테스트."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestESGIntegrationFlow:

    def test_lca_to_lcc_flow(self, sample_project):
        from app.services.esg.lca.lca_service import LCAService
        from app.services.esg.lcc.lcc_service import LCCService

        lca = LCAService()
        materials = [
            {"name": "concrete_35mpa", "quantity_kg": 800000},
            {"name": "rebar_sd400", "quantity_kg": 120000},
        ]
        lca_result = lca.calculate_a1_a3(materials)
        assert "total_gwp_kgco2eq" in lca_result
        assert lca_result["total_gwp_kgco2eq"] > 0

        lcc = LCCService()
        lcc_result = lcc.calculate_lcc({
            "initial_cost_krw": sample_project["budget_krw"],
            "annual_maintenance_krw": 1_200_000_000,
            "annual_energy_krw": 500_000_000,
            "disposal_cost_krw": 2_000_000_000,
            "analysis_period_years": 30,
        })
        assert "total_lcc_npv_krw" in lcc_result
        assert lcc_result["total_lcc_npv_krw"] > sample_project["budget_krw"]

    def test_lca_to_epd_flow(self):
        from app.services.esg.lca.lca_service import LCAService
        from app.services.esg.epd.epd_carbon_service import EPDCarbonService

        lca = LCAService()
        lca_result = lca.calculate_a1_a3([
            {"name": "concrete_35mpa", "quantity_kg": 800000},
            {"name": "rebar_sd400", "quantity_kg": 120000},
        ])
        assert lca_result["total_gwp_kgco2eq"] > 0

        epd = EPDCarbonService()
        epd_result = epd.calculate_material_carbon([
            {"name": "레미콘_35MPa", "quantity_kg": 800000},
            {"name": "철근_SD400", "quantity_kg": 120000},
            {"name": "EPS단열재", "quantity_kg": 8000},
        ])
        assert "total_gwp_kgco2eq" in epd_result
        assert epd_result["total_gwp_kgco2eq"] > 0
        assert epd_result["materials_assessed"] == 3

    def test_energy_to_zeb_flow(self, sample_project):
        from app.services.energy.energy_service import EnergyService
        from app.services.esg.zeb.zeb_service import ZEBService

        energy = EnergyService()
        sim = energy.simulate_energy({
            "total_area_sqm": sample_project["total_floor_area_sqm"],
            "floors": sample_project["floors_above"],
        })
        assert "annual_energy_kwh" in sim
        energy_per_sqm = sim["energy_per_sqm_kwh"]

        zeb = ZEBService()
        grade = zeb.evaluate_zeb_grade({
            "primary_energy_kwh_sqm_yr": energy_per_sqm,
            "renewable_generation_kwh_sqm_yr": energy_per_sqm * 0.5,
        })
        assert "grade" in grade
        assert "energy_independence_pct" in grade

    def test_re100_tracking_flow(self):
        from app.services.esg.re100.re100_service import RE100Service

        re100 = RE100Service()
        tracking = re100.track_renewable_energy(2_000_000, 600_000)
        assert "renewable_pct" in tracking
        assert tracking["renewable_pct"] == pytest.approx(30.0, abs=0.1)
        assert tracking["gap_kwh"] == 1_400_000

        progress = re100.calculate_re100_progress([
            {"year": 2023, "renewable_pct": 20.0},
            {"year": 2024, "renewable_pct": 30.0},
        ])
        assert "trend" in progress
        assert progress["trend"] == "증가"
        assert progress["latest_pct"] == 30.0

    def test_zeb_envelope_optimization(self):
        from app.services.esg.zeb.zeb_service import ZEBService

        zeb = ZEBService()
        improvements = zeb.optimize_envelope({
            "u_wall": 0.21,
            "u_window": 1.5,
            "airtightness_ach": 3.0,
        })
        assert isinstance(improvements, list)
        assert len(improvements) >= 2

    def test_full_esg_assessment(self):
        from app.services.esg.lca.lca_service import LCAService
        from app.services.esg.lcc.lcc_service import LCCService
        from app.services.esg.epd.epd_carbon_service import EPDCarbonService
        from app.services.esg.re100.re100_service import RE100Service
        from app.services.esg.zeb.zeb_service import ZEBService

        carbon = LCAService().calculate_a1_a3([
            {"name": "concrete_35mpa", "quantity_kg": 800000},
            {"name": "rebar_sd400", "quantity_kg": 120000},
        ])
        assert carbon["total_gwp_kgco2eq"] > 0

        cost = LCCService().calculate_lcc({
            "initial_cost_krw": 80_000_000_000,
            "annual_maintenance_krw": 1_200_000_000,
            "annual_energy_krw": 500_000_000,
            "disposal_cost_krw": 2_000_000_000,
        })
        assert cost["total_lcc_npv_krw"] > 0

        epd_result = EPDCarbonService().calculate_material_carbon([
            {"name": "레미콘_35MPa", "quantity_kg": 800000},
        ])
        assert epd_result["total_gwp_kgco2eq"] > 0

        re100_result = RE100Service().track_renewable_energy(2_000_000, 600_000)
        assert re100_result["renewable_pct"] > 0

        zeb_result = ZEBService().evaluate_zeb_grade({
            "primary_energy_kwh_sqm_yr": 100.0,
            "renewable_generation_kwh_sqm_yr": 50.0,
        })
        assert "grade" in zeb_result

        esg_summary = {
            "embodied_carbon_kg": carbon["total_gwp_kgco2eq"],
            "lifecycle_cost_krw": cost["total_lcc_npv_krw"],
            "gwp_kg_co2eq": epd_result["total_gwp_kgco2eq"],
            "renewable_energy_pct": re100_result["renewable_pct"],
            "zeb_grade": zeb_result["grade"],
        }
        assert all(v is not None for v in esg_summary.values())

    def test_lcc_sensitivity_analysis(self):
        from app.services.esg.lcc.lcc_service import LCCService

        lcc = LCCService()
        base = {
            "initial_cost_krw": 80_000_000_000,
            "annual_maintenance_krw": 1_200_000_000,
            "annual_energy_krw": 500_000_000,
            "disposal_cost_krw": 2_000_000_000,
            "analysis_period_years": 30,
            "discount_rate_nominal": 0.045,
            "inflation_rate": 0.025,
        }
        base_result = lcc.calculate_lcc(base)
        high_dr = {**base, "discount_rate_nominal": 0.08}
        high_dr_result = lcc.calculate_lcc(high_dr)
        assert high_dr_result["maintenance_npv_krw"] < base_result["maintenance_npv_krw"]

    def test_digital_twin_esg_integration(self):
        from app.services.digital_twin.realtime_optimizer import RealtimeOptimizer

        optimizer = RealtimeOptimizer()
        hvac = optimizer.optimize_hvac(26.0, 22.0, 50)
        assert "mode" in hvac
        assert "power_pct" in hvac
        assert hvac["current_temp"] == 26.0
        assert hvac["target_temp"] == 22.0

    def test_monte_carlo_risk_flow(self, sample_project):
        from app.services.finance.monte_carlo_service import MonteCarloService

        mc = MonteCarloService(seed=42)
        result = mc.run_simulation({
            "initial_investment": sample_project["budget_krw"],
            "revenue_mean": 2_000_000_000,
            "revenue_std": 400_000_000,
            "cost_mean": 800_000_000,
            "cost_std": 160_000_000,
            "project_years": 5,
        }, iterations=500)
        assert "mean_npv" in result
        assert "positive_npv_pct" in result
        assert 0 <= result["positive_npv_pct"] <= 100

    def test_re100_source_recommendation(self):
        from app.services.esg.re100.re100_service import RE100Service

        re100 = RE100Service()
        sources = re100.recommend_sources(1_400_000)
        assert isinstance(sources, list)
        assert len(sources) > 0
        for src in sources:
            assert "source" in src
            assert "annual_cost_krw" in src

    def test_epd_low_carbon_alternatives(self):
        from app.services.esg.epd.epd_carbon_service import EPDCarbonService

        epd = EPDCarbonService()
        result = epd.recommend_low_carbon_alternatives("구조용강재_H형강")
        assert isinstance(result, dict)
        for alt in result["alternatives"]:
            assert alt["gwp"] < 1.53
