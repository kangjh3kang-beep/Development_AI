"""종합 부지분석 서비스.

주소 하나만 입력하면 7개 카테고리 자동 분석 보고서를 생성.
기존 서비스(LandInfoService, OrdinanceService, MOLITService 등)를 재사용.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog

from app.services.data_validation.price_stats import robust_price_stats
from app.services.feasibility.permit_validator import (
    DEVELOPMENT_TYPE_NAMES,
    PERMIT_COMPLEXITY,
    get_permitted_types,
    permitted_types_known,
)
from app.services.land_intelligence import far_tier_service
from app.services.land_intelligence.land_info_service import LandInfoService

logger = structlog.get_logger()

# ── 세대·면적 표준(전용율·평균 전용면적·전형 용적률) = 단일 출처 unit_standards (W1-3) ──
#    Top3 추천(feasibility_v2)과 각자 테이블을 보유해 동일 GFA에서 세대수가 어긋나던
#    이중정의 해소. 값 수정은 반드시 unit_standards에서(여기 재정의 금지).
from app.services.feasibility.unit_standards import (  # noqa: E402
    AVG_EXCLUSIVE_AREA_SQM as AVG_EXCLUSIVE_AREA,
)
from app.services.feasibility.unit_standards import (
    EXCLUSIVE_AREA_RATIO,
)
from app.services.feasibility.unit_standards import (
    TYPICAL_FAR_PCT as TYPICAL_FAR,
)

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

# ── 개발방식별 일반적 용적률 — 단일 출처 unit_standards.TYPICAL_FAR_PCT(상단 import) ──

# ── 개발방식별 분양가 보정계수 ──
# 주의: 다른 계수 테이블(EXCLUSIVE_AREA_RATIO 등)과 동일하게 M01~M15 전수 유지.
SALE_PRICE_MULTIPLIER: dict[str, float] = {
    "M01": 1.0, "M02": 1.0, "M03": 1.0, "M04": 0.95,
    "M05": 0.7,  # 임대협동조합: 저가 임대 성격 반영
    "M06": 1.0, "M07": 1.1, "M08": 0.8, "M09": 0.65,
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


def _extract_sigungu_from_address(address: str | None) -> str | None:
    """주소 → 도시계획조례 정본 레벨 행정구역명(조례값·딥링크 공용).

    ★단일 SSOT(ordinance_service.resolve_ordinance_region)를 경유한다 — 특별시/광역시는 시
    본청(서울특별시), 도 산하는 시/군(용인시)이 용적률/건폐율 도시계획조례의 정본이며 자치구는
    별도 조례가 없다(국토의 계획 및 이용에 관한 법률 제77·78조). 종전엔 자치구(강남구)를 반환해
    조례 딥링크 연결실패·값 미로드를 유발했다. 조례 관련 모든 레벨 해소를 이 한 출처로 일원화.
    """
    from app.services.land_intelligence.ordinance_service import resolve_ordinance_region
    return resolve_ordinance_region(address)


def _build_site_evidence_block(result: dict) -> dict[str, Any]:
    """종합 부지분석 결과 → 근거·법령·신선도 공용 블록(전역정책 Phase0, additive).

    effective_far(sec1)의 법정/조례/실효 용적률·건폐율을 한 줄씩 트레이스하고,
    국토계획법 시행령 한도(far_limit/bcr_limit) + 조례(ordinance_far/bcr) 법령 근거를
    레지스트리(get_legal_refs)로 연결한다. URL은 전적으로 레지스트리 출력만 사용.
    zone_type 미확정·근거 부재면 빈 블록(가짜 링크·할루시네이션 금지). graceful.
    """
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        zone_type = (result.get("zone_type") or "").strip()
        sec1 = result.get("effective_far") if isinstance(result.get("effective_far"), dict) else {}
        if not zone_type or not sec1:
            return build_evidence_block()  # 빈 블록(정직)

        national_far = sec1.get("national_far_pct")
        national_bcr = sec1.get("national_bcr_pct")
        ordinance_far = sec1.get("ordinance_far_pct")
        ordinance_bcr = sec1.get("ordinance_bcr_pct")
        effective_far = sec1.get("effective_far_pct")
        effective_bcr = sec1.get("effective_bcr_pct")
        ordinance_confirmed = bool(sec1.get("ordinance_confirmed"))
        sigungu = _extract_sigungu_from_address(result.get("address"))

        items: list[dict[str, Any]] = []
        ref_keys: list[str] = []

        # 법정 상한(국토계획법 시행령 제85·84조) — far_limit/bcr_limit 근거.
        if national_far is not None:
            items.append({
                "label": "법정 용적률 상한",
                "value": f"{round(float(national_far))}%",
                "basis": f"{zone_type} 국가 법정상한(국토계획법 시행령)",
                "legal_ref_key": "far_limit",
            })
            ref_keys.append("far_limit")
        if national_bcr is not None:
            items.append({
                "label": "법정 건폐율 상한",
                "value": f"{round(float(national_bcr))}%",
                "basis": f"{zone_type} 국가 법정상한(국토계획법 시행령)",
                "legal_ref_key": "bcr_limit",
            })
            ref_keys.append("bcr_limit")

        # 조례 실효값(법정과 다르고 조례가 확인된 경우만) — ordinance_far/bcr 근거.
        if ordinance_confirmed and ordinance_far is not None and ordinance_far != national_far:
            items.append({
                "label": "조례 적용 용적률",
                "value": f"{round(float(ordinance_far))}%",
                "basis": f"{sigungu or '지자체'} 도시계획 조례 실효값",
                "legal_ref_key": "ordinance_far",
            })
            ref_keys.append("ordinance_far")
        if ordinance_confirmed and ordinance_bcr is not None and ordinance_bcr != national_bcr:
            items.append({
                "label": "조례 적용 건폐율",
                "value": f"{round(float(ordinance_bcr))}%",
                "basis": f"{sigungu or '지자체'} 도시계획 조례 실효값",
                "legal_ref_key": "ordinance_bcr",
            })
            ref_keys.append("ordinance_bcr")

        # 실효(적용) 한도 — min(법정, 조례). 법령키는 위 한도 근거를 공유하므로 생략(중복 방지).
        if effective_far is not None:
            items.append({
                "label": "실효 용적률(적용)",
                "value": f"{round(float(effective_far))}%",
                "basis": "min(법정상한, 조례) — 실제 설계·분석 적용값",
            })
        if effective_bcr is not None:
            items.append({
                "label": "실효 건폐율(적용)",
                "value": f"{round(float(effective_bcr))}%",
                "basis": "min(법정상한, 조례) — 실제 설계·분석 적용값",
            })

        return build_evidence_block(
            items=items,
            legal_ref_keys=ref_keys,
            sigungu=sigungu,
            sources=["vworld_zoning", "vworld_land_info", "molit_transactions"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 무손상(빈 블록 폴백)
        try:
            from app.services.data_validation.evidence_contract import build_evidence_block

            return build_evidence_block()
        except Exception:  # noqa: BLE001
            return {"evidence": [], "legal_refs": [], "provenance": [], "trust": None}


# ── T1-4(경사도 고아 데이터 배선) — terrain 분석 → detect_special_parcel 계약 ──
#   docs/LEGAL_ENGINE_SLOPE_FOREST_PLAN_2026-07-02.md T1: terrain_service가 SRTM 30m
#   DEM으로 실산출하는 mean_pct/max_pct가 특이부지 게이트에 미배선(고아 데이터)이던 것을
#   종합분석 경로에서 배선한다. 계약(E-gate 합의):
#   terrain_facts = {"평균경사도_pct": float, "최대경사도_pct": float, "source": str}
#   원칙: 데이터 없으면 None=현행 완전 동일(additive) · developability 완화 금지(전달만).
_TERRAIN_FACTS_SOURCE = "SRTM30_DEM"
_TERRAIN_FETCH_TIMEOUT_S = 15.0


def _is_forest_slope_candidate(sp_input: dict | None) -> bool:
    """경사도 심층검토 후보 여부 — 임야 지목 또는 산지 구역만(불필요 DEM 호출 차단).

    detect_special_parcel의 산지 게이트(경사도 forest_facts)가 소비하는 입력만 대상.
    비후보는 terrain 조회 자체를 생략해 현행 동작·지연을 100% 보존한다(additive).
    """
    if not isinstance(sp_input, dict):
        return False
    if "임야" in str(sp_input.get("land_category") or ""):
        return True
    districts = sp_input.get("special_districts") or []
    if isinstance(districts, (list, tuple)):
        return any("산지" in str(d) for d in districts)
    return False


def _terrain_facts_from_result(terrain_result: dict | None) -> dict[str, Any] | None:
    """terrain_service.analyze_terrain 결과 → terrain_facts 계약 dict.

    ok:false·slope 결손·비수치는 None(무날조 — 불확실 데이터는 전달하지 않는다).
    source는 SRTM 30m DEM 근사임을 명기(공식 평균경사도조사서 아님 — 한계는
    special_parcel 쪽 정확도한계 고지가 담당).
    """
    if not isinstance(terrain_result, dict) or not terrain_result.get("ok"):
        return None
    slope = terrain_result.get("slope")
    if not isinstance(slope, dict):
        return None
    mean_pct = slope.get("mean_pct")
    max_pct = slope.get("max_pct")
    if not isinstance(mean_pct, (int, float)) or not isinstance(max_pct, (int, float)):
        return None
    return {
        "평균경사도_pct": float(mean_pct),
        "최대경사도_pct": float(max_pct),
        "source": _TERRAIN_FACTS_SOURCE,
    }


async def _fetch_terrain_facts(
    address: str | None, pnu: str | None, sp_input: dict | None
) -> dict[str, Any] | None:
    """후보 필지에 한해 DEM 경사도(terrain_service)를 조회해 terrain_facts 산출.

    비후보·실패·타임아웃은 전부 None(graceful) — 특이부지 감지의 현행 경로 무손상.
    """
    if not _is_forest_slope_candidate(sp_input):
        return None
    try:
        from app.services.terrain import terrain_service as _ts

        terrain = await asyncio.wait_for(
            _ts.analyze_terrain(address, pnu, None, None),
            timeout=_TERRAIN_FETCH_TIMEOUT_S,
        )
        return _terrain_facts_from_result(terrain)
    except Exception as exc:  # noqa: BLE001 — 경사도 조회 실패는 무손상(None=현행 동일)
        # 조용한 강등 방지(기록·공유 원칙): 실패 사유를 debug로 남긴다(게이트엔 무영향).
        logger.debug("terrain_facts 조회 실패(무손상 폴백)", pnu=pnu, error=str(exc))
        return None


# ── T2/T3(고아 함수 배선) — 조례 경사도 기준·산림청 임목축적을 종합분석 경로에 실연결 ──
#   #162가 resolve_slope_criteria(T2)·get_forest_facts(T3)를 만들었으나 프로덕션 호출처가
#   0건(dead-path)이었다. detect_special_parcel은 이미 slope_criteria/forest_data 인자를
#   받아 임야 요인 forest_facts에 예비판정을 가산하도록 완성돼 있으므로, 여기서 두 함수를
#   호출해 전달만 하면 응답의 special_parcel.forest_preliminary_assessment 로 흐른다.
#   ★게이트(developability=NEEDS_OFFICIAL_SURVEY) 불변 — 예비판정(참고용)만 채워진다.
_FOREST_FETCH_TIMEOUT_S = 12.0
_SLOPE_CRITERIA_TIMEOUT_S = 12.0


async def _fetch_forest_data(
    pnu: str | None, sp_input: dict | None
) -> dict[str, Any] | None:
    """후보 필지(임야/산지)에 한해 산림청 임목축적(get_forest_facts)을 조회 — 별표4 150% 비교 재료.

    get_forest_facts는 동기(httpx.Client)이므로 이벤트루프 블로킹 방지를 위해 스레드로
    실행한다. env(FOREST_API_KEY/FOREST_API_BASE) 미설정 시 커넥터가 네트워크 시도 없이
    즉시 None을 반환(무날조 정직 게이트)하므로, 배선해도 키 프로비저닝 전엔 예비판정이
    '데이터 미확보'로 정직 표기된다. 비후보·실패·타임아웃은 전부 None(graceful).
    """
    if not _is_forest_slope_candidate(sp_input):
        return None
    pnu_clean = (pnu or "").strip()
    if not pnu_clean:
        return None
    try:
        from app.integrations.forest_service_client import get_forest_facts

        return await asyncio.wait_for(
            asyncio.to_thread(get_forest_facts, pnu_clean),
            timeout=_FOREST_FETCH_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001 — 임목축적 조회 실패는 무손상(None=현행 동일)
        # 조용한 강등 방지: 조회 실패를 debug로 남긴다(예비판정은 정직 '미확보'로 표기됨).
        logger.debug("forest_data(임목축적) 조회 실패(무손상 폴백)", pnu=pnu_clean, error=str(exc))
        return None


async def _fetch_slope_criteria(
    address: str | None, sp_input: dict | None
) -> dict[str, Any] | None:
    """후보 필지(임야/산지)에 한해 조례 경사도 기준(resolve_slope_criteria)을 조회 — 경사도 예비판정 기준.

    법제처 자치법규 API(MOLEG_API_KEY 기설정 — 조례 FAR/BCR 조회에 이미 라이브 사용)로
    개발행위허가 경사도 기준을 실조회한다. 실패·미검출은 None → special_parcel이 국가기준
    별표4 25°로 폴백(무날조: 조례값 날조 금지). 비후보·타임아웃도 None(graceful).
    """
    if not _is_forest_slope_candidate(sp_input):
        return None
    sigungu = _extract_sigungu_from_address(address)
    if not sigungu:
        return None
    try:
        from app.services.land_intelligence.ordinance_service import OrdinanceService

        return await asyncio.wait_for(
            OrdinanceService().resolve_slope_criteria(sigungu),
            timeout=_SLOPE_CRITERIA_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001 — 조례 경사도 조회 실패는 무손상(국가기준 폴백)
        # 조용한 강등 방지: 실패 시 국가기준 별표4 25°로 폴백되므로 사유를 debug로 남긴다.
        logger.debug("slope_criteria(조례 경사도) 조회 실패(국가기준 폴백)", sigungu=sigungu, error=str(exc))
        return None


def _detect_special_parcel_compat(
    sp_input: dict,
    terrain_facts: dict[str, Any] | None,
    forest_data: dict[str, Any] | None = None,
    slope_criteria: dict[str, Any] | None = None,
) -> dict | None:
    """detect_special_parcel 호환 호출 — 관측데이터(terrain/forest/slope)는 지원 시그니처에만 전달.

    W1/W2 병렬 착지 안전장치: special_parcel.py(E-gate 소유)에 각 인자가 아직 없으면
    있는 인자만 골라 전달한다(기존 호출부 무수정 호환 원칙). 배선은 전달만 하며
    developability 판정에는 일절 개입하지 않는다(정직 게이트 보존).
    """
    import inspect

    from app.services.zoning import special_parcel as _sp_mod

    detect = _sp_mod.detect_special_parcel
    try:
        params = inspect.signature(detect).parameters
    except (TypeError, ValueError):  # 시그니처 미해석 — 현행 호출 폴백
        params = {}
    kwargs: dict[str, Any] = {}
    if terrain_facts is not None and "terrain_facts" in params:
        kwargs["terrain_facts"] = terrain_facts
    if forest_data is not None and "forest_data" in params:
        kwargs["forest_data"] = forest_data
    if slope_criteria is not None and "slope_criteria" in params:
        kwargs["slope_criteria"] = slope_criteria
    return detect(sp_input, **kwargs)


class ComprehensiveAnalysisService:
    """주소 입력만으로 7개 분석 카테고리를 자동 수행."""

    def __init__(self) -> None:
        self.land_info = LandInfoService()

    async def analyze(
        self,
        address: str,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        with_senior: bool = True,
        parcels: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "종합분석 시작",
            address=address[:30],
            llm_provider=llm_provider or "default",
            llm_model=llm_model or "default",
        )

        # Phase 1: 기본 데이터 수집 (LandInfoService 재사용)
        base = await self.land_info.collect_comprehensive(address)

        # Phase 1 성장루프: 직전 분석 prior read(best-effort, 없으면 None — 무중단)
        from app.services.ledger.prior_context import build_prior_block, load_prior
        _pnu = base.get("pnu")
        prior = await load_prior(
            analysis_type="site_analysis", tenant_id=tenant_id,
            pnu=_pnu, address=address, project_id=project_id,
        )
        prior_block = build_prior_block(prior)

        zone_type = base.get("zone_type", "")
        land_area = 0.0
        lr = base.get("land_register")
        if isinstance(lr, dict):
            land_area = float(lr.get("area_sqm", 0) or 0)

        # Phase 2: 7개 분석 섹션 + 법적 검증 + FAR 최적화
        # 실효용적률은 collect_comprehensive가 이미 산출(단일출처) — 중복계산 방지 위해 재사용.
        sec1 = base.get("effective_far") or self._calc_effective_far(base, zone_type, land_area)
        effective_far = sec1["effective_far_pct"]
        effective_bcr = sec1["effective_bcr_pct"]

        # ★(단일/다필지 일원화) parcels 제공 시 면적가중 통합집계로 land_area·zone_type·effective_far를
        #   덮어쓴다 — 이후 7섹션·GFA·유형별검증이 전부 '통합면적' 기준으로 산출된다(543㎡ 단일 버그 제거).
        #   목적은 N≥2 통합. N=1은 _aggregate의 구조적 항등(total=단일면적·blended=그 값)이라 단일과 사실상
        #   동일하나, 프론트가 실효치(farPct)를 직접 제공하면 그 출처(parcels-info)가 single-path base 산출과
        #   미세 차이날 수 있다(프론트는 length>1일 때만 전송 → 운영 UI는 N=1 override 미도달).
        #   미제공(레거시 단일주소 호출)은 위 단일 경로 그대로(완전 무변경).
        integrated = await self._integrated_context(parcels) if parcels else None
        land_area_basis = "단일/미제공 — 대지면적 그대로"
        # ★F2(QA REQUEST CHANGES) 면적 기준 이원화: 취득원가(land_cost)는 gross(전체 매입대상
        #   면적 — 도로·GB 등 제외 필지도 실제로는 매입 대상이므로 축소하면 낙관 편향/무날조
        #   위반 방향), 개발규모(GFA·세대수 등)는 usable(산입가능 면적) 유지. land_area_gross는
        #   아래에서 usable로 덮이기 전 gross 값을 별도 보존해 _calc_land_prices에 전달한다.
        land_area_gross = land_area  # 단일필지 기본값(원본 공부면적, usable 축소 없음)
        if integrated and float(integrated.get("total_area_sqm") or 0) > 0:
            land_area = float(integrated["total_area_sqm"])
            land_area_gross = land_area  # 다필지 gross(통합 전체 면적 — 제외 필지 포함)
            land_area_basis = "다필지 통합(gross) 대지면적"
            # ★P0-2(c)(RC3) 대지면적은 usable(도로·구거·하천 지목·BLOCKED 게이트 제외) 기준을
            #   채택한다 — gross 전량 합산은 건축 불가 지목까지 개발규모 산정에 넣는 과대표시였다.
            #   result["integrated_zoning"]에는 gross(total_area_sqm)가 그대로 남아 하위호환되고,
            #   여기서는 land_area(GFA·세대수 등 이후 산정에 쓰이는 변수)만 usable로 교체한다.
            #   land_area_gross는 위에서 이미 고정했으므로 아래 override는 land_area에만 영향.
            _eff_area = integrated.get("land_area_effective_sqm")
            if _eff_area is not None and float(_eff_area) > 0:
                land_area = float(_eff_area)
                if abs(land_area - float(integrated["total_area_sqm"])) > 0.5:
                    land_area_basis = "실사용가능(usable_confirmed) 대지면적 — 도로·구거·하천·개발불가 게이트 필지 제외"
            dz = integrated.get("dominant_zone")
            if dz and dz != "mixed_review_required":
                zone_type = dz
            if integrated.get("blended_far_eff_pct") is not None:
                effective_far = float(integrated["blended_far_eff_pct"])
            if integrated.get("blended_bcr_eff_pct") is not None:
                effective_bcr = float(integrated["blended_bcr_eff_pct"])
            # sec1(실효용적률 카드)도 통합 실효치로 정합 + 통합 메타 부착(혼재 시 검토필요 표기 유지).
            #   ★national_far_pct(표시필드)는 덮지 않는다 — evidence "국가 법정상한(국토계획법 시행령)"으로
            #   소비되므로 blended(면적가중 혼합값)로 바꾸면 단일 시행령 정값이 아닌데 시행령 링크가 걸려
            #   라벨-값 거짓이 된다(리뷰 P1). 표시필드는 보존하고, far_optimization의 ceiling만 아래에서
            #   통합 blended로 전달한다(두 값은 의미가 다름: 시행령 정값 vs 통합 최대상한).
            sec1 = {
                **(sec1 if isinstance(sec1, dict) else {}),
                "effective_far_pct": effective_far,
                "effective_bcr_pct": effective_bcr,
                "integrated": True, "parcel_count": integrated.get("parcel_count"),
                "dominant_zone": dz, "zone_mix": integrated.get("zone_mix"),
            }
            # ★면적의존 산출물(annotations 문구·far_optimization)도 통합면적 기준으로 재생성한다.
            #   숫자만 바꾸면 "대표 763㎡ 기준 최대 연면적…" 대표필지 문구가 그대로 남는 버그(RC#1)를
            #   공용 SSOT 헬퍼로 봉합 — 문구/시나리오가 통합면적·N필지로 정합.
            #   ★far_optimization ceiling만 §84 면적가중 법정 blended로 전달(표시필드 national_far_pct는 불변).
            #   build_integrated_context가 각 필지 실효/법정 결측을 대칭 정규화(같은 부분집합)해
            #   blended_법정 ≥ blended_실효를 구조보장하므로 ceiling ≥ base(자기모순 차단).
            #   추가로 simulator가 cap=max(cap,base) 클램프로 방어. 결측이면 대표 법정으로 폴백.
            _bl_far = integrated.get("blended_far_legal_pct")
            sec1 = far_tier_service.rebuild_area_dependent(
                sec1,
                land_area=land_area, effective_far=effective_far, effective_bcr=effective_bcr,
                zone_type=(zone_type if isinstance(zone_type, str) else str(zone_type)),
                national_far=(_bl_far if _bl_far is not None else sec1.get("national_far_pct")),
                parcel_count=int(integrated.get("parcel_count") or 2),
                zone_mix=integrated.get("zone_mix"),
            )
            # ★P0-5(RC7) 봉합: 위 rebuild_area_dependent는 면적의존 문구(최대 연면적 등)만
            #   갈아끼우고, "법정 용적률 상한은 250%입니다"·"실효 용적률은... 200%가 적용됩니다"
            #   같은 법정/조례 비교 서술은 대표필지 값 그대로 남긴다(그 함수 설계 계약). 다필지
            #   통합에서는 effective_far_pct가 blended 값(예: 139.6%)으로 override되므로 저
            #   문장을 방치하면 "실효 139.6% vs 문장 속 200%" 수치-서술 충돌이 남는다(라이브
            #   재현 버그). 법정/조례 비교 문장만 통합 기준 1문장으로 교체한다(별도 함수 — 블라스트 최소).
            sec1 = far_tier_service.rebuild_legal_basis_annotations(
                sec1,
                effective_far=effective_far, effective_bcr=effective_bcr,
                national_far=(_bl_far if _bl_far is not None else sec1.get("national_far_pct")),
                national_bcr=integrated.get("blended_bcr_legal_pct"),
                parcel_count=int(integrated.get("parcel_count") or 2),
                zone_mix=integrated.get("zone_mix"),
            )

        # ── P0-2(d)(e)(RC4) 공급면적(세대수/주차 등) 산정 전 경량 게이트 선산출 ──
        #   기존엔 특이부지(GB 등) 감지가 공급면적 산정 '이후'(아래 특이부지 감지 블록)라 이미
        #   산정된 공급면적을 막을 수 없었다. detect_special_parcel은 순수 동기 함수라 터레인/
        #   산림 관측(임야 세부판정 보정용 — GB/도로 등 기본 게이트에는 불필요) 없이도 가볍게
        #   먼저 호출해 developability만 뽑는다(로직 복제 아님 — 동일 SSOT 함수 재호출, 최종
        #   상세 감지는 기존 위치에서 관측데이터 포함해 그대로 재실행해 result["special_parcel"]에
        #   싣는다). 비연접(파편 필지) 클러스터도 여기서 함께 차단한다.
        _supply_blocked_reason: str | None = None
        try:
            _lr_gate = base.get("land_register") if isinstance(base.get("land_register"), dict) else {}
            _gate_sp_input = {
                "zone_type": zone_type,
                "land_category": _lr_gate.get("land_category") or "",
                "special_districts": base.get("special_districts") or [],
                "road_contact": base.get("road_contact"),
                "road_width_m": base.get("road_width_m") or _lr_gate.get("road_width_m"),
                # ★road_width_source 동반 — 폭만 넘기면 하류가 실측/추정을 구분하지 못해
                #   근거 문구가 범주 대표값을 실측인 양 표기한다(필드는 최종표면까지 추적).
                "road_width_source": base.get("road_width_source") or _lr_gate.get("road_width_source"),
            }
            _early_gate = _detect_special_parcel_compat(_gate_sp_input, None, None, None)
            if _early_gate and _early_gate.get("developability") == "BLOCKED":
                _supply_blocked_reason = (
                    _early_gate.get("honest_disclosure")
                    or "개발제한구역 등 개발불가 게이트로 공급규모(세대수·주차)를 산정하지 않습니다."
                )
        except Exception:  # noqa: BLE001 — 게이트 선산출 실패는 무손상(기존 공급산정 진행)
            pass
        if integrated and (integrated.get("adjacency") or {}).get("contiguous") is False:
            _components = (integrated.get("adjacency") or {}).get("components")
            _supply_blocked_reason = (
                f"비연접 파편 필지 {_components if _components else '다수'}개 클러스터 — "
                "단일 대지 개발이 불가합니다. 연접 필지 재선택 또는 클러스터별 분석이 필요합니다."
            )

        # ★F1(QA REQUEST CHANGES·차단) 빈 zone 단일필지 500 크래시 무날조 게이트.
        #   재현: zone_type=""(빈 용도지역) → calc_effective_far가 P0-1로 eff/legal=None을
        #   정직 반환하는데, get_permitted_types("")는 부분일치 검색 `zone_type in key`가
        #   빈 문자열과 항상 True로 매칭돼(예: "" in "제1종전용주거지역") permitted가 비지
        #   않은 채로 반환된다 — 그래서 _calc_supply_areas의 '미등재 용도지역 판정불가' 조기
        #   반환(=permitted 빈 목록 전제)을 우회하고 min(effective_far, typical_far)(:941)에서
        #   effective_far=None과 int를 비교해 TypeError로 500이 난다. get_permitted_types
        #   자체 수정은 SSOT 전역 영향이 커(블라스트 확대) 이 호출부에서 None을 정직 게이트로
        #   막는다(임의 수치 미생성 — 기존 _supply_blocked_reason 메커니즘 재사용).
        if _supply_blocked_reason is None and (effective_far is None or effective_bcr is None):
            _supply_blocked_reason = "용도지역 미확인 — 공급규모(세대수·주차)를 산정하지 않습니다(임의 수치 미생성)."

        if _supply_blocked_reason:
            sec2 = [{
                "development_type": None, "type_name": "판정불가",
                "note": _supply_blocked_reason, "blocked_reason": _supply_blocked_reason,
            }]
        else:
            sec2 = self._calc_supply_areas(zone_type, land_area, effective_far, effective_bcr)
        # ★F2: 취득원가(토지가액)는 gross 기준 — 제외 필지(도로·GB 등)도 매입 대상이므로
        #   usable(land_area)로 축소하면 취득원가를 실제보다 낮게 표시하는 낙관 편향이 된다
        #   (무날조 원칙 위반 방향: 과소표시도 할루시네이션과 동일하게 금지). GFA/공급 산정
        #   (sec2, 위)만 usable을 쓰고 land_prices는 이 gross 값을 쓴다.
        sec3 = self._calc_land_prices(base, land_area_gross)
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

        # Section 8: 종상향/종변경 잠재력(예상치 — 현행 실효 용적률과 분리)
        # ★integrated(인접성·필지수) 전달 — 파편 다필지 종상향 랭킹 인접성 게이트 배선.
        sec8 = self._calc_upzoning(base, zone_type, land_area, sec6, sec7, integrated)

        result = {
            "address": address,
            "pnu": base.get("pnu"),
            "zone_type": zone_type,
            "land_area_sqm": land_area,
            # ★P0-2(c)/F2 land_area_sqm(개발규모=usable 기준)의 산출 근거 — 정직 표기(additive).
            #   ★F2: 면적 기준 이원화(취득원가 gross vs 개발규모 usable)를 dict로 병기한다.
            #   gfa_basis는 기존 문자열 그대로(하위 신규 필드라 호환 우려 없음 — 이번 세션 신설).
            "land_area_basis": {
                "gfa_basis": land_area_basis,
                "land_cost_basis": "gross(전체 매입대상 면적 — 도로·구거·하천·개발불가 게이트 필지도 매입 대상이라 제외하지 않음)",
                "gross_sqm": land_area_gross,
                "usable_sqm": land_area,
            },
            # 통합집계 산물(다필지 시) — 프론트 통합 카드·인터프리터 그라운딩용. 단일/미제공은 None.
            "integrated_zoning": integrated,
            "parcel_count": (integrated or {}).get("parcel_count") if integrated else (len(parcels) if parcels else 1),
            "effective_far": sec1,
            "supply_areas": sec2,
            "land_prices": sec3,
            "transaction_prices": sec4,
            "sale_prices": sec5,
            "location": sec6,
            "development_plans": sec7,
            "upzoning": sec8,
            "upzoning_scenarios": sec8.get("scenarios", []),
            "potential_far_range": sec8.get("potential_far_range"),
            "analyzed_at": datetime.now().isoformat(),
            "llm_config": {
                "provider": llm_provider or "anthropic",
                "model": llm_model,
            },
            "warnings": base.get("warnings", []),
        }

        # ── P0-3(RC6) 법정초과 할루시네이션 가드 핫패스 배선 — 공용 헬퍼(★A-3/G8) 경유 ──
        #   run_range_checks(다중 도메인 검증 — 무거움) 대신 check_against_legal만 경량 직접
        #   호출한다(hotpath_guard.apply_legal_hotpath_guard로 표준화 — comprehensive이 이
        #   패턴의 정본이었고, 이제 다른 분석 표면도 동일 헬퍼를 재사용한다). P0-1이 근본원인
        #   (zone 미매칭 하드코딩 폴백)을 제거했으므로 이 가드는 벨트&브레이스(다른 경로로
        #   법정초과 값이 흘러들어와도 정직 경고로 표면화). 무날조: 값 자체는 몰래 클램프하지
        #   않는다 — additive(integrity_warnings 신설, 기존 키 불변). sec1은 result["effective_far"]와
        #   동일 객체 참조이므로 confidence_target mutation이 곧바로 result에 반영된다(동작 불변).
        from app.services.verification.hotpath_guard import apply_legal_hotpath_guard

        apply_legal_hotpath_guard(
            result,
            zone_type=zone_type, bcr_pct=sec1.get("effective_bcr_pct"), far_pct=sec1.get("effective_far_pct"),
            regulation_payload=base, plan_payload=base.get("special_districts"),
            confidence_target=sec1,
        )

        # ── Stage 1: 건축가능항목 선정·랭킹(인허가가능성 × 가용용적률) — additive·graceful ──
        #   현행 실효 용적률(sec1)과 종상향 시나리오(sec8)를 결합해 '이 부지에서 무엇을 지을
        #   수 있는가'를 사업유형별로 랭킹한다(별표 허용용도를 결정입력으로 승격). AI 해석 전에
        #   부착해 인터프리터도 건축가능항목을 그라운딩하게 한다(무회귀: 실패는 무손상).
        try:
            from app.services.land_intelligence.buildable_options import (
                rank_buildable_options,
            )

            _bo = rank_buildable_options(
                zone_type=zone_type,
                effective_far_pct=sec1.get("effective_far_pct"),
                upzoning=sec8,
            )
            # Stage 3 가산: 상위 사업유형에 유사 설계 도면(참조 라이브러리)을 첨부해 시장조사
            #   미리보기를 제공한다(가산만·무회귀, 검색 실패는 graceful). top 2만 — latency 절제.
            try:
                from app.services.land_intelligence.similar_market_service import (
                    attach_similar_designs_to_options,
                )

                _bo["options"] = await attach_similar_designs_to_options(
                    _bo.get("options") or [], zone_type=zone_type,
                    area_sqm=land_area, top_n=2,
                )
                if _bo.get("options"):
                    _bo["top_recommendation"] = _bo["options"][0]
            except Exception:  # noqa: BLE001 — 유사도면 가산 실패는 무손상(옵션은 유지)
                pass
            result["buildable_options"] = _bo
        except Exception:  # noqa: BLE001 — 건축가능항목 산출 실패는 기존 분석 무손상
            pass

        # ── 특이부지 감지(학교·GB·농지·산지·맹지·문화재 등) — ★LLM 그라운딩용 배선 ──
        #   감사 적발(orphan handoff): 종합분석이 special_parcel을 결과에 넣지 않아
        #   site_analysis_interpreter가 특이제약을 인지 못하고 '최대 연면적 가능'류를 독자
        #   서술하는 할루시네이션 위험. 여기서 감지해 result에 부착하면 인터프리터가 그라운딩한다.
        try:
            _lr = base.get("land_register") if isinstance(base.get("land_register"), dict) else {}
            _sp_input = {
                "zone_type": zone_type,
                "land_category": _lr.get("land_category") or "",
                "special_districts": base.get("special_districts")
                or (sec7.get("special_districts") if isinstance(sec7, dict) else [])
                or [],
                "road_contact": base.get("road_contact"),
                "road_width_m": base.get("road_width_m") or _lr.get("road_width_m"),
                # ★road_width_source 동반 — 위 _gate_sp_input과 동일 계약(폭만 넘기면 출처 소실).
                "road_width_source": base.get("road_width_source") or _lr.get("road_width_source"),
            }
            # T1/T2/T3 실배선 — 임야/산지 후보만 관측데이터 3종을 병렬 조회해 전달:
            #   terrain_facts(DEM 경사도)·slope_criteria(조례 경사도 기준)·forest_data(산림청 임목축적).
            #   각 헬퍼가 실패·비후보·미프로비저닝을 자체 None 처리(무날조 정직 게이트) → gather는
            #   예외 없이 완주. 미확보는 각각 None=현행 완전 동일. 게이트 판정은 E-gate 소유(전달만).
            _addr = base.get("address") or address
            # return_exceptions=True(사내 패턴 정합) — 헬퍼는 자체가드로 None을 주지만, 만약의
            # 예외도 분석 전체를 끊지 않도록 개별 결과를 None으로 치환한다(무손상 하드닝).
            _facts = await asyncio.gather(
                _fetch_terrain_facts(_addr, _pnu, _sp_input),
                _fetch_slope_criteria(_addr, _sp_input),
                _fetch_forest_data(_pnu, _sp_input),
                return_exceptions=True,
            )
            _terrain_facts, _slope_criteria, _forest_data = (
                r if not isinstance(r, BaseException) else None for r in _facts
            )
            special = _detect_special_parcel_compat(
                _sp_input, _terrain_facts, _forest_data, _slope_criteria
            )
            if special:
                result["special_parcel"] = special
                _warns = result.get("warnings")
                result["warnings"] = (_warns if isinstance(_warns, list) else []) + special.get("warnings", [])
                result["developability"] = special.get("developability")
            # ── WP-B: 개발행위허가 절차게이트(국토계획법 §56~58) additive 부착 ──
            #   자연녹지 등 비도시·녹지 지역이 밀도한도만으로 '개발가능'으로 오고지되던 과대낙관을
            #   봉합한다. 이미 확보한 관측데이터(_slope_criteria·_terrain_facts)를 그대로 넘겨
            #   경사도 예비판정까지 흐르게 한다(실패는 무손상 graceful).
            try:
                from app.services.permit.dev_act_permit_gate import assess_dev_act_permit

                _dev_gate = assess_dev_act_permit(
                    _sp_input,
                    slope_criteria=_slope_criteria,
                    terrain_facts=_terrain_facts,
                    sigungu=_extract_sigungu_from_address(_addr),
                )
                if _dev_gate:
                    result["dev_act_permit_gate"] = _dev_gate
            except Exception:  # noqa: BLE001 — 개발행위허가 게이트 실패는 무손상(기존 분석 유지)
                pass

            # ── WP-A: 접도·도로 기반(P4) access_basis additive 부착 ──
            #   종합분석 result에 접도 판정(legal/physical/emergency 3상태)을 동봉해, 인터프리터가
            #   맹지·자루형·막다른도로·접도구역 등 접근 제약을 그라운딩할 수 있게 한다(위 WP-B와
            #   동일 additive·graceful 패턴). vworld road_side(이미 조회된 land_register 산출)
            #   어댑터로 road_contact를 파생하고, 다필지 세트면 인접(⑳ _parcel_adjacency) 완화신호도
            #   함께 넘긴다(항목3 — 대표필지 맹지라도 자기세트 내 인접 도로접 필지가 있으면 완화).
            try:
                from app.services.access.access_basis_service import (
                    adapt_vworld_access_fields,
                    assess_access,
                )

                _access_input = dict(_sp_input)
                _access_input.update(
                    adapt_vworld_access_fields(_lr, _access_input.get("special_districts"))
                )
                if integrated is not None:
                    _access_input["multi_parcel_adjacency"] = integrated.get("adjacency")
                result["access_basis"] = assess_access(
                    _access_input, sigungu=_extract_sigungu_from_address(_addr),
                ).model_dump()
            except Exception:  # noqa: BLE001 — 접도 게이트 실패는 무손상(기존 분석 유지)
                pass
        except Exception:  # noqa: BLE001 — 특이부지 감지 실패는 무손상(기존 분석 유지)
            pass

        # ── 허용 건축물(별표 SSOT) 화면 배선 — 국토계획법 시행령 별표2~20 ──
        #   감사 적발(커버리지 갭): 화면은 permit_validator(M코드)만 소비해, 자연녹지 등
        #   비주거·비상업 용도지역에서 별표(예: 자연녹지 별표17: 단독주택·제1종근생·종교·교육·수련)
        #   허용건축물 상세가 화면에 안 나왔다. development_type_analyzer(별표 단일SSOT)를 소비해
        #   allowed_buildings를 가산한다(additive·무회귀 — 실패는 기존 분석 무손상).
        #   ★전역: 녹지·관리 등 모든 용도지역이 별표 허용건축물을 얻는다(M코드만이면 상세 누락).
        try:
            from app.services.zoning import development_type_analyzer

            _dev_types = development_type_analyzer.analyze(
                zone_type=zone_type,
                land_area_sqm=land_area,
                effective_far_pct=effective_far,
                effective_bcr_pct=effective_bcr,
            )
            result["allowed_buildings"] = {
                "zone_type": zone_type,
                "source": "국토계획법 시행령 별표2~20(허용 건축물)",
                "allowed_types": _dev_types.get("allowed_types", []),
                "restricted_types": _dev_types.get("restricted_types", []),
                "recommended_type": _dev_types.get("recommended_type"),
                "recommendation_reason": _dev_types.get("recommendation_reason"),
                "legal_basis": _dev_types.get("legal_basis"),
            }
        except Exception:  # noqa: BLE001 — 허용 건축물 배선 실패는 무손상(기존 분석 유지)
            pass

        # ── 전역정책 Phase0: 근거·법령링크·신선도 공용 블록(additive, graceful) ──
        # 용적률/건폐율 법정·조례·실효 한도를 근거 트레이스 + 레지스트리 법령링크로 부착해
        # "용적률 200%가 왜 나왔나"에 법령 원문까지 답한다(EvidencePanel 소비). AI 해석 전에
        # 부착해 인터프리터도 그라운딩하게 한다(setdefault — 기존 키 있으면 보존).
        try:
            _ev_block = _build_site_evidence_block(result)
            result.setdefault("evidence", _ev_block.get("evidence", []))
            result.setdefault("legal_refs", _ev_block.get("legal_refs", []))
            result.setdefault("provenance", _ev_block.get("provenance", []))
        except Exception:  # noqa: BLE001 — 근거 블록 부착 실패는 무손상
            pass

        # ── 시니어 자문 모세혈관 배선(P0·최다트래픽) — deliberation(심의)·urban·legal ──
        # 시니어 전문가 판단프레임워크·근거(법조문 citation)를 result에 첨부해 메인 분석에
        # 흐르게 한다. AI 해석 전에 부착해 인터프리터도 그라운딩(전문가 판단기준 인지)한다.
        # ★정량 verdict 핵심(입력매핑 정교화): 종합분석은 정비사업 입력(비례율·동의율)이 보통 없어
        #   urban/legal evaluator는 verdict=None(프레임워크·citation만)이었다. 실효 용적률/건폐율과
        #   법정상한을 심의위원 CSP(delib.multi_clause_csp)에 actual/limit으로 매핑하면 준수=PASS·
        #   초과=BLOCK 실판정이 산출된다(build_compliance_inputs 공용 빌더로 DRY 매핑).
        # ★무회귀: with_senior=True 기본이되 attach_senior_consultation_multi는 절대 raise 안 함.
        if with_senior:
            try:
                from app.services.senior_agents.consultation_hook import (
                    attach_senior_consultation_multi,
                    build_compliance_inputs,
                )

                # 심의 CSP 입력(실효 far/bcr=설계 적용값 actual, 법정상한=limit). 한도는 실효가
                # min(법정,조례)이므로 법정상한(national_*) 초과 여부로 위반을 판정한다. 법정상한이
                # 없으면 실효값을 한도로 자급평가(actual=limit → 준수 PASS)한다.
                _far_eff = sec1.get("effective_far_pct")
                _bcr_eff = sec1.get("effective_bcr_pct")
                _far_lim = sec1.get("national_far_pct") or _far_eff
                _bcr_lim = sec1.get("national_bcr_pct") or _bcr_eff
                _road_w = base.get("road_width_m") if isinstance(base, dict) else None
                if (isinstance(base, dict) and not _road_w
                        and isinstance(lr, dict)):
                    _road_w = lr.get("road_width_m")
                _sr_inputs: dict[str, Any] = build_compliance_inputs(
                    far_actual=_far_eff, far_limit=_far_lim,
                    bcr_actual=_bcr_eff, bcr_limit=_bcr_lim,
                    road_width_actual=_road_w,
                )
                # 정비사업 비례율·동의율 입력(있을 때만) — sec8 종상향/정비 시나리오에 실릴 수 있음.
                for _k in (
                    "post_appraisal_total", "total_project_cost", "prior_appraisal_total",
                    "prior_appraisal_individual", "member_sale_price",
                    "consent_owner_count", "total_owner_count",
                    "consent_area_sqm", "total_area_sqm", "redevelopment_type",
                ):
                    _v = base.get(_k) if isinstance(base, dict) else None
                    if _v is not None:
                        _sr_inputs[_k] = _v
                result["senior_consultation"] = attach_senior_consultation_multi(
                    ["deliberation", "urban", "legal"], _sr_inputs,
                )
            except Exception:  # noqa: BLE001 — 시니어 자문 첨부 실패는 메인 분석 무손상
                pass

        # Phase 3: AI 해석 생성 (선택적 — API 키 있을 때만)
        # llm_provider/llm_model이 지정된 경우 get_llm()으로 커스텀 LLM 생성
        custom_llm = None
        if llm_provider:
            try:
                from app.services.ai.llm_provider import get_llm
                custom_llm = get_llm(
                    provider=llm_provider,
                    model=llm_model,
                )
            except Exception as e:
                logger.warning(
                    "커스텀 LLM 생성 실패, 기본 프로바이더로 폴백",
                    provider=llm_provider,
                    model=llm_model,
                    error=str(e),
                )

        try:
            from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter
            interpreter = SiteAnalysisInterpreter()
            if custom_llm is not None:
                interpreter._llm = custom_llm
            ai_interpretation = await interpreter.generate_interpretation(result, prior_context=prior_block)
            result["ai_interpretation"] = ai_interpretation
        except Exception as e:
            logger.warning("AI 해석 생성 스킵", error=str(e))
            result["ai_interpretation"] = None

        # Phase 4: 시장분석 AI 내러티브 생성 (선택적 — API 키 있을 때만)
        # ★D-1(정직화) additive: 실패 시 None만 두면 프론트가 "정상인데 비어있음"과
        # "생성 자체가 실패함"을 구분할 수 없다. market_interpretation_status로 사유를 병기한다
        # (기존 market_interpretation 키·값은 완전히 그대로 — 이 필드는 순수 추가).
        try:
            from app.services.ai.market_interpreter import MarketInterpreter
            market_interpreter = MarketInterpreter()
            if custom_llm is not None:
                market_interpreter._llm = custom_llm
            market_interpretation = await market_interpreter.generate_interpretation(result, prior_context=prior_block)
            result["market_interpretation"] = market_interpretation
            result["market_interpretation_status"] = {"status": "ok"}
        except Exception as e:
            logger.warning("시장분석 AI 해석 생성 스킵", error=str(e))
            result["market_interpretation"] = None
            result["market_interpretation_status"] = {
                "status": "unavailable",
                "reason": f"{type(e).__name__}: {str(e)[:160]}",
            }

        # Phase 1 성장루프: prior 첨부(주입 증거) + write-back(다음 회차 prior가 됨, best-effort)
        result["prior_analysis"] = prior
        from app.services.ledger import analysis_ledger_service as ledger
        from app.services.ledger import lineage
        from app.services.ledger.contradiction import detect_contradictions

        wb_payload = {
            "kind": "site_analysis", "schema_version": "site_analysis/v1",
            "zone_type": result.get("zone_type"),
            "effective_far": result.get("effective_far"),
            "land_area_sqm": result.get("land_area_sqm"),
            "potential_far_range": result.get("potential_far_range"),
            "findings_brief": [
                {"check_id": "ZONE", "status": "info",
                 "current": (result.get("effective_far") or {}).get("effective_far_pct"),
                 "limit": None},
            ],
        }
        # Phase 2: prior 대비 결정론 모순 표면화(판정/수치 불변 — 비교 전용)
        contradictions = detect_contradictions(prior, wb_payload)
        result["contradictions"] = contradictions

        wb = await ledger.append_analysis(
            analysis_type="site_analysis", payload=wb_payload,
            tenant_id=tenant_id, pnu=_pnu, address=address, project_id=project_id,
            source="comprehensive", created_by=None,
        )
        # ★성장루프 조인키: 원장 content_hash 를 응답 최상위 `ledger_hash` 로 노출
        #   (공용 헬퍼 — 프론트 피드백 👍/👎 → learning_loop 등가조인. 미적재 시 키 생략).
        ledger.attach_ledger_hash(result, wb)
        # Phase 2: 파생 lineage 엣지(child=이번 write-back, parent=prior) — best-effort
        if (prior and prior.get("content_hash") and wb.get("ok")
                and not wb.get("unchanged") and wb.get("content_hash")):
            await lineage.record_edge(
                child_hash=wb["content_hash"], child_type="site_analysis",
                parent_hash=prior["content_hash"],
                parent_type=prior.get("analysis_type", "site_analysis"),
                tenant_id=tenant_id,
                contradiction_count=len(contradictions["contradictions"]),
                max_severity=contradictions["max_severity"],
            )
        # 주: 종합분석은 중심엔진 shadow 대상 제외 — 플랫폼에 FAR/BCR '적합 verdict'가 없고 effective_far가
        # 합법 완화로 법정상한을 정당 초과할 수 있어 verdict 합성이 거짓 발산을 낳음(shadow_mappers 주석 참조).

        # ★분석 반영(동기·전수감사 #2): SpecialistAgent 결정론 교차검증(zoning 허용용도·far 실효검증
        #   + 심의/설계 게이트) 결과를 result["specialists"]에 동기 수집해 화면에 반영한다. 그간 아래
        #   .delay(fire-and-forget)만 있어 결과가 분석에 미반영이던 갭을 해소한다. 비동기 성장뇌 적재
        #   (.delay)와 분리·병행: 동기 수집=화면 교차검증, .delay=노하우 적재. 실패는 graceful(무손상).
        try:
            from app.core.config import get_settings as _get_settings
            from app.services.agents.specialist_dispatch import (
                build_sync_specialist_domains,
                run_specialist_domains,
            )

            _engine_set = bool((getattr(_get_settings(), "DELIBERATION_ENGINE_URL", "") or "").strip())
            # ★A2 additive: pnu·land_area(대지면적)를 심의/설계 엔진 입력 조립에 실전달(engine_inputs
            #   공용 빌더가 use_zone·calc_targets에 사용). land_area는 기존에도 far 도메인에는
            #   전달돼 있었으나 심의/설계에는 미도달이었다(build_sync_specialist_domains 내부에서 소비).
            _sync_domains = build_sync_specialist_domains(
                zone_type=zone_type, base=base, land_area=land_area,
                address=address, engine_set=_engine_set, pnu=_pnu,
            )
            # ★A5 과금 게이트: 종합분석은 결정론 교차검증만 유지하고 allow_llm=False로 LLM 해석을
            #   스킵한다(결정론 findings·prior·recall·원장 cite는 무영향). LLM 해석(과금)은
            #   decision_brief의 use_llm 경로 전용 — 여기서 이중 과금하지 않는다(정책 명기).
            _specialists = await run_specialist_domains(
                _sync_domains, tenant_id=tenant_id, project_id=project_id,
                pnu=_pnu, address=address, allow_llm=False,
            )
            if _specialists:
                result["specialists"] = _specialists
        except Exception as e:  # noqa: BLE001 — 교차검증 동기 반영 실패는 분석 무손상(정직 degrade)
            logger.warning("종합분석 specialist 동기 교차검증 스킵(graceful)", err=str(e)[:160])

        # 성장 뇌(MemoryHub) 비동기 적재(.delay): 위 동기 교차검증(zoning/far[/심의/설계])이
        #   SpecialistAgent.run을 거치며 이미 MemoryHub ingest를 발화하므로, 여기선 동기 미커버 도메인(market)만
        #   비동기 적재한다(★중복 ingest 방지 — 동기/비동기를 도메인 단위로 정확히 분리).
        #   market은 공시지가 의존이라 화면 교차검증 대상에서 제외(무목업)하되 노하우 적재는 수행.
        try:
            _op = (sec3 or {}).get("official_price_per_sqm")
            if isinstance(_op, (int, float)) and not isinstance(_op, bool) and _op > 0:
                from app.tasks.specialist_tasks import dispatch_domain_specialists
                dispatch_domain_specialists({
                    "domains": {"market": {"official_price_per_sqm": _op}},
                    "tenant_id": tenant_id, "project_id": project_id,
                    "pnu": _pnu, "address": address,
                })
        except Exception as e:  # noqa: BLE001 — 성장 뇌 트리거 실패는 분석을 막지 않음(정직 degrade)
            logger.warning("종합분석 specialist(market) 적재 스킵(graceful)", err=str(e)[:160])

        return result

    async def _integrated_context(self, parcels: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        """다필지 통합 컨텍스트(모듈 공개 함수 build_integrated_context로 위임 — SSOT)."""
        return await build_integrated_context(parcels)

    # ────────────────────────────────────────────
    # Section 1: 실효용적률 산정 (단일출처 far_tier_service 위임)
    # ────────────────────────────────────────────
    def _calc_effective_far(self, base: dict, zone_type: str, land_area: float = 0) -> dict[str, Any]:
        from app.services.land_intelligence import far_tier_service
        return far_tier_service.calc_effective_far(base, zone_type, land_area)

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
        # ★리뷰 HIGH: 미등재 용도지역은 '허용유형 없음'이 아니라 판정불가 — 빈 섹션 대신 정직 고지.
        if not permitted and not permitted_types_known(zone_type):
            return [{"development_type": None, "type_name": "판정불가",
                     "note": f"'{zone_type}' 인허가 매트릭스 미등재 — 허용유형 판정불가"
                             "(국토계획법 시행령 별표 확인 필요)"}]
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

            # 개발방식별 적합성 분석 설명 생성
            suitability_note = self._generate_suitability_note(
                dev_type, type_name, zone_type, land_area,
                applied_far, effective_bcr, unit_count, floor_count, total_gfa,
            )

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
                "suitability_note": suitability_note,
                **self._validate_feasibility(
                    dev_type, type_name, zone_type, land_area,
                    effective_far, effective_bcr, unit_count, total_gfa, floor_count,
                ),
            })

        return sorted(results, key=lambda x: x["permit_complexity"])

    def _generate_suitability_note(
        self,
        dev_type: str, type_name: str, zone_type: str, land_area: float,
        applied_far: float, effective_bcr: float,
        unit_count: int, floor_count: int, total_gfa: float,
    ) -> str:
        """개발방식별 적합성을 자연어로 설명."""
        notes: list[str] = []

        # 대지 규모 적합성
        if land_area < 200:
            if dev_type in ("M10", "M11", "M13"):
                notes.append(f"대지면적 {land_area:,.0f}㎡로 {type_name}에 적합한 소규모 필지입니다.")
            else:
                notes.append(f"대지면적 {land_area:,.0f}㎡는 {type_name} 사업에 다소 협소할 수 있습니다.")
        elif land_area < 1000:
            notes.append(f"대지면적 {land_area:,.0f}㎡로 {type_name} 중소규모 사업이 가능합니다.")
        else:
            notes.append(f"대지면적 {land_area:,.0f}㎡로 {type_name} 대규모 사업에 유리합니다.")

        # 용적률 활용도
        typical = TYPICAL_FAR.get(dev_type, 250)
        if applied_far < typical * 0.7:
            notes.append(
                f"해당 용도지역의 실효 용적률({applied_far:.0f}%)이 "
                f"{type_name} 통상 기준({typical:.0f}%) 대비 낮아 사업성 검토가 필요합니다."
            )
        elif applied_far >= typical:
            notes.append(
                f"실효 용적률({applied_far:.0f}%)이 {type_name} 통상 기준을 충족하여 "
                f"용적률 측면에서 양호합니다."
            )

        # 세대수/층수 규모감
        if unit_count > 0 and dev_type not in ("M10", "M11"):
            notes.append(f"예상 {unit_count}세대, 지상 {floor_count}층 규모입니다.")

        return " ".join(notes)

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
        except Exception as e:  # noqa: BLE001
            # W2-13: 검증엔진 예외를 실제 판정처럼 보이는 "조건부"로 둔갑시키지 않음 —
            # "검증불가" + 오류 사유로 정직 표기(프론트는 미지정 상태 기본 스타일로 렌더).
            logger.warning("유형별 법규검증 실패 — 검증불가 표기", dev_type=dev_type, err=str(e)[:160])
            return {
                "feasibility_status": "검증불가",
                "validation_error": str(e)[:120],
                "conditions_met": [], "blocking_issues": [], "recommendations": [],
            }

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

    # 지역별 공시지가 대비 시세 보정계수
    # 공시지가 현실화율(2025 기준)의 역수 + 지역 프리미엄 반영
    # - 서울 강남권: 공시지가 현실화율 약 50~65% → 보정계수 1.5~2.0배
    # - 서울 비강남권: 공시지가 현실화율 약 65~80% → 보정계수 1.2~1.5배
    # - 경기 주요시(성남/용인/화성 등): 현실화율 약 70~85% → 보정계수 1.1~1.4배
    # - 기타 지방: 현실화율 약 80~90% → 보정계수 1.0~1.2배
    MARKET_MULTIPLIER_MAP: dict[str, float] = {
        # 서울 강남권 (공시지가 대비 시세 괴리가 큰 지역)
        "강남구": 1.8, "서초구": 1.7, "송파구": 1.6, "용산구": 1.6,
        # 서울 주요 주거·상업지역
        "마포구": 1.5, "성동구": 1.5, "광진구": 1.4, "영등포구": 1.4,
        "동작구": 1.4, "강동구": 1.4,
        # 서울 기타
        "관악구": 1.3, "구로구": 1.3, "금천구": 1.2,
        "노원구": 1.3, "도봉구": 1.2, "중랑구": 1.2, "강북구": 1.2,
        "성북구": 1.3, "은평구": 1.2, "서대문구": 1.3,
        "종로구": 1.5, "중구": 1.5, "양천구": 1.3, "강서구": 1.3,
        # 경기 주요시
        "성남시": 1.4, "분당": 1.5, "판교": 1.6,
        "수원시": 1.3, "용인시": 1.3, "화성시": 1.2,
        "고양시": 1.3, "일산": 1.3,
        "의정부시": 1.2, "남양주시": 1.2, "구리시": 1.3,
        "파주시": 1.1, "양주시": 1.1,
        "안양시": 1.3, "안산시": 1.2, "시흥시": 1.2,
        "김포시": 1.2, "광명시": 1.4, "하남시": 1.4,
        "부천시": 1.2, "광주시": 1.2,
        # 광역시
        "해운대구": 1.4, "수영구": 1.3,
        "연수구": 1.3, "송도": 1.4,
    }
    MARKET_MULTIPLIER_REGION: dict[str, float] = {
        "서울특별시": 1.4, "서울": 1.4,
        "경기도": 1.2, "경기": 1.2,
        "인천광역시": 1.2, "인천": 1.2,
        "부산광역시": 1.2, "부산": 1.2,
        "대구광역시": 1.15, "대전광역시": 1.15,
        "광주광역시": 1.1, "울산광역시": 1.15,
        "세종특별자치시": 1.2, "제주특별자치도": 1.15,
    }

    def _get_market_multiplier(self, address: str) -> tuple[float, str]:
        """주소 기반 공시지가→시세 보정계수 산정.

        Returns:
            (보정계수, 산정 근거 설명)
        """
        for district, mult in self.MARKET_MULTIPLIER_MAP.items():
            if district in address:
                return mult, (
                    f"{district} 지역의 공시지가 현실화율(약 {100/mult:.0f}%)을 반영한 "
                    f"보정계수 {mult}배를 적용하였습니다."
                )
        for region, mult in self.MARKET_MULTIPLIER_REGION.items():
            if region in address:
                return mult, (
                    f"{region} 평균 공시지가 현실화율을 기반으로 "
                    f"보정계수 {mult}배를 적용하였습니다."
                )
        return 1.2, "지역별 세부 보정계수가 미등록되어 전국 평균 보정계수 1.2배를 적용하였습니다."

    def _calc_land_prices(self, base: dict, land_area: float) -> dict[str, Any]:
        prices = base.get("official_prices", [])
        latest = prices[0] if prices else {}
        price_per_sqm = int(latest.get("price_per_sqm", 0) or 0)

        lr = base.get("land_register") or {}
        if not price_per_sqm:
            price_per_sqm = int(lr.get("official_price_per_sqm", 0) or 0)

        address = base.get("address", "")
        market_multiplier, multiplier_rationale = self._get_market_multiplier(address)
        estimated_market = int(price_per_sqm * market_multiplier)

        # 분석 주석 생성
        annotations: list[str] = []
        if price_per_sqm > 0:
            annotations.append(
                f"개별공시지가 ㎡당 {price_per_sqm:,}원 "
                f"(평당 {int(price_per_sqm * 3.305785):,}원)이 확인되었습니다."
            )
            annotations.append(multiplier_rationale)
            annotations.append(
                f"추정 시세는 ㎡당 {estimated_market:,}원 "
                f"(평당 {int(estimated_market * 3.305785):,}원)이며, "
                f"실제 거래 시 입지·접도·형상 등에 따라 차이가 발생할 수 있습니다."
            )
            if land_area > 0:
                total_est = int(estimated_market * land_area)
                annotations.append(
                    f"대지면적 기준 추정 토지가액은 약 {total_est / 100_000_000:,.1f}억원입니다."
                )
        else:
            annotations.append(
                "개별공시지가가 조회되지 않았습니다. 토지대장 미등록 또는 비과세 필지일 수 있습니다."
            )

        return {
            "official_price_per_sqm": price_per_sqm,
            "official_price_per_pyeong": int(price_per_sqm * 3.305785),
            "total_official_value_won": int(price_per_sqm * land_area),
            "estimated_market_per_sqm": estimated_market,
            "estimated_market_per_pyeong": int(estimated_market * 3.305785),
            "total_estimated_value_won": int(estimated_market * land_area),
            "market_multiplier": market_multiplier,
            "source": "VWORLD 개별공시지가 + 지역별 시세보정",
            "annotations": annotations,
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
                amounts = [
                    int(item.get("price_10k_won") or str(item.get("거래금액", "0")).replace(",", "").strip() or 0)
                    for item in raw
                    if item.get("price_10k_won") or item.get("거래금액")
                ]
                _s = robust_price_stats(amounts)  # ★대표통계(이상치 제거·공용 헬퍼)
                result[key] = {
                    "count": _s["count"],
                    "avg_price_10k": _s["avg"],
                    "max_price_10k": _s["max"],
                    "min_price_10k": _s["min"],
                    "excluded_outliers": _s["excluded"],
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
        # ★리뷰 HIGH: 미등재 용도지역은 판정불가 정직 고지(빈 섹션 금지) — _calc_supply_areas와 동일.
        if not permitted and not permitted_types_known(zone_type):
            return [{"development_type": None, "type_name": "판정불가",
                     "note": f"'{zone_type}' 인허가 매트릭스 미등재 — 허용유형 판정불가"
                             "(국토계획법 시행령 별표 확인 필요)"}]
        base_price = self._get_base_price(address)

        results = []
        for dev_type in permitted:
            if dev_type not in SALE_PRICE_MULTIPLIER:
                # 침묵 폴백 금지: 미등록 개발유형은 감지 가능하도록 경고 후 1.0 적용
                logger.warning(
                    "분양가 보정계수 미등록 개발유형 — 기본값 1.0 폴백",
                    dev_type=dev_type,
                )
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
        base.get("address", "")

        subway = infra.get("nearest_subway")
        schools = infra.get("schools", [])

        # 입지 점수 산정 (100점 만점)
        # 기본점수 50점 + 교통접근성 최대 25점 + 교육환경 최대 15점 + 지역보정 최대 10점
        score = 50
        score_breakdown: list[str] = ["기본 입지점수 50점"]

        if subway:
            dist = subway.get("distance_m", 9999)
            station_name = subway.get("name", "")
            if dist < 300:
                score += 25
                score_breakdown.append(
                    f"역세권 최우수 — {station_name} 도보 {dist}m (약 {dist // 80}분), "
                    f"초역세권으로 교통 접근성 최고 등급 (+25점)"
                )
            elif dist < 500:
                score += 20
                score_breakdown.append(
                    f"역세권 우수 — {station_name} 도보 {dist}m (약 {dist // 80}분), "
                    f"도보 통근 가능 거리 (+20점)"
                )
            elif dist < 1000:
                score += 10
                score_breakdown.append(
                    f"역세권 보통 — {station_name} 도보 {dist}m (약 {dist // 80}분), "
                    f"도보 접근은 가능하나 다소 거리 있음 (+10점)"
                )
            else:
                score_breakdown.append(
                    f"비역세권 — 최근접 역 {station_name} {dist}m, "
                    f"대중교통 접근성이 낮아 차량 의존도가 높을 수 있음 (+0점)"
                )
        else:
            score_breakdown.append(
                "반경 2km 내 지하철역 미확인 — 비역세권으로 교통 접근성 점수 미부여 (+0점)"
            )

        if len(schools) >= 3:
            score += 15
            school_names = ", ".join(s.get("name", "") for s in schools[:3])
            score_breakdown.append(
                f"학군 우수 — 반경 1km 내 학교 {len(schools)}개소 "
                f"({school_names} 등), 학부모 수요 높을 것으로 판단 (+15점)"
            )
        elif len(schools) >= 1:
            score += 10
            score_breakdown.append(
                f"학군 보통 — 반경 1km 내 학교 {len(schools)}개소, "
                f"기본적 교육 인프라 확보 (+10점)"
            )
        else:
            score_breakdown.append(
                "반경 1km 내 학교 미확인 — 교육 인프라 점수 미부여 (+0점)"
            )

        final_score = min(100, score)
        grade = "A" if final_score >= 80 else "B" if final_score >= 60 else "C" if final_score >= 40 else "D"
        grade_desc = {
            "A": "우수 입지 — 역세권·학군 모두 양호하여 주거·상업 개발 모두 유리",
            "B": "양호 입지 — 교통 또는 교육 인프라 중 하나 이상 양호",
            "C": "보통 입지 — 기반 인프라 보완이 필요하며, 개발 유형 선정 시 주의",
            "D": "취약 입지 — 대중교통·학교 접근이 어려워 특수 개발(물류, 공장 등) 검토 권장",
        }

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
            "location_score": final_score,
            "grade": grade,
            "grade_description": grade_desc.get(grade, ""),
            "score_breakdown": score_breakdown,
        }

    # ────────────────────────────────────────────
    # Section 7: 주변 개발계획
    # ────────────────────────────────────────────
    # 규제 지역명 → 개발 영향 해석
    REGULATION_INTERPRETATION: dict[str, str] = {
        "대공방어협조구역": (
            "대공방어협조구역에 포함되어 군부대 협의가 필요합니다. "
            "건축물 높이가 제한될 수 있으며, 사업 인허가 시 국방부 협의 절차가 추가됩니다."
        ),
        "비행안전구역": (
            "비행안전구역으로 건축물 높이가 엄격히 제한됩니다. "
            "공항·비행장 인근 지역으로 항공법에 따른 높이 제한 검토가 필수입니다."
        ),
        "폐기물매립시설": (
            "폐기물매립시설 설치제한지역에 포함됩니다. "
            "환경영향평가가 필요할 수 있으며, 주거개발 시 민원 리스크가 존재합니다."
        ),
        "상수원보호구역": (
            "상수원보호구역으로 개발이 극히 제한됩니다. "
            "음식점·숙박시설 등 오염 유발 시설은 원칙적으로 불허됩니다."
        ),
        "개발제한구역": (
            "개발제한구역(그린벨트)에 포함되어 건축행위가 극히 제한됩니다. "
            "해제 여부 및 해제 가능성을 별도로 검토해야 합니다."
        ),
        "경관지구": (
            "경관지구로 지정되어 건축물의 높이·형태·색채 등이 제한될 수 있습니다. "
            "해당 지자체의 경관 심의를 거쳐야 합니다."
        ),
        "고도지구": (
            "고도지구로 지정되어 건축물 높이가 최고 또는 최저로 제한됩니다. "
            "고층 개발이 제한될 수 있어 용적률 소진에 영향을 줍니다."
        ),
        "방화지구": (
            "방화지구로 지정되어 건축물은 내화구조 의무 적용 대상입니다. "
            "공사비가 상승할 수 있습니다 (건축법 제58조)."
        ),
        "군사시설보호": (
            "군사시설보호구역에 포함되어 군부대 협의 없이 건축이 불가합니다. "
            "인허가 소요 기간이 길어질 수 있습니다."
        ),
        "문화재보호": (
            "문화재보호구역으로 문화재청 협의가 필요합니다. "
            "발굴 조사비 부담 및 사업 지연 리스크가 있습니다."
        ),
        "자연공원": (
            "자연공원구역에 포함되어 개발이 크게 제한됩니다. "
            "자연공원법에 따른 행위 허가를 별도로 받아야 합니다."
        ),
        "도시자연공원": (
            "도시자연공원구역에 포함됩니다. "
            "공원 해제 절차를 거치지 않으면 건축이 불가합니다."
        ),
    }

    def _research_dev_plans(self, base: dict) -> dict[str, Any]:
        districts = base.get("special_districts", [])
        land_use = base.get("land_use_plan")

        regulations: list[str] = []
        if isinstance(land_use, dict):
            for d in land_use.get("districts", []):
                if isinstance(d, dict):
                    regulations.append(d.get("district_name", ""))
        elif isinstance(land_use, list):
            for d in land_use:
                if isinstance(d, dict):
                    regulations.append(d.get("district_name", ""))

        # ★D-2(정직화) 중복 제거(순서 보존) — VWorld가 동일 designation을 중복 반환할 때
        # land_use_regulations·regulation_notes·risk_factors가 그대로 중복 표시되던 문제.
        # dict.fromkeys는 삽입 순서를 보존하면서 중복만 제거한다(첫 등장 순서 그대로).
        clean_regulations = list(dict.fromkeys(r for r in regulations if r))

        # 각 규제에 대한 해석 주석 생성
        regulation_notes: list[dict[str, str]] = []
        for reg_name in clean_regulations:
            interpretation = None
            for keyword, note in self.REGULATION_INTERPRETATION.items():
                if keyword in reg_name:
                    interpretation = note
                    break
            regulation_notes.append({
                "name": reg_name,
                "interpretation": interpretation or "",
            })

        # 종합 개발 리스크 평가
        risk_keywords = {
            "개발제한구역": "극히 높음",
            "상수원보호구역": "극히 높음",
            "군사시설보호": "높음",
            "대공방어협조구역": "보통",
            "비행안전구역": "보통",
            "폐기물매립시설": "보통",
            "고도지구": "보통",
            "경관지구": "낮음",
            "방화지구": "낮음",
        }
        risk_level = "낮음"
        risk_factors: list[str] = []
        for reg_name in clean_regulations:
            for keyword, level in risk_keywords.items():
                if keyword in reg_name:
                    risk_factors.append(f"{reg_name} ({level})")
                    if level == "극히 높음":
                        risk_level = "극히 높음"
                    elif level == "높음" and risk_level not in ("극히 높음",):
                        risk_level = "높음"
                    elif level == "보통" and risk_level == "낮음":
                        risk_level = "보통"

        # ★D-2(정직화) additive: 규제명 → verified 법령 링크. 기존 법령 레지스트리 자산
        # (legal_refs_for_districts — 토지이음 지역지구별 규제법령집 매핑, services/legal 계열)을
        # 그대로 재사용한다(임의 URL 조립 금지 — build_law_url은 이 함수 내부에서만 쓰인다).
        # 매핑되는 법령키가 없으면 link=None(정직 — 근거 없는 링크 날조 금지).
        land_use_regulations_detail = self._build_land_use_regulations_detail(clean_regulations)

        return {
            "special_districts": districts,
            "land_use_regulations": clean_regulations,
            "land_use_regulations_detail": land_use_regulations_detail,
            "regulation_notes": regulation_notes,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "source": "VWORLD 토지이용계획",
        }

    @staticmethod
    def _build_land_use_regulations_detail(regulation_names: list[str]) -> list[dict[str, Any]]:
        """규제명 목록 → [{name, link}] — link는 legal_reference_registry의 verified 키만 채택.

        기존 자산(legal_refs_for_districts, app/services/legal/legal_reference_registry.py —
        토지이음 지역지구별 규제법령집 매핑) 재사용. 매핑 실패·근거 미확인은 link=None(무날조).
        """
        if not regulation_names:
            return []
        try:
            from app.services.legal.legal_reference_registry import legal_refs_for_districts

            lookup = legal_refs_for_districts(regulation_names)
            refs_by_key = {r.get("key"): r for r in (lookup.get("refs") or [])}
            by_district = lookup.get("by_district") or {}
            detail: list[dict[str, Any]] = []
            for name in regulation_names:
                link: str | None = None
                for key in by_district.get(name) or []:
                    ref = refs_by_key.get(key)
                    if ref and ref.get("url_status") == "verified":
                        link = ref.get("url")
                        break
                detail.append({"name": name, "link": link})
            return detail
        except Exception as e:  # noqa: BLE001 — 링크 매핑 실패는 무손상(link=None 정직 폴백)
            logger.warning("규제 법령링크 매핑 실패(graceful)", err=str(e)[:160])
            return [{"name": n, "link": None} for n in regulation_names]

    # ────────────────────────────────────────────
    # Section 8: 종상향/종변경 잠재력(예상치)
    # ────────────────────────────────────────────
    def _calc_upzoning(
        self,
        base: dict,
        zone_type: str,
        land_area: float,
        location: Any = None,
        dev_plans: Any = None,
        integrated: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """현행 실효 용적률과 분리된 종상향/종변경 잠재 시나리오(단일출처 위임).

        ★확정버그 수정(P0): far_tier_service.calc_upzoning은 parcel_count·adjacency_contiguous를
        이미 받을 수 있었으나(다필지 인접성 게이트) 이 호출부가 인자를 전달하지 않아 항상
        기본값(1·None)만 넘어가 UpzoningPotentialAnalyzer의 인접성 감점이 무발동이었다(파편
        9필지+개발제한구역 혼합에서 "종상향 가능성 상·1순위"가 산출되던 실버그). integrated
        (build_integrated_context가 이미 재사용 가능하게 부착한 adjacency_contiguous·
        parcel_count — 재계산 금지)를 전달만 하면 된다. 단일필지(integrated=None)는 기존과
        동일(parcel_count=1·adjacency_contiguous=None, 무회귀).
        """
        from app.services.land_intelligence import far_tier_service
        _parcel_count = int((integrated or {}).get("parcel_count") or 1)
        _adjacency_contiguous = (integrated or {}).get("adjacency_contiguous")
        return far_tier_service.calc_upzoning(
            base, zone_type, land_area, location, dev_plans,
            parcel_count=_parcel_count, adjacency_contiguous=_adjacency_contiguous,
        )


# ────────────────────────────────────────────
# 다필지 통합 컨텍스트 — 플랫폼 공용 진입점(SSOT)
# ────────────────────────────────────────────

async def build_integrated_context(parcels: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """필지목록(면적·용도지역 보유) → 면적가중 통합 용도/실효한도/GFA 집계.

    ★플랫폼 공용 단일경유(SSOT): /zoning/integrated-analysis와 동일한
    _enrich_effective_and_special(필지별 실효=조례+법정+특이 in-place)
    + _aggregate_integrated_zoning(면적가중)을 재사용한다(중복산식 0).
    종합분석뿐 아니라 파이프라인·수지(Top3)·90초진단·의사결정브리프 등
    다필지를 받는 모든 분석 진입점이 이 함수를 통해 통합 컨텍스트를 얻는다.
    프론트가 이미 면적·용도지역을 제공하면 재수집 없이 경량으로 동작하고,
    N=1은 항등(단일필지값과 동일)이라 단일/다필지가 한 경로로 일원화된다.
    실패는 graceful None(호출측은 단일 경로로 무회귀 폴백).

    ★F5(QA REQUEST CHANGES) 스코프 정리 — 반환 dict의 adjacency/usable/
    land_area_effective_sqm(P0-2 신설)는 이 함수를 호출하는 모든 소비처에 공통으로
    실린다(구조상 additive 키라 전 소비처가 받는다). 다만 그 값을 실제로 land_area
    산정에 '채택'하는 것은 현재 comprehensive_analysis_service.analyze()뿐이다.
    rough_feasibility_orchestrator.build_rough_scenario·feasibility_service_v2·
    pipeline.py는 여전히 integrated["total_area_sqm"](gross)만 land_area로 채택한다
    (usable/adjacency 필드는 받되 미소비 — 과대 주장 금지). usable 채택을 이 소비처들
    에도 확장하는 것은 후속 P1 스코프다.
    """
    # ★다필지 parcels 계약 공용 정규화(SSOT) — str[]/dict[] 양 shape 를 canonical dict[] 로 수렴.
    #   기존 인라인 camelCase↔snake 키맵(_f 포함)을 parcel_normalize.normalize_parcels 로 이관했다
    #   (byte-동일 이관 — 재작성 아님). dict 는 원본 키 보존+정본 snake 오버레이(merge)라 통합집계
    #   산출값은 무회귀(집계는 snake 키만 읽음). str 요소도 {address} 로 승격돼 수용된다
    #   (과거: isinstance(dict) 필터가 str 을 무음 드롭 → 빈 items → 단일필지 폴백으로 배선실수 은폐).
    #
    #   ★area 결측 행 처리(정직 축소): str→{address} 로 승격된 행은 area_sqm 이 없어 아래 필터에
    #     걸린다. 이 함수의 보강 경로(_enrich_effective_and_special)는 조례/법정한도·특이부지 게이트
    #     '전용'이라 주소로 area 를 조회하지 못한다(zone 전용 구조). 따라서 무리하게 신규 area 조회를
    #     만들지 않고 필터를 그대로 유지한다 = 오늘과 동일 동작(무악화). 승격 행은 str 을 dict 로
    #     받는 다른 엔드포인트(auto_zoning enrich_parcel_list 등, area 를 실제 조회)에서 보강된다.
    from app.services.land_intelligence.parcel_normalize import normalize_parcels

    items: list[dict[str, Any]] = [
        q for q in normalize_parcels(parcels) if (q.get("area_sqm") or 0) > 0
    ]
    if not items:
        return None
    try:
        from app.services.zoning.special_parcel import _aggregate_integrated_zoning

        # 실효치·법정 미보유 필지가 있으면(프론트 미보강) 라우터 공용 enrich로 보강(조례 1회캐시·순수계산).
        #   ★/zoning/integrated-analysis와 동일 산식 단일경유 — 보유 시 재계산 0(핫패스 경량).
        #   ★법정(_far_legal)만 결측인 경우(예: 지도픽이 farPct만 제공)도 보강 대상에 포함한다 —
        #   안 하면 아래 _aggregate의 blended가 실효는 그 필지를 포함하고 법정은 제외하는 부분집합 괴리로
        #   blended_법정 < blended_실효(상한<기준 자기모순)를 만든다.
        if any(
            (it.get("_far_eff") is None or it.get("_far_legal") is None) and it.get("zone_type")
            for it in items
        ):
            from apps.api.routers.auto_zoning import _enrich_effective_and_special
            await _enrich_effective_and_special(items)
        # ★부분집합 대칭 정규화(구조적 불변식 보장): _aggregate의 _blended는 실효/법정을 각 키 non-None
        #   필지만으로 독립 평균하므로, 두 값이 '같은 부분집합'에서 산출되려면 각 필지에서
        #   (_far_eff 유무) ⟺ (_far_legal 유무)가 성립해야 blended_법정 ≥ blended_실효가 보장된다.
        #   두 방향 모두 정규화한다(실효/건폐율 각각):
        #   ① 법정 결측·실효 존재 → 법정을 실효로 하한보정(법정≥실효이므로 안전, 필지 보존).
        #   ② 실효 결측·법정 존재 → 실효를 날조하지 않고 법정을 제외(양쪽 결측 처리, 실효 과대 방지).
        #   (①은 지도픽이 farPct만 줄 때, ②는 zone_type 없이 farLegalPct만 있을 때 발생 — 리뷰 P0/P1 봉합)
        for it in items:
            fe, fl = it.get("_far_eff"), it.get("_far_legal")
            if fe is not None and fl is None:
                it["_far_legal"] = fe
            elif fe is None and fl is not None:
                it["_far_legal"] = None
            be, bl = it.get("_bcr_eff"), it.get("_bcr_legal")
            if be is not None and bl is None:
                it["_bcr_legal"] = be
            elif be is None and bl is not None:
                it["_bcr_legal"] = None
        integrated = _aggregate_integrated_zoning(items)

        # ★F4(QA REQUEST CHANGES) 블라스트 격리: 아래 인접성·usable 신규 블록은 각자
        #   독립 try/except로 감싼다. 이전엔 이 블록이 위쪽의 큰 try에 그대로 딸려 있어,
        #   shapely 형상 파싱 실패 등 신규 로직에서 예외가 나면 바깥 except가 '통합집계
        #   전체'(blended_far_eff_pct 등 이미 완성된 _aggregate_integrated_zoning 결과까지)를
        #   버리고 None을 반환해 33필지→대표 763㎡ 단일필지 폴백 회귀를 재현할 위험이 있었다.
        #   신규 블록 실패는 해당 키만 None+사유로 정직 누락시키고 blended 통합집계는 보존한다.
        try:
            # ★P0-2(a)(RC2) 인접성(_parcel_adjacency) 결합 — geometry 보유 시 shapely 연결요소로
            #   판정한다. /zoning/integrated-analysis(routers/auto_zoning.py)와 동일 함수를
            #   재import(산식 복제 금지 — 위 _enrich_effective_and_special과 동일한 기존 임포트
            #   패턴). geometry 미보유(2개 미만)는 True를 지어내지 않고 None+사유로 정직 표기한다.
            geoms = [it.get("geometry") for it in items]
            present = [g for g in geoms if g]
            if len(present) < 2 and len(items) >= 2:
                integrated["adjacency"] = {
                    "contiguous": None, "components": None,
                    "basis": "형상(geometry) 데이터 부족 — 인접성 확인 불가(통합개발 가능 여부 미확정)",
                }
            else:
                from apps.api.routers.auto_zoning import _parcel_adjacency
                _adj = _parcel_adjacency(geoms)
                integrated["adjacency"] = {
                    "contiguous": _adj.get("contiguous"),
                    "components": _adj.get("components"),
                    "basis": _adj.get("note"),
                }
        except Exception as e:  # noqa: BLE001 — 인접성 산출 실패는 그 키만 정직 누락(통합집계 보존)
            logger.warning("인접성 산출 실패 — adjacency만 정직 누락(graceful)", err=str(e)[:160])
            integrated["adjacency"] = {
                "contiguous": None, "components": None, "basis": "인접성 산출 실패(정직 미확인)",
            }

        try:
            # ★WP-A 항목3 — 다필지 세트 구성원 도로접면 신호 집계(신규 조회 없음, items에 이미
            #   실려온 road_side/road_contact만 재사용). access_basis_service._multi_parcel_
            #   mitigation_factor의 입력(member_road_contact)으로 소비된다. 신호가 하나도 없으면
            #   None(정직 미상) — 과대낙관 폴백 금지.
            _road_signals: list[bool] = []
            for it in items:
                rc = it.get("road_contact")
                if isinstance(rc, bool):
                    _road_signals.append(rc)
                    continue
                rs = it.get("road_side")
                if rs:
                    _road_signals.append("맹지" not in str(rs))
            _member_road_contact: bool | None = any(_road_signals) if _road_signals else None
            integrated["adjacency"] = {
                **(integrated.get("adjacency") or {}), "member_road_contact": _member_road_contact,
            }
        except Exception as e:  # noqa: BLE001 — 신호 집계 실패는 그 키만 정직 누락(adjacency 본체 보존)
            logger.warning("다필지 도로접면 신호 집계 실패(graceful)", err=str(e)[:160])
            integrated["adjacency"] = {**(integrated.get("adjacency") or {}), "member_road_contact": None}

        # ★P0(종상향 랭킹 인접성 게이트 전파) 최상위 additive 노출 — 기존 adjacency 자산을
        #   그대로 재사용(재계산 금지)해 _calc_upzoning → UpzoningPotentialAnalyzer가 바로
        #   소비할 수 있는 얕은 키로 승격한다. integrated_zoning(응답 최상위)에도 그대로 실린다.
        integrated["adjacency_contiguous"] = (integrated.get("adjacency") or {}).get("contiguous")
        integrated["cluster_count"] = (integrated.get("adjacency") or {}).get("components")

        try:
            # ★P0-2(b)(RC3) 실사용가능용지 3계층(compute_usable_area) 결합 — 도로·구거·하천 지목은
            #   전액 제외(EXCLUDED_LAND_CATEGORIES), GB 등 BLOCKED 게이트 필지도 제외한다(게이트
            #   신호는 위 enrich가 붙인 _special을 special 키로 매핑해야 인식 — enrich 미실행 시엔
            #   지목 제외만 적용되고 게이트 제외는 정직하게 스킵된다). gross 전량 합산(RC3) 방지.
            from app.services.zoning.usable_area import compute_usable_area

            usable_input = []
            for it in items:
                ui = dict(it)
                sp = it.get("_special")
                if isinstance(sp, dict):
                    ui["special"] = sp
                usable_input.append(ui)
            _usable = compute_usable_area(usable_input)
            integrated["usable"] = {
                "confirmed_sqm": _usable.get("usable_confirmed_sqm"),
                "conditional_sqm": _usable.get("usable_conditional_sqm"),
                "excluded_sqm": _usable.get("excluded_sqm"),
                "excluded": _usable.get("excluded_parcels") or [],
                "warnings": _usable.get("warnings") or [],
            }
            # 실사용가능(confirmed) 면적이 산출되면 그것을, 아니면 gross(total_area_sqm)를 채택한다
            # (usable_confirmed_sqm=0은 '전부 제외/미확보'일 수 있어 gross 폴백 — 무날조 0 은닉 방지).
            _confirmed = integrated["usable"]["confirmed_sqm"]
            integrated["land_area_effective_sqm"] = (
                _confirmed if _confirmed and _confirmed > 0 else integrated.get("total_area_sqm")
            )
        except Exception as e:  # noqa: BLE001 — usable 산출 실패는 그 키만 정직 누락(통합집계 보존)
            logger.warning("usable 산출 실패 — usable만 정직 누락(graceful)", err=str(e)[:160])
            integrated["usable"] = None
            integrated["land_area_effective_sqm"] = None

        return integrated
    except Exception as e:  # noqa: BLE001 — 통합집계(_aggregate_integrated_zoning) 실패는 단일 경로로 폴백(분석 무중단)
        logger.warning("통합집계 실패 — 단일필지 경로로 폴백(graceful)", err=str(e)[:160])
        return None
