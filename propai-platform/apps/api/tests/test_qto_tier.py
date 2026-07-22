"""W3-3(P9) 적산 Q1~Q4 등급 분류(qto_tier) 단위 테스트 — 사실 재-표기 검증.

검증 범위:
- classify_item: qty_source(user/bim/parametric) → qto_source(bim/derived) → driver →
  항목명 키워드 → UNKNOWN 우선순위.
- classify_origin_cost_keys: OriginCostCalculator 결과의 법정요율 키만 Q3, 집계 키는 제외.
- summarize_tiers: 금액/건수 기준 분포·dominant_tier·UNKNOWN 카운트.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from app.services.cost.qto_tier import (  # noqa: E402
    ORIGIN_COST_KEY_TIER,
    QtoTier,
    classify_item,
    classify_origin_cost_keys,
    summarize_tiers,
)


class TestClassifyItemQtySource:
    def test_user_입력은_Q1(self):
        r = classify_item({"qty_source": "user"})
        assert r["tier"] == QtoTier.Q1_MEASURED

    def test_user_입력_라벨은_확정치이지_실측이_아님(self):
        # ★오케스트레이터 OpenQ 판정: user 는 Q1 유지하되 라벨은 정직화 — "현장 실측"을
        # 무조건 주장하지 않고, 오히려 "실측 아님(확정치)"임을 명시한다.
        r = classify_item({"qty_source": "user"})
        assert "확정" in r["tier_basis"]
        assert "실측 아님" in r["tier_basis"]
        assert "BIM" not in r["tier_basis"]

    def test_bim_실측은_Q1(self):
        r = classify_item({"qty_source": "bim"})
        assert r["tier"] == QtoTier.Q1_MEASURED

    def test_bim_라벨은_실측_명시(self):
        r = classify_item({"qty_source": "bim"})
        assert "실측" in r["tier_basis"]

    def test_parametric은_Q2(self):
        r = classify_item({"qty_source": "parametric"})
        assert r["tier"] == QtoTier.Q2_PARAMETRIC

    def test_qty_source_우선_driver보다_먼저(self):
        # qty_source 신호가 있으면 driver는 무시(첫 일치 우선).
        r = classify_item({"qty_source": "bim", "driver": "gfa"})
        assert r["tier"] == QtoTier.Q1_MEASURED


class TestClassifyItemQtoSource:
    def test_boq_builder_bim은_Q1(self):
        r = classify_item({"qto_source": "bim"})
        assert r["tier"] == QtoTier.Q1_MEASURED

    def test_boq_builder_derived는_Q2(self):
        r = classify_item({"qto_source": "derived"})
        assert r["tier"] == QtoTier.Q2_PARAMETRIC


class TestClassifyItemDriver:
    def test_gfa_driver는_Q2(self):
        assert classify_item({"driver": "gfa"})["tier"] == QtoTier.Q2_PARAMETRIC

    def test_households_driver는_Q2(self):
        assert classify_item({"driver": "households"})["tier"] == QtoTier.Q2_PARAMETRIC

    def test_fixed_driver도_Q2(self):
        assert classify_item({"driver": "fixed"})["tier"] == QtoTier.Q2_PARAMETRIC


class TestClassifyItemNameHints:
    def test_예비비_이름은_Q4(self):
        r = classify_item({"name": "예비비"})
        assert r["tier"] == QtoTier.Q4_ALLOWANCE

    def test_contingency_이름은_Q4(self):
        r = classify_item({"name": "contingency_won"})
        assert r["tier"] == QtoTier.Q4_ALLOWANCE

    def test_설계비_이름은_Q3(self):
        r = classify_item({"name": "design_fee_won"})
        assert r["tier"] == QtoTier.Q3_FACTORED

    def test_item_name_필드도_인식(self):
        r = classify_item({"item_name": "일반관리비"})
        assert r["tier"] == QtoTier.Q3_FACTORED


class TestClassifyItemUnknown:
    def test_신호_없으면_UNKNOWN(self):
        r = classify_item({"name": "알수없는항목"})
        assert r["tier"] == QtoTier.UNKNOWN
        assert "신호" in r["tier_basis"] or "근거" in r["tier_basis"]

    def test_빈_dict도_UNKNOWN(self):
        assert classify_item({})["tier"] == QtoTier.UNKNOWN


class TestClassifyOriginCostKeys:
    def test_요율_키만_분류(self):
        calc = {
            "direct_cost": 1000, "indirect_labor_cost": 50, "vat": 100,
            "total_project_cost": 9999,  # 집계값 — 매핑 대상 아님
        }
        out = classify_origin_cost_keys(calc)
        assert "indirect_labor_cost" in out
        assert "vat" in out
        assert "direct_cost" not in out          # 집계값(직접비 항목 합) — 제외
        assert "total_project_cost" not in out   # 집계값 — 제외
        assert out["vat"]["tier"] == QtoTier.Q3_FACTORED

    def test_모든_매핑_키가_Q3(self):
        assert all(t == QtoTier.Q3_FACTORED for t in ORIGIN_COST_KEY_TIER.values())

    def test_calc에_없는_키는_생략(self):
        out = classify_origin_cost_keys({"vat": 100})
        assert list(out.keys()) == ["vat"]

    def test_insurance_total은_이중계상_방지위해_매핑에서_제외(self):
        """★R1 HIGH 회귀가드: insurance_total(6개 보험료의 소계)이 개별 6항목과
        함께 Q3 로 다시 잡히면 같은 금액이 두 번 합산된다(리뷰어 실증: Q3 +15.5%).
        ORIGIN_COST_KEY_TIER·classify_origin_cost_keys 양쪽에서 배제되어야 한다."""
        assert "insurance_total" not in ORIGIN_COST_KEY_TIER
        calc = {
            "industrial_acc_ins": 10, "employment_ins": 5, "health_ins": 8,
            "national_pension": 12, "long_term_care": 1, "retirement_fund": 6,
            "insurance_total": 42,  # 위 6개의 합(집계값)
        }
        out = classify_origin_cost_keys(calc)
        assert "insurance_total" not in out
        assert len(out) == 6  # 개별 보험료 6항목만 분류(소계 제외)

    def test_ORIGIN_COST_KEY_TIER_12개(self):
        # indirect_labor_cost·보험료 6항목·safety_health·env_preserve·general_mgmt·
        # profit·vat = 12개(insurance_total 소계 제외).
        assert len(ORIGIN_COST_KEY_TIER) == 12


class TestSummarizeTiers:
    def test_금액_기준_분포_합계_100(self):
        items = [
            {"qty_source": "bim", "amount": 300},
            {"qty_source": "parametric", "amount": 700},
        ]
        s = summarize_tiers(items)
        pct_sum = sum(
            v["pct_amount"] for v in s["by_tier"].values() if v["pct_amount"] is not None
        )
        assert abs(pct_sum - 100.0) < 0.2
        assert s["by_tier"][QtoTier.Q1_MEASURED.value]["amount_won"] == 300
        assert s["by_tier"][QtoTier.Q2_PARAMETRIC.value]["amount_won"] == 700

    def test_dominant_tier(self):
        items = [
            {"qty_source": "bim", "amount": 100},
            {"qty_source": "parametric", "amount": 900},
        ]
        s = summarize_tiers(items)
        assert s["dominant_tier"] == QtoTier.Q2_PARAMETRIC.value

    def test_amount_없어도_count_기준_분포_제공(self):
        # 공내역서 초안(단가 빈칸) 같은 무금액 항목 — pct_count 로 성숙도 판단.
        items = [{"qty_source": "bim"}, {"qty_source": "bim"}, {"qty_source": "parametric"}]
        s = summarize_tiers(items)
        assert s["by_tier"][QtoTier.Q1_MEASURED.value]["count"] == 2
        assert s["by_tier"][QtoTier.Q1_MEASURED.value]["pct_count"] == pytest.approx(66.7, abs=0.5)
        assert all(v["pct_amount"] is None for v in s["by_tier"].values())

    def test_비파괴_원본_items_불변(self):
        items = [{"qty_source": "bim", "amount": 100}]
        summarize_tiers(items)
        assert "tier" not in items[0]  # 원본 dict에는 tier 키가 없어야 함(사본만 태깅)

    def test_extra_tier_amounts_합산(self):
        items = [{"qty_source": "bim", "amount": 100}]
        extra = {"vat": {"amount_won": 50, "tier": QtoTier.Q3_FACTORED}}
        s = summarize_tiers(items, extra_tier_amounts=extra)
        assert s["by_tier"][QtoTier.Q3_FACTORED.value]["amount_won"] == 50
        assert s["by_tier"][QtoTier.Q3_FACTORED.value]["count"] == 1

    def test_unknown_count(self):
        items = [{"name": "미상항목"}, {"qty_source": "bim"}]
        s = summarize_tiers(items)
        assert s["unknown_count"] == 1
