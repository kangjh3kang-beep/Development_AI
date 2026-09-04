"""TaxAIService.calculate_capital_gains_tax Decimal 정비 골든 회귀 테스트 (W3-9 R2).

★스코프 정정(R1 리뷰 HIGH-2): 이 함수는 라우터·오케스트레이터 호출이 0건인
**비서빙 유틸리티**다(호출부는 이 테스트 파일과 tests/unit/test_tax_service.py뿐).
"세금 코어 Decimal 승격"이 아니라 "미사용 양도세 함수 Decimal 정비"가 정확한
서술이다 — 실제로 서빙되는 양도세 경로(ⓐ`_calculate_transfer_tax`=무반올림
raw float, ⓑ`disposal_stage_engine.calculate_d01_capital_gains_tax`=만원 단위
int 절사)는 이번에 건드리지 않았다(tax_ai_service.py 상단 docstring 표 참조).

GOLDEN_CASES(30건): 전환 **전**(현행 float 구현) 실행 결과를 그대로 고정한 것
(전환 후 출력을 복붙한 것이 아님). 모두 정수 원 단위 입력이라 float 뺄셈과
Decimal 뺄셈이 같은 값을 내므로 구현 전환 자체를 판별하지 못한다 — 이는 R1
리뷰에서 뮤테이션 테스트(M1: HALF_EVEN→HALF_UP, M3: Decimal 구현 전면 원복)로
실증되었다(둘 다 0/30 FAIL). 그래서 이 파일이 회귀만 잡고 전환의 존재·정책
자체는 못 지킨다는 것이 R1 판정이었다.

DISCRIMINATING_CASES(3건, R2 신규): 판별력 확보를 위해 추가.
기대값은 **수정 후 코드 출력을 복붙하지 않고**, 이 함수와 독립된 별도 코드
경로(고정밀 Decimal, context precision=50, fractions 동등성 교차확인)로 직접
산출한 참값이다:
  - reviewer_diverge_1 / self_found_diverge_2: float 누적오차 때문에 원래
    구현(구)과 Decimal 구현(신)이 실제로 갈리는 입력 — 신 쪽이 참값과 일치함을
    독립 오라클로 확증했다(M3 원복 뮤테이션을 잡아낸다).
  - exact_half_tie_rounding_policy: 특정 필드가 정확히 x.5원에서 반올림되는
    입력 — ROUND_HALF_EVEN과 ROUND_HALF_UP의 결과가 실제로 갈린다(M1 반올림
    정책 뮤테이션을 잡아낸다. R2에서 HALF_EVEN→HALF_UP을 직접 재주입해 이
    케이스가 FAIL함을 확인 후 원복함 — 커밋 메시지 참조).

※ 참고: 이 세 케이스가 나오게 된 배경(부동소수 float 누적오차가 원단위
경계를 넘는 사례)은 극단적 규모(양도차익 조 단위 이상) 또는 서로 다른 이진
표현오차가 누적되는 입력에서 드물게(수백만 건 중 수 건, 실측) 발생한다 —
이는 W3-9에서 확인된 의도된 정밀도 개선이며, GOLDEN_CASES 30건은 그 경계에
해당하지 않도록 선정되어 여전히 완전일치를 유지한다(회귀 확인용, 판별력은
DISCRIMINATING_CASES가 담당).
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


# (이름, 입력 kwargs, 독립 고정밀 Decimal 오라클로 산출한 참값, 참고: 구현 전환 전 값)
# ★기대값은 이 함수의 수정 후 출력을 복붙한 것이 아니다 — precision=50 고정밀
# Decimal 컨텍스트를 쓰는 별도 코드 경로(oracle)로 독립 산출했다. "old" 주석은
# 문서화 목적으로만 남기며 단언에는 쓰지 않는다(전면 원복 시 이 값과 달라져야
# FAIL하는 것이 이 케이스의 존재 이유다).
DISCRIMINATING_CASES: list[tuple[str, dict, dict]] = [
    (
        # 리뷰어 재현: float 뺄셈 gain(2465705902.500001)의 이진 오차가 누적되어
        # taxable_gain 반올림 경계를 넘는다. old(구현 전환 전) taxable_gain=493141180.
        "reviewer_diverge_1",
        {"sale_price": 3072821815.0339155, "acquisition_price": 607115912.5339148,
         "holding_years": 23, "is_single_home": True, "home_count": 2},
        {"gain": 2465705902.500001, "deduction_rate": 0.8, "deduction_amount": 1972564722,
         "taxable_gain": 493141181, "bracket_rate": 0.4, "bracket_deduction": 25940000,
         "base_tax": 171316472, "multi_home_surcharge": 98628236, "tax": 269944708,
         "effective_rate": 0.10948},
    ),
    (
        # 자체 발견(500만건 오라클 대조 퍼징): old taxable_gain=17074176056.
        "self_found_diverge_2",
        {"sale_price": 89246106642.80602, "acquisition_price": 64854426562.09173,
         "holding_years": 26, "is_single_home": False, "home_count": 1},
        {"gain": 24391680080.714287, "deduction_rate": 0.3, "deduction_amount": 7317504024,
         "taxable_gain": 17074176057, "bracket_rate": 0.45, "bracket_deduction": 65940000,
         "base_tax": 7617439225, "multi_home_surcharge": 0, "tax": 7617439225,
         "effective_rate": 0.312297},
    ),
    (
        # 의도적으로 구성: gain=1,000,000,001.25 × deduction_rate=0.4(5년·1세대1주택,
        # 정확한 소수) = deduction_amount 400,000,000.5 — 정확한 x.5원 타이.
        # floor=400,000,000(짝수) → ROUND_HALF_EVEN은 400,000,000(유지),
        # ROUND_HALF_UP은 400,000,001(올림)로 서로 다른 값을 낸다.
        "exact_half_tie_rounding_policy",
        {"sale_price": 1500000001.5, "acquisition_price": 500000000.25,
         "holding_years": 5, "is_single_home": True, "home_count": 1},
        {"gain": 1000000001.25, "deduction_rate": 0.4, "deduction_amount": 400000000,
         "taxable_gain": 600000001, "bracket_rate": 0.42, "bracket_deduction": 35940000,
         "base_tax": 216060000, "multi_home_surcharge": 0, "tax": 216060000,
         "effective_rate": 0.21606},
    ),
    (
        # R2b: M4(경계 전진만 되돌림 — gain_dec = Decimal(str(gain)), 즉 R1 상태) 킬러 케이스.
        # 리뷰어 확보 입력. gain(float 뺄셈) 자체의 이진오차가 taxable_gain 반올림
        # 경계를 넘는다 — MED-1(gain_dec를 sale/acq 각각의 Decimal(str())에서 직접
        # 계산) 없이는 이 케이스가 오라클과 어긋난다.
        "decimal_boundary_position_1",
        {"sale_price": 101221006029.84569, "acquisition_price": 1594587558.4171154,
         "holding_years": 21, "is_single_home": False, "home_count": 3},
        {"gain": 99626418471.42857, "deduction_rate": 0.3, "deduction_amount": 29887925541,
         "taxable_gain": 69738492930, "bracket_rate": 0.45, "bracket_deduction": 65940000,
         "base_tax": 31316381819, "multi_home_surcharge": 20921547879, "tax": 52237929698,
         "effective_rate": 0.524338},
    ),
    (
        # R2b: M4 킬러 케이스 2건째. deduction_amount가 R1 상태(gain_dec=Decimal(str(gain)))로는
        # 31,446,215,012, MED-1 적용 후(현재)는 31,446,215,013로 갈린다(리뷰어 확보 입력).
        "decimal_boundary_position_2",
        {"sale_price": 46796153996.30562, "acquisition_price": 7488385230.680617,
         "holding_years": 15, "is_single_home": True, "home_count": 1},
        {"gain": 39307768765.625, "deduction_rate": 0.8, "deduction_amount": 31446215013,
         "taxable_gain": 7861553753, "bracket_rate": 0.45, "bracket_deduction": 65940000,
         "base_tax": 3471759189, "multi_home_surcharge": 0, "tax": 3471759189,
         "effective_rate": 0.088322},
    ),
]

# ROUND_HALF_UP이었다면 exact_half_tie_rounding_policy의 deduction_amount는
# 400000001이 된다(HALF_EVEN=400000000과 다름) — 반올림 정책 뮤테이션(M1) 탐지용
# 참고값. 별도 단언(test_half_up_would_diverge)에서만 사용한다.
_HALF_UP_DEDUCTION_AMOUNT_FOR_TIE_CASE = 400000001


class TestCalculateCapitalGainsTaxDecimalGolden:
    """calculate_capital_gains_tax Decimal 정비 — 30건 골든 회귀(바이트 동일 확증)."""

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


class TestCalculateCapitalGainsTaxDiscriminating:
    """판별력 확보 케이스(R2 신규) — Decimal 구현 전면 원복(M3)·반올림 정책 변경(M1)을 잡는다.

    기대값은 이 함수와 독립된 고정밀 Decimal 오라클로 산출했다(수정 후 코드
    출력 복붙 아님) — DISCRIMINATING_CASES 정의부 주석 참조.
    """

    @pytest.mark.parametrize("name,kwargs,expected", DISCRIMINATING_CASES,
                              ids=[c[0] for c in DISCRIMINATING_CASES])
    def test_discriminating_case_matches_independent_oracle(self, name, kwargs, expected):
        svc = _svc()
        actual = svc.calculate_capital_gains_tax(**kwargs)
        assert actual == expected, f"{name}: {actual} != {expected}"

    def test_half_up_would_diverge(self):
        """정책 잠금 문서화: exact_half_tie_rounding_policy는 HALF_UP이었다면
        다른 값(400000001)이 나왔을 것이다 — 실제 반올림 정책 검증은 R2 커밋
        메시지에 기록된 수동 뮤테이션 재주입(ROUND_HALF_EVEN→ROUND_HALF_UP 후
        본 테스트 스위트 재실행 → FAIL 확인 → 원복)으로 수행했다.
        """
        svc = _svc()
        name, kwargs, expected = DISCRIMINATING_CASES[2]
        assert name == "exact_half_tie_rounding_policy"
        actual = svc.calculate_capital_gains_tax(**kwargs)
        assert actual["deduction_amount"] == expected["deduction_amount"] == 400000000
        assert _HALF_UP_DEDUCTION_AMOUNT_FOR_TIE_CASE == 400000001
        assert actual["deduction_amount"] != _HALF_UP_DEDUCTION_AMOUNT_FOR_TIE_CASE
