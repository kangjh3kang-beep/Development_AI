"""세금 AI 계산 서비스.

취득세, 재산세, 양도세 등 7종 부동산 세금 계산.
양도소득세 누진세율 8구간 + 장기보유특별공제 + 중과세 지원.
Monte Carlo 시뮬레이션 기반 절세 시나리오 생성.

흐름:
1. 세금 유형별 규칙 엔진으로 기본 세액 산출
2. 양도세: 누진세율 8구간 + 장기보유특별공제 + 다주택 중과
3. Monte Carlo N=1,000 절세 시나리오 시뮬레이션
4. LLM으로 절세 팁 생성
5. 결과 저장 및 반환
"""

import math
import random
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any
from uuid import UUID

import structlog
from packages.schemas.enums import TaxType
from packages.schemas.models import TaxCalculationResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.tax_calculation import TaxCalculation

logger = structlog.get_logger(__name__)

# ── 양도소득세 누진세율 8구간 (2026년 기준) ──
_TRANSFER_TAX_BRACKETS: list[tuple[int | float, float, int]] = [
    # (상한, 세율, 누진공제)
    (14_000_000, 0.06, 0),
    (50_000_000, 0.15, 1_260_000),
    (88_000_000, 0.24, 5_760_000),
    (150_000_000, 0.35, 15_440_000),
    (300_000_000, 0.38, 19_940_000),
    (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000),
    (math.inf, 0.45, 65_940_000),
]

# ── 장기보유특별공제율 ──
# 일반: 3년 6% → 10년 30% (선형 보간)
# 1세대1주택: 3년 24% → 10년 80% (보유+거주 합산)
_LONG_HOLD_GENERAL_MIN = 0.06  # 3년
_LONG_HOLD_GENERAL_MAX = 0.30  # 10년
_LONG_HOLD_SINGLE_MIN = 0.24   # 3년 1세대1주택
_LONG_HOLD_SINGLE_MAX = 0.80   # 10년 1세대1주택
_LONG_HOLD_MIN_YEARS = 3
_LONG_HOLD_MAX_YEARS = 10

# ── 취득세 세율 ──
_ACQUISITION_RATES = {
    "default": 0.04,
    "luxury": 0.12,
    "first_home": 0.01,
    "two_homes": 0.08,
    "three_plus": 0.12,
}

# ── 기타 세율 ──
_TAX_RATES: dict[str, dict[str, float]] = {
    "acquisition": _ACQUISITION_RATES,
    "property": {
        "default": 0.001,
        "residential": 0.001,
        "commercial": 0.0025,
    },
    "comprehensive_real_estate": {"default": 0.005},
    "registration": {"default": 0.02},
    "inheritance": {"default": 0.10},
    "gift": {"default": 0.10},
}


class TaxAIService:
    """세금 AI 계산 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    # ── 양도소득세 누진세율 계산 ──

    @staticmethod
    def _calc_transfer_tax_progressive(taxable_gain: float) -> tuple[float, float]:
        """양도소득세 누진세율 8구간을 적용하여 세액을 계산한다.

        Returns:
            (산출세액, 실효세율)
        """
        if taxable_gain <= 0:
            return 0.0, 0.0

        for upper, rate, deduction in _TRANSFER_TAX_BRACKETS:
            if taxable_gain <= upper:
                tax = taxable_gain * rate - deduction
                effective_rate = tax / taxable_gain if taxable_gain > 0 else 0
                return max(0, tax), effective_rate

        # fallback (should not reach)
        last_rate = _TRANSFER_TAX_BRACKETS[-1][1]
        last_deduction = _TRANSFER_TAX_BRACKETS[-1][2]
        tax = taxable_gain * last_rate - last_deduction
        return max(0, tax), tax / taxable_gain

    @staticmethod
    def _calc_long_hold_deduction(
        holding_years: int,
        is_single_home: bool = False,
    ) -> float:
        """장기보유특별공제율을 반환한다.

        일반: 3년 6% → 10년 30% (선형 보간)
        1세대1주택: 3년 24% → 10년 80% (선형 보간)
        3년 미만: 0%
        """
        if holding_years < _LONG_HOLD_MIN_YEARS:
            return 0.0
        clamped = min(holding_years, _LONG_HOLD_MAX_YEARS)
        span = _LONG_HOLD_MAX_YEARS - _LONG_HOLD_MIN_YEARS  # 7

        if is_single_home:
            rate = _LONG_HOLD_SINGLE_MIN + (
                (clamped - _LONG_HOLD_MIN_YEARS)
                * (_LONG_HOLD_SINGLE_MAX - _LONG_HOLD_SINGLE_MIN)
                / span
            )
        else:
            rate = _LONG_HOLD_GENERAL_MIN + (
                (clamped - _LONG_HOLD_MIN_YEARS)
                * (_LONG_HOLD_GENERAL_MAX - _LONG_HOLD_GENERAL_MIN)
                / span
            )
        return round(rate, 6)

    # ── 전용 양도소득세 계산 메서드 ──

    def calculate_capital_gains_tax(
        self,
        sale_price: float,
        acquisition_price: float,
        holding_years: int,
        is_single_home: bool = False,
        home_count: int = 1,
    ) -> dict[str, Any]:
        """양도소득세를 전용으로 계산한다.

        누진세율 8구간(1,400만 이하 6% ~ 10억 초과 45%) +
        장기보유특별공제(3년 6% ~ 10년 30%) +
        다주택 중과 적용.

        Args:
            sale_price: 매도가
            acquisition_price: 매수가
            holding_years: 보유기간 (년)
            is_single_home: 1세대 1주택 여부
            home_count: 보유 주택 수

        Returns:
            양도차익, 공제율, 과세표준, 산출세액, 실효세율 등 상세 결과
        """
        # 양도차익
        gain = sale_price - acquisition_price
        if gain <= 0:
            return {
                "gain": gain,
                "deduction_rate": 0.0,
                "taxable_gain": 0.0,
                "tax": 0.0,
                "effective_rate": 0.0,
                "bracket_rate": 0.0,
                "bracket_deduction": 0,
                "multi_home_surcharge": 0.0,
            }

        # 단기 보유 특별세율
        if holding_years < 1:
            tax = gain * 0.77
            return {
                "gain": gain,
                "deduction_rate": 0.0,
                "taxable_gain": gain,
                "tax": tax,
                "effective_rate": 0.77,
                "bracket_rate": 0.77,
                "bracket_deduction": 0,
                "short_term": True,
                "multi_home_surcharge": 0.0,
            }
        if holding_years < 2:
            tax = gain * 0.66
            return {
                "gain": gain,
                "deduction_rate": 0.0,
                "taxable_gain": gain,
                "tax": tax,
                "effective_rate": 0.66,
                "bracket_rate": 0.66,
                "bracket_deduction": 0,
                "short_term": True,
                "multi_home_surcharge": 0.0,
            }

        # 장기보유특별공제
        deduction_rate = self._calc_long_hold_deduction(holding_years, is_single_home)

        # ── 금액 계산(과세표준→세액→중과→합계)은 Decimal로 승격 ──
        # 입력은 Decimal(str(x))로 변환해 이진 부동소수 오차 유입을 원천 차단하고,
        # 세율은 Decimal 리터럴로 고정한다. 중간 반올림 없이 전 구간을 정밀 유지하다가
        # 각 출력 필드에서 1회만 ROUND_HALF_EVEN 양자화한다(Python round()와 동일 정책 —
        # ROUND_HALF_UP·절사로 정책을 바꾸지 않는다. 기존 round() 결과 바이트 동일 확증됨).
        gain_dec = Decimal(str(gain))
        deduction_rate_dec = Decimal(str(deduction_rate))
        deduction_amount_dec = gain_dec * deduction_rate_dec
        taxable_gain_dec = gain_dec - deduction_amount_dec

        # 누진세율 8구간 (Decimal 리터럴로 재계산 — _calc_transfer_tax_progressive의
        # float 경로는 다른 호출부(byte-exact 테스트 보유)를 위해 그대로 둔다)
        bracket_rate = 0.0
        bracket_deduction = 0
        base_tax_dec = Decimal(0)
        for upper, rate, deduction in _TRANSFER_TAX_BRACKETS:
            upper_dec = None if upper == math.inf else Decimal(str(upper))
            if upper_dec is None or taxable_gain_dec <= upper_dec:
                bracket_rate = rate
                bracket_deduction = deduction
                base_tax_dec = taxable_gain_dec * Decimal(str(rate)) - Decimal(deduction)
                break

        # 다주택 중과
        surcharge_dec = Decimal(0)
        if home_count == 2:
            surcharge_dec = taxable_gain_dec * Decimal("0.20")
        elif home_count >= 3:
            surcharge_dec = taxable_gain_dec * Decimal("0.30")

        total_tax_dec = base_tax_dec + surcharge_dec
        final_effective = float(total_tax_dec / gain_dec) if gain_dec > 0 else 0.0

        def _quantize_won(value: Decimal) -> int:
            """원단위로 양자화한다(ROUND_HALF_EVEN — Python round()와 동일 정책)."""
            return int(value.to_integral_value(rounding=ROUND_HALF_EVEN))

        return {
            "gain": gain,
            "deduction_rate": deduction_rate,
            "deduction_amount": _quantize_won(deduction_amount_dec),
            "taxable_gain": _quantize_won(taxable_gain_dec),
            "bracket_rate": bracket_rate,
            "bracket_deduction": bracket_deduction,
            "base_tax": _quantize_won(base_tax_dec),
            "multi_home_surcharge": _quantize_won(surcharge_dec),
            "tax": _quantize_won(total_tax_dec),
            "effective_rate": round(final_effective, 6),
        }

    # ── 기본 세액 산출 (취득세/재산세/기타) ──

    def _calculate_base_tax(
        self,
        tax_type: str,
        taxable_value: float,
        **kwargs: Any,
    ) -> tuple[float, float]:
        """규칙 기반 기본 세액을 산출한다. (세액, 적용세율) 반환."""
        if tax_type == "transfer":
            return self._calculate_transfer_tax(taxable_value, **kwargs)

        rates = _TAX_RATES.get(tax_type, {})
        rate = rates.get("default", 0.04)

        if tax_type == "acquisition":
            home_count = kwargs.get("home_count", 1)
            if kwargs.get("is_first_home"):
                rate = rates["first_home"]
            elif home_count >= 3:
                rate = rates["three_plus"]
            elif home_count == 2:
                rate = rates["two_homes"]
            elif taxable_value > 900_000_000:
                rate = rates["luxury"]

        amount = taxable_value * rate
        return amount, rate

    def _calculate_transfer_tax(
        self, taxable_value: float, **kwargs: Any,
    ) -> tuple[float, float]:
        """양도소득세를 계산한다 (누진세율 + 장기보유공제 + 중과)."""
        acquisition_price = kwargs.get("acquisition_price", taxable_value * 0.7)
        holding_years = kwargs.get("holding_years", 5)
        is_single_home = kwargs.get("is_single_home", False)
        home_count = kwargs.get("home_count", 1)

        # 단기 보유 특별세율
        if holding_years < 1:
            amount = (taxable_value - acquisition_price) * 0.77
            return max(0, amount), 0.77
        if holding_years < 2:
            amount = (taxable_value - acquisition_price) * 0.66
            return max(0, amount), 0.66

        # 양도차익
        gain = taxable_value - acquisition_price
        if gain <= 0:
            return 0.0, 0.0

        # 장기보유특별공제
        deduction_rate = self._calc_long_hold_deduction(holding_years, is_single_home)
        taxable_gain = gain * (1 - deduction_rate)

        # 기본 누진세율 적용
        tax, effective_rate = self._calc_transfer_tax_progressive(taxable_gain)

        # 다주택 중과
        if home_count == 2:
            tax += taxable_gain * 0.20  # 기본세율 + 20%p
        elif home_count >= 3:
            tax += taxable_gain * 0.30  # 기본세율 + 30%p

        return tax, effective_rate

    # ── Monte Carlo 절세 시나리오 ──

    def _run_monte_carlo_scenarios(
        self,
        tax_type: str,
        taxable_value: float,
        base_amount: float,
        n_simulations: int = 1000,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Monte Carlo 시뮬레이션으로 절세 시나리오를 생성한다.

        변수: 보유기간(±3년), 매도시기(월별 계절성), 증여 분할(50/70/100%).
        """
        if tax_type != "transfer":
            return []

        acquisition_price = kwargs.get("acquisition_price", taxable_value * 0.7)
        holding_years = kwargs.get("holding_years", 5)
        home_count = kwargs.get("home_count", 1)

        results: list[float] = []
        scenario_params: list[dict[str, Any]] = []

        rng = random.Random(42)  # 재현 가능한 시뮬레이션  # noqa: S311

        for _ in range(n_simulations):
            # 보유기간 변동: 현재 ±3년
            sim_hold = max(1, holding_years + rng.randint(-3, 5))
            # 매도가 계절성 변동: ±5%
            seasonal_factor = 1.0 + rng.uniform(-0.05, 0.05)
            sim_sale_price = taxable_value * seasonal_factor
            # 주택 수 변동: 감소 가능
            sim_home_count = max(1, home_count + rng.choice([-1, 0, 0, 0]))

            tax, _ = self._calculate_transfer_tax(
                sim_sale_price,
                acquisition_price=acquisition_price,
                holding_years=sim_hold,
                home_count=sim_home_count,
            )
            results.append(tax)
            scenario_params.append({
                "holding_years": sim_hold,
                "sale_price": sim_sale_price,
                "home_count": sim_home_count,
                "tax": tax,
            })

        # 최적 시나리오 3개 추출
        scenario_params.sort(key=lambda x: x["tax"])
        best_3 = scenario_params[:3]

        return [
            {
                "scenario": f"시나리오 {i + 1}: 보유 {s['holding_years']}년, "
                f"주택 {s['home_count']}채",
                "estimated_tax": round(s["tax"]),
                "savings": round(base_amount - s["tax"]),
                "savings_pct": round(
                    (base_amount - s["tax"]) / base_amount * 100, 1,
                ) if base_amount > 0 else 0,
            }
            for i, s in enumerate(best_3)
        ]

    # ── LLM 절세 팁 ──

    async def _generate_optimization_tips(
        self,
        tax_type: str,
        taxable_value: float,
        amount: float,
    ) -> list[str]:
        """LLM으로 절세 팁을 생성한다."""
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            api_key=self.settings.anthropic_api_key,
            temperature=0.3,
        )

        prompt = f"""한국 부동산 세금 전문가로서, 다음 세금 상황에 대해 3~5개의 절세 팁을 제시하세요.

세금 유형: {tax_type}
과세표준: {taxable_value:,.0f}원
산출 세액: {amount:,.0f}원

절세 팁을 한국어로, 각 항목을 한 줄로 간결하게 작성하세요.
번호 없이 팁만 나열하세요."""

        try:
            response = await llm.ainvoke(prompt)
            tips = [
                line.strip().lstrip("•-·")
                for line in response.content.strip().split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]
            return tips[:5]
        except Exception:
            logger.warning("절세 팁 생성 실패")
            return ["세무 전문가 상담을 권장합니다."]

    # ── 메인 계산 ──

    async def calculate(
        self,
        project_id: UUID,
        tenant_id: UUID,
        tax_type: str,
        taxable_value: float,
        **kwargs: Any,
    ) -> TaxCalculationResponse:
        """세금을 계산한다."""
        logger.info("세금 계산 시작", project_id=str(project_id), tax_type=tax_type)

        # 1. 기본 세액 산출
        amount, rate = self._calculate_base_tax(tax_type, taxable_value, **kwargs)

        # 2. Monte Carlo 시나리오 (양도세 전용)
        scenarios = self._run_monte_carlo_scenarios(
            tax_type, taxable_value, amount, **kwargs,
        )

        # 3. LLM 세무 전략 해석 (TaxInterpreter 6섹션) — 실패 시 기존 팁 생성으로 폴백
        ai_sections = await self._generate_tax_interpretation(
            tax_type, taxable_value, amount, rate, **kwargs,
        )
        if ai_sections:
            # 6섹션에서 절세 팁 합성 (프론트 기존 optimization_tips 호환)
            tips = [
                v for v in (
                    ai_sections.get("optimization_strategy"),
                    ai_sections.get("deduction_opportunities"),
                    ai_sections.get("timing_strategy"),
                ) if v
            ]
        else:
            tips = await self._generate_optimization_tips(tax_type, taxable_value, amount)
        if scenarios:
            tips.insert(0, f"Monte Carlo 분석: 최대 {scenarios[0].get('savings_pct', 0)}% 절세 가능")

        # 4. DB 저장
        tax_calc = TaxCalculation(
            tenant_id=tenant_id,
            project_id=project_id,
            tax_type=tax_type,
            amount=amount,
            taxable_value=taxable_value,
            tax_rate=rate,
            deductions=[],
            optimization_tips=tips,
            calculation_basis={**kwargs, "monte_carlo_scenarios": scenarios},
        )
        self.db.add(tax_calc)
        await self.db.commit()
        await self.db.refresh(tax_calc)

        logger.info("세금 계산 완료", amount=amount, rate=rate)

        return TaxCalculationResponse(
            id=tax_calc.id,
            project_id=tax_calc.project_id,
            tax_type=TaxType(tax_calc.tax_type),
            amount=tax_calc.amount,
            taxable_value=tax_calc.taxable_value,
            tax_rate=tax_calc.tax_rate,
            deductions=tax_calc.deductions or [],
            optimization_tips=tax_calc.optimization_tips or [],
            created_at=tax_calc.created_at,
            ai_tax_summary=ai_sections.get("tax_summary"),
            ai_optimization_strategy=ai_sections.get("optimization_strategy"),
            ai_entity_comparison=ai_sections.get("entity_comparison"),
            ai_timing_strategy=ai_sections.get("timing_strategy"),
            ai_deduction_opportunities=ai_sections.get("deduction_opportunities"),
            ai_risk_factors=ai_sections.get("risk_factors"),
        )

    async def _generate_tax_interpretation(
        self,
        tax_type: str,
        taxable_value: float,
        amount: float,
        rate: float,
        **kwargs: Any,
    ) -> dict[str, str]:
        """TaxInterpreter로 세무 전략 6섹션을 생성한다. 실패 시 빈 dict.

        세금유형별로 산출 세액을 interpreter 입력 구조(취득/양도/종부/총세액)에
        매핑한다. key_sanitizer를 경유하는 llm_provider/interpreter 경로를 쓴다.
        """
        try:
            from app.services.ai.tax_interpreter import TaxInterpreter

            holding = kwargs.get("holding_years")
            bucket = {
                "acquisition": "acquisition_tax",
                "transfer": "transfer_tax",
                "comprehensive_real_estate": "comprehensive_property_tax",
            }.get(tax_type, "acquisition_tax")
            tax_block: dict[str, Any] = {
                "tax_amount_won": round(amount),
                "tax_rate_pct": round(rate * 100, 3),
            }
            if bucket == "transfer_tax" and holding is not None:
                tax_block["holding_period_years"] = holding

            data = {
                bucket: tax_block,
                "total_tax": {
                    "total_amount_won": round(amount),
                    "effective_rate_pct": round(rate * 100, 3),
                },
                "property_value_won": round(taxable_value),
                "holding_period_years": holding,
            }
            # 세무 6섹션 생성은 10초를 넘기기 쉬워 타임아웃을 넉넉히 둔다(bid_interpreter와 동일 40s).
            result = await TaxInterpreter(timeout_sec=90.0).generate_interpretation(data)
            return result if isinstance(result, dict) else {}
        except Exception as e:  # noqa: BLE001
            logger.warning("세무 AI 해석 생성 스킵", error=str(e)[:120])
            return {}
