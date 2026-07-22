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
import time
from datetime import datetime
from typing import Any

from ..data_validation.price_stats import robust_price_stats
from ..external_api.building_registry_service import BuildingRegistryService
from ..external_api.commercial_area_service import CommercialAreaService
from ..external_api.molit_service import MOLITService
from ..external_api.vworld_service import VWorldService
from ..zoning.auto_zoning_service import ZONE_INFERENCE_WARNING, AutoZoningService
from ..zoning.legal_zone_limits import _is_confirmed_ordinance_source
from .ordinance_service import OrdinanceService

logger = logging.getLogger(__name__)


def _strip_zone_inference_warning(warnings: list | None) -> list:
    """주소키워드 추론 경고 제거 — 실조회 값으로 교체된 뒤 거짓 경고 잔존 방지(W-C)."""
    return [w for w in (warnings or []) if w != ZONE_INFERENCE_WARNING]

# ── 종합 토지정보 인프로세스 TTL 캐시(Redis 비의존, 중복 외부호출 제거) ──
_COMP_CACHE: dict[str, tuple[float, dict]] = {}
_COMP_CACHE_TTL = 300.0  # 5분


def _comp_cache_get(key: str) -> dict | None:
    entry = _COMP_CACHE.get(key)
    if entry and (time.time() - entry[0]) < _COMP_CACHE_TTL:
        return entry[1]
    if entry:
        _COMP_CACHE.pop(key, None)
    return None


def _comp_cache_set(key: str, value: dict) -> None:
    _COMP_CACHE[key] = (time.time(), value)
    if len(_COMP_CACHE) > 64:  # 단순 상한
        oldest = min(_COMP_CACHE, key=lambda k: _COMP_CACHE[k][0])
        _COMP_CACHE.pop(oldest, None)


# 조례 데이터: OrdinanceService가 법제처 API → 캐시DB → 법정상한 순으로 실시간 조회


# ── 접도(도로접면) → 도로 너비 추정 ──
# 토지대장 '도로접면' 표준 분류를 대표 너비(m)로 환산한다.
# 출처: 부동산 가격공시 토지특성조사표 도로접면 구분.
_ROAD_SIDE_WIDTH_M: list[tuple[str, float]] = [
    ("광대로", 40.0),   # 광대한면/광대소각/광대세각 — 폭 25m 이상
    ("광대", 40.0),
    ("중로", 20.0),     # 중로한면/중로각지 — 폭 12~25m
    ("소로", 10.0),     # 소로한면/소로각지 — 폭 8~12m
    ("세로(가)", 6.0),  # 자동차 통행 가능 — 폭 4~8m
    ("세로가", 6.0),
    ("세로(불)", 3.0),  # 자동차 통행 불가 — 폭 < 4m
    ("세로불", 3.0),
    ("맹지", 0.0),      # 도로 없음
]


def estimate_road_width_m(road_side: str | None) -> float | None:
    """토지대장 '도로접면' 문자열로부터 대표 도로 너비(m)를 추정.

    매칭 실패 시 None을 반환하여 데이터 부재를 명확히 한다(보고서 "-" 표시).
    """
    if not road_side:
        return None
    text = road_side.replace(" ", "")
    # '세로(가)'와 '세로(불)'을 먼저 구분해야 하므로 긴 키부터 매칭
    for keyword, width in _ROAD_SIDE_WIDTH_M:
        if keyword.replace(" ", "") in text:
            return width
    return None


# ── 정밀 접도 (연속지적도 도로 필지 기하 측정) ──

def _haversine_m_pure(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 경위도 좌표 간 거리(m). 모듈 레벨 순수함수."""
    import math
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _mrr_short_side_m(geom) -> float | None:
    """폴리곤 최소회전사각형(MRR)의 짧은 변 길이(m) — 도로 필지의 폭.

    도로 필지는 보통 가늘고 긴 형태이므로 MRR의 짧은 변이 도로 폭에 해당한다.
    퇴화(점·선) 형상이면 None.
    """
    try:
        mrr = geom.minimum_rotated_rectangle
        xs, ys = mrr.exterior.coords.xy  # 닫힌 5점
    except Exception:
        return None
    if len(xs) < 4:
        return None
    s1 = _haversine_m_pure(ys[0], xs[0], ys[1], xs[1])
    s2 = _haversine_m_pure(ys[1], xs[1], ys[2], xs[2])
    short = min(s1, s2)
    return short if short > 0 else None


def compute_precise_road_width_m(
    subject_geom_json: dict,
    road_parcels: list[dict],
    adjacency_m: float = 3.0,
) -> float | None:
    """대상 필지에 인접한 도로 필지의 폭(m)을 측정.

    연속지적도에서 지목='도로'인 필지 중 대상 필지에 접한(거리 adjacency_m 이내)
    것들을 찾아, 그중 가장 넓은 도로의 폭을 반환한다. 주된 접도 도로가 개발
    가능성을 좌우하므로 최댓값을 채택한다. 측정 불가 시 None.
    """
    from shapely.geometry import shape

    try:
        subj = shape(subject_geom_json)
    except Exception:
        return None

    # 인접 판정 임계값을 도(degree) 단위로 환산 (위도 기준 근사)
    thr_deg = adjacency_m / 111_320.0

    best: float | None = None
    for rp in road_parcels:
        if "도로" not in (rp.get("jimok") or ""):
            continue
        try:
            rgeom = shape(rp["geometry"])
        except Exception:
            continue
        try:
            if subj.distance(rgeom) > thr_deg:
                continue
        except Exception:
            continue
        width = _mrr_short_side_m(rgeom)
        if width and (best is None or width > best):
            best = width

    return round(best, 1) if best else None


# ── 입지 점수화 ──
# 항목별 가중치(합 100). 거리가 가까울수록(또는 너비가 넓을수록) 높은 점수.
_LOCATION_WEIGHTS: dict[str, int] = {
    "subway": 25,      # 지하철 접근성
    "school": 15,      # 학군
    "hospital": 12,    # 의료
    "mart": 12,        # 대형마트
    "convenience": 8,  # 편의점
    "park": 10,        # 공원/녹지
    "bus": 8,          # 버스 접근성
    "road": 10,        # 접도(도로 너비)
}

# 거리 기반 항목: (full_score_거리m, zero_score_거리m). 선형 보간.
_LOCATION_DISTANCE_BANDS: dict[str, tuple[float, float]] = {
    "subway": (400, 2000),
    "school": (300, 1500),
    "hospital": (500, 3000),
    "mart": (500, 3000),
    "convenience": (200, 1000),
    "park": (400, 2000),
    "bus": (200, 800),
}


def _distance_score(distance_m: float | None, full_m: float, zero_m: float) -> float:
    """거리(m)를 0~1 점수로 선형 보간. 가까우면 1, 멀면 0."""
    if distance_m is None:
        return 0.0
    if distance_m <= full_m:
        return 1.0
    if distance_m >= zero_m:
        return 0.0
    return (zero_m - distance_m) / (zero_m - full_m)


def _road_score(road_width_m: float | None) -> float:
    """도로 너비(m)를 0~1 점수로 환산. 6m=0.5, 20m 이상=1.0, 맹지=0."""
    if road_width_m is None:
        return 0.0
    if road_width_m <= 0:
        return 0.0
    if road_width_m >= 20:
        return 1.0
    return min(1.0, road_width_m / 20.0)


def _nearest_distance(items: list[dict] | None) -> float | None:
    """POI 리스트에서 최근접 거리(m)를 반환."""
    if not items:
        return None
    dists = [
        i.get("distance_m") for i in items
        if isinstance(i, dict) and i.get("distance_m") is not None
    ]
    return min(dists) if dists else None


def compute_location_score(
    infra: dict[str, Any] | None, road_width_m: float | None = None
) -> dict[str, Any]:
    """수집된 인프라 + 접도 정보로 입지 점수(0~100)와 등급(A~E)을 산출.

    각 항목은 가중치 × 정규화 점수(0~1)로 합산한다. 데이터가 없는 항목은
    0점으로 처리되며, items에 '미수집'으로 표기되어 할루시네이션을 방지한다.
    레이더 차트용 항목별 점수(0~100)도 함께 반환한다.
    """
    infra = infra or {}

    # 항목별 최근접 거리 산출
    subway = infra.get("nearest_subway") or {}
    subway_dist = subway.get("distance_m") if isinstance(subway, dict) else None
    distances: dict[str, float | None] = {
        "subway": subway_dist,
        "school": _nearest_distance(infra.get("schools")),
        "hospital": _nearest_distance(infra.get("hospitals")),
        "mart": _nearest_distance(infra.get("marts")),
        "convenience": _nearest_distance(infra.get("convenience_stores")),
        "park": _nearest_distance(infra.get("parks")),
        "bus": _nearest_distance(infra.get("bus_stops")),
    }

    labels = {
        "subway": "지하철", "school": "학교", "hospital": "병원",
        "mart": "대형마트", "convenience": "편의점", "park": "공원",
        "bus": "버스", "road": "접도",
    }

    items: list[dict[str, Any]] = []
    total = 0.0
    for key, weight in _LOCATION_WEIGHTS.items():
        if key == "road":
            norm = _road_score(road_width_m)
            detail = f"{road_width_m:.0f}m" if road_width_m else "미수집"
        else:
            band = _LOCATION_DISTANCE_BANDS[key]
            dist = distances.get(key)
            norm = _distance_score(dist, band[0], band[1])
            detail = f"{round(dist)}m" if dist is not None else "미수집"
        score = weight * norm
        total += score
        items.append({
            "category": labels[key],
            "key": key,
            "score": round(norm * 100),   # 레이더용 0~100
            "weight": weight,
            "detail": detail,
        })

    total_score = round(total)
    if total_score >= 80:
        grade = "A"
    elif total_score >= 65:
        grade = "B"
    elif total_score >= 50:
        grade = "C"
    elif total_score >= 35:
        grade = "D"
    else:
        grade = "E"

    return {
        "total_score": total_score,
        "grade": grade,
        "items": items,
    }


class LandInfoService:
    """토지 기본정보 종합 수집 서비스 (L3)."""

    def __init__(self):
        self.vworld = VWorldService()
        self.molit = MOLITService()
        self.building = BuildingRegistryService()
        self.zoning = AutoZoningService()
        self.ordinance = OrdinanceService()
        self.commercial = CommercialAreaService()

    async def collect_comprehensive(self, address: str, pnu: str | None = None) -> dict[str, Any]:
        """종합 토지정보 수집 — 인프로세스 TTL 캐시(Redis 비의존)로 중복 호출 제거.

        한 번의 부지분석에서 동일 주소가 여러 번 수집되거나(파이프라인 이중호출) Redis가
        다운된 환경에서도 외부 API 중복 호출을 막아 지연을 크게 줄인다.
        """
        key = f"{(address or '').strip()}|{pnu or ''}"
        hit = _comp_cache_get(key)
        if hit is not None:
            return hit
        result = await self._collect_comprehensive_impl(address, pnu)
        if isinstance(result, dict) and result:
            _comp_cache_set(key, result)
        return result

    async def _collect_comprehensive_impl(self, address: str, pnu: str | None = None) -> dict[str, Any]:
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
            # zone_type 출처(W-C): keyword_inference(추론)/vworld_*(실조회)/None(미확인)
            "zone_source": None,
            "zone_limits": None,
            "special_districts": [],
            "warnings": [],
            # 분묘대장: 전국 단위 무료 공공API 미제공 → 정직 표기(가짜데이터 생성 금지)
            # TODO(후속): 디지털트윈 항공/위성 레이어 판독으로 분묘 후보지 시각 식별 연계
            "grave_registry": {
                "available": False,
                "reason": "전국 단위 무료 공공API 미제공",
                "suggestion": "현장조사·항공/위성 판독(디지털트윈 항공레이어) 또는 지자체 개별 확인 권장",
                "data_source": "unavailable",
            },
        }

        # Phase 1: 기본 용도지역 분석 (기존 서비스 활용)
        try:
            zoning_result = await self.zoning.analyze_by_address(address)
            result["pnu"] = zoning_result.get("pnu")
            result["coordinates"] = zoning_result.get("coordinates")
            result["zone_type"] = zoning_result.get("zone_type")
            result["zone_source"] = zoning_result.get("zone_source")
            result["zone_limits"] = zoning_result.get("zone_limits")
            result["special_districts"] = zoning_result.get("special_districts", [])
            result["warnings"] = zoning_result.get("warnings", [])

            # 기본 토지정보가 zoning에서 이미 조회됨
            if zoning_result.get("land_area_sqm"):
                # owner_type(소유구분)은 권위 소스인 토지대장(_fetch_land_register,
                # VWORLD LP_PA_CBND_BUBUN own_gbn_nm)이 Phase 2에서 채운다. 여기서는
                # zoning이 제공하면 사용하고, 없으면 정직하게 빈값 유지(무목업).
                result["land_register"] = {
                    "land_category": zoning_result.get("land_category", ""),
                    "area_sqm": zoning_result.get("land_area_sqm"),
                    "owner_type": zoning_result.get("owner_type", ""),
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
                self._fetch_land_characteristics(effective_pnu),
            ]
            land_reg, land_use, price_data, bldg, land_char = await asyncio.gather(
                *tasks, return_exceptions=True
            )

            # 토지특성(NED getLandCharacteristics) — 면적·지목·용도지역의 권위 소스.
            # 지적도(get_land_info)가 면적 0을 주거나 주소키워드 감지가 용도지역을
            # 놓친 필지를 정확히 보완한다.
            if isinstance(land_char, dict) and land_char:
                # 용도지역: AutoZoning이 못 찾았거나 '주소키워드 추론값'이면 토지특성
                # (NED 실조회)으로 채움/덮어쓰기 — 실조회 우선(W-C ②). 종전에는
                # 추론 선점값이 'not zone_type' 가드에 걸려 NED 실값을 영구 차단했다.
                zone_inferred = result.get("zone_source") == "keyword_inference"
                if land_char.get("zone_type") and (zone_inferred or not result.get("zone_type")):
                    result["zone_type"] = land_char["zone_type"]
                    result["zone_limits"] = self._zone_limits_for(land_char["zone_type"])
                    result["zone_source"] = "vworld_ned"
                    result["warnings"] = _strip_zone_inference_warning(result.get("warnings"))
                # 다용도(둘 이상 용도지역) 필지 표기
                if land_char.get("zone_type_2"):
                    result["zone_type_secondary"] = land_char["zone_type_2"]
                result["land_characteristics"] = land_char

            # 토지대장 정보 (지적도 기반)
            if isinstance(land_reg, dict) and land_reg:
                result["land_register"] = land_reg

            # 토지대장 면적/지목이 비었으면 토지특성으로 보강
            if isinstance(land_char, dict) and land_char:
                lr = result.get("land_register")
                if not isinstance(lr, dict):
                    lr = {}
                if not lr.get("area_sqm"):
                    lr["area_sqm"] = land_char.get("area_sqm", 0)
                if not lr.get("land_category"):
                    lr["land_category"] = land_char.get("land_category", "")
                if not lr.get("land_use_situation"):
                    lr["land_use_situation"] = land_char.get("land_use_situation", "")
                if not lr.get("road_side"):
                    lr["road_side"] = land_char.get("road_side", "")
                if not lr.get("terrain"):
                    lr["terrain"] = land_char.get("terrain_form", "")
                if not lr.get("official_price_per_sqm"):
                    lr["official_price_per_sqm"] = land_char.get("official_price_per_sqm", 0)
                lr.setdefault("address", address)
                result["land_register"] = lr
                # 최상위 land_area_sqm도 채움(프론트 표시 일원화)
                if not result.get("land_area_sqm") and land_char.get("area_sqm"):
                    result["land_area_sqm"] = land_char["area_sqm"]

            # 토지이용계획 (VWORLD NED — 중첩 규제 전부 포함)
            if isinstance(land_use, list) and land_use:
                # districts에서 확정된 용도지역으로 채움 — 추론 선점값(keyword_inference)도
                # 실조회(districts) 값으로 덮어쓴다(실조회 우선, W-C ②).
                zone_inferred = result.get("zone_source") == "keyword_inference"
                district_zone = self._zone_from_districts(land_use)
                if district_zone and (zone_inferred or not result.get("zone_type")):
                    result["zone_type"] = district_zone
                    result["zone_limits"] = self._zone_limits_for(district_zone)
                    result["zone_source"] = "vworld_ned_land_use"
                    result["warnings"] = _strip_zone_inference_warning(result.get("warnings"))
                lup_zone = result.get("zone_type") or district_zone
                result["land_use_plan"] = {
                    "zone_type": lup_zone,
                    "zone_limits": result.get("zone_limits"),
                    "districts": land_use,
                    "regulations": self._extract_regulations_from_land_use(land_use),
                }
                # ★토지이음 '지역지구별 규제법령집'을 법령엔진(진실원천)에 실시간 반영:
                #   fetch된 각 지역지구 designation → 관련 법령조문(law.go.kr verified 링크)으로 매핑.
                #   매핑 실패 designation은 unmatched로 정직 표기(가짜 링크 금지). 부착 실패는 무손상.
                try:
                    from app.services.legal.legal_reference_registry import (
                        legal_refs_for_districts,
                    )
                    _sigungu = (result.get("local_ordinance") or {}).get("sigungu")
                    _dlr = legal_refs_for_districts(land_use, sigungu=_sigungu)
                    result["land_use_plan"]["district_legal_refs"] = _dlr["refs"]
                    result["land_use_plan"]["district_legal_by_district"] = _dlr["by_district"]
                    if _dlr["unmatched"]:
                        result["land_use_plan"]["district_legal_unmatched"] = _dlr["unmatched"]
                except Exception:  # noqa: BLE001 — 규제법령집 부착 실패는 무손상(graceful)
                    pass

                # ★토지이음 '행위제한설명' 보강 — 도로조건(접도요건)·건축선(후퇴)·고시정보 deep-link.
                #   road_side(land_characteristics)·sigungu 기반 결정론 산출(무목업·근거기반).
                try:
                    from app.services.legal.tojieum_supplement import (
                        assess_road_conditions,
                        building_line_setback,
                        gosi_info,
                    )
                    _lc = result.get("land_characteristics") or {}
                    _road_side = _lc.get("road_side") or (result.get("land_register") or {}).get("road_side")
                    _sigungu2 = (result.get("local_ordinance") or {}).get("sigungu")
                    _sido2 = (result.get("local_ordinance") or {}).get("sido")
                    result["action_restriction_detail"] = {
                        "road_conditions": assess_road_conditions(_road_side),
                        "building_line": building_line_setback(_road_side),
                        "gosi_info": gosi_info(_sido2, _sigungu2),
                    }
                except Exception:  # noqa: BLE001 — 보강 실패는 무손상(graceful)
                    pass

                # ★혼재 용도지역(둘 이상 용도지역에 걸치는 대지) 면적가중 건폐/용적(국토계획법 제84조).
                #   zone_type_secondary가 있으면 두 용도지역의 한도를 면적가중 평가(면적 미확보 시 정직).
                try:
                    _sec = result.get("zone_type_secondary")
                    if _sec and result.get("zone_type") and _sec != result.get("zone_type"):
                        from app.services.zoning.legal_zone_limits import mixed_zone_limits
                        result["mixed_zone_assessment"] = mixed_zone_limits([
                            {"zone_type": result.get("zone_type")},
                            {"zone_type": _sec},
                        ])
                except Exception:  # noqa: BLE001 — 혼재 평가 실패는 무손상
                    pass

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

        # 건축물대장 조회 상태 — 프론트가 "확정 나대지"와 "조회불가(미승인)"를 구분하도록 신호.
        #   ok=건축물있음 / no_data=조회성공·무건축물(나대지) / unavailable=미승인·오류(확인불가) / no_key=키없음
        _bstatus = getattr(self.building, "last_status", "unknown")
        if result.get("building_info") or result.get("building_detail"):
            result["building_lookup_status"] = "ok"
        elif _bstatus == "no_data":
            result["building_lookup_status"] = "no_data"
        elif _bstatus == "no_key":
            result["building_lookup_status"] = "no_key"
        elif _bstatus in ("unauthorized", "error"):
            result["building_lookup_status"] = "unavailable"
        else:
            result["building_lookup_status"] = "unknown"

        # Phase 2-C: 인근 실거래가 수집 (MOLIT API — 반경 1km / 최근 1년)
        try:
            tx_summary = await self._fetch_nearby_transactions(address, effective_pnu)
            if tx_summary:
                result["nearby_transactions"] = tx_summary
        except Exception as e:
            result["warnings"].append(f"인근 실거래가 수집 실패: {str(e)}")

        # Phase 2-D: 접도 너비 — 정밀(연속지적도 도로필지 기하측정) 우선,
        # 실패 시 토지대장 도로접면 텍스트 추정으로 폴백.
        road_width_m: float | None = None
        road_width_source: str | None = None
        try:
            road_width_m = await self._fetch_precise_road_width(
                effective_pnu, result.get("coordinates")
            )
            if road_width_m is not None:
                road_width_source = "cadastral_road_parcel"
        except Exception as e:
            logger.warning("정밀 접도 분석 실패: %s (%s)", address, str(e))

        _lr_road = result.get("land_register") or {}
        if road_width_m is None and isinstance(_lr_road, dict):
            road_width_m = estimate_road_width_m(_lr_road.get("road_side"))
            if road_width_m is not None:
                road_width_source = "road_side_estimate"
        if road_width_m is not None and isinstance(_lr_road, dict):
            _lr_road["road_width_m"] = road_width_m
            _lr_road["road_width_source"] = road_width_source

        # Phase 2-E: 주변 인프라 분석 (VWORLD POI — 지하철/학교/병원/마트/편의점/공원/버스)
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

        # Phase 2-F: 입지 점수화 (인프라 + 접도 → 0~100 점수, A~E 등급)
        # 인프라 데이터가 전혀 없어도 접도 점수만으로 산출 가능하므로 항상 계산한다.
        try:
            location_score = compute_location_score(
                result.get("infrastructure"), road_width_m
            )
            if result.get("infrastructure") is None:
                result["infrastructure"] = {}
            result["infrastructure"]["location_score"] = location_score
            result["infrastructure"]["road_width_m"] = road_width_m
            result["infrastructure"]["road_width_source"] = road_width_source
        except Exception as e:
            logger.warning("입지 점수화 실패: %s (%s)", address, str(e))

        # Phase 3: 지자체 조례 실시간 분석 (법제처 API → 캐시 → 법정상한)
        if result["zone_type"]:
            try:
                ordinance_result = await self.ordinance.get_ordinance_limits(
                    address, result["zone_type"], pnu=effective_pnu,
                )
                result["local_ordinance"] = ordinance_result

                # 조례 실효값으로 zone_limits 업데이트
                # ★정직성 가드(2026-07-22 라이브 결함, live-fix①): ordinance_result["effective_*"]는
                #   조례 미확보(source="법정상한") 폴백 시에도 항상 채워진다(national_* 값 그대로).
                #   이를 무조건 ordinance_*_pct에 얹으면 legal_zone_limits._extract_ordinance_far가
                #   "명시적 조례 신호"로 오인해 far_basis_detail.조례값.confirmed=True로 승격시킨다
                #   (라이브 재현: 용인시 수지구 자연녹지 — 법정상한 100%가 조례값·확정으로 표시).
                #   project_pipeline._site_trust_adapter가 이미 쓰는 정답 패턴(source가 실제
                #   조례/법제처 확정출처일 때만 ordinance_*_pct 주입)을 여기도 동일 적용한다
                #   (무날조·정직표기 — 수치는 그대로, '확정' 오표기만 제거).
                if result["zone_limits"] and ordinance_result:
                    _ord_confirmed_src = _is_confirmed_ordinance_source(ordinance_result.get("source"))
                    if _ord_confirmed_src and ordinance_result.get("effective_bcr"):
                        result["zone_limits"]["ordinance_bcr_pct"] = ordinance_result["effective_bcr"]
                    if _ord_confirmed_src and ordinance_result.get("effective_far"):
                        result["zone_limits"]["ordinance_far_pct"] = ordinance_result["effective_far"]
                    result["zone_limits"]["ordinance_source"] = ordinance_result.get("source", "")
                    result["zone_limits"]["ordinance_legal_basis"] = ordinance_result.get("legal_basis", "")
            except Exception as e:
                logger.warning("조례 분석 실패: %s (%s)", address, str(e))
                result["local_ordinance"] = None

        # Phase 4: 실효용적률 계층 + 종상향 잠재 시나리오 (화면경로 반영 — 단일출처 far_tier_service)
        # /zoning/comprehensive·/zoning/analyze가 이 결과를 그대로 사용한다(중복계산 없음).
        try:
            from app.services.land_intelligence import far_tier_service

            zt = result.get("zone_type") or ""
            la = 0.0
            lr = result.get("land_register")
            if isinstance(lr, dict):
                la = float(lr.get("area_sqm", 0) or 0)
            if la <= 0 and result.get("land_area_sqm"):
                la = float(result.get("land_area_sqm") or 0)

            if zt:
                eff = far_tier_service.calc_effective_far(result, zt, la)
                result["effective_far"] = eff
                up = far_tier_service.calc_upzoning(
                    result, zt, la, result.get("infrastructure"), None
                )
                result["upzoning"] = up
                result["upzoning_scenarios"] = up.get("scenarios", [])
                result["potential_far_range"] = up.get("potential_far_range")
        except Exception as e:
            logger.warning("실효용적률/종상향 산정 스킵: %s (%s)", address, str(e))

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

    async def _fetch_land_characteristics(self, pnu: str) -> dict[str, Any] | None:
        """토지특성 조회 (VWORLD NED — 면적·지목·용도지역·이용상황)."""
        try:
            return await self.vworld.get_land_characteristics(pnu)
        except Exception as e:
            logger.warning("토지특성 조회 실패: %s (%s)", pnu, str(e))
            return None

    @staticmethod
    def _zone_limits_for(zone_type: str) -> dict[str, Any] | None:
        """용도지역명 → 법정 건폐율/용적률 한도(국토계획법 시행령 ZONE_LIMITS).

        ★녹지지역 등 층수 제한(max_floors)이 있는 용도지역은 max_height_m이 None이라도
        '실효 높이(effective_height_m = 층수×기본층고 3.0m)'를 함께 산출해 전파한다.
        이로써 종합규제분석이 높이를 '제한 없음'으로 오표시하던 6경로 버그를 SSOT에서 차단한다.
        실효 높이는 층수×층고 근사값임을 height_basis로 정직 표기(무목업).
        """
        if not zone_type:
            return None
        from app.services.zoning.auto_zoning_service import ZONE_LIMITS, build_zone_limits

        key = zone_type.replace(" ", "").strip()
        matched_key = key if key in ZONE_LIMITS else None
        limits = ZONE_LIMITS.get(key)
        if not limits:
            for k, v in ZONE_LIMITS.items():
                if k in key or key in k:
                    limits = v
                    matched_key = k
                    break
        if not limits or matched_key is None:
            return None
        # 공용 빌더(SSOT 단일경유)로 max_floors + effective_height_m(녹지 4층 실효높이)까지 전파.
        return build_zone_limits(matched_key, limits)

    @staticmethod
    def _zone_from_districts(districts: list[dict[str, Any]]) -> str | None:
        """토지이용계획 districts에서 용도지역(주거/상업/공업/녹지/관리 등)을 추출."""
        from app.services.zoning.auto_zoning_service import ZONE_LIMITS

        names = [(d.get("district_name") or "").replace(" ", "") for d in districts]
        # ZONE_LIMITS에 정의된 정식 용도지역명과 매칭(가장 구체적인 것 우선)
        for zone_name in ZONE_LIMITS:
            for n in names:
                if zone_name in n or n in zone_name:
                    return zone_name
        # 일반 '○○지역' 패턴 폴백
        for n in names:
            if n.endswith("지역") and n not in ("도시지역", "관리지역", "농림지역"):
                return n
        return None

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
        연면적·층수가 0인 경우 "정보 미등록"으로 표시하여
        데이터 부재를 명확히 전달한다.
        """
        try:
            # 총괄표제부(getBrBasisOulnInfo) — 면적·건폐율·용적률 권위 소스
            raw = await self.building.get_building_by_pnu(pnu)
            # 표제부(getBrTitleInfo) — 세대수·동수·호수 정확 + 멸실/미준공 best-effort
            title: dict[str, Any] | None = None
            try:
                title = await self.building.get_title_by_pnu(pnu)
            except Exception as e:  # noqa: BLE001
                logger.warning("표제부 조회 실패(상세 통합): %s (%s)", pnu, str(e))
                title = None

            if not raw and not title:
                return None
            raw = raw or {}
            title_present = bool(title)

            total_area = float(raw.get("total_area_sqm", 0) or 0)
            building_area = float(raw.get("building_area_sqm", 0) or 0)
            ground_floors = int(raw.get("ground_floors", 0) or 0)
            underground_floors = int(raw.get("underground_floors", 0) or 0)
            bcr_pct = float(raw.get("bcr_pct", 0) or 0)
            far_pct = float(raw.get("far_pct", 0) or 0)
            main_purpose = raw.get("main_purpose", "") or ""
            structure = raw.get("structure", "") or ""
            use_approval_date = raw.get("use_approval_date", "") or ""
            building_name = raw.get("building_name", "") or ""
            # 세대/가구/호/동: 총괄표제부 기본값
            household_count = int(raw.get("household_count", 0) or 0)
            family_count = int(raw.get("family_count", 0) or 0)
            ho_count = int(raw.get("ho_count", 0) or 0)
            dong_count = 0

            # 표제부 우선 병합 (세대·동·호·사용승인일은 표제부가 더 정확)
            is_demolished = False
            demolition_date = ""
            demolition_basis = ""
            is_uncompleted = False
            uncompleted_basis = ""
            if title:
                household_count = int(title.get("household_count", 0) or 0) or household_count
                family_count = int(title.get("family_count", 0) or 0) or family_count
                ho_count = int(title.get("ho_count", 0) or 0) or ho_count
                dong_count = int(title.get("dong_count", 0) or 0)
                if not ground_floors:
                    ground_floors = int(title.get("ground_floors", 0) or 0)
                if not underground_floors:
                    underground_floors = int(title.get("underground_floors", 0) or 0)
                if not total_area:
                    total_area = float(title.get("total_area_sqm", 0) or 0)
                if not main_purpose:
                    main_purpose = title.get("main_purpose", "") or ""
                if not structure:
                    structure = title.get("structure", "") or ""
                # 사용승인일: 표제부가 권위(총괄표제부는 공란 빈번)
                title_use_apr = str(title.get("use_approval_date", "") or "")
                if title_use_apr:
                    use_approval_date = title_use_apr
                if not building_name:
                    building_name = title.get("building_name", "") or ""
                # 멸실/미준공 (best-effort, 추정·확인필요)
                is_demolished = bool(title.get("is_demolished", False))
                demolition_date = str(title.get("demolition_date", "") or "")
                demolition_basis = str(title.get("demolition_basis", "") or "")
                is_uncompleted = bool(title.get("is_uncompleted", False))
                uncompleted_basis = str(title.get("uncompleted_basis", "") or "")

            # 건축물대장에 건물명만 있고 상세 데이터가 모두 0인 경우 처리
            has_detail = (total_area > 0 or ground_floors > 0 or main_purpose)
            data_status = "정상" if has_detail else "정보 미등록"

            if not has_detail and building_name:
                logger.info(
                    "건축물대장 상세 데이터 미등록: pnu=%s, 건물명=%s "
                    "(건축물대장 표제부에 건물명만 기재되고 상세 정보가 미등록된 경우)",
                    pnu, building_name,
                )

            result = {
                "main_purpose": main_purpose or ("정보 미등록" if not has_detail else ""),
                "structure": structure or ("정보 미등록" if not has_detail else ""),
                "total_area_sqm": total_area,
                "total_area_sqm_display": f"{total_area:,.1f}㎡" if total_area > 0 else "정보 미등록",
                "building_area_sqm": building_area,
                "ground_floors": ground_floors,
                "ground_floors_display": f"지상 {ground_floors}층" if ground_floors > 0 else "정보 미등록",
                "underground_floors": underground_floors,
                "bcr_pct": bcr_pct,
                "far_pct": far_pct,
                "use_approval_date": use_approval_date or ("정보 미등록" if not has_detail else ""),
                "building_name": building_name,
                "address": raw.get("address", ""),
                "road_address": raw.get("road_address", ""),
                "data_status": data_status,
                # ── 표제부 배선 신규 필드 (세대·가구·호·동) ──
                "household_count": household_count,  # 세대수
                "household_count_display": f"{household_count:,}세대" if household_count > 0 else "정보 미등록",
                "family_count": family_count,  # 가구수
                "ho_count": ho_count,  # 호수
                "ho_count_display": f"{ho_count:,}호" if ho_count > 0 else "정보 미등록",
                "dong_count": dong_count,  # 동수
                "dong_count_display": f"{dong_count}개동" if dong_count > 0 else "정보 미등록",
                "title_status": "정상" if title_present else "표제부 미조회",
                # ── 멸실 (best-effort, 추정·확인필요) ──
                "is_demolished": is_demolished,
                "demolition_date": demolition_date,
                "demolition_basis": demolition_basis,
                # ── 미준공/공사중 (best-effort, 추정·확인필요) ──
                "is_uncompleted": is_uncompleted,
                "uncompleted_basis": uncompleted_basis,
                # 데이터 출처: 실제 공공API 호출 결과 여부 (무목업)
                "data_source": "molit_live" if (raw or title_present) else "unavailable",
            }
            return result
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

        # 최근 3개월 거래를 수집 — 월별 호출을 병렬화(asyncio.gather)하여 지연 단축
        def _ymd(off: int) -> str:
            y, m = now.year, now.month - off
            if m <= 0:
                m += 12
                y -= 1
            return f"{y}{m:02d}"

        # ★label별 올바른 API 매핑(무목업): apt→아파트(getRTMSDataSvcAptTradeDev),
        #   land→토지 매매(getRTMSDataSvcLandTrade). 과거 land 버킷이 아파트 API를
        #   호출해 아파트 거래가 토지로 잘못 채워지던 버그를 교정.
        fetchers = {
            "apt": (self.molit.get_apt_transactions, "molit_apt_live"),
            "land": (self.molit.get_land_transactions, "molit_land_live"),
        }

        for label, (fetcher, live_source) in fetchers.items():
            all_items: list[dict[str, Any]] = []
            month_results = await asyncio.gather(
                *[fetcher(lawd_cd, _ymd(off)) for off in range(3)],
                return_exceptions=True,
            )
            for items in month_results:
                if isinstance(items, list):
                    all_items.extend(items)
                elif isinstance(items, Exception):
                    # 키 미승인(403)·네트워크 등 — 정직 로깅, 다른 유형으로 대체 금지
                    logger.warning(
                        "인근 실거래 조회 실패: label=%s lawd_cd=%s (%s)",
                        label, lawd_cd, str(items),
                    )

            if not all_items:
                # 무자료/키미승인/오류 → 빈값 + 사유(아파트 데이터 복제 절대 금지)
                result[label] = {
                    "avg_price_10k": 0,
                    "max_price_10k": 0,
                    "min_price_10k": 0,
                    "count": 0,
                    "items": [],
                    "data_source": "unavailable",
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
                # ★대표통계(이상치 제거): 토지 지분·정정 등 미미거래(예 4만원)·초고가가 최저/최고/
                #   평균을 왜곡하던 문제 수정. count는 원시 유효건수 정직 유지, excluded 투명 표기.
                _stats = robust_price_stats(prices)
                result[label] = {
                    "avg_price_10k": _stats["avg"],
                    "max_price_10k": _stats["max"],
                    "min_price_10k": _stats["min"],
                    "count": _stats["count"],
                    "excluded_outliers": _stats["excluded"],
                    "data_source": live_source,
                    "items": [
                        {
                            "price_10k": str(
                                item.get("거래금액", item.get("price_10k_won", "0"))
                            ).replace(",", "").strip(),
                            "area_sqm": item.get("전용면적", item.get("area_m2", "")),
                            "deal_date": item.get("deal_date") or f"{item.get('년', '')}.{item.get('월', '')}.{item.get('일', '')}",
                            # 토지는 건물명/층이 없음 → 지목(또는 용도지역)을 표시명으로 사용
                            "name": (
                                item.get("아파트", item.get("building_name", ""))
                                or item.get("jimok", "")
                                or item.get("land_use", "")
                            ),
                            "floor": item.get("층", item.get("floor", "")),
                            # 토지 전용 부가정보(아파트는 빈값)
                            "jimok": item.get("jimok", ""),
                            "land_use": item.get("land_use", ""),
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
                    "data_source": "unavailable",
                }

        return result if any(v.get("count", 0) > 0 for v in result.values()) else None

    async def _fetch_precise_road_width(
        self, pnu: str | None, coords: dict | None,
    ) -> float | None:
        """연속지적도 도로 필지 기반 정밀 접도 너비(m).

        대상 필지 geometry를 가져와 주변 bbox(반경 ~60m) 필지 중 지목='도로'인
        인접 필지의 폭을 측정한다. PNU·좌표 부재 또는 측정 불가 시 None.
        """
        import math

        if not pnu or not coords:
            return None
        lat = coords.get("lat")
        lon = coords.get("lon")
        if not lat or not lon:
            return None

        # 대상 필지 경계
        land = await self.vworld.get_land_info(pnu)
        subj_geom = land.get("geometry") if isinstance(land, dict) else None
        if not subj_geom:
            return None

        # 주변 필지 bbox (반경 ~60m): 위도/경도 도 단위 환산
        d_lat = 60 / 111_320
        d_lon = 60 / (111_320 * max(0.1, math.cos(math.radians(lat))))
        parcels = await self.vworld.get_parcels_in_bbox(
            lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat,
        )
        if not parcels:
            return None

        return compute_precise_road_width_m(subj_geom, parcels)

    async def _fetch_infrastructure(
        self, lat: float, lon: float,
    ) -> dict[str, Any] | None:
        """주변 인프라 분석 (VWORLD POI 검색 활용).

        - 최근접 지하철역 거리 (반경 2km, 1차 1km → 폴백 2km)
        - 학군 정보 (반경 1km 학교)

        VWORLD POI 검색 API 주의사항:
        - Referer 헤더는 VWORLD에 등록된 도메인과 일치해야 함
        - bbox 형식: "minX,minY,maxX,maxY" (EPSG:4326 경위도)
        - type=place 검색 시 category는 선택 사항 (지정하면 결과 제한)
        """
        import httpx

        from app.core.config import settings

        infra: dict[str, Any] = {
            "nearest_subway": None,
            "schools": [],
            "hospitals": [],
            "marts": [],
            "convenience_stores": [],
            "parks": [],
            "bus_stops": [],
        }

        if not settings.VWORLD_API_KEY:
            return None

        # VWORLD 등록 도메인과 일치하는 Referer
        headers = {"Referer": "https://www.4t8t.net"}

        # ── 지하철역 검색 (1차: 반경 1km → 결과 없으면 2km로 확대) ──
        for search_radius in [1000, 2000]:
            try:
                async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                    # category 파라미터를 제거하여 검색 범위를 넓힘
                    # VWORLD POI 검색에서 category 지정 시 일부 데이터 누락 발생
                    resp = await client.get(
                        f"{settings.VWORLD_BASE_URL}/search",
                        params={
                            "service": "search",
                            "request": "search",
                            "key": settings.VWORLD_API_KEY,
                            "query": "지하철역",
                            "type": "place",
                            "format": "json",
                            "size": "3",
                            "bbox": self._make_bbox(lat, lon, radius_m=search_radius),
                        },
                    )
                    if resp.status_code == 404:
                        logger.debug(
                            "VWORLD POI 검색 404 — URL 경로 확인 필요: %s (반경 %dm)",
                            resp.url, search_radius,
                        )
                        break  # 404는 반경 확대해도 동일
                    resp.raise_for_status()
                    data = resp.json()
                    response_obj = data.get("response", {})
                    status = response_obj.get("status", "")
                    if status != "OK":
                        logger.debug(
                            "VWORLD 지하철 검색 NOT OK: status=%s, 반경=%dm",
                            status, search_radius,
                        )
                        continue

                    result_obj = response_obj.get("result", {})
                    items = result_obj.get("items", [])
                    if items:
                        item = items[0]
                        station_lat = float(item.get("point", {}).get("y", 0))
                        station_lon = float(item.get("point", {}).get("x", 0))
                        dist_m = self._haversine_m(lat, lon, station_lat, station_lon)
                        infra["nearest_subway"] = {
                            "name": item.get("title", ""),
                            "distance_m": round(dist_m),
                        }
                        break  # 찾았으면 중단
            except Exception as e:
                logger.debug("지하철역 검색 실패 (반경 %dm): %s", search_radius, str(e))

        # ── 학교 검색 (반경 1km, category 미지정으로 폴백) ──
        for attempt, params_override in enumerate([
            {"category": "교육시설"},  # 1차: 교육시설 카테고리
            {},                         # 2차: 카테고리 미지정 (전체 검색)
        ]):
            if infra["schools"]:
                break  # 이미 결과가 있으면 재시도 불필요
            try:
                async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                    search_params: dict[str, Any] = {
                        "service": "search",
                        "request": "search",
                        "key": settings.VWORLD_API_KEY,
                        "query": "학교",
                        "type": "place",
                        "format": "json",
                        "size": "5",
                        "bbox": self._make_bbox(lat, lon, radius_m=1000),
                    }
                    search_params.update(params_override)
                    resp = await client.get(
                        f"{settings.VWORLD_BASE_URL}/search",
                        params=search_params,
                    )
                    if resp.status_code == 404:
                        logger.debug("VWORLD POI 학교 검색 404 (시도 %d)", attempt + 1)
                        break
                    resp.raise_for_status()
                    data = resp.json()
                    response_obj = data.get("response", {})
                    if response_obj.get("status") != "OK":
                        continue

                    items = response_obj.get("result", {}).get("items", [])
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
                logger.debug("학교 검색 실패 (시도 %d): %s", attempt + 1, str(e))

        # ── 생활 인프라 POI 확장 (병원/마트/편의점/공원/버스/IC) ──
        # 각 카테고리를 반경 내에서 검색해 최근접순 상위 N개를 수집한다.
        # 개별 카테고리 실패는 무시하고 나머지를 계속 수집한다.
        poi_categories: list[tuple[str, str, int, int]] = [
            # (infra_key, query, radius_m, size)
            ("hospitals", "병원", 3000, 3),
            ("marts", "대형마트", 3000, 3),
            ("convenience_stores", "편의점", 1000, 5),
            ("parks", "공원", 2000, 3),
            ("bus_stops", "버스정류장", 800, 5),
        ]
        for infra_key, query, radius, size in poi_categories:
            try:
                pois = await self._search_poi(lat, lon, query, radius, size, headers, settings)
                if pois:
                    infra[infra_key] = pois
            except Exception as e:
                logger.debug("POI 검색 실패 (%s): %s", query, str(e))

        has_data = (
            infra["nearest_subway"] is not None
            or len(infra["schools"]) > 0
            or any(infra.get(k) for k in ("hospitals", "marts", "convenience_stores", "parks", "bus_stops"))
        )
        return infra if has_data else None

    async def _search_poi(
        self, lat: float, lon: float, query: str,
        radius_m: int, size: int, headers: dict, settings,
    ) -> list[dict[str, Any]]:
        """VWORLD POI 검색 범용 헬퍼 — 거리순 정렬된 {name, distance_m} 리스트 반환.

        지하철·학교 검색과 동일한 패턴(category 미지정, bbox 반경)을 사용한다.
        """
        import httpx

        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            resp = await client.get(
                f"{settings.VWORLD_BASE_URL}/search",
                params={
                    "service": "search",
                    "request": "search",
                    "key": settings.VWORLD_API_KEY,
                    "query": query,
                    "type": "place",
                    "format": "json",
                    "size": str(size),
                    "bbox": self._make_bbox(lat, lon, radius_m=radius_m),
                },
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            response_obj = resp.json().get("response", {})
            if response_obj.get("status") != "OK":
                return []
            items = response_obj.get("result", {}).get("items", []) or []

        pois: list[dict[str, Any]] = []
        for item in items:
            p_lat = float(item.get("point", {}).get("y", 0))
            p_lon = float(item.get("point", {}).get("x", 0))
            if p_lat == 0 or p_lon == 0:
                continue
            pois.append({
                "name": item.get("title", ""),
                "distance_m": round(self._haversine_m(lat, lon, p_lat, p_lon)),
            })
        pois.sort(key=lambda x: x["distance_m"])
        return pois

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

