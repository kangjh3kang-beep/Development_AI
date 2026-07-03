"""모듈 조립기 + FeasibilityServiceV2 테스트."""

import pytest

from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
from app.services.feasibility.modules.base_module import BaseModule, ModuleInput, ModuleOutput
from app.services.feasibility.modules.module_assembler import (
    ALL_MODULE_CODES,
    get_module,
    list_modules,
)


def _make_input(dev_type: str = "M06", **kwargs) -> ModuleInput:
    """테스트용 기본 입력."""
    defaults = dict(
        development_type=dev_type,
        project_name="테스트 프로젝트",
        total_land_area_sqm=50_000,
        land_category="land",
        official_price_per_sqm=500_000,
        price_multiplier=1.0,
        total_gfa_sqm=100_000,
        building_type="apartment",
        total_households=1000,
        avg_sale_price_per_pyeong=15_000_000,
        avg_area_pyeong=30,
        sale_ratio=1.0,
        bridge_amount_won=30_000_000_000,
        pf_amount_won=100_000_000_000,
        midpay_amount_won=50_000_000_000,
        sido_name="경기",
        sigungu_name="수원시",
        project_months=48,
    )
    defaults.update(kwargs)
    return ModuleInput(**defaults)


class TestModuleAssembler:
    def test_all_15_codes_supported(self):
        assert len(ALL_MODULE_CODES) == 15
        for code in ALL_MODULE_CODES:
            module = get_module(code)
            assert isinstance(module, BaseModule)
            assert module.code == code

    def test_m01_specialized(self):
        m = get_module("M01")
        assert m.name == "재개발"

    def test_m02_specialized(self):
        m = get_module("M02")
        assert m.name == "재건축"

    def test_m04_specialized(self):
        m = get_module("M04")
        assert m.name == "지역주택조합"

    def test_m08_specialized(self):
        m = get_module("M08")
        assert m.name == "오피스텔"

    def test_m06_generic(self):
        m = get_module("M06")
        assert m.name == "일반분양"

    def test_invalid_code(self):
        with pytest.raises(ValueError, match="지원하지 않는"):
            get_module("M99")

    def test_list_modules(self):
        modules = list_modules()
        assert len(modules) == 15
        codes = [m["code"] for m in modules]
        assert "M01" in codes
        assert "M15" in codes


class TestModuleCalculation:
    def test_m06_basic(self):
        """M06 일반분양 — 기본 계산."""
        module = get_module("M06")
        inp = _make_input("M06")
        output = module.calculate(inp)

        assert isinstance(output, ModuleOutput)
        assert output.development_type == "M06"
        assert output.total_revenue_won > 0
        assert output.total_cost_won > 0
        assert output.grade in "ABCDEF"

    def test_m01_redevelopment(self):
        """M01 재개발 — 비례율 반영."""
        module = get_module("M01")
        inp = _make_input("M01", params={"proportional_rate": 1.1})
        output = module.calculate(inp)
        assert output.special_detail.get("proportional_rate") == 1.1

    def test_m02_with_levy(self):
        """M02 재건축 — 초과이익환수 포함."""
        module = get_module("M02")
        inp = _make_input("M02", params={"excess_gain_won": 1_000_000_000})
        output = module.calculate(inp)
        assert output.special_detail.get("reconstruction_levy") is not None
        levy = output.special_detail["reconstruction_levy"]["amount_won"]
        assert levy > 0  # 10억 초과이익 → 환수금 발생

    def test_m08_dcf(self):
        """M08 오피스텔 — DCF t=1 기준."""
        module = get_module("M08")
        inp = _make_input("M08", params={
            "annual_noi_won": 5_000_000_000,
            "terminal_cap_rate": 0.06,
            "hold_years": 10,
        })
        output = module.calculate(inp)
        dcf = output.special_detail.get("dcf", {})
        assert dcf.get("npv_won", 0) > 0
        assert dcf.get("hold_years") == 10


class TestFeasibilityServiceV2:
    def test_single_calculate(self):
        svc = FeasibilityServiceV2()
        inp = _make_input("M06")
        output = svc.calculate(inp)
        assert output.grade in "ABCDEF"

    def test_validate_error(self):
        svc = FeasibilityServiceV2()
        inp = ModuleInput(development_type="M06")  # 면적 0 → 검증 실패
        with pytest.raises(ValueError, match="입력 검증"):
            svc.calculate(inp)

    def test_calculate_multi(self):
        svc = FeasibilityServiceV2()
        inputs = [
            _make_input("M01"),
            _make_input("M06"),
            _make_input("M08", params={
                "annual_noi_won": 3_000_000_000,
                "terminal_cap_rate": 0.06,
                "hold_years": 10,
            }),
        ]
        result = svc.calculate_multi(inputs)
        assert len(result["results"]) == 3
        assert len(result["comparison"]["ranking"]) == 3

    def test_list_modules(self):
        svc = FeasibilityServiceV2()
        modules = svc.list_available_modules()
        assert len(modules) == 15
