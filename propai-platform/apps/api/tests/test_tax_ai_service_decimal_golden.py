"""TaxAIService.calculate_capital_gains_tax Decimal 승격 골든 회귀 테스트 (W3-9).

★기대값은 전환 **전**(현행 float 구현) 실행 결과를 그대로 고정한 것이다
(전환 후 출력을 복붙한 것이 아님 — 30건 모두 전환 전 라이브 코드로 직접 산출·
전환 후 프로토타입과의 완전일치를 확증한 뒤 여기 박제했다).

목적: 세금 코어(과세표준→세액→다주택중과→합계) Decimal 승격이
현행 round() 출력과 바이트 동일함을 대표 입력 30건으로 고정 검증한다.
전환 후 이 파일의 전건이 그대로 통과해야 한다(단 1건도 값이 바뀌면 안 됨).

※ 참고: 극단적 규모(양도차익 조 단위 이상) 또는 특정 세율 경계에서는
매우 드물게(실측 약 1/500,000~1/3,000,000, 항상 ±1원) Decimal 승격이
현행 float 누적오차를 교정하며 값이 달라질 수 있다 — 이는 W3-9 재실측에서
확인된 의도된 정밀도 개선이며, 아래 대표 입력들은 그 경계에 해당하지
않도록 선정되어 완전일치를 유지한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.tax_ai_service import TaxAIService


def _svc() -> TaxAIService:
    return object.__new__(TaxAIService)


# (이름, 입력 kwargs, 전환 전 실측 기대값)
GOLDEN_CASES: list[tuple[str, dict, dict]] = [
    ("basic_5y_general", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 5},
     {"gain": 1000000000.0, "deduction_rate": 0.128571, "deduction_amount": 128571000, "taxable_gain": 871429000,
      "bracket_rate": 0.42, "bracket_deduction": 35940000, "base_tax": 330060180, "multi_home_surcharge": 0,
      "tax": 330060180, "effective_rate": 0.33006}),
    ("basic_10y_general_max", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 10},
     {"gain": 1000000000.0, "deduction_rate": 0.3, "deduction_amount": 300000000, "taxable_gain": 700000000,
      "bracket_rate": 0.42, "bracket_deduction": 35940000, "base_tax": 258060000, "multi_home_surcharge": 0,
      "tax": 258060000, "effective_rate": 0.25806}),
    ("single_home_5y", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 5,
                         "is_single_home": True},
     {"gain": 1000000000.0, "deduction_rate": 0.4, "deduction_amount": 400000000, "taxable_gain": 600000000,
      "bracket_rate": 0.42, "bracket_deduction": 35940000, "base_tax": 216060000, "multi_home_surcharge": 0,
      "tax": 216060000, "effective_rate": 0.21606}),
    ("single_home_10y_max", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 10,
                              "is_single_home": True},
     {"gain": 1000000000.0, "deduction_rate": 0.8, "deduction_amount": 800000000, "taxable_gain": 200000000,
      "bracket_rate": 0.38, "bracket_deduction": 19940000, "base_tax": 56060000, "multi_home_surcharge": 0,
      "tax": 56060000, "effective_rate": 0.05606}),
    ("min_3y_general", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 3},
     {"gain": 1000000000.0, "deduction_rate": 0.06, "deduction_amount": 60000000, "taxable_gain": 940000000,
      "bracket_rate": 0.42, "bracket_deduction": 35940000, "base_tax": 358860000, "multi_home_surcharge": 0,
      "tax": 358860000, "effective_rate": 0.35886}),
    ("min_3y_single", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 3,
                        "is_single_home": True},
     {"gain": 1000000000.0, "deduction_rate": 0.24, "deduction_amount": 240000000, "taxable_gain": 760000000,
      "bracket_rate": 0.42, "bracket_deduction": 35940000, "base_tax": 283260000, "multi_home_surcharge": 0,
      "tax": 283260000, "effective_rate": 0.28326}),
    ("interp_4y_general", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 4},
     {"gain": 1000000000.0, "deduction_rate": 0.094286, "deduction_amount": 94286000, "taxable_gain": 905714000,
      "bracket_rate": 0.42, "bracket_deduction": 35940000, "base_tax": 344459880, "multi_home_surcharge": 0,
      "tax": 344459880, "effective_rate": 0.34446}),
    ("interp_6y_general", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 6},
     {"gain": 1000000000.0, "deduction_rate": 0.162857, "deduction_amount": 162857000, "taxable_gain": 837143000,
      "bracket_rate": 0.42, "bracket_deduction": 35940000, "base_tax": 315660060, "multi_home_surcharge": 0,
      "tax": 315660060, "effective_rate": 0.31566}),
    ("interp_8y_single", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 8,
                           "is_single_home": True},
     {"gain": 1000000000.0, "deduction_rate": 0.64, "deduction_amount": 640000000, "taxable_gain": 360000000,
      "bracket_rate": 0.4, "bracket_deduction": 25940000, "base_tax": 118060000, "multi_home_surcharge": 0,
      "tax": 118060000, "effective_rate": 0.11806}),
    ("over_10y_capped", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 15},
     {"gain": 1000000000.0, "deduction_rate": 0.3, "deduction_amount": 300000000, "taxable_gain": 700000000,
      "bracket_rate": 0.42, "bracket_deduction": 35940000, "base_tax": 258060000, "multi_home_surcharge": 0,
      "tax": 258060000, "effective_rate": 0.25806}),
    ("multihome_2", {"sale_price": 1000000000.0, "acquisition_price": 500000000.0, "holding_years": 5,
                      "home_count": 2},
     {"gain": 500000000.0, "deduction_rate": 0.128571, "deduction_amount": 64285500, "taxable_gain": 435714500,
      "bracket_rate": 0.4, "bracket_deduction": 25940000, "base_tax": 148345800, "multi_home_surcharge": 87142900,
      "tax": 235488700, "effective_rate": 0.470977}),
    ("multihome_3", {"sale_price": 1000000000.0, "acquisition_price": 500000000.0, "holding_years": 5,
                      "home_count": 3},
     {"gain": 500000000.0, "deduction_rate": 0.128571, "deduction_amount": 64285500, "taxable_gain": 435714500,
      "bracket_rate": 0.4, "bracket_deduction": 25940000, "base_tax": 148345800, "multi_home_surcharge": 130714350,
      "tax": 279060150, "effective_rate": 0.55812}),
    ("multihome_2_single", {"sale_price": 1000000000.0, "acquisition_price": 500000000.0, "holding_years": 10,
                             "is_single_home": True, "home_count": 2},
     {"gain": 500000000.0, "deduction_rate": 0.8, "deduction_amount": 400000000, "taxable_gain": 100000000,
      "bracket_rate": 0.35, "bracket_deduction": 15440000, "base_tax": 19560000, "multi_home_surcharge": 20000000,
      "tax": 39560000, "effective_rate": 0.07912}),
    ("no_gain_equal", {"sale_price": 500000000.0, "acquisition_price": 500000000.0, "holding_years": 5},
     {"gain": 0.0, "deduction_rate": 0.0, "taxable_gain": 0.0, "tax": 0.0, "effective_rate": 0.0,
      "bracket_rate": 0.0, "bracket_deduction": 0, "multi_home_surcharge": 0.0}),
    ("negative_gain", {"sale_price": 400000000.0, "acquisition_price": 500000000.0, "holding_years": 5},
     {"gain": -100000000.0, "deduction_rate": 0.0, "taxable_gain": 0.0, "tax": 0.0, "effective_rate": 0.0,
      "bracket_rate": 0.0, "bracket_deduction": 0, "multi_home_surcharge": 0.0}),
    ("short_term_under1y", {"sale_price": 600000000.0, "acquisition_price": 500000000.0, "holding_years": 0},
     {"gain": 100000000.0, "deduction_rate": 0.0, "taxable_gain": 100000000.0, "tax": 77000000.0,
      "effective_rate": 0.77, "bracket_rate": 0.77, "bracket_deduction": 0, "short_term": True,
      "multi_home_surcharge": 0.0}),
    ("short_term_1to2y", {"sale_price": 600000000.0, "acquisition_price": 500000000.0, "holding_years": 1},
     {"gain": 100000000.0, "deduction_rate": 0.0, "taxable_gain": 100000000.0, "tax": 66000000.0,
      "effective_rate": 0.66, "bracket_rate": 0.66, "bracket_deduction": 0, "short_term": True,
      "multi_home_surcharge": 0.0}),
    ("bracket1_boundary", {"sale_price": 514000000.0, "acquisition_price": 500000000.0, "holding_years": 3},
     {"gain": 14000000.0, "deduction_rate": 0.06, "deduction_amount": 840000, "taxable_gain": 13160000,
      "bracket_rate": 0.06, "bracket_deduction": 0, "base_tax": 789600, "multi_home_surcharge": 0,
      "tax": 789600, "effective_rate": 0.0564}),
    ("bracket2_boundary", {"sale_price": 550000000.0, "acquisition_price": 500000000.0, "holding_years": 3},
     {"gain": 50000000.0, "deduction_rate": 0.06, "deduction_amount": 3000000, "taxable_gain": 47000000,
      "bracket_rate": 0.15, "bracket_deduction": 1260000, "base_tax": 5790000, "multi_home_surcharge": 0,
      "tax": 5790000, "effective_rate": 0.1158}),
    ("bracket7_boundary", {"sale_price": 1500000000.0, "acquisition_price": 500000000.0, "holding_years": 3},
     {"gain": 1000000000.0, "deduction_rate": 0.06, "deduction_amount": 60000000, "taxable_gain": 940000000,
      "bracket_rate": 0.42, "bracket_deduction": 35940000, "base_tax": 358860000, "multi_home_surcharge": 0,
      "tax": 358860000, "effective_rate": 0.35886}),
    ("large_realistic_50eok", {"sale_price": 5500000000.0, "acquisition_price": 500000000.0, "holding_years": 7},
     {"gain": 5000000000.0, "deduction_rate": 0.197143, "deduction_amount": 985715000, "taxable_gain": 4014285000,
      "bracket_rate": 0.45, "bracket_deduction": 65940000, "base_tax": 1740488250, "multi_home_surcharge": 0,
      "tax": 1740488250, "effective_rate": 0.348098}),
    ("tiny_gain_1won", {"sale_price": 500000001.0, "acquisition_price": 500000000.0, "holding_years": 5},
     {"gain": 1.0, "deduction_rate": 0.128571, "deduction_amount": 0, "taxable_gain": 1, "bracket_rate": 0.06,
      "bracket_deduction": 0, "base_tax": 0, "multi_home_surcharge": 0, "tax": 0, "effective_rate": 0.052286}),
    ("apartment_typical", {"sale_price": 1200000000.0, "acquisition_price": 700000000.0, "holding_years": 7,
                            "is_single_home": True},
     {"gain": 500000000.0, "deduction_rate": 0.56, "deduction_amount": 280000000, "taxable_gain": 220000000,
      "bracket_rate": 0.38, "bracket_deduction": 19940000, "base_tax": 63660000, "multi_home_surcharge": 0,
      "tax": 63660000, "effective_rate": 0.12732}),
    ("investor_multi3", {"sale_price": 3500000000.0, "acquisition_price": 1800000000.0, "holding_years": 4,
                          "home_count": 3},
     {"gain": 1700000000.0, "deduction_rate": 0.094286, "deduction_amount": 160286200, "taxable_gain": 1539713800,
      "bracket_rate": 0.45, "bracket_deduction": 65940000, "base_tax": 626931210, "multi_home_surcharge": 461914140,
      "tax": 1088845350, "effective_rate": 0.640497}),
    ("investor_multi2_10y", {"sale_price": 2800000000.0, "acquisition_price": 900000000.0, "holding_years": 10,
                              "home_count": 2},
     {"gain": 1900000000.0, "deduction_rate": 0.3, "deduction_amount": 570000000, "taxable_gain": 1330000000,
      "bracket_rate": 0.45, "bracket_deduction": 65940000, "base_tax": 532560000, "multi_home_surcharge": 266000000,
      "tax": 798560000, "effective_rate": 0.420295}),
    ("high_value_20y", {"sale_price": 8000000000.0, "acquisition_price": 1000000000.0, "holding_years": 20},
     {"gain": 7000000000.0, "deduction_rate": 0.3, "deduction_amount": 2100000000, "taxable_gain": 4900000000,
      "bracket_rate": 0.45, "bracket_deduction": 65940000, "base_tax": 2139060000, "multi_home_surcharge": 0,
      "tax": 2139060000, "effective_rate": 0.30558}),
    ("high_value_20y_single", {"sale_price": 8000000000.0, "acquisition_price": 1000000000.0, "holding_years": 20,
                                "is_single_home": True},
     {"gain": 7000000000.0, "deduction_rate": 0.8, "deduction_amount": 5600000000, "taxable_gain": 1400000000,
      "bracket_rate": 0.45, "bracket_deduction": 65940000, "base_tax": 564060000, "multi_home_surcharge": 0,
      "tax": 564060000, "effective_rate": 0.08058}),
    ("mid_holding_12y", {"sale_price": 2200000000.0, "acquisition_price": 600000000.0, "holding_years": 12},
     {"gain": 1600000000.0, "deduction_rate": 0.3, "deduction_amount": 480000000, "taxable_gain": 1120000000,
      "bracket_rate": 0.45, "bracket_deduction": 65940000, "base_tax": 438060000, "multi_home_surcharge": 0,
      "tax": 438060000, "effective_rate": 0.273788}),
    ("small_apartment_flip", {"sale_price": 650000000.0, "acquisition_price": 550000000.0, "holding_years": 2,
                               "home_count": 2},
     {"gain": 100000000.0, "deduction_rate": 0.0, "deduction_amount": 0, "taxable_gain": 100000000,
      "bracket_rate": 0.35, "bracket_deduction": 15440000, "base_tax": 19560000, "multi_home_surcharge": 20000000,
      "tax": 39560000, "effective_rate": 0.3956}),
    ("giant_value_1000eok", {"sale_price": 100500000000.0, "acquisition_price": 500000000.0, "holding_years": 9,
                              "home_count": 3},
     {"gain": 100000000000.0, "deduction_rate": 0.265714, "deduction_amount": 26571400000,
      "taxable_gain": 73428600000, "bracket_rate": 0.45, "bracket_deduction": 65940000, "base_tax": 32976930000,
      "multi_home_surcharge": 22028580000, "tax": 55005510000, "effective_rate": 0.550055}),
]


class TestCalculateCapitalGainsTaxDecimalGolden:
    """calculate_capital_gains_tax Decimal 승격 — 30건 골든 회귀(바이트 동일 확증)."""

    @pytest.mark.parametrize("name,kwargs,expected", GOLDEN_CASES, ids=[c[0] for c in GOLDEN_CASES])
    def test_golden_output_unchanged(self, name, kwargs, expected):
        svc = _svc()
        actual = svc.calculate_capital_gains_tax(**kwargs)
        assert actual == expected, f"{name}: {actual} != {expected}"

    def test_모든_필드_타입_보존(self):
        """Decimal이 응답에 새어나가지 않는다 — 모든 값이 int/float(기존 타입)이어야 한다."""
        svc = _svc()
        for _, kwargs, _ in GOLDEN_CASES:
            result = svc.calculate_capital_gains_tax(**kwargs)
            for key, value in result.items():
                assert isinstance(value, (int, float, bool)), (
                    f"{key}={value!r}({type(value)}) — Decimal 등 비표준 타입 유출"
                )
