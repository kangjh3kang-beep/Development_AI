"""세금 AI 서비스 (양도세/취득세/종부세)."""


from app.services.data_validation.calculation_metadata import CalculationMetadata


class TaxAIService:
    """부동산 세금 AI 계산기.

    - 취득세: 주택(1~3%), 비주택(4%)
    - 양도세: 보유기간별 차등 (장기보유특별공제 포함)
    - 종합부동산세: 과세표준별 누진세율
    """

    # 취득세율 테이블
    ACQUISITION_TAX_RATES = {
        "주택_6억이하": 0.01,
        "주택_6억~9억": 0.02,
        "주택_9억초과": 0.03,
        "주택_다주택_2주택": 0.12,
        "주택_다주택_3주택이상": 0.15,
        "비주택": 0.04,
        "농지": 0.03,
    }

    # 양도세 기본세율 (과세표준 구간별)
    TRANSFER_TAX_BRACKETS = [
        (14_000_000, 0.06, 0),
        (50_000_000, 0.15, 1_260_000),
        (88_000_000, 0.24, 5_760_000),
        (150_000_000, 0.35, 15_440_000),
        (300_000_000, 0.38, 19_940_000),
        (500_000_000, 0.40, 25_940_000),
        (1_000_000_000, 0.42, 35_940_000),
        (float("inf"), 0.45, 65_940_000),
    ]

    # 장기보유특별공제율 (보유연수별)
    LONG_TERM_DEDUCTION = {
        3: 0.06, 4: 0.08, 5: 0.10, 6: 0.12, 7: 0.14,
        8: 0.16, 9: 0.18, 10: 0.20, 15: 0.30,
    }

    # 종합부동산세율 (과세표준 구간별)
    COMPREHENSIVE_TAX_BRACKETS = [
        (300_000_000, 0.006, 0),
        (600_000_000, 0.008, 180_000),
        (1_200_000_000, 0.012, 780_000),
        (5_000_000_000, 0.016, 2_580_000),
        (9_400_000_000, 0.022, 12_580_000),
        (float("inf"), 0.030, 22_280_000),
    ]

    def calculate_acquisition_tax(
        self,
        property_value_krw: int,
        property_type: str = "주택",
        house_count: int = 1,
    ) -> dict:
        """취득세 계산."""
        if property_type != "주택":
            rate_key = "비주택" if property_type != "농지" else "농지"
        elif house_count >= 3:
            rate_key = "주택_다주택_3주택이상"
        elif house_count == 2:
            rate_key = "주택_다주택_2주택"
        elif property_value_krw <= 600_000_000:
            rate_key = "주택_6억이하"
        elif property_value_krw <= 900_000_000:
            rate_key = "주택_6억~9억"
        else:
            rate_key = "주택_9억초과"

        rate = self.ACQUISITION_TAX_RATES[rate_key]
        tax = int(property_value_krw * rate)
        local_education_tax = int(tax * 0.1)
        special_rural_tax = int(tax * 0.2) if property_value_krw > 600_000_000 else 0

        metadata = CalculationMetadata("취득세")
        metadata.set_legal_basis("2024-06-01")
        metadata.add_source("취득세율표", "하드코딩")
        metadata.add_source("지방교육세율", "하드코딩")
        metadata.add_source("농어촌특별세율", "하드코딩")

        result = {
            "property_value_krw": property_value_krw,
            "property_type": property_type,
            "house_count": house_count,
            "rate_key": rate_key,
            "tax_rate_pct": rate * 100,
            "acquisition_tax_krw": tax,
            "local_education_tax_krw": local_education_tax,
            "special_rural_tax_krw": special_rural_tax,
            "total_tax_krw": tax + local_education_tax + special_rural_tax,
        }
        result["_metadata"] = metadata.to_dict()
        return result

    def _transfer_tax_metadata(self, is_primary_residence: bool = False) -> CalculationMetadata:
        """양도세 계산 메타데이터 생성."""
        metadata = CalculationMetadata("양도소득세")
        metadata.set_legal_basis("2024-06-01")
        metadata.add_source("양도세율표", "하드코딩")
        metadata.add_source("장기보유특별공제율", "하드코딩")
        if is_primary_residence:
            metadata.add_source("1세대1주택 비과세 기준", "하드코딩")
        return metadata

    def calculate_transfer_tax(
        self,
        acquisition_price_krw: int,
        transfer_price_krw: int,
        holding_years: int = 1,
        is_primary_residence: bool = False,
        actual_residence_years: int = 0,
    ) -> dict:
        """양도세 계산."""
        gain = transfer_price_krw - acquisition_price_krw
        metadata = self._transfer_tax_metadata(is_primary_residence)

        # 1세대1주택 비과세 (보유 3년 + 거주 2년 이상, 실거래가 12억 이하)
        if is_primary_residence and holding_years >= 3 and actual_residence_years >= 2:
            if gain <= 1_200_000_000:  # 12억 이하 전액 비과세
                result = {"gain_krw": gain, "tax_krw": 0, "effective_rate_pct": 0.0,
                        "deduction_applied": "1세대1주택 비과세", "details": []}
                result["_metadata"] = metadata.to_dict()
                return result
            else:
                # 12억 초과분만 과세
                taxable_gain = gain - 1_200_000_000
                # 장기보유특별공제 적용
                deduction_rate = 0.0
                for years, rate in sorted(self.LONG_TERM_DEDUCTION.items()):
                    if holding_years >= years:
                        deduction_rate = rate
                deduction = int(taxable_gain * deduction_rate)
                taxable = taxable_gain - deduction - 2_500_000

                if taxable <= 0:
                    result = {
                        "gain_krw": gain, "tax_krw": 0, "effective_rate_pct": 0.0,
                        "deduction_applied": "1세대1주택 비과세 (12억 초과분 공제 후 0)",
                        "details": [],
                    }
                    result["_metadata"] = metadata.to_dict()
                    return result

                tax = 0
                for bracket_limit, rate, cumulative_deduction in self.TRANSFER_TAX_BRACKETS:
                    if taxable <= bracket_limit:
                        tax = int(taxable * rate - cumulative_deduction)
                        break

                result = {
                    "acquisition_price_krw": acquisition_price_krw,
                    "transfer_price_krw": transfer_price_krw,
                    "gain_krw": gain,
                    "holding_years": holding_years,
                    "deduction_applied": "1세대1주택 비과세 (12억 초과분 과세)",
                    "taxable_excess_krw": taxable_gain,
                    "long_term_deduction_rate_pct": deduction_rate * 100,
                    "long_term_deduction_krw": deduction,
                    "basic_deduction_krw": 2_500_000,
                    "taxable_krw": taxable,
                    "tax_krw": max(0, tax),
                    "effective_rate_pct": round(max(0, tax) / gain * 100, 2) if gain > 0 else 0,
                }
                result["_metadata"] = metadata.to_dict()
                return result

        if gain <= 0:
            result = {
                "gain_krw": gain,
                "tax_krw": 0,
                "effective_rate_pct": 0,
                "note": "양도차익 없음",
            }
            result["_metadata"] = metadata.to_dict()
            return result

        # 장기보유특별공제
        deduction_rate = 0.0
        for years, rate in sorted(self.LONG_TERM_DEDUCTION.items()):
            if holding_years >= years:
                deduction_rate = rate
        deduction = int(gain * deduction_rate)
        taxable = gain - deduction - 2_500_000  # 기본공제 250만원

        if taxable <= 0:
            result = {
                "gain_krw": gain,
                "deduction_krw": deduction,
                "tax_krw": 0,
                "effective_rate_pct": 0,
            }
            result["_metadata"] = metadata.to_dict()
            return result

        # 누진세율 적용
        tax = 0
        for bracket_limit, rate, cumulative_deduction in self.TRANSFER_TAX_BRACKETS:
            if taxable <= bracket_limit:
                tax = int(taxable * rate - cumulative_deduction)
                break

        result = {
            "acquisition_price_krw": acquisition_price_krw,
            "transfer_price_krw": transfer_price_krw,
            "gain_krw": gain,
            "holding_years": holding_years,
            "long_term_deduction_rate_pct": deduction_rate * 100,
            "long_term_deduction_krw": deduction,
            "basic_deduction_krw": 2_500_000,
            "taxable_krw": taxable,
            "tax_krw": max(0, tax),
            "effective_rate_pct": round(max(0, tax) / gain * 100, 2) if gain > 0 else 0,
        }
        result["_metadata"] = metadata.to_dict()
        return result

    def calculate_comprehensive_tax(
        self,
        total_property_value_krw: int,
        deduction_krw: int = 600_000_000,
        house_count: int = 1,
    ) -> dict:
        """종합부동산세 계산."""
        taxable = total_property_value_krw - deduction_krw
        if taxable <= 0:
            metadata = CalculationMetadata("종합부동산세")
            metadata.set_legal_basis("2024-06-01")
            metadata.add_source("종합부동산세율표", "하드코딩")
            result = {
                "total_property_value_krw": total_property_value_krw,
                "deduction_krw": deduction_krw,
                "taxable_krw": 0,
                "tax_krw": 0,
                "house_count": house_count,
                "note": "과세표준 미달",
            }
            result["_metadata"] = metadata.to_dict()
            return result

        base_tax = 0
        for bracket_limit, rate, cumulative_deduction in self.COMPREHENSIVE_TAX_BRACKETS:
            if taxable <= bracket_limit:
                base_tax = int(taxable * rate - cumulative_deduction)
                break

        # 다주택 중과 (2주택 이상 50% 중과)
        surcharge = 0
        if house_count >= 2:
            surcharge = int(base_tax * 0.5)

        total_tax = max(0, base_tax) + surcharge

        metadata = CalculationMetadata("종합부동산세")
        metadata.set_legal_basis("2024-06-01")
        metadata.add_source("종합부동산세율표", "하드코딩")
        metadata.add_source("다주택 중과세율", "하드코딩")

        result = {
            "total_property_value_krw": total_property_value_krw,
            "deduction_krw": deduction_krw,
            "taxable_krw": taxable,
            "house_count": house_count,
            "base_tax_krw": max(0, base_tax),
            "surcharge_krw": surcharge,
            "tax_krw": total_tax,
            "effective_rate_pct": round(total_tax / total_property_value_krw * 100, 3),
        }
        result["_metadata"] = metadata.to_dict()
        return result

    def monte_carlo_tax_simulation(
        self,
        base_value_krw: int,
        annual_growth_rates: list,
        holding_years: int = 5,
    ) -> dict:
        """몬테카를로 세금 시뮬레이션."""
        scenarios = []
        for growth_rate in annual_growth_rates:
            future_value = base_value_krw * ((1 + growth_rate) ** holding_years)
            transfer_tax = self.calculate_transfer_tax(
                base_value_krw, int(future_value), holding_years
            )
            scenarios.append({
                "growth_rate_pct": round(growth_rate * 100, 1),
                "future_value_krw": int(future_value),
                "transfer_tax_krw": transfer_tax["tax_krw"],
                "effective_rate_pct": transfer_tax["effective_rate_pct"],
            })
        return {
            "base_value_krw": base_value_krw,
            "holding_years": holding_years,
            "scenario_count": len(scenarios),
            "scenarios": scenarios,
        }
