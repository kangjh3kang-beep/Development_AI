"""P1-1 적정분양가 추천 — 현장(분양) 기준층 분양가를 주변시세로 산정해 3안 제시.

분양가 산정의 1차 기준은 '동일종목 주변시세 + 주변 분양가'(거래사례비교)이다([[project_fair_price_basis]]).
시장 인텔의 build_report(라이브 실거래·분양가 → compute_fair_price)를 그대로 재사용해
대표 84㎡ 적정 총액을 얻고, 이를 ㎡단가로 환산해 공격적/기준/보수적 3안을 만든다.

가짜값 금지: 주변 비교데이터가 없으면 data_source='unavailable'.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.site_org import SalesSite
from apps.api.integrations.region_codes import pnu_to_bcode

PYEONG_SQM = 3.305785
_REF_AREA_SQM = 84.0  # 시장 대표 평형(주변 분양가/실거래의 84㎡ 기준 총액)

# 3안 배수: 보수적(수요 안전)·기준(시장 적정)·공격적(상단 분양).
_TIERS = {"conservative": 0.93, "base": 1.00, "aggressive": 1.07}
_TIER_LABEL = {"conservative": "보수적", "base": "기준", "aggressive": "공격적"}


async def _site_location(db: AsyncSession, site_id: uuid.UUID) -> tuple[str | None, str | None]:
    """site → project 의 주소·첫 PNU(법정동코드 유도용)를 반환."""
    site = (await db.execute(select(SalesSite).where(SalesSite.id == site_id))).scalar_one_or_none()
    if not site:
        return None, None
    row = (await db.execute(
        text("select address, pnu_codes from projects where id = :pid"),
        {"pid": str(site.project_id)},
    )).mappings().first()
    if not row:
        return None, None
    address = row.get("address")
    pnu = None
    pc = row.get("pnu_codes")
    if isinstance(pc, (list, tuple)) and pc:
        pnu = str(pc[0])
    elif isinstance(pc, dict) and pc:
        pnu = str(next(iter(pc.values())))
    elif isinstance(pc, str) and pc:
        pnu = pc
    return address, pnu


async def suggest_base_price(
    db: AsyncSession, site_id: uuid.UUID, bcode: str | None = None,
) -> dict[str, Any]:
    """기준층 적정분양가 3안(공격적/기준/보수적)을 ㎡단가·84㎡총액·평당가로 제시한다."""
    address, pnu = await _site_location(db, site_id)
    if not address:
        return {"data_source": "unavailable",
                "note": "현장에 연결된 부지 주소가 없습니다 — 프로젝트 부지분석 후 다시 시도하세요."}

    # 법정동코드: 명시 bcode > PNU 유도. 둘 다 없으면 정직 unavailable.
    lawd = (bcode or "").strip() or None
    if not lawd and pnu:
        conv = pnu_to_bcode(pnu)
        lawd = conv[0] if conv else None
    if not lawd:
        return {"data_source": "unavailable", "address": address,
                "note": "법정동코드(bcode)를 확보하지 못했습니다 — 부지분석에서 주소를 확정하거나 bcode를 전달하세요."}

    # 시장 인텔 재사용(라이브 실거래·주변 분양가 → 적정가). LLM 미사용(빠르게).
    from app.services.market.market_report_service import MarketReportService
    report = await MarketReportService().build_report(address, lawd, use_llm=False, options={})
    pb = report.get("pricing_band") or {}
    mr = pb.get("market_reference") or {}
    fair_total_10k = mr.get("fair_price_10k")  # 84㎡ 기준 적정 총액(만원)
    if not fair_total_10k or fair_total_10k <= 0:
        return {"data_source": pb.get("data_source", "unavailable"), "address": address, "lawd_cd": lawd,
                "note": "주변 실거래·분양가 비교 데이터가 없어 적정분양가를 산출할 수 없습니다(가짜값 금지)."}

    per_sqm_10k = fair_total_10k / _REF_AREA_SQM           # 만원/㎡
    per_pyeong_10k = per_sqm_10k * PYEONG_SQM              # 만원/평
    tiers = []
    for key, f in _TIERS.items():
        tiers.append({
            "tier": key,
            "label": _TIER_LABEL[key],
            "per_sqm_10k": round(per_sqm_10k * f, 1),       # 기준단가 후보(base_unit_price=만원/㎡)
            "per_pyeong_10k": round(per_pyeong_10k * f),    # 표시용 평당가(만원)
            "ref_unit_total_10k": round(per_sqm_10k * f * _REF_AREA_SQM),  # 84㎡ 총액(만원)
        })

    return {
        "data_source": mr.get("data_source", pb.get("data_source", "fallback")),
        "address": address,
        "lawd_cd": lawd,
        "ref_area_sqm": _REF_AREA_SQM,
        "market_reference": mr,           # 주변 분양가·실거래·가중방식(근거)
        "tiers": tiers,                   # 공/기/보 3안(㎡단가·평당·84㎡총액)
        "basis": pb.get("basis"),
        "note": "적정분양가 1차 기준=거래사례비교(주변 실거래+주변 분양가). 기준층 단가로 채택 후 층/동/라인/평형 가중치로 분산.",
    }
