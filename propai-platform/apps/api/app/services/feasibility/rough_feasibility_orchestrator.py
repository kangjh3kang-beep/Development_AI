"""사업성 개략수지 통합 오케스트레이터.

주소(+다필지)만 넣으면 '개략(rough) 사업성 수지'를 한 번에 조립한다. 새 계산식은 만들지
않고, 이미 검증된 엔진들을 순서대로 호출·결합만 한다(재구현 0):

  1) 통합면적/용도/실효용적률  = build_integrated_context (다필지 면적가중, N=1 항등)
  2) Top1 개발방향/GFA          = FeasibilityServiceV2.auto_recommend_top3
  3) 토지비(적정금액)           = desk_appraisal(탁상감정) → land_cost_engine(취득세 등)
  4) 공사비(국토부 기본형건축비) = construction_cost_engine(SSOT 단가)
  5) 분양수입(주변 실거래)       = suggest_base_price → (폴백) regional_pricing
  6) 총사업비 + 20% 마진         = aggregate_feasibility(토지+공사+금융+제경비) → 총사업비×0.20
  7) 2차 사용자 수정(overrides)  = 값 교체 후 6·8 재계산(각 값 source=user_override)
  8) 월별 DCF                    = dcf_assembly.assemble_monthly_dcf(공용 SSOT — 상세수지와 동일 규칙)

무목업 원칙: 실데이터를 못 구한 축은 값을 null로 두고 degraded_notes에 사유를 남긴다.
가짜 0·임의 추정값을 만들지 않는다(정직 degrade). 각 축에는 basis/evidence/source를 붙여
'왜 이 값인가'를 추적 가능하게 한다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

# ── 재사용 자산(모듈 최상단 import — 테스트가 monkeypatch로 대체하기 쉽게 이름을 노출) ──
from app.services.feasibility import construction_cost_engine, land_cost_engine, regional_pricing
from app.services.feasibility.aggregation_engine import aggregate_feasibility
from app.services.feasibility.dcf_assembly import assemble_monthly_dcf
from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
from app.services.land_intelligence.comprehensive_analysis_service import (
    build_integrated_context,
)
from app.services.land_intelligence.desk_appraisal_service import desk_appraisal
from app.services.tax.project_charges import compute_developer_stage_charges, parse_bool_flag

logger = logging.getLogger(__name__)

# ── 상수(모두 문서화된 표준 가정 — 임의 날조 아님) ──
_PYEONG_SQM = 3.305785
# 연면적(GFA)→공급(분양)면적 표준비. suggest._SALE_EFFICIENCY(=0.70)와 동일 근거로,
# 분양가능면적 = GFA × 0.70. (전용률·주거공용 반영한 연면적 대비 분양면적 표준치)
_GFA_TO_SALEABLE_RATIO = 0.70
_DEFAULT_MARGIN_RATE_PCT = 20.0        # 일반사업 기본 개발이익 마진(총사업비 대비)
_DEFAULT_DISCOUNT_RATE = 0.06          # DCF 할인율(연) — /cashflow 엔드포인트 기본과 동일
# 엔진 금융·제경비 비율 산출이 실패했을 때만 쓰는 정직 폴백비율(토지+공사 대비).
_FALLBACK_FINANCE_RATIO = 0.08
_FALLBACK_OTHER_RATIO = 0.04

# 개발방향 추천이 자기자본 미입력 시 쓰는 기본치(auto_recommend_top3 기본과 동일 — 100억).
_DEFAULT_EQUITY_WON = 10_000_000_000

# 개발유형 건축유형(_get_building_type) → MOLIT 실거래 물건유형(get_transactions prop_type).
# 주변 실거래로 분양단가를 잡을 때 어떤 실거래 API를 조회할지 결정한다(주거=아파트 등).
_BUILDING_TO_MOLIT_PROP: dict[str, str] = {
    "apartment": "apt",
    "officetel": "officetel",
    "office": "commercial",     # 업무시설 = 비주거용(상업) 실거래
    "house": "house",           # 단독·다가구
    "townhouse": "villa",       # 연립·다세대(타운하우스)
}
# 주변 실거래 표본이 이보다 적으면 중앙값 신뢰가 낮아 지역 시세표로 폴백한다(무목업 — 소표본 미신뢰).
_MIN_TRADE_SAMPLES = 5

# 오케스트레이터 전용 서비스 인스턴스(스테이트리스 — 재사용). 테스트는 이 이름을 교체 가능.
_service = FeasibilityServiceV2()


# ─────────────────────────────────────────────────────────────────────────────
# 얇은 래퍼(테스트 seam) — 네트워크·엔진 의존부를 함수 경계로 분리해 mock을 쉽게 한다.
# ─────────────────────────────────────────────────────────────────────────────
async def _auto_recommend(
    *, address: str, land_area_sqm: float | None, region: str,
    equity_won: int, parcels: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Top3 개발방향 추천 호출(규칙 산출 — use_llm=False로 LLM·과금 없음)."""
    return await _service.auto_recommend_top3(
        address=address,
        land_area_sqm=land_area_sqm,
        region=region,
        equity_won=equity_won,
        use_llm=False,
        parcels=parcels,
    )


def _engine_cost_ratios(input_used: Any) -> tuple[float, float, str | None]:
    """기존 수지엔진(v2)을 1회 돌려 '금융비·제경비 비율(토지+공사 대비)'만 추출한다.

    새 산식을 만들지 않고 '기존 엔진 비율'을 그대로 재사용하기 위함. 실패하면 문서화된
    표준 폴백비율(금융8%+제경비4%)로 정직 강등하고 사유를 note로 반환한다.
    """
    try:
        out = _service.calculate(input_used)
        denom = float(out.total_land_cost_won or 0) + float(out.total_construction_cost_won or 0)
        if denom > 0:
            fin = float(out.total_finance_cost_won or 0) / denom
            oth = float(out.total_other_cost_won or 0) / denom
            return fin, oth, None
    except Exception as e:  # noqa: BLE001 — 비율 추출 실패는 폴백비율로 강등(무중단)
        logger.warning("엔진 금융·제경비 비율 추출 실패 — 표준 폴백비율 적용: %s", str(e)[:120])
    return (
        _FALLBACK_FINANCE_RATIO,
        _FALLBACK_OTHER_RATIO,
        "금융·제경비: 엔진 비율 추출 실패 — 표준 폴백비율(금융 8%+제경비 4%) 적용(참고용)",
    )


async def _sigungu5_from_address(address: str) -> str | None:
    """주소 → VWorld 지오코딩 → PNU → 시군구 5자리(법정동시군구코드). 실패 시 None(가짜 코드 금지).

    ★HIGH-1: 주변 실거래(MOLIT) 조회는 site_id/db 없이 시군구 5자리 코드만 있으면 된다.
    현장(sales site) 연결이 없어도 이 함수로 시군구를 스스로 확보해 실거래를 1순위로 쓴다.
    """
    if not address:
        return None
    try:
        from app.services.external_api.vworld_service import VWorldService
        from apps.api.integrations.region_codes import pnu_to_bcode

        geo = await VWorldService().geocode_address(address)
        pnu = (geo or {}).get("pnu") or ""
        conv = pnu_to_bcode(pnu)          # (시군구 5자리, 법정동 5자리) — 아니면 None
        if conv:
            return conv[0]
        # PNU가 짧아도 앞 5자리가 숫자면 시군구 코드로 사용(자체 충족).
        if len(pnu) >= 5 and pnu[:5].isdigit():
            return pnu[:5]
    except Exception as e:  # noqa: BLE001 — 지오코딩 실패는 지역 시세로 폴백(무중단)
        logger.warning("분양단가 실거래용 지오코딩 실패 — 지역 시세 폴백: %s", str(e)[:120])
    return None


async def _trade_sale_price_per_pyeong(
    *, dev_type: str, address: str,
) -> tuple[int, str, str, None] | None:
    """주변 실거래(MOLIT) 직접 조회 → 분양단가(원/평, 공급면적). site_id 불필요(★HIGH-1).

    주소를 지오코딩해 시군구 5자리를 얻고, 검증된 공용 헬퍼 _trade_per_pyeong으로 동·시군구
    전용 평당가 중앙값을 구한다(재구현 0). 실거래는 '전용면적' 기준이므로, 개략수지가 쓰는
    '공급(분양가능)면적' 기준으로 환산(×전용률)하고 신축 분양 프리미엄(기준안 1.15)을 곱한다
    — sales site 연결 경로(suggest_base_price base tier)와 동일 산식으로 일치시킨다.

    표본 부족(_MIN_TRADE_SAMPLES 미만)·조회 실패면 None(호출부가 지역 시세로 폴백).
    """
    sigungu5 = await _sigungu5_from_address(address)
    if not sigungu5:
        return None
    try:
        # 검증된 실거래 헬퍼·환산상수 재사용(SSOT — 값 발산 방지).
        from app.services.sales.pricing.suggest import (
            _JEONYULRYUL,
            _PREMIUM,
            _extract_dong,
            _trade_per_pyeong,
        )

        building = _service._get_building_type(dev_type)
        prop_type = _BUILDING_TO_MOLIT_PROP.get(building, "apt")
        dong = _extract_dong(address)
        pp = await _trade_per_pyeong(sigungu5, dong, prop_type)
    except Exception as e:  # noqa: BLE001 — 실거래 조회 실패는 지역 시세로 폴백(무중단)
        logger.warning("주변 실거래(MOLIT) 분양단가 조회 실패 — 지역 시세 폴백: %s", str(e)[:120])
        return None

    d_med, d_n = pp["dong"]["median"], pp["dong"]["n"]
    s_med, s_n = pp["sigungu"]["median"], pp["sigungu"]["n"]
    # 동(정밀) 우선, 표본 부족 시 시군구. 둘 다 미달이면 None(소표본 미신뢰 — 무목업).
    if d_med and d_n >= _MIN_TRADE_SAMPLES:
        scope, med, n = "동", int(d_med), int(d_n)
    elif s_med and s_n >= _MIN_TRADE_SAMPLES:
        scope, med, n = "시군구", int(s_med), int(s_n)
    else:
        return None

    premium = _PREMIUM["base"]
    # 전용 평당가(만원) → 공급 평당가(원/평) × 신축 프리미엄.
    price = int(round(med * _JEONYULRYUL * premium * 10000))
    basis = (
        f"주변 실거래(MOLIT) {scope} 중앙값 {med:,}만원/평(전용, 표본 {n}건·최근 8개월) × "
        f"전용률 {_JEONYULRYUL} × 신축 프리미엄 {premium} → 공급 평당가(공급면적 기준)"
    )
    return price, "주변 실거래(MOLIT)", basis, None


async def _resolve_sale_price_per_pyeong(
    *, db: Any, site_id: Any, dev_type: str, region: str, address: str,
) -> tuple[int | None, str, str, str | None]:
    """분양단가(원/평, 공급면적 기준) 결정 — 실거래 1순위, 지역 시세표는 '추정' 폴백.

    우선순위:
      1) sales site 연결(db+site_id) 있으면 suggest_base_price(신뢰루프) — 현장 확정 우선.
      2) 주변 실거래(MOLIT) 직접 조회 — site_id 없이도 주소 지오코딩으로 확보(★HIGH-1 핵심).
      3) 지역×유형 시세 테이블 폴백 — 이때만 '(추정·비실거래)' 명시 + degraded note.

    Returns: (price_won_per_pyeong|None, source, basis, degraded_note|None)
    """
    # 1순위: 주변 실거래(MOLIT) 앵커 + 신뢰루프 — sales site 연결(db+site_id) 있을 때만.
    if db is not None and site_id is not None:
        try:
            from app.services.sales.pricing.suggest import suggest_base_price

            res = await suggest_base_price(db, site_id)
            if isinstance(res, dict) and res.get("data_source") == "live":
                tiers = res.get("tiers") or []
                # '기준(base)' 프리미엄 tier 채택(없으면 중앙 tier).
                base_tier = next((t for t in tiers if t.get("tier") == "base"), None)
                if base_tier is None and tiers:
                    base_tier = tiers[len(tiers) // 2]
                pp10k = (base_tier or {}).get("per_pyeong_10k")
                if pp10k:
                    price = int(round(float(pp10k) * 10000))  # 만원/평 → 원/평
                    conf = (res.get("trust") or {}).get("confidence")
                    conf_txt = f"(신뢰도 {conf:.0%})" if isinstance(conf, (int, float)) else ""
                    return (
                        price,
                        "주변 실거래(MOLIT)+신뢰루프",
                        f"주변 실거래 시세×신축 프리미엄 기준 분양단가{conf_txt} · 공급면적 기준",
                        None,
                    )
        except Exception as e:  # noqa: BLE001 — 실거래 조회 실패는 다음 순위로 폴백(무중단)
            logger.warning("suggest_base_price 실패 — 주변 실거래 직접조회로 폴백: %s", str(e)[:120])

    # 2순위: 주변 실거래(MOLIT) 직접 조회 — site_id 없이 주소→시군구로 확보(★HIGH-1).
    trade = await _trade_sale_price_per_pyeong(dev_type=dev_type, address=address)
    if trade is not None:
        return trade

    # 3순위(폴백): 지역×유형 시세 테이블(수지·추천 공용 SSOT) — 실거래 아님(추정치).
    try:
        price, basis_key = regional_pricing.resolve_regional_sale_price_per_pyeong(
            dev_type=dev_type, region=region, address=address,
        )
    except Exception as e:  # noqa: BLE001 — 시세 테이블 실패는 분양단가 미확보(정직 null)
        logger.warning("지역 시세 테이블 조회 실패: %s", str(e)[:120])
        return None, "unavailable", "분양단가 미확보", "분양단가: 실거래·지역시세 모두 실패 — 미산출(무목업)"

    # ★HIGH-1: 지역 시세표는 실거래가 아니다. 전국 기본값뿐 아니라 시군구/시도 매칭도
    #   모두 '분양단가 실거래 미확보 — 지역 시세표 추정'을 degraded에 남기고, source에도
    #   '(추정·비실거래)'를 명시해 초록(실거래) 배지로 오표기되지 않게 한다.
    note = "분양단가: 실거래 미확보 — 지역 시세표 추정(참고용, 실제 시세로 재산정 필요)"
    if basis_key == "national_default":
        note = "분양단가: 실거래·지역시세 미매칭 — 전국 기본값 추정 폴백(참고용, 실제 시세로 재산정 필요)"
    return (
        int(price),
        f"지역 시세 테이블({basis_key}·추정·비실거래)",
        "지역×유형 시장표준 시세(원/평, 공급면적) — 주변 실거래 미확보 시 추정 폴백",
        note,
    )




def _num(value: Any) -> float | None:
    """숫자 캐스팅(불리언·비수치는 None) — overrides 방어용."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _null_block(kind: str) -> dict[str, Any]:
    """미확보 축의 표준 null 블록(키는 고정 — 프론트가 안정적으로 소비)."""
    if kind == "land":
        return {"total_won": None, "per_sqm_won": None, "basis": None, "evidence": None, "source": None}
    if kind == "construction":
        return {"total_won": None, "unit_per_sqm_won": None, "basis": None, "source": None}
    if kind == "revenue":
        return {"total_won": None, "sale_price_per_pyeong": None,
                "saleable_area_pyeong": None, "basis": None, "source": None}
    if kind == "charges":
        return {"total_won": None, "construction_stage_won": None, "sale_stage_won": None,
                "buyer_borne_total_won": None, "items": None, "basis": None, "source": None}
    return {}


async def build_rough_scenario(
    *,
    address: str,
    parcels: list[dict[str, Any]] | None = None,
    project_id: str | None = None,
    dev_type: str | None = None,
    region: str = "",  # ★기본값 "서울" 금지 — 지방 부지 과대평가 회피(주소 시도추론에 위임, auto_recommend_top3와 동일)
    equity_won: int | None = None,
    overrides: dict[str, Any] | None = None,
    db: Any = None,
    site_id: Any = None,
) -> dict[str, Any]:
    """주소(+다필지) → 개략 사업성 수지 + 20% 마진 + 월별 DCF 조립.

    Args:
        address: 대표 주소(다필지면 개발 대표필지 주소).
        parcels: 다필지 목록(면적·용도지역 보유). 있으면 면적가중 통합, 없으면 단일 경로.
        project_id: 프로젝트 식별자(로깅·연동용, 계산에는 미사용).
        dev_type: 개발유형 코드(M01~M15). 미지정 시 Top1 자동 추천.
        region: 시도명(분양가 테이블 키). 주소 시군구가 매칭되면 무시됨.
        equity_won: 자기자본(원). None이면 100억 기본.
        overrides: 2차 사용자 수정값(land_cost_won·construction_unit_won·
            sale_price_per_pyeong·construction_months·margin_rate_pct·discount_rate_pct 등).
        db, site_id: (선택) sales site 연결 시 주변 실거래(MOLIT) 분양단가 사용.

    Returns:
        고정 키 계약 dict(프론트 소비) — inputs/land_cost/construction_cost/revenue/
        margin/summary/cashflow/overrides_applied/degraded_notes.
    """
    overrides = overrides or {}
    degraded: list[str] = []          # 미확보·강등 사유(무목업 정직 고지)
    applied: list[str] = []           # 실제 반영된 override 키 목록

    equity = int(equity_won) if equity_won is not None else _DEFAULT_EQUITY_WON
    margin_rate_pct = _num(overrides.get("margin_rate_pct"))
    if margin_rate_pct is None:
        margin_rate_pct = _DEFAULT_MARGIN_RATE_PCT
    else:
        applied.append("margin_rate_pct")
    discount_rate = _num(overrides.get("discount_rate_pct"))
    if discount_rate is None:
        discount_rate = _DEFAULT_DISCOUNT_RATE
    else:
        discount_rate = discount_rate / 100.0
        applied.append("discount_rate_pct")

    # ── 1) 다필지 통합 컨텍스트(면적가중) — 없으면 None(단일/추천 경로) ──
    integrated: dict[str, Any] | None = None
    try:
        integrated = await build_integrated_context(parcels)
    except Exception as e:  # noqa: BLE001 — 통합집계 실패는 단일 경로로 폴백(무중단)
        logger.warning("통합 컨텍스트 산출 실패 — 단일 경로 폴백: %s", str(e)[:120])

    # ── 2) 개발방향 추천(zone·면적·실효FAR·공시지가·입력빌더 확보) ──
    seed_area = float(integrated["total_area_sqm"]) if (integrated and integrated.get("total_area_sqm")) else None
    try:
        rec_result = await _auto_recommend(
            address=address, land_area_sqm=seed_area, region=region,
            equity_won=equity, parcels=parcels,
        )
    except Exception as e:  # noqa: BLE001 — 추천 실패는 전체 개략수지 산출 불가(정직 degrade)
        logger.warning("개발방향 추천 실패: %s", str(e)[:160])
        return _degraded_result(
            address, integrated, parcels,
            [f"개발방향 추천 실패로 개략수지를 산출할 수 없습니다: {str(e)[:120]}"],
        )

    recs = rec_result.get("recommendations") or []
    all_results = rec_result.get("all_results") or []

    # 통합값 우선(SSOT), 없으면 추천이 산출한 값 사용.
    # ★A-2(배선 P1 — usable 면적 전파): GFA/개발규모는 usable(land_area_effective_sqm — 도로·구거·
    #   하천 지목+BLOCKED 게이트 제외, build_integrated_context가 이미 산출) 채택, 토지비 산정
    #   (desk_appraisal/land_cost 경로)은 gross(total_area_sqm) 유지 — comprehensive_analysis_
    #   service의 F2/P0-2(c) 이원화 원칙과 동일 SSOT(제외 필지도 실제 매입 대상이므로 축소 금지).
    #   산식복제 아님 — build_integrated_context 출력을 채택만 한다.
    land_area = None
    land_area_gross = None
    if integrated and float(integrated.get("total_area_sqm") or 0) > 0:
        land_area_gross = float(integrated["total_area_sqm"])
        _eff_area = integrated.get("land_area_effective_sqm")
        land_area = float(_eff_area) if (_eff_area is not None and float(_eff_area) > 0) else land_area_gross
    elif rec_result.get("land_area_sqm"):
        land_area = float(rec_result["land_area_sqm"])
        land_area_gross = land_area
    # 개발규모/토지비 면적 기준 병기(additive) — usable=0(전 필지 제외) 등 결측 시 gross로 정직 폴백.
    land_area_basis = (
        {"gfa_sqm_basis": "usable", "land_cost_basis": "gross",
         "gross_sqm": land_area_gross, "usable_sqm": land_area}
        if land_area is not None else None
    )
    zone_type = None
    if integrated and integrated.get("dominant_zone") and integrated["dominant_zone"] != "mixed_review_required":
        zone_type = integrated["dominant_zone"]
    else:
        zone_type = rec_result.get("zone_type")
    effective_far = None
    if integrated and integrated.get("blended_far_eff_pct") is not None:
        effective_far = float(integrated["blended_far_eff_pct"])
    elif rec_result.get("effective_far_pct") is not None:
        effective_far = float(rec_result["effective_far_pct"])
    parcel_count = None
    if integrated and integrated.get("parcel_count"):
        parcel_count = int(integrated["parcel_count"])
    else:
        parcel_count = int(rec_result.get("parcel_count") or (len(parcels) if parcels else 1))

    # ── ★A-3/G8 법정초과 경량 가드 확산 — comprehensive analyze()의 P0-3 패턴을 공용
    #   헬퍼(hotpath_guard)로 이 오케스트레이터의 effective_far 사용부에도 적용(additive).
    #   BCR은 이 경로에서 미사용(FAR→GFA→ROI만 소비, footprint 산정 없음)이라 far_pct만 검증한다.
    #   regulation_payload 미보유(이 계층엔 조례 원본 미노출) — 근거 불명확 시 정직하게 경고
    #   대상으로 다룬다(무날조: 몰래 안전하다고 가정하지 않음).
    #   ★QA MEDIUM 수정: effective_far는 다필지 통합 시 면적가중 블렌드(blended_far_eff_pct)다.
    #   zone_type(dominant 단일 zone)의 단일 법정상한과 비교하면 정당한 혼합용도 블렌드도
    #   오탐(false "high")한다 — legal_far_pct override로 비교 기준을 같은 면적가중 법정
    #   블렌드(blended_far_legal_pct)로 맞춘다. integrated 부재(단일필지/추천경로)면 override
    #   미전달로 기존 zone_type 단일 법정상한 비교 그대로(무회귀).
    from app.services.verification.hotpath_guard import apply_legal_hotpath_guard

    integrity_warnings = apply_legal_hotpath_guard(
        {}, zone_type=zone_type, bcr_pct=None, far_pct=effective_far,
        legal_far_pct=(integrated.get("blended_far_legal_pct") if integrated else None),
    )

    # 특이부지 BLOCK 또는 허용유형 없음 → 후보 미생성(정직 고지, 가짜 수치 금지).
    if not recs:
        note = (
            rec_result.get("honest_disclosure")
            or rec_result.get("error")
            or "개발 가능한 사업모델이 없어 개략수지를 산출하지 않습니다(무목업)."
        )
        out = _degraded_result(address, integrated, parcels, [note])
        out["inputs"].update({
            "land_area_sqm": land_area, "zone_type": zone_type,
            "effective_far_pct": effective_far, "parcel_count": parcel_count,
            "land_area_basis": land_area_basis,
        })
        out["integrity_warnings"] = integrity_warnings
        if rec_result.get("special_parcel"):
            out["special_parcel"] = rec_result["special_parcel"]
        return out

    # 개발유형 선택 — 지정되면 all_results에서 매칭, 없으면 Top1(recommendations[0]).
    chosen = None
    if dev_type:
        chosen = next((r for r in all_results if r.get("development_type") == dev_type), None)
        if chosen is None:
            degraded.append(f"지정 개발유형 '{dev_type}'은 이 부지 인허가 가능목록에 없어 Top1로 대체했습니다.")
    if chosen is None:
        chosen = recs[0]
    dev_type_final = chosen.get("development_type")
    input_used = chosen.get("input_used")   # ModuleInput(dataclass) — 엔진 비율 추출·폴백 공시지가원
    official_price = float(getattr(input_used, "official_price_per_sqm", 0) or 0) if input_used is not None else 0.0
    land_price_reliable = bool(rec_result.get("land_price_reliable"))
    if not rec_result.get("area_reliable", True):
        degraded.append(rec_result.get("area_disclosure") or "부지면적 미확보 — 가정치 기준(참고용).")
    # ★P3(침묵 폴백 정직화): 용적률 250% 가정치 폴백도 동일 관례로 정직 강등(침묵 전파 금지).
    if not rec_result.get("far_reliable", True):
        degraded.append(rec_result.get("far_disclosure") or "용적률 상한 미확보 — 250% 가정치 기준(참고용).")

    # ── GFA·분양가능면적(전용률/분양률 반영) ──
    gfa_sqm = None
    saleable_pyeong = None
    if land_area and effective_far:
        gfa_sqm = round(land_area * effective_far / 100.0, 1)
        saleable_pyeong = round(gfa_sqm * _GFA_TO_SALEABLE_RATIO / _PYEONG_SQM, 1)
    else:
        degraded.append("면적 또는 실효용적률 미확보 — GFA/공사비/분양수입 산출 불가.")

    # 세대수 가정(리스크시뮬 base 재계산·표시용): GFA ÷ 유형 표준 전용면적(unit_standards SSOT).
    # /baseline 라우트와 동일 관례 — 프론트가 산식을 복제하지 않고 이 값을 그대로 소비한다.
    total_households_assumed: int | None = None
    if gfa_sqm:
        try:
            _avg_unit_area = _service._get_type_avg_unit_area(dev_type_final)
            if _avg_unit_area > 0:
                total_households_assumed = max(1, int(gfa_sqm / _avg_unit_area))
        except Exception:  # noqa: BLE001 — 가정 실패는 정직 null
            total_households_assumed = None

    # ── 3+5) 토지비·분양단가 — 상호 비의존 외부호출을 병렬로(LOW-7) ──
    # 토지비(탁상감정/공시지가)와 분양단가(주변 실거래/지역시세)는 서로 독립적인 외부호출이라
    # 순차로 기다릴 이유가 없다. 각각 자기 주소 지오코딩으로 자립하므로 asyncio.gather로 동시에
    # 실행해 대기시간을 줄인다. override(2차 수정) 축은 네트워크 없이 즉시 처리한다.
    ov_land = _num(overrides.get("land_cost_won"))
    ov_price = _num(overrides.get("sale_price_per_pyeong"))
    if ov_land is not None:
        applied.append("land_cost_won")
    if ov_price is not None:
        applied.append("sale_price_per_pyeong")

    async def _land_leg() -> tuple[int | None, dict[str, Any], list[str]]:
        """토지비 축 — override면 즉시, 아니면 탁상감정/공시지가(외부호출). notes를 함께 반환.

        ★A-2: 토지비는 gross(land_area_gross) 기준 — usable 축소로 제외된 필지(도로·GB 등)도
        실제로는 매입 대상이라 gross로 산정해야 취득원가를 축소 왜곡하지 않는다(무날조 방향).
        """
        if ov_land is not None:
            lt = int(ov_land)
            return lt, {
                "total_won": lt,
                "per_sqm_won": int(lt / land_area_gross) if land_area_gross else None,
                "basis": "사용자 지정 토지비(2차 수정)",
                "evidence": None, "source": "user_override",
            }, []
        if land_area_gross:
            return await _resolve_land_cost(
                address=address, land_area=land_area_gross, official_price=official_price,
                land_price_reliable=land_price_reliable,
            )
        return None, _null_block("land"), ["토지면적 미확보 — 토지비 산출 불가."]

    async def _sale_leg() -> tuple[int | None, str, str, str | None]:
        """분양단가 축 — override면 즉시, 아니면 주변 실거래(MOLIT)→지역시세(외부호출)."""
        if ov_price is not None:
            return int(ov_price), "user_override", "사용자 지정 분양단가(2차 수정, 원/평·공급면적)", None
        return await _resolve_sale_price_per_pyeong(
            db=db, site_id=site_id, dev_type=dev_type_final, region=region, address=address,
        )

    land_result, sale_result = await asyncio.gather(_land_leg(), _sale_leg())
    land_total, land_block, land_notes = land_result
    degraded.extend(land_notes)
    price_pp, price_source, price_basis, price_note = sale_result
    if price_note:
        degraded.append(price_note)

    # ── 4) 공사비(국토부 기본형건축비 SSOT) ──
    constr_block = _null_block("construction")
    constr_total: int | None = None
    if gfa_sqm:
        building_type = _service._get_building_type(dev_type_final)
        ov_unit = _num(overrides.get("construction_unit_won"))
        try:
            if ov_unit is not None:
                cc = construction_cost_engine.calculate_total_construction_cost(
                    total_gfa_sqm=gfa_sqm, building_type=building_type, unit_cost_per_sqm=int(ov_unit),
                )
                applied.append("construction_unit_won")
                c_source, c_basis = "user_override", "사용자 지정 공사비 단가(2차 수정) + 간접비 15%"
            else:
                cc = construction_cost_engine.calculate_total_construction_cost(
                    total_gfa_sqm=gfa_sqm, building_type=building_type,
                )
                c_source = "construction_cost_engine(국토부 SSOT)"
                c_basis = "국토부 기본형건축비(unit_price_repository SSOT) 직접공사비 + 간접비 15%"
            constr_total = int(cc["total_construction_cost_won"])
            constr_block = {
                "total_won": constr_total,
                "unit_per_sqm_won": int(cc["direct"]["unit_cost_per_sqm"]),
                "basis": c_basis, "source": c_source,
            }
        except Exception as e:  # noqa: BLE001 — 공사비 산출 실패는 정직 null
            logger.warning("공사비 산출 실패: %s", str(e)[:120])
            degraded.append(f"공사비 산출 실패: {str(e)[:100]}")

    # ── 5) 분양수입(위에서 병렬 확보한 분양단가 × 분양가능면적) ──
    revenue_block = _null_block("revenue")
    revenue_total: int | None = None
    if price_pp and saleable_pyeong:
        revenue_total = int(saleable_pyeong * price_pp)
        revenue_block = {
            "total_won": revenue_total,
            "sale_price_per_pyeong": price_pp,
            "saleable_area_pyeong": saleable_pyeong,
            "basis": f"{price_basis} × 분양가능면적 {saleable_pyeong:,.0f}평(=GFA×{_GFA_TO_SALEABLE_RATIO})",
            "source": price_source,
        }
    else:
        degraded.append("분양수입 미확보(분양단가 또는 분양가능면적 결측).")

    # ── 6) 총사업비(토지+공사+금융+제경비) + 20% 마진 ──
    project_months = _num(overrides.get("project_months_total")) or _service._get_type_project_months(dev_type_final)
    project_months = int(project_months)
    margin_block: dict[str, Any] = {
        "developer_profit_won": None, "rate_pct": margin_rate_pct, "target_revenue_won": None,
    }
    summary: dict[str, Any] = {
        "total_cost_won": None, "total_revenue_won": revenue_total, "net_profit_won": None,
        "roi_pct": None, "npv_won": None, "irr_pct": None, "payback_month": None, "grade": None,
    }
    core_ready = land_total is not None and constr_total is not None and revenue_total is not None
    finance_total: int | None = None
    other_total: int | None = None
    if land_total is not None and constr_total is not None:
        fin_ratio, oth_ratio, ratio_note = _engine_cost_ratios(input_used)
        if ratio_note:
            degraded.append(ratio_note)
        base_sum = land_total + constr_total
        finance_total = round(base_sum * fin_ratio)
        other_total = round(base_sum * oth_ratio)

    # ── 6b) 부담금(B공사+C분양 단계, 시행사 부담) — ★상시-0 봉합 ──
    # 종전에는 total_tax_cost_won=0으로 학교용지·광역교통·상하수도·HUG 보증수수료 등
    # B/C단계 부담금이 총사업비에서 통째로 누락됐다(토지비에 계상되는 건 A취득단계뿐).
    # A단계는 토지비(include_taxes_and_fees=True)에 기계상돼 제외(이중계상 방지),
    # D(양도)단계는 사업비 성격이 아니라 제외 — 시행사 부담 B+C만 계상한다.
    charges_total: int | None = None
    charges_block: dict[str, Any] = _null_block("charges")
    charges_result: dict[str, Any] | None = None
    if core_ready:
        try:
            charges_result = compute_developer_stage_charges(
                sido_name=str(getattr(input_used, "sido_name", "") or region or ""),
                sigungu_name=str(getattr(input_used, "sigungu_name", "") or ""),
                total_households=total_households_assumed or 0,
                total_sale_amount_won=revenue_total,
                total_gfa_sqm=float(gfa_sqm or 0),
                building_type=_service._get_building_type(dev_type_final),
                # ★C01 부가세 면세기준(국민주택규모)은 '전용 85㎡' — 공급면적(avg_area_pyeong)을
                #   넘기면 전용 61~85㎡ 최다 구간이 과세로 뒤집혀 분양수입의 ~2.7%가 날조 과세된다
                #   (리뷰 P2-2). 개발유형 표준 전용면적(unit_standards SSOT)을 전달한다.
                avg_area_sqm=_service._get_type_avg_unit_area(dev_type_final) or 85.0,
                in_infra_charge_zone=parse_bool_flag(overrides.get("in_infra_charge_zone")),
            )
            charges_total = int(charges_result["total_won"])
            _compact = [
                {"code": it.get("code"), "name": it.get("name"),
                 "amount_won": it.get("amount_won"), "borne_by": it.get("borne_by", "developer")}
                for stage in (charges_result["construction"], charges_result["sale"])
                for it in (stage.get("items") or [])
            ]
            charges_block = {
                "total_won": charges_total,
                "construction_stage_won": int(charges_result["construction"]["total_won"]),
                "sale_stage_won": int(charges_result["sale"]["total_won"]),
                "buyer_borne_total_won": int(charges_result["sale"].get("buyer_borne_total_won") or 0),
                "items": _compact,
                "basis": "B(공사)+C(분양) 단계 시행사 부담 합계 — 취득단계 세금은 토지비에 기계상(이중계상 방지), 수분양자 부담분 제외",
                "source": "utility_stage_engine + sale_stage_engine(통합 세금엔진)",
            }
            degraded.extend(charges_result["unavailable_notes"])
        except Exception as e:  # noqa: BLE001 — 부담금 산출 실패는 정직 강등(총사업비 미반영 고지)
            logger.warning("부담금(B/C단계) 산출 실패: %s", str(e)[:120])
            degraded.append(f"부담금(B/C단계) 산출 실패 — 총사업비에 미반영: {str(e)[:100]}")
            # 부분 성공 잔재 일괄 초기화 — 합계·블록·DCF 주입이 항상 같은 상태를 보게 한다.
            charges_total = None
            charges_block = _null_block("charges")
            charges_result = None

    if core_ready:
        agg = aggregate_feasibility(
            total_revenue_won=revenue_total,
            total_land_cost_won=land_total,
            total_construction_cost_won=constr_total,
            total_finance_cost_won=finance_total or 0,
            total_other_cost_won=other_total or 0,
            # ★6b: B+C 시행사 부담금 계상(취득세는 토지비에 기계상 — A단계만 제외)
            total_tax_cost_won=charges_total or 0,
            equity_won=equity,
            discount_rate=discount_rate,
            project_months=project_months,
        )
        total_cost = int(agg["total_cost_won"])
        developer_profit = int(round(total_cost * margin_rate_pct / 100.0))
        margin_block = {
            "developer_profit_won": developer_profit,
            "rate_pct": margin_rate_pct,
            # 목표매출(역산) = 총사업비 × (1 + 마진율) — 마진 확보에 필요한 분양수입.
            "target_revenue_won": int(round(total_cost * (1 + margin_rate_pct / 100.0))),
        }
        summary.update({
            "total_cost_won": total_cost,
            "net_profit_won": int(agg["net_profit_won"]),
            "roi_pct": agg["roi_pct"],
            "grade": agg["grade"],
        })
    else:
        degraded.append("핵심 축(토지비·공사비·분양수입) 중 결측이 있어 총사업비·마진을 산출하지 않습니다(무목업).")

    # ── 7) 총사업비 구성(금융·제경비·부담금 노출 — 근거 투명화) ──
    cost_breakdown = {
        "land_won": land_total, "construction_won": constr_total,
        "finance_won": finance_total, "other_won": other_total,
        "charges_won": charges_total,
    }

    # ── 8) 월별 DCF(위 산출을 시드) — npv·irr·payback·peak ──
    cashflow_block: dict[str, Any] | None = None
    if core_ready:
        construction_months = _num(overrides.get("construction_months"))
        if construction_months is not None:
            construction_months = max(1, int(construction_months))  # ★MEDIUM-6: 하한 가드(0·음수 방지)
            applied.append("construction_months")
        else:
            construction_months = max(6, project_months - 6)   # 설계 3 + 정산 3 제외 근사
        sale_start = _num(overrides.get("sale_start_month"))
        sale_start = int(sale_start) if sale_start is not None else min(6, max(0, construction_months - 1))
        sale_start = max(0, min(sale_start, construction_months - 1))
        sale_duration = _num(overrides.get("sale_duration_months"))
        sale_duration = int(sale_duration) if sale_duration is not None else 6
        # ★6b: 부담금(B/C단계)을 DCF에도 시점 주입 — 총사업비(summary)와 현금흐름(NPV·IRR)이
        #   같은 비용 기저를 쓰도록 정합(B→착공월, C→분양수입 비례; A/D는 0 — 위 6b와 동일 계약).
        tax_schedule: dict[str, Any] | None = None
        if charges_result is not None and charges_total:
            tax_schedule = {
                "acquisition_won": 0,
                "construction_won": int(charges_result["construction"]["total_won"]),
                "sale_won": int(charges_result["sale"]["total_won"]),
                "disposal_settlement_won": 0,
                "d06_annual_won": 0,
                "d06_years": 0,
            }
        # ★W3(100% 캠페인): DCF 조립을 공용 SSOT(dcf_assembly.assemble_monthly_dcf)로 이관 —
        #   상세수지(경로A /calculate)와 동일 규칙 소비(수치 무회귀·NPV 무차입 기저·IRR 동일 선택).
        dcf = assemble_monthly_dcf(
            land_cost_won=float(land_total),
            construction_cost_won=float(constr_total),
            revenue_won=float(revenue_total),
            project_months=project_months,
            equity_won=float(equity),
            discount_rate=discount_rate,
            total_cost_won=summary.get("total_cost_won"),
            # ★R1-HIGH-2 동반 교정: 제경비(other_total)를 DCF 유출에 주입 — 종전엔 rough도
            #   동일 누락으로 NPV·IRR이 과대였다(의도된 정확화 — 총사업비와 동일 비용 기저).
            soft_cost_won=float(other_total) if other_total else None,
            tax_schedule=tax_schedule,
            construction_months=construction_months,
            sale_start_month=sale_start,
            sale_duration_months=max(1, sale_duration),
        )
        if dcf is not None:
            summary.update({
                "npv_won": dcf["npv_won"],
                "irr_pct": dcf["irr_pct"],
                "payback_month": dcf["payback_month"],
            })
            cashflow_block = {
                "monthly_rows": dcf["rows"],
                "summary": {
                    **dcf["cf_summary"],
                    "npv_won": dcf["npv_won"],
                    "payback_month": dcf["payback_month"],
                    "discount_rate_annual_pct": round(discount_rate * 100, 2),
                },
            }
        else:
            degraded.append("월별 DCF 생성 실패 — NPV·IRR·회수기간 미산출(정직 null).")

    # ★TENTATIVE(선행절차 전제 잠정치) 특이부지 정직고지 — has-recs 경로에서도 소실 금지.
    #   맹지·도로/학교 PRECONDITION 등은 recs가 생성돼 정상 경로를 타지만, ROI·등급·마진·NPV가
    #   확정치가 아니라 '선행절차 전제 잠정치'임을 반드시 노출한다(특이부지 할루시네이션 가드 재소실 방지).
    scenario_status = rec_result.get("scenario_status", "actual")
    if scenario_status == "tentative":
        _tnote = (
            (chosen.get("tentative_reason") if isinstance(chosen, dict) else None)
            or rec_result.get("honest_disclosure")
            or "선행절차(접도 확보 등)를 전제한 잠정치 — ROI·등급·수지는 확정치가 아닙니다."
        )
        degraded.insert(0, f"[잠정·선행절차 전제] {_tnote}")

    return {
        "address": address,
        "project_id": project_id,
        "scenario_status": scenario_status,
        "special_parcel": rec_result.get("special_parcel"),
        "inputs": {
            "land_area_sqm": land_area,
            "zone_type": zone_type,
            "effective_far_pct": effective_far,
            "dev_type": dev_type_final,
            "dev_type_name": chosen.get("type_name"),
            "gfa_sqm": gfa_sqm,
            "saleable_area_pyeong": saleable_pyeong,
            "parcel_count": parcel_count,
            "project_months": project_months,
            "total_households": total_households_assumed,
            "land_area_basis": land_area_basis,
        },
        "land_cost": land_block,
        "construction_cost": constr_block,
        "revenue": revenue_block,
        "charges": charges_block,
        "cost_breakdown": cost_breakdown,
        "margin": margin_block,
        "summary": summary,
        "cashflow": cashflow_block,
        "overrides_applied": applied,
        "degraded_notes": degraded,
        # ★A-3/G8(additive) — 법정초과 경량 가드 검출 시만 채워짐(빈 배열=검출 없음, 기존 키 불변).
        "integrity_warnings": integrity_warnings,
    }


async def _resolve_land_cost(
    *, address: str, land_area: float, official_price: float,
    land_price_reliable: bool,
) -> tuple[int | None, dict[str, Any], list[str]]:
    """토지비(적정금액) — 1순위 탁상감정(적정가), 폴백 공시지가×배율. 실패 시 (None, null블록, notes).

    notes: 미확보·강등 사유(호출부가 degraded_notes에 합산). 무목업 — 값을 못 구하면 정직 null.
    """
    notes: list[str] = []
    # 1순위: 탁상감정(공시지가기준법+거래사례비교) 적정 단가 → 취득세 등 포함 총토지비.
    try:
        da = await desk_appraisal(address=address, area_sqm=land_area)
    except Exception as e:  # noqa: BLE001 — 탁상감정 실패는 공시지가 폴백으로(무중단)
        logger.warning("탁상감정 실패 — 공시지가 폴백 시도: %s", str(e)[:120])
        da = {"ok": False}

    if isinstance(da, dict) and da.get("ok") and da.get("appraised_price_per_sqm"):
        appraised = float(da["appraised_price_per_sqm"])
        lc = land_cost_engine.calculate_total_land_cost(
            total_area_sqm=land_area, official_price_per_sqm=appraised,
            price_multiplier=1.0, land_category="land", include_taxes_and_fees=True,
        )
        return int(lc["total_land_cost_won"]), {
            "total_won": int(lc["total_land_cost_won"]),
            "per_sqm_won": int(appraised),
            "basis": f"탁상감정 적정단가 {int(appraised):,}원/㎡ × 면적 {land_area:,.0f}㎡ + 취득세 등(land_cost_engine)",
            "evidence": da.get("evidence"),
            "source": da.get("source") or "desk_appraisal(탁상감정)",
        }, notes

    # 폴백: 공시지가(또는 미확보 시 표준 가정단가) × 배율(1.1) → 취득세 등 포함.
    if official_price and official_price > 0:
        lc = land_cost_engine.calculate_total_land_cost(
            total_area_sqm=land_area, official_price_per_sqm=official_price,
            price_multiplier=1.1, land_category="land", include_taxes_and_fees=True,
        )
        total = int(lc["total_land_cost_won"])
        per_sqm = int(official_price * 1.1)
        if land_price_reliable:
            # 실제 공시지가 확보 — '공시지가'라 정직하게 부를 수 있다.
            notes.append("토지비: 탁상감정 미확보 — 공시지가×1.1 배율 폴백(참고용)")
            block = {
                "total_won": total, "per_sqm_won": per_sqm,
                "basis": f"공시지가 {int(official_price):,}원/㎡ × 배율 1.1 × 면적 {land_area:,.0f}㎡ + 취득세 등",
                "evidence": None, "source": "공시지가×배율(폴백)",
            }
        else:
            # ★HIGH-2(무목업): 공시지가 전혀 미확보. 엔진 묵시 표준단가를 '공시지가'라 부르면 거짓이다.
            #   값(표준 가정단가)은 유지하되 '실지가 아님'을 basis·source·degraded에 정직 명시한다.
            notes.append("토지비: 공시지가 미확보 — 표준 가정단가로 산정(실지가 아님)")
            block = {
                "total_won": total, "per_sqm_won": per_sqm,
                "basis": (f"표준 가정단가 {int(official_price):,}원/㎡ × 배율 1.1 × 면적 {land_area:,.0f}㎡ "
                          "+ 취득세 등(공시지가 미확보·실지가 아님)"),
                "evidence": None, "source": "표준 가정단가(공시지가 미확보·실지가 아님)",
            }
        return total, block, notes

    notes.append("토지비 미확보 — 탁상감정·공시지가 모두 실패(무목업 null).")
    return None, _null_block("land"), notes


def _degraded_result(
    address: str, integrated: dict[str, Any] | None,
    parcels: list[dict[str, Any]] | None, notes: list[str],
) -> dict[str, Any]:
    """산출 불가(추천 실패·BLOCK 등) 시의 표준 정직 응답(키 고정, 값 null)."""
    parcel_count = None
    if integrated and integrated.get("parcel_count"):
        parcel_count = int(integrated["parcel_count"])
    elif parcels:
        parcel_count = len(parcels)
    land_area = float(integrated["total_area_sqm"]) if (integrated and integrated.get("total_area_sqm")) else None
    return {
        "address": address,
        "project_id": None,
        "scenario_status": "unavailable",
        "inputs": {
            "land_area_sqm": land_area, "zone_type": None, "effective_far_pct": None,
            "dev_type": None, "dev_type_name": None, "gfa_sqm": None,
            "saleable_area_pyeong": None, "parcel_count": parcel_count, "project_months": None,
            "total_households": None,
        },
        "land_cost": _null_block("land"),
        "construction_cost": _null_block("construction"),
        "revenue": _null_block("revenue"),
        "charges": _null_block("charges"),
        "cost_breakdown": {"land_won": None, "construction_won": None, "finance_won": None,
                           "other_won": None, "charges_won": None},
        "margin": {"developer_profit_won": None, "rate_pct": _DEFAULT_MARGIN_RATE_PCT, "target_revenue_won": None},
        "summary": {
            "total_cost_won": None, "total_revenue_won": None, "net_profit_won": None,
            "roi_pct": None, "npv_won": None, "irr_pct": None, "payback_month": None, "grade": None,
        },
        "cashflow": None,
        "overrides_applied": [],
        "degraded_notes": notes,
        # ★A-3/G8(additive) — 산출 자체가 없어 검증 대상(effective_far)도 없음(빈 배열).
        "integrity_warnings": [],
    }

