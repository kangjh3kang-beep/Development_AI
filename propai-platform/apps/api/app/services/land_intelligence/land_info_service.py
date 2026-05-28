"""토지 기본정보 종합 수집 서비스.

주소 입력으로부터 토지대장, 개별공시지가, 토지이용계획확인원 정보를
자동 수집하는 통합 파이프라인.

데이터 소스:
- VWORLD: 필지정보, 용도지역/지구/구역
- 국토부(MOLIT): 실거래가, 공시지가
- 자동용도지역감지: auto_zoning_service
"""

import asyncio
import logging
from typing import Any

from ..external_api.vworld_service import VWorldService
from ..external_api.molit_service import MOLITService
from ..zoning.auto_zoning_service import AutoZoningService, ZONE_LIMITS

logger = logging.getLogger(__name__)


# 지자체별 조례 건폐율/용적률 (법정 상한 이내 실효값)
# 향후 DB화 또는 법제처 API 연동 예정
LOCAL_ORDINANCE_DB: dict[str, dict[str, dict[str, float]]] = {
    "서울특별시": {
        "강남구": {"제2종일반주거지역": {"bcr": 60, "far": 200}, "제3종일반주거지역": {"bcr": 50, "far": 250}, "일반상업지역": {"bcr": 60, "far": 800}},
        "서초구": {"제2종일반주거지역": {"bcr": 60, "far": 200}, "제3종일반주거지역": {"bcr": 50, "far": 250}},
        "송파구": {"제2종일반주거지역": {"bcr": 60, "far": 200}},
        "마포구": {"제2종일반주거지역": {"bcr": 60, "far": 200}, "준주거지역": {"bcr": 60, "far": 400}},
        "영등포구": {"준공업지역": {"bcr": 60, "far": 400}},
        "성동구": {"준공업지역": {"bcr": 60, "far": 400}, "제2종일반주거지역": {"bcr": 60, "far": 200}},
    },
    "경기도": {
        "성남시": {"제2종일반주거지역": {"bcr": 60, "far": 220}},
        "수원시": {"제2종일반주거지역": {"bcr": 60, "far": 250}},
        "용인시": {"제2종일반주거지역": {"bcr": 60, "far": 200}},
        "화성시": {"제2종일반주거지역": {"bcr": 60, "far": 250}},
        "의정부시": {"제2종일반주거지역": {"bcr": 60, "far": 250}},
    },
}


class LandInfoService:
    """토지 기본정보 종합 수집 서비스."""

    def __init__(self):
        self.vworld = VWorldService()
        self.molit = MOLITService()
        self.zoning = AutoZoningService()

    async def collect_comprehensive(self, address: str) -> dict[str, Any]:
        """주소로부터 종합 토지정보를 수집한다.

        반환 구조:
        {
            address, pnu, coordinates,
            land_register: {지목, 면적, 소유구분, 이용상황, 도로접면, 지형},
            official_prices: [{year, price_per_sqm}],
            land_use_plan: {
                zone_type, zone_limits,
                districts: [{category, name}],
                regulations: [{name, restriction}]
            },
            local_ordinance: {sido, sigungu, ordinance_bcr, ordinance_far, effective_bcr, effective_far},
            special_districts: [...],
            warnings: [...]
        }
        """
        result: dict[str, Any] = {
            "address": address,
            "pnu": None,
            "coordinates": None,
            "land_register": None,
            "official_prices": [],
            "land_use_plan": None,
            "local_ordinance": None,
            "zone_type": None,
            "zone_limits": None,
            "special_districts": [],
            "warnings": [],
        }

        # Phase 1: 기본 용도지역 분석 (기존 서비스 활용)
        try:
            zoning_result = await self.zoning.analyze_by_address(address)
            result["pnu"] = zoning_result.get("pnu")
            result["coordinates"] = zoning_result.get("coordinates")
            result["zone_type"] = zoning_result.get("zone_type")
            result["zone_limits"] = zoning_result.get("zone_limits")
            result["special_districts"] = zoning_result.get("special_districts", [])
            result["warnings"] = zoning_result.get("warnings", [])

            # 기본 토지정보가 zoning에서 이미 조회됨
            if zoning_result.get("land_area_sqm"):
                result["land_register"] = {
                    "land_category": zoning_result.get("land_category", ""),
                    "area_sqm": zoning_result.get("land_area_sqm"),
                    "owner_type": "",
                    "land_use_situation": "",
                    "road_side": "",
                    "terrain": "",
                }
        except Exception as e:
            result["warnings"].append(f"기본 용도지역 분석 실패: {str(e)}")

        # Phase 2: PNU 기반 상세정보 병렬 수집
        pnu = result.get("pnu")
        if pnu:
            tasks = [
                self._fetch_land_register(pnu),
                self._fetch_land_use_districts(pnu),
                self._fetch_official_prices(pnu),
            ]
            land_reg, districts, prices = await asyncio.gather(*tasks, return_exceptions=True)

            # 토지대장 정보
            if isinstance(land_reg, dict) and land_reg:
                result["land_register"] = land_reg

            # 용도지구/구역
            if isinstance(districts, list):
                result["land_use_plan"] = {
                    "zone_type": result["zone_type"],
                    "zone_limits": result["zone_limits"],
                    "districts": districts,
                    "regulations": self._extract_regulations(districts),
                }

            # 공시지가 이력
            if isinstance(prices, list):
                result["official_prices"] = prices

        # Phase 3: 지자체 조례 분석
        if result["zone_type"]:
            result["local_ordinance"] = self._analyze_local_ordinance(
                address, result["zone_type"]
            )
            # 조례 실효값으로 zone_limits 업데이트
            if result["local_ordinance"] and result["zone_limits"]:
                ord_data = result["local_ordinance"]
                if ord_data.get("effective_bcr"):
                    result["zone_limits"]["ordinance_bcr_pct"] = ord_data["effective_bcr"]
                if ord_data.get("effective_far"):
                    result["zone_limits"]["ordinance_far_pct"] = ord_data["effective_far"]

        return result

    async def _fetch_land_register(self, pnu: str) -> dict[str, Any] | None:
        """토지대장 정보 조회 (VWORLD 필지정보 활용)."""
        try:
            land_info = await self.vworld.get_land_info(pnu)
            if not land_info:
                return None
            props = land_info.get("properties", {})
            return {
                "land_category": props.get("jimok", ""),
                "area_sqm": props.get("area", 0),
                "owner_type": props.get("owner_type", ""),
                "land_use_situation": props.get("land_use_situation", ""),
                "road_side": props.get("road_side", ""),
                "terrain": props.get("terrain", ""),
                "address": props.get("address", ""),
                "official_price_per_sqm": props.get("official_price", 0),
            }
        except Exception as e:
            logger.warning("토지대장 조회 실패", pnu=pnu, error=str(e))
            return None

    async def _fetch_land_use_districts(self, pnu: str) -> list[dict[str, Any]]:
        """용도지구/구역 목록 조회."""
        try:
            return await self.vworld.get_land_use_districts(pnu)
        except Exception as e:
            logger.warning("용도지구 조회 실패", pnu=pnu, error=str(e))
            return []

    async def _fetch_official_prices(self, pnu: str) -> list[dict[str, Any]]:
        """개별공시지가 이력 조회 (최근 5년)."""
        prices = []
        try:
            for year in range(2026, 2020, -1):
                try:
                    price_data = await self.molit.get_official_land_price(pnu)
                    if price_data:
                        prices.append({
                            "year": year,
                            "price_per_sqm": price_data if isinstance(price_data, (int, float)) else 0,
                        })
                        break  # 현재 API가 연도별 미지원이면 최신 1건만
                except Exception:
                    continue
        except Exception as e:
            logger.warning("공시지가 이력 조회 실패", pnu=pnu, error=str(e))
        return prices

    def _extract_regulations(self, districts: list[dict[str, Any]]) -> list[dict[str, str]]:
        """용도지구/구역에서 행위제한 정보를 추출."""
        regulation_map = {
            "경관지구": "건축물 높이·형태·색채 제한 (국토계획법 제37조)",
            "미관지구": "건축물 형태·의장 제한",
            "고도지구": "건축물 높이 최고/최저 제한 (국토계획법 제37조)",
            "방화지구": "건축물 구조 제한 — 내화구조 의무 (건축법 제58조)",
            "보존지구": "건축행위 제한 (역사문화/생태계 보존)",
            "시설보호구역": "건축행위 제한 (군사시설/학교 보호)",
            "개발제한구역": "건축행위 극히 제한 (그린벨트)",
            "자연환경보전지역": "건축행위 극히 제한",
            "농림지역": "농업·임업 외 건축 제한",
        }
        regulations = []
        for district in districts:
            name = district.get("name", "")
            for keyword, restriction in regulation_map.items():
                if keyword in name:
                    regulations.append({"name": name, "restriction": restriction})
                    break
            else:
                if name:
                    regulations.append({"name": name, "restriction": "해당 지구/구역 관련 법규 확인 필요"})
        return regulations

    def _analyze_local_ordinance(self, address: str, zone_type: str) -> dict[str, Any] | None:
        """지자체 조례 기반 건폐율/용적률 실효값 분석."""
        # 주소에서 시도/시군구 추출
        sido = None
        sigungu = None
        for s in LOCAL_ORDINANCE_DB:
            if s in address:
                sido = s
                break
        if not sido:
            return None

        for sg in LOCAL_ORDINANCE_DB.get(sido, {}):
            if sg in address:
                sigungu = sg
                break

        if not sigungu:
            return {"sido": sido, "sigungu": None, "effective_bcr": None, "effective_far": None, "note": "해당 시군구 조례 데이터 미보유"}

        zone_data = LOCAL_ORDINANCE_DB.get(sido, {}).get(sigungu, {}).get(zone_type)
        legal_limits = ZONE_LIMITS.get(zone_type, {})

        if zone_data:
            return {
                "sido": sido,
                "sigungu": sigungu,
                "legal_bcr": legal_limits.get("max_bcr"),
                "legal_far": legal_limits.get("max_far"),
                "ordinance_bcr": zone_data.get("bcr"),
                "ordinance_far": zone_data.get("far"),
                "effective_bcr": min(legal_limits.get("max_bcr", 100), zone_data.get("bcr", 100)),
                "effective_far": min(legal_limits.get("max_far", 1500), zone_data.get("far", 1500)),
                "legal_basis": f"{sido} {sigungu} 도시계획 조례",
            }
        return {
            "sido": sido,
            "sigungu": sigungu,
            "effective_bcr": legal_limits.get("max_bcr"),
            "effective_far": legal_limits.get("max_far"),
            "note": f"{sigungu}의 {zone_type} 조례 세부값 미보유 — 법정 상한 적용",
        }
