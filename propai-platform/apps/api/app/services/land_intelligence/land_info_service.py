"""토지 기본정보 종합 수집 서비스 (L3).

주소 입력으로부터 토지대장, 개별공시지가, 토지이용계획확인원,
실거래가, 건축물대장, 주변 인프라 정보를 자동 수집하는 통합 파이프라인.

데이터 소스:
- VWORLD: 필지정보, 용도지역/지구/구역, POI 검색(인프라)
- 국토부(MOLIT): 실거래가, 공시지가
- 건축HUB: 건축물대장 (용도, 구조, 연면적, 층수, 사용승인일)
- 자동용도지역감지: auto_zoning_service
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from ..external_api.vworld_service import VWorldService
from ..external_api.molit_service import MOLITService
from ..external_api.building_registry_service import BuildingRegistryService
from ..zoning.auto_zoning_service import AutoZoningService
from .ordinance_service import OrdinanceService

logger = logging.getLogger(__name__)


# 조례 데이터: OrdinanceService가 법제처 API → 캐시DB → 법정상한 순으로 실시간 조회


class LandInfoService:
    """토지 기본정보 종합 수집 서비스 (L3)."""

    def __init__(self):
        self.vworld = VWorldService()
        self.molit = MOLITService()
        self.building = BuildingRegistryService()
        self.zoning = AutoZoningService()
        self.ordinance = OrdinanceService()

    async def collect_comprehensive(self, address: str, pnu: str | None = None) -> dict[str, Any]:
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
            nearby_transactions: {
                apt: {avg_price, max_price, min_price, count, items: [...]},
                land: {avg_price, max_price, min_price, count, items: [...]},
            },
            building_detail: {용도, 구조, 연면적, 층수, 사용승인일, ...},
            infrastructure: {
                nearest_subway: {name, distance_m},
                schools: [{name, type, distance_m}],
            },
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
            "building_detail": None,
            "official_prices": [],
            "land_use_plan": None,
            "local_ordinance": None,
            "nearby_transactions": None,
            "infrastructure": None,
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

        # 프론트엔드에서 전달된 PNU가 있으면 우선 사용 (VWORLD 서버 차단 우회)
        if pnu and not result.get("pnu"):
            result["pnu"] = pnu

        # Phase 2: PNU 기반 상세정보 병렬 수집 (VWORLD NED + 공공데이터포털)
        effective_pnu: str | None = result.get("pnu")
        if effective_pnu is not None:
            tasks = [
                self._fetch_land_register(effective_pnu),
                self._fetch_land_use_plan(effective_pnu),
                self._fetch_official_price(effective_pnu),
                self._fetch_building_info(effective_pnu),
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

        # Phase 2-B: 건축물대장 상세 정보 (용도, 구조, 연면적, 층수, 사용승인일)
        if effective_pnu is not None:
            try:
                bldg_detail = await self._fetch_building_detail(effective_pnu)
                if bldg_detail:
                    result["building_detail"] = bldg_detail
            except Exception as e:
                logger.warning("건축물대장 상세 조회 실패: %s (%s)", effective_pnu, str(e))

        # Phase 2-C: 인근 실거래가 수집 (MOLIT API — 반경 1km / 최근 1년)
        try:
            tx_summary = await self._fetch_nearby_transactions(address, effective_pnu)
            if tx_summary:
                result["nearby_transactions"] = tx_summary
        except Exception as e:
            result["warnings"].append(f"인근 실거래가 수집 실패: {str(e)}")

        # Phase 2-D: 주변 인프라 분석 (VWORLD POI — 지하철, 학교)
        coords = result.get("coordinates")
        if coords and coords.get("lat") and coords.get("lon"):
            try:
                infra = await self._fetch_infrastructure(
                    coords["lat"], coords["lon"]
                )
                if infra:
                    result["infrastructure"] = infra
            except Exception as e:
                result["warnings"].append(f"주변 인프라 분석 실패: {str(e)}")

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

    # ── L3 신규 메서드: 실거래가, 건축물대장 상세, 인프라 분석 ──

    async def _fetch_building_detail(self, pnu: str) -> dict[str, Any] | None:
        """건축물대장 상세정보 조회 (용도, 구조, 연면적, 층수, 사용승인일).

        BuildingRegistryService.get_building_by_pnu()를 호출하되,
        building_info와 별도로 정리된 상세 정보를 반환한다.
        """
        try:
            raw = await self.building.get_building_by_pnu(pnu)
            if not raw:
                return None
            return {
                "main_purpose": raw.get("main_purpose", ""),
                "structure": raw.get("structure", ""),
                "total_area_sqm": raw.get("total_area_sqm", 0),
                "building_area_sqm": raw.get("building_area_sqm", 0),
                "ground_floors": raw.get("ground_floors", 0),
                "underground_floors": raw.get("underground_floors", 0),
                "bcr_pct": raw.get("bcr_pct", 0),
                "far_pct": raw.get("far_pct", 0),
                "use_approval_date": raw.get("use_approval_date", ""),
                "building_name": raw.get("building_name", ""),
                "address": raw.get("address", ""),
                "road_address": raw.get("road_address", ""),
            }
        except Exception as e:
            logger.warning("건축물대장 상세 조회 실패: %s (%s)", pnu, str(e))
            return None

    async def _fetch_nearby_transactions(
        self, address: str, pnu: str | None = None,
    ) -> dict[str, Any] | None:
        """인근 실거래가 자동 수집 (MOLIT API).

        PNU 앞 5자리(법정동코드)를 추출하여 최근 1년간 아파트/토지 거래를 조회.
        평균, 최고, 최저 거래가 및 거래건수를 요약한다.
        """
        # PNU 앞 5자리 = 법정동코드 (lawd_cd)
        lawd_cd = self._extract_lawd_cd(address, pnu)
        if not lawd_cd:
            return None

        now = datetime.now()
        result: dict[str, Any] = {}

        # 최근 12개월 거래를 수집 (최근 3개월만 조회하여 API 부하 절감)
        for prop_type, label in [("apt", "apt"), ("land", "land")]:
            all_items: list[dict[str, Any]] = []
            for month_offset in range(3):
                year = now.year
                month = now.month - month_offset
                if month <= 0:
                    month += 12
                    year -= 1
                deal_ymd = f"{year}{month:02d}"
                try:
                    items = await self.molit.get_apt_transactions(lawd_cd, deal_ymd)
                    if isinstance(items, list):
                        all_items.extend(items)
                except Exception as e:
                    logger.debug("실거래 조회 (%s/%s): %s", prop_type, deal_ymd, str(e))

            if not all_items:
                result[label] = {
                    "avg_price_10k": 0,
                    "max_price_10k": 0,
                    "min_price_10k": 0,
                    "count": 0,
                    "items": [],
                }
                continue

            # 거래금액 파싱 (만원 단위)
            prices: list[int] = []
            for item in all_items:
                price_str = str(
                    item.get("거래금액", item.get("price_10k_won", "0"))
                ).replace(",", "").strip()
                try:
                    p = int(price_str)
                    if p > 0:
                        prices.append(p)
                except (ValueError, TypeError):
                    pass

            if prices:
                result[label] = {
                    "avg_price_10k": round(sum(prices) / len(prices)),
                    "max_price_10k": max(prices),
                    "min_price_10k": min(prices),
                    "count": len(prices),
                    "items": [
                        {
                            "price_10k": str(
                                item.get("거래금액", item.get("price_10k_won", "0"))
                            ).replace(",", "").strip(),
                            "area_sqm": item.get("전용면적", item.get("area_m2", "")),
                            "deal_date": f"{item.get('년', '')}.{item.get('월', '')}.{item.get('일', '')}",
                            "name": item.get("아파트", item.get("building_name", "")),
                            "floor": item.get("층", item.get("floor", "")),
                        }
                        for item in all_items[:10]  # 상위 10건만
                    ],
                }
            else:
                result[label] = {
                    "avg_price_10k": 0,
                    "max_price_10k": 0,
                    "min_price_10k": 0,
                    "count": 0,
                    "items": [],
                }

        return result if any(v.get("count", 0) > 0 for v in result.values()) else None

    async def _fetch_infrastructure(
        self, lat: float, lon: float,
    ) -> dict[str, Any] | None:
        """주변 인프라 분석 (VWORLD POI 검색 활용).

        - 최근접 지하철역 거리 (반경 1km)
        - 학군 정보 (반경 500m 학교)
        """
        import httpx
        from app.core.config import settings

        infra: dict[str, Any] = {
            "nearest_subway": None,
            "schools": [],
        }

        if not settings.VWORLD_API_KEY:
            return None

        headers = {"Referer": "https://developmentai-production.up.railway.app"}

        # 지하철역 검색 (반경 1km)
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                resp = await client.get(
                    f"{settings.VWORLD_BASE_URL}/req/search",
                    params={
                        "service": "search",
                        "request": "search",
                        "key": settings.VWORLD_API_KEY,
                        "query": "지하철역",
                        "type": "place",
                        "category": "교통시설",
                        "format": "json",
                        "size": "1",
                        "bbox": self._make_bbox(lat, lon, radius_m=1000),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("response", {}).get("result", {}).get("items", [])
                if items:
                    item = items[0]
                    station_lat = float(item.get("point", {}).get("y", 0))
                    station_lon = float(item.get("point", {}).get("x", 0))
                    dist_m = self._haversine_m(lat, lon, station_lat, station_lon)
                    infra["nearest_subway"] = {
                        "name": item.get("title", ""),
                        "distance_m": round(dist_m),
                    }
        except Exception as e:
            logger.debug("지하철역 검색 실패: %s", str(e))

        # 학교 검색 (반경 500m)
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                resp = await client.get(
                    f"{settings.VWORLD_BASE_URL}/req/search",
                    params={
                        "service": "search",
                        "request": "search",
                        "key": settings.VWORLD_API_KEY,
                        "query": "학교",
                        "type": "place",
                        "category": "교육시설",
                        "format": "json",
                        "size": "5",
                        "bbox": self._make_bbox(lat, lon, radius_m=500),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("response", {}).get("result", {}).get("items", [])
                for item in (items or []):
                    s_lat = float(item.get("point", {}).get("y", 0))
                    s_lon = float(item.get("point", {}).get("x", 0))
                    dist_m = self._haversine_m(lat, lon, s_lat, s_lon)
                    name = item.get("title", "")
                    # 학교 유형 추정
                    school_type = "기타"
                    if "초등" in name or "초교" in name:
                        school_type = "초등학교"
                    elif "중학" in name or "중교" in name:
                        school_type = "중학교"
                    elif "고등" in name or "고교" in name:
                        school_type = "고등학교"
                    elif "대학" in name:
                        school_type = "대학교"
                    infra["schools"].append({
                        "name": name,
                        "type": school_type,
                        "distance_m": round(dist_m),
                    })
        except Exception as e:
            logger.debug("학교 검색 실패: %s", str(e))

        has_data = infra["nearest_subway"] is not None or len(infra["schools"]) > 0
        return infra if has_data else None

    @staticmethod
    def _extract_lawd_cd(address: str, pnu: str | None) -> str | None:
        """주소 또는 PNU에서 법정동코드(5자리)를 추출."""
        # PNU 앞 5자리 = 시군구코드
        if pnu and len(pnu) >= 5:
            return pnu[:5]

        # 주소 기반 매핑 (서울 주요 구)
        district_map: dict[str, str] = {
            "강남": "11680", "서초": "11650", "송파": "11710", "강동": "11740",
            "마포": "11440", "용산": "11170", "성동": "11200", "광진": "11215",
            "동대문": "11230", "중랑": "11260", "성북": "11290", "강북": "11305",
            "도봉": "11320", "노원": "11350", "은평": "11380", "서대문": "11410",
            "종로": "11110", "중구": "11140", "동작": "11590", "관악": "11620",
            "영등포": "11560", "금천": "11545", "구로": "11530", "양천": "11500",
            "강서": "11500",
        }
        for district, code in district_map.items():
            if district in address:
                return code
        if "서울" in address:
            return "11680"  # 기본값 강남
        return None

    @staticmethod
    def _make_bbox(lat: float, lon: float, radius_m: int = 1000) -> str:
        """좌표 중심으로 radius_m 반경의 bbox 문자열 생성."""
        # 1도 ≈ 111,320m (위도), 경도는 위도에 따라 달라짐
        import math
        d_lat = radius_m / 111_320
        d_lon = radius_m / (111_320 * math.cos(math.radians(lat)))
        return f"{lon - d_lon},{lat - d_lat},{lon + d_lon},{lat + d_lat}"

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """두 좌표 간 거리(m) 계산 (Haversine 공식)."""
        import math
        R = 6_371_000  # 지구 반지름 (m)
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lam = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

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

