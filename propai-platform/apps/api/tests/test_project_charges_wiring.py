"""부담금 상시-0 봉합 회귀 테스트 — A10·C07 채널 배선 + B/C단계 공용 헬퍼.

배경(2026-07-15 수지·적산엔진 감사):
- A10 개발부담금: cost_blocks.compute_taxes가 end/start 지가·개발비용 인자를 전달하지
  않아 어떤 경로에서도 산정 불가(상시 0원 데드 경로).
- C07 기반시설부담금: in_infra_charge_zone 게이트 미전달 → 항상 미부과.
- 개략수지(rough): total_tax_cost_won=0으로 B/C단계 부담금 전량 누락.

봉합 계약:
1. 채널 미제공 시 기존 결과와 완전 동일(무회귀) — 하위호환 golden 비교.
2. params.end_land_value_won 제공 시 A10 활성 — 개시지가 기본=매입가(권위),
   개발비용 기본=모듈 공사비(자동 전달).
3. params.in_infra_charge_zone=True 시 C07 부과.
4. compute_developer_stage_charges: 시행사 부담(B+C)만 합산, 수분양자 부담 제외,
   산출 불가 항목은 unavailable_notes로 정직 표기.
"""

from __future__ import annotations

from app.services.feasibility.modules.base_module import ModuleInput
from app.services.feasibility.modules.common.cost_blocks import compute_taxes
from app.services.feasibility.modules.generic_module import GenericModule
from app.services.tax.integrated_tax_engine import calculate_all_taxes
from app.services.tax.project_charges import compute_developer_stage_charges


def _base_input(**overrides) -> ModuleInput:
    kwargs = dict(
        development_type="M06",
        total_land_area_sqm=2_000.0,
        official_price_per_sqm=3_000_000,
        price_multiplier=1.1,
        total_gfa_sqm=4_000.0,
        building_type="apartment",
        total_households=350,          # 학교용지부담금(300세대) 게이트 통과
        avg_sale_price_per_pyeong=15_000_000,
        avg_area_pyeong=34.0,
        sale_ratio=0.95,
        sido_name="서울특별시",
        sigungu_name="강남구",
        project_months=36,
        region_type="capital_area",
    )
    kwargs.update(overrides)
    return ModuleInput(**kwargs)


def _find_item(stage: dict, code: str) -> dict | None:
    return next((it for it in stage.get("items") or [] if it.get("code") == code), None)


# ─────────────────────────────────────────────────────────────────────────────
# 1) 하위호환 — 채널 미제공 시 종전 호출과 결과 완전 동일(무회귀 golden)
# ─────────────────────────────────────────────────────────────────────────────
class TestBackwardCompat:
    def test_no_params_identical_to_legacy_call(self):
        """params 없는 compute_taxes = 봉합 전 인자 집합의 calculate_all_taxes와 동일."""
        inp = _base_input()
        sale_won = 50_000_000_000
        new = compute_taxes(inp, sale_won)
        legacy = calculate_all_taxes(  # 봉합 전 cost_blocks가 전달하던 인자 그대로
            purchase_won=int(inp.total_land_area_sqm * inp.official_price_per_sqm * inp.price_multiplier),
            land_category=inp.land_category,
            house_count=inp.house_count,
            is_adjusted=inp.is_adjusted_area,
            area_sqm=inp.total_land_area_sqm,
            official_price_per_sqm=inp.official_price_per_sqm,
            region_type=inp.region_type,
            sido_name=inp.sido_name,
            sigungu_name=inp.sigungu_name,
            total_households=inp.total_households,
            total_sale_amount_won=sale_won,
            total_gfa_sqm=inp.total_gfa_sqm,
            building_type=inp.building_type,
            total_units=inp.total_households,
            avg_area_sqm=inp.avg_area_pyeong * 3.305785,
        )
        assert new["grand_total_won"] == legacy["grand_total_won"]
        assert new["summary_by_stage"] == legacy["summary_by_stage"]
        # A10 미활성(end 미제공)·C07 미부과(게이트 False) 유지
        assert _find_item(new["acquisition"], "A10") is None
        c07 = _find_item(new["sale"], "C07")
        assert c07 is not None and c07["amount_won"] == 0

    def test_development_cost_alone_stays_dormant(self):
        """개발비용만 전달(end 지가 미제공)해도 결과 불변 — A10 게이트는 end 지가."""
        inp = _base_input()
        base = compute_taxes(inp, 0)
        with_dev = compute_taxes(inp, 0, development_cost_won=8_000_000_000)
        assert with_dev["grand_total_won"] == base["grand_total_won"]


# ─────────────────────────────────────────────────────────────────────────────
# 2) A10 개발부담금 채널
# ─────────────────────────────────────────────────────────────────────────────
class TestA10Channel:
    def test_end_land_value_activates_a10(self):
        """params.end_land_value_won 제공 → A10 산정. 개시지가 기본=매입가(권위 출처)."""
        inp = _base_input(params={"end_land_value_won": 20_000_000_000})
        purchase = int(inp.total_land_area_sqm * inp.official_price_per_sqm * inp.price_multiplier)
        result = compute_taxes(inp, 0)
        a10 = _find_item(result["acquisition"], "A10")
        assert a10 is not None
        assert a10["detail"]["start_value"] == purchase
        assert a10["detail"]["end_value"] == 20_000_000_000
        # 개발이익환수법 산식: (종료-개시-정상상승-개발비) × 부과율 > 0
        assert a10["amount_won"] > 0

    def test_development_cost_flows_from_module(self):
        """development_cost_won 인자(모듈 공사비)가 A10 개발비용으로 전달된다."""
        inp = _base_input(params={"end_land_value_won": 20_000_000_000})
        dev_cost = 5_000_000_000
        result = compute_taxes(inp, 0, development_cost_won=dev_cost)
        a10 = _find_item(result["acquisition"], "A10")
        assert a10 is not None and a10["detail"]["dev_cost"] == dev_cost

    def test_explicit_params_override_defaults(self):
        """params의 start/development_cost 명시값이 기본값(매입가·모듈 공사비)에 우선."""
        inp = _base_input(params={
            "end_land_value_won": 20_000_000_000,
            "start_land_value_won": 9_000_000_000,
            "development_cost_won": 3_000_000_000,
        })
        result = compute_taxes(inp, 0, development_cost_won=5_000_000_000)
        a10 = _find_item(result["acquisition"], "A10")
        assert a10 is not None
        assert a10["detail"]["start_value"] == 9_000_000_000
        assert a10["detail"]["dev_cost"] == 3_000_000_000

    def test_generic_module_wires_construction_cost(self):
        """GenericModule 경로: A10 개발비용 = 모듈이 계산한 공사비(자동 배선)."""
        inp = _base_input(params={"end_land_value_won": 100_000_000_000})
        out = GenericModule("M06").calculate(inp)
        a10 = _find_item(out.tax_detail["acquisition"], "A10")
        assert a10 is not None
        assert a10["detail"]["dev_cost"] == out.total_construction_cost_won
        # 세금총액이 총사업비에 실제 계상(상시-0 봉합의 최종 표면)
        assert out.total_tax_cost_won == out.tax_detail["grand_total_won"]

    def test_malformed_params_are_safe(self):
        """비수치·음수 params는 0으로 무해화(채널 오염 방지)."""
        inp = _base_input(params={"end_land_value_won": "abc"})
        result = compute_taxes(inp, 0)
        assert _find_item(result["acquisition"], "A10") is None
        inp2 = _base_input(params={"end_land_value_won": -5})
        result2 = compute_taxes(inp2, 0)
        assert _find_item(result2["acquisition"], "A10") is None


# ─────────────────────────────────────────────────────────────────────────────
# 3) C07 기반시설부담금 채널
# ─────────────────────────────────────────────────────────────────────────────
class TestC07Channel:
    def test_infra_zone_gate_activates_c07(self):
        inp = _base_input(params={"in_infra_charge_zone": True})
        result = compute_taxes(inp, 10_000_000_000)
        c07 = _find_item(result["sale"], "C07")
        assert c07 is not None and c07["amount_won"] > 0

    def test_gate_off_by_default(self):
        inp = _base_input()
        result = compute_taxes(inp, 10_000_000_000)
        c07 = _find_item(result["sale"], "C07")
        assert c07 is not None and c07["amount_won"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4) 공용 헬퍼 — B/C단계 시행사 부담 계약
# ─────────────────────────────────────────────────────────────────────────────
class TestDeveloperStageCharges:
    def test_total_is_developer_only_sum(self):
        charges = compute_developer_stage_charges(
            sido_name="서울특별시", sigungu_name="강남구",
            total_households=350, total_sale_amount_won=50_000_000_000,
            total_gfa_sqm=4_000.0, building_type="apartment", avg_area_sqm=112.0,
        )
        assert charges["total_won"] == (
            charges["construction"]["total_won"] + charges["sale"]["total_won"]
        )
        # 수분양자 부담(C04~C06)은 합계에서 제외(참고 필드로만 분리 제공)
        buyer = charges["sale"].get("buyer_borne_total_won", 0)
        assert buyer > 0
        developer_sale_items = sum(
            it["amount_won"] for it in charges["sale"]["items"] if it.get("borne_by") == "developer"
        )
        assert charges["sale"]["total_won"] == developer_sale_items
        # 학교용지부담금(300세대↑) 실계상 확인 — 상시-0 봉합의 핵심 표적
        b02 = _find_item(charges["construction"], "B02")
        assert b02 is not None and b02["amount_won"] > 0

    def test_unavailable_notes_collected(self):
        """조례 단가 미등록 지자체 → 값 날조 대신 unavailable_notes 정직 표기."""
        charges = compute_developer_stage_charges(
            sido_name="존재하지않는도", sigungu_name="없는시",
            total_households=350, total_sale_amount_won=50_000_000_000,
            total_gfa_sqm=4_000.0, building_type="apartment", avg_area_sqm=112.0,
        )
        assert any("상수도" in n or "하수도" in n for n in charges["unavailable_notes"])

    def test_infra_zone_gate_passthrough(self):
        base = compute_developer_stage_charges(
            sido_name="서울특별시", total_households=350,
            total_sale_amount_won=50_000_000_000, total_gfa_sqm=4_000.0,
        )
        gated = compute_developer_stage_charges(
            sido_name="서울특별시", total_households=350,
            total_sale_amount_won=50_000_000_000, total_gfa_sqm=4_000.0,
            in_infra_charge_zone=True,
        )
        assert gated["total_won"] > base["total_won"]
