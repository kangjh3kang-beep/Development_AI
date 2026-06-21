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
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.site_org import SalesSite
from apps.api.integrations.region_codes import pnu_to_bcode
from app.services.data_validation.trust import Signal, cross_validate
from datetime import UTC

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


def _sales_legal_refs() -> list[dict]:
    """분양가 추천 결과에 부착할 분양 관련 법령 근거(verified 딥링크) — 가산 필드.

    레지스트리 미가용 시 빈 리스트(graceful, 기존 응답 무손상).
    근거: 건축물분양법 분양신고(제5조)·분양보증/신탁(제6조), 분양가상한제(주택법 제57조).
    """
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs([
            "building_sales_filing", "building_sales_guarantee", "housing_price_cap",
        ])
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


async def _trade_per_pyeong(sigungu5: str, dong: str | None, prop_type: str) -> dict[str, Any]:
    """MOLIT 실거래 → 전용 평당가(만원). 동/시군구 각각의 중앙값·표본수."""
    from datetime import datetime, timezone
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
                continue
            if amt <= 0 or ar <= 0:
                continue
            pp = amt / (ar / PYEONG_SQM)   # 만원/평(전용)
            if not (_PP_MIN <= pp <= _PP_MAX):
                continue
            sigu_pp.append(pp)
            if dong and dong in str(r.get("dong") or ""):
                dong_pp.append(pp)
    return {
        "dong": {"median": round(statistics.median(dong_pp)) if dong_pp else None, "n": len(dong_pp)},
        "sigungu": {"median": round(statistics.median(sigu_pp)) if sigu_pp else None, "n": len(sigu_pp)},
    }


async def suggest_base_price(
    db: AsyncSession, site_id: uuid.UUID, bcode: str | None = None,
    construction_cost_per_gfa_won: int | None = None,
) -> dict[str, Any]:
    """기준층 적정분양가 3안 — 주변 실거래 앵커 + 교차검증 신뢰루프. 공급면적(상업=분양면적) 기준.

    construction_cost_per_gfa_won(선택): 정밀공사비(연면적㎡당 원). 전달 시 원가 검증에 사용,
    미전달 시 표준단가(SSOT)로 검증한다(2차 가드 — 시장가가 원가를 회수하는지 교차확인).
    """
    address, pnu, dev_type = await _site_location(db, site_id)
    if not address:
        return {"data_source": "unavailable",
                "note": "현장에 연결된 부지 주소가 없습니다 — 프로젝트 부지분석 후 다시 시도하세요."}

    lawd = (bcode or "").strip() or None
    if not lawd and pnu:
        conv = pnu_to_bcode(pnu)
        lawd = conv[0] if conv else None
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
    pp = await _trade_per_pyeong(sigungu5, dong, prop_type)
    d_med, d_n = pp["dong"]["median"], pp["dong"]["n"]
    s_med, s_n = pp["sigungu"]["median"], pp["sigungu"]["n"]

    # ── 교차검증(신뢰루프): 동(앵커) vs 시군구. 이상치 제외·신뢰도 산출 ──
    signals: list[Signal] = []
    if d_med:
        signals.append(Signal("동_실거래", float(d_med), sample_size=d_n, source="live", weight=1.3))
    if s_med:
        signals.append(Signal("시군구_실거래", float(s_med), sample_size=s_n, source="live", weight=1.0))
    if not signals:
        return {"data_source": "unavailable", "address": address, "lawd_cd": lawd,
                "note": "주변 실거래가 없어 적정분양가를 산출할 수 없습니다(가짜값 금지)."}

    trust = cross_validate(
        signals, anchor="동_실거래" if d_med else "시군구_실거래",
        outlier_ratio=1.6, min_anchor_samples=20, plausible_min=_PP_MIN, plausible_max=_PP_MAX,
    )
    if trust.trusted_value is None or trust.verdict == "fail":
        return {"data_source": "unavailable", "address": address, "lawd_cd": lawd,
                "trust": trust.to_dict(),
                "note": "주변 실거래 신뢰도 부족으로 적정분양가 산출 보류(가짜값 금지)."}

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
        "legal_refs": _sales_legal_refs(),        # 분양 관련 법령 근거(가산) — 건축물분양법 신고·보증
        "note": (f"적정분양가 = 주변 실거래({trust.to_dict()['used_sources']}) 시세에 신축 프리미엄. "
                 f"평당가는 {area_basis_label} 기준(전용률 {_JEONYULRYUL}). 신뢰도 {trust.confidence:.0%}. "
                 "기준단가 채택 후 층/동/라인/평형 가중치로 분산." + cost_note),
    }
