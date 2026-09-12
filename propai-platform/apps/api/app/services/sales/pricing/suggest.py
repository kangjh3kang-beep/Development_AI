"""P1-1 적정분양가 추천 — 주변 실거래 앵커 + 교차검증(신뢰루프) 기반.

분양가의 1차 기준은 '동일종목 주변시세(실거래) + 주변 분양가'([[project_fair_price_basis]]).
★사고 교훈(용인 신봉동 과대): 인근 럭셔리 분양가(반경 3km)를 그대로 채택하고 실거래 앵커를
놓치면 2배 이상 과대된다. 따라서 ① MOLIT 실거래(동→시군구)를 앵커로 ② 교차검증
(data_validation/trust)으로 이상치 제외·신뢰도 산출 ③ 공급면적(아파트)/분양면적(상업) 기준
환산 후 신축 프리미엄으로 3안 제시. 신뢰 미달이면 정직 강등(가짜값 금지).
"""
from __future__ import annotations

import statistics
import uuid
from datetime import UTC
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.data_validation.trust import Signal, cross_validate
from apps.api.app.utils.withheld import INSUFFICIENT_COVERAGE, withheld
from apps.api.database.models.sales.site_org import SalesSite
from apps.api.integrations.region_codes import pnu_to_bcode

logger = structlog.get_logger(__name__)

PYEONG_SQM = 3.305785
_REF_EXCLUSIVE_SQM = 84.0          # 84타입 전용면적

# ★「최근 건축년도」의 경계(년). 신축 분양가의 비교 대상을 고르는 축이다.
#   실측(남양주 화도읍 · 8개월 469건 · 전용 만원/평):
#       0~5년 3,226 · 6~10년 3,620 · 11~20년 1,997 · 21~30년 1,629 · 31년+ 914
#   ★**10년과 11년 사이에서 크게 꺾인다**(3,620 → 1,997). 그래서 10을 경계로 둔다.
#   ★서울 재건축 기대 지역은 31년+ 이 **반등**하지만(노원·강남 실측), 그것은
#     «신축 분양가의 비교 대상»이 아니므로 이 축과 무관하다.
_RECENT_BUILD_YEARS = 10
_REF_SUPPLY_SQM = 112.4            # 84타입 표준 공급면적(전용률 ~74.7%)
_REF_SUPPLY_PYEONG = round(_REF_SUPPLY_SQM / PYEONG_SQM, 1)  # ≈ 34.0평
_JEONYULRYUL = 0.747               # 전용률(전용/공급) 표준 가정 — 전용 평당가→공급 평당가 환산

# 아파트=공급면적, 오피스텔/상가(상업)=분양(계약)면적 기준.
_CONTRACT_BASIS_TYPES = {"OFFICETEL", "RETAIL", "KNOWLEDGE_CENTER", "HOTEL"}
_PROP_TYPE = {"APT": "apt", "OFFICETEL": "officetel", "RETAIL": "commercial"}

# 신축 분양 프리미엄(주변 실거래 시세 대비). 보수=시세근접·기준·공격.
_PREMIUM = {"conservative": 1.05, "base": 1.15, "aggressive": 1.25}
_TIER_LABEL = {"conservative": "보수적", "base": "기준", "aggressive": "공격적"}

# 평당가(전용, 만원) 현실 sanity 범위 — 전국 아파트 실거래 분포 가드.
_PP_MIN, _PP_MAX = 300.0, 20000.0

# ── 원가 검증(2차 가드) — 시장기반 분양가가 원가를 회수하는지 교차확인 ──
# [[project_fair_price_basis]]: 1차=거래사례비교(아래 tiers), 2차=지불여력/원가회수 검증.
# 분양가는 시장에서 결정되나, 원가(공사비+간접) 대비 마진 여력을 함께 보여 비현실 분양가를 가드한다.
_SALE_EFFICIENCY = 0.70          # 공급면적/연면적(GFA) 표준비 — 공사비(GFA당)를 공급평당으로 환산
_MAX_VIABLE_COST_RATIO = 0.65    # 공사비가 분양가의 65% 초과 시 토지비·금융비·마진 여력 부족 경고
# dev_type(sales) → construction_cost_engine building_type 매핑.
_BUILDING_TYPE = {"APT": "apartment", "OFFICETEL": "officetel", "RETAIL": "commercial",
                  "KNOWLEDGE_CENTER": "office", "HOTEL": "commercial"}


def _cost_validation(
    dev_type: str | None, tiers: list[dict[str, Any]],
    construction_cost_per_gfa_won: int | None,
) -> dict[str, Any] | None:
    """시장기반 분양가 tiers가 원가(공사비+간접)를 회수하는지 검증한다(2차 가드).

    공사비 단가(GFA당)를 공급평당 원가로 환산해 tier별 원가비율·마진을 부착하고,
    보수안이 원가기반 최저선 미만이면 경고한다. 정밀공사비(per_gfa) 전달 시 그것을,
    아니면 표준단가(construction_cost_engine SSOT)를 쓴다. import/계산 실패 시 None(graceful).
    """
    try:
        from app.services.feasibility.construction_cost_engine import (
            DEFAULT_INDIRECT_RATIOS,
            _resolve_direct_unit_cost,
        )
        building_type = _BUILDING_TYPE.get((dev_type or "").upper(), "apartment")
        direct_per_gfa = construction_cost_per_gfa_won or _resolve_direct_unit_cost(building_type)
        if not direct_per_gfa or direct_per_gfa <= 0:
            return None
        total_per_gfa = direct_per_gfa * (1 + sum(DEFAULT_INDIRECT_RATIOS.values()))  # +간접 15%
        cost_per_supply_pyeong_10k = total_per_gfa / _SALE_EFFICIENCY / 10000.0 * PYEONG_SQM
        for t in tiers:
            price = float(t.get("per_pyeong_10k") or 0)
            if price <= 0:
                continue
            ratio = cost_per_supply_pyeong_10k / price
            t["construction_cost_ratio_pct"] = round(ratio * 100, 1)
            t["margin_over_construction_pct"] = round((1 - ratio) * 100, 1)
            t["cost_viable"] = ratio <= _MAX_VIABLE_COST_RATIO
        floor = round(cost_per_supply_pyeong_10k / _MAX_VIABLE_COST_RATIO)
        cons_price = float(tiers[0].get("per_pyeong_10k") or 0) if tiers else 0
        viable = cons_price >= floor
        return {
            "cost_basis": "정밀공사비" if construction_cost_per_gfa_won else "표준단가(SSOT)",
            "construction_cost_per_gfa_won": int(direct_per_gfa),
            "construction_cost_per_supply_pyeong_10k": round(cost_per_supply_pyeong_10k),
            "sale_efficiency": _SALE_EFFICIENCY,
            "max_viable_cost_ratio": _MAX_VIABLE_COST_RATIO,
            "viable_price_floor_per_pyeong_10k": floor,
            "conservative_viable": viable,
            "warning": None if viable else (
                f"보수안 분양가({round(cons_price)}만/평)가 원가기반 최저선({floor}만/평) 미만 — "
                "토지비·금융비·마진 회수가 어려울 수 있습니다(시장가 < 원가 신호)."
            ),
        }
    except Exception:  # noqa: BLE001 — 원가엔진 미가용 시 검증 생략(시장기반 분양가는 그대로 유효)
        return None


# 분양가 추천에 부착할 분양 관련 법령 근거 키(레지스트리 단일출처).
# 건축물분양법 분양신고(제5조)·분양보증/신탁(제6조), 분양가상한제(주택법 제57조).
_SALES_LEGAL_REF_KEYS = ["building_sales_filing", "building_sales_guarantee", "housing_price_cap"]


def _sales_legal_refs() -> list[dict]:
    """분양가 추천 결과에 부착할 분양 관련 법령 근거(verified 딥링크) — 가산 필드.

    레지스트리 미가용 시 빈 리스트(graceful, 기존 응답 무손상).
    """
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs(_SALES_LEGAL_REF_KEYS)
    except Exception:  # noqa: BLE001
        return []


def _price_evidence(
    market_pp_supply: float, area_basis_label: str, tiers: list[dict[str, Any]],
    trust: Any,
) -> list[dict[str, Any]]:
    """적정분양가 산출 근거 트레이스(EvidencePanel 소비 구조) — graceful 빈배열.

    주변 실거래(앵커)·신축 프리미엄 3안·분양가상한제 근거를 한 줄씩 트레이스한다.
    법령 근거는 분양가상한제(housing_price_cap) 키만 연결(분양가 산출의 직접 한도 근거).
    """
    try:
        used = ", ".join(getattr(trust, "used", None) or []) or "주변 실거래"
        ev: list[dict[str, Any]] = [{
            "label": "주변 시세(공급환산)",
            "value": f"{round(market_pp_supply):,}만원/평",
            "basis": f"주변 실거래({used}) 교차검증 — {area_basis_label} 기준",
        }]
        for t in tiers or []:
            ev.append({
                "label": f"적정분양가 — {t.get('label', '')}",
                "value": f"{int(t.get('per_pyeong_10k') or 0):,}만원/평",
                "basis": f"주변 시세 × 신축 프리미엄 +{t.get('premium_pct', 0)}%",
                # 분양가상한제 적용지역이면 상한 근거가 됨(레지스트리 단일출처).
                "legal_ref_key": "housing_price_cap",
            })
        return ev
    except Exception:  # noqa: BLE001
        return []


async def _site_location(
    db: AsyncSession, site_id: uuid.UUID,
) -> tuple[str | None, str | None, str | None]:
    """site → project 주소·첫 PNU(법정동코드 유도)·development_type."""
    # ★★삭제된 현장의 입지를 주지 않는다(2026-09-12 · 리뷰 M3③).
    #   종전 면제 사유는 «인자가 이미 해석된 값» 이었는데 **거짓**이다 — 진입점 중
    #   `POST /api/v2/feasibility/rough-scenario` 가 `Depends(get_current_user_optional)`
    #   (익명 허용)로 요청 본문의 `site_id` 를 무검증 전달한다. 그 경로는 별건이고,
    #   여기서는 **삭제 여부만** 막는다(`if not site` 가 이미 None 안전).
    site = (await db.execute(select(SalesSite).where(
        SalesSite.id == site_id, SalesSite.deleted_at.is_(None)))).scalar_one_or_none()
    if not site:
        return None, None, None
    row = (await db.execute(
        text("select address, pnu_codes from projects where id = :pid"),
        {"pid": str(site.project_id)},
    )).mappings().first()
    dev = getattr(site, "development_type", None)
    if not row:
        return None, None, dev
    address = row.get("address")
    pnu = None
    pc = row.get("pnu_codes")
    if isinstance(pc, (list, tuple)) and pc:
        pnu = str(pc[0])
    elif isinstance(pc, dict) and pc:
        pnu = str(next(iter(pc.values())))
    elif isinstance(pc, str) and pc:
        pnu = pc
    return address, pnu, dev


def _extract_dong(address: str | None) -> str | None:
    """주소에서 읍/면/동/리 토큰 추출(예: '신봉동')."""
    import re
    if not address:
        return None
    m = re.findall(r"([가-힣]{1,6}(?:동|읍|면|리))", address)
    return m[-1] if m else None


def _quantile(vals: list[float], q: float) -> float:
    """표본이 작아도 죽지 않는 분위수.

    ★`statistics.quantiles` 는 **표본 2건 미만에서 StatisticsError** 를 낸다.
      분양권 전매는 표본이 원래 작다(실측: 빌리브센트하이 12개월 **7건**) — 여기서
      예외가 나면 상위 대역 축이 통째로 사라지는데, 그 실패는 **조용하다**.
    """
    if not vals:
        raise ValueError("빈 표본에 분위수를 물었다 — 호출부가 먼저 걸러야 한다")
    xs = sorted(vals)
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


async def _trade_per_pyeong(
    sigungu5: str, dong: str | None, prop_type: str, *, collect_cases: bool = False,
) -> dict[str, Any]:
    """MOLIT 실거래 → 전용 평당가(만원). 동/시군구 각각의 중앙값·표본수.

    collect_cases=True(opt-in — 기본 False는 반환 shape 완전 불변, 무회귀): 같은 수집 루프에서
    개별 거래 사례를 선정/제외 사유와 함께 "cases" 키에 추가로 담는다(market_precision W3-8
    ComparableSet 빌더 전용 — 새 MOLIT 호출을 추가하지 않고 이 함수의 기존 수집을 재사용).
    """
    from datetime import datetime

    from apps.api.integrations.molit_client import MolitClient
    m = MolitClient()
    # 최근 8개월(YYYYMM) 조회 — 표본 확보. MOLIT는 신고지연이 있어 최신월은 적을 수 있어 넉넉히.
    now = datetime.now(UTC)
    yms = []
    y, mo = now.year, now.month
    for _ in range(8):
        yms.append(f"{y:04d}{mo:02d}")
        mo -= 1
        if mo == 0:
            mo = 12; y -= 1
    dong_pp: list[float] = []
    sigu_pp: list[float] = []
    recent_dong_pp: list[float] = []
    recent_sigu_pp: list[float] = []
    _NOW_YEAR = now.year
    cases: list[dict[str, Any]] = []
    direct_n = 0        # 직거래(제외하지 않음 — 근거에 밝히기만 한다)
    cancelled_n = 0     # 계약 해제(제외한다)
    latest_ym_n = 0     # 조회 최신월 건수 — 0이면 「신고 지연으로 최신 시세 미반영」
    for ym in yms:
        try:
            rows = await m.get_transactions(sigungu5, ym, prop_type=prop_type, num_rows=1000)
        except Exception:  # noqa: BLE001
            rows = []
        if ym == yms[0]:
            latest_ym_n = len(rows or [])
        for r in rows or []:
            try:
                amt = float(r.get("price_10k_won") or 0)
                ar = float(r.get("area_m2") or 0)
            except (TypeError, ValueError):
                # ★R1 M-2 봉합: 파싱실패 행도 무음 폐기하지 않는다(수집 N=선정+제외 항등 유지) —
                # 값 자체가 없어 price/area 는 None 으로 남기고 exclude_reason 으로 사유를 명시한다.
                if collect_cases:
                    cases.append({
                        "ym": ym, "dong": r.get("dong"), "jibun": r.get("jibun"),
                        "building_name": r.get("building_name"), "deal_date": r.get("deal_date"),
                        "price_10k_won": None, "area_m2": None, "per_pyeong_10k": None,
                        "matched_dong": False, "included": False,
                        "exclude_reason": "수치 파싱 실패(가격/면적 값 형식 오류)",
                    })
                continue
            if amt <= 0 or ar <= 0:
                if collect_cases:
                    cases.append({
                        "ym": ym, "dong": r.get("dong"), "jibun": r.get("jibun"),
                        "building_name": r.get("building_name"), "deal_date": r.get("deal_date"),
                        "price_10k_won": amt, "area_m2": ar, "per_pyeong_10k": None,
                        "matched_dong": False, "included": False,
                        "exclude_reason": "금액 또는 면적 결측/0",
                    })
                continue
            pp = amt / (ar / PYEONG_SQM)   # 만원/평(전용)
            # ★★2026-09-07 — **소비처 0 결함 봉합.** `molit_client` 는 `is_cancelled`·
            #   `dealing_type` 을 파싱해 **보존만** 하면서 주석에 *"제외·가중은 **소비처
            #   판단**이다"* 라고 적어 뒀는데, **판단하는 소비처가 한 곳도 없었다**
            #   (`git grep is_cancelled` → 파서 외 0건). 계약이 해제된 거래는 **성립하지
            #   않은 가격**이라 시세가 아니다. 같은 파일 실측(3,482건): 해제 68건(1.95%) ·
            #   **해제 건 평균이 정상 대비 +11.5%(고가 편향)**.
            cancelled = bool(r.get("is_cancelled"))
            in_range = (_PP_MIN <= pp <= _PP_MAX) and not cancelled
            matched_dong = bool(dong and dong in str(r.get("dong") or ""))
            # ★직거래(`dealingGbn`)는 **제외하지 않는다.** 라이브 실측(빌리브센트하이 7건)에서
            #   직거래를 빼도 중앙값이 **2,436 → 2,439(+0.1%)** 로 사실상 불변이었다.
            #   *안 재본 편향을 근거로 행을 버리지 않는다* — 대신 **건수를 근거에 밝힌다**.
            if str(r.get("dealing_type") or "").strip() == "직거래":
                direct_n += 1
            if cancelled:
                cancelled_n += 1
            if collect_cases:
                cases.append({
                    "ym": ym, "dong": r.get("dong"), "jibun": r.get("jibun"),
                    "building_name": r.get("building_name"), "deal_date": r.get("deal_date"),
                    "price_10k_won": amt, "area_m2": ar, "per_pyeong_10k": round(pp, 1),
                    "matched_dong": matched_dong, "included": in_range,
                    "dealing_type": r.get("dealing_type"),
                    "is_cancelled": cancelled,
                    # ★사유를 **가른다** — 「해제」와 「범위 밖」이 같은 문구면 원장을 보고
                    #   되짚을 수 없다(§유료 규율 4: 실패는 전용 필드로 자기를 구별한다).
                    "exclude_reason": (
                        None if in_range
                        else "계약 해제 거래(cdealType) — 성립하지 않은 가격이라 시세가 아니다"
                        if cancelled
                        else f"평당가 sanity 범위({_PP_MIN:.0f}~{_PP_MAX:.0f}만원/평) 벗어남"
                    ),
                })
            if not in_range:
                continue
            sigu_pp.append(pp)
            if matched_dong:
                dong_pp.append(pp)
            # ★★**최근 건축년도(신축) 축을 따로 센다**(2026-09-06 · 사용자 결정).
            #   기존 집계는 신축·구축을 **한 통**에 넣는다 — 실측(남양주 화도읍 469건):
            #       전체 중앙 1,391 만원/평(전용) ↔ 신축(≤10년) **1,846** = **+33%**
            #       ★21~30년 구축이 **202건(최다)** 이라 중앙값을 끌어내린다.
            #   **신축 분양가의 비교 대상은 신축**이므로 별도 축으로 낸다.
            #   ★기존 두 키(`dong`·`sigungu`)는 **손대지 않는다** — 무회귀.
            try:
                _by = int(r.get("build_year") or 0)
            except (TypeError, ValueError):
                _by = 0
            if _by > 0 and (_NOW_YEAR - _by) <= _RECENT_BUILD_YEARS:
                recent_sigu_pp.append(pp)
                if matched_dong:
                    recent_dong_pp.append(pp)
    result: dict[str, Any] = {
        "dong": {"median": round(statistics.median(dong_pp)) if dong_pp else None, "n": len(dong_pp)},
        "sigungu": {"median": round(statistics.median(sigu_pp)) if sigu_pp else None, "n": len(sigu_pp)},
        # ★신축(최근 건축년도) 축 — 소비처가 없으면 그냥 안 읽는다(기존 계약 불변).
        "recent_dong": {
            "median": round(statistics.median(recent_dong_pp)) if recent_dong_pp else None,
            "n": len(recent_dong_pp)},
        "recent_sigungu": {
            "median": round(statistics.median(recent_sigu_pp)) if recent_sigu_pp else None,
            "n": len(recent_sigu_pp)},
        "recent_build_years": _RECENT_BUILD_YEARS,
        # ★★2026-09-07 — **중앙값이 「분양 가능 대역」을 가린다.**
        #   라이브 실측(빌리브센트하이 7건, 전용→공급 0.75 환산):
        #       중앙값 1,827만원/평  ↔  **최고 2,032만원/평**  (같은 단지·같은 12개월)
        #   신규 분양은 **시장 평균가가 아니라 상위 대역**을 겨냥한다(신축·고층·최근).
        #   ★그래서 «중앙값을 상위값으로 바꾼다»가 아니라 **둘 다 낸다** — 어느 쪽을 쓸지는
        #     사용자 판단이고, 한 수로 뭉개면 근거가 사라진다.
        #   ★기존 키는 손대지 않는다(무회귀 — 소비처가 없으면 그냥 안 읽는다).
        "dong_upper": {
            "p75": round(_quantile(dong_pp, 0.75)) if dong_pp else None,
            "max": round(max(dong_pp)) if dong_pp else None,
            "n": len(dong_pp)},
        "sigungu_upper": {
            "p75": round(_quantile(sigu_pp, 0.75)) if sigu_pp else None,
            "max": round(max(sigu_pp)) if sigu_pp else None,
            "n": len(sigu_pp)},
        # ★진단 — 「왜 이 값인가」를 되짚을 수 있게. **표시가 아니라 판정 재료**다.
        "diagnostics": {
            "cancelled_excluded_n": cancelled_n,   # 제외했다
            "direct_deal_n": direct_n,             # 제외하지 않았다(근거에 밝힌다)
            "latest_ym": yms[0],
            "latest_ym_rows": latest_ym_n,         # 0이면 신고 지연으로 최신 시세 미반영
            "months_scanned": len(yms),
        },
    }
    if collect_cases:
        result["cases"] = cases
    return result


async def _nearby_presale_reference(sigungu5: str) -> dict[str, Any]:
    """청약홈 주변 분양 — 적정분양가 '참고·교차검증' 출처(★앵커 아님).

    ★용인 신봉동 과대표시 사고 교훈: 주변 분양가를 산정 앵커로 쓰면 럭셔리 분양가에 2배 과대된다.
    따라서 여기서는 청약홈 주변 분양가를 '참고·교차검증'으로만 surface하고(실거래 앵커는 그대로 유지),
    분양가 산정 tiers/앵커 로직은 일절 건드리지 않는다. graceful(실패→available False, 결과 무손상).
    """
    from app.services.land_intelligence.presale_service import _LAWD_TO_AREA, PresaleService

    area = _LAWD_TO_AREA.get((sigungu5 or "")[:2])
    if not area:
        return {"available": False, "note": "청약홈 지역 매핑 불가"}
    try:
        svc = PresaleService()
        listing = await svc.list_announcements(area=area, product="apt", months_back=12, max_items=50)
        if not listing.get("available"):
            return {"available": False, "area": area, "note": listing.get("note") or "청약홈 분양정보 미확보"}
        items = listing.get("items") or []
        samples: list[dict[str, Any]] = []
        prices: list[float] = []
        for it in items[:2]:  # 최근 2건만 분양가 상세 조회(지연 최소).
            try:
                d = await svc.detail(it.get("house_manage_no") or "", it.get("pblanc_no") or "", "apt")
            except Exception:  # noqa: BLE001
                d = {}
            pmin, pmax = d.get("price_min_man"), d.get("price_max_man")
            for p in (pmin, pmax):
                if isinstance(p, (int, float)) and p > 0:
                    prices.append(float(p))
            samples.append({"name": it.get("name"), "status": it.get("status"),
                            "recruit_date": it.get("recruit_date"),
                            "price_min_man": pmin, "price_max_man": pmax})
        return {
            "available": True, "area": area, "count": listing.get("count"),
            "samples": samples,
            "price_range_man": ([round(min(prices)), round(max(prices))] if prices else None),
            "note": "청약홈 주변 분양가는 '참고·교차검증'입니다 — 적정분양가 산정은 주변 실거래 앵커 기준(주변 분양가 과대표시 방지).",
        }
    except Exception:  # noqa: BLE001 — 청약홈 실패는 적정분양가 결과 무손상(참고 누락만).
        return {"available": False, "area": area, "note": "청약홈 조회 실패"}


# ★★청약홈을 **신호로 승격**할 때 쓰는 반경 상한(m). 사용자 결정(2026-09-06).
#   ★종전 참고 경로(`_nearby_presale_reference`)는 **시도 전체**(`_LAWD_TO_AREA[sigungu5[:2]]`)의
#     최근 2건이라 **앵커로 쓸 수 없다** — 실측(남양주 41360 → 「경기」):
#         성남복정2 신혼희망타운 7.98~8.12억 · 시흥 은계 에피트 3.08~4.85억
#     마석 사업지와 **무관한 지역**이고, 그 파일 주석이 적은 **«용인 신봉동 과대표시 사고
#     — 럭셔리 분양가에 2배 과대»** 의 정체가 바로 이것이다.
#   → 신호로 쓸 때는 **반경**(`PresaleService.nearby`)으로 좁히고 **거리를 근거에 싣는다.**
_PRESALE_SIGNAL_RADIUS_M = 10_000
# 반경 안 표본이 이보다 적으면 **신호로 쓰지 않는다**(한두 건이 사업 전체를 정하면 안 된다).
_PRESALE_SIGNAL_MIN_SAMPLES = 3


async def _presale_signal_per_pyeong(address: str) -> dict[str, Any]:
    """청약홈 **반경 내** 분양가 → 공급 평당가(만원/평). 신호로 쓸 수 있는 형태.

    ★참고 경로와 **다른 함수**로 둔다 — 참고는 시도 전체(넓게 보여 주기),
      신호는 반경 안(값을 정하기). **같은 데이터원이라도 쓰임이 다르면 범위가 다르다.**

    Returns:
        {'available', 'per_pyeong_man', 'n', 'radius_m', 'nearest_m', 'note', 'samples'}
        ★`available=False` 면 **값을 내지 않는다**(호출부가 다음 단으로).
    """
    addr = (address or "").strip()
    if not addr:
        return {"available": False, "note": "주소 없음 — 반경을 잡을 수 없다"}
    try:
        from app.services.land_intelligence.presale_service import PresaleService

        # ★★★**좌표가 없으면 `nearby` 는 거리필터를 적용하지 않는다** — 그 함수가
        #   *«중심좌표 없음 — 거리필터 미적용»* 이라 명시하고 **전국 목록을 그대로** 준다.
        #   라이브 검증이 그것을 잡았다: 마석우리인데 **분당센트로·여의도 더로드캐슬**이
        #   섞여 **3,155만원/평**이 나왔고 `distance_m` 이 전부 `None` 이었다.
        #   ★«반경을 넘겼으니 걸렸겠지»는 **추측**이다 — 좌표를 먼저 얻고, 못 얻으면 **쓰지 않는다.**
        from apps.api.app.services.land_intelligence.nearby_map_service import NearbyMapService

        center = None
        try:
            center = await NearbyMapService().geocode_one(addr)
        except Exception as e:  # noqa: BLE001
            logger.warning("청약홈 신호 지오코딩 실패: %s", str(e)[:100])
        if not center or center.get("lat") is None or center.get("lon") is None:
            return {"available": False,
                    "note": "중심좌표를 얻지 못해 반경을 적용할 수 없음 — 신호 미사용"}

        svc = PresaleService()
        near = await svc.nearby(center_lat=center["lat"], center_lon=center["lon"], area=None,
                                radius_m=_PRESALE_SIGNAL_RADIUS_M, months_back=12)
        items = near.get("items") or []
        # ★★거리가 **실제로 붙었는지** 확인한다 — `None` 이면 필터가 안 걸린 것이다.
        items = [it for it in items
                 if isinstance(it.get("distance_m"), (int, float))
                 and it["distance_m"] <= _PRESALE_SIGNAL_RADIUS_M]
        if not items:
            return {"available": False, "radius_m": _PRESALE_SIGNAL_RADIUS_M,
                    "note": f"반경 {_PRESALE_SIGNAL_RADIUS_M // 1000}km 내 "
                            "거리 확인된 분양 공고 없음"}
        items.sort(key=lambda x: x.get("distance_m") or 10 ** 9)
        pps: list[float] = []
        samples: list[dict[str, Any]] = []
        for it in items[:5]:          # 지연 상한 — 가까운 순으로 최대 5건만 상세 조회
            try:
                d = await svc.detail(it.get("house_manage_no") or "",
                                     it.get("pblanc_no") or "", "apt")
            except Exception:  # noqa: BLE001
                continue
            for m in (d.get("models") or []):
                try:
                    area_sqm = float(m.get("supply_area_m2") or 0)
                    price_man = float(m.get("price_man") or 0)
                except (TypeError, ValueError):
                    continue
                if area_sqm > 0 and price_man > 0:
                    pps.append(price_man / (area_sqm / PYEONG_SQM))
            samples.append({"name": it.get("name"), "distance_m": it.get("distance_m")})
        if len(pps) < _PRESALE_SIGNAL_MIN_SAMPLES:
            return {"available": False, "radius_m": _PRESALE_SIGNAL_RADIUS_M,
                    "note": f"반경 내 분양가 표본 {len(pps)}건 — 하한 "
                            f"{_PRESALE_SIGNAL_MIN_SAMPLES}건 미달로 신호 미사용"}
        nearest = min((s.get("distance_m") or 10 ** 9) for s in samples)
        return {
            "available": True,
            "per_pyeong_man": round(statistics.median(pps)),
            "n": len(pps),
            "radius_m": _PRESALE_SIGNAL_RADIUS_M,
            "nearest_m": None if nearest >= 10 ** 9 else int(nearest),
            "samples": samples,
            "note": (f"청약홈 반경 {_PRESALE_SIGNAL_RADIUS_M // 1000}km 내 "
                     f"주택형 {len(pps)}건 중앙값(공급면적 기준)"),
        }
    except Exception as e:  # noqa: BLE001 — 조회 실패는 다음 단으로(무중단)
        logger.warning("청약홈 신호 조회 실패 — 다음 단으로: %s: %s",
                       type(e).__name__, str(e)[:100])
        return {"available": False, "note": "청약홈 조회 실패"}


async def suggest_base_price(
    db: AsyncSession, site_id: uuid.UUID, bcode: str | None = None,
    construction_cost_per_gfa_won: int | None = None,
    *, collect_cases: bool = False,
) -> dict[str, Any]:
    """기준층 적정분양가 3안 — 주변 실거래 앵커 + 교차검증 신뢰루프. 공급면적(상업=분양면적) 기준.

    construction_cost_per_gfa_won(선택): 정밀공사비(연면적㎡당 원). 전달 시 원가 검증에 사용,
    미전달 시 표준단가(SSOT)로 검증한다(2차 가드 — 시장가가 원가를 회수하는지 교차확인).

    collect_cases=True(opt-in, market_precision W3-8 전용 — 기본 False는 반환 shape 완전 불변,
    무회귀): 내부 ``_trade_per_pyeong`` 호출에 그대로 전달해 개별 MOLIT 사례를 "trade_cases"
    키에 실어 반환한다. ★R1 M-1 봉합: 종전엔 market_precision 조립 단계(comparables.py)가
    이 함수가 이미 가져온 행을 버리고 별도로 재수집(총 16개월 조회 = 8개월×2회)했다 —
    이제 이 함수가 collect_cases=True로 1회만 수집한 원시 행을 그대로 실어 보내고, 조립
    단계는 그 행을 소비만 한다(총 8개월 조회로 원복, 재수집 없음).
    """
    address, pnu, dev_type = await _site_location(db, site_id)
    if not address:
        return {"data_source": "unavailable",
                "note": "현장에 연결된 부지 주소가 없습니다 — 프로젝트 부지분석 후 다시 시도하세요."}

    lawd = (bcode or "").strip() or None
    # ★bcode 오염 가드(전역전파): 입력 bcode는 비권위(엑셀 양식 예시값 잔류·외부전달 오염 가능).
    #   부지 PNU(부지분석 확정 권위값)의 시군구(앞 5자리)와 어긋나면 잘못된 지역 실거래를 조회해
    #   엉뚱한 적정분양가가 나오므로, 오염으로 보고 무시하고 PNU로 유도한다(권위출처 우선).
    pnu_lawd = None  # conv[0]=시군구 5자리(법정동코드 아님) — 아래 비교는 양변 [:5]로 정규화
    if pnu:
        conv = pnu_to_bcode(pnu)
        pnu_lawd = conv[0] if conv else None
    if lawd and pnu_lawd and lawd[:5] != pnu_lawd[:5]:
        lawd = None  # 시군구 불일치 = 오염 → PNU 우선
    if not lawd and pnu_lawd:
        lawd = pnu_lawd
    if not lawd:
        # 프로젝트에 PNU가 없으면 주소를 VWorld로 지오코딩해 PNU→법정동코드 유도(자체 충족).
        try:
            from app.services.external_api.vworld_service import VWorldService
            geo = await VWorldService().geocode_address(address)
            gp = (geo or {}).get("pnu") or ""
            if len(gp) >= 19:
                conv = pnu_to_bcode(gp)
                lawd = conv[0] if conv else None
            elif len(gp) >= 10:
                lawd = gp[:10]
        except Exception:  # noqa: BLE001
            lawd = None
    if not lawd:
        return {"data_source": "unavailable", "address": address,
                "note": "법정동코드(bcode)를 확보하지 못했습니다 — 부지분석에서 주소를 확정하거나 bcode를 전달하세요."}

    sigungu5 = lawd[:5]
    dong = _extract_dong(address)
    is_contract = (dev_type or "").upper() in _CONTRACT_BASIS_TYPES
    area_basis = "contract" if is_contract else "supply"
    area_basis_label = "분양(계약)면적" if is_contract else "공급면적"
    prop_type = _PROP_TYPE.get((dev_type or "").upper(), "apt")

    # ── 원천: MOLIT 실거래(동·시군구) 전용 평당가 ──
    pp = await _trade_per_pyeong(sigungu5, dong, prop_type, collect_cases=collect_cases)
    d_med, d_n = pp["dong"]["median"], pp["dong"]["n"]
    s_med, s_n = pp["sigungu"]["median"], pp["sigungu"]["n"]
    # ★R1 M-1: collect_cases=True 일 때만 원시 사례를 보존(기본 False 는 이 변수가 아예 안 쓰임 —
    # 아래 반환 dict들에 조건부로만 실려 반환 shape 을 불변으로 유지한다).
    trade_cases_extra: dict[str, Any] = {"trade_cases": pp.get("cases") or []} if collect_cases else {}

    # ── 교차검증(신뢰루프): 앵커 vs 보조 신호. 이상치 제외·신뢰도 산출 ──
    # ★★**앵커 계단을 올렸다**(2026-09-06 · 사용자 결정):
    #     ①분양권 전매 → ②최근 건축년도(신축) 실거래 → ③혼합 실거래
    #   종전 앵커는 ③(혼합)뿐이었고, 실측상 **-33.5%** 였다:
    #       마석우리 공급평당 — 혼합 1,200 ↔ 분양권 1,827 ↔ 사용자 관측 실제 분양 1,804
    #   ★기존 신호(동·시군구 실거래)는 **그대로 둔다** — 교차검증 재료로 계속 쓰인다.
    #     바뀌는 것은 **어느 것을 앵커로 삼는가**다.
    presale_pp: dict[str, Any] = {}
    if prop_type == "apt":
        try:
            presale_pp = await _trade_per_pyeong(sigungu5, dong, "apt_presale")
        except TypeError as e:
            # ★시그니처 불일치는 «조회 실패»가 아니라 **배선 오류**다(무언 폴백 금지).
            logger.error("분양권 조회 시그니처 불일치 — 배선 오류: %s", str(e)[:140])
        except Exception as e:  # noqa: BLE001 — 조회 실패는 다음 단으로(무중단)
            logger.warning("분양권 전매 조회 실패 — 다음 단으로: %s: %s",
                           type(e).__name__, str(e)[:100])
    p_med = (presale_pp.get("dong") or {}).get("median") or (presale_pp.get("sigungu") or {}).get("median")
    p_n = ((presale_pp.get("dong") or {}).get("n") or 0) or ((presale_pp.get("sigungu") or {}).get("n") or 0)
    rec = pp.get("recent_dong") or {}
    if not (rec.get("median") and (rec.get("n") or 0) >= 5):
        rec = pp.get("recent_sigungu") or {}

    # ★★청약홈을 **신호로 승격**(2026-09-06 · 사용자 결정). 단 **반경 안**에서만 —
    #   시도 전체를 쓰면 «용인 신봉동 과대표시 사고»(럭셔리 분양가 2배 과대)가 재발한다.
    #   실측: 남양주(41360) → 「경기」 최근 2건이 **성남복정 8.12억 · 시흥은계 4.85억** 으로
    #   마석 사업지와 무관하다. 그래서 `_presale_signal_per_pyeong`(반경 10km)을 따로 둔다.
    #   ★가중치는 분양권 전매(1.6)보다 **낮다** — 청약홈은 **공급자 책정가**라 시장 검증 전이고,
    #     실제 계약가는 미분양·할인으로 달라질 수 있다. 분양권은 **거래된 값**이다.
    presale_sig = await _presale_signal_per_pyeong(address)

    signals: list[Signal] = []
    if presale_sig.get("available") and presale_sig.get("per_pyeong_man"):
        signals.append(Signal("청약홈_분양가", float(presale_sig["per_pyeong_man"]),
                              sample_size=int(presale_sig.get("n") or 0),
                              source="live", weight=1.5))
    # ★분양권은 **이미 신축 분양가**이고 **거래된 값**이다 — 가중치 최상.
    if p_med and p_n >= 5:
        signals.append(Signal("분양권_전매", float(p_med), sample_size=int(p_n),
                              source="live", weight=1.6))
    if rec.get("median") and (rec.get("n") or 0) >= 5:
        signals.append(Signal("신축_실거래", float(rec["median"]), sample_size=int(rec["n"]),
                              source="live", weight=1.45))
    if d_med:
        signals.append(Signal("동_실거래", float(d_med), sample_size=d_n, source="live", weight=1.3))
    if s_med:
        signals.append(Signal("시군구_실거래", float(s_med), sample_size=s_n, source="live", weight=1.0))
    if not signals:
        return {"data_source": "unavailable", "address": address, "lawd_cd": lawd,
                "note": "주변 실거래가 없어 적정분양가를 산출할 수 없습니다(가짜값 금지).",
                **trade_cases_extra}

    # ★앵커도 같은 계단을 따른다 — 신호를 추가만 하고 앵커를 안 바꾸면 **값이 안 움직인다**.
    _names = {sig.name for sig in signals}
    _anchor = next((n for n in ("분양권_전매", "청약홈_분양가", "신축_실거래",
                                "동_실거래", "시군구_실거래")
                    if n in _names), "시군구_실거래")
    trust = cross_validate(
        signals, anchor=_anchor,
        outlier_ratio=1.6, min_anchor_samples=20, plausible_min=_PP_MIN, plausible_max=_PP_MAX,
    )
    if trust.trusted_value is None or trust.verdict == "fail":
        # ★보류값 계약(2026-08-25) — `data_source="unavailable"` 은 **자체 어휘**였다.
        #   닫힌 코드를 함께 실어 기계가 셀 수 있게 한다(기존 키는 그대로 — 소비처 불변).
        return {"data_source": "unavailable", "address": address, "lawd_cd": lawd,
                "trust": trust.to_dict(),
                **withheld(INSUFFICIENT_COVERAGE,
                           "주변 실거래 신뢰도 부족으로 적정분양가 산출 보류(가짜값 금지).",
                           field="suggested_price", text_field="note"),
                **trade_cases_extra}

    market_pp_exclusive = float(trust.trusted_value)        # 만원/평(전용) — 주변 시세
    # 공급면적 평당가 시세 = 전용 평당가 × 전용률(상업=분양면적도 동일 환산 가정 후 라벨만 구분)
    market_pp_supply = market_pp_exclusive * _JEONYULRYUL
    per_sqm_supply_10k = market_pp_supply / PYEONG_SQM       # 만원/㎡(공급)

    tiers = []
    for key, prem in _PREMIUM.items():
        pp_sup = market_pp_supply * prem
        tiers.append({
            "tier": key,
            "label": _TIER_LABEL[key],
            "premium_pct": round((prem - 1) * 100),
            "per_pyeong_10k": round(pp_sup),                       # 공급 평당가(만원)
            "per_sqm_10k": round(per_sqm_supply_10k * prem, 1),    # base_unit_price 후보(만원/㎡, PER_AREA)
            "ref_unit_total_10k": round(pp_sup * _REF_SUPPLY_PYEONG),  # 84타입(공급34평) 총액(만원)
        })

    # ── 2차 가드: 원가(공사비+간접) 회수 검증 — 시장가가 원가를 못 넘으면 경고(가짜값 아님) ──
    cost_val = _cost_validation(dev_type, tiers, construction_cost_per_gfa_won)
    cost_note = f" ⚠️ {cost_val['warning']}" if (cost_val and cost_val.get("warning")) else ""

    # ── 전역정책 Phase0: 근거·법령·신선도 공용 블록(build_evidence_block 경유) ──
    # legal_refs/trust는 하위호환 위해 기존 키도 유지하고, evidence·provenance를 가산한다.
    # provenance=molit_transactions(실거래) 신선도. 모두 graceful(실패→빈배열).
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        ev_block = build_evidence_block(
            items=_price_evidence(market_pp_supply, area_basis_label, tiers, trust),
            legal_ref_keys=_SALES_LEGAL_REF_KEYS,
            trust=trust,
            sources=["molit_transactions"],
        )
    except Exception:  # noqa: BLE001 — 공용블록 실패해도 분양가 결과 무손상
        ev_block = {"evidence": [], "legal_refs": [], "provenance": [], "trust": None}

    # ── 청약홈 주변 분양가 참고·교차검증(★앵커 아님 — 가격 tiers 무변경). 과대표시 방지 위해 '참고'로만. ──
    # ★★**위험은 양방향이다**(2026-09-06 실측으로 추가). 종전 주석은 «과대표시 방지» 만
    #   적었는데, **과소표시 위험이 실재하고 더 컸다**:
    #       남양주 화도읍 마석우리 · 공급 평당(만원)
    #         실거래 앵커      1,200
    #         분양권 전매      1,827
    #         실제 분양(관측)  1,804   → 종전 앵커는 **-33.5%**
    #   사용자가 «주변 신축 분양이 평당 2,000에 육박하는데 왜 1,200인가» 로 신고했다.
    #   ★**과대를 막으려다 과소를 만들었다** — §D-19(경계는 양방향)의 다른 얼굴이다.
    #   ★현재 조치: **site 미연결 경로(2순위)** 는 분양권 전매를 앵커로 삼아 오차 1.3%.
    #     이 경로(site 연결)의 앵커 변경은 **도메인·사업 결정**이라 보류하고
    #     `tests/test_presale_anchor_ledger.py` 가 부채로 드러낸다.
    nearby_presale = await _nearby_presale_reference(sigungu5)
    if nearby_presale.get("available") and nearby_presale.get("price_range_man"):
        pr = nearby_presale["price_range_man"]
        _ev_list = ev_block.get("evidence")
        if not isinstance(_ev_list, list):
            _ev_list = []
            ev_block["evidence"] = _ev_list
        _ev_list.append({
            "label": "주변 분양가(청약홈) 참고",
            "value": f"{pr[0]:,}~{pr[1]:,}만원",
            "basis": "청약홈 인근 분양 단지 분양가 — 거래사례비교 '참고'(산정 앵커는 주변 실거래, 주변 분양가 과대표시 방지)",
        })

    # ★신호로 **채택된** 청약홈은 참고와 다르게 표기한다 — 어느 것이 값을 정했는지 갈린다.
    if presale_sig.get("available"):
        _evl = ev_block.get("evidence")
        if isinstance(_evl, list):
            _evl.append({
                "label": ("주변 분양가(청약홈) — **앵커**"
                          if _anchor == "청약홈_분양가" else "주변 분양가(청약홈) 신호"),
                "value": f"{presale_sig['per_pyeong_man']:,}만원/평(공급)",
                "basis": (
                    f"{presale_sig.get('note')} · 최근접 "
                    f"{(presale_sig.get('nearest_m') or 0) / 1000:.1f}km"
                    " — 공급자 책정 분양가라 실제 계약가와 다를 수 있습니다"
                ),
            })

    return {
        "data_source": "live",
        "address": address,
        "lawd_cd": lawd,
        "development_type": dev_type,
        "area_basis": area_basis,
        "area_basis_label": area_basis_label,
        "ref_supply_sqm": _REF_SUPPLY_SQM,
        "ref_supply_pyeong": _REF_SUPPLY_PYEONG,
        "market_reference": {
            "scope": "동" if (d_med and trust.used and "동_실거래" in trust.used) else "시군구",
            "dong": pp["dong"], "sigungu": pp["sigungu"],
            "market_pp_exclusive_10k": round(market_pp_exclusive),   # 주변 실거래 평당가(전용)
            "market_pp_supply_10k": round(market_pp_supply),         # 공급환산 평당가(시세)
            "jeonyulryul": _JEONYULRYUL,
        },
        "trust": trust.to_dict(),                 # 신뢰도·이상치·경고(투명)
        "tiers": tiers,                           # 신축 프리미엄 3안(공급 평당가 기준)
        "cost_validation": cost_val,              # 2차 가드: 원가 회수 검증(None=원가엔진 미가용)
        # ★Phase0 공용 근거블록 — legal_refs(레지스트리 단일출처) + evidence·provenance 가산.
        "legal_refs": ev_block.get("legal_refs") or _sales_legal_refs(),
        "evidence": ev_block.get("evidence", []),       # 산출 근거 트레이스(EvidencePanel)
        "provenance": ev_block.get("provenance", []),   # 원천(실거래) 신선도
        "nearby_presale": nearby_presale,               # ★청약홈 주변 분양가 참고·교차검증(앵커 아님)
        "note": (f"적정분양가 = 주변 실거래({trust.to_dict()['used_sources']}) 시세에 신축 프리미엄. "
                 f"평당가는 {area_basis_label} 기준(전용률 {_JEONYULRYUL}). 신뢰도 {trust.confidence:.0%}. "
                 "기준단가 채택 후 층/동/라인/평형 가중치로 분산." + cost_note),
        **trade_cases_extra,
    }
