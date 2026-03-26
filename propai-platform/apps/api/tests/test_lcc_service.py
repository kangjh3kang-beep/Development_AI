"""LCCService 단위 테스트.

ISO 15686-5 기반 LCC 생애주기비용 산정 로직을 검증한다.
실질할인율, NPV 산출, 대수선 스케줄, 에너지 가격 상승, 대안 비교 등을 테스트한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.lcc_service import (
    ALTERNATIVES,
    DEFAULT_REPAIR_SCHEDULE,
    LCCService,
)


class TestRealDiscountRate:
    """실질할인율 계산 테스트."""

    def test_실질할인율_계산(self):
        """nominal=3.5%, inflation=1.3% → 실질할인율 ≈ 2.17%."""
        rate = LCCService._calc_real_discount_rate(0.035, 0.013)
        # Fisher 공식: (1.035 / 1.013) - 1 ≈ 0.02172
        assert abs(rate - 0.02172) < 0.001

    def test_실질할인율_0_인플레이션(self):
        """inflation=0 → 실질할인율 == 명목할인율."""
        rate = LCCService._calc_real_discount_rate(0.035, 0.0)
        assert abs(rate - 0.035) < 1e-10


class TestNPV:
    """NPV 산출 테스트."""

    # 공통 파라미터
    INITIAL = 10_000_000_000  # 100억
    MAINT = 200_000_000       # 2억/년
    ENERGY = 300_000_000      # 3억/년
    ESCALATION = 0.02
    YEARS = 40

    def _get_repair_costs(self) -> dict[int, float]:
        return LCCService._calc_repair_costs(
            self.INITIAL, DEFAULT_REPAIR_SCHEDULE, self.YEARS
        )

    def test_npv_40년_총합(self):
        """npv_total = npv_construction + npv_maintenance + npv_energy + npv_repair."""
        repair_costs = self._get_repair_costs()
        real_rate = LCCService._calc_real_discount_rate(0.035, 0.013)

        npv_total, npv_con, npv_maint, npv_energy, npv_repair, _ = LCCService._calc_npv(
            initial_cost=self.INITIAL,
            annual_maintenance=self.MAINT,
            annual_energy=self.ENERGY,
            energy_escalation_rate=self.ESCALATION,
            repair_costs=repair_costs,
            real_discount_rate=real_rate,
            analysis_years=self.YEARS,
        )
        assert abs(npv_total - (npv_con + npv_maint + npv_energy + npv_repair)) < 1.0

    def test_npv_초기비_포함(self):
        """npv_total > initial_cost (유지비+에너지비+대수선비가 추가되므로)."""
        repair_costs = self._get_repair_costs()
        real_rate = LCCService._calc_real_discount_rate(0.035, 0.013)

        npv_total, _, _, _, _, _ = LCCService._calc_npv(
            initial_cost=self.INITIAL,
            annual_maintenance=self.MAINT,
            annual_energy=self.ENERGY,
            energy_escalation_rate=self.ESCALATION,
            repair_costs=repair_costs,
            real_discount_rate=real_rate,
            analysis_years=self.YEARS,
        )
        assert npv_total > self.INITIAL

    def test_할인율_0_단순합산(self):
        """할인율 0 → NPV = 단순 합산 (시간 가치 없음)."""
        repair_costs = LCCService._calc_repair_costs(
            self.INITIAL, DEFAULT_REPAIR_SCHEDULE, self.YEARS
        )

        npv_total, npv_con, npv_maint, npv_energy, npv_repair, _ = LCCService._calc_npv(
            initial_cost=self.INITIAL,
            annual_maintenance=self.MAINT,
            annual_energy=self.ENERGY,
            energy_escalation_rate=self.ESCALATION,
            repair_costs=repair_costs,
            real_discount_rate=0.0,
            analysis_years=self.YEARS,
        )

        # 단순 합산 검증
        assert npv_con == self.INITIAL

        # 유지비: 2억 * 40년 = 80억
        expected_maint = self.MAINT * self.YEARS
        assert abs(npv_maint - expected_maint) < 1.0

        # 에너지비: 합산 = sum(3억 * (1.02)^y for y in 1..40)
        expected_energy = sum(
            self.ENERGY * ((1 + self.ESCALATION) ** y) for y in range(1, self.YEARS + 1)
        )
        assert abs(npv_energy - expected_energy) < 1.0

        # 대수선비: 단순 합산
        expected_repair = sum(repair_costs.values())
        assert abs(npv_repair - expected_repair) < 1.0


class TestRepairSchedule:
    """대수선 스케줄 테스트."""

    def test_대수선_15년_주기_적용(self):
        """전기설비: 15년 주기 → year 15, 30에 비용 발생."""
        initial_cost = 10_000_000_000
        repair_costs = LCCService._calc_repair_costs(
            initial_cost, DEFAULT_REPAIR_SCHEDULE, 40
        )
        # 전기설비: 15년 주기, 30% = 30억
        electric_cost = initial_cost * 0.30  # 30억

        # year 15: 전기설비만 (다른 설비는 아직 안 됨)
        assert repair_costs.get(15, 0) >= electric_cost

        # year 30: 전기설비 + 구조보수(30년 주기)
        assert repair_costs.get(30, 0) >= electric_cost

    def test_대수선_20년_주기_적용(self):
        """기계설비: 20년 주기 → year 20, 40에 비용 발생."""
        initial_cost = 10_000_000_000
        repair_costs = LCCService._calc_repair_costs(
            initial_cost, DEFAULT_REPAIR_SCHEDULE, 40
        )
        mechanical_cost = initial_cost * 0.40  # 40억

        # year 20: 기계설비 발생
        assert repair_costs.get(20, 0) >= mechanical_cost

        # year 40: 기계설비 + (전기설비 누적 등)
        assert repair_costs.get(40, 0) >= mechanical_cost

    def test_기본_repair_schedule(self):
        """DEFAULT_REPAIR_SCHEDULE은 4개 항목이다."""
        assert len(DEFAULT_REPAIR_SCHEDULE) == 4
        names = {item["name"] for item in DEFAULT_REPAIR_SCHEDULE}
        assert names == {"전기설비", "기계설비", "외벽/방수", "구조보수"}


class TestEnergy:
    """에너지 비용 테스트."""

    def test_에너지_가격_상승_반영(self):
        """에너지 상승률 적용 시 year 10 에너지비 > year 1."""
        repair_costs: dict[int, float] = {}
        _, _, _, _, _, yearly = LCCService._calc_npv(
            initial_cost=10_000_000_000,
            annual_maintenance=200_000_000,
            annual_energy=300_000_000,
            energy_escalation_rate=0.02,
            repair_costs=repair_costs,
            real_discount_rate=0.02,
            analysis_years=40,
        )
        # 명목 에너지비 (할인 전)
        year1_energy = yearly[0]["energy_krw"]
        year10_energy = yearly[9]["energy_krw"]
        assert year10_energy > year1_energy


class TestAlternatives:
    """대안 비교 테스트."""

    def _run_comparison(self) -> list[dict]:
        initial = 10_000_000_000
        repair_costs = LCCService._calc_repair_costs(
            initial, DEFAULT_REPAIR_SCHEDULE, 40
        )
        real_rate = LCCService._calc_real_discount_rate(0.035, 0.013)

        return LCCService._compare_alternatives(
            initial_cost=initial,
            annual_maintenance=200_000_000,
            annual_energy=300_000_000,
            energy_escalation_rate=0.02,
            repair_costs=repair_costs,
            real_discount_rate=real_rate,
            analysis_years=40,
        )

    def test_대안비교_고단열_에너지절감(self):
        """고단열안 NPV < 기본안 NPV (에너지 절감 효과가 초기비 증가보다 크다)."""
        results = self._run_comparison()
        base = next(r for r in results if r["alternative"] == "기본안")
        high_insul = next(r for r in results if r["alternative"] == "고단열안")
        assert high_insul["npv_total_krw"] < base["npv_total_krw"]

    def test_대안비교_태양광_최대절감(self):
        """태양광안 에너지 절감율이 가장 높다."""
        results = self._run_comparison()
        solar = next(r for r in results if r["alternative"] == "태양광안")
        for r in results:
            assert solar["energy_saving_rate"] >= r["energy_saving_rate"]


class TestYearlyCashflow:
    """연도별 현금흐름 테스트."""

    def test_yearly_cashflow_40개(self):
        """40년 분석 시 yearly cashflow 리스트 길이는 40."""
        repair_costs = LCCService._calc_repair_costs(
            10_000_000_000, DEFAULT_REPAIR_SCHEDULE, 40
        )
        real_rate = LCCService._calc_real_discount_rate(0.035, 0.013)

        _, _, _, _, _, yearly = LCCService._calc_npv(
            initial_cost=10_000_000_000,
            annual_maintenance=200_000_000,
            annual_energy=300_000_000,
            energy_escalation_rate=0.02,
            repair_costs=repair_costs,
            real_discount_rate=real_rate,
            analysis_years=40,
        )
        assert len(yearly) == 40
        # 각 항목에 필요한 키가 모두 있는지 확인
        for entry in yearly:
            assert "year" in entry
            assert "maintenance_krw" in entry
            assert "energy_krw" in entry
            assert "repair_krw" in entry
            assert "total_krw" in entry
            assert "discount_factor" in entry
            assert "pv_total_krw" in entry


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
