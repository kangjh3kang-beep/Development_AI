"""구독 과금 코어 — 등급 요금·LLM 사용 한도·할증 단가·실시간 환율.

모델:
- 청구사용량(원) = 실LLM원가($) × 실시간환율(원/$) × 등급 할증배수
- 월 포함한도(원) = 구독료 × 0.5  (이 한도까지 무료, 초과 시 서비스 중단)
- 한도 소진 시 추가결제(시뮬레이션)로 한도 충전. 할증은 기본·추가 동일 적용.

등급(할증배수, 낮은등급 높은마진): 파워 ×1.5(+50%) / 슈퍼파워 ×1.4(+40%) / 마스터 ×1.3(+30%).
비구독(free/guest)은 무료횟수 소진 후 과금 시 ×1.5(+50%). 상위 등급일수록 추가 단가가 저렴.
"""

import contextlib
import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# ── 과금 설정(관리자 수정 가능). 기본값 → DB(billing_config) 오버라이드 ──
# 파이프라인 7단계: site_analysis/design/cost/feasibility/tax/esg/report
_PIPELINE_STAGES = ["site_analysis", "design", "cost", "feasibility", "tax", "esg", "report"]

_DEFAULT_CONFIG: dict[str, Any] = {
    "budget_ratio": 0.5,  # 구독료의 N%를 LLM 포함한도로
    "tiers": {
        # base_quota_krw=월 기본 포함 사용량(원), overage_margin_pct=초과분 원가 마진율(%).
        # multiplier는 하위호환(overage_margin_pct 우선).
        "power": {"fee_krw": 24500, "multiplier": 1.5, "overage_margin_pct": 50, "base_quota_krw": 12250, "label": "파워"},
        "superpower": {"fee_krw": 49900, "multiplier": 1.4, "overage_margin_pct": 40, "base_quota_krw": 24950, "label": "슈퍼파워"},
        "master": {"fee_krw": 99000, "multiplier": 1.3, "overage_margin_pct": 30, "base_quota_krw": 49500, "label": "마스터"},
    },
    "service_fees": {
        "project_create": 2000,           # 프로젝트 생성 건당
        "land_analysis": 2000,            # 토지분석(구독자) 건당
        "sales_provision": 50000,         # 분양현장 생성 건당(관리자 책정)
        "photoreal_render": 3000,         # AI 포토리얼 렌더(외부 GPU 호출) 건당
        "concept_render": 0,              # 컨셉 조감도/투시도(text2img) 건당. 기본 0=무료(관리자 미책정 시 무료)
        "registry_issue": 1200,           # 등기부등본 발급·열람 건당(AI 분석 없음)
        "registry_analysis": 2000,        # 등기부등본 권리분석(AI) 건당 — 발급/열람과 차별화
        "stages": {s: 2000 for s in _PIPELINE_STAGES},  # 파이프라인 단계별 건당
        # 분석 모듈(시장 인구/소득 등) 건당 사용료 맵. 기본 빈 dict = 전부 무료.
        # 관리자가 설정한 키만 과금되고, 미설정 키는 0원(무료·실행).
        # 설정 가능한 키 예: persona_sales_agent / persona_urban_planner(실무 전문가 페르소나 LLM,
        #   use_llm=True일 때만 적용·미설정=무료) — service_fee_analysis_module(key)가 미설정 시 0 반환.
        "analysis_modules": {},
        # 대량 다필지 배치 — 필지당 단가(원). 기본 0 = 무료(관리자 미책정 시 무료 실행).
        "bulk_parcel_per_unit": 0,
    },
    "free_tier": {
        "analysis_fee": {"free": 5000, "guest": 10000},  # 무료 소진 후 토지분석 단가
        "analysis_quota": {"free": 3, "guest": 1},        # 무료 토지분석 횟수
    },
}

# 런타임 설정(기본 복제). apply_config로 in-place 갱신(별칭 유지).
_CONFIG: dict[str, Any] = {
    "budget_ratio": _DEFAULT_CONFIG["budget_ratio"],
    "tiers": {k: dict(v) for k, v in _DEFAULT_CONFIG["tiers"].items()},
    "service_fees": {
        "project_create": _DEFAULT_CONFIG["service_fees"]["project_create"],
        "land_analysis": _DEFAULT_CONFIG["service_fees"]["land_analysis"],
        "sales_provision": _DEFAULT_CONFIG["service_fees"]["sales_provision"],
        "photoreal_render": _DEFAULT_CONFIG["service_fees"]["photoreal_render"],
        "concept_render": _DEFAULT_CONFIG["service_fees"]["concept_render"],
        "registry_issue": _DEFAULT_CONFIG["service_fees"]["registry_issue"],
        "registry_analysis": _DEFAULT_CONFIG["service_fees"]["registry_analysis"],
        "stages": dict(_DEFAULT_CONFIG["service_fees"]["stages"]),
        "analysis_modules": dict(_DEFAULT_CONFIG["service_fees"]["analysis_modules"]),
        "bulk_parcel_per_unit": _DEFAULT_CONFIG["service_fees"]["bulk_parcel_per_unit"],
    },
    "free_tier": {
        "analysis_fee": dict(_DEFAULT_CONFIG["free_tier"]["analysis_fee"]),
        "analysis_quota": dict(_DEFAULT_CONFIG["free_tier"]["analysis_quota"]),
    },
}

# 하위호환 별칭(같은 객체 참조 — apply_config는 in-place 갱신하므로 유효 유지)
TIER_BILLING: dict[str, dict[str, Any]] = _CONFIG["tiers"]


def get_config() -> dict[str, Any]:
    return _CONFIG


def apply_config(override: dict[str, Any]) -> None:
    """관리자 수정값을 런타임 설정에 병합(in-place, 별칭 유지)."""
    if not isinstance(override, dict):
        return
    if "budget_ratio" in override:
        with contextlib.suppress(ValueError, TypeError):
            _CONFIG["budget_ratio"] = float(override["budget_ratio"])
    for tier, vals in (override.get("tiers") or {}).items():
        if not isinstance(vals, dict):
            continue
        # 신규 플랜 추가 허용(기존에 없던 tier면 기본값으로 생성).
        if tier not in _CONFIG["tiers"]:
            _CONFIG["tiers"][tier] = {"fee_krw": 0, "multiplier": 1.0, "label": tier}
        # fee_krw(월요금)·label·base_quota_krw(기본 사용량)·overage_margin_pct(초과 마진율%).
        # multiplier는 하위호환 유지(overage_margin_pct 미설정 시 사용).
        for k in ("fee_krw", "multiplier", "label", "base_quota_krw", "overage_margin_pct"):
            if k in vals:
                _CONFIG["tiers"][tier][k] = vals[k]
    # 플랜 삭제(_remove_tiers). 시스템 보호 등급은 삭제 불가(과금·권한 무결성).
    for tier in (override.get("_remove_tiers") or []):
        if tier in _CONFIG["tiers"] and tier not in {"free", "guest", "super_admin"}:
            _CONFIG["tiers"].pop(tier, None)
    sf = override.get("service_fees") or {}
    for k in ("project_create", "land_analysis", "sales_provision", "photoreal_render",
              "concept_render", "registry_issue", "registry_analysis", "bulk_parcel_per_unit"):
        if k in sf:
            try:
                _CONFIG["service_fees"][k] = max(0.0, float(sf[k]))  # 음수 차단
            except (ValueError, TypeError):
                _CONFIG["service_fees"][k] = sf[k]
    for s, v in (sf.get("stages") or {}).items():
        if s in _CONFIG["service_fees"]["stages"]:
            _CONFIG["service_fees"]["stages"][s] = v
    # 분석 모듈 사용료 병합 — 관리자가 보낸 키:값(원)을 set한다.
    # 숫자로 변환 가능할 때만, 음수는 0으로 방지(허위 마이너스 차감 차단).
    am = _CONFIG["service_fees"].setdefault("analysis_modules", {})
    for k, v in (sf.get("analysis_modules") or {}).items():
        with contextlib.suppress(ValueError, TypeError):
            am[k] = max(0.0, float(v))
    ft = override.get("free_tier") or {}
    for sub in ("analysis_fee", "analysis_quota"):
        for t, v in (ft.get(sub) or {}).items():
            _CONFIG["free_tier"][sub][t] = v


# ── 서비스 사용료 접근자(설정 기반) ──
def service_fee_bulk_parcel_per_unit() -> float:
    """대량 다필지 배치 — 필지당 단가(원). 미설정 시 0(무료)."""
    return max(0.0, float(_CONFIG["service_fees"].get("bulk_parcel_per_unit", 0) or 0))


def service_fee_project_create() -> float:
    return float(_CONFIG["service_fees"].get("project_create", 0))


def service_fee_land_analysis() -> float:
    return float(_CONFIG["service_fees"].get("land_analysis", 0))


def service_fee_sales_provision() -> float:
    return float(_CONFIG["service_fees"].get("sales_provision", 0))


def service_fee_photoreal_render() -> float:
    return float(_CONFIG["service_fees"].get("photoreal_render", 3000))


def service_fee_concept_render() -> float:
    """컨셉 조감도/투시도(text2img) 건당 사용료. 관리자 미설정 시 0원(무료·실행)."""
    return max(0.0, float(_CONFIG["service_fees"].get("concept_render", 0) or 0))


def service_fee_registry_analysis() -> float:
    return float(_CONFIG["service_fees"].get("registry_analysis", 2000))


def service_fee_registry_issue() -> float:
    return float(_CONFIG["service_fees"].get("registry_issue", 1200))


def service_fee_stage(stage: str) -> float:
    return float(_CONFIG["service_fees"].get("stages", {}).get(stage, 0))


def service_fee_analysis_module(key: str) -> float:
    """분석 모듈(시장 인구/소득 등) 건당 사용료. 관리자 미설정 시 0원(무료·실행)."""
    try:
        return max(0.0, float(_CONFIG["service_fees"].get("analysis_modules", {}).get(key, 0) or 0))
    except (ValueError, TypeError):
        return 0.0


def analysis_module_fees() -> dict:
    """관리자가 설정한 분석 모듈 사용료 맵(미설정 시 빈 dict = 전부 무료)."""
    return {k: float(v) for k, v in (_CONFIG["service_fees"].get("analysis_modules", {}) or {}).items()}


def free_tier_analysis_fee(tier: str) -> float:
    return float(_CONFIG["free_tier"]["analysis_fee"].get(tier, _CONFIG["free_tier"]["analysis_fee"].get("free", 0)))


def free_tier_analysis_quota(tier: str) -> int:
    return int(_CONFIG["free_tier"]["analysis_quota"].get(tier, 0))

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


# 비구독(free/guest) 할증배수 — 무료횟수 소진 후 과금 시 적용(낮은등급 높은마진).
_NON_SUB_MULTIPLIER = 1.5


def tier_multiplier(tier: str) -> float:
    """등급 초과분 마진배수. 플랜별 overage_margin_pct(%)가 있으면 1+pct/100,
    없으면 기존 multiplier. 비구독(free/guest 등)은 1.5(+50%)."""
    if tier in TIER_BILLING:
        t = TIER_BILLING[tier]
        pct = t.get("overage_margin_pct")
        if pct is not None:
            try:
                return 1.0 + float(pct) / 100.0
            except (ValueError, TypeError):
                pass
        return float(t.get("multiplier", 1.0))
    return _NON_SUB_MULTIPLIER


def tier_included_budget_krw(tier: str) -> float:
    """등급 월 포함 LLM 사용량(원). 플랜별 base_quota_krw가 설정돼 있으면 그 값,
    없으면 구독료 × budget_ratio(하위호환)."""
    t = TIER_BILLING.get(tier, {})
    bq = t.get("base_quota_krw")
    if bq is not None:
        try:
            v = float(bq)
            if v >= 0:
                return round(v)
        except (ValueError, TypeError):
            pass
    return round(tier_fee_krw(tier) * float(_CONFIG.get("budget_ratio", 0.5)))


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


def markup_quote(real_cost_usd: float, tier: str, rate: float, *, internal: bool = False) -> dict[str, Any]:
    """추가결제 견적.

    ★할증배수(50/40/30%)·실원가·환율은 **내부 정책**이므로 기본은 노출하지 않고
    사용자/외부에는 **실지급액(원)만** 반환한다. internal=True(관리자/감사)일 때만 상세 포함.
    """
    billed = round(billed_krw(real_cost_usd, tier, rate))
    out: dict[str, Any] = {"amount_krw": billed}  # 실지급액(원)
    if internal:
        out.update({
            "real_cost_usd": round(real_cost_usd, 4),
            "real_cost_krw": round(real_cost_usd * rate),
            "multiplier": tier_multiplier(tier),
            "exchange_rate": round(rate, 2),
        })
    return out


def public_status(status: dict[str, Any]) -> dict[str, Any]:
    """사용자/외부 노출용 과금 현황 — 내부 정책(배수·환율) 제거, 실지급액(원)만."""
    return {
        "tier": status.get("tier"),
        "tier_label": status.get("tier_label"),
        "metered": status.get("metered"),
        "fee_krw": status.get("fee_krw"),
        "included_budget_krw": status.get("included_budget_krw"),
        "budget_krw": status.get("budget_krw"),
        "billed_krw": status.get("billed_krw"),
        "remaining_krw": status.get("remaining_krw"),
        "usage_pct": status.get("usage_pct"),
        "blocked": status.get("blocked"),
        # 서비스 사용료(LLM 별개) — 실지급액(원)만
        "service_fee_krw": status.get("service_fee_krw"),
        "free_analysis_quota": status.get("free_analysis_quota"),
        "free_analysis_used": status.get("free_analysis_used"),
        "free_analysis_remaining": status.get("free_analysis_remaining"),
    }
