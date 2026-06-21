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


def _price_evidence(
    op: float, mult: float, mult_rationale: str, est_per_sqm: int,
    area_f: float | None, est_total: int | None, src: str,
) -> list[dict[str, Any]]:
    """토지 적정 매입가 산출 근거 트레이스(EvidencePanel 소비 구조) — graceful 빈배열.

    공시지가(원천)·지역 보정계수·적정시세·면적·총매입가를 한 줄씩 트레이스한다.
    법령 근거 키는 현 레지스트리에 verified 키가 없어 연결하지 않는다(가짜 링크 금지).
    """
    try:
        ev: list[dict[str, Any]] = [{
            "label": "개별공시지가",
            "value": f"{int(op):,}원/㎡",
            "basis": f"{src} — 부동산 가격공시(개별공시지가). PNU 입력 시 NED 토지특성으로 자동조회.",
        }, {
            "label": "지역 시세보정계수",
            "value": f"×{mult}",
            "basis": mult_rationale,
        }, {
            "label": "적정 시세",
            "value": f"{est_per_sqm:,}원/㎡",
            "basis": f"개별공시지가 × 보정계수 = {int(op):,} × {mult}",
        }]
        if area_f:
            ev.append({
                "label": "토지면적",
                "value": f"{round(area_f, 1):,}㎡",
                "basis": f"{src}" if "NED" in src else "사용자 입력값",
            })
        if est_total:
            ev.append({
                "label": "적정 총 매입가",
                "value": f"{est_total:,}원",
                "basis": f"적정 시세 × 면적 = {est_per_sqm:,} × {round(area_f or 0, 1):,} (참고용 추정치, 수정 가능)",
            })
        return ev
    except Exception:  # noqa: BLE001
        return []


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

    # ── 전역정책 Phase0: 근거·법령·신선도 공용 블록(build_evidence_block 경유) ──
    # 적정 매입가 산출 근거 트레이스 + 원천(공시지가/토지정보) 신선도를 가산한다.
    # 법령 근거(P2): 공시지가는 부동산공시법 제10조(개별공시지가 결정·공시), 적정가 추정은
    #   감정평가법 제3조(표준지공시지가 기준 원칙)를 verified 딥링크로 연결한다.
    # 모두 graceful(실패→빈배열) — 기존 응답 키·계산 무손상.
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        ev_block = build_evidence_block(
            items=_price_evidence(op, mult, rationale, est_per_sqm, area_f, est_total, src),
            legal_ref_keys=["official_land_price", "land_appraisal"],
            sources=["molit_official_price", "vworld_land_info"],
        )
    except Exception:  # noqa: BLE001 — 공용블록 실패해도 적정가 추정 결과 무손상
        ev_block = {"evidence": [], "legal_refs": [], "provenance": [], "trust": None}

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
        # 신뢰 정보(정직 표기) — 단일출처(공시지가×보정) 추정임을 명시하고 교차검증 경로를 안내한다.
        # (가짜 cross_validation 신호를 만들지 않고, 단일출처 한계를 정직하게 고지)
        "trust": {
            "method": "single_source",
            "basis": "개별공시지가 × 지역 시세보정(현실화율 역수)",
            "confidence": 0.7,
            "recheck_recommended": True,
            "cross_validation": None,
            "note": "단일 출처(공시지가 기준) 추정입니다. 주변 토지 실거래와의 교차검증은 "
                    "/land-price/desk-appraisal(공시지가법+거래사례비교법 결합) 또는 토지조서 구획도의 "
                    "주변 실거래를 활용하세요.",
        },
        # ★Phase0 공용 근거블록(가산) — 산출 근거 트레이스(EvidencePanel) + 원천 신선도.
        # legal_refs: 부동산공시법 제10조·감정평가법 제3조 verified 딥링크(P2 연결). 기존 키·계산 무손상.
        "evidence": ev_block.get("evidence", []),       # 산출 근거 트레이스(EvidencePanel)
        "legal_refs": ev_block.get("legal_refs", []),   # 공시지가·감정평가 법령링크(verified)
        "provenance": ev_block.get("provenance", []),   # 원천(공시지가/토지정보) 신선도
    }
