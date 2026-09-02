"""공사단계 세금 엔진 테스트 — B01~B08."""

from app.services.tax.utility_stage_engine import (
    calculate_all_utility_stage,
    calculate_b01_metro_transport,
    calculate_b02_school_site,
    calculate_b03_water_supply,
    calculate_b04_sewage,
)


class TestB01MetroTransport:
    """★실산식(표준건축비×부과율×건축연면적) — 이전 세대별 정액표(날조) 폐기 후 교정."""

    def test_formula_with_standard_cost(self):
        # 표준건축비 200만/㎡ × 부과율 **4%(서울=수도권)** × 연면적 10,000㎡ = 8억
        # ★2026-08-27 교정: 종전 1%(전용 59㎡≤85)는 **법령에 근거가 없다**.
        #   시행령 §16조의2⑧2호 = 100분의 2, 수도권은 100분의 4.
        result = calculate_b01_metro_transport(
            sido_name="서울", total_gfa_sqm=10_000, building_type="apartment",
            exclusive_area_sqm=59, standard_build_cost_won_per_sqm=2_000_000,
        )
        assert result["name"] == "광역교통시설부담금"
        assert result["amount_won"] == 800_000_000
        assert result["detail"]["amount_computable"] is True

    def test_non_capital_metro_is_half_of_capital(self):
        """★두 모집단 — 같은 입력에서 부산(비수도권)은 서울의 **절반**이어야 한다."""
        kw = dict(total_gfa_sqm=10_000, building_type="apartment",
                  exclusive_area_sqm=59, standard_build_cost_won_per_sqm=2_000_000)
        seoul = calculate_b01_metro_transport(sido_name="서울", **kw)
        busan = calculate_b01_metro_transport(sido_name="부산", **kw)
        assert busan["amount_won"] == 400_000_000
        assert seoul["amount_won"] == busan["amount_won"] * 2, (
            "수도권과 비수도권이 갈리지 않는다 — 요율이 지역에 도달하지 않았다"
        )

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

    def test_officetel_charged_as_quasi_housing(self):
        """★R1 CRITICAL 교정: 분양형 오피스텔=준주택 포함 부과 대상(학교용지법 §2 3호·
        2021.6.23~현행 유지) — 300호 이상이면 0.4% 부과. 무단 면제는 20억 과소계상 회귀."""
        result = calculate_b02_school_site(
            total_sale_amount_won=500_000_000_000,
            total_households=1000,
            building_type="officetel",
        )
        assert result["amount_won"] == 2_000_000_000  # 5000억 × 0.4%
        assert "준주택" in result["detail"]["note"]  # 규모 기준 한계 정직 표기

    def test_office_and_commercial_exempt(self):
        """순수 업무(M09 office)·상업시설은 주택건설사업 아님 — 면제(종전 미게이트 오부과 봉합)."""
        for bt in ("office", "commercial", "지식산업센터"):
            result = calculate_b02_school_site(
                total_sale_amount_won=300_000_000_000,
                total_households=500,
                building_type=bt,
            )
            assert result["amount_won"] == 0, bt
            assert "주택건설사업 아님" in result["detail"]["reason"]

    def test_detached_house_rate_1_4pct(self):
        """★R1 MEDIUM 교정: 단독주택지(M10/M11 — 생산자 토큰 'house')는 §5의2 2호
        1.4% 요율(공동주택 0.4%와 별도)."""
        result = calculate_b02_school_site(
            total_sale_amount_won=500_000_000_000,
            total_households=1000,
            building_type="house",
        )
        assert result["rate"] == 0.014
        assert result["amount_won"] == 7_000_000_000  # 5000억 × 1.4%

    def test_producer_tokens_all_resolve(self):
        """★R1 HIGH 교정(토큰 누수): 생산자(_get_building_type) 실방출 토큰 전수가
        의도된 요율로 판정 — house/townhouse가 死토큰으로 새지 않음."""
        from app.services.tax.utility_stage_engine import school_site_rate_for

        assert school_site_rate_for("apartment") == 0.004
        assert school_site_rate_for("officetel") == 0.004  # 준주택 포함
        assert school_site_rate_for("townhouse") == 0.004  # 연립·공동주택 계열
        assert school_site_rate_for("house") == 0.014  # 단독주택지 §5의2
        assert school_site_rate_for("office") is None  # 업무시설 면제

    def test_unknown_token_charged_conservatively(self):
        """미지 토큰(주상복합 등)은 공동주택 요율 부과 — 과소계상 방지 보수 방향."""
        from app.services.tax.utility_stage_engine import school_site_rate_for

        assert school_site_rate_for("주상복합") == 0.004
        assert school_site_rate_for("") == 0.004

    def test_orchestrator_passes_building_type(self):
        """오케스트레이터(calculate_all_utility_stage)가 building_type을 B02에 전달 —
        업무시설(office)은 면제로 관통."""
        from app.services.tax.utility_stage_engine import calculate_all_utility_stage

        r = calculate_all_utility_stage(
            sido_name="서울", sigungu_name="강남구",
            total_households=1000, total_sale_amount_won=500_000_000_000,
            total_gfa_sqm=100_000, building_type="office",
        )
        b02 = next(it for it in r["items"] if it["code"] == "B02")
        assert b02["amount_won"] == 0
        assert "주택건설사업 아님" in b02["detail"]["reason"]


class TestB03WaterSupply:
    def test_withheld_without_sourced_rate(self):
        """★종전 이 테스트는 *"오산 1624세대: 120만원/세대 × 1624 ≈ 19.49억"* 을 참조하며
        `amount_won > 0` 만 단언했다 — 그 단가는 **출처 없는 생성값**이었고, 주석은
        *"data에 typo(1,200,000원으로 해석)"* 라는 **낡은 사실**까지 담고 있었다.
        단언이 `> 0` 이라 그 typo 를 **구별할 수도 없었다.**
        """
        result = calculate_b03_water_supply(
            sido_name="경기", sigungu_name="오산시", total_households=1624,
        )
        assert result["amount_won"] == 0
        assert result["detail"]["confidence"] == "unavailable"


class TestB04Sewage:
    def test_withheld_without_sourced_rate(self):
        result = calculate_b04_sewage(
            sido_name="서울", sigungu_name="강남구", total_households=500,
        )
        assert result["amount_won"] == 0, "종전 90,000,000원은 원/세대 × 세대수 (차원 오류)"
        assert result["detail"]["confidence"] == "unavailable"
        assert "㎥/일" in result["detail"]["reason"]




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
        # ★2026-08-27: 8종 → **4종**. B05~B08 은 부담금이 아니어서 빠졌다
        #   (인입 3건은 cost/utility_connection_cost 로 이관 · 소방은 도급단가 포함이라 제거).
        #   ★이 단언이 「법정 부담금만 남았는가」를 잠근다 — 새 항목이 들어오면 여기가 빨개진다.
        assert result["applicable_count"] == 4
        codes = [it["code"] for it in result["items"]]
        assert codes == ["B01", "B02", "B03", "B04"], f"법정 부담금 외가 섞였다: {codes}"
        # ★반대 방향 — 공사비 성격 코드가 되돌아오면 안 된다.
        assert not ({"B05", "B06", "B07", "B08"} & set(codes))


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
        # ★2026-08-27: 종전엔 *"B05 는 법령 근거가 없다"* 를 단언했다.
        #   지금은 **항목 자체가 없다** — 법정 부담금이 아니어서 이 엔진에서 빠졌다.
        #   ★「근거 없는 항목이 여기 있어도 된다」가 아니라 **「여기 있으면 안 된다」**가 계약이다.
        assert "B05" not in by_code, "공사비 성격 항목이 부담금 엔진에 되돌아왔다"
        assert all(by_code[c].get("legal_ref") for c in by_code), (
            f"법령 근거 없는 부담금이 있다: {[c for c in by_code if not by_code[c].get('legal_ref')]}"
        )

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
