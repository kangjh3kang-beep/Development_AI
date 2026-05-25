"""원가계산서 생성기 테스트."""

from app.services.cost.origin_cost_calculator import (
    OriginCostCalculator, CostItem, RATES_2026,
)


SAMPLE_ITEMS = [
    CostItem(
        work_code="A01", item_name="철근콘크리트", spec="25-240-15",
        unit="m3", quantity=500.0,
        mat_unit=82000, labor_unit=45000, exp_unit=15000,
    ),
    CostItem(
        work_code="A05", item_name="창호", spec="AL 시스템",
        unit="set", quantity=200.0,
        mat_unit=350000, labor_unit=80000, exp_unit=20000,
    ),
]


class TestRates:

    def test_rates_count(self):
        assert len(RATES_2026) == 12

    def test_vat_ten_percent(self):
        assert RATES_2026["vat"] == 0.10

    def test_industrial_accident(self):
        assert RATES_2026["industrial_accident"] == 0.035

    def test_all_positive(self):
        for k, v in RATES_2026.items():
            assert v > 0, f"{k} is not positive"


class TestCostItem:

    def test_amounts(self):
        item = SAMPLE_ITEMS[0]
        assert item.mat_amt == 500 * 82000
        assert item.labor_amt == 500 * 45000
        assert item.exp_amt == 500 * 15000
        assert item.total_amt == item.mat_amt + item.labor_amt + item.exp_amt


class TestOriginCostCalculator:

    def test_calculate_basic(self):
        calc = OriginCostCalculator()
        result = calc.calculate(SAMPLE_ITEMS)

        assert result["item_count"] == 2
        assert result["direct_material_cost"] > 0
        assert result["direct_labor_cost"] > 0
        assert result["total_project_cost"] > result["net_construction_cost"]

    def test_calculation_chain(self):
        """12단계 법정요율 체인 순서 검증."""
        calc = OriginCostCalculator()
        r = calc.calculate(SAMPLE_ITEMS)

        # 직접비 = 재료 + 노무 + 경비
        assert r["direct_cost"] == (r["direct_material_cost"] +
                                     r["direct_labor_cost"] +
                                     r["direct_expense_cost"])

        # 간접노무비 = 직접노무비 × 14.40%
        expected_indirect = round(r["direct_labor_cost"] * 0.144)
        assert abs(r["indirect_labor_cost"] - expected_indirect) <= 1

        # 총노무비 = 직접노무비 + 간접노무비
        assert r["total_labor_cost"] == r["direct_labor_cost"] + r["indirect_labor_cost"]

        # 총공사비 > 세전공사비
        assert r["total_project_cost"] > r["construction_cost_pre_vat"]

        # VAT = 세전 × 10%
        expected_vat = round(r["construction_cost_pre_vat"] * 0.10)
        assert abs(r["vat"] - expected_vat) <= 1

    def test_dict_input(self):
        """dict 입력도 정상 처리."""
        calc = OriginCostCalculator()
        items = [
            {"work_code": "A01", "item_name": "콘크리트", "spec": "",
             "unit": "m3", "quantity": 100, "mat_unit": 80000,
             "labor_unit": 40000, "exp_unit": 10000},
        ]
        result = calc.calculate(items)
        assert result["item_count"] == 1
        assert result["total_project_cost"] > 0

    def test_category_totals(self):
        calc = OriginCostCalculator()
        result = calc.calculate(SAMPLE_ITEMS)
        assert "A01" in result["category_totals"]
        assert "A05" in result["category_totals"]

    def test_to_excel_data(self):
        calc = OriginCostCalculator()
        result = calc.calculate(SAMPLE_ITEMS)
        rows = calc.to_excel_data(result)
        assert len(rows) == 20  # 헤더 + 19개 행
        assert rows[0][0] == "구 분"
        assert "총 공사비" in rows[-1][0]

    def test_custom_rates(self):
        """커스텀 요율 적용."""
        calc = OriginCostCalculator()
        custom = RATES_2026.copy()
        custom["vat"] = 0.12  # 12% VAT
        result = calc.calculate(SAMPLE_ITEMS, rates=custom)
        expected_vat = round(result["construction_cost_pre_vat"] * 0.12)
        assert abs(result["vat"] - expected_vat) <= 1
