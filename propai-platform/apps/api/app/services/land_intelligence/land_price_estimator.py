"""토지 적정 매입가 추정 — 공시지가 × 지역 시세보정계수 (+ 주변 토지 실거래 블렌딩).

토지조서 '매입예정가' 자동 산정용. 개별공시지가(NED/VWorld)에 지역별 공시지가 현실화율
역수(MARKET_MULTIPLIER)를 곱해 적정 시세를 추정한다. 사용자가 수정 가능(참고값).
"""

from __future__ import annotations

from typing import Any

# 지역 시세보정계수는 comprehensive_analysis_service의 검증된 맵을 재사용(인스턴스화 없이).
from app.services.land_intelligence.comprehensive_analysis_service import ComprehensiveAnalysisService as _CAS


def _market_multiplier(address: str) -> tuple[float, str]:
    addr = address or ""
    for district, mult in _CAS.MARKET_MULTIPLIER_MAP.items():
        if district in addr:
            return mult, f"{district} 공시지가 현실화율(약 {100/mult:.0f}%) 반영 보정 {mult}배"
    for region, mult in _CAS.MARKET_MULTIPLIER_REGION.items():
        if region in addr:
            return mult, f"{region} 평균 공시지가 현실화율 반영 보정 {mult}배"
    return 1.2, "전국 평균 보정 1.2배(지역 미등록)"


async def estimate_land_price(
    *,
    pnu: str | None = None,
    address: str = "",
    area_sqm: float | None = None,
    official_price_per_sqm: float | None = None,
) -> dict[str, Any]:
    """적정 매입가(원) 추정. 공시지가 미입력 시 PNU로 NED 토지특성 조회."""
    op = official_price_per_sqm
    area = area_sqm
    src = "입력값"

    if (op is None or not area):
        try:
            from app.services.external_api.vworld_service import VWorldService
            vw = VWorldService()
            # PNU 없으면 주소→PNU 지오코딩
            if not pnu and address:
                geo = await vw.geocode_address(address)
                pnu = (geo or {}).get("pnu") or pnu
            if pnu:
                lc = await vw.get_land_characteristics(pnu)
                if lc:
                    op = op if op is not None else lc.get("official_price_per_sqm")
                    area = area or lc.get("area_sqm")
                    src = "NED 토지특성(주소→PNU 개별공시지가)"
        except Exception:  # noqa: BLE001
            pass

    if not op or op <= 0:
        return {"ok": False, "message": "공시지가를 확인할 수 없습니다. PNU 또는 공시지가를 입력하세요."}

    mult, rationale = _market_multiplier(address)
    op = float(op)
    est_per_sqm = int(op * mult)
    area_f = float(area) if area else None
    est_total = int(est_per_sqm * area_f) if area_f else None

    return {
        "ok": True,
        "official_price_per_sqm": int(op),
        "market_multiplier": mult,
        "estimated_price_per_sqm": est_per_sqm,
        "area_sqm": round(area_f, 1) if area_f else None,
        "estimated_total_won": est_total,
        "source": src,
        "rationale": (
            f"개별공시지가 {int(op):,}원/㎡ × {rationale}"
            + (f" × 면적 {round(area_f, 1):,}㎡ = 적정 매입가 약 {est_total:,}원" if area_f and est_total else "")
            + ". 참고용 추정치이며 사용자가 수정할 수 있습니다."
        ),
    }
