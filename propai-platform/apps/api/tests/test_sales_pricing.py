"""#8 적정분양가·매출역산·원가 — 머니패스 순수로직 회귀 안전망(Wave2 P1).

DB 무관(또는 가짜세션) 단위테스트로 다음 회귀를 영구 차단한다.
- compute_unit_price: Decimal 정합(float 혼입 차단)·ROUND_HALF_UP·평형 환산·가중치(RATE/FIXED) 정확성.
- decompose: 구성요소 합 = 분양가(잔차 0 — 마지막 RATE 구성 흡수)·ROUND_HALF_UP·CAP 모드(CUSTOM 제외).
- solve_base_for_target: 역산 base 계산·엣지(세대0·목표0·음수 base)·결정론·round-trip 잔차(gap_10k) 노출.
- project_revenue: 세대별 가격 합 = 총매출·만원 환산.
- suggest 교차검증: 이상치 배제·데이터없음 정직(가짜값 금지)·신뢰도 강등.
- _extract_dong: 동/읍/면/리 파싱 견고성(도로명=None 정직).
- _cost_validation: 원가엔진 미가용 시 graceful None.

라이브 MOLIT 실거래·실 DB 는 sandbox 미가용(deploy-pending) — 여기선 순수로직·math 만 검증한다.
"""
from __future__ import annotations

import os
import sys
import uuid as uuid_mod
from decimal import ROUND_HALF_UP, Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.sales.pricing.engine import (  # noqa: E402
    VAT,
    Q,
    _area,
    _match_weights,
    compute_unit_price,
    decompose,
)
from app.services.sales.pricing.suggest import (  # noqa: E402
    _cost_validation,
    _extract_dong,
)


# ── 가짜 ORM 행(순수로직 테스트용 — DB 미접촉) ─────────────────────────────────
class _Type:
    def __init__(self, supply=None, contract=None, exclusive=None, name="84A"):
        self.supply_area = supply
        self.contract_area = contract
        self.exclusive_area = exclusive
        self.type_name = name


class _Base:
    def __init__(self, basis="PER_AREA", unit_price=0, area_kind="supply", round_factor=1):
        self.basis = basis
        self.base_unit_price = unit_price
        self.base_area_kind = area_kind
        self.round_factor = round_factor


class _Weight:
    def __init__(self, basis="RATE", value=0, dimension="CUSTOM", match_key="", priority=0):
        self.basis = basis
        self.value = value
        self.dimension = dimension
        self.match_key = match_key
        self.priority = priority


class _Comp:
    def __init__(self, component_type, basis, value, vat=False, label=None):
        self.component_type = component_type
        self.basis = basis
        self.value = value
        self.vat_applicable = vat
        self.label = label or component_type


class _Unit:
    def __init__(self, floor=10, line="1", aspect="S", uid=None):
        self.floor = floor
        self.line = line
        self.aspect = aspect
        self.id = uid or uuid_mod.uuid4()


# ── _area: 평형 환산(area_kind 우선, 없으면 supply 폴백) ──────────────────────────
class TestArea:
    def test_supply_kind(self):
        assert _area(_Type(supply=112.4), "supply") == Decimal("112.4")

    def test_contract_kind(self):
        assert _area(_Type(supply=112.4, contract=120.0), "contract") == Decimal("120.0")

    def test_falls_back_to_supply_when_kind_missing(self):
        """area_kind 면적이 없으면 supply 로 폴백(0 으로 죽지 않음)."""
        assert _area(_Type(supply=100.0, contract=None), "contract") == Decimal("100.0")

    def test_zero_when_all_none(self):
        assert _area(_Type(), "supply") == Decimal("0")

    def test_returns_decimal_not_float(self):
        """★Decimal 정합: float 가 아닌 Decimal 반환(부동소수 오차 차단)."""
        assert isinstance(_area(_Type(supply=84.0), "supply"), Decimal)


# ── compute_unit_price: 기준가×(1+ΣRATE)+ΣFIXED, ROUND_HALF_UP, float 차단 ──────────
class TestComputeUnitPrice:
    def test_per_area_basic(self):
        """PER_AREA: 단가 1,000원/㎡ × 공급 100㎡ = 100,000원(가중치 없음)."""
        p = compute_unit_price(_Unit(), _Type(supply=100), _Base(unit_price=1000), [])
        assert p == Decimal(100_000)
        assert isinstance(p, Decimal)

    def test_per_unit_basis(self):
        """PER_UNIT: 면적 무시, 단가 그대로."""
        p = compute_unit_price(_Unit(), _Type(supply=100), _Base(basis="PER_UNIT", unit_price=500_000_000), [])
        assert p == Decimal(500_000_000)

    def test_rate_weight_applied(self):
        """RATE 가중치 +5%: 100,000 × 1.05 = 105,000."""
        w = [_Weight(basis="RATE", value=0.05)]
        p = compute_unit_price(_Unit(), _Type(supply=100), _Base(unit_price=1000), w)
        assert p == Decimal(105_000)

    def test_fixed_weight_added(self):
        """FIXED 가중치 +50,000원: 100,000 + 50,000 = 150,000."""
        w = [_Weight(basis="FIXED", value=50_000)]
        p = compute_unit_price(_Unit(), _Type(supply=100), _Base(unit_price=1000), w)
        assert p == Decimal(150_000)

    def test_rate_and_fixed_combined(self):
        """(amt×(1+ΣRATE)) + ΣFIXED 순서: 100,000×1.1 + 50,000 = 160,000."""
        w = [_Weight(basis="RATE", value=0.1), _Weight(basis="FIXED", value=50_000)]
        p = compute_unit_price(_Unit(), _Type(supply=100), _Base(unit_price=1000), w)
        assert p == Decimal(160_000)

    def test_round_half_up(self):
        """★ROUND_HALF_UP: 0.5 는 올림. 단가 1,000.5원 환산 결과의 끝자리 반올림."""
        # 단가 1,001원/㎡ × 100.005㎡ = 100,105.005 → HALF_UP → 100,105.
        p = compute_unit_price(_Unit(), _Type(supply=Decimal("100.005")), _Base(unit_price=1001), [])
        assert p == Decimal(100_105)

    def test_round_half_up_rounds_point_five_up(self):
        """정확히 .5 는 올림(HALF_UP) — 은행반올림(HALF_EVEN) 아님."""
        # 0.5 가 떨어지도록: 단가 1원/㎡ × 0.5㎡ = 0.5 → HALF_UP → 1.
        p = compute_unit_price(_Unit(), _Type(supply=Decimal("0.5")), _Base(unit_price=1), [])
        assert p == Decimal(1)

    def test_float_contamination_blocked(self):
        """★머니패스 Decimal 정합: 단가/면적/가중치에 float 가 섞여도 부동소수 오차 없이 정확.
        0.1+0.2 부동소수(0.30000000000000004) 같은 누적오차가 가격에 새지 않는다."""
        # float 단가 0.1원/㎡ × float 면적 3.0㎡ + RATE float 0.2 = 0.3×1.2 = 0.36 → HALF_UP → 0.
        # 핵심은 'Decimal(str())' 정규화로 0.1*3 이 정확히 0.3 으로 잡히는 것.
        w = [_Weight(basis="RATE", value=0.2)]
        p = compute_unit_price(_Unit(), _Type(supply=3.0), _Base(unit_price=0.1), w)
        # 0.1*3=0.3, ×1.2=0.36 → HALF_UP(정수) → 0. float 오차였다면 0.36000000004 라도 결과는 0.
        assert p == Decimal(0)
        # 더 또렷한 케이스: 단가 10원/㎡ × 3.0 × (1+0.2) = 36 정확.
        p2 = compute_unit_price(_Unit(), _Type(supply=3.0), _Base(unit_price=10), [_Weight("RATE", 0.2)])
        assert p2 == Decimal(36)

    def test_none_base_price_is_zero(self):
        p = compute_unit_price(_Unit(), _Type(supply=100), _Base(unit_price=None), [])
        assert p == Decimal(0)


# ── _match_weights: 차원별 매칭(FLOOR/LINE/ASPECT/CUSTOM) + 우선순위 정렬 ────────────
class TestMatchWeights:
    def test_floor_match(self):
        u = _Unit(floor=10)
        ws = [_Weight(dimension="FLOOR", match_key="10"), _Weight(dimension="FLOOR", match_key="20")]
        out = _match_weights(u, ws, {})
        assert len(out) == 1 and out[0].match_key == "10"

    def test_custom_always_matches(self):
        u = _Unit()
        out = _match_weights(u, [_Weight(dimension="CUSTOM")], {})
        assert len(out) == 1

    def test_group_weights_appended(self):
        u = _Unit()
        g = _Weight(basis="RATE", value=0.03, priority=10)
        out = _match_weights(u, [], {u.id: [g]})
        assert g in out

    def test_priority_desc_sort(self):
        u = _Unit()
        lo = _Weight(dimension="CUSTOM", priority=1)
        hi = _Weight(dimension="CUSTOM", priority=9)
        out = _match_weights(u, [lo, hi], {})
        assert out[0] is hi and out[1] is lo


# ── decompose: 구성요소 합 = 분양가(잔차 0)·ROUND_HALF_UP·CAP 모드 ─────────────────
class TestDecompose:
    def test_sum_equals_price_residual_absorbed(self):
        """★머니패스 핵심: Σ구성 = 분양가(잔차 0). RATE 비율 합이 1이 아니어도 마지막 RATE 가 흡수.
        반올림 누적으로 어긋나던 1~몇 원 잔차를 마지막 RATE 구성에 명시 흡수한다."""
        price = Decimal(100_000_003)  # 홀수(반올림 잔차 유발)
        comps = [_Comp("LAND", "RATE", 0.3), _Comp("BUILD", "RATE", 0.65), _Comp("CUSTOM", "FIXED", 50_000)]
        rows = decompose(price, comps, "GENERAL")
        assert sum(r["amount"] for r in rows) == price  # 잔차 0 불변

    def test_residual_goes_to_last_rate_component(self):
        """잔차는 '마지막 RATE 구성'에 흡수(FIXED 는 불변)."""
        price = Decimal(100_000_003)
        comps = [_Comp("LAND", "RATE", 0.3), _Comp("BUILD", "RATE", 0.65), _Comp("CUSTOM", "FIXED", 50_000)]
        rows = decompose(price, comps, "GENERAL")
        by_type = {r["type"]: r["amount"] for r in rows}
        assert by_type["LAND"] == Decimal(30_000_001)  # 100,000,003 × 0.3 = 30,000,000.9 → HALF_UP 30,000,001
        assert by_type["CUSTOM"] == Decimal(50_000)     # FIXED 불변
        # BUILD 가 잔차 흡수: price − LAND − CUSTOM = 100,000,003 − 30,000,001 − 50,000 = 69,950,002.
        assert by_type["BUILD"] == Decimal(69_950_002)

    def test_fixed_not_adjusted_no_rate(self):
        """RATE 구성이 하나도 없으면(전부 FIXED) 잔차를 강제로 끼워넣지 않는다(구성 정의 그대로)."""
        price = Decimal(100_000)
        comps = [_Comp("LAND", "FIXED", 30_000), _Comp("BUILD", "FIXED", 60_000)]
        rows = decompose(price, comps, "GENERAL")
        # 합(90,000)≠price(100,000)이지만 FIXED 만이라 잔차를 억지로 흡수하지 않음(정직).
        assert sum(r["amount"] for r in rows) == Decimal(90_000)

    def test_cap_mode_excludes_custom(self):
        """CAP(상한제): CUSTOM(업무대행비) 제외, 남은 RATE 가 price 로 재정합."""
        price = Decimal(100_000_000)
        comps = [_Comp("LAND", "RATE", 0.3), _Comp("BUILD", "RATE", 0.65), _Comp("CUSTOM", "FIXED", 50_000)]
        rows = decompose(price, comps, "CAP")
        types = [r["type"] for r in rows]
        assert "CUSTOM" not in types
        assert sum(r["amount"] for r in rows) == price  # 남은 구성 합 = price

    def test_vat_on_final_amount(self):
        """★VAT 는 잔차 보정 '후' 금액 기준 — 보정 전 금액으로 매기면 합계 어긋남."""
        price = Decimal(100_000_003)
        comps = [_Comp("LAND", "RATE", 0.3, vat=True), _Comp("BUILD", "RATE", 0.65, vat=False),
                 _Comp("CUSTOM", "FIXED", 50_000)]
        rows = decompose(price, comps, "GENERAL")
        land = next(r for r in rows if r["type"] == "LAND")
        # LAND amount 30,000,001 × 10% = 3,000,000.1 → HALF_UP 3,000,000.
        assert land["vat"] == (land["amount"] * VAT).quantize(Q, ROUND_HALF_UP)
        # VAT 미적용 구성은 0.
        build = next(r for r in rows if r["type"] == "BUILD")
        assert build["vat"] == Decimal(0)

    def test_empty_comps(self):
        assert decompose(Decimal(100_000), [], "GENERAL") == []

    def test_float_price_normalized(self):
        """price 에 float 가 들어와도 Decimal 정규화(부동소수 오차 차단)."""
        rows = decompose(100_000.0, [_Comp("LAND", "RATE", 1.0)], "GENERAL")
        assert rows[0]["amount"] == Decimal(100_000)

    def test_normal_rows_carry_no_warning(self):
        """정상 구성(ΣRATE≈1)은 warning=None(거짓 경고 금지)."""
        price = Decimal(100_000_003)
        comps = [_Comp("LAND", "RATE", 0.3), _Comp("BUILD", "RATE", 0.65), _Comp("CUSTOM", "FIXED", 50_000)]
        rows = decompose(price, comps, "GENERAL")
        assert all(r["warning"] is None for r in rows)


# ── decompose 적대적 엣지(iter-2): 왜곡 회귀 차단 — 음수/과배분/팽창/음수 방어 ──────────────
class TestDecomposeAdversarial:
    def test_fixed_exceeds_price_no_negative_amount(self):
        """★① ΣFIXED>price: 정액 합이 분양가 초과 → 흡수 금지·음수 amount 0건·경고.
        흡수했다면 마지막 RATE 가 음수가 되어 음수 amount·음수 VAT 가 회계로 샜을 케이스."""
        price = Decimal(1_000_000)
        comps = [_Comp("CUSTOM", "FIXED", 900_000), _Comp("CUSTOM2", "FIXED", 700_000),
                 _Comp("BUILD", "RATE", 0.5, vat=True)]
        rows = decompose(price, comps, "GENERAL")
        # 어떤 행도 음수 amount/vat 가 아니어야 한다(회계 음수 전파 0).
        assert all(r["amount"] >= 0 for r in rows)
        assert all(r["vat"] >= 0 for r in rows)
        # 흡수 금지이므로 BUILD 는 설정 비율 그대로(0.5×price=500,000), 잔차를 억지로 안 먹음.
        build = next(r for r in rows if r["type"] == "BUILD")
        assert build["amount"] == Decimal(500_000)
        assert all(r["warning"] for r in rows)  # 모든 행에 경고 부착(정직)

    def test_rate_over_allocation_warns_no_absorption(self):
        """★② ΣRATE>1 과배분: 비율 합 1.5 → 흡수하면 마지막 RATE 가 음수/왜곡 → 흡수 금지·경고.
        흡수했다면 BUILD 가 음수 잔차를 먹어 비율이 크게 어긋났을 케이스."""
        price = Decimal(100_000_000)
        comps = [_Comp("LAND", "RATE", 0.8), _Comp("BUILD", "RATE", 0.7)]  # ΣRATE=1.5
        rows = decompose(price, comps, "GENERAL")
        # 흡수 금지 → BUILD 는 설정 0.7 그대로(0.7×price=70,000,000). 음수 0.
        build = next(r for r in rows if r["type"] == "BUILD")
        assert build["amount"] == Decimal(70_000_000)
        assert all(r["amount"] >= 0 for r in rows)
        assert all(r["warning"] for r in rows)

    def test_single_rate_under_allocation_no_inflation(self):
        """★③ ΣRATE<1 단일 LAND RATE 0.3: 흡수하면 토지비 30%→100% 팽창(왜곡) → 흡수 금지·경고.
        토지비가 분양가 전액으로 둔갑하던 회계 왜곡을 차단한다."""
        price = Decimal(100_000_000)
        comps = [_Comp("LAND", "RATE", 0.3)]
        rows = decompose(price, comps, "GENERAL")
        land = next(r for r in rows if r["type"] == "LAND")
        # 흡수 금지 → 설정 비율 그대로 30,000,000 (100,000,000 으로 팽창하지 않음).
        assert land["amount"] == Decimal(30_000_000)
        assert land["warning"]  # 왜곡 경고 부착

    def test_normal_small_residual_still_absorbed(self):
        """무회귀 가드: ΣRATE 가 정확히 1 인 정상 구성은 반올림 잔차만 마지막 RATE 가 흡수(왜곡 아님)."""
        price = Decimal(100_000_001)  # 홀수(반올림 잔차)
        comps = [_Comp("LAND", "RATE", 0.4), _Comp("BUILD", "RATE", 0.6)]  # ΣRATE=1.0
        rows = decompose(price, comps, "GENERAL")
        assert sum(r["amount"] for r in rows) == price  # 잔차 0(흡수 정상 동작)
        assert all(r["warning"] is None for r in rows)  # 정상 → 경고 없음

    def test_mid_distortion_large_ratio_rate_blocked(self):
        """★[iter-4 HIGH·중간왜곡] ΣRATE 0.9(LAND 0.3 + BUILD 0.6): 잔차 10% 가 BUILD 0.6→0.7 로
        흡수되면 절대(0.10<0.20)·상대(0.167<0.5) 둘 다 통과해 과거엔 묵음 팽창됐다(건축비 60%→70%,
        VAT 과세표준 팽창). 흡수 절대변화량(|잔차|/흡수전 금액=16.7%>10%) 기준으로 흡수를 취소·경고."""
        price = Decimal(100_000_000)
        comps = [_Comp("LAND", "RATE", 0.3), _Comp("BUILD", "RATE", 0.6, vat=True)]  # ΣRATE=0.9
        rows = decompose(price, comps, "GENERAL")
        build = next(r for r in rows if r["type"] == "BUILD")
        # 흡수 금지 → BUILD 는 설정 0.6 그대로(60,000,000). 0.7(70,000,000)로 팽창하지 않음.
        assert build["amount"] == Decimal(60_000_000)
        assert build["warning"]  # 중간왜곡 경고 부착
        # VAT 도 팽창 전(설정 비율) 금액 기준 — 과세표준이 부풀지 않음.
        assert build["vat"] == (Decimal(60_000_000) * VAT).quantize(Q, ROUND_HALF_UP)

    def test_legit_095_rate_with_fixed_still_absorbed(self):
        """무회귀 가드: ΣRATE 0.95 + 소액 FIXED 의 합법 흡수(|잔차|/구성금액≈7.6%<10%)는 그대로 흡수.
        중간왜곡 가드가 정상 구성을 과적발하지 않음을 고정(거짓 경고 0)."""
        price = Decimal(100_000_003)
        comps = [_Comp("LAND", "RATE", 0.3), _Comp("BUILD", "RATE", 0.65), _Comp("CUSTOM", "FIXED", 50_000)]
        rows = decompose(price, comps, "GENERAL")
        assert sum(r["amount"] for r in rows) == price  # 잔차 0(흡수 정상)
        assert all(r["warning"] is None for r in rows)   # 정상 → 경고 없음

    def test_persist_guard_blocks_negative_amount(self):
        """★[영속 불변 가드] generate_price_table 의 amount/vat>=0 가드(엔진 레벨)와 일관 — decompose
        가 음수 방어를 거쳐 음수 amount 를 내보내지 않음을 어떤 엣지에서도 보장."""
        # 정액이 분양가를 살짝 초과하는 경계(흡수 금지) — 음수가 없어야 한다.
        price = Decimal(500_000)
        comps = [_Comp("CUSTOM", "FIXED", 500_001), _Comp("BUILD", "RATE", 1.0, vat=True)]
        rows = decompose(price, comps, "GENERAL")
        assert all(r["amount"] >= 0 and r["vat"] >= 0 for r in rows)


# ── _extract_dong: 동/읍/면/리 파싱 견고성(도로명=None 정직) ──────────────────────
class TestExtractDong:
    def test_dong(self):
        assert _extract_dong("경기도 용인시 수지구 신봉동 123") == "신봉동"

    def test_dong_before_road_name(self):
        """동 뒤에 도로명이 와도 마지막 행정동(동/읍/면/리)을 잡는다."""
        assert _extract_dong("서울특별시 강남구 역삼동 테헤란로 152") == "역삼동"

    def test_dong_with_ga_suffix(self):
        """'성수동1가' 같은 표기에서 동 토큰을 추출."""
        assert _extract_dong("서울 성동구 성수동1가 656") == "성수동"

    def test_road_name_only_returns_none(self):
        """★정직성: 도로명주소(동 없음)는 가짜로 만들지 않고 None."""
        assert _extract_dong("경기도 화성시 동탄대로 123") is None

    def test_eup_myeon_ri(self):
        assert _extract_dong("강원도 평창군 대관령면") == "대관령면"

    def test_none_and_empty(self):
        assert _extract_dong(None) is None
        assert _extract_dong("") is None

    def test_no_digit_false_match(self):
        """숫자 접두('101동' 같은 건물 동)는 한글 토큰이 아니라 행정동으로 오인하지 않는다."""
        # 주소에 행정동이 있으면 그걸, 없으면 None.
        assert _extract_dong("우동") == "우동"  # 부산 우동(짧은 동명)


# ── _cost_validation: 원가엔진 graceful + 시장가<원가 경고 ──────────────────────────
class TestCostValidation:
    def test_no_tiers_returns_dict_or_none(self):
        """tiers 비어도 원가엔진 가용 시 dict(또는 미가용 시 None) — 예외 없이 graceful."""
        out = _cost_validation("APT", [], None)
        assert out is None or isinstance(out, dict)

    def test_zero_precise_cost_falls_back_to_ssot(self):
        """정밀공사비 0 전달 시엔 표준단가(SSOT)로 폴백해 검증한다(0 으로 검증 생략이 아님).
        ★머니패스: 시장가가 원가를 회수하는지 항상 교차확인하므로, 정밀공사비 미전달이어도
        표준단가 기반 검증이 수행돼 cost_basis='표준단가(SSOT)' 가 된다."""
        out = _cost_validation("APT", [{"per_pyeong_10k": 3000}], 0)
        if out is None:
            pytest.skip("원가엔진 미가용(graceful None) — sandbox 의존성 부재")
        assert out["cost_basis"] == "표준단가(SSOT)"
        assert out["construction_cost_per_gfa_won"] > 0  # 0 이 아닌 표준단가 사용

    def test_high_price_is_cost_viable(self):
        """평당 충분히 높은 분양가는 원가 회수 가능(viable)·경고 없음.
        원가 GFA당 200만원 → 공급평당 원가 ≈ 200×1.15/0.70/10000×3.305 ≈ 1,086만/평,
        최저선 ≈ 1,086/0.65 ≈ 1,671만/평. 보수안 3,000만/평 > 최저선 → viable."""
        tiers = [{"per_pyeong_10k": 3000}]
        out = _cost_validation("APT", tiers, 2_000_000)  # 정밀공사비 GFA당 200만원
        if out is None:
            pytest.skip("원가엔진 미가용(graceful None) — 검증 생략")
        assert out["conservative_viable"] is True
        assert out["warning"] is None
        # tier 에 원가비율·마진 부착(반쪽출하 아님).
        assert "construction_cost_ratio_pct" in tiers[0]
        assert "margin_over_construction_pct" in tiers[0]

    def test_low_price_warns_not_fake(self):
        """★정직 가드: 시장가가 원가기반 최저선 미만이면 경고(가짜로 올리지 않음·경고만).
        보수안 100만/평은 어떤 원가기반 최저선보다도 낮아 viable=False·경고."""
        tiers = [{"per_pyeong_10k": 100}]  # 비현실적으로 낮은 분양가
        out = _cost_validation("APT", tiers, 2_000_000)
        if out is None:
            pytest.skip("원가엔진 미가용(graceful None)")
        assert out["conservative_viable"] is False
        assert out["warning"]  # 경고 문구 존재(빈/None 아님)


# ── solve_base_for_target: 역산 math·엣지·round-trip 잔차(gap_10k) ─────────────────
# 가짜 AsyncSession 으로 solve_base 의 'base 계산·엣지 가드'를 검증한다. generate_price_table/
# project_revenue 는 monkeypatch 로 대체해 base 가 올바르게 산출·반영되는지에 집중한다.
class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return list(self._rows)


class _SolveDB:
    """solve_base_for_target 의 select(...) 호출 순서를 흉내내는 가짜 세션.

    호출 순서(스칼라): ①weights ②base_rows ③groups ④(그룹별 members) ⑤types ⑥units ⑦price_tables.
    그룹이 없으면 ④는 생략된다. add/flush 는 no-op(역산 base 계산까지만 검증).
    """
    def __init__(self, weights, base_rows, types, units, price_tables, groups=None):
        self._seq = [
            _ScalarsResult(weights),       # ① weights
            _ScalarsResult(base_rows),     # ② base_rows
            _ScalarsResult(groups or []),  # ③ groups (없으면 빈 → members 루프 미진입)
            _ScalarsResult(types),         # ⑤ types (그룹 0 이면 바로 여기)
            _ScalarsResult(units),         # ⑥ units
            _ScalarsResult(price_tables),  # ⑦ price tables (opt_prem)
        ]
        self._call = 0
        self.added = []

    async def execute(self, *_a, **_k):
        r = self._seq[self._call]
        self._call += 1
        return r

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


class _TBase:
    """base_rows / type 공용 — id 와 type_id 를 같게 둬 단일 타입 시나리오를 단순화."""
    def __init__(self, tid, supply, basis="PER_AREA", area_kind="supply", round_factor=1, unit_price=0):
        self.id = tid
        self.type_id = tid
        self.supply_area = supply
        self.contract_area = None
        self.exclusive_area = None
        self.type_name = "84A"
        self.basis = basis
        self.base_unit_price = unit_price
        self.base_area_kind = area_kind
        self.round_factor = round_factor


class _UnitRow:
    def __init__(self, uid, type_id, floor=10, line="1", aspect="S"):
        self.id = uid
        self.type_id = type_id
        self.floor = floor
        self.line = line
        self.aspect = aspect


@pytest.fixture
def _patch_regen(monkeypatch):
    """generate_price_table/project_revenue 를 가짜로 대체 — solve_base 의 base 계산에 집중.
    project_revenue 는 '선형모델 그대로 달성'(반올림 없음)을 흉내내 round-trip 을 검증한다."""
    from app.services.sales.pricing import engine

    captured = {}

    async def _fake_generate(db, site_id, round_id, by=None, collect=None):
        # ★[iter-4 자가회귀 차단] production generate_price_table 은 collect= 키워드(경고 수집용)를
        #   넘긴다. 목 시그니처가 그걸 안 받으면 TypeError 로 solve_base 경로가 통째로 깨진다
        #   (시그니처 표류=자가회귀). 실엔진과 동일하게 collect 를 받아 흡수한다(여기선 미사용).
        return len(captured.get("units", []))

    async def _fake_revenue(db, site_id, round_id):
        # 반영된 base 로 선형 총매출(반올림 무시) — solve 가 넘긴 achieved 가 target 근처인지 검증용.
        return {"total_revenue_10k": captured.get("achieved_10k", 0),
                "units_priced": len(captured.get("units", []))}

    monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
    monkeypatch.setattr(engine, "project_revenue", _fake_revenue)
    return captured


# ── 시그니처 계약(iter-4 자가회귀 재발방지): generate_price_table 이 collect= 를 받아야 한다 ──────
# solve_base_for_target / 라우터(actions.pricing_generate)가 collect= 키워드로 경고를 수집하므로,
# generate_price_table 시그니처에서 collect 가 사라지면 TypeError 로 머니패스가 통째로 깨진다.
# 목(_fake_generate)이 production 과 시그니처가 어긋나 5건이 한꺼번에 FAIL 했던 자가회귀를, 이
# 계약테스트로 영구 고정한다(목이 아니라 '진짜' 엔진 시그니처를 검사 — 시그니처 표류 즉시 적발).
class TestGenerateSignatureContract:
    def test_generate_price_table_accepts_collect_kw(self):
        """★production generate_price_table 이 collect= 키워드를 수용해야 한다(시그니처 표류 차단)."""
        import inspect

        from app.services.sales.pricing.engine import generate_price_table
        params = inspect.signature(generate_price_table).parameters
        assert "collect" in params, "generate_price_table 시그니처에 collect= 가 있어야 한다(경고 수집 머니패스)"
        # by= 도 함께 유지(호출부 무회귀) — 둘 다 키워드로 받아야 라우터·solve_base 가 안 깨진다.
        assert "by" in params


class TestSolveBaseForTarget:
    async def test_no_units_returns_not_ok(self, _patch_regen):
        """세대/면적 없음(M<=0) → ok:False(억지 0 분양가 금지)."""
        from app.services.sales.pricing.engine import solve_base_for_target
        db = _SolveDB(weights=[], base_rows=[], types=[], units=[], price_tables=[])
        out = await solve_base_for_target(db, "site", "round", 100_000)
        assert out["ok"] is False
        assert "역산 불가" in out["note"]

    async def test_zero_target_rejected(self, _patch_regen):
        """목표 0 이하 → ok:False(입력단계 차단)."""
        from app.services.sales.pricing.engine import solve_base_for_target
        db = _SolveDB(weights=[], base_rows=[], types=[], units=[], price_tables=[])
        out = await solve_base_for_target(db, "site", "round", 0)
        assert out["ok"] is False
        assert "0보다" in out["note"]

    async def test_negative_target_rejected(self, _patch_regen):
        from app.services.sales.pricing.engine import solve_base_for_target
        db = _SolveDB(weights=[], base_rows=[], types=[], units=[], price_tables=[])
        out = await solve_base_for_target(db, "site", "round", -5)
        assert out["ok"] is False

    async def test_base_solved_exact_no_weights(self, _patch_regen):
        """단일 타입·1세대(공급 100㎡)·가중치 없음 → base = target_won / 면적.
        목표 10,000만원(=1억원) / 100㎡ = 1,000,000원/㎡."""
        from app.services.sales.pricing.engine import solve_base_for_target
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        tb = _TBase(tid, supply=100, round_factor=1)
        db = _SolveDB(weights=[], base_rows=[tb], types=[tb],
                      units=[_UnitRow(uid, tid)], price_tables=[])
        _patch_regen["units"] = [uid]
        # 목표 1억원 = 10,000만원.
        out = await solve_base_for_target(db, "site", "round", 10_000)
        assert out["ok"] is True
        # base = 100,000,000원 / 100㎡ = 1,000,000원/㎡.
        assert out["base_unit_price"] == 1_000_000

    async def test_base_solved_with_rate_weight(self, _patch_regen):
        """RATE +25% 가중치 1세대: M = 100 × 1 × 1.25 = 125. base = 100,000,000 / 125 = 800,000."""
        from app.services.sales.pricing.engine import solve_base_for_target
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        tb = _TBase(tid, supply=100, round_factor=1)
        w = _Weight(basis="RATE", value=0.25, dimension="CUSTOM")
        db = _SolveDB(weights=[w], base_rows=[tb], types=[tb],
                      units=[_UnitRow(uid, tid)], price_tables=[])
        _patch_regen["units"] = [uid]
        out = await solve_base_for_target(db, "site", "round", 10_000)
        assert out["ok"] is True
        assert out["base_unit_price"] == 800_000

    async def test_gap_10k_present_and_signed(self, _patch_regen):
        """★round-trip 잔차(gap_10k) 노출: 목표−실달성. 정직성(가짜 수렴 위장 금지)."""
        from app.services.sales.pricing.engine import solve_base_for_target
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        tb = _TBase(tid, supply=100, round_factor=1)
        db = _SolveDB(weights=[], base_rows=[tb], types=[tb],
                      units=[_UnitRow(uid, tid)], price_tables=[])
        _patch_regen["units"] = [uid]
        _patch_regen["achieved_10k"] = 9_998  # 목표 10,000 에 2만원(=2 in 10k) 미달(반올림 누적 가정)
        out = await solve_base_for_target(db, "site", "round", 10_000)
        assert out["achieved_total_10k"] == 9_998
        assert out["gap_10k"] == 2  # 목표 10,000 − 달성 9,998 = +2(미달)

    async def test_gap_won_round_trip_no_floor_bias(self, monkeypatch, _patch_regen):
        """★[iter-2 floor 편향 제거] gap 을 원(KRW) 기반·round 로 산출 — 실초과(목표 < 실달성)도
        정확히 음수 gap 으로 잡힌다(절단 total_revenue_10k 로 빼면 항상 양수 미달로 치우치던 버그).
        실달성 1억원 + 9,000원(=목표 1억원을 9,000원 초과) → gap_won=-9,000, gap_10k=round(-0.9)=-1."""
        from app.services.sales.pricing import engine

        async def _rev_won(db, site_id, round_id):
            # 원기반 총매출 제공: 목표(1억=100,000,000원)를 9,000원 초과 달성.
            return {"total_revenue_10k": 10_000, "total_revenue_won": 100_009_000, "units_priced": 1}

        monkeypatch.setattr(engine, "project_revenue", _rev_won)
        tid = uuid_mod.uuid4(); uid = uuid_mod.uuid4()
        tb = _TBase(tid, supply=100, round_factor=1)
        db = _SolveDB(weights=[], base_rows=[tb], types=[tb],
                      units=[_UnitRow(uid, tid)], price_tables=[])
        out = await engine.solve_base_for_target(db, "site", "round", 10_000)
        # 목표 100,000,000 − 달성 100,009,000 = −9,000(초과). round(-9000/10000)=round(-0.9)=-1.
        assert out["gap_won"] == -9_000
        assert out["gap_10k"] == -1
        assert out["achieved_total_won"] == 100_009_000

    async def test_determinism_same_inputs_same_base(self, _patch_regen):
        """결정론: 동일 입력 → 동일 base(부동소수 비결정성 없음)."""
        from app.services.sales.pricing.engine import solve_base_for_target
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()

        def _mk():
            tb = _TBase(tid, supply=84.97, round_factor=1)
            return _SolveDB(weights=[], base_rows=[tb], types=[tb],
                            units=[_UnitRow(uid, tid)], price_tables=[])

        _patch_regen["units"] = [uid]
        a = await solve_base_for_target(_mk(), "site", "round", 33_333)
        b = await solve_base_for_target(_mk(), "site", "round", 33_333)
        assert a["base_unit_price"] == b["base_unit_price"]


# ── apply_group_pricing 멱등 race 백스톱(iter-4 HIGH): 동시 더블서브밋 → 둘째 23505 graceful 재사용 ──
# 동시 트랜잭션 2건이 거의 동시에 '없음'을 보고 둘 다 INSERT 하는 race 에서, 둘째 INSERT 가
# IntegrityError(23505)로 터질 때 미가공 500 이 아니라 기존 그룹 재사용(group_reused=True)으로
# graceful 매핑됨을 단언한다(DB 부분 유니크 인덱스가 백스톱, 서비스가 SAVEPOINT 로 흡수).
class _Result:
    """select(...) 결과 — scalars().first()/iteration 둘 다 지원(엔진이 두 형태로 소비)."""
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _Nested:
    """begin_nested() 의 async 컨텍스트(SAVEPOINT) 흉내 — 본문서 flush 가 IntegrityError 면 그대로 전파."""
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False  # 예외를 삼키지 않음(엔진의 try/except IntegrityError 가 받도록)


class _ExistingGroup:
    """race 에서 먼저 INSERT 된 '기존' 그룹(둘째 트랜잭션이 재조회로 발견·재사용할 대상)."""
    def __init__(self):
        self.id = uuid_mod.uuid4()
        self.basis = None
        self.value = None
        self.priority = None
        self.selector = {}


class _RaceDB:
    """apply_group_pricing(RATE)의 race 경로를 흉내내는 가짜 세션.

    호출 순서: ①find_by_idem(없음) → begin_nested→add→flush(IntegrityError) →
              ②find_by_idem(기존 그룹 발견) → 멤버조회(없음) → flush(ok) →
              generate_price_table/project_revenue(monkeypatch 로 대체).
    """
    def __init__(self, existing):
        self._existing = existing
        self._selects = 0
        self._flushes = 0
        self.added = []

    async def execute(self, *_a, **_k):
        self._selects += 1
        if self._selects == 1:
            return _Result([])          # ① 최초 조회: 없음 → INSERT 시도
        if self._selects == 2:
            return _Result([self._existing])  # ② race 충돌 후 재조회: 기존 그룹 발견
        return _Result([])              # 멤버 조회 등: 빈 결과

    def begin_nested(self):
        return _Nested()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self._flushes += 1
        if self._flushes == 1:
            # SAVEPOINT 안 첫 flush(=둘째 트랜잭션의 INSERT)에서 23505 → IntegrityError.
            from sqlalchemy.exc import IntegrityError
            raise IntegrityError("INSERT", {}, Exception("duplicate key value (23505)"))
        # 이후 flush 는 정상.

    async def commit(self):
        pass

    async def rollback(self):
        pass


class TestApplyGroupPricingRace:
    async def test_double_submit_integrity_error_graceful_reuse(self, monkeypatch):
        """★동시 더블서브밋: 둘째 INSERT 23505 → 미가공 500 금지, 기존 그룹 재사용(group_reused)."""
        from app.services.sales.pricing import engine

        async def _fake_generate(db, site_id, round_id, by=None, collect=None):
            return 1

        async def _fake_revenue(db, site_id, round_id):
            return {"total_revenue_10k": 12345, "units_priced": 1}

        monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
        monkeypatch.setattr(engine, "project_revenue", _fake_revenue)

        existing = _ExistingGroup()
        db = _RaceDB(existing)
        res = await engine.apply_group_pricing(
            db, uuid_mod.uuid4(), uuid_mod.uuid4(), [uuid_mod.uuid4()],
            mode="RATE", value=0.05, group_name="로열층", idempotency_key="k1")
        assert res["ok"] is True
        assert res["group_reused"] is True          # 23505 를 기존 그룹 재사용으로 graceful 매핑
        assert existing.value == 0.05               # 재사용 그룹에 최신 입력 반영(가산 1회분)
        assert res["total_revenue_10k"] == 12345    # 머니패스 정상 완료(500 누출 0)

    async def test_double_submit_unrecoverable_reraises_not_silent(self, monkeypatch):
        """★silent-fail 금지: 23505 후 재조회도 비면(인덱스 미적용 등) 0/빈값 은폐 대신 예외 전파."""
        from sqlalchemy.exc import IntegrityError

        from app.services.sales.pricing import engine

        async def _fake_generate(db, site_id, round_id, by=None, collect=None):
            return 1

        async def _fake_revenue(db, site_id, round_id):
            return {"total_revenue_10k": 0, "units_priced": 0}

        monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
        monkeypatch.setattr(engine, "project_revenue", _fake_revenue)

        class _RaceDBNoReuse(_RaceDB):
            async def execute(self, *_a, **_k):
                self._selects += 1
                return _Result([])  # 최초·재조회 모두 비어 있음(복구 불가)

        db = _RaceDBNoReuse(_ExistingGroup())
        with pytest.raises(IntegrityError):
            await engine.apply_group_pricing(
                db, uuid_mod.uuid4(), uuid_mod.uuid4(), [uuid_mod.uuid4()],
                mode="RATE", value=0.05, group_name="로열층", idempotency_key="k1")


# ── apply_group_pricing 멱등키 콘텐츠해시(iter-5 HIGH): 실호출형태(group_name·idem 미전송) 분리 보존 ──
# ★ 과거 회귀: 클라(프론트 PriceGroupingPanel)는 group_name·idempotency_key 를 안 보내므로, 폴백 멱등키가
#    f"{mode}:그룹"(상수)로 붕괴 → 같은 라운드의 모든 RATE 적용이 단일 그룹에 충돌. {A,B}+5% 후 {C,D}+3%
#    적용이 동일 그룹을 재사용→value 0.05→0.03 덮어쓰기+C,D 합산으로 A,B 의 +5% 가 묵음소실(분양가/매출
#    왜곡)했다. iter-5 는 멱등키를 '작업 내용 콘텐츠 해시'(mode+정렬세대ID+값)로 바꿔 distinct 선택을
#    분리 그룹으로 보존한다. 기존 TestApplyGroupPricingRace 는 idempotency_key 를 명시 전달해 이 HIGH 경로를
#    가렸으므로, 여기선 '실호출형태(idem·group_name 미전송)' 그대로 검증해 거짓신뢰를 제거한다.
class _StatefulGroupDB:
    """apply_group_pricing(RATE/FIXED)의 멱등 get-or-create 를 충실히 흉내내는 상태유지 가짜 세션.

    실 DB 없이도 '같은 멱등키면 재사용, 다른 멱등키면 새 그룹'을 검증할 수 있도록, db.add 로 들어온
    SalesPriceGroup 을 selector→idem 으로 보관하고, _find_group_by_idem 의 select 가 들어오면 그
    where 절의 idem 바인드값을 컴파일 파라미터에서 꺼내 일치하는 그룹을 돌려준다(없으면 None).
    멤버 조회(SalesPriceGroupMember)는 빈 결과(중복 없음). flush 는 no-op(IntegrityError 없음=인덱스 정상).
    """
    def __init__(self):
        self.groups: list = []          # 보관된 SalesPriceGroup(추가 순서대로)
        self.members: list = []         # 추가된 멤버(세대-그룹 매핑)
        self.add_calls = 0

    @staticmethod
    def _idem_in_stmt(stmt) -> str | None:
        # SalesPriceGroup select 의 where(selector->>'idem' == :idem) 바인드값을 컴파일 파라미터에서 추출.
        #   where 절은 (site_id, selector->>'round_id'==:round, selector->>'idem'==:idem) 순서라,
        #   값 바인드(param_N)는 ①round_id UUID ②idem 순으로 붙는다. JSONB 경로키('round_id'/'idem')는
        #   selector_N 키라 param_N 만 추리고, 그중 마지막(=idem)을 돌려준다(round_id UUID 는 '-' 포함으로 제외).
        try:
            params = stmt.compile().params
        except Exception:
            return None
        cand = [v for k, v in params.items()
                if k.startswith("param_") and isinstance(v, str) and "-" not in v]
        return cand[-1] if cand else None

    async def execute(self, stmt, *_a, **_k):
        from app.services.sales.pricing.engine import SalesPriceGroup
        try:
            entity = stmt.column_descriptions[0]["entity"]
        except Exception:
            entity = None
        # SalesPriceGroup select(=_find_group_by_idem)면 idem 일치 그룹을 돌려준다(없으면 None).
        if entity is SalesPriceGroup:
            idem = self._idem_in_stmt(stmt)
            match = [g for g in self.groups if (g.selector or {}).get("idem") == idem]
            return _Result(match)
        # 멤버 조회 등은 빈 결과(멤버 중복 없음).
        return _Result([])

    def add(self, obj):
        self.add_calls += 1
        from app.services.sales.pricing.engine import SalesPriceGroup, SalesPriceGroupMember
        if isinstance(obj, SalesPriceGroup):
            if not getattr(obj, "id", None):
                obj.id = uuid_mod.uuid4()
            self.groups.append(obj)
        elif isinstance(obj, SalesPriceGroupMember):
            self.members.append(obj)

    def begin_nested(self):
        return _Nested()

    async def flush(self):
        pass  # 인덱스 정상(중복 멱등키 없음) → 23505 없음.

    async def commit(self):
        pass

    async def rollback(self):
        pass


class TestApplyGroupPricingContentHashIdem:
    async def test_distinct_selections_stay_separate_no_value_overwrite(self, monkeypatch):
        """★[HIGH] 실호출형태(group_name·idempotency_key 미전송) 그대로 두 distinct 선택을 적용하면
        서로 다른 콘텐츠해시 멱등키 → 분리 그룹 2개 생성(재사용 0)·value 비덮어쓰기. 상수키 회귀였다면
        둘째가 첫째 그룹을 재사용(group_reused=True)하며 value 가 0.05→0.03 으로 덮어써졌을 것이다."""
        from app.services.sales.pricing import engine

        async def _fake_generate(db, site_id, round_id, by=None, collect=None):
            return 2

        async def _fake_revenue(db, site_id, round_id):
            return {"total_revenue_10k": 99999, "units_priced": 4}

        monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
        monkeypatch.setattr(engine, "project_revenue", _fake_revenue)

        db = _StatefulGroupDB()
        site_id = uuid_mod.uuid4()
        round_id = uuid_mod.uuid4()
        a, b, c, d = (uuid_mod.uuid4() for _ in range(4))

        # 첫 적용 {A,B}+5% — group_name·idempotency_key 미전송(실호출형태).
        r1 = await engine.apply_group_pricing(db, site_id, round_id, [a, b], mode="RATE", value=0.05)
        # 둘째 적용 {C,D}+3% — 역시 실호출형태(미전송).
        r2 = await engine.apply_group_pricing(db, site_id, round_id, [c, d], mode="RATE", value=0.03)

        assert r1["ok"] is True and r2["ok"] is True
        # 둘 다 새 그룹(재사용 아님) — 분리 보존.
        assert r1["group_reused"] is False
        assert r2["group_reused"] is False
        # 분리 그룹 2개가 생성됐다(상수키 붕괴였다면 1개만 존재).
        assert len(db.groups) == 2
        # 두 그룹의 멱등키가 서로 다르다(콘텐츠해시 — 선택/값이 달라 분리).
        idems = {(g.selector or {}).get("idem") for g in db.groups}
        assert len(idems) == 2
        # value 비덮어쓰기: {A,B} 그룹은 0.05, {C,D} 그룹은 0.03 그대로 보존(묵음소실 없음).
        g_ab = next(g for g in db.groups if {m.unit_id for m in db.members if m.group_id == g.id} == {a, b})
        g_cd = next(g for g in db.groups if {m.unit_id for m in db.members if m.group_id == g.id} == {c, d})
        assert float(g_ab.value) == 0.05
        assert float(g_cd.value) == 0.03

    async def test_identical_request_dedups_double_click(self, monkeypatch):
        """무회귀 가드: 같은 선택·같은 값의 반복(더블클릭/재시도)은 동일 콘텐츠해시 → 같은 그룹 재사용
        (group_reused=True)으로 흡수돼 RATE 복리가산이 안 생긴다. (회귀 해소가 멱등 자체를 깨지 않음 확인.)"""
        from app.services.sales.pricing import engine

        async def _fake_generate(db, site_id, round_id, by=None, collect=None):
            return 2

        async def _fake_revenue(db, site_id, round_id):
            return {"total_revenue_10k": 50000, "units_priced": 2}

        monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
        monkeypatch.setattr(engine, "project_revenue", _fake_revenue)

        db = _StatefulGroupDB()
        site_id = uuid_mod.uuid4()
        round_id = uuid_mod.uuid4()
        a, b = uuid_mod.uuid4(), uuid_mod.uuid4()

        r1 = await engine.apply_group_pricing(db, site_id, round_id, [a, b], mode="RATE", value=0.05)
        # 동일 요청 재전송(더블클릭) — 세대·값·모드 동일.
        r2 = await engine.apply_group_pricing(db, site_id, round_id, [b, a], mode="RATE", value=0.05)

        assert r1["group_reused"] is False  # 최초 생성
        assert r2["group_reused"] is True   # 동일 콘텐츠해시 → 기존 그룹 재사용(복리가산 차단)
        assert len(db.groups) == 1          # 그룹은 1개만(중복 생성 0)


# ── generate_price_table / project_revenue 디스패치 가짜 세션(iter-5 MED 검증용) ──────────────────
# 호출 순서에 의존하지 않고 '질의 대상 엔티티'로 결과를 돌려주는 상태유지 가짜 세션. 영속(add)되는
# 가격표·구성행을 보관해 project_revenue 가 같은 세션에서 합산·검산할 수 있게 한다.
class _GenCfg:
    def __init__(self, mode="GENERAL"):
        self.pricing_mode = mode


class _OneResult:
    """scalar_one()/scalar_one_or_none() 결과 — scalars().first() 도 지원."""
    def __init__(self, obj):
        self._obj = obj

    def scalar_one(self):
        return self._obj

    def scalar_one_or_none(self):
        return self._obj

    def scalars(self):
        return _Result([self._obj] if self._obj is not None else [])


class _SumResult:
    """group_by(...).all() 결과 — (component_type, sum(amount), sum(vat)) 튜플들."""
    def __init__(self, tuples):
        self._t = tuples

    def all(self):
        return list(self._t)


class _GenDB:
    """generate_price_table·project_revenue 가 쓰는 select/delete/add/flush 를 엔티티별로 디스패치.

    SalesUnitPriceTable 조회는 두 곳에서 형태가 다르다: generate 는 unit+round 단건(scalar_one_or_none),
    project_revenue 는 site+round 전체(scalars). 컴파일 파라미터에 unit UUID(여러 '-' 포함값 2개 이상)가
    있으면 단건 조회로 보고 None(신규 생성 유도), 아니면 영속된 전체 가격표를 돌려준다.
    """
    def __init__(self, cfg, base_rows, weights, comps, groups, types, units, members=None):
        self._cfg = cfg
        self._base_rows = base_rows
        self._weights = weights
        self._comps = comps
        self._groups = groups        # 모든 그룹(차수 무관) — round 필터는 아래에서 충실히 적용
        self._all_members = members or []  # SalesPriceGroupMember 행(그룹별 세대 매핑)
        self._types = types
        self._units = units
        self.price_tables: list = []   # 영속된 SalesUnitPriceTable
        self.breakdowns: list = []     # 영속된 SalesUnitPriceBreakdown
        self.gen_logs: list = []
        self.group_selects: list = []  # 캡처: SalesPriceGroup select 의 round 바인드(라운드필터 검증용)

    @staticmethod
    def _uuid_params(stmt):
        # selector JSONB 텍스트 비교 바인드(param_N, 문자열 UUID)만 추린다 — 그룹 round 필터값 추출용.
        try:
            return [v for k, v in stmt.compile().params.items()
                    if k.startswith("param_") and isinstance(v, str) and "-" in v]
        except Exception:
            return []

    @staticmethod
    def _all_uuid_strs(stmt):
        # 모든 바인드값을 UUID 문자열로 정규화(컬럼비교는 UUID 객체, JSONB 텍스트비교는 str) — 멤버 group_id 추출용.
        out = []
        try:
            for v in stmt.compile().params.values():
                s = str(v)
                if "-" in s and len(s) >= 32:
                    out.append(s)
        except Exception:
            pass
        return out

    async def execute(self, stmt, *_a, **_k):
        from app.services.sales.pricing.engine import (
            SalesPriceBase,
            SalesPriceComposition,
            SalesPriceGroup,
            SalesPriceGroupMember,
            SalesSiteConfig,
            SalesUnitInventory,
            SalesUnitPriceBreakdown,
            SalesUnitPriceTable,
            SalesUnitType,
        )
        # DELETE(원가구성 재생성 전 삭제) — column_descriptions 가 없는 Delete 문.
        if not hasattr(stmt, "column_descriptions"):
            self.breakdowns = []  # 단일 라운드/단일 재생성 가정 → 전량 비움.
            return _Result([])
        try:
            entity = stmt.column_descriptions[0]["entity"]
        except Exception:
            entity = None
        name = getattr(entity, "__name__", "")
        if entity is SalesSiteConfig:
            return _OneResult(self._cfg)
        if entity is SalesPriceBase:
            return _Result(self._base_rows)
        if name == "SalesPriceWeight":
            return _Result(self._weights)
        if entity is SalesPriceComposition:
            return _Result(self._comps)
        if entity is SalesPriceGroup:
            rid_vals = self._uuid_params(stmt)  # where 에 round_id(UUID)가 바인드돼야 누출 차단
            self.group_selects.append(rid_vals)
            if rid_vals:  # selector→round_id 필터를 충실히 적용(누출 차단 동작 재현)
                rid = rid_vals[-1]
                return _Result([g for g in self._groups if (g.selector or {}).get("round_id") == rid])
            return _Result(self._groups)
        if entity is SalesPriceGroupMember:
            # group_id 바인드로 그룹별 멤버를 돌려준다(라운드필터 통과한 그룹만 가산되도록).
            gids = self._all_uuid_strs(stmt)
            gid = gids[-1] if gids else None
            members = [m for m in self._all_members if str(m.group_id) == gid]
            return _Result(members)
        if entity is SalesUnitType:
            return _Result(self._types)
        if entity is SalesUnitInventory:
            return _Result(self._units)
        if entity is SalesUnitPriceTable:
            # unit+round 단건 조회(generate)는 UUID 바인드 2개(unit, round) → None(신규 생성).
            # site+round 전체 조회(project_revenue)는 UUID 바인드 2개지만 단건이 아니라 전체 → 영속분.
            # 구분: generate 는 scalar_one_or_none 으로 소비하므로 _OneResult, revenue 는 scalars.
            # 여기선 '이미 영속된 가격표가 있으면 전체(revenue), 없으면 단건 None(generate)'로 단순화.
            if self.price_tables and len(self._uuid_params(stmt)) >= 1:
                # revenue 단계: 전체 반환. generate 단계의 단건 조회와 구분 위해 호출맥락 사용 어려우니,
                # generate 의 단건조회(없을 때)는 빈→None, revenue 는 채워진 전체를 준다.
                return _PriceTableDual(self.price_tables)
            return _PriceTableDual([])
        if entity is SalesUnitPriceBreakdown:
            agg: dict = {}
            for b in self.breakdowns:
                e = agg.setdefault(b.component_type, [0, 0])
                e[0] += int(b.amount or 0)
                e[1] += int(b.vat_amount or 0)
            return _SumResult([(ct, a, v) for ct, (a, v) in agg.items()])
        return _Result([])

    def add(self, obj):
        from app.services.sales.pricing.engine import (
            SalesPriceBase,
            SalesPriceGenerationLog,
            SalesUnitPriceBreakdown,
            SalesUnitPriceTable,
        )
        if isinstance(obj, SalesUnitPriceTable):
            self.price_tables.append(obj)
        elif isinstance(obj, SalesUnitPriceBreakdown):
            self.breakdowns.append(obj)
        elif isinstance(obj, SalesPriceGenerationLog):
            self.gen_logs.append(obj)
        elif isinstance(obj, SalesPriceBase):
            self._base_rows.append(obj)

    async def flush(self):
        pass


class _PriceTableDual:
    """SalesUnitPriceTable 조회 결과 — scalar_one_or_none()(generate 단건)·scalars()(revenue 전체) 겸용."""
    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return _Result(self._rows)


class _GroupRow:
    """가격그룹 가짜 행 — '그룹'(id·selector)이자 '가중치'(_match_weights/compute_unit_price 소비) 겸용.
    CUSTOM 차원이라 모든 세대에 매칭(선택 세대 전부에 가산되는 그룹 가중치를 흉내)."""
    def __init__(self, round_id, basis="RATE", value=0.0, priority=10):
        self.id = uuid_mod.uuid4()
        self.selector = {"round_id": str(round_id), "idem": f"{basis}:auto:test"}
        self.basis = basis
        self.value = value
        self.dimension = "CUSTOM"
        self.match_key = ""
        self.priority = priority


class _MemberRow:
    """SalesPriceGroupMember 가짜 행(그룹↔세대 매핑)."""
    def __init__(self, group_id, unit_id):
        self.group_id = group_id
        self.unit_id = unit_id


class TestGeneratePriceTableNegativeClamp:
    async def test_negative_price_clamped_zero_not_propagated_to_revenue(self, monkeypatch):
        """★[MED·음수 total_price 회계누출 차단] 큰 음수 FIXED 가중치로 compute_unit_price 가 음수 분양가를
        내도 base_price/total_price 가 0 으로 clamp 돼 영속되고, project_revenue 합산이 음수로 새지 않는다.
        과거엔 breakdown amount/vat 만 >=0 가드돼 total_price 음수가 매출 롤업으로 샜다."""
        from app.services.sales.pricing import engine
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        tb = _TBase(tid, supply=100, basis="PER_AREA", area_kind="supply", round_factor=1, unit_price=1000)
        # 면적 100㎡ × 1,000원 = 100,000원. 거기에 −1,000,000,000원 정액가중치 → 음수 분양가(−999,900,000).
        w = _Weight(basis="FIXED", value=-1_000_000_000, dimension="CUSTOM")
        # 원가구성은 단순 1행(LAND RATE 1.0) — clamp 된 0 가격이면 구성도 0(음수 없음).
        comps = [_Comp("LAND", "RATE", 1.0)]
        db = _GenDB(_GenCfg("GENERAL"), base_rows=[tb], weights=[w], comps=comps,
                    groups=[], types=[tb], units=[_UnitRow(uid, tid)])
        n = await engine.generate_price_table(db, uuid_mod.uuid4(), uuid_mod.uuid4())
        assert n == 1
        # 영속된 가격표가 음수가 아니다(0 으로 clamp).
        pt = db.price_tables[0]
        assert pt.base_price == Decimal(0)
        assert pt.total_price == Decimal(0)
        # 음수 분양가 clamp 경고가 종단(생성로그 snapshot)으로 노출된다(은폐 아님).
        assert db.gen_logs and db.gen_logs[0].params_snapshot["warn_count"] == 1
        # 모든 원가구성 amount/vat 도 음수 0.
        assert all(int(b.amount or 0) >= 0 and int(b.vat_amount or 0) >= 0 for b in db.breakdowns)

    async def test_revenue_sum_non_negative_after_clamp(self, monkeypatch):
        """clamp 후 project_revenue 총매출이 음수가 아님(롤업·원장 음수 누출 0)."""
        from app.services.sales.pricing import engine
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        site = uuid_mod.uuid4()
        rnd = uuid_mod.uuid4()
        tb = _TBase(tid, supply=100, basis="PER_AREA", area_kind="supply", round_factor=1, unit_price=1000)
        w = _Weight(basis="FIXED", value=-1_000_000_000, dimension="CUSTOM")
        comps = [_Comp("LAND", "RATE", 1.0)]
        db = _GenDB(_GenCfg("GENERAL"), base_rows=[tb], weights=[w], comps=comps,
                    groups=[], types=[tb], units=[_UnitRow(uid, tid)])
        await engine.generate_price_table(db, site, rnd)
        rev = await engine.project_revenue(db, site, rnd)
        assert rev["total_revenue_won"] >= 0
        assert rev["total_base_won"] >= 0
        assert rev["total_breakdown_won"] >= 0


class TestGeneratePriceTableRoundLeak:
    async def test_group_select_filters_by_round(self, monkeypatch):
        """★[MED·라운드누출 차단] generate_price_table 의 그룹 조회 where 에 round_id(UUID)가 바인드돼야
        한다(과거엔 site_id 만 → A차수 그룹이 B차수에 가산). _GenDB 가 그룹조회 round 바인드를 캡처해 확인."""
        from app.services.sales.pricing import engine
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        rnd = uuid_mod.uuid4()
        tb = _TBase(tid, supply=100, basis="PER_AREA", area_kind="supply", round_factor=1, unit_price=1000)
        db = _GenDB(_GenCfg("GENERAL"), base_rows=[tb], weights=[], comps=[_Comp("LAND", "RATE", 1.0)],
                    groups=[], types=[tb], units=[_UnitRow(uid, tid)])
        await engine.generate_price_table(db, uuid_mod.uuid4(), rnd)
        # 그룹 select 가 최소 1회 일어났고, 그 where 에 round_id(UUID 바인드)가 있었다.
        assert db.group_selects, "그룹 select 가 호출돼야 한다"
        assert any(str(rnd) in vals for vals in db.group_selects), "그룹 조회가 round_id 로 필터돼야 한다(누출 차단)"

    async def test_other_round_group_excluded(self, monkeypatch):
        """A차수 그룹은 B차수 분양가표 생성에서 제외(가산 누출 0). _GenDB 가 selector→round_id 필터를
        충실히 적용하므로, B차수 생성 시 A차수 그룹의 RATE 가중치가 가격에 섞이지 않음을 확인."""
        from app.services.sales.pricing import engine
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        round_a = uuid_mod.uuid4()
        round_b = uuid_mod.uuid4()
        tb = _TBase(tid, supply=100, basis="PER_AREA", area_kind="supply", round_factor=1, unit_price=1000)
        # A차수에 속한 그룹(RATE +50%)이 이 세대(uid)를 멤버로 가진다 — B차수 생성에 섞이면 +50% 누출.
        ga = _GroupRow(round_id=round_a, basis="RATE", value=0.5)
        members = [_MemberRow(ga.id, uid)]
        db = _GenDB(_GenCfg("GENERAL"), base_rows=[tb], weights=[], comps=[_Comp("LAND", "RATE", 1.0)],
                    groups=[ga], types=[tb], units=[_UnitRow(uid, tid)], members=members)
        # B차수로 생성 — A차수 그룹은 round 필터로 제외돼 가격이 100,000원(가산 0).
        #   필터가 깨졌다면 A그룹 +50% 가 가산돼 150,000원이 됐을 것이다(누출).
        await engine.generate_price_table(db, uuid_mod.uuid4(), round_b)
        pt = db.price_tables[0]
        assert pt.base_price == Decimal(100_000)  # 100㎡×1,000=100,000 (A그룹 +50% 미적용=누출 0)

    async def test_same_round_group_included_positive_control(self, monkeypatch):
        """양성 대조: 같은 차수의 그룹(+50%)은 정상 가산돼 150,000원이 된다 — 멤버매칭·가산 기계가
        살아있음을 확인(test_other_round_group_excluded 가 트리비얼 통과가 아님을 보증)."""
        from app.services.sales.pricing import engine
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        rnd = uuid_mod.uuid4()
        tb = _TBase(tid, supply=100, basis="PER_AREA", area_kind="supply", round_factor=1, unit_price=1000)
        g = _GroupRow(round_id=rnd, basis="RATE", value=0.5)  # 같은 차수(rnd) 그룹
        members = [_MemberRow(g.id, uid)]
        db = _GenDB(_GenCfg("GENERAL"), base_rows=[tb], weights=[], comps=[_Comp("LAND", "RATE", 1.0)],
                    groups=[g], types=[tb], units=[_UnitRow(uid, tid)], members=members)
        await engine.generate_price_table(db, uuid_mod.uuid4(), rnd)
        pt = db.price_tables[0]
        assert pt.base_price == Decimal(150_000)  # 100,000 × (1+0.5) = 150,000 (같은 차수 → 정상 가산)


# ── 멤버레벨 복리 사각 차단(iter-7 HIGH): 같은 (group, unit) 중복 멤버행이 RATE 를 2배로 복리하면 안 됨 ──
# 멤버테이블 UNIQUE(group_id,unit_id) 부재 + _attach_members SELECT-then-INSERT(TOCTOU)로 같은
# (group, unit) 멤버행이 2건 생기면, _load_group_map 이 같은 그룹을 멤버행 수만큼 append → _match_weights
# 가 2회 반환 → compute_unit_price rate_sum 이 2배(1.05→1.10) 복리됐다. _load_group_map 의 group.id 기준
# dedup(앱레벨 즉시방어)으로 멤버행이 몇 개든 한 그룹은 1회만 가산됨을 고정한다(마이그 039 는 DB 정본).
class TestGeneratePriceTableMemberDedup:
    async def test_duplicate_member_rows_no_rate_compounding(self, monkeypatch):
        """★[HIGH] 같은 그룹(+50%)에 같은 세대(uid)가 '중복 멤버행 2건'으로 매여도 가산은 1회분만
        (150,000원). dedup 이 없었다면 같은 그룹이 2회 가산돼 100,000×(1+0.5+0.5)=200,000 으로 복리됐을
        케이스. _load_group_map 의 group.id dedup 으로 복리를 by-construction 차단."""
        from app.services.sales.pricing import engine
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        rnd = uuid_mod.uuid4()
        tb = _TBase(tid, supply=100, basis="PER_AREA", area_kind="supply", round_factor=1, unit_price=1000)
        g = _GroupRow(round_id=rnd, basis="RATE", value=0.5)  # 같은 차수 그룹 +50%
        # ★중복 멤버행: 같은 (group_id, unit_id) 2건(UNIQUE 부재·TOCTOU race 가 만들 수 있는 상태).
        members = [_MemberRow(g.id, uid), _MemberRow(g.id, uid)]
        db = _GenDB(_GenCfg("GENERAL"), base_rows=[tb], weights=[], comps=[_Comp("LAND", "RATE", 1.0)],
                    groups=[g], types=[tb], units=[_UnitRow(uid, tid)], members=members)
        await engine.generate_price_table(db, uuid_mod.uuid4(), rnd)
        pt = db.price_tables[0]
        # 복리 0: 100,000 × (1+0.5) = 150,000 (200,000 으로 부풀지 않음).
        assert pt.base_price == Decimal(150_000)

    async def test_load_group_map_dedups_group_per_unit(self):
        """_load_group_map 직접 검증: 같은 그룹의 중복 멤버행이 있어도 unit 의 그룹리스트엔 그룹이 1개만
        담긴다(append 중복 0). 가산 기계(_match_weights→compute_unit_price)에 들어가기 전에 dedup."""
        from app.services.sales.pricing import engine
        uid = uuid_mod.uuid4()
        rnd = uuid_mod.uuid4()
        g = _GroupRow(round_id=rnd, basis="RATE", value=0.5)
        members = [_MemberRow(g.id, uid), _MemberRow(g.id, uid), _MemberRow(g.id, uid)]

        class _GMDB:
            async def execute(self, stmt, *_a, **_k):
                from app.services.sales.pricing.engine import SalesPriceGroup, SalesPriceGroupMember
                try:
                    entity = stmt.column_descriptions[0]["entity"]
                except Exception:
                    entity = None
                if entity is SalesPriceGroup:
                    return _Result([g])
                if entity is SalesPriceGroupMember:
                    return _Result(members)
                return _Result([])

        gmap = await engine._load_group_map(_GMDB(), uuid_mod.uuid4(), rnd)
        assert len(gmap[uid]) == 1  # 중복 멤버행 3건이어도 그룹은 1개만(복리 차단)


# ── _attach_members 멤버 중복 INSERT graceful(iter-7 HIGH): 23505 SAVEPOINT 흡수 + 멱등 ──────────────
# 동시 race 로 같은 (group_id, unit_id)를 둘째 트랜잭션이 INSERT 하면 039 부분 유니크 인덱스가
# 23505(IntegrityError)를 낸다. _attach_members 가 멤버 add 를 begin_nested(SAVEPOINT) 안에서 flush 해
# 23505 를 graceful 흡수(미가공 500 금지·중복행 0)함을 고정한다.
class _MemberRaceDB:
    """apply_group_pricing(RATE) 멤버 INSERT 의 23505 race 를 흉내내는 가짜 세션.

    흐름: ①find_by_idem(없음)→그룹 SAVEPOINT add→flush(ok·그룹 인덱스 충돌 없음)→
          멤버조회(없음)→멤버 SAVEPOINT add→flush(IntegrityError=23505)→graceful 흡수.
    멤버 flush 만 23505 를 내도록, 그룹 flush 와 멤버 flush 를 분리 카운트한다.
    """
    def __init__(self):
        self._selects = 0
        self._member_added = False
        self.groups = []
        self.members = []

    async def execute(self, stmt, *_a, **_k):
        from app.services.sales.pricing.engine import SalesPriceGroup, SalesPriceGroupMember
        try:
            entity = stmt.column_descriptions[0]["entity"]
        except Exception:
            entity = None
        if entity is SalesPriceGroup:
            return _Result([])      # _find_group_by_idem: 항상 없음(신규 INSERT 경로)
        if entity is SalesPriceGroupMember:
            return _Result([])      # 멤버조회: 없음(INSERT 시도)
        return _Result([])

    def begin_nested(self):
        return _Nested()

    def add(self, obj):
        from app.services.sales.pricing.engine import SalesPriceGroup, SalesPriceGroupMember
        if isinstance(obj, SalesPriceGroup):
            if not getattr(obj, "id", None):
                obj.id = uuid_mod.uuid4()
            self.groups.append(obj)
        elif isinstance(obj, SalesPriceGroupMember):
            self._member_added = True
            self.members.append(obj)

    async def flush(self):
        # 멤버가 막 add 된 직후의 flush(=멤버 INSERT)에서만 23505 — 그룹 flush 는 정상.
        if self._member_added:
            self._member_added = False
            from sqlalchemy.exc import IntegrityError
            raise IntegrityError("INSERT member", {}, Exception("duplicate key (23505)"))

    async def commit(self):
        pass

    async def rollback(self):
        pass


class TestAttachMembersGraceful:
    async def test_member_integrity_error_absorbed_no_500(self, monkeypatch):
        """★[HIGH] 멤버 INSERT 23505(동시 race·039 인덱스 위반) → 미가공 500 금지, SAVEPOINT 흡수 후
        머니패스 정상 완료(ok:True). 중복 멤버행이 영속되지 않아 _load_group_map 복리가 원천 차단."""
        from app.services.sales.pricing import engine

        async def _fake_generate(db, site_id, round_id, by=None, collect=None):
            return 1

        async def _fake_revenue(db, site_id, round_id):
            return {"total_revenue_10k": 777, "units_priced": 1}

        monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
        monkeypatch.setattr(engine, "project_revenue", _fake_revenue)

        db = _MemberRaceDB()
        res = await engine.apply_group_pricing(
            db, uuid_mod.uuid4(), uuid_mod.uuid4(), [uuid_mod.uuid4()], mode="RATE", value=0.05)
        assert res["ok"] is True               # 23505 흡수 → 머니패스 정상 완료(500 누출 0)
        assert res["total_revenue_10k"] == 777


# ── OVERRIDE_PSQM value<=0 silent-zero 차단(iter-7 MED): 0/음수 평당단가 거부(묵음 0 확정 금지) ──────
class TestApplyGroupPricingOverrideZeroGuard:
    async def test_override_value_zero_rejected_not_silent(self, monkeypatch):
        """★[MED] OVERRIDE_PSQM value=0 → ok:False(묵음 0 확정 금지). 과거엔 override_price=0 이 영속돼
        generate_price_table 이 base_price=0 을 경고 없이 확정(매출 0 cascade)했다."""
        from app.services.sales.pricing import engine
        db = _StatefulGroupDB()  # 진입 가드에서 막히므로 세션은 미접촉
        res = await engine.apply_group_pricing(
            db, uuid_mod.uuid4(), uuid_mod.uuid4(), [uuid_mod.uuid4()],
            mode="OVERRIDE_PSQM", value=0)
        assert res["ok"] is False
        assert "0보다 커야" in res["note"]

    async def test_override_value_negative_rejected(self, monkeypatch):
        """음수 평당단가도 거부(음수 확정금액 영속 차단)."""
        from app.services.sales.pricing import engine
        db = _StatefulGroupDB()
        res = await engine.apply_group_pricing(
            db, uuid_mod.uuid4(), uuid_mod.uuid4(), [uuid_mod.uuid4()],
            mode="OVERRIDE_PSQM", value=-1000)
        assert res["ok"] is False


# ── resolve_unit_price 패리티(iter-6 HIGH·전역스윕): 계약가 자동해소 폴백이 generate 와 동일거동 ──────
# resolve_unit_price 는 per-unit 가격표가 없을 때 기준단가에서 1세대 계약가를 직접 산정하는 폴백이다.
# 과거 이 경로만 (a) 그룹조회를 site_id 만으로 해 타 차수 그룹 RATE 가 누출됐고 (b) 음수 price clamp 가
# 없어 음수 계약 total_price 가 영속됐다. iter-6 은 두 거동을 공용헬퍼(_load_group_map·_clamp_price)로
# 추출해 generate_price_table 과 패리티를 보장한다. 여기선 그 패리티(타차수 제외·음수 0 clamp)를 고정한다.
class _ResolveDB:
    """resolve_unit_price 의 select 를 엔티티별로 디스패치하는 가짜 세션.

    소비 형태: SalesPriceBase=scalars().first() 단건, SalesUnitType=scalar_one_or_none(),
    SalesPriceWeight=scalars() 리스트, (_load_group_map)SalesPriceGroup=scalars()+selector→round_id
    필터, SalesPriceGroupMember=scalars(). 그룹의 round_id 필터를 충실히 적용해 누출 차단을 재현한다.
    """
    def __init__(self, base_rows, ttype, weights, groups, members):
        self._base_rows = base_rows
        self._ttype = ttype
        self._weights = weights
        self._groups = groups
        self._members = members

    async def execute(self, stmt, *_a, **_k):
        from app.services.sales.pricing.engine import (
            SalesPriceBase,
            SalesPriceGroup,
            SalesPriceGroupMember,
            SalesUnitType,
        )
        try:
            entity = stmt.column_descriptions[0]["entity"]
        except Exception:
            entity = None
        name = getattr(entity, "__name__", "")
        if entity is SalesPriceBase:
            return _Result(self._base_rows)
        if entity is SalesUnitType:
            return _OneResult(self._ttype)
        if name == "SalesPriceWeight":
            return _Result(self._weights)
        if entity is SalesPriceGroup:
            # _load_group_map 의 selector→round_id 필터를 재현(라운드필터 바인드값으로 거른다).
            try:
                params = stmt.compile().params
                rid = next((v for k, v in params.items()
                            if k.startswith("param_") and isinstance(v, str) and "-" in v), None)
            except Exception:
                rid = None
            if rid is not None:
                return _Result([g for g in self._groups if (g.selector or {}).get("round_id") == rid])
            return _Result(self._groups)
        if entity is SalesPriceGroupMember:
            gids = []
            try:
                for v in stmt.compile().params.values():
                    s = str(v)
                    if "-" in s and len(s) >= 32:
                        gids.append(s)
            except Exception:
                pass
            gid = gids[-1] if gids else None
            return _Result([m for m in self._members if str(m.group_id) == gid])
        return _Result([])


class _ResolveBase:
    """resolve_unit_price 용 기준단가 행(SalesPriceBase) — round_id 보유."""
    def __init__(self, site_id, round_id, type_id, basis="PER_AREA", unit_price=1000,
                 area_kind="supply", round_factor=1):
        self.site_id = site_id
        self.round_id = round_id
        self.type_id = type_id
        self.basis = basis
        self.base_unit_price = unit_price
        self.base_area_kind = area_kind
        self.round_factor = round_factor


class TestResolveUnitPriceParity:
    async def test_other_round_group_excluded(self):
        """★[HIGH·패리티] resolve 폴백도 타 차수 그룹은 제외(누출 0) — generate 의 test_other_round_group_excluded
        와 동일 거동. A차수 그룹(+50%)이 이 세대 멤버여도 B차수 해소에는 섞이지 않아 100,000원."""
        from app.services.sales.pricing.engine import resolve_unit_price
        site = uuid_mod.uuid4()
        round_a = uuid_mod.uuid4()
        round_b = uuid_mod.uuid4()
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        u = _UnitRow(uid, tid)
        # br 의 round_id 는 B차수(폴백에서 rid=round_b 로 결정).
        br = _ResolveBase(site, round_b, tid, unit_price=1000)
        ttype = _TBase(tid, supply=100)
        ga = _GroupRow(round_id=round_a, basis="RATE", value=0.5)  # A차수 그룹(+50%)
        members = [_MemberRow(ga.id, uid)]
        db = _ResolveDB(base_rows=[br], ttype=ttype, weights=[], groups=[ga], members=members)
        price = await resolve_unit_price(db, site, u)
        # A차수 그룹은 차수필터로 제외 → 100㎡×1,000=100,000 (과거 site_id 만이면 +50% 누출돼 150,000).
        assert price == 100_000

    async def test_same_round_group_included_positive_control(self):
        """양성 대조: 같은 차수 그룹(+50%)은 정상 가산(150,000) — 멤버매칭이 살아있음을 보증."""
        from app.services.sales.pricing.engine import resolve_unit_price
        site = uuid_mod.uuid4()
        rnd = uuid_mod.uuid4()
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        u = _UnitRow(uid, tid)
        br = _ResolveBase(site, rnd, tid, unit_price=1000)
        ttype = _TBase(tid, supply=100)
        g = _GroupRow(round_id=rnd, basis="RATE", value=0.5)
        members = [_MemberRow(g.id, uid)]
        db = _ResolveDB(base_rows=[br], ttype=ttype, weights=[], groups=[g], members=members)
        price = await resolve_unit_price(db, site, u)
        assert price == 150_000  # 100,000 × 1.5 (같은 차수 → 정상 가산)

    async def test_negative_price_clamped_to_none(self):
        """★[HIGH·패리티] resolve 폴백도 음수 분양가를 0 으로 clamp — generate 와 동일거동. 0 이면 None
        (계약 자동해소 대상 없음). 과거 int(price) 만이면 음수 계약 total_price 가 영속됐다."""
        from app.services.sales.pricing.engine import resolve_unit_price
        site = uuid_mod.uuid4()
        rnd = uuid_mod.uuid4()
        tid = uuid_mod.uuid4()
        uid = uuid_mod.uuid4()
        u = _UnitRow(uid, tid)
        br = _ResolveBase(site, rnd, tid, unit_price=1000)  # 100㎡×1,000=100,000
        ttype = _TBase(tid, supply=100)
        # 큰 음수 FIXED 가중치로 분양가 음수 유도(−999,900,000) → clamp 0 → None.
        w = _Weight(basis="FIXED", value=-1_000_000_000, dimension="CUSTOM")
        db = _ResolveDB(base_rows=[br], ttype=ttype, weights=[w], groups=[], members=[])
        price = await resolve_unit_price(db, site, u)
        assert price is None  # 음수 0 clamp → None(음수 계약가 영속 0)

    async def test_no_base_returns_none(self):
        """기준단가 없으면 None(억지 0/가짜 계약가 금지)."""
        from app.services.sales.pricing.engine import resolve_unit_price
        site = uuid_mod.uuid4()
        tid = uuid_mod.uuid4()
        u = _UnitRow(uuid_mod.uuid4(), tid)
        db = _ResolveDB(base_rows=[], ttype=None, weights=[], groups=[], members=[])
        assert await resolve_unit_price(db, site, u) is None


# ── apply_group_pricing 값정정 supersede(iter-6 MED): 같은 세대집합 +5%→+7% 재적용이 단일 그룹 수렴 ──
# 과거 멱등키 payload 에 value 가 포함돼, 같은 세대집합에 +5% 후 값정정 +7% 재적용이 value 가 달라
# '별도 키→별도 RATE 그룹' 2개로 공존했다. _match_weights 가 둘 다 반환→rate_sum 0.05+0.07=0.12 복리.
# iter-6 은 payload 에서 value 를 빼 같은 (mode,정렬세대ID)는 동일 키로 기존 그룹을 supersede(value 갱신)
# →단일 그룹(rate_sum=0.07)으로 수렴시킨다. distinct 세대집합 분리(iter-5 성과)는 무회귀로 함께 고정.
class TestApplyGroupPricingValueCorrectionSupersede:
    async def test_value_correction_converges_single_group(self, monkeypatch):
        """★[MED] 같은 세대집합 {A,B} 에 +5% 적용 후 값정정 +7% 재적용 → 동일 멱등키로 기존 그룹 재사용
        (supersede)·value 0.07 로 갱신. 그룹 1개만 존재(복리 +12% 없음). 과거 value 포함키였다면 그룹 2개
        공존→rate_sum 0.12 복리."""
        from app.services.sales.pricing import engine

        async def _fake_generate(db, site_id, round_id, by=None, collect=None):
            return 2

        async def _fake_revenue(db, site_id, round_id):
            return {"total_revenue_10k": 12345, "units_priced": 2}

        monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
        monkeypatch.setattr(engine, "project_revenue", _fake_revenue)

        db = _StatefulGroupDB()
        site_id = uuid_mod.uuid4()
        round_id = uuid_mod.uuid4()
        a, b = uuid_mod.uuid4(), uuid_mod.uuid4()

        # +5% 적용 — 실호출형태(group_name·idempotency_key 미전송).
        r1 = await engine.apply_group_pricing(db, site_id, round_id, [a, b], mode="RATE", value=0.05)
        # 값정정 +7% 재적용(같은 세대집합) — value 만 다름.
        r2 = await engine.apply_group_pricing(db, site_id, round_id, [b, a], mode="RATE", value=0.07)

        assert r1["group_reused"] is False   # 최초 생성
        assert r2["group_reused"] is True    # 동일 세대집합 멱등키 → 기존 그룹 supersede
        assert len(db.groups) == 1           # 단일 그룹 수렴(2개 공존 아님 → 복리 차단)
        # supersede: 그룹 value 가 정정값 0.07 로 갱신(가산 1회분=rate_sum 0.07, not 0.05+0.07=0.12).
        assert float(db.groups[0].value) == 0.07

    async def test_distinct_selections_still_separate_no_regression(self, monkeypatch):
        """무회귀 가드(iter-5 성과): value 제외 키여도 서로 다른 세대집합 {A,B}+5% 와 {C,D}+3% 는 여전히
        분리 그룹 2개·value 비덮어쓰기(distinct 분리 보존). value 를 키에서 뺀 것이 distinct 분리를 깨지 않음."""
        from app.services.sales.pricing import engine

        async def _fake_generate(db, site_id, round_id, by=None, collect=None):
            return 2

        async def _fake_revenue(db, site_id, round_id):
            return {"total_revenue_10k": 99999, "units_priced": 4}

        monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
        monkeypatch.setattr(engine, "project_revenue", _fake_revenue)

        db = _StatefulGroupDB()
        site_id = uuid_mod.uuid4()
        round_id = uuid_mod.uuid4()
        a, b, c, d = (uuid_mod.uuid4() for _ in range(4))

        r1 = await engine.apply_group_pricing(db, site_id, round_id, [a, b], mode="RATE", value=0.05)
        r2 = await engine.apply_group_pricing(db, site_id, round_id, [c, d], mode="RATE", value=0.03)

        assert r1["group_reused"] is False and r2["group_reused"] is False
        assert len(db.groups) == 2  # 분리 보존(distinct 세대집합 → 별도 그룹)
        idems = {(g.selector or {}).get("idem") for g in db.groups}
        assert len(idems) == 2      # 서로 다른 멱등키(콘텐츠해시 — 세대집합 다름)
        # value 비덮어쓰기 보존.
        g_ab = next(g for g in db.groups if {m.unit_id for m in db.members if m.group_id == g.id} == {a, b})
        g_cd = next(g for g in db.groups if {m.unit_id for m in db.members if m.group_id == g.id} == {c, d})
        assert float(g_ab.value) == 0.05
        assert float(g_cd.value) == 0.03

    async def test_same_selection_diff_mode_separate(self, monkeypatch):
        """무회귀: 같은 세대집합이라도 mode 가 다르면(RATE vs FIXED) 키 접두가 달라 분리 그룹(키 충돌 0)."""
        from app.services.sales.pricing import engine

        async def _fake_generate(db, site_id, round_id, by=None, collect=None):
            return 2

        async def _fake_revenue(db, site_id, round_id):
            return {"total_revenue_10k": 1, "units_priced": 2}

        monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
        monkeypatch.setattr(engine, "project_revenue", _fake_revenue)

        db = _StatefulGroupDB()
        site_id = uuid_mod.uuid4()
        round_id = uuid_mod.uuid4()
        a, b = uuid_mod.uuid4(), uuid_mod.uuid4()

        await engine.apply_group_pricing(db, site_id, round_id, [a, b], mode="RATE", value=0.05)
        r2 = await engine.apply_group_pricing(db, site_id, round_id, [a, b], mode="FIXED", value=100_000)
        assert r2["group_reused"] is False  # mode 접두가 달라 분리(같은 세대집합이라도)
        assert len(db.groups) == 2


# ── 멱등키 SSOT 일원화(iter-7 MED): 클라키도 콘텐츠해시 분모에 결합 — 일관 사용 시 단일 그룹 수렴 ──────
# 과거엔 클라 idempotency_key(임의문자열)면 그대로 키로 쓰고, 없으면 콘텐츠해시를 써 두 키가 같은
# (site, round) 네임스페이스를 공유했다. 그래서 '같은 세대집합'을 클라키로 일관 호출하더라도, 키가
# 콘텐츠와 무관해 멤버집합이 같은 다른 그룹과 섞일 위험이 있었다. iter-7 은 멱등키 분모를 항상
# 콘텐츠해시(mode+정렬세대ID)로 하고 클라키를 prefix 결합한다(별도 네임스페이스 금지). 같은 클라키+
# 같은 세대집합은 동일 idem 으로 수렴(복리 0), 혼용(키 전송↔미전송)은 운영 계약상 금지(주석 명문화).
class TestApplyGroupPricingIdemKeySSOT:
    async def test_same_client_key_same_units_converges_single_group(self, monkeypatch):
        """★[MED] 같은 클라키(k1)+같은 세대집합을 반복 호출하면 동일 멱등키로 기존 그룹 재사용
        (group_reused=True)·단일 그룹 수렴. 콘텐츠해시 분모 결합으로 클라키도 dedup 된다(복리 0)."""
        from app.services.sales.pricing import engine

        async def _fake_generate(db, site_id, round_id, by=None, collect=None):
            return 2

        async def _fake_revenue(db, site_id, round_id):
            return {"total_revenue_10k": 1, "units_priced": 2}

        monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
        monkeypatch.setattr(engine, "project_revenue", _fake_revenue)

        db = _StatefulGroupDB()
        site_id = uuid_mod.uuid4()
        round_id = uuid_mod.uuid4()
        a, b = uuid_mod.uuid4(), uuid_mod.uuid4()

        r1 = await engine.apply_group_pricing(
            db, site_id, round_id, [a, b], mode="RATE", value=0.05, idempotency_key="k1")
        # 같은 클라키·같은 세대집합 재전송(순서만 다름) — 동일 idem 으로 수렴해야 한다.
        r2 = await engine.apply_group_pricing(
            db, site_id, round_id, [b, a], mode="RATE", value=0.05, idempotency_key="k1")
        assert r1["group_reused"] is False  # 최초 생성
        assert r2["group_reused"] is True   # 동일 idem → 재사용(복리 차단)
        assert len(db.groups) == 1          # 단일 그룹 수렴

    async def test_client_key_idem_includes_content_hash(self, monkeypatch):
        """클라키가 들어와도 멱등키는 콘텐츠해시 분모를 포함한다(별도 네임스페이스 금지). idem 에 mode·
        클라키·콘텐츠해시 꼬리가 모두 들어감을 고정(같은 세대집합의 auto 키와 동일 hash 꼬리 공유)."""
        from app.services.sales.pricing import engine

        async def _fake_generate(db, site_id, round_id, by=None, collect=None):
            return 1

        async def _fake_revenue(db, site_id, round_id):
            return {"total_revenue_10k": 1, "units_priced": 1}

        monkeypatch.setattr(engine, "generate_price_table", _fake_generate)
        monkeypatch.setattr(engine, "project_revenue", _fake_revenue)

        db = _StatefulGroupDB()
        site_id = uuid_mod.uuid4()
        round_id = uuid_mod.uuid4()
        a = uuid_mod.uuid4()
        await engine.apply_group_pricing(
            db, site_id, round_id, [a], mode="RATE", value=0.05, idempotency_key="k1")
        idem = (db.groups[0].selector or {}).get("idem")
        assert idem.startswith("RATE:cli:k1:")  # mode·클라키 prefix + 콘텐츠해시 꼬리
        # 콘텐츠해시 꼬리(32자 hex)가 붙어 있다(콘텐츠 분모 결합).
        assert len(idem.split(":")[-1]) == 32


# ── suggest_base_price: 적정분양가 교차검증 정직성(무목업·가짜값 금지) ─────────────────
# _site_location/_trade_per_pyeong 을 monkeypatch 해 DB·MOLIT 없이 honesty 분기를 검증한다.
# (라이브 MOLIT·실 DB 는 sandbox 미가용 — deploy-pending. 여기선 정직 강등 경로만 단언.)
class TestSuggestBasePriceHonesty:
    async def test_no_address_unavailable(self, monkeypatch):
        """부지 주소 없음 → data_source='unavailable'(가짜값 생성 금지)."""
        from app.services.sales.pricing import suggest

        async def _loc(*_a, **_k):
            return None, None, None
        monkeypatch.setattr(suggest, "_site_location", _loc)
        out = await suggest.suggest_base_price(None, uuid_mod.uuid4())
        assert out["data_source"] == "unavailable"
        assert "tiers" not in out  # 가짜 3안을 만들지 않음

    async def test_no_trades_unavailable_not_fake(self, monkeypatch):
        """★무목업 핵심: 주변 실거래 0건(MOLIT 무응답) → unavailable(가짜 시세 금지)."""
        from app.services.sales.pricing import suggest

        async def _loc(*_a, **_k):
            return "경기도 용인시 수지구 신봉동 1", "4546310100100010000", "APT"

        async def _trade(*_a, **_k):
            return {"dong": {"median": None, "n": 0}, "sigungu": {"median": None, "n": 0}}

        monkeypatch.setattr(suggest, "_site_location", _loc)
        monkeypatch.setattr(suggest, "_trade_per_pyeong", _trade)
        out = await suggest.suggest_base_price(None, uuid_mod.uuid4(), bcode="4546310100")
        assert out["data_source"] == "unavailable"
        assert "가짜값 금지" in out["note"]

    async def test_fail_verdict_unavailable(self, monkeypatch):
        """신뢰도 부족(cross_validate verdict=fail) → unavailable(정직 강등·가짜값 금지)."""
        from app.services.data_validation.trust import TrustResult
        from app.services.sales.pricing import suggest

        async def _loc(*_a, **_k):
            return "경기도 용인시 수지구 신봉동 1", "4546310100100010000", "APT"

        async def _trade(*_a, **_k):
            return {"dong": {"median": 3000, "n": 3}, "sigungu": {"median": 3000, "n": 5}}

        def _cv(*_a, **_k):
            return TrustResult(None, 0.1, "fail", warnings=["표본 부족"])

        monkeypatch.setattr(suggest, "_site_location", _loc)
        monkeypatch.setattr(suggest, "_trade_per_pyeong", _trade)
        monkeypatch.setattr(suggest, "cross_validate", _cv)
        out = await suggest.suggest_base_price(None, uuid_mod.uuid4(), bcode="4546310100")
        assert out["data_source"] == "unavailable"
        assert out["trust"]["verdict"] == "fail"

    async def test_success_live_with_tiers_and_cost(self, monkeypatch):
        """정상: 신뢰 통과 → data_source='live' + 3안(보수<기준<공격) + 신뢰도 + 원가검증 부착."""
        from app.services.data_validation.trust import TrustResult
        from app.services.sales.pricing import suggest

        async def _loc(*_a, **_k):
            return "경기도 용인시 수지구 신봉동 1", "4546310100100010000", "APT"

        async def _trade(*_a, **_k):
            return {"dong": {"median": 3000, "n": 40}, "sigungu": {"median": 2900, "n": 120}}

        def _cv(*_a, **_k):
            # 전용 평당가 3,000만원, 표본 충분, pass.
            return TrustResult(3000.0, 0.85, "pass", used=["동_실거래"], consensus_ratio=1.03)

        monkeypatch.setattr(suggest, "_site_location", _loc)
        monkeypatch.setattr(suggest, "_trade_per_pyeong", _trade)
        monkeypatch.setattr(suggest, "cross_validate", _cv)
        out = await suggest.suggest_base_price(None, uuid_mod.uuid4(), bcode="4546310100")
        assert out["data_source"] == "live"
        tiers = out["tiers"]
        assert len(tiers) == 3
        # 보수<기준<공격 단조 증가(프리미엄 1.05<1.15<1.25).
        pps = [t["per_pyeong_10k"] for t in tiers]
        assert pps[0] < pps[1] < pps[2]
        # 신뢰도·근거 투명 노출(반쪽출하 아님).
        assert out["trust"]["confidence"] == 0.85
        assert out["market_reference"]["market_pp_exclusive_10k"] == 3000
        # 원가검증(2차 가드) 키 존재(None 또는 dict — graceful).
        assert "cost_validation" in out


# ── 라우터 입력검증(iter-2): 누락/형식오류 키 → 500 누출 대신 400(HTTPException) ──────────
# 가드는 DB 접근 전에 수행되므로 가짜 ctx/db 로 충분(엔진/세션 미접촉). 누락키 KeyError·잘못된
# UUID/숫자 ValueError 가 그대로 500 으로 새지 않고 400 으로 매핑되는지 회귀가드.
class _FakeUser:
    id = "u1"
    tenant_id = None


class _FakeCtx:
    user = _FakeUser()
    site_id = uuid_mod.uuid4()


class _FakeDB:
    async def commit(self):
        pass

    async def rollback(self):
        pass


class TestRouterPricingValidation:
    async def test_generate_missing_round_id_400(self):
        from fastapi import HTTPException

        from app.api.endpoints.sales import actions
        with pytest.raises(HTTPException) as ei:
            await actions.pricing_generate({}, _FakeDB(), _FakeCtx())
        assert ei.value.status_code == 400

    async def test_generate_bad_round_id_400(self):
        from fastapi import HTTPException

        from app.api.endpoints.sales import actions
        with pytest.raises(HTTPException) as ei:
            await actions.pricing_generate({"round_id": "not-a-uuid"}, _FakeDB(), _FakeCtx())
        assert ei.value.status_code == 400

    async def test_solve_base_missing_round_id_400(self):
        from fastapi import HTTPException

        from app.api.endpoints.sales import actions
        with pytest.raises(HTTPException) as ei:
            await actions.pricing_solve_base({"target_total_10k": 10_000}, _FakeDB(), _FakeCtx())
        assert ei.value.status_code == 400

    async def test_solve_base_missing_target_400(self):
        from fastapi import HTTPException

        from app.api.endpoints.sales import actions
        with pytest.raises(HTTPException) as ei:
            await actions.pricing_solve_base({"round_id": str(uuid_mod.uuid4())}, _FakeDB(), _FakeCtx())
        assert ei.value.status_code == 400

    async def test_solve_base_non_numeric_target_400(self):
        from fastapi import HTTPException

        from app.api.endpoints.sales import actions
        with pytest.raises(HTTPException) as ei:
            await actions.pricing_solve_base(
                {"round_id": str(uuid_mod.uuid4()), "target_total_10k": "abc"}, _FakeDB(), _FakeCtx())
        assert ei.value.status_code == 400

    async def test_group_apply_missing_round_id_400(self):
        from fastapi import HTTPException

        from app.api.endpoints.sales import actions
        with pytest.raises(HTTPException) as ei:
            await actions.pricing_group_apply({"unit_ids": [], "mode": "RATE", "value": 0.05}, _FakeDB(), _FakeCtx())
        assert ei.value.status_code == 400

    async def test_group_apply_bad_unit_uuid_400(self):
        from fastapi import HTTPException

        from app.api.endpoints.sales import actions
        with pytest.raises(HTTPException) as ei:
            await actions.pricing_group_apply(
                {"round_id": str(uuid_mod.uuid4()), "unit_ids": ["bad-uuid"], "value": 1}, _FakeDB(), _FakeCtx())
        assert ei.value.status_code == 400

    async def test_group_apply_non_numeric_value_400(self):
        from fastapi import HTTPException

        from app.api.endpoints.sales import actions
        with pytest.raises(HTTPException) as ei:
            await actions.pricing_group_apply(
                {"round_id": str(uuid_mod.uuid4()), "unit_ids": [], "value": "x"}, _FakeDB(), _FakeCtx())
        assert ei.value.status_code == 400
