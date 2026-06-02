"""구독 과금 코어 — 등급 요금·LLM 사용 한도·할증 단가·실시간 환율.

모델:
- 청구사용량(원) = 실LLM원가($) × 실시간환율(원/$) × 등급 할증배수
- 월 포함한도(원) = 구독료 × 0.5  (이 한도까지 무료, 초과 시 서비스 중단)
- 한도 소진 시 추가결제(시뮬레이션)로 한도 충전. 할증은 기본·추가 동일 적용.

등급(할증배수): 파워 ×2.0(+100%) / 슈퍼파워 ×1.4(+40%) / 마스터 ×1.3(+30%).
상위 등급일수록 추가 단가가 저렴.
"""

import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

BUDGET_RATIO = 0.5  # 구독료의 50%를 LLM 포함한도로

# 구독 등급별 요금(원) + 할증배수
TIER_BILLING: dict[str, dict[str, float]] = {
    "power": {"fee_krw": 24500, "multiplier": 2.0, "label": "파워"},
    "superpower": {"fee_krw": 49900, "multiplier": 1.4, "label": "슈퍼파워"},
    "master": {"fee_krw": 99000, "multiplier": 1.3, "label": "마스터"},
}

# LLM 모델 단가(USD / 1M tokens) — 청구계산용. 키는 모델명 부분일치.
MODEL_PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "opus": {"in": 15.0, "out": 75.0},
    "sonnet": {"in": 3.0, "out": 15.0},
    "haiku": {"in": 0.8, "out": 4.0},
}
_DEFAULT_PRICING = {"in": 3.0, "out": 15.0}  # 미상 모델 = sonnet 기준

_FALLBACK_RATE = 1350.0  # 환율 조회 실패 시 폴백(원/$)
_RATE_CACHE: dict[str, Any] = {"rate": _FALLBACK_RATE, "ts": 0.0}
_RATE_TTL = 3600.0  # 1시간 캐시


def tier_fee_krw(tier: str) -> float:
    return float(TIER_BILLING.get(tier, {}).get("fee_krw", 0.0))


def tier_multiplier(tier: str) -> float:
    return float(TIER_BILLING.get(tier, {}).get("multiplier", 1.0))


def tier_included_budget_krw(tier: str) -> float:
    """등급 월 포함 LLM 한도(원) = 구독료 × 0.5."""
    return round(tier_fee_krw(tier) * BUDGET_RATIO)


def is_metered_tier(tier: str) -> bool:
    """LLM 사용량 과금이 적용되는 구독 등급인지."""
    return tier in TIER_BILLING


async def get_usd_krw_rate() -> float:
    """실시간 USD/KRW 환율(원/$). 1시간 캐시 + 실패 시 폴백."""
    now = time.time()
    if now - _RATE_CACHE["ts"] < _RATE_TTL and _RATE_CACHE["rate"]:
        return float(_RATE_CACHE["rate"])
    rate = None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://open.er-api.com/v6/latest/USD")
            if r.status_code == 200:
                krw = r.json().get("rates", {}).get("KRW")
                if krw and float(krw) > 0:
                    rate = float(krw)
    except Exception as e:  # noqa: BLE001
        logger.debug("환율 조회 실패, 폴백 사용", err=str(e)[:60])
    if rate is None:
        rate = float(_RATE_CACHE["rate"] or _FALLBACK_RATE)
    _RATE_CACHE.update({"rate": rate, "ts": now})
    return rate


def model_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """토큰 사용량 → 실 LLM 원가(USD)."""
    m = (model or "").lower()
    pricing = _DEFAULT_PRICING
    for key, p in MODEL_PRICING_USD_PER_MTOK.items():
        if key in m:
            pricing = p
            break
    return (input_tokens / 1_000_000) * pricing["in"] + (output_tokens / 1_000_000) * pricing["out"]


def billed_krw(real_cost_usd: float, tier: str, rate: float) -> float:
    """실원가($) → 청구액(원) = $×환율×등급배수. 할증은 기본·추가 동일."""
    return real_cost_usd * rate * tier_multiplier(tier)


def markup_quote(real_cost_usd: float, tier: str, rate: float) -> dict[str, Any]:
    """추가결제 견적: 실원가 대비 등급 할증 적용 청구액(시뮬레이션 표시용)."""
    billed = billed_krw(real_cost_usd, tier, rate)
    return {
        "real_cost_usd": round(real_cost_usd, 4),
        "real_cost_krw": round(real_cost_usd * rate),
        "multiplier": tier_multiplier(tier),
        "billed_krw": round(billed),
        "exchange_rate": round(rate, 2),
    }
