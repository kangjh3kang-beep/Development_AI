"""실효용적률 계층 산정 + 종상향 잠재 시나리오 — 단일출처(SSOT) 공용 모듈.

`ComprehensiveAnalysisService`(`/analysis/comprehensive`)와 `LandInfoService`
(`/zoning/comprehensive`·`/zoning/analyze` 화면경로)가 **동일 로직**을 공유하도록
모듈 레벨 함수로 추출한다(로직 복제 금지). 두 호출 모두 이 함수만 사용한다.

반환 필드는 프론트(site-analysis page.tsx, cf6dfda) 캡처 필드명과 정합:
- effective_far(객체, effective_far_pct·far_basis_detail 포함)
- upzoning(scenarios·potential_far_range 포함) / upzoning_scenarios / potential_far_range
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services.zoning.far_incentive_calculator import calculate as calc_far_incentive

logger = structlog.get_logger()


def calc_effective_far(base: dict, zone_type: str, land_area: float = 0) -> dict[str, Any]:
    """실효 용적률 계층(법정범위→조례→계획상한→인센티브) 산정.

    `base`는 LandInfoService.collect_comprehensive 결과(local_ordinance·zone_limits·
    special_districts 포함). far_basis_detail 메타를 동봉해 그라운딩/검증기가 활용한다.
    """
    ordinance = base.get("local_ordinance") or {}
    zone_limits = base.get("zone_limits") or {}

    # 법정상한 SSOT: zone_limits가 비어/누락이어도 용도지역명으로 법정값을 도출한다.
    # (과거 폴백 60/200은 자연녹지(법정 20/100)에 200%/60%를 지어내는 할루시네이션 원인이었음)
    from app.services.zoning.legal_zone_limits import (
        applicable_limits_for,
        legal_limits_for,
    )
    legal = legal_limits_for(zone_type) or {}
    legal_bcr = legal.get("max_bcr_pct")
    legal_far = legal.get("max_far_pct")
    legal_min_far = legal.get("min_far_pct")

    # ── 계층 적용 한도 산정: 법정범위 → 조례 적용값 → 도시·군관리계획/지구단위계획 상한.
    # base(local_ordinance/zone_limits)와 special_districts(계획 상한용적률)를 페이로드로 전달.
    applied = applicable_limits_for(
        zone_type,
        sigungu=(ordinance.get("sigungu") if isinstance(base.get("local_ordinance"), dict) else None),
        regulation_payload=base,
        plan_payload=base.get("special_districts"),
    ) or {}

    # ★법정(국토계획법) 상한은 '용도지역 라벨 기준 SSOT(legal_*)'를 최우선으로 채택한다.
    # (이전: 업스트림 zone_limits.max_*_pct를 먼저 신뢰 → 라벨과 불일치한 값(예: 일반상업지역에
    #  제1종주거값 60/200)이 그대로 표시되고 실효=min(200,800)=200으로 오염되는 버그.
    #  법정값은 용도지역명으로 결정되는 고정 상한이므로, 라벨에서 도출한 legal_*가 진실의 단일원천.)
    national_bcr = float(
        legal_bcr
        or zone_limits.get("max_bcr_pct")
        or zone_limits.get("bcr")
        or 60
    )
    national_far = float(
        legal_far
        or zone_limits.get("max_far_pct")
        or zone_limits.get("far")
        or 200
    )
    ordinance_bcr = float(ordinance.get("effective_bcr") or ordinance.get("ordinance_bcr") or national_bcr)
    ordinance_far = float(ordinance.get("effective_far") or ordinance.get("ordinance_far") or national_far)
    effective_bcr = min(national_bcr, ordinance_bcr)
    effective_far = min(national_far, ordinance_far)

    # ── 완화근거(basis) 인지: effective는 '법정값을 기본'으로 하되, 페이로드에 명시적
    #    완화근거/완화율이 있을 때만 상향을 반영한다(근거 없으면 법정값 유지).
    #    interpreter·검증기가 활용하도록 basis 메타를 동봉한다.
    from app.services.zoning.legal_zone_limits import (
        _has_relaxation_basis,
        SANITY_MULTIPLIER,
    )
    relaxation_ratio = (
        ordinance.get("relaxation_ratio_pct")
        or ordinance.get("완화율")
        or base.get("relaxation_ratio_pct")
    )
    basis_present = (
        relaxation_ratio is not None
        or _has_relaxation_basis(ordinance)
        or _has_relaxation_basis(base.get("special_districts"))
    )
    far_basis = "법정/조례"  # 기본: 법정값(조례 가감 반영)

    # ── 산정 계층: 1)법정범위 → 2)조례 적용값 → 3)도시·군관리계획/지구단위계획 상한 → 4)인센티브.
    ordinance_confirmed = bool(applied.get("ordinance_confirmed"))
    plan_far_ceiling = applied.get("plan_far_pct")
    # 기준 용적률(상한): 조례 적용값(있으면) > 법정범위 max(없으면, 확인필요 플래그).
    if ordinance_confirmed:
        far_basis = f"조례 적용값({applied.get('far_source') or '지자체 도시계획조례'})"
    # 도시·군관리계획/지구단위계획 상한용적률이 있으면 최우선(조례·법정 초과 정당).
    if plan_far_ceiling is not None:
        effective_far = max(effective_far, float(plan_far_ceiling))
        far_basis = "도시·군관리계획/지구단위계획 상한용적률(최우선 적용)"

    # 4) 인센티브 완화율(근거 있을 때만) — 상한용적률 cap.
    if basis_present and relaxation_ratio is not None:
        try:
            ratio = float(relaxation_ratio)
            # 완화율(%)을 기준 용적률에 반영하되 합리성 절대 상한(법정×배수) 내로 제한.
            relaxed = national_far * (1.0 + ratio / 100.0)
            cap = national_far * SANITY_MULTIPLIER
            effective_far = min(max(effective_far, relaxed), cap)
            far_basis = f"완화근거(완화율 {ratio:g}%) 반영"
        except (TypeError, ValueError):
            pass
    elif basis_present and plan_far_ceiling is None and not ordinance_confirmed:
        # 근거 키워드는 있으나 정량 완화율·조례·계획 미제시 → 법정값 유지(가능성만 안내).
        far_basis = "완화근거 명시(정량 완화율 미제시 — 별도 검토 필요)"

    # ★provenance 정직성: 조례 미확정(법정상한 폴백)이고 계획상한·완화근거도 없으면
    #   far_basis를 '법정상한 적용(조례 미확인)'으로 정직 표기한다(false-confirmed 방지).
    #   ordinance_service 3차 폴백(source='법정상한', recheck_recommended=True)을 신호로 인식.
    _ord_src = str(ordinance.get("source") or "")
    _ord_recheck = bool(ordinance.get("recheck_recommended"))
    if (
        not ordinance_confirmed
        and plan_far_ceiling is None
        and not basis_present
        and ("법정상한" in _ord_src or _ord_recheck)
    ):
        far_basis = "법정상한 적용(조례 미확인)"

    # ── far_basis 상세 메타: 산정 계층·데이터출처를 그라운딩/검증기가 활용하도록 동봉.
    far_basis_detail: dict[str, Any] = {
        "법정범위": {
            "min_far_pct": legal_min_far if legal_min_far is not None else national_far,
            "max_far_pct": legal_far if legal_far is not None else national_far,
            "max_bcr_pct": legal_bcr,
        },
        "조례값": (
            {
                "far_pct": applied.get("ordinance_far_pct"),
                "bcr_pct": applied.get("ordinance_bcr_pct"),
                "confirmed": ordinance_confirmed,
            }
            if ordinance_confirmed
            else None
        ),
        "계획상한": (
            {"far_pct": plan_far_ceiling, "bcr_pct": applied.get("plan_bcr_pct")}
            if plan_far_ceiling is not None
            else None
        ),
        "인센티브": (
            {"relaxation_ratio_pct": float(relaxation_ratio)}
            if (relaxation_ratio is not None)
            else None
        ),
        "최종근거": far_basis,
        "데이터출처": applied.get("sources") or ["법정범위"],
        "조례확인필요": not ordinance_confirmed and plan_far_ceiling is None,
    }

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

    # 분석 주석 생성 — 전문적 부동산 용어, 자연스러운 한국어
    source = ordinance.get("source", "법정상한")
    sido = ordinance.get("sido", "")
    sigungu = ordinance.get("sigungu", "")
    region_name = f"{sido} {sigungu}".strip() or "해당 지자체"

    annotations: list[str] = []
    annotations.append(
        f"국토계획법 시행령에 따른 {zone_type}의 법정 건폐율 상한은 {national_bcr}%, "
        f"법정 용적률 상한은 {national_far}%입니다."
    )

    if ordinance_far < national_far:
        diff_pct = national_far - ordinance_far
        annotations.append(
            f"{region_name} 도시계획 조례에서 용적률을 {ordinance_far}%로 규정하여, "
            f"법정상한 대비 {diff_pct:.0f}%p 낮게 적용됩니다. "
            f"이는 해당 지역의 도시계획 방향(기반시설 용량, 주거환경 보전 등)을 반영한 것입니다."
        )
    elif ordinance_far == national_far:
        annotations.append(
            f"{region_name}의 조례 용적률이 법정상한({national_far}%)과 동일하게 규정되어 있어, "
            f"별도의 조례 제한 없이 법정상한이 그대로 적용됩니다."
        )

    if ordinance_bcr < national_bcr:
        annotations.append(
            f"{region_name} 조례에서 건폐율을 {ordinance_bcr}%로 강화 적용하고 있습니다. "
            f"(법정상한 {national_bcr}% 대비 {national_bcr - ordinance_bcr:.0f}%p 축소)"
        )

    annotations.append(
        f"실효 용적률은 법정상한({national_far}%)과 조례({ordinance_far}%) 중 "
        f"낮은 값인 {effective_far}%가 적용되며, "
        f"실효 건폐율은 {effective_bcr}%입니다."
    )

    if land_area > 0:
        max_gfa = land_area * effective_far / 100
        max_bldg = land_area * effective_bcr / 100
        annotations.append(
            f"대지면적 {land_area:,.1f}㎡ 기준으로 최대 연면적 {max_gfa:,.1f}㎡ "
            f"(약 {max_gfa / 3.305785:,.0f}평), "
            f"최대 건축면적 {max_bldg:,.1f}㎡ (약 {max_bldg / 3.305785:,.0f}평)까지 "
            f"건축이 가능합니다."
        )

    if incentive.get("simulation_table"):
        base_far = incentive.get("base_far", effective_far)
        max_incentive_far = incentive.get("max_far", national_far)
        annotations.append(
            f"기부체납 활용 시 기본용적률 {base_far}%에서 최대 {max_incentive_far}%까지 "
            f"완화가 가능합니다 (국토계획법 시행령 제46조). "
            f"기부체납 비율에 따른 상세 시뮬레이션은 별도 섹션을 참조하세요."
        )

    return {
        "national_bcr_pct": national_bcr,
        "national_far_pct": national_far,
        "ordinance_bcr_pct": ordinance_bcr,
        "ordinance_far_pct": ordinance_far,
        "effective_bcr_pct": effective_bcr,
        "effective_far_pct": effective_far,
        "far_basis": far_basis,
        "far_basis_detail": far_basis_detail,
        "ordinance_confirmed": ordinance_confirmed,
        "legal_min_far_pct": legal_min_far if legal_min_far is not None else national_far,
        "legal_max_far_pct": legal_far if legal_far is not None else national_far,
        "relaxation_present": basis_present,
        "far_incentive": incentive,
        "source": source,
        "annotations": annotations,
        "far_optimization": simulate_far_optimization(zone_type, effective_far, national_far, land_area),
    }


def simulate_far_optimization(
    zone_type: str, effective_far: float, national_far: float, land_area: float,
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


def calc_upzoning(
    base: dict,
    zone_type: str,
    land_area: float,
    location: Any = None,
    dev_plans: Any = None,
    *,
    parcel_count: int = 1,
    adjacency_contiguous: bool | None = None,
) -> dict[str, Any]:
    """현행 실효 용적률과 **분리된** 종상향/종변경 잠재 시나리오(예상치)를 산출.

    규칙엔진(UpzoningPotentialAnalyzer)에 수집 데이터(면적·역세권·특수구역·시군구)를
    전달한다. 목표 용도지역의 조례 용적률은 OrdinanceService 캐시를 동기 resolver로 주입한다.

    다필지 통합분석에서는 통합 면적(land_area)과 함께 통합 필지수(parcel_count)·인접성
    (adjacency_contiguous)을 주입한다. 단일필지 경로는 기본값(1·None)으로 종전과 동일하게 동작한다
    (하위호환·무회귀). 통합 면적이 커져 종상향 경로의 최소면적을 충족하면 가능성이 상향된다.
    """
    try:
        from app.services.zoning.upzoning_potential import UpzoningPotentialAnalyzer

        ordinance = base.get("local_ordinance") or {}
        sigungu = ordinance.get("sigungu") if isinstance(ordinance, dict) else None

        # 역세권 여부(location 섹션의 nearest_subway). location 미전달 시 base.infrastructure 폴백.
        near_station = False
        near_station_m: float | None = None
        loc = location if isinstance(location, dict) else (base.get("infrastructure") or {})
        if isinstance(loc, dict):
            subway = (loc.get("transportation") or {}).get("nearest_subway") or loc.get("nearest_subway")
            if isinstance(subway, dict):
                near_station_m = subway.get("distance_m")
                if near_station_m is not None and near_station_m <= 500:
                    near_station = True

        special_districts = base.get("special_districts") or (
            dev_plans.get("special_districts") if isinstance(dev_plans, dict) else []
        )

        analyzer = UpzoningPotentialAnalyzer()
        return analyzer.analyze(
            zone_type=zone_type,
            land_area_sqm=land_area,
            sigungu=sigungu,
            near_station=near_station,
            near_station_m=near_station_m,
            adjacency_contiguous=adjacency_contiguous,
            parcel_count=parcel_count,
            special_districts=special_districts,
            ordinance_far_resolver=ordinance_far_cache_resolver,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("종상향 잠재력 분석 스킵", error=str(e))
        return {
            "current_zone": zone_type,
            "scenarios": [],
            "potential_far_range": None,
            "summary": "종상향 잠재력 분석을 일시적으로 산출하지 못했습니다.",
            "disclaimer": "예상치 미산출",
        }


def ordinance_far_cache_resolver(sigungu: str, zone_type: str) -> float | None:
    """목표 용도지역의 조례 용적률(%)을 OrdinanceService 정적 캐시에서 동기 조회.

    외부 API 없이 캐시(ORDINANCE_CACHE)만 사용한다(없으면 None → 법정범위 폴백).
    """
    try:
        from app.services.land_intelligence.ordinance_service import ORDINANCE_CACHE

        sig = sigungu or ""
        # 1) 시·군·구 키워드가 매칭되는 시·도 블록 우선.
        for sido, sido_block in ORDINANCE_CACHE.items():
            if sig and (sig in sido or sido in sig):
                z = sido_block.get(zone_type)
                if z and z.get("far"):
                    return float(z["far"])
        # 2) 폴백: 캐시에 해당 용도지역 조례가 있는 첫 블록.
        for sido_block in ORDINANCE_CACHE.values():
            z = sido_block.get(zone_type)
            if z and z.get("far"):
                return float(z["far"])
        return None
    except Exception:  # noqa: BLE001
        return None
