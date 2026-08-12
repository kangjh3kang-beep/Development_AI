"""간편 분양성 조사 — **지번 하나**로 시세·개발호재·입지·분양사례를 한 화면에 모은다.

## 이 서비스가 하는 일과 하지 않는 일

★**새 분석엔진을 만들지 않는다.** 이 저장소의 규율(그린필드 금지)대로 기존 엔진 셋을 조립만 한다:

  - `MarketReportService.build_report` → 시세(trade/rent/apt_trend) · 입지(infrastructure) ·
    인구·소득(demographics) · **분양가 적정성(pricing_band)** · 서술(narrative)
  - `VWorldService.get_planning_facilities(kinds="all")` → **개발호재**(도시계획시설 계획결정)
  - `PresaleService.nearby` → **분양사례**(청약홈 인근 분양 공고)

## ★★이름과 내용의 정직한 경계 — 반드시 읽을 것

사용자 요청 이름은 "분양성 조사"다. 그런데 **분양성 판단의 핵심 지표 일부가 이 저장소에 없다**:

  · 청약 경쟁률   — 코드 전체 검색 0건(청약홈 API 연동은 분양가·상세까지만)
  · 미분양 통계   — 전용 서비스 없음(문자열은 LLM 인터프리터 안에만 = 서술용)
  · 흡수율        — 위 둘이 없으면 산출 불가

없는 것을 LLM 서술로 메우면 **정확히 이 저장소가 반복해서 데인 실패 형태**다(무목업·정직표기).
그래서 이 서비스는 **가진 것만 근거로 내고, 없는 것은 `unavailable` 로 드러낸다.**
`demand_indicators` 블록이 그 자리이며, 항상 존재하고 항상 사유를 담는다 —
**블록을 아예 빼면 "안 본 것"과 "없는 것"이 구분되지 않는다.**

## 왜 "간편"인가

전체 시장조사보고서는 무겁고 비동기 잡으로 돈다(`/api/v1/market/report/jobs` 가 그 증거다).
이 서비스는 **같은 엔진을 쓰되 표면을 좁혀** 한 화면 분량으로 요약한다 — 계산을 새로 하지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 개발호재 조회 반경(m). 도시계획시설은 광역 영향이라 실거래(주변시세)보다 넓게 본다.
CATALYST_RADIUS_M = 2000
# 분양사례 조회 반경(m)·기간(개월). 청약홈 공고는 건수가 적어 시세보다 넓고 길게 본다.
PRESALE_RADIUS_M = 3000
PRESALE_MONTHS_BACK = 12

# ★이 저장소에 **데이터원이 없는** 분양성 지표. 여기 적힌 것은 화면에 그대로 사유로 나간다.
#   새 데이터원을 붙이면 이 목록에서 빼고 실제 블록을 채운다(그때까지 추정으로 채우지 않는다).
_MISSING_DEMAND_INDICATORS: tuple[tuple[str, str], ...] = (
    ("청약경쟁률", "청약홈 연동이 분양가·공고상세까지만 — 경쟁률 엔드포인트 미연동"),
    ("미분양", "미분양 통계 데이터원 미연동"),
    ("흡수율", "경쟁률·미분양이 없어 산출 불가(추정값을 만들지 않는다)"),
)


def _summarize_catalysts(facilities: list[dict[str, Any]] | None) -> dict[str, Any]:
    """도시계획시설 목록을 **개발호재 블록**으로 요약한다.

    ★"호재"라고 단정하지 않는다 — 도시계획시설 계획결정은 **사실**이고, 그것이 호재인지는
      사업 성격에 따라 다르다(예: 변전소·폐기물처리시설은 오히려 기피시설이다).
      그래서 필드명을 `planned_facilities` 로 두고, 화면 문구도 "계획 고시된 시설"로 쓴다.
    """
    rows = [f for f in (facilities or []) if isinstance(f, dict)]
    if not rows:
        return {
            "available": False,
            "count": 0,
            "items": [],
            "note": "반경 내 도시계획시설 계획결정 없음(또는 조회 실패) — 미확보",
        }
    # 가까운 순으로 보여준다. 거리 미상은 뒤로.
    rows.sort(key=lambda r: (r.get("distance_m") is None, r.get("distance_m") or 0))
    return {
        "available": True,
        "count": len(rows),
        "items": rows[:20],
        "radius_m": CATALYST_RADIUS_M,
        "source": "vworld_도시계획시설",
    }


def _summarize_presale(nearby: dict[str, Any] | None) -> dict[str, Any]:
    """청약홈 인근 분양 공고를 **분양사례 블록**으로 요약한다."""
    data = nearby if isinstance(nearby, dict) else {}
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]
    if not data.get("available") or not items:
        # ★사유를 **실제 원인에 맞춰** 고른다. 상위가 준 note 를 그대로 쓰면 어긋난다 —
        #   실측에서 상위 조회가 실패했는데 사유는 "중심좌표 없음"으로 나왔다(라이브 1차).
        #   사유가 원인과 다르면 다음 사람이 엉뚱한 데를 본다(CLAUDE.md §C-10).
        if not isinstance(nearby, dict):
            note = "분양 공고 조회 실패 — 미확보"
        elif not data.get("available"):
            note = data.get("note") or "청약홈 조회 결과 없음 — 미확보"
        else:
            note = "반경·기간 내 분양 공고 없음(조회는 성공)"
        return {"available": False, "count": 0, "items": [], "note": note}
    return {
        "available": True,
        "count": len(items),
        "items": items[:10],
        "radius_m": PRESALE_RADIUS_M,
        "months_back": PRESALE_MONTHS_BACK,
        "source": "청약홈(ApplyhomeInfoDetailSvc)",
    }


def _demand_indicators() -> dict[str, Any]:
    """분양성 **수요 지표**의 현재 상태 — 없는 것을 없다고 말하는 블록.

    ★항상 반환한다. 비어 있을 때 블록을 생략하면 화면에서 "안 본 것"과 "없는 것"이
      구분되지 않는다 — 이 저장소가 여러 번 데인 형태다.
    """
    return {
        "available": False,
        "missing": [{"name": n, "reason": r} for n, r in _MISSING_DEMAND_INDICATORS],
        "note": (
            "분양성의 수요 축(경쟁률·미분양·흡수율)은 **데이터원 미연동**이라 산출하지 않습니다. "
            "이 보고서는 공급·가격 축(주변시세·분양사례·분양가 적정성)에 근거합니다."
        ),
    }


def _compact_market(report: dict[str, Any]) -> dict[str, Any]:
    """전체 시장조사보고서에서 **간편 표면**만 뽑는다(재계산 없음).

    ★`.get` 으로만 접근한다 — 상위 엔진의 계약이 바뀌어도 이 조립이 터지지 않게.
      대신 무엇을 못 받았는지는 `sections_present` 로 **드러낸다**(조용한 결손 금지).
    """
    keys = ("trade", "rent", "apt_trend", "infrastructure", "demographics", "pricing_band")
    picked = {k: report.get(k) for k in keys}
    return {
        **picked,
        "zone_type": report.get("zone_type"),
        "official_price_per_sqm": report.get("official_price_per_sqm"),
        "coordinates": report.get("coordinates"),
        "months": report.get("months"),
        "narrative": report.get("narrative"),
        "sections_present": sorted(k for k, v in picked.items() if v),
        "sections_missing": sorted(k for k, v in picked.items() if not v),
    }


class QuickSalesSurveyService:
    """지번 1개 → 간편 분양성 조사 보고서(조립 전용)."""

    async def build(
        self,
        *,
        address: str,
        lawd_cd: str,
        pnu: str | None = None,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        from apps.api.app.services.market.market_report_service import MarketReportService

        report = await MarketReportService().build_report(
            address=address, lawd_cd=lawd_cd, pnu=pnu, use_llm=use_llm
        )
        coords = report.get("coordinates") or {}
        lat, lon = coords.get("lat"), coords.get("lon")

        # ★호재·분양사례는 **병렬**로 — 둘 다 외부 API 라 직렬이면 체감이 두 배가 된다.
        #   그리고 한쪽이 실패해도 나머지는 살린다(`return_exceptions=True`).
        catalysts_raw, presale_raw = await asyncio.gather(
            self._planning_facilities(lat, lon),
            self._nearby_presale(lat, lon, lawd_cd),
            return_exceptions=True,
        )
        if isinstance(catalysts_raw, BaseException):
            logger.warning("개발호재 조회 실패 — 미확보로 표기", exc_info=catalysts_raw)
            catalysts_raw = None
        if isinstance(presale_raw, BaseException):
            logger.warning("분양사례 조회 실패 — 미확보로 표기", exc_info=presale_raw)
            presale_raw = None

        return {
            "address": address,
            "lawd_cd": lawd_cd,
            "pnu": pnu,
            "generated_at": report.get("generated_at"),
            "market": _compact_market(report),
            "planned_facilities": _summarize_catalysts(catalysts_raw),
            "presale_cases": _summarize_presale(presale_raw),
            "demand_indicators": _demand_indicators(),
            # ★이 보고서가 무엇에 근거하는지 화면이 그대로 인용할 문장.
            "scope_note": (
                "간편 조사입니다 — 공급·가격 축(주변시세·분양사례·분양가 적정성)에 근거하며, "
                "수요 축(경쟁률·미분양·흡수율)은 데이터원 미연동으로 포함하지 않습니다."
            ),
        }

    async def _planning_facilities(
        self, lat: float | None, lon: float | None
    ) -> list[dict[str, Any]] | None:
        if lat is None or lon is None:
            return None
        from apps.api.app.services.external_api.vworld_service import VWorldService

        return await VWorldService().get_planning_facilities(
            lat=float(lat), lon=float(lon), radius_m=CATALYST_RADIUS_M, kinds="all"
        )

    async def _nearby_presale(
        self, lat: float | None, lon: float | None, lawd_cd: str
    ) -> dict[str, Any] | None:
        from apps.api.app.services.land_intelligence.presale_service import (
            PresaleService,
            area_from_lawd,
        )

        return await PresaleService().nearby(
            center_lat=float(lat) if lat is not None else None,
            center_lon=float(lon) if lon is not None else None,
            area=area_from_lawd(lawd_cd),
            radius_m=PRESALE_RADIUS_M,
            months_back=PRESALE_MONTHS_BACK,
        )
