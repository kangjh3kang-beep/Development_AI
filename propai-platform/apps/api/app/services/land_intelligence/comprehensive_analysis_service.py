"""종합 부지분석 서비스.

주소 하나만 입력하면 7개 카테고리 자동 분석 보고서를 생성.
기존 서비스(LandInfoService, OrdinanceService, MOLITService 등)를 재사용.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog

from app.services.land_intelligence.land_info_service import LandInfoService
from app.services.land_intelligence.ordinance_service import OrdinanceService
from app.services.zoning.far_incentive_calculator import calculate as calc_far_incentive
from app.services.feasibility.permit_validator import (
    DEVELOPMENT_TYPE_NAMES,
    PERMIT_COMPLEXITY,
    get_permitted_types,
)

logger = structlog.get_logger()

# ── 개발방식별 전용율 (전용면적 / 공급면적) ──
EXCLUSIVE_AREA_RATIO: dict[str, float] = {
    "M01": 0.75,  # 재개발 (공동주택)
    "M02": 0.75,  # 재건축 (공동주택)
    "M03": 0.65,  # 역세권개발
    "M04": 0.75,  # 지역주택조합
    "M05": 0.70,  # 임대협동조합
    "M06": 0.75,  # 일반분양 (공동주택)
    "M07": 0.60,  # 주상복합
    "M08": 0.55,  # 오피스텔
    "M09": 0.55,  # 지식산업센터
    "M10": 0.85,  # 단독주택
    "M11": 0.85,  # 전원주택
    "M12": 0.80,  # 타운하우스
    "M13": 0.65,  # 도시형생활주택
    "M14": 0.70,  # 공공임대
    "M15": 0.75,  # 민간리츠
}

# ── 개발방식별 평균 전용면적 (m2) ──
AVG_EXCLUSIVE_AREA: dict[str, float] = {
    "M01": 84, "M02": 84, "M03": 59, "M04": 84, "M05": 49,
    "M06": 84, "M07": 102, "M08": 28, "M09": 50, "M10": 165,
    "M11": 200, "M12": 130, "M13": 26, "M14": 59, "M15": 84,
}

# ── 개발방식별 주차 기준 ──
PARKING_RULES: dict[str, dict[str, Any]] = {
    "M01": {"method": "per_unit", "ratio": 1.0},
    "M02": {"method": "per_unit", "ratio": 1.0},
    "M03": {"method": "per_unit", "ratio": 1.0},
    "M04": {"method": "per_unit", "ratio": 1.0},
    "M05": {"method": "per_unit", "ratio": 0.7},
    "M06": {"method": "per_unit", "ratio": 1.0},
    "M07": {"method": "per_unit", "ratio": 1.0},
    "M08": {"method": "per_sqm", "basis_sqm": 150},  # 150m2당 1대
    "M09": {"method": "per_sqm", "basis_sqm": 134},
    "M10": {"method": "per_unit", "ratio": 1.0},
    "M11": {"method": "per_unit", "ratio": 1.0},
    "M12": {"method": "per_unit", "ratio": 2.0},
    "M13": {"method": "per_unit", "ratio": 0.5},  # 도시형: 세대당 0.5대
    "M14": {"method": "per_unit", "ratio": 0.7},
    "M15": {"method": "per_unit", "ratio": 1.0},
}

# ── 개발방식별 일반적 용적률 ──
TYPICAL_FAR: dict[str, float] = {
    "M01": 250, "M02": 300, "M03": 400, "M04": 250, "M05": 200,
    "M06": 250, "M07": 400, "M08": 500, "M09": 400, "M10": 100,
    "M11": 80, "M12": 150, "M13": 300, "M14": 250, "M15": 300,
}

# ── 개발방식별 분양가 보정계수 ──
SALE_PRICE_MULTIPLIER: dict[str, float] = {
    "M01": 1.0, "M02": 1.0, "M04": 0.95, "M06": 1.0,
    "M07": 1.1, "M08": 0.8, "M09": 0.65,
    "M10": 1.1, "M11": 0.75, "M12": 1.05, "M13": 0.7,
    "M14": 0.85, "M15": 1.0,
}

# ── 시군구별 기준 분양가 (만원/평) ──
SIGUNGU_BASE_PRICES: dict[str, int] = {
    "강남구": 5500, "서초구": 5000, "송파구": 4500, "용산구": 4000,
    "마포구": 3500, "성동구": 3200, "영등포구": 3000,
    "강동구": 3000, "동작구": 2800, "광진구": 2800,
    "관악구": 2500, "구로구": 2200, "금천구": 2000,
    "노원구": 2200, "도봉구": 2000, "중랑구": 2200, "강북구": 2000,
    "성남시": 3500, "분당": 4000, "판교": 4500,
    "수원시": 2200, "용인시": 2000, "화성시": 1800,
    "고양시": 2000, "일산": 2200,
    "의정부시": 1400, "남양주시": 1600, "구리시": 2200,
    "파주시": 1200, "양주시": 1100,
    "안양시": 2500, "안산시": 1500, "시흥시": 1400,
    "김포시": 1600, "광명시": 2800, "하남시": 3000,
    "부천시": 2000, "광주시": 1500,
    "해운대구": 2800, "수영구": 2500,
    "연수구": 2500, "송도": 2800,
}

REGION_BASE_PRICES: dict[str, int] = {
    "서울특별시": 3000, "서울": 3000,
    "경기도": 1800, "경기": 1800,
    "인천광역시": 1800, "인천": 1800,
    "부산광역시": 2000, "부산": 2000,
    "대구광역시": 1800, "대전광역시": 1700,
    "광주광역시": 1500, "울산광역시": 1600,
    "세종특별자치시": 1800, "제주특별자치도": 1500,
}

# ── 공사비 기준단가 (원/m2, 2026 기준) ──
CONSTRUCTION_COST_PER_SQM: dict[str, int] = {
    "M01": 2_400_000, "M02": 2_400_000, "M03": 2_500_000,
    "M04": 2_400_000, "M05": 2_200_000, "M06": 2_400_000,
    "M07": 2_600_000, "M08": 2_600_000, "M09": 2_200_000,
    "M10": 2_100_000, "M11": 2_100_000, "M12": 2_000_000,
    "M13": 2_300_000, "M14": 2_200_000, "M15": 2_400_000,
}


class ComprehensiveAnalysisService:
    """주소 입력만으로 7개 분석 카테고리를 자동 수행."""

    def __init__(self) -> None:
        self.land_info = LandInfoService()

    async def analyze(self, address: str) -> dict[str, Any]:
        logger.info("종합분석 시작", address=address[:30])

        # Phase 1: 기본 데이터 수집 (LandInfoService 재사용)
        base = await self.land_info.collect_comprehensive(address)

        zone_type = base.get("zone_type", "")
        land_area = 0.0
        lr = base.get("land_register")
        if isinstance(lr, dict):
            land_area = float(lr.get("area_sqm", 0) or 0)

        # Phase 2: 7개 분석 섹션 + 법적 검증 + FAR 최적화
        sec1 = self._calc_effective_far(base, zone_type, land_area)
        effective_far = sec1["effective_far_pct"]
        effective_bcr = sec1["effective_bcr_pct"]

        sec2 = self._calc_supply_areas(zone_type, land_area, effective_far, effective_bcr)
        sec3 = self._calc_land_prices(base, land_area)
        sec5 = self._calc_sale_prices(address, zone_type)

        # 비동기 섹션
        sec4, sec6 = {}, {}
        try:
            sec4_task = self._research_transactions(base)
            sec6_task = self._analyze_location(base)
            sec4, sec6 = await asyncio.gather(sec4_task, sec6_task, return_exceptions=True)
            if isinstance(sec4, Exception):
                sec4 = {"error": str(sec4)}
            if isinstance(sec6, Exception):
                sec6 = {"error": str(sec6)}
        except Exception:
            pass

        sec7 = self._research_dev_plans(base)

        return {
            "address": address,
            "pnu": base.get("pnu"),
            "zone_type": zone_type,
            "land_area_sqm": land_area,
            "effective_far": sec1,
            "supply_areas": sec2,
            "land_prices": sec3,
            "transaction_prices": sec4,
            "sale_prices": sec5,
            "location": sec6,
            "development_plans": sec7,
            "analyzed_at": datetime.now().isoformat(),
            "warnings": base.get("warnings", []),
        }

    # ────────────────────────────────────────────
    # Section 1: 실효용적률 산정
    # ────────────────────────────────────────────
    def _calc_effective_far(self, base: dict, zone_type: str, land_area: float = 0) -> dict[str, Any]:
        ordinance = base.get("local_ordinance") or {}
        zone_limits = base.get("zone_limits") or {}

        national_bcr = float(zone_limits.get("max_bcr_pct", zone_limits.get("bcr", 60)))
        national_far = float(zone_limits.get("max_far_pct", zone_limits.get("far", 200)))
        ordinance_bcr = float(ordinance.get("effective_bcr") or ordinance.get("ordinance_bcr") or national_bcr)
        ordinance_far = float(ordinance.get("effective_far") or ordinance.get("ordinance_far") or national_far)
        effective_bcr = min(national_bcr, ordinance_bcr)
        effective_far = min(national_far, ordinance_far)

        incentive: dict[str, Any] = {}
        try:
            incentive = calc_far_incentive(
                zone_type=zone_type,
                ordinance_far=effective_far,
                donation_ratio_pct=0.0,
                national_far=national_far,
            )
        except Exception:
            pass

        return {
            "national_bcr_pct": national_bcr,
            "national_far_pct": national_far,
            "ordinance_bcr_pct": ordinance_bcr,
            "ordinance_far_pct": ordinance_far,
            "effective_bcr_pct": effective_bcr,
            "effective_far_pct": effective_far,
            "far_incentive": incentive,
            "source": ordinance.get("source", "법정상한"),
            "far_optimization": self._simulate_far_optimization(zone_type, effective_far, national_far, land_area),
        }

    def _simulate_far_optimization(
        self, zone_type: str, effective_far: float, national_far: float, land_area: float,
    ) -> dict[str, Any]:
        try:
            from app.services.zoning.far_optimization_simulator import simulate_far_scenarios
            return simulate_far_scenarios(
                zone_type=zone_type,
                ordinance_far=effective_far,
                national_far=national_far,
                land_area_sqm=land_area,
            )
        except Exception:
            return {}

    # ────────────────────────────────────────────
    # Section 2: 개발방식별 적정공급면적 산정
    # ────────────────────────────────────────────
    def _calc_supply_areas(
        self,
        zone_type: str,
        land_area: float,
        effective_far: float,
        effective_bcr: float,
    ) -> list[dict[str, Any]]:
        permitted = get_permitted_types(zone_type)
        results = []

        for dev_type in permitted:
            type_name = DEVELOPMENT_TYPE_NAMES.get(dev_type, dev_type)
            exclusive_ratio = EXCLUSIVE_AREA_RATIO.get(dev_type, 0.75)
            avg_exclusive = AVG_EXCLUSIVE_AREA.get(dev_type, 84)
            typical_far = TYPICAL_FAR.get(dev_type, 250)

            applied_far = min(effective_far, typical_far)
            total_gfa = land_area * (applied_far / 100)
            supply_area_per_unit = avg_exclusive / exclusive_ratio
            unit_count = max(1, int(total_gfa / supply_area_per_unit)) if supply_area_per_unit > 0 else 1
            building_area = land_area * (effective_bcr / 100)
            floor_count = max(1, round(total_gfa / building_area)) if building_area > 0 else 1

            parking = self._calc_parking(dev_type, unit_count, total_gfa)
            construction_cost = CONSTRUCTION_COST_PER_SQM.get(dev_type, 2_400_000)

            results.append({
                "dev_type": dev_type,
                "type_name": type_name,
                "exclusive_ratio_pct": round(exclusive_ratio * 100, 1),
                "avg_exclusive_area_sqm": avg_exclusive,
                "avg_exclusive_area_pyeong": round(avg_exclusive / 3.305785, 1),
                "supply_area_per_unit_sqm": round(supply_area_per_unit, 1),
                "supply_area_per_unit_pyeong": round(supply_area_per_unit / 3.305785, 1),
                "applied_far_pct": applied_far,
                "total_gfa_sqm": round(total_gfa, 1),
                "total_gfa_pyeong": round(total_gfa / 3.305785, 1),
                "unit_count": unit_count,
                "building_area_sqm": round(building_area, 1),
                "floor_count": floor_count,
                "parking_count": parking,
                "construction_cost_per_sqm": construction_cost,
                "estimated_construction_cost_won": int(total_gfa * construction_cost),
                "permit_complexity": PERMIT_COMPLEXITY.get(dev_type, 3),
                "project_months": self._project_months(dev_type),
                **self._validate_feasibility(
                    dev_type, type_name, zone_type, land_area,
                    effective_far, effective_bcr, unit_count, total_gfa, floor_count,
                ),
            })

        return sorted(results, key=lambda x: x["permit_complexity"])

    def _validate_feasibility(
        self, dev_type: str, type_name: str, zone_type: str,
        land_area: float, effective_far: float, effective_bcr: float,
        unit_count: int, total_gfa: float, floor_count: int,
    ) -> dict[str, Any]:
        try:
            from app.services.zoning.development_feasibility_validator import validate_development_feasibility
            result = validate_development_feasibility(
                dev_type=dev_type, type_name=type_name, zone_type=zone_type,
                land_area=land_area, effective_far=effective_far, effective_bcr=effective_bcr,
                unit_count=unit_count, total_gfa=total_gfa, floor_count=floor_count,
            )
            return result.to_dict()
        except Exception:
            return {"feasibility_status": "조건부", "conditions_met": [], "blocking_issues": [], "recommendations": []}

    def _calc_parking(self, dev_type: str, unit_count: int, total_gfa: float) -> int:
        rule = PARKING_RULES.get(dev_type, {"method": "per_unit", "ratio": 1.0})
        if rule["method"] == "per_unit":
            return max(1, round(unit_count * rule["ratio"]))
        return max(1, round(total_gfa / rule["basis_sqm"]))

    def _project_months(self, dev_type: str) -> int:
        months = {
            "M01": 60, "M02": 60, "M03": 48, "M04": 48, "M05": 36,
            "M06": 36, "M07": 42, "M08": 30, "M09": 36, "M10": 12,
            "M11": 12, "M12": 24, "M13": 24, "M14": 36, "M15": 48,
        }
        return months.get(dev_type, 36)

    # ────────────────────────────────────────────
    # Section 3: 토지 주변시세
    # ────────────────────────────────────────────
    def _calc_land_prices(self, base: dict, land_area: float) -> dict[str, Any]:
        prices = base.get("official_prices", [])
        latest = prices[0] if prices else {}
        price_per_sqm = int(latest.get("price_per_sqm", 0) or 0)

        lr = base.get("land_register") or {}
        if not price_per_sqm:
            price_per_sqm = int(lr.get("official_price_per_sqm", 0) or 0)

        market_multiplier = 1.2
        estimated_market = int(price_per_sqm * market_multiplier)

        return {
            "official_price_per_sqm": price_per_sqm,
            "official_price_per_pyeong": int(price_per_sqm * 3.305785),
            "total_official_value_won": int(price_per_sqm * land_area),
            "estimated_market_per_sqm": estimated_market,
            "estimated_market_per_pyeong": int(estimated_market * 3.305785),
            "total_estimated_value_won": int(estimated_market * land_area),
            "market_multiplier": market_multiplier,
            "source": "VWORLD 개별공시지가 + 시세보정",
        }

    # ────────────────────────────────────────────
    # Section 4: 물건별 주변 실거래가
    # ────────────────────────────────────────────
    async def _research_transactions(self, base: dict) -> dict[str, Any]:
        existing = base.get("nearby_transactions")
        if isinstance(existing, dict) and existing:
            return existing

        pnu = base.get("pnu", "")
        if len(pnu) >= 5:
            lawd_cd = pnu[:5]
        else:
            return {"message": "PNU 부재로 실거래가 조회 불가"}

        try:
            from app.services.external_api.molit_service import MOLITService
            molit = MOLITService()
            from datetime import datetime as dt
            ym = dt.now().strftime("%Y%m")

            tasks = {
                "아파트": molit.get_apt_transactions(lawd_cd, ym),
            }
            if hasattr(molit, "get_officetel_transactions"):
                tasks["오피스텔"] = molit.get_officetel_transactions(lawd_cd, ym)
            if hasattr(molit, "get_villa_transactions"):
                tasks["연립다세대"] = molit.get_villa_transactions(lawd_cd, ym)

            keys = list(tasks.keys())
            raw_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

            result: dict[str, Any] = {}
            for i, key in enumerate(keys):
                raw = raw_results[i]
                if isinstance(raw, Exception) or not isinstance(raw, list):
                    result[key] = {"count": 0, "items": []}
                    continue
                items = raw[:10]
                amounts = [int(item.get("거래금액", "0").replace(",", "").strip() or 0) for item in raw if item.get("거래금액")]
                result[key] = {
                    "count": len(raw),
                    "avg_price_10k": int(sum(amounts) / len(amounts)) if amounts else 0,
                    "max_price_10k": max(amounts) if amounts else 0,
                    "min_price_10k": min(amounts) if amounts else 0,
                    "items": items,
                }
            return result
        except Exception as e:
            logger.warning("실거래가 조회 실패", error=str(e))
            return {"error": str(e)}

    # ────────────────────────────────────────────
    # Section 5: 물건별 분양가
    # ────────────────────────────────────────────
    def _calc_sale_prices(self, address: str, zone_type: str) -> list[dict[str, Any]]:
        permitted = get_permitted_types(zone_type)
        base_price = self._get_base_price(address)

        results = []
        for dev_type in permitted:
            multiplier = SALE_PRICE_MULTIPLIER.get(dev_type, 1.0)
            price_man = int(base_price * multiplier)
            results.append({
                "dev_type": dev_type,
                "type_name": DEVELOPMENT_TYPE_NAMES.get(dev_type, dev_type),
                "sale_price_per_pyeong_man": price_man,
                "sale_price_per_sqm_man": int(price_man / 3.305785),
                "source": "지역 통계 기반 추정",
            })
        return results

    def _get_base_price(self, address: str) -> int:
        for sg, price in SIGUNGU_BASE_PRICES.items():
            if sg in address:
                return price
        for region, price in REGION_BASE_PRICES.items():
            if region in address:
                return price
        return 1500

    # ────────────────────────────────────────────
    # Section 6: 입지분석
    # ────────────────────────────────────────────
    async def _analyze_location(self, base: dict) -> dict[str, Any]:
        infra = base.get("infrastructure") or {}
        coords = base.get("coordinates") or {}
        address = base.get("address", "")

        subway = infra.get("nearest_subway")
        schools = infra.get("schools", [])

        score = 50
        if subway:
            dist = subway.get("distance_m", 9999)
            if dist < 300:
                score += 25
            elif dist < 500:
                score += 20
            elif dist < 1000:
                score += 10
        if len(schools) >= 3:
            score += 15
        elif len(schools) >= 1:
            score += 10

        return {
            "transportation": {
                "nearest_subway": subway,
                "subway_accessible": bool(subway and subway.get("distance_m", 9999) < 1000),
            },
            "education": {
                "schools": schools,
                "school_count": len(schools),
            },
            "coordinates": coords,
            "location_score": min(100, score),
            "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D",
        }

    # ────────────────────────────────────────────
    # Section 7: 주변 개발계획
    # ────────────────────────────────────────────
    def _research_dev_plans(self, base: dict) -> dict[str, Any]:
        districts = base.get("special_districts", [])
        land_use = base.get("land_use_plan")

        regulations = []
        if isinstance(land_use, dict):
            for d in land_use.get("districts", []):
                if isinstance(d, dict):
                    regulations.append(d.get("district_name", ""))
        elif isinstance(land_use, list):
            for d in land_use:
                if isinstance(d, dict):
                    regulations.append(d.get("district_name", ""))

        return {
            "special_districts": districts,
            "land_use_regulations": [r for r in regulations if r],
            "source": "VWORLD 토지이용계획",
        }
