"""시공/ESG AI 서비스 단위 테스트.

Step 2.2 품질 게이트:
1. generate_construction_schedule: CPM 기반 13공정 일정 검증
2. calculate_carbon_emission: 자재/장비/전력 탄소 배출 산정 검증
3. estimate_zeb_energy: ZEB 에너지 시뮬레이션 검증
"""

from apps.api.services.construction_ai_service import ConstructionAIService

# ──────────────────────────────────────
# generate_construction_schedule 검증
# ──────────────────────────────────────


class TestConstructionSchedule:
    """CPM 기반 13공정 시공 일정 검증."""

    def _make_service(self) -> ConstructionAIService:
        return ConstructionAIService.__new__(ConstructionAIService)

    def test_returns_13_phases(self) -> None:
        """일정에 13개 공정이 포함된다."""
        svc = self._make_service()
        result = svc.generate_construction_schedule(10_000.0)
        assert len(result["schedule"]) == 13

    def test_total_duration_positive(self) -> None:
        """총 소요일이 양수이다."""
        svc = self._make_service()
        result = svc.generate_construction_schedule(5_000.0)
        assert result["total_duration_days"] > 0

    def test_critical_path_not_empty(self) -> None:
        """주공정선(Critical Path)이 존재한다."""
        svc = self._make_service()
        result = svc.generate_construction_schedule(10_000.0)
        assert len(result["critical_path"]) > 0

    def test_milestones_include_start_and_end(self) -> None:
        """마일스톤에 착공(0일)과 준공이 포함된다."""
        svc = self._make_service()
        result = svc.generate_construction_schedule(10_000.0)
        milestone_names = [m["name"] for m in result["milestones"]]
        assert "착공" in milestone_names
        assert "준공" in milestone_names

    def test_start_day_0(self) -> None:
        """착공 마일스톤이 0일이다."""
        svc = self._make_service()
        result = svc.generate_construction_schedule(10_000.0)
        start = next(m for m in result["milestones"] if m["name"] == "착공")
        assert start["day"] == 0

    def test_larger_area_longer_duration(self) -> None:
        """면적이 크면 총 소요일이 증가한다."""
        svc = self._make_service()
        small = svc.generate_construction_schedule(5_000.0)
        large = svc.generate_construction_schedule(50_000.0)
        assert large["total_duration_days"] > small["total_duration_days"]

    def test_src_structure_takes_longer(self) -> None:
        """SRC(철골철근콘크리트)는 RC보다 오래 걸린다."""
        svc = self._make_service()
        rc = svc.generate_construction_schedule(10_000.0, structure_type="RC")
        src = svc.generate_construction_schedule(10_000.0, structure_type="SRC")
        assert src["total_duration_days"] >= rc["total_duration_days"]

    def test_sc_structure_shorter(self) -> None:
        """SC(철골)는 RC보다 빠르다."""
        svc = self._make_service()
        rc = svc.generate_construction_schedule(10_000.0, structure_type="RC")
        sc = svc.generate_construction_schedule(10_000.0, structure_type="SC")
        assert sc["total_duration_days"] <= rc["total_duration_days"]

    def test_minimum_duration_3_days(self) -> None:
        """각 공정 최소 소요일 3일."""
        svc = self._make_service()
        result = svc.generate_construction_schedule(100.0)  # 아주 작은 면적
        for phase in result["schedule"]:
            assert phase["duration_days"] >= 3

    def test_predecessor_order(self) -> None:
        """후속 공정은 선행 공정 종료 후 시작한다."""
        svc = self._make_service()
        result = svc.generate_construction_schedule(10_000.0)
        schedule_map = {p["phase_id"]: p for p in result["schedule"]}
        # 기초공사(3)는 토공사(2) 종료 후 시작
        assert schedule_map[3]["start_day"] >= schedule_map[2]["end_day"]


# ──────────────────────────────────────
# calculate_carbon_emission 검증
# ──────────────────────────────────────


class TestCarbonEmission:
    """탄소 배출량 산정 검증."""

    def test_basic_calculation(self) -> None:
        """기본 자재/장비/전력 배출량 계산."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={"concrete": 1000.0, "steel": 100.0},
            equipment={"excavator": 200.0, "crane": 150.0},
            power={"electricity_kwh": 50_000.0, "diesel_liter": 10_000.0},
        )
        assert result["total_emission_tco2e"] > 0
        assert result["material_emission_tco2e"] > 0
        assert result["equipment_emission_tco2e"] > 0
        assert result["power_emission_tco2e"] > 0

    def test_material_detail(self) -> None:
        """자재별 상세 배출량이 포함된다."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={"concrete": 500.0, "steel": 50.0},
            equipment={},
            power={},
        )
        assert "concrete" in result["material_detail"]
        assert "steel" in result["material_detail"]
        # 콘크리트: 500톤 × 130 kgCO₂e/톤 = 65,000 kgCO₂e = 65 tCO₂e
        assert abs(result["material_detail"]["concrete"] - 65.0) < 0.1
        # 철강: 50톤 × 2,300 kgCO₂e/톤 = 115,000 kgCO₂e = 115 tCO₂e
        assert abs(result["material_detail"]["steel"] - 115.0) < 0.1

    def test_equipment_detail(self) -> None:
        """장비별 상세 배출량이 포함된다."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={},
            equipment={"excavator": 100.0},  # 100시간 × 45 kgCO₂e/h = 4,500 kg
            power={},
        )
        assert abs(result["equipment_detail"]["excavator"] - 4.5) < 0.1

    def test_power_detail(self) -> None:
        """전력/연료별 상세 배출량이 포함된다."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={},
            equipment={},
            power={"electricity_kwh": 10_000.0},  # 10,000 × 0.4781 = 4,781 kg
        )
        assert abs(result["power_detail"]["electricity_kwh"] - 4.781) < 0.1

    def test_total_equals_sum(self) -> None:
        """총 배출량 = 자재 + 장비 + 전력."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={"concrete": 100.0},
            equipment={"crane": 50.0},
            power={"diesel_liter": 1000.0},
        )
        expected_total = (
            result["material_emission_tco2e"]
            + result["equipment_emission_tco2e"]
            + result["power_emission_tco2e"]
        )
        assert abs(result["total_emission_tco2e"] - expected_total) < 0.01

    def test_empty_inputs(self) -> None:
        """입력이 비어있으면 배출량 0."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={},
            equipment={},
            power={},
        )
        assert result["total_emission_tco2e"] == 0.0

    def test_unknown_material_uses_default(self) -> None:
        """미정의 자재는 기본 배출 계수(150) 적용."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={"unknown_material": 10.0},
            equipment={},
            power={},
        )
        # 10톤 × 150 kgCO₂e/톤 = 1,500 kg = 1.5 tCO₂e
        assert abs(result["material_detail"]["unknown_material"] - 1.5) < 0.1

    def test_unknown_equipment_uses_default(self) -> None:
        """미정의 장비는 기본 배출 계수(30) 적용."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={},
            equipment={"unknown_equip": 100.0},
            power={},
        )
        # 100시간 × 30 kgCO₂e/h = 3,000 kg = 3.0 tCO₂e
        assert abs(result["equipment_detail"]["unknown_equip"] - 3.0) < 0.1

    def test_recommendations_not_empty(self) -> None:
        """배출이 있으면 감축 권장사항이 1개 이상 포함된다."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={"steel": 200.0},
            equipment={"excavator": 500.0},
            power={"electricity_kwh": 100_000.0},
        )
        assert len(result["recommendations"]) >= 1

    def test_high_emission_carbon_credit_recommendation(self) -> None:
        """총 배출량 100 tCO₂e 초과 → 탄소 배출권 검토 권장."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={"steel": 500.0},  # 500 × 2,300 = 1,150,000 kg = 1,150 tCO₂e
            equipment={},
            power={},
        )
        assert result["total_emission_tco2e"] > 100
        assert any("배출권" in r for r in result["recommendations"])

    def test_steel_highest_factor(self) -> None:
        """철강이 콘크리트보다 배출 계수가 높다."""
        steel_only = ConstructionAIService.calculate_carbon_emission(
            material={"steel": 1.0},
            equipment={},
            power={},
        )
        concrete_only = ConstructionAIService.calculate_carbon_emission(
            material={"concrete": 1.0},
            equipment={},
            power={},
        )
        assert (
            steel_only["material_emission_tco2e"]
            > concrete_only["material_emission_tco2e"]
        )


# ──────────────────────────────────────
# estimate_zeb_energy 검증
# ──────────────────────────────────────


class TestZEBEnergy:
    """ZEB 에너지 시뮬레이션 검증."""

    def _make_service(self) -> ConstructionAIService:
        return ConstructionAIService.__new__(ConstructionAIService)

    def test_basic_result_keys(self) -> None:
        """결과에 필수 키가 포함된다."""
        svc = self._make_service()
        result = svc.estimate_zeb_energy(10_000.0)
        assert "annual_energy_demand_kwh" in result
        assert "annual_renewable_generation_kwh" in result
        assert "zeb_grade" in result
        assert "energy_independence_rate" in result
        assert "recommendations" in result

    def test_better_insulation_lower_demand(self) -> None:
        """단열 등급이 높을수록 에너지 수요가 낮다."""
        svc = self._make_service()
        grade1 = svc.estimate_zeb_energy(10_000.0, insulation_grade="1등급")
        grade4 = svc.estimate_zeb_energy(10_000.0, insulation_grade="4등급")
        assert grade1["annual_energy_demand_kwh"] < grade4["annual_energy_demand_kwh"]

    def test_higher_wwr_higher_demand(self) -> None:
        """창면적비가 높을수록 에너지 수요 증가."""
        svc = self._make_service()
        low_wwr = svc.estimate_zeb_energy(10_000.0, window_wall_ratio=0.20)
        high_wwr = svc.estimate_zeb_energy(10_000.0, window_wall_ratio=0.60)
        assert high_wwr["annual_energy_demand_kwh"] > low_wwr["annual_energy_demand_kwh"]

    def test_zeb_grade_valid(self) -> None:
        """ZEB 등급이 유효한 값이다."""
        svc = self._make_service()
        result = svc.estimate_zeb_energy(10_000.0)
        valid_grades = {"1등급", "2등급", "3등급", "4등급", "5등급", "미달"}
        assert result["zeb_grade"] in valid_grades

    def test_recommendations_not_empty(self) -> None:
        """권장사항이 1개 이상 포함된다."""
        svc = self._make_service()
        result = svc.estimate_zeb_energy(10_000.0)
        assert len(result["recommendations"]) >= 1
