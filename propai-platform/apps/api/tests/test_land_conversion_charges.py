"""T4 부담금 브리지(land_conversion_charges) 테스트 — 순수 계산·무날조·설명가능성.

계획서: docs/LEGAL_ENGINE_SLOPE_FOREST_PLAN_2026-07-02.md §T4
- 농지보전부담금 = 개별공시지가 × 30% (㎡당 상한 50,000원) × 전용면적, confidence="estimated"
- 대체산림자원조성비 = (고시 단가 + 공시지가×1%) × 면적, 고시 단가는 하드코딩 금지 —
  ForestChargeRates 명시 주입 없으면 amount=None + 산식 설명(무날조)
- 모든 반환에 formula/basis/legal_ref_key/confidence/limitations 동반(설명가능성)
"""

import dataclasses

import pytest

from app.services.feasibility.land_conversion_charges import (
    ForestChargeRates,
    calc_farmland_preservation_charge,
    calc_forest_replacement_charge,
)

EXPLAINABILITY_KEYS = {"formula", "basis", "legal_ref_key", "confidence", "limitations"}


# ──────────────────────────────────────────────────────────────────────────
# 농지보전부담금
# ──────────────────────────────────────────────────────────────────────────
class TestFarmlandPreservationCharge:
    def test_basic_formula_10man_1000m2(self):
        """공시지가 10만원/㎡ × 30% × 1,000㎡ = 3,000만원 (계획서 정산 케이스)."""
        r = calc_farmland_preservation_charge(
            official_land_price_per_m2=100_000, conversion_area_m2=1_000
        )
        assert r["amount_won"] == 30_000_000
        assert r["per_m2_won"] == 30_000
        assert r["cap_applied"] is False

    def test_cap_50000_per_m2(self):
        """공시지가 20만원/㎡ → 30%=6만원이지만 ㎡당 5만원 캡 발동 (계획서 케이스)."""
        r = calc_farmland_preservation_charge(
            official_land_price_per_m2=200_000, conversion_area_m2=1_000
        )
        assert r["per_m2_won"] == 50_000
        assert r["amount_won"] == 50_000_000
        assert r["cap_applied"] is True

    def test_cap_boundary_exact(self):
        """공시지가 166,666.67원/㎡ 근방 — 딱 5만원 경계에서 캡 미발동/발동 일관."""
        r = calc_farmland_preservation_charge(
            official_land_price_per_m2=166_666, conversion_area_m2=1
        )
        assert r["per_m2_won"] == pytest.approx(49_999.8)
        assert r["cap_applied"] is False

    def test_explainability_fields(self):
        r = calc_farmland_preservation_charge(
            official_land_price_per_m2=100_000, conversion_area_m2=100
        )
        assert set(r.keys()) >= EXPLAINABILITY_KEYS
        assert r["confidence"] == "estimated"
        assert r["legal_ref_key"] == "farmland_preservation_charge"
        # 무날조·정직 고지: 감면 미반영을 한계에 명시
        assert any("감면" in lim for lim in r["limitations"])
        # 산식·근거에 30%·상한이 드러나야 함
        assert "30%" in r["formula"]
        assert "50,000" in r["formula"] or "5만" in r["formula"]
        assert "농지법" in r["basis"]

    def test_zero_area_is_zero(self):
        r = calc_farmland_preservation_charge(
            official_land_price_per_m2=100_000, conversion_area_m2=0
        )
        assert r["amount_won"] == 0

    @pytest.mark.parametrize(
        "price,area", [(-1, 100), (100_000, -5)],
    )
    def test_negative_inputs_rejected(self, price, area):
        with pytest.raises(ValueError):
            calc_farmland_preservation_charge(
                official_land_price_per_m2=price, conversion_area_m2=area
            )


# ──────────────────────────────────────────────────────────────────────────
# 대체산림자원조성비
# ──────────────────────────────────────────────────────────────────────────
class TestForestReplacementCharge:
    RATES = ForestChargeRates(
        year=2026,
        junbojeon_won_per_m2=8_090,
        bojeon_won_per_m2=10_510,
        restricted_won_per_m2=16_180,
    )

    def test_no_rates_returns_none_with_formula(self):
        """무날조: 고시 단가 미주입 → amount=None + 산식 설명 + 고시 확인 안내."""
        r = calc_forest_replacement_charge(
            official_land_price_per_m2=100_000,
            conversion_area_m2=1_000,
            forest_type="준보전산지",
            rates=None,
        )
        assert r["amount_won"] is None
        assert r["confidence"] == "unavailable"
        assert "고시" in r["formula"] or "고시" in r["basis"]
        assert any("고시" in lim for lim in r["limitations"])
        assert r["legal_ref_key"] == "forest_replacement_charge"

    def test_with_rates_junbojeon(self):
        """(단가 8,090 + 공시지가 100,000×1%) × 1,000㎡ = 9,090,000원."""
        r = calc_forest_replacement_charge(
            official_land_price_per_m2=100_000,
            conversion_area_m2=1_000,
            forest_type="준보전산지",
            rates=self.RATES,
        )
        assert r["amount_won"] == pytest.approx(9_090_000)
        assert r["per_m2_won"] == pytest.approx(9_090)
        assert r["confidence"] == "estimated"
        assert r["rates_year"] == 2026

    def test_with_rates_bojeon(self):
        r = calc_forest_replacement_charge(
            official_land_price_per_m2=50_000,
            conversion_area_m2=200,
            forest_type="보전산지",
            rates=self.RATES,
        )
        # (10,510 + 500) × 200 = 2,202,000
        assert r["amount_won"] == pytest.approx(2_202_000)

    def test_with_rates_restricted(self):
        r = calc_forest_replacement_charge(
            official_land_price_per_m2=0,
            conversion_area_m2=10,
            forest_type="산지전용제한지역",
            rates=self.RATES,
        )
        assert r["amount_won"] == pytest.approx(161_800)

    def test_invalid_forest_type_rejected(self):
        with pytest.raises(ValueError):
            calc_forest_replacement_charge(
                official_land_price_per_m2=100_000,
                conversion_area_m2=100,
                forest_type="농업진흥지역",
                rates=self.RATES,
            )

    def test_explainability_fields(self):
        r = calc_forest_replacement_charge(
            official_land_price_per_m2=100_000,
            conversion_area_m2=100,
            forest_type="준보전산지",
            rates=self.RATES,
        )
        assert set(r.keys()) >= EXPLAINABILITY_KEYS
        assert "산지관리법" in r["basis"]
        assert "1%" in r["formula"]
        # 감면·가산 상한 등 고시 세부기준 미반영 한계 정직 고지
        assert len(r["limitations"]) >= 1

    def test_negative_inputs_rejected(self):
        with pytest.raises(ValueError):
            calc_forest_replacement_charge(
                official_land_price_per_m2=-1,
                conversion_area_m2=100,
                forest_type="준보전산지",
                rates=self.RATES,
            )

    def test_rates_dataclass_is_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            self.RATES.junbojeon_won_per_m2 = 0  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────────
# 결정론(순수함수) 보증
# ──────────────────────────────────────────────────────────────────────────
def test_deterministic():
    a = calc_farmland_preservation_charge(
        official_land_price_per_m2=123_456, conversion_area_m2=777
    )
    b = calc_farmland_preservation_charge(
        official_land_price_per_m2=123_456, conversion_area_m2=777
    )
    assert a == b
