"""
자동 용도지역 감지 서비스.
주소 입력 -> PNU 자동 조회 -> 용도지역 감지 -> 건폐율/용적률/높이 한도 자동 매핑.
"""
import logging
from typing import Optional
from ..external_api.vworld_service import VWorldService

logger = logging.getLogger(__name__)

# 용도지역별 법적 한도 (국토의 계획 및 이용에 관한 법률 제78조)
ZONE_LIMITS = {
    "제1종전용주거지역": {"max_bcr": 40, "max_far": 100, "max_height_m": 10},
    "제2종전용주거지역": {"max_bcr": 50, "max_far": 150, "max_height_m": 12},
    "제1종일반주거지역": {"max_bcr": 60, "max_far": 200, "max_height_m": None},
    "제2종일반주거지역": {"max_bcr": 60, "max_far": 250, "max_height_m": None},
    "제3종일반주거지역": {"max_bcr": 50, "max_far": 300, "max_height_m": None},
    "준주거지역": {"max_bcr": 70, "max_far": 500, "max_height_m": None},
    "중심상업지역": {"max_bcr": 90, "max_far": 1500, "max_height_m": None},
    "일반상업지역": {"max_bcr": 80, "max_far": 1300, "max_height_m": None},
    "근린상업지역": {"max_bcr": 70, "max_far": 900, "max_height_m": None},
    "유통상업지역": {"max_bcr": 80, "max_far": 1100, "max_height_m": None},
    "전용공업지역": {"max_bcr": 70, "max_far": 300, "max_height_m": None},
    "일반공업지역": {"max_bcr": 70, "max_far": 350, "max_height_m": None},
    "준공업지역": {"max_bcr": 70, "max_far": 400, "max_height_m": None},
    "보전녹지지역": {"max_bcr": 20, "max_far": 80, "max_height_m": None},
    "생산녹지지역": {"max_bcr": 20, "max_far": 100, "max_height_m": None},
    "자연녹지지역": {"max_bcr": 20, "max_far": 100, "max_height_m": None},
    "역세권개발구역": {"max_bcr": 80, "max_far": 700, "max_height_m": None},
    "도시재생활성화구역": {"max_bcr": 80, "max_far": 500, "max_height_m": None},
}


class AutoZoningService:
    def __init__(self):
        self.vworld = VWorldService()

    async def analyze_by_address(self, address: str) -> dict:
        """주소로부터 전체 부지 정보를 자동 수집."""
        result = {
            "address": address,
            "pnu": None,
            "zone_type": None,
            "zone_limits": None,
            "land_area_sqm": None,
            "land_category": None,
            "official_price_per_sqm": None,
            "special_districts": [],
            "warnings": [],
        }

        # Step 1: 주소 -> PNU
        try:
            geocode = await self.vworld.geocode_address(address)
            if geocode:
                result["pnu"] = geocode.get("pnu")
                result["coordinates"] = {
                    "lat": geocode.get("lat"),
                    "lon": geocode.get("lon"),
                }
        except Exception:
            # VWORLD API 키 미설정 시 PNU 변환 불가 — 경고 없이 계속 진행
            pass

        # PNU 없어도 주소 키워드 기반으로 용도지역 분석 계속 진행
        if not result["pnu"]:
            # 주소에서 용도지역을 추론하여 기본 분석 제공
            result["zone_type"] = self._detect_zone_from_address(address)
            if result["zone_type"]:
                zone_key = self._normalize_zone_name(result["zone_type"])
                limits = ZONE_LIMITS.get(zone_key)
                if limits:
                    result["zone_limits"] = {
                        "max_bcr_pct": limits["max_bcr"],
                        "max_far_pct": limits["max_far"],
                        "max_height_m": limits["max_height_m"],
                        "zone_key": zone_key,
                        "legal_basis": "국토의 계획 및 이용에 관한 법률 제78조",
                    }
            result["special_districts"] = self._detect_special_districts(
                str(result.get("zone_type") or ""), address
            )
            return result

        # Step 2: PNU -> 필지 정보 (면적, 지목, 용도지역)
        try:
            land_info = await self.vworld.get_land_info(result["pnu"])
            if land_info:
                props = land_info.get("properties", {})
                result["land_area_sqm"] = props.get("area")
                result["land_category"] = props.get("jimok", "대")
                result["zone_type"] = props.get(
                    "use_zone"
                ) or self._detect_zone_from_land_use(props)
                result["official_price_per_sqm"] = props.get("official_price")
        except Exception as e:
            result["warnings"].append(f"필지 정보 조회 실패: {str(e)}")

        # Step 3: 용도지역 -> 법적 한도 매핑
        if result["zone_type"]:
            zone_key = self._normalize_zone_name(result["zone_type"])
            limits = ZONE_LIMITS.get(zone_key)
            if limits:
                result["zone_limits"] = {
                    "max_bcr_pct": limits["max_bcr"],
                    "max_far_pct": limits["max_far"],
                    "max_height_m": limits["max_height_m"],
                    "zone_key": zone_key,
                    "legal_basis": "국토의 계획 및 이용에 관한 법률 제78조",
                }
            else:
                result["warnings"].append(
                    f"'{result['zone_type']}' 용도지역의 법적 한도를 자동 매핑할 수 없습니다."
                )

        # Step 4: 특수구역 감지
        result["special_districts"] = self._detect_special_districts(
            result.get("zone_type", ""), address
        )

        return result

    def _normalize_zone_name(self, raw_zone: str) -> str:
        """VWORLD에서 반환된 용도지역명을 표준 키로 변환."""
        normalized = raw_zone.replace(" ", "").strip()
        # Try exact match first
        if normalized in ZONE_LIMITS:
            return normalized
        # Try partial match
        for key in ZONE_LIMITS:
            if key in normalized or normalized in key:
                return key
        return normalized

    def _detect_zone_from_land_use(self, props: dict) -> Optional[str]:
        """토지이용계획에서 용도지역 추출."""
        land_use_plan = props.get("land_use_plan", "")
        for zone_name in ZONE_LIMITS:
            if zone_name in land_use_plan:
                return zone_name
        return None

    def _detect_zone_from_address(self, address: str) -> Optional[str]:
        """주소 키워드로 용도지역을 추론.

        VWORLD API 없이도 주소의 지역명으로 대략적인 용도지역을 판단한다.
        정확도는 낮지만, PNU 변환 실패 시 폴백으로 사용.
        """
        # 상업지역 키워드
        if any(kw in address for kw in ["역", "상가", "시장", "번화가", "명동", "강남역", "종로"]):
            return "일반상업지역"
        # 공업지역 키워드
        if any(kw in address for kw in ["공단", "산단", "공업", "지식산업"]):
            return "준공업지역"
        # 녹지지역 키워드
        if any(kw in address for kw in ["산", "임야", "녹지", "자연"]):
            return "자연녹지지역"
        # 기본: 일반주거지역 (한국 도시의 대부분)
        return "제2종일반주거지역"

    def _detect_special_districts(self, zone_type: str, address: str) -> list:
        """특수구역 감지 (역세권, 도시재생 등)."""
        districts = []
        special_keywords = {
            "역세권": "역세권개발구역",
            "도시재생": "도시재생활성화구역",
            "재정비": "재정비촉진구역",
            "지구단위": "지구단위계획구역",
        }
        for keyword, district_name in special_keywords.items():
            if keyword in (zone_type or "") or keyword in address:
                districts.append(
                    {
                        "name": district_name,
                        "bonus_far": ZONE_LIMITS.get(district_name, {}).get(
                            "max_far"
                        ),
                    }
                )
        return districts
