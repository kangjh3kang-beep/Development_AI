"""공동주택/집합건물 대지지분(대지권) 분석 — 토지조서 정확화.

토지조서는 '실토지면적'을 확보하기 위한 것이다. 단일/다량 필지에 공동주택·다세대·
집합상가가 건축된 경우, 각 세대(동·호)에 대지지분이 배정돼 있으므로 세대별 대지지분의
합이 필지(대지)면적과 일치해야 정확한 토지조서가 완성된다.

산정: 건축물대장 표제부(대지면적) + 전유공용면적(호별 전유면적) → 호별 대지지분을
전유면적 비례로 배분(area-weighted). Σ(세대 대지지분)=대지면적(구성상 일치)으로 정합 검증.
무목업: 정확 대지권비율은 등기부(대지권등록부) 유료라 '전유면적 비례 산정'임을 정직 표기.
키 미설정/무자료/단독·토지는 is_aggregate=False로 정직 반환(가짜 생성 금지).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PYEONG_SQM = 3.305785  # 1평 = 3.305785㎡ (대지지분 평 환산 공용 상수)


def _condo_legal_refs() -> list[dict]:
    """집합건물 대지지분(대지사용권) 산정의 법령 근거(verified 딥링크) — 가산 필드.

    레지스트리 미가용(import 실패) 시 빈 리스트(graceful, 기존 응답 무손상).
    근거: 집합건물법 구분소유(제1·2조)·대지사용권 일체성(제20조)·관리단(제23조)·분양자 담보책임(제9조).
    """
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs([
            "condo_ownership", "condo_section_def", "land_use_right",
            "condo_management_body", "condo_seller_warranty",
        ])
    except Exception:  # noqa: BLE001 — 근거 부착 실패는 핵심 산정에 무영향(정직 빈 리스트)
        return []


class LandShareService:
    """집합건물 세대별 대지지분 분석."""

    async def analyze_by_pnu(self, pnu: str) -> dict[str, Any]:
        from app.services.external_api.building_registry_service import BuildingRegistryService

        if not pnu or len(pnu) < 19:
            return {"is_aggregate": False, "pnu": pnu, "reason": "PNU(19자리)가 필요합니다."}

        breg = BuildingRegistryService()
        title = await breg.get_title_by_pnu(pnu)
        units = await breg.get_exclusive_units_by_pnu(pnu)

        plat_area = float((title or {}).get("plat_area_sqm") or 0)
        # 표제부 대지면적이 비면 VWorld 토지특성(필지 면적)으로 폴백.
        if plat_area <= 0:
            try:
                from app.services.external_api.vworld_service import VWorldService
                lc = await VWorldService().get_land_characteristics(pnu)
                plat_area = float((lc or {}).get("area_sqm") or 0)
            except Exception:  # noqa: BLE001
                plat_area = 0.0

        if not units:
            return {
                "is_aggregate": False, "pnu": pnu,
                "plat_area_sqm": round(plat_area, 2) if plat_area else None,
                "reason": "집합건축물 전유부 미확인 — 토지(나대지)·단독건물이거나 건축물대장 미승인. "
                          "이 경우 필지 면적 자체가 실토지면적입니다(세대 대지지분 분할 없음).",
            }

        # 방어적 접근(.get): 상위 메서드가 키를 보장하더라도 형태 변화에 KeyError 없이 견딘다.
        def _ex(u: dict[str, Any]) -> float:
            try:
                return float(u.get("exclusive_area_sqm") or 0)
            except (TypeError, ValueError):
                return 0.0

        total_excl = sum(_ex(u) for u in units)
        result_units: list[dict[str, Any]] = []
        for u in units:
            ex = _ex(u)
            ratio = (ex / total_excl) if total_excl > 0 else 0.0
            share_sqm = plat_area * ratio
            result_units.append({
                "dong": str(u.get("dong", "") or ""), "ho": str(u.get("ho", "") or ""),
                "exclusive_area_sqm": round(ex, 2),
                "exclusive_pyeong": round(ex / PYEONG_SQM, 2),
                "share_ratio": round(ratio, 6),
                "land_share_sqm": round(share_sqm, 3),
                "land_share_pyeong": round(share_sqm / PYEONG_SQM, 3),
                "purpose": str(u.get("purpose", "") or ""),
            })

        sum_share = round(sum(x["land_share_sqm"] for x in result_units), 2)
        plat_r = round(plat_area, 2)
        # 합계 일치(sum_match)는 전유 비례 산정이라 구성상 성립 — '정확성 증명'이 아니다(반올림만 봄).
        sum_match = (plat_area > 0) and abs(sum_share - plat_r) <= max(0.5, plat_r * 0.01)

        # ★실제로 실패할 수 있는 교차검증: 표제부 세대/호수(hhldCnt/hoCnt) vs 전유부 집계 호수.
        #   불일치하면 일부 세대 전유부 누락·대지권 미등기 의심 → 비례배분 신뢰도 저하 경고.
        title_units = max(
            int((title or {}).get("household_count") or 0),
            int((title or {}).get("ho_count") or 0),
        )
        n_units = len(result_units)
        # ★방향성 교차검증: '누락(전유부 호수 < 표제부)'만 신뢰도 저하로 본다.
        #   - 부족(n_units < 표제부): 일부 세대 전유부 누락 → 그 지분이 나머지에 과대배분 → 경고(실패 가능).
        #   - 초과/동일(n_units ≥ 표제부): 집합상가·오피스텔 근생 호실 등으로 전유부가 더 많은 건 정상 → 경고 안 함.
        #   허용오차 3%(반올림 흡수). 표제부 세대수 미제공(0)이면 교차검증 불가로 통과.
        count_tol = round(title_units * 0.03)
        count_match = (title_units == 0) or (n_units >= title_units - count_tol)
        if title_units == 0:
            count_note = "표제부 세대/호수 미제공 — 누락 교차검증 불가(전유부 집계만 신뢰)."
        elif count_match:
            count_note = f"표제부 {title_units}세대 ≤ 전유부 {n_units}호 — 세대 누락 없음(신뢰)."
        else:
            count_note = (f"표제부 {title_units}세대 > 전유부 {n_units}호 — 일부 세대 전유부 누락·대지권 "
                          "미등기 가능. 누락 세대의 지분이 나머지에 과대 배분됐을 수 있음(등기부 확인 권장).")

        return {
            "is_aggregate": True, "pnu": pnu,
            "plat_area_sqm": plat_r,
            "plat_area_pyeong": round(plat_area / PYEONG_SQM, 2) if plat_area else None,
            "unit_count": n_units,
            "title_unit_count": title_units or None,
            "total_exclusive_sqm": round(total_excl, 2),
            "building_name": (title or {}).get("building_name", ""),
            "main_purpose": (title or {}).get("main_purpose", ""),
            "units": result_units,
            # ── 법령 근거(가산) — 집합건물 대지지분(대지사용권) 산정의 규범 근거. ──
            #   special_parcel.legal_basis 패턴과 동일하게 verified 딥링크를 부착(소비처 옵셔널).
            "legal_refs": _condo_legal_refs(),
            "validation": {
                "sum_land_share_sqm": sum_share,
                "plat_area_sqm": plat_r,
                "sum_match": sum_match,         # 합계 일치(구성상 성립 — 정의 검증)
                "count_match": count_match,     # 세대수 교차검증(실제 실패 가능 — 누락 탐지)
                "count_note": count_note,
                "reliable": sum_match and count_match,
                "method": "전유면적 비례 배분(area-weighted). 합계는 정의상 대지면적과 일치하므로 정확성 증명이 "
                          "아니며, 표제부 세대수 교차검증으로 누락을 점검합니다. 정확 대지권비율(분모/분자)은 "
                          "등기부 대지권등록부에서 확인하세요.",
            },
        }

    async def analyze_by_address(self, address: str) -> dict[str, Any]:
        """주소/지번 → VWorld 지오코딩으로 PNU 확보 후 대지지분 분석."""
        from app.services.external_api.vworld_service import VWorldService
        geo = await VWorldService().geocode_address((address or "").strip())
        pnu = (geo or {}).get("pnu")
        if not pnu:
            return {"is_aggregate": False, "address": address,
                    "reason": "주소/지번 지오코딩 실패 — PNU 미확보. 정확한 주소로 보완하세요."}
        out = await self.analyze_by_pnu(str(pnu))
        out["address"] = address
        return out