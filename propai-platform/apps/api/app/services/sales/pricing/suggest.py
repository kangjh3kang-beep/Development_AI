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

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.data_validation.trust import Signal, cross_validate
from apps.api.database.models.sales.site_org import SalesSite
from apps.api.integrations.region_codes import pnu_to_bcode

PYEONG_SQM = 3.305785
_REF_EXCLUSIVE_SQM = 84.0          # 84타입 전용면적
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
    site = (await db.execute(select(SalesSite).where(SalesSite.id == site_id))).scalar_one_or_none()
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
    cases: list[dict[str, Any]] = []
    for ym in yms:
        try:
            rows = await m.get_transactions(sigungu5, ym, prop_type=prop_type, num_rows=1000)
        except Exception:  # noqa: BLE001
            rows = []
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
            in_range = _PP_MIN <= pp <= _PP_MAX
            matched_dong = bool(dong and dong in str(r.get("dong") or ""))
            if collect_cases:
                cases.append({
                    "ym": ym, "dong": r.get("dong"), "jibun": r.get("jibun"),
                    "building_name": r.get("building_name"), "deal_date": r.get("deal_date"),
                    "price_10k_won": amt, "area_m2": ar, "per_pyeong_10k": round(pp, 1),
                    "matched_dong": matched_dong, "included": in_range,
                    "exclude_reason": (
                        None if in_range
                        else f"평당가 sanity 범위({_PP_MIN:.0f}~{_PP_MAX:.0f}만원/평) 벗어남"
                    ),
                })
            if not in_range:
                continue
            sigu_pp.append(pp)
            if matched_dong:
                dong_pp.append(pp)
    result: dict[str, Any] = {
        "dong": {"median": round(statistics.median(dong_pp)) if dong_pp else None, "n": len(dong_pp)},
        "sigungu": {"median": round(statistics.median(sigu_pp)) if sigu_pp else None, "n": len(sigu_pp)},
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

    # ── 교차검증(신뢰루프): 동(앵커) vs 시군구. 이상치 제외·신뢰도 산출 ──
    signals: list[Signal] = []
    if d_med:
        signals.append(Signal("동_실거래", float(d_med), sample_size=d_n, source="live", weight=1.3))
    if s_med:
        signals.append(Signal("시군구_실거래", float(s_med), sample_size=s_n, source="live", weight=1.0))
    if not signals:
        return {"data_source": "unavailable", "address": address, "lawd_cd": lawd,
                "note": "주변 실거래가 없어 적정분양가를 산출할 수 없습니다(가짜값 금지).",
                **trade_cases_extra}

    trust = cross_validate(
        signals, anchor="동_실거래" if d_med else "시군구_실거래",
        outlier_ratio=1.6, min_anchor_samples=20, plausible_min=_PP_MIN, plausible_max=_PP_MAX,
    )
    if trust.trusted_value is None or trust.verdict == "fail":
        return {"data_source": "unavailable", "address": address, "lawd_cd": lawd,
                "trust": trust.to_dict(),
                "note": "주변 실거래 신뢰도 부족으로 적정분양가 산출 보류(가짜값 금지).",
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
