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


def coerce_fee(value: Any, *, where: str) -> float | None:
    """요율 값을 float(0 이상)으로 정규화한다. **숫자가 아니면 None**(= 적용 거부).

    왜 거부가 맞나: 이 값들의 소비처(`service_fee_project_create()` 등)는 `float(...)` 를
    **무방비로** 호출한다. 숫자가 아닌 값을 설정에 넣으면 그 순간이 아니라 **나중에 과금하는
    요청 경로에서** ValueError 가 터진다. 게다가 `save_config` 가 그것을 DB 에 영속시키므로
    재기동해도 되살아난다 — 즉 관리자 오타 하나가 **지속적인 과금 장애**가 된다.

    그래서 적용을 거부하고 **이전 값을 보존**한다. 다만 조용히 버리면 관리자는 설정이 반영된
    줄 알므로 반드시 경고를 남긴다(무언 실패 금지).

    음수는 0으로 clamp 한다(허위 마이너스 차감 차단).
    """
    try:
        return max(0.0, float(value))
    except (ValueError, TypeError):
        # ★락의 범위: 테스트는 "경고가 뜬다"와 "`where` 가 **어느 키**인지 말한다"를 잠근다.
        #   아래 **문구 자체는 일부러 잠그지 않았다** — 사람이 읽는 산문이라 계약이 아니고,
        #   단언하면 표현을 다듬을 때마다 깨지는 취약한 락이 된다(변이 검증에서 이 줄만
        #   살아남는 것은 그 때문이며 구멍이 아니다).
        logger.warning(
            "과금 요율 값이 숫자가 아니어서 **적용하지 않았다**(이전 값 유지)",
            where=where, value=repr(value)[:80],
        )
        return None


def apply_config(override: dict[str, Any]) -> None:
    """관리자 수정값을 런타임 설정에 병합(in-place, 별칭 유지).

    ★값 위생은 `coerce_fee` 한 곳으로 모았다. 이전에는 같은 함수 안에서 요율 세 뭉치가
    **서로 다르게** 처리됐다 — `service_fees` 단일 키는 변환 실패 시 **원본을 그대로 저장**해
    "음수 차단" 주석이 약속한 위생을 우회했고, `stages` 는 **검증이 아예 없었으며**,
    `analysis_modules` 만 올바르게 건너뛰었다. 옳은 패턴이 바로 옆에 있었는데 나머지가
    그것을 안 쓰고 있었다.
    """
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
            fee = coerce_fee(sf[k], where=f"service_fees.{k}")
            if fee is not None:
                _CONFIG["service_fees"][k] = fee
    for s, v in (sf.get("stages") or {}).items():
        if s in _CONFIG["service_fees"]["stages"]:
            fee = coerce_fee(v, where=f"service_fees.stages.{s}")
            if fee is not None:
                _CONFIG["service_fees"]["stages"][s] = fee
    # 분석 모듈 사용료 병합 — 관리자가 보낸 키:값(원)을 set한다.
    am = _CONFIG["service_fees"].setdefault("analysis_modules", {})
    for k, v in (sf.get("analysis_modules") or {}).items():
        fee = coerce_fee(v, where=f"service_fees.analysis_modules.{k}")
        if fee is not None:
            am[k] = fee
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

# ── LLM 모델 단가(USD / 1M tokens) — 실원가 계산의 SSOT ──────────────────────────
#
# ★2026-08-01 정정: 종전 표는 세대(opus/sonnet/haiku) 3키뿐이라 두 가지로 틀렸다.
#   ①`opus` $15/$75 = **Opus 3 시절 단가**. 실제 Opus 4.5~5는 $5/$25 → 원가 3배 과다계상.
#   ②OpenAI·Google 모델은 표에 아예 없어 전부 `_DEFAULT_PRICING`(sonnet $3/$15)로 폴백.
#     gpt-4o-mini는 실제 $0.15/$0.60이라 **20배 이상 과다**였다(그게 OpenAI 기본 모델).
#   할증배수(50/40/30%)가 이 원가에 곱해지므로 오차가 그대로 청구액에 실린다.
#
# ★매칭 규칙: **긴 키 우선(부분일치)**. 세대 키(`opus`)만 두면 `claude-opus-5`가 구형 단가에
#   걸린다. 정확 ID를 먼저 등재하고 세대 키는 미등재 신모델용 안전망으로만 남긴다.
#
# ★유지보수 계약: `llm_provider.PROVIDERS`가 노출하는 모든 모델은 여기 등재돼야 한다.
#   test_billing_pricing.py 의 불변식이 이를 강제한다(노출 모델 ⊆ 등재 모델).
MODEL_PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    # ── Anthropic (출처: Anthropic 공식 단가표, 2026-06-24 기준) ──
    "claude-fable-5": {"in": 10.0, "out": 50.0},
    "claude-opus-5": {"in": 5.0, "out": 25.0},
    "claude-opus-4-8": {"in": 5.0, "out": 25.0},
    "claude-opus-4-7": {"in": 5.0, "out": 25.0},
    "claude-opus-4-6": {"in": 5.0, "out": 25.0},
    "claude-sonnet-5": {"in": 3.0, "out": 15.0},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-haiku-4-5": {"in": 1.0, "out": 5.0},
    # ── OpenAI / Google ──
    # ★미검증(verified=False): 아래 값은 각 사 공식 단가표로 **재확인 필요**하다. 다만 현행
    #   폴백($3/$15)보다는 실제에 훨씬 가까우므로(gpt-4o-mini 기준 20배→오차 소폭) 등재해
    #   과다청구를 먼저 줄인다. 확인 후 이 주석과 함께 값을 확정할 것.
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "gpt-4o": {"in": 2.50, "out": 10.0},
    "gemini-2.5-pro": {"in": 1.25, "out": 10.0},
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
    "gemini-2.0-flash": {"in": 0.10, "out": 0.40},
    # ── 세대 안전망(미등재 신모델용) — 정확 ID가 없을 때만 걸린다 ──
    "opus": {"in": 5.0, "out": 25.0},
    "sonnet": {"in": 3.0, "out": 15.0},
    "haiku": {"in": 1.0, "out": 5.0},
}
# 어느 키에도 걸리지 않은 모델. ★조용히 쓰지 않는다 — model_cost_usd가 경고 로그를 남긴다
#   (미등재 모델을 노출하면 청구가 틀어지므로 운영이 즉시 알아채야 한다).
_DEFAULT_PRICING = {"in": 3.0, "out": 15.0}

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


def resolve_model_pricing(model: str) -> tuple[dict[str, float], str | None]:
    """모델명 → (단가, 매칭된 키). 미등재면 (기본단가, None).

    ★긴 키 우선: 정확 ID(`claude-opus-5`)가 세대 키(`opus`)를 이긴다. dict 삽입순서에 기대면
    `opus`가 먼저 걸려 신형 모델이 구형 단가로 청구되는 종전 결함이 재발한다.
    """
    m = (model or "").lower()
    for key in sorted(MODEL_PRICING_USD_PER_MTOK, key=len, reverse=True):
        if key in m:
            return MODEL_PRICING_USD_PER_MTOK[key], key
    return _DEFAULT_PRICING, None


def model_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """토큰 사용량 → 실 LLM 원가(USD).

    ★미등재 모델은 조용히 넘어가지 않는다. 폴백 단가로 계산은 하되(청구 파이프라인을 죽이지
    않는다) 경고를 남겨 운영이 등재 누락을 즉시 알 수 있게 한다 — 종전에는 어떤 모델이든
    말없이 sonnet 단가가 적용돼 OpenAI/Google 전 모델이 과다청구되고 있었다.
    """
    pricing, matched = resolve_model_pricing(model)
    if matched is None:
        logger.warning(
            "LLM 단가 미등재 모델 — 폴백 단가로 청구됨(등재 필요)",
            model=(model or "")[:80], fallback=_DEFAULT_PRICING,
        )
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
