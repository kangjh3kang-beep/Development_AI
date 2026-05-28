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
from ..external_api.building_registry_service import BuildingRegistryService
from ..zoning.auto_zoning_service import AutoZoningService
from .ordinance_service import OrdinanceService

logger = logging.getLogger(__name__)


# 조례 데이터: OrdinanceService가 법제처 API → 캐시DB → 법정상한 순으로 실시간 조회


class LandInfoService:
    """토지 기본정보 종합 수집 서비스."""

    def __init__(self):
        self.vworld = VWorldService()
        self.molit = MOLITService()
        self.building = BuildingRegistryService()
        self.zoning = AutoZoningService()
        self.ordinance = OrdinanceService()

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
            "building_info": None,
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

        # Phase 2: PNU 기반 상세정보 병렬 수집 (VWORLD NED + 공공데이터포털)
        pnu = result.get("pnu")
        if pnu:
            tasks = [
                self._fetch_land_register(pnu),
                self._fetch_land_use_plan(pnu),
                self._fetch_official_price(pnu),
                self._fetch_building_info(pnu),
            ]
            land_reg, land_use, price_data, bldg = await asyncio.gather(*tasks, return_exceptions=True)

            # 토지대장 정보
            if isinstance(land_reg, dict) and land_reg:
                result["land_register"] = land_reg

            # 토지이용계획 (VWORLD NED — 중첩 규제 전부 포함)
            if isinstance(land_use, list) and land_use:
                result["land_use_plan"] = {
                    "zone_type": result["zone_type"],
                    "zone_limits": result["zone_limits"],
                    "districts": land_use,
                    "regulations": self._extract_regulations_from_land_use(land_use),
                }

            # 개별공시지가 (VWORLD NED)
            if isinstance(price_data, dict) and price_data:
                result["official_prices"] = [price_data]
                # land_register에도 공시지가 반영
                if result.get("land_register"):
                    result["land_register"]["official_price_per_sqm"] = price_data.get("price_per_sqm", 0)

            # 건축물대장 (공공데이터포털)
            if isinstance(bldg, dict) and bldg:
                result["building_info"] = bldg

        # Phase 3: 지자체 조례 실시간 분석 (법제처 API → 캐시 → 법정상한)
        if result["zone_type"]:
            try:
                ordinance_result = await self.ordinance.get_ordinance_limits(
                    address, result["zone_type"]
                )
                result["local_ordinance"] = ordinance_result

                # 조례 실효값으로 zone_limits 업데이트
                if result["zone_limits"] and ordinance_result:
                    if ordinance_result.get("effective_bcr"):
                        result["zone_limits"]["ordinance_bcr_pct"] = ordinance_result["effective_bcr"]
                    if ordinance_result.get("effective_far"):
                        result["zone_limits"]["ordinance_far_pct"] = ordinance_result["effective_far"]
                    result["zone_limits"]["ordinance_source"] = ordinance_result.get("source", "")
                    result["zone_limits"]["ordinance_legal_basis"] = ordinance_result.get("legal_basis", "")
            except Exception as e:
                logger.warning("조례 분석 실패: %s (%s)", address, str(e))
                result["local_ordinance"] = None

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
            logger.warning("토지대장 조회 실패: %s (%s)", pnu, str(e))
            return None

    async def _fetch_land_use_plan(self, pnu: str) -> list[dict[str, Any]]:
        """토지이용계획 조회 (VWORLD NED — 중첩 규제 전부)."""
        try:
            return await self.vworld.get_land_use_plan(pnu)
        except Exception as e:
            logger.warning("토지이용계획 조회 실패: %s (%s)", pnu, str(e))
            return []

    async def _fetch_official_price(self, pnu: str) -> dict[str, Any] | None:
        """개별공시지가 조회 (VWORLD NED)."""
        try:
            return await self.vworld.get_individual_land_price(pnu, year=2025)
        except Exception as e:
            logger.warning("공시지가 조회 실패: %s (%s)", pnu, str(e))
            return None

    async def _fetch_building_info(self, pnu: str) -> dict[str, Any] | None:
        """건축물대장 조회 (공공데이터포털 건축HUB)."""
        try:
            return await self.building.get_building_by_pnu(pnu)
        except Exception as e:
            logger.warning("건축물대장 조회 실패: %s (%s)", pnu, str(e))
            return None

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

    def _extract_regulations_from_land_use(self, land_use_items: list[dict[str, Any]]) -> list[dict[str, str]]:
        """토지이용계획 응답에서 행위제한 정보를 추출.

        VWORLD NED getLandUseAttr 응답의 district_name에서 규제 키워드 매칭.
        """
        regulation_map = {
            "경관지구": "건축물 높이·형태·색채 제한 (국토계획법 제37조)",
            "미관지구": "건축물 형태·의장 제한",
            "고도지구": "건축물 높이 최고/최저 제한 (국토계획법 제37조)",
            "방화지구": "건축물 구조 제한 — 내화구조 의무 (건축법 제58조)",
            "보존지구": "건축행위 제한 (역사문화/생태계 보존)",
            "시설보호구역": "건축행위 제한 (군사시설/학교 보호)",
            "대공방어협조구역": "대공방어 관련 건축물 높이 제한",
            "개발제한구역": "건축행위 극히 제한 (그린벨트)",
            "자연환경보전지역": "건축행위 극히 제한",
            "농림지역": "농업·임업 외 건축 제한",
            "군사시설": "군사시설보호법에 의한 행위 제한",
            "상대보전": "개발행위 제한 (수도권정비계획법)",
        }
        regulations = []
        for item in land_use_items:
            name = item.get("district_name", "")
            if not name:
                continue
            matched = False
            for keyword, restriction in regulation_map.items():
                if keyword in name:
                    regulations.append({"name": name, "restriction": restriction})
                    matched = True
                    break
            if not matched and "지역" not in name and "도시" not in name:
                # 용도지역/도시지역은 규제가 아니므로 제외
                regulations.append({"name": name, "restriction": "관련 법규 확인 필요"})
        return regulations

