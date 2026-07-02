"""
자동 용도지역 감지 서비스.
주소 입력 -> PNU 자동 조회 -> 용도지역 감지 -> 건폐율/용적률/높이 한도 자동 매핑.
"""
import logging
import re
from typing import Any

from ..external_api.vworld_service import VWorldService

logger = logging.getLogger(__name__)

# 주소 키워드 추론 경고문(W-C) — 추론값이 실조회(NED 등)로 교체되면 소비자
# (land_info_service)가 이 문구를 식별해 제거한다(거짓 경고 잔존 방지).
ZONE_INFERENCE_WARNING = "용도지역이 주소 키워드 추론값입니다 — 실조회 확인 필요"

# 'OO역' 단어 경계 매칭 — '역삼동'·'2구역'·'OO지역'의 '역' 1글자 과민 매칭 방지.
#  · 앞에 한글 2자 이상('강남역'·'서울역'), 단 직전 글자가 구/지/권이면 제외
#    ('촉진구역'·'OO지역'·'역세권' 내부 매칭 차단 — 역세권은 키워드로 별도 처리)
#  · 뒤에 한글이 이어지면 제외('역삼동'·'광역시')
_STATION_RE = re.compile(r"[가-힣]{2,}(?<![구지권])역(?![가-힣])")

# '산 123'/'산123' 임야 지번 표기 — '부산'·'울산'·'안산'의 '산' 1글자 과민 매칭 방지.
_MOUNTAIN_LOT_RE = re.compile(r"산\s?\d")

# 용도지역별 법적 한도 (국토의 계획 및 이용에 관한 법률 제78조)
#  · max_height_m: 미터 단위 높이 제한(대부분 가로구역별 최고높이로 별도 관리 → None).
#  · max_floors: 층수 제한(★녹지지역). 국토계획법 시행령 별표 — 녹지지역 안에서 건축할 수
#    있는 건축물은 원칙적으로 4층 이하. 녹지가 아닌 지역은 층수 SSOT 제한이 없어 None.
#    이 값이 1곳(solar_envelope)에만 고립되어 '높이 제한없음'으로 표시되던 버그의 SSOT 정본.
ZONE_LIMITS = {
    # 시행령 84조 상한 50%
    "제1종전용주거지역": {"max_bcr": 50, "max_far": 100, "max_height_m": 10, "max_floors": None},
    "제2종전용주거지역": {"max_bcr": 50, "max_far": 150, "max_height_m": 12, "max_floors": None},
    "제1종일반주거지역": {"max_bcr": 60, "max_far": 200, "max_height_m": None, "max_floors": None},
    "제2종일반주거지역": {"max_bcr": 60, "max_far": 250, "max_height_m": None, "max_floors": None},
    "제3종일반주거지역": {"max_bcr": 50, "max_far": 300, "max_height_m": None, "max_floors": None},
    "준주거지역": {"max_bcr": 70, "max_far": 500, "max_height_m": None, "max_floors": None},
    "중심상업지역": {"max_bcr": 90, "max_far": 1500, "max_height_m": None, "max_floors": None},
    "일반상업지역": {"max_bcr": 80, "max_far": 1300, "max_height_m": None, "max_floors": None},
    "근린상업지역": {"max_bcr": 70, "max_far": 900, "max_height_m": None, "max_floors": None},
    "유통상업지역": {"max_bcr": 80, "max_far": 1100, "max_height_m": None, "max_floors": None},
    "전용공업지역": {"max_bcr": 70, "max_far": 300, "max_height_m": None, "max_floors": None},
    "일반공업지역": {"max_bcr": 70, "max_far": 350, "max_height_m": None, "max_floors": None},
    "준공업지역": {"max_bcr": 70, "max_far": 400, "max_height_m": None, "max_floors": None},
    # ★녹지지역: 건폐 20%·용적 80~100%이나 '4층 이하' 층수 제한이 더 강한 제약.
    #   자연녹지 현실 용적률 = 건폐 20%×4층 = 80%(법정 100%는 5층 필요 → 층수제한이 바인딩).
    "보전녹지지역": {"max_bcr": 20, "max_far": 80, "max_height_m": None, "max_floors": 4},
    "생산녹지지역": {"max_bcr": 20, "max_far": 100, "max_height_m": None, "max_floors": 4},
    "자연녹지지역": {"max_bcr": 20, "max_far": 100, "max_height_m": None, "max_floors": 4},
    # 관리지역·농림·자연환경보전 (시행령 84·85조) — 누락 시 해당 지역 법규검증이
    # 빈 결과(=통과로 보임)로 끝나는 문제가 있어 보완 (2026-06 리뷰 M-7)
    "보전관리지역": {"max_bcr": 20, "max_far": 80, "max_height_m": None, "max_floors": None},
    "생산관리지역": {"max_bcr": 20, "max_far": 80, "max_height_m": None, "max_floors": None},
    "계획관리지역": {"max_bcr": 40, "max_far": 100, "max_height_m": None, "max_floors": None},
    "농림지역": {"max_bcr": 20, "max_far": 80, "max_height_m": None, "max_floors": None},
    "자연환경보전지역": {"max_bcr": 20, "max_far": 80, "max_height_m": None, "max_floors": None},
    "역세권개발구역": {"max_bcr": 80, "max_far": 700, "max_height_m": None, "max_floors": None},
    "도시재생활성화구역": {"max_bcr": 80, "max_far": 500, "max_height_m": None, "max_floors": None},
}


def build_zone_limits(zone_key: str, limits: dict) -> dict:
    """ZONE_LIMITS 항목 → 표준 zone_limits 페이로드(공용 빌더, SSOT 단일경유).

    ★녹지지역 등 max_floors가 있고 max_height_m이 None이면 '실효 높이'(층수×기본층고
    3.0m)를 함께 산출해 전파한다 — 종합규제분석이 높이를 '제한 없음'으로 오표시하던
    버그를 출처(SSOT)에서 차단. 실효 높이는 층수×층고 근사값임을 height_basis로 정직 표기.
    """
    max_floors = limits.get("max_floors")
    max_height_m = limits.get("max_height_m")
    payload: dict = {
        "max_bcr_pct": limits["max_bcr"],
        "max_far_pct": limits["max_far"],
        "max_height_m": max_height_m,
        "max_floors": max_floors,
        "zone_key": zone_key,
        "legal_basis": "국토의 계획 및 이용에 관한 법률 제78조",
    }
    if max_height_m is None and max_floors:
        eff = round(max_floors * 3.0, 1)
        payload["effective_height_m"] = eff
        payload["height_basis"] = (
            f"국토계획법 시행령 별표 — 녹지지역 {max_floors}층 이하"
            f"(실효 높이≈{eff}m = {max_floors}층×3.0m 층고 근사)"
        )
    return payload


class AutoZoningService:
    def __init__(self):
        self.vworld = VWorldService()

    async def analyze_by_address(self, address: str) -> dict:
        """주소로부터 전체 부지 정보를 자동 수집."""
        result: dict[str, Any] = {
            "address": address,
            "pnu": None,
            "zone_type": None,
            # zone_type 출처 정직 표기(W-C): keyword_inference(주소 추론) /
            # vworld_land_info·vworld_land_use_plan·vworld_ned(실조회) / None(미확인)
            "zone_source": None,
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
                # 추론값 정직 표기(W-C): 실조회가 아님을 zone_source+경고로 명시.
                # 소비자(land_info_service)는 이 표식을 보고 NED 실값으로 덮어쓴다.
                result["zone_source"] = "keyword_inference"
                result["warnings"].append(ZONE_INFERENCE_WARNING)
                zone_key = self._normalize_zone_name(result["zone_type"])
                limits = ZONE_LIMITS.get(zone_key)
                if limits:
                    result["zone_limits"] = build_zone_limits(zone_key, limits)
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
                if result["zone_type"]:
                    # 실조회 출처 표기(W-C): 지적 속성(use_zone) vs 토지이용계획 문자열
                    result["zone_source"] = (
                        "vworld_land_info" if props.get("use_zone") else "vworld_land_use_plan"
                    )
                result["official_price_per_sqm"] = props.get("official_price")
        except Exception as e:
            result["warnings"].append(f"필지 정보 조회 실패: {str(e)}")

        # Step 2-B: 토지특성(NED) — 면적/용도지역/지목의 권위 소스로 보강.
        # 지적도(get_land_info)가 면적 0·용도지역 공란을 주는 필지를 정확히 채운다.
        if not result.get("land_area_sqm") or not result.get("zone_type"):
            try:
                lc = await self.vworld.get_land_characteristics(result["pnu"])
                if lc:
                    if not result.get("land_area_sqm") and lc.get("area_sqm"):
                        result["land_area_sqm"] = lc["area_sqm"]
                    if not result.get("zone_type") and lc.get("zone_type"):
                        result["zone_type"] = lc["zone_type"]
                        result["zone_source"] = "vworld_ned"
                    if not result.get("land_category") and lc.get("land_category"):
                        result["land_category"] = lc["land_category"]
                    if not result.get("official_price_per_sqm") and lc.get("official_price_per_sqm"):
                        result["official_price_per_sqm"] = lc["official_price_per_sqm"]
                    if lc.get("zone_type_2"):
                        result["zone_type_secondary"] = lc["zone_type_2"]
                    # 접도(도로접면) → 대표 도로폭(m). estimate_road_width_m 재사용(DRY·NED 실데이터).
                    # 시니어 심의 접도 CSP·건축법 44조 적합성 입력원(미확보 시 미설정·무목업).
                    road_side = lc.get("road_side")
                    if road_side:
                        # lazy import — land_info_service↔auto_zoning 순환참조 회피.
                        from ..land_intelligence.land_info_service import (
                            estimate_road_width_m,
                        )
                        result["road_side"] = road_side
                        rw = estimate_road_width_m(road_side)
                        if rw is not None:
                            result["road_width_m"] = rw
            except Exception as e:  # noqa: BLE001
                result["warnings"].append(f"토지특성 조회 실패: {str(e)}")

        # Step 3: 용도지역 -> 법적 한도 매핑
        if result["zone_type"]:
            zone_key = self._normalize_zone_name(result["zone_type"])
            limits = ZONE_LIMITS.get(zone_key)
            if limits:
                result["zone_limits"] = build_zone_limits(zone_key, limits)
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

    def _detect_zone_from_land_use(self, props: dict) -> str | None:
        """토지이용계획에서 용도지역 추출."""
        land_use_plan = props.get("land_use_plan", "")
        for zone_name in ZONE_LIMITS:
            if zone_name in land_use_plan:
                return zone_name
        return None

    def _detect_zone_from_address(self, address: str) -> str | None:
        """주소 키워드로 용도지역을 추론.

        VWORLD API 없이도 주소의 지역명으로 대략적인 용도지역을 판단한다.
        정확도는 낮지만, PNU 변환 실패 시 폴백으로 사용. 호출부는 반드시
        zone_source='keyword_inference'로 추론임을 표기한다(W-C).

        과민 규칙 완화(W-C ④): '역'·'산' 1글자 포함 매칭이 '역삼동'→상업,
        '부산'→녹지 같은 오판을 내던 것을 단어 경계로 강화 —
        'OO역'(_STATION_RE)·'역세권', '산 123' 임야 지번(_MOUNTAIN_LOT_RE)만 인정.
        """
        # 상업지역 키워드 — 'OO역'은 단어 경계 정규식으로만 매칭('역' 1글자 금지)
        if _STATION_RE.search(address) or any(
            kw in address for kw in ["역세권", "상가", "시장", "번화가", "명동", "종로"]
        ):
            return "일반상업지역"
        # 공업지역 키워드
        if any(kw in address for kw in ["공단", "산단", "공업", "지식산업"]):
            return "준공업지역"
        # 녹지지역 키워드 — '산'은 임야 지번 표기('산 123')만 인정('부산' 등 지명 오판 방지)
        if _MOUNTAIN_LOT_RE.search(address) or any(
            kw in address for kw in ["임야", "녹지", "자연"]
        ):
            return "자연녹지지역"
        # 기본: 일반주거지역 (한국 도시의 대부분) — None 반환은 다수 소비자
        # (precheck/feasibility/pipeline 등)가 zone_type 존재를 전제하므로 유지하되,
        # 호출부의 zone_source='keyword_inference' 표기로 추론임을 정직 공개한다.
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
