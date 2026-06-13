"""M3 — 적정 분양가 산정 엔진(거래사례비교 1차 + 지불여력 2차 검증).

★분양가 산정의 핵심 우선순위(실무 기준):
  1차(핵심): **거래사례비교법** — ①주변 동일종목(같은 유형·평형) 실거래 시세,
            ②주변 신규 분양 단지의 분양가. 이 둘이 적정 분양가의 앵커다.
  2차(보조): **지불여력(PIR/DSR/LTV 역산)** — 1차로 산출한 시장가를 타깃 수요가
            감당 가능한지(미분양 위험) 검증. 분양가를 직접 만드는 1차 기준이 아니다.

따라서 headline `fair_price_10k` 는 **시장 비교가**(분양가 우선 가중 + 실거래 보정)이며,
지불여력 밴드는 그 가격의 수요 수용성 판정(밴드 내/초과)에만 쓴다.

정직성: 각 데이터의 출처(live/fallback/mock/unavailable)를 그대로 전파. 비교 데이터가
전혀 없으면 fair_price 를 만들지 않고 data_source='unavailable' 반환(가짜값 금지).
규제·시장 기준수치(LTV/DSR/PIR)는 조사 시점값이며 basis 로 근거 명시.
출처: nearby_map_service(주변 실거래)·PresaleService(청약홈 주변 분양가)·KB/금융위/HF.
"""

from __future__ import annotations

from typing import Any, Optional

# ── 거래사례비교 가중(분양가가 실거래보다 더 직접적인 비교지표) ──
W_PRESALE = 0.6   # 주변 신규 분양가 가중
W_TRADE = 0.4     # 주변 실거래 시세 가중

# ── 지불여력(2차 검증) 규제·시장 기준값(2025~2026 조사 시점, 운영 반영 전 재확인) ──
DEFAULT_DSR = 0.40
DEFAULT_LTV = 0.50
DEFAULT_STRESS_RATE = 0.055
DEFAULT_TERM_YEARS = 30
DEFAULT_PIR = 6.3
_AFFORD_BASIS = (
    "지불여력 검증: DSR 40%·LTV 50%·스트레스금리 5.5%·만기 30년·PIR 6.3(2023 주거실태조사) — "
    "금융위/KB부동산/한국주택금융공사(2025~2026 조사시점). 운영 반영 전 원출처 재확인."
)
_MARKET_BASIS = "적정 분양가 1차 기준: 거래사례비교(주변 실거래 시세 + 주변 신규 분양가)."


def _loan_from_payment(annual_payment_10k: float, annual_rate: float, term_years: int) -> float:
    """연 상환액 → 대출 원금(만원). 월복리 연금현가."""
    months = max(1, int(term_years * 12))
    monthly_payment = annual_payment_10k / 12.0
    r = annual_rate / 12.0
    if r <= 0:
        return monthly_payment * months
    factor = (1.0 - (1.0 + r) ** (-months)) / r
    return monthly_payment * factor


def _affordability(
    annual_income_10k: Optional[float], income_source: Optional[str],
    *, pir: float, ltv: float, dsr: float, stress_rate: float, term_years: int,
) -> dict[str, Any]:
    """2차 검증: 타깃 가구 연소득 → 감당 가능한 가격 밴드(보수 PIR ~ 낙관 DSR/LTV)."""
    if not annual_income_10k or annual_income_10k <= 0:
        return {"data_source": "unavailable", "note": "타깃 가구 소득 없음 — KOSIS 소득 분석 선택 시 검증."}
    annual_payment = annual_income_10k * dsr
    loan_amount = _loan_from_payment(annual_payment, stress_rate, term_years)
    optimistic_10k = round(loan_amount / ltv) if ltv > 0 else 0   # DSR+LTV 낙관
    conservative_10k = round(pir * annual_income_10k)              # PIR 보수
    band_low = min(conservative_10k, optimistic_10k)
    band_high = max(conservative_10k, optimistic_10k)
    return {
        "annual_income_10k": round(annual_income_10k),
        "affordable_by_pir_10k": conservative_10k,
        "affordable_by_dsr_ltv_10k": optimistic_10k,
        "max_loan_10k": round(loan_amount),
        "band_10k": [band_low, band_high],
        "recommended_cap_10k": band_low,  # 보수적 수용 상한
        "data_source": income_source if income_source in ("live", "fallback", "mock") else "fallback",
        "assumptions": {"dsr": dsr, "ltv": ltv, "stress_rate": stress_rate, "term_years": term_years, "pir": pir},
    }


def compute_fair_price(
    *,
    comparable_trade_10k: Optional[float] = None,
    nearby_presale_10k: Optional[float] = None,
    annual_income_10k: Optional[float] = None,
    trade_source: Optional[str] = None,
    presale_source: Optional[str] = None,
    income_source: Optional[str] = None,
    pir: float = DEFAULT_PIR,
    ltv: float = DEFAULT_LTV,
    dsr: float = DEFAULT_DSR,
    stress_rate: float = DEFAULT_STRESS_RATE,
    term_years: int = DEFAULT_TERM_YEARS,
) -> dict[str, Any]:
    """적정 분양가(시장 비교 1차) + 지불여력(2차 검증)을 산정한다.

    Args:
        comparable_trade_10k: 주변 동일종목 실거래 기반 대표 분양가(만원, 1차 핵심).
        nearby_presale_10k: 주변 신규 분양가 평균(만원, 1차 핵심).
        annual_income_10k: 타깃 가구 연소득(만원, 2차 검증).
    """
    # None 가능성을 지역 변수로 명시 narrowing(가드 후 float 확정).
    presale = float(nearby_presale_10k) if (nearby_presale_10k and nearby_presale_10k > 0) else None
    trade = float(comparable_trade_10k) if (comparable_trade_10k and comparable_trade_10k > 0) else None

    # ── 1차: 거래사례비교(분양가 우선 가중 + 실거래 보정) ──
    if presale is not None and trade is not None:
        fair = presale * W_PRESALE + trade * W_TRADE
        method = f"주변 분양가({W_PRESALE:.0%}) + 실거래 시세({W_TRADE:.0%}) 가중"
        msrc = "live" if "live" in (presale_source, trade_source) else (presale_source or trade_source or "fallback")
    elif presale is not None:
        fair = presale
        method = "주변 신규 분양가 단독(실거래 비교 없음)"
        msrc = presale_source or "fallback"
    elif trade is not None:
        fair = trade
        method = "주변 실거래 시세 단독(주변 분양가 정보 없음)"
        msrc = trade_source or "fallback"
    else:
        # 비교 데이터 전무 → 가짜 분양가 만들지 않음(정직).
        return {
            "data_source": "unavailable",
            "note": "주변 실거래·분양가 비교 데이터 없음 — 적정 분양가 산출 불가(가짜값 금지).",
            "basis": _MARKET_BASIS,
            "affordability": _affordability(
                annual_income_10k, income_source,
                pir=pir, ltv=ltv, dsr=dsr, stress_rate=stress_rate, term_years=term_years),
        }

    fair_price_10k = round(fair)
    market_reference = {
        "comparable_trade_10k": round(trade) if trade is not None else None,
        "nearby_presale_10k": round(presale) if presale is not None else None,
        "fair_price_10k": fair_price_10k,
        "method": method,
        "data_source": msrc,
    }

    # ── 2차: 지불여력 검증 ──
    afford = _affordability(
        annual_income_10k, income_source,
        pir=pir, ltv=ltv, dsr=dsr, stress_rate=stress_rate, term_years=term_years)

    # 시장 적정가가 수요 지불여력 밴드 내/초과인지 판정.
    verdict = "unavailable"
    if afford.get("band_10k"):
        cap = afford["recommended_cap_10k"]
        high = afford["band_10k"][1]
        if fair_price_10k <= cap:
            verdict = "within_conservative"   # 수요 감당 가능(안전)
        elif fair_price_10k <= high:
            verdict = "within_optimistic"      # 수용 가능하나 부담
        else:
            verdict = "over_band"              # 지불여력 초과 — 미분양 위험

    return {
        "fair_price_10k": fair_price_10k,        # 헤드라인 = 시장 비교 적정 분양가
        "market_reference": market_reference,    # 1차(핵심)
        "affordability": afford,                 # 2차(보조 검증)
        "affordability_verdict": verdict,
        "data_source": msrc,
        "basis": f"{_MARKET_BASIS} {_AFFORD_BASIS}",
        "note": "적정 분양가는 거래사례비교(시장)가 1차, 지불여력은 수요 수용성 2차 검증. 전문 감정·분양 검토 필수.",
    }
