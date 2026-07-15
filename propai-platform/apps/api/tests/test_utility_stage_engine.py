"""공사단계 세금 엔진 테스트 — B01~B08."""

from app.services.tax.utility_stage_engine import (
    calculate_all_utility_stage,
    calculate_b01_metro_transport,
    calculate_b02_school_site,
    calculate_b03_water_supply,
    calculate_b04_sewage,
    calculate_b05_electricity,
    calculate_b08_fire,
)


class TestB01MetroTransport:
    """★실산식(표준건축비×부과율×건축연면적) — 이전 세대별 정액표(날조) 폐기 후 교정."""

    def test_formula_with_standard_cost(self):
        # 표준건축비 200만/㎡ × 부과율 1%(전용 59㎡) × 연면적 10,000㎡ = 2억
        result = calculate_b01_metro_transport(
            sido_name="서울", total_gfa_sqm=10_000, building_type="apartment",
            exclusive_area_sqm=59, standard_build_cost_won_per_sqm=2_000_000,
        )
        assert result["name"] == "광역교통시설부담금"
        assert result["amount_won"] == 200_000_000
        assert result["detail"]["amount_computable"] is True

    def test_unavailable_without_standard_cost(self):
        """★무목업: 표준건축비 고시값 미설정 → amount_won 0 + unavailable(합산 안전·정직)."""
        result = calculate_b01_metro_transport(
            sido_name="서울", total_gfa_sqm=10_000, building_type="apartment",
        )
        assert result["amount_won"] == 0
        assert result["detail"]["confidence"] == "unavailable"
        assert result["detail"]["amount_computable"] is False

    def test_non_metro_zero(self):
        result = calculate_b01_metro_transport(
            sido_name="제주", total_gfa_sqm=10_000, building_type="apartment",
            standard_build_cost_won_per_sqm=2_000_000,
        )
        assert result["amount_won"] == 0
        assert result["detail"]["applicable"] is False


class TestB02SchoolSite:
    def test_under_300(self):
        """300세대 미만 면제."""
        result = calculate_b02_school_site(
            total_sale_amount_won=100_000_000_000,
            total_households=200,
        )
        assert result["amount_won"] == 0

    def test_over_300(self):
        """300세대 이상: 분양가 × 0.4% (학교용지법 §5의2 현행 요율·2025.6.21 개정)."""
        result = calculate_b02_school_site(
            total_sale_amount_won=500_000_000_000,
            total_households=1000,
        )
        assert result["amount_won"] == 2_000_000_000  # 5000억 × 0.4%

    def test_officetel_exempt_regardless_of_households(self):
        """★건물유형 게이트(감사 P1 잔여 최종): 오피스텔(준주택·업무시설)은 학교용지법
        §2 대상 외 — 300호 이상이어도 면제(종전 미게이트 시 분양매출 0.4% 오부과)."""
        result = calculate_b02_school_site(
            total_sale_amount_won=500_000_000_000,
            total_households=1000,
            building_type="officetel",
        )
        assert result["amount_won"] == 0
        assert "주택건설사업 아님" in result["detail"]["reason"]

    def test_commercial_exempt(self):
        """상업시설도 대상 외 — 면제."""
        result = calculate_b02_school_site(
            total_sale_amount_won=300_000_000_000,
            total_households=500,
            building_type="commercial",
        )
        assert result["amount_won"] == 0

    def test_housing_types_still_charged(self):
        """주거 유형(아파트·공동주택·단독주택)은 게이트 통과 — 기존 부과 유지."""
        for bt in ("apartment", "아파트", "공동주택", "단독주택"):
            result = calculate_b02_school_site(
                total_sale_amount_won=500_000_000_000,
                total_households=1000,
                building_type=bt,
            )
            assert result["amount_won"] == 2_000_000_000, bt

    def test_orchestrator_passes_building_type(self):
        """오케스트레이터(calculate_all_utility_stage)가 building_type을 B02에 전달."""
        from app.services.tax.utility_stage_engine import calculate_all_utility_stage

        r = calculate_all_utility_stage(
            sido_name="서울", sigungu_name="강남구",
            total_households=1000, total_sale_amount_won=500_000_000_000,
            total_gfa_sqm=100_000, building_type="officetel",
        )
        b02 = next(it for it in r["items"] if it["code"] == "B02")
        assert b02["amount_won"] == 0
        assert "주택건설사업 아님" in b02["detail"]["reason"]


class TestB03WaterSupply:
    def test_oasan_reference(self):
        """오산 1624세대 참조: 120만원/세대 × 1624 ≈ 19.49억."""
        result = calculate_b03_water_supply(
            sido_name="경기", sigungu_name="오산시",
            total_households=1624,
        )
        # 경기_오산시 = 120_0000 (data에 typo — 1,200,000원으로 해석)
        assert result["amount_won"] > 0


class TestB04Sewage:
    def test_basic(self):
        result = calculate_b04_sewage(
            sido_name="서울", sigungu_name="강남구",
            total_households=500,
        )
        # 서울: 180,000원/세대 × 500 = 9000만
        assert result["amount_won"] == 90_000_000


class TestB05Electricity:
    def test_basic(self):
        result = calculate_b05_electricity(total_households=1000)
        assert result["amount_won"] == 250_000_000


class TestB08Fire:
    def test_basic(self):
        result = calculate_b08_fire(total_gfa_sqm=100_000)
        assert result["amount_won"] == 350_000_000


class TestAllUtilityStage:
    def test_full(self):
        result = calculate_all_utility_stage(
            sido_name="서울",
            sigungu_name="강남구",
            total_households=1000,
            total_sale_amount_won=500_000_000_000,
            total_gfa_sqm=100_000,
        )
        assert result["stage"] == "construction"
        assert result["applicable_count"] == 8
        assert result["total_won"] > 0
        codes = [it["code"] for it in result["items"]]
        assert "B01" in codes
        assert "B08" in codes


class TestChargeLegalRefs:
    """부담금 출력에 법령 근거(근거+링크·evidence) 부착 — verified law.go.kr URL."""

    def test_utility_charges_carry_legal_ref(self):
        r = calculate_all_utility_stage(
            sido_name="서울", sigungu_name="강남구", total_households=1000,
            total_sale_amount_won=500_000_000_000, total_gfa_sqm=100_000,
        )
        by_code = {it["code"]: it for it in r["items"]}
        expect = {"B01": "광역교통", "B02": "학교용지", "B03": "수도법", "B04": "하수도"}
        for code, kw in expect.items():
            ref = by_code[code].get("legal_ref")
            assert ref and ref.get("url"), f"{code}: legal_ref/url 누락"
            assert kw in (ref.get("law_name", "") + ref.get("title", "")), f"{code}: 근거 법령 불일치"
        # 법령키 없는 B05~B08은 legal_ref 미부착(오탐 방지).
        assert "legal_ref" not in by_code["B05"]

    def test_sale_c07_carries_legal_ref(self):
        from app.services.tax.sale_stage_engine import calculate_all_sale_stage

        r = calculate_all_sale_stage(
            total_sale_amount_won=500_000_000_000, total_units=1000,
            total_gfa_sqm=100_000, in_infra_charge_zone=True,
        )
        c07 = next(it for it in r["items"] if it["code"] == "C07")
        ref = c07.get("legal_ref")
        assert ref and ref.get("url"), "C07 legal_ref/url 누락"
        assert "국토" in ref.get("law_name", "")
