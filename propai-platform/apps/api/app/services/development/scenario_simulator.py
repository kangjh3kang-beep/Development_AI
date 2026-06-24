"""다각도 개발방식 시뮬레이션.

단일/다필지 부지에 대해 관련 개발정책의 적용요건을 판정하고, 정책별 예상 용적률·
적정 기부채납·실현성을 산정해 최적 사업방안을 제안한다. 어떤 정책도 적용되지 않으면
단순 건축(현 용도지역 한도 내) 추진방안으로 폴백한다.

대상 정책: 단순건축 / 지구단위계획 연계 / 도시개발사업(도시개발법) / 가로주택정비사업 /
모아주택(소규모주택정비) / 소규모재건축 / 역세권 활성화사업 / 역세권 장기전세주택 /
재개발·재건축(정비사업).

요건·수치는 일반 기준 기반 추정이며 정밀 산정은 지구단위계획·심의 단계 확인이 필요하다.
규칙기반 후보 생성 + LLM 종합·검증(하이브리드).
"""

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

PYEONG_SQM = 3.305785

# 정책별 매도청구권 — 동의요건 충족 시 미동의자(잔여)에 매도청구 가능.
# consent_pct=사업 추진 동의 임계, claimable_remainder=임계 충족 시 매도청구 가능한 잔여(=100-임계),
# basis=근거 법령. (실제 적용은 소유관계·동의현황·보유기간 등 현장확인 필요)
MAGDO_RULES: dict[str, dict[str, Any]] = {
    "재개발·재건축(정비사업)": {
        "consent_required": "조합설립: 토지등소유자 3/4 이상 + 토지면적 1/2 이상(재건축은 각 동 과반·전체 3/4·면적 3/4)",
        "consent_pct": 75,
        "basis": "도시 및 주거환경정비법 제64조(매도청구)",
        "note": "조합설립 동의 후 미동의 조합원·토지등소유자에게 매도청구",
    },
    "가로주택정비사업": {
        "consent_required": "토지등소유자 80% 이상 + 토지면적 2/3 이상(공동주택 각 동 과반)",
        "consent_pct": 80,
        "basis": "빈집 및 소규모주택 정비에 관한 특례법 제35조(매도청구)",
        "note": "사업시행 동의요건 충족 후 미동의자에게 매도청구",
    },
    "모아주택/모아타운": {
        "consent_required": "소규모재건축: 전체 3/4 이상 + 각 동 과반 + 토지면적 3/4 이상",
        "consent_pct": 75,
        "basis": "빈집 및 소규모주택 정비에 관한 특례법 제35조(매도청구)",
        "note": "동의요건 충족 후 미동의자 매도청구(모아타운 내 개별 소규모정비)",
    },
    "도시개발사업(도시개발법)": {
        "consent_required": "수용·사용방식: 토지면적 2/3 이상 + 토지소유자 총수 1/2 이상 동의",
        "consent_pct": 67,
        "basis": "도시개발법 제22조(토지등의 수용·사용) · 토지보상법",
        "note": "수용방식은 미동의 토지 수용(매도청구에 준함). 환지방식은 환지처분으로 갈음",
    },
    "역세권 장기전세주택(시프트)": {
        "consent_required": "대지 사용권원 95% 이상 확보(주택건설사업)",
        "consent_pct": 95,
        "basis": "주택법 제22조·제23조(매도청구)",
        "note": "95%↑ 확보→잔여 전부 매도청구 / 80~95%→10년 미만 보유 토지에 매도청구",
    },
    "지구단위계획 연계": {
        "consent_required": "주택건설사업: 대지 사용권원 95% 이상 확보",
        "consent_pct": 95,
        "basis": "주택법 제22조(매도청구)",
        "note": "지구단위 내 주택건설사업 시 95%↑ 확보→잔여 매도청구(80~95%는 10년 미만 보유분)",
    },
    "역세권 활성화사업": {
        "consent_required": "주택건설사업 준용: 대지 사용권원 95% 이상 확보",
        "consent_pct": 95,
        "basis": "주택법 제22조(매도청구) — 사업방식에 따라 정비/소규모정비 준용",
        "note": "용도상향 복합개발. 주택 포함 시 95%↑ 확보→잔여 매도청구",
    },
}


def _magdo(scheme: str) -> dict[str, Any] | None:
    """정책별 매도청구권 분석(동의요건·매도청구 가능 잔여 비율·근거)."""
    r = MAGDO_RULES.get(scheme)
    if not r:
        return None  # 단순건축 등 단일 사업주체/소유 → 매도청구 불요
    return {
        "consent_required": r["consent_required"],
        "consent_threshold_pct": r["consent_pct"],
        "claimable_remainder_pct": round(100 - r["consent_pct"], 1),
        "basis": r["basis"],
        "note": r["note"],
    }


# ── 사업방식 → 근거법령 키(legal_reference_registry) 매핑 ──
#   시나리오↔규범 일치(가산)용. 소규모정비특례법(가로주택·소규모재건축·자율주택·소규모재개발),
#   정비법(재개발·재건축·주거환경개선·공공정비), 도시개발법, 국토계획법(지구단위·입지규제최소),
#   결합건축(건축법), 리모델링(주택법) 등. 미매핑 방식은 빈 리스트(무해).
_SCHEME_LEGAL_KEYS: dict[str, list[str]] = {
    "단순 건축": ["building_permit", "zone_use"],
    "지구단위계획 연계": ["district_unit_plan"],
    "도시개발사업(도시개발법)": ["urban_dev_replot"],
    "가로주택정비사업": ["small_housing_overview", "small_housing_road_project", "small_housing_sell_claim"],
    "모아주택/모아타운": ["small_housing_overview", "small_housing_road_project", "small_housing_sell_claim"],
    "재개발·재건축(정비사업)": ["redev_impl", "redev_mgmt"],
    "자율주택정비사업": ["small_housing_overview", "small_housing_road_project"],
    "소규모재개발사업": ["small_housing_overview", "small_housing_road_project", "small_housing_sell_claim"],
    "소규모재건축사업": ["small_housing_overview", "small_housing_road_project", "small_housing_sell_claim"],
    "주거환경개선사업": ["redev_impl"],
    "공공재개발·공공재건축": ["redev_impl", "redev_mgmt"],
    "공동주택 리모델링": ["housing_approval"],
    "결합건축": ["bldg_far"],
    "입지규제최소구역": ["zone_use"],
    "도심복합개발사업": ["urban_complex"],
    "역세권 장기전세주택(시프트)": ["housing_approval"],
    "지구단위계획": ["district_unit_plan"],
    "대지조성사업": ["housing_approval"],
}


def _scheme_legal_refs(scheme: str) -> list[dict]:
    """사업방식별 근거법령(verified 딥링크) — 가산 필드. 미매핑/실패 시 빈 리스트(무해)."""
    keys = _SCHEME_LEGAL_KEYS.get(scheme or "")
    if not keys:
        return []
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs(keys)
    except Exception:  # noqa: BLE001
        return []


def _is_residential(zone: str) -> bool:
    return "주거" in (zone or "")


def _is_commercial(zone: str) -> bool:
    return "상업" in (zone or "") or "준주거" in (zone or "")


class DevelopmentScenarioSimulator:
    async def simulate(
        self,
        address: str,
        parcels: list[str] | None = None,
        site: dict[str, Any] | None = None,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        site = site or {}
        addrs = self._merge(address, parcels)
        multi = len(addrs) >= 2

        # 부지 정보 수집(단일/다필지)
        enriched, subway_m = await self._collect(addrs, site)
        total_area = sum(p.get("area") or 0 for p in enriched)
        # ★용적률 출처: 실효(현행·조례 반영)를 시나리오 기준으로 사용(결함A 교정).
        #   법정상한은 라벨 구분용으로 별도 보관.
        far_effective = self._blended_far(enriched, "max_far")
        far_legal = self._blended_far(enriched, "max_far_legal")
        zones = [p.get("zone") for p in enriched if p.get("zone")]
        primary_zone = zones[0] if zones else (site.get("zone_type") or "")
        near_station = (subway_m is not None and subway_m <= 500) or any(
            "역세권" in (p.get("zone") or "") for p in enriched
        )

        # ── 특이부지 게이트(orchestrator.recommend:66-84 패턴 복제·비대칭 해소) ──
        #   임야/산지/농지/GB/맹지/학교용지 등 비일상 토지에도 20개 시나리오를 찍어내던 결함B 차단.
        #   developability∈{BLOCKED} 또는 resolvable∈{NO}면 시나리오 생성 중단·정직고지(가짜 면적/규모 미산정).
        #   CONDITIONAL/PRECONDITION은 시나리오를 생성하되 경고·선행절차를 동반(아래 ctx로 전파).
        from app.services.zoning.special_parcel import (
            detect_multi_parcel,
            detect_special_parcel,
        )

        if multi:
            special_gate = detect_multi_parcel(enriched)
        else:
            sp = detect_special_parcel(enriched[0]) if enriched else None
            special_gate = sp  # None이면 일상 부지(특이 없음)

        if special_gate and (
            special_gate.get("developability") in {"BLOCKED"}
            or special_gate.get("resolvable") in {"NO"}
        ):
            # 후보생성 중단 — 가짜 개발규모/시나리오는 미산정(무목업). 다만 ★사용자 피드백:
            #   '개발 불가'로 끝내지 말고 인허가·도시계획 변경 등 '개발가능 방안(선행절차)'을 제시한다.
            #   special_parcel이 이미 보유한 resolution_paths·permit_prerequisites·alternatives·법령을
            #   추천 '방안'으로 surface(가짜 규모는 여전히 미산정 — 정직).
            disclosure = special_gate.get("honest_disclosure") or (
                "통상 절차로는 즉시 개발이 어려운 제약이 포함됩니다."
            )
            # 해결 방안 집계(게이트 resolution_paths + 각 factor permit_prerequisites + alternatives).
            methods, ref_keys, alternatives = self._resolution_from_gate(special_gate)
            try:
                from app.services.legal.legal_reference_registry import get_legal_refs
                method_refs = get_legal_refs(ref_keys) if ref_keys else []
            except Exception:  # noqa: BLE001
                method_refs = []
            # 추천: '개발 불가'가 아니라 '선행절차(도시계획 변경·인허가) 통과 시 개발 가능' 방안 제시.
            has_path = bool(methods)
            rec_scheme = ("특이부지 개발 — 선행절차(도시계획 변경·인허가) 방안" if has_path
                          else "현 제약상 통상 개발 불가 — 대안 검토")
            rec_reason = (disclosure + " 다만 아래 선행절차(인허가·도시계획 변경 등)를 거치면 개발이 가능할 수 있습니다."
                          if has_path else
                          disclosure + " 통상 개발경로가 막혀 있어, 대안(필지 제외·용도 재검토)을 검토하세요.")
            return {
                "site": {
                    "address": address, "region": self._region(address),
                    "multi": multi, "parcel_count": len(addrs),
                    "total_area_sqm": round(total_area, 1) if total_area else None,
                    "primary_zone": primary_zone, "zones": zones,
                    "special_parcel_gate": special_gate,
                },
                "special_parcel_gate": special_gate,
                "scenarios": [],  # 가짜 개발규모 시나리오는 미생성(무목업)
                "recommended": {
                    "scheme": rec_scheme,
                    "est_far": None,
                    "reason": rec_reason,
                },
                # ★개발가능 방안(선행절차) — 인허가·도시계획 변경 등 actionable 경로 + 법령(verified).
                "resolution_methods": methods,
                "resolution_legal_refs": method_refs,
                "alternatives": alternatives,
                "developable_via_precondition": has_path,
                "fallback_simple_build": None,
                "magdo_summary": None,
                "honest_disclosure": disclosure,
                "blocked": not has_path,  # 선행절차 경로가 있으면 완전 blocked 아님(조건부 가능).
            }

        # 인접성: 통합개발(합필/일단지)은 필지가 맞닿아야 가능
        adjacency = self._adjacency(enriched) if multi else {"contiguous": True, "components": 1, "note": "단일 필지"}
        integration_ok = adjacency.get("contiguous") is not False  # None(미상)은 허용하되 주의

        # 건축물 노후도·세대수·소유구분(실데이터)
        buildings = self._buildings(enriched)

        # 블록(주변 필지 일괄) 노후도 — 주거지역에서만(가로주택/모아/정비 노후요건)
        block = None
        if _is_residential(primary_zone):
            primary_coords = (enriched[0] or {}).get("coords") if enriched else None
            block = await self._block_aging(primary_coords, radius_m=100)

        ctx = {
            "address": address, "region": self._region(address),
            "multi": multi, "parcel_count": len(addrs),
            "total_area_sqm": round(total_area, 1) if total_area else None,
            "primary_zone": primary_zone, "zones": zones,
            # ★시나리오 산정 기준 = 실효 용적률(현행·조례 반영). 법정상한은 라벨 구분용으로 병기.
            "far_effective_blended": far_effective,
            "far_legal_blended": far_legal,
            "near_station_m": subway_m, "near_station": near_station,
            "adjacency": adjacency, "integration_feasible": integration_ok,
            "buildings": buildings, "block_aging": block,
            # 특이부지 게이트(통과/조건부) 결과 — CONDITIONAL/PRECONDITION이면 경고·선행절차 동반.
            "special_parcel_gate": special_gate,
            "parcels": [{"address": p.get("address"), "zone": p.get("zone"),
                         "area": p.get("area"), "max_far": p.get("max_far"),
                         "max_far_legal": p.get("max_far_legal"),
                         "owner_type": p.get("owner_type"), "bldg_year": p.get("bldg_year"),
                         "units": p.get("units")} for p in enriched],
        }

        scenarios = self._scenarios(ctx)
        # 적합도 정렬(가능>조건부>불가, est_far 내림차순)
        rank = {"가능": 0, "조건부": 1, "불가": 2}
        scenarios.sort(key=lambda s: (rank.get(s["applicable"], 3), -(s.get("est_far") or 0)))
        applicable = [s for s in scenarios if s["applicable"] in ("가능", "조건부")]
        recommended = applicable[0] if applicable else next(
            s for s in scenarios if s["scheme"] == "단순 건축"
        )

        # 매도청구 요약(추천안 기준 + 다필지 잔여 추정)
        magdo_summary = self._magdo_summary(recommended, ctx)

        result: dict[str, Any] = {
            "site": ctx,
            "scenarios": scenarios,
            "recommended": {"scheme": recommended["scheme"], "est_far": recommended.get("est_far"),
                            "reason": recommended.get("notes") or recommended.get("pros", [""])[0]},
            "fallback_simple_build": next(s for s in scenarios if s["scheme"] == "단순 건축"),
            "magdo_summary": magdo_summary,
            # ★평수 티어 매트릭스(소규모 필지 가능/조건부/불가 상세 분류) — 순수 additive 뷰.
            "pyeong_classification": self._classify_by_pyeong_tier(total_area, scenarios),
        }
        # 특이부지가 조건부/선행절차 부지면 정직 고지를 최상위로 노출(시나리오는 산정하되 경고 동반).
        #   산지전용·농지전용·도시계획시설 폐지 등 선행절차 통과를 전제로만 개발 가능함을 명시.
        if special_gate and special_gate.get("developability") in (
            "CONDITIONAL", "PRECONDITION", "CAUTION"
        ):
            result["special_parcel_gate"] = special_gate
            result["honest_disclosure"] = special_gate.get("honest_disclosure") or (
                "특이 토지특성으로 인허가·전용·도시계획 변경 등 선행절차 통과를 조건으로만 개발이 가능합니다. "
                "아래 시나리오의 개발규모는 선행절차 통과를 전제로 한 잠재치입니다."
            )
        if use_llm:
            result["ai"] = await self._llm(ctx, scenarios)
        return result

    # ── 부지 수집 ──
    @staticmethod
    def _merge(address: str, parcels: list[str] | None) -> list[str]:
        out: list[str] = []
        for a in [address, *(parcels or [])]:
            a = (a or "").strip()
            if a and a not in out:
                out.append(a)
        return out

    async def _collect(self, addrs: list[str], site: dict) -> tuple[list[dict], float | None]:
        import asyncio

        from app.services.zoning.auto_zoning_service import AutoZoningService, ZONE_LIMITS

        az = AutoZoningService()

        from app.services.external_api.building_registry_service import BuildingRegistryService
        from app.services.external_api.vworld_service import VWorldService

        vworld = VWorldService()
        breg = BuildingRegistryService()

        from app.services.land_intelligence.far_tier_service import calc_effective_far
        from app.services.land_intelligence.ordinance_service import OrdinanceService

        _ord_svc = OrdinanceService()

        async def one(a: str) -> dict:
            try:
                r = await az.analyze_by_address(a)
                zl = r.get("zone_limits") or {}
                # 법정상한(라벨/ZONE_LIMITS 기준) — 별도 보관(라벨 구분용).
                far_legal = zl.get("max_far_pct") or zl.get("max_far")
                if not far_legal and r.get("zone_type"):
                    lim = ZONE_LIMITS.get((r["zone_type"] or "").replace(" ", ""))
                    far_legal = lim.get("max_far") if lim else None
                # ★실효 용적률(현행 baseline·조례 반영) — orchestrator._baseline_far와 동일 SSOT.
                #   법정상한만 쓰던 결함A 교정. 조회 실패/미산정 시 법정상한으로 폴백(회귀0).
                zone_type = r.get("zone_type") or ""
                far = far_legal
                if zone_type:
                    # ★조례 실효 반영 — local_ordinance가 비면 calc_effective_far가 법정값을 반환하므로,
                    #   OrdinanceService로 조례 한도를 조회해 주입(permits/parcels-info와 동일 — 서울 제1종 150 등 실효).
                    try:
                        ordinance = await _ord_svc.get_ordinance_limits(a, zone_type)
                    except Exception:  # noqa: BLE001 — 조례 조회 실패는 법정 폴백(정직)
                        ordinance = None
                    try:
                        eff = calc_effective_far(
                            {
                                "zone_limits": zl,
                                "special_districts": r.get("special_districts") or [],
                                "local_ordinance": ordinance or {},
                            },
                            zone_type,
                            r.get("land_area_sqm") or 0,
                        )
                        eff_far = eff.get("effective_far_pct")
                        if eff_far is not None and eff_far > 0:
                            far = float(eff_far)
                    except Exception:  # noqa: BLE001
                        pass
                pnu = r.get("pnu")
                coords = r.get("coordinates") or {}
                geometry = None
                owner_type = None
                try:
                    if pnu:
                        li = await vworld.get_land_info(pnu)
                        if li:
                            geometry = li.get("geometry")
                            owner_type = (li.get("properties") or {}).get("owner_type")
                    if geometry is None and coords.get("lat") and coords.get("lon"):
                        pp = await vworld.get_parcel_by_point(coords["lat"], coords["lon"])
                        geometry = pp.get("geometry") if pp else None
                except Exception:  # noqa: BLE001
                    pass
                # 건축물대장(노후도·세대수)
                bldg_year = units = None
                structure = None
                try:
                    if pnu:
                        b = await breg.get_title_by_pnu(pnu) or await breg.get_building_by_pnu(pnu)
                        if b:
                            ud = (b.get("use_approval_date") or "")[:4]
                            bldg_year = int(ud) if ud.isdigit() else None
                            units = b.get("household_count") or b.get("ho_count") or 0
                            structure = b.get("structure")
                except Exception:  # noqa: BLE001
                    pass
                return {"address": a, "zone": r.get("zone_type"),
                        "area": r.get("land_area_sqm"),
                        "max_far": far,            # 실효 용적률(현행·조례 반영) — 시나리오 산정 기준
                        "max_far_legal": far_legal,  # 법정상한(라벨 구분용)
                        "pnu": pnu, "geometry": geometry, "owner_type": owner_type,
                        "bldg_year": bldg_year, "units": units, "structure": structure,
                        "coords": coords,
                        # ── 특이부지 게이트 입력 키(detect_special_parcel/detect_multi_parcel 정합) ──
                        "land_category": r.get("land_category") or "",
                        "special_districts": r.get("special_districts") or [],
                        "zone_limits": zl,
                        "official_price_per_sqm": r.get("official_price_per_sqm"),
                        # 접도 미확보 → None(맹지 오탐 방지). orchestrator._enrich_context와 동일 정책.
                        "road_contact": None, "road_width_m": None,
                        # 게이트는 zone_type 키로 읽으므로 동봉(zone과 동일값).
                        "zone_type": r.get("zone_type") or ""}
            except Exception:  # noqa: BLE001
                return {"address": a, "zone": None, "area": None, "max_far": None,
                        "max_far_legal": None, "geometry": None,
                        "land_category": "", "special_districts": [], "zone_limits": {},
                        "official_price_per_sqm": None, "road_contact": None,
                        "road_width_m": None, "zone_type": ""}

        enriched = await asyncio.gather(*[one(a) for a in addrs])
        enriched = list(enriched)
        # 주 필지 인근 지하철 거리(comprehensive)
        subway_m = None
        try:
            from app.services.land_intelligence.land_info_service import LandInfoService

            comp = await LandInfoService().collect_comprehensive(addrs[0])
            infra = comp.get("infrastructure") or {}
            ns = infra.get("nearest_subway") if isinstance(infra, dict) else None
            if isinstance(ns, dict):
                subway_m = ns.get("distance_m")
            # 면적/용도 보강
            if not enriched[0].get("area") and comp.get("land_area_sqm"):
                enriched[0]["area"] = comp["land_area_sqm"]
            if not enriched[0].get("zone") and comp.get("zone_type"):
                enriched[0]["zone"] = comp["zone_type"]
        except Exception:  # noqa: BLE001
            pass
        return enriched, subway_m

    @staticmethod
    def _adjacency(parcels: list[dict]) -> dict[str, Any]:
        """필지 인접성 판정 — 통합개발(합필/일단지)은 필지가 맞닿아야 가능.

        shapely로 각 필지 폴리곤 간 거리를 계산해 연결요소(그룹) 수를 구한다.
        contiguous=True면 모든 필지가 하나로 연결(통합개발 가능).
        """
        geoms = [p.get("geometry") for p in parcels]
        present = [g for g in geoms if g]
        if len(present) < 2:
            return {"contiguous": True, "components": 1, "checked": len(present),
                    "note": "단일 필지"}
        try:
            from shapely.geometry import shape

            polys = []
            for g in geoms:
                try:
                    polys.append(shape(g).buffer(0) if g else None)
                except Exception:  # noqa: BLE001
                    polys.append(None)
            idx = [i for i, p in enumerate(polys) if p is not None]
            if len(idx) < 2:
                return {"contiguous": None, "components": None, "checked": len(idx),
                        "note": "필지 형상 데이터 부족 — 인접성 확인 불가(현장 확인 필요)"}
            TOL_DEG = 0.00006  # 약 6m(공유경계 정밀오차·세도로 허용)
            n = len(idx)
            parent = list(range(n))

            def find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            for a in range(n):
                for b in range(a + 1, n):
                    if polys[idx[a]].distance(polys[idx[b]]) <= TOL_DEG:
                        parent[find(a)] = find(b)
            comps = len({find(i) for i in range(n)})
            return {
                "contiguous": comps == 1,
                "components": comps,
                "checked": n,
                "note": "모든 필지가 맞닿아 통합개발 가능" if comps == 1
                else f"{comps}개 그룹으로 분리 — 비인접 필지는 통합개발(합필/일단지) 불가",
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("인접성 분석 실패", err=str(e)[:80])
            return {"contiguous": None, "components": None, "checked": len(present),
                    "note": "인접성 분석 실패 — 현장/지적도 확인 필요"}

    @staticmethod
    def _buildings(parcels: list[dict]) -> dict[str, Any]:
        """건축물 노후도·세대수·소유구분 집계(실데이터). 노후 기준: RC/철골 30년, 그 외 20년."""
        from datetime import datetime

        year_now = datetime.now().year
        with_b = [p for p in parcels if p.get("bldg_year")]
        old = 0
        ages: list[int] = []
        for p in with_b:
            yr = p.get("bldg_year")
            age = year_now - int(yr)
            ages.append(age)
            st = p.get("structure") or ""
            thr = 30 if any(k in st for k in ("철근", "철골", "RC", "SRC", "콘크리트")) else 20
            if age >= thr:
                old += 1
        total_units = sum(int(p.get("units") or 0) for p in with_b)
        owner_types = sorted({p.get("owner_type") for p in parcels if p.get("owner_type")})
        return {
            "buildings_found": len(with_b),
            "old_count": old,
            "old_ratio": round(old / len(with_b), 2) if with_b else None,
            "avg_age": round(sum(ages) / len(ages)) if ages else None,
            "oldest_age": max(ages) if ages else None,
            "total_units": total_units or None,
            "owner_types": owner_types or None,
            "note": "1필지=1대표건축물 기준(블록 전체 노후도는 현장확인 필요)",
        }

    @staticmethod
    async def _block_aging(coords: dict | None, radius_m: int = 100, max_parcels: int = 40) -> dict[str, Any] | None:
        """블록(주변 필지 일괄) 노후도 집계 — 가로주택/모아/정비 노후·불량 2/3 요건 판정용.

        대상 좌표 중심 bbox 내 필지(VWorld)를 가져와 각 필지 건축물 사용승인일로
        노후건물 비율을 산정한다(API 부하 제한: 반경·필지수 상한).
        """
        if not coords or not coords.get("lat") or not coords.get("lon"):
            return None
        import asyncio
        from datetime import datetime

        from app.services.external_api.building_registry_service import BuildingRegistryService
        from app.services.external_api.vworld_service import VWorldService

        lat, lon = coords["lat"], coords["lon"]
        dlat = radius_m / 111000.0
        import math as _m

        dlon = radius_m / (111000.0 * max(0.3, _m.cos(_m.radians(lat))))
        vworld = VWorldService()
        try:
            parcels = await vworld.get_parcels_in_bbox(
                lon - dlon, lat - dlat, lon + dlon, lat + dlat, max_count=max_parcels
            )
        except Exception:  # noqa: BLE001
            return None
        pnus = [p.get("pnu") for p in (parcels or []) if p.get("pnu")][:max_parcels]
        if not pnus:
            return None

        breg = BuildingRegistryService()
        sem = asyncio.Semaphore(8)
        year_now = datetime.now().year

        async def age_of(pnu: str):
            async with sem:
                try:
                    b = await breg.get_title_by_pnu(pnu)
                except Exception:  # noqa: BLE001
                    return None
                if not b:
                    return None
                ud = (b.get("use_approval_date") or "")[:4]
                if not ud.isdigit():
                    return None
                st = b.get("structure") or ""
                thr = 30 if any(k in st for k in ("철근", "철골", "RC", "SRC", "콘크리트")) else 20
                return {"age": year_now - int(ud), "old": (year_now - int(ud)) >= thr,
                        "units": int(b.get("household_count") or b.get("ho_count") or 0)}

        results = [r for r in await asyncio.gather(*[age_of(p) for p in pnus]) if r]
        if not results:
            return {"parcels_scanned": len(pnus), "buildings_found": 0, "old_ratio": None,
                    "note": "주변 건축물대장 데이터 부족 — 현장 확인 필요"}
        old = sum(1 for r in results if r["old"])
        ages = [r["age"] for r in results]
        return {
            "parcels_scanned": len(pnus),
            "buildings_found": len(results),
            "old_count": old,
            "old_ratio": round(old / len(results), 2),
            "avg_age": round(sum(ages) / len(ages)),
            "total_units": sum(r["units"] for r in results) or None,
            "meets_2_3": (old / len(results)) >= 2 / 3,
            "radius_m": radius_m,
            "note": f"중심 반경 {radius_m}m 내 {len(results)}개 건축물 기준 노후도(가로주택/모아/정비 2/3 요건 참고)",
        }

    @staticmethod
    def _magdo_summary(recommended: dict, ctx: dict) -> dict[str, Any] | None:
        """추천 사업방안 기준 매도청구 요약 + 다필지 잔여 매도청구 추정."""
        m = recommended.get("magdo")
        if not m:
            return {
                "applicable": False,
                "scheme": recommended.get("scheme"),
                "note": "단일 사업주체/단독 소유 또는 단순건축 — 매도청구 불요(전 토지 사용권원 확보 전제)",
            }
        n = ctx.get("parcel_count") or 1
        thr = m.get("consent_threshold_pct")
        remainder = m.get("claimable_remainder_pct")
        # 다필지(소유자=필지 가정)일 때 동의 필요 필지수·매도청구 가능 필지수 추정
        parcel_est = None
        if n >= 2 and thr:
            import math

            need = math.ceil(n * thr / 100.0)
            parcel_est = {
                "total_parcels": n,
                "consent_needed_parcels": min(need, n),
                "claimable_parcels_max": max(0, n - need),
                "assumption": "1필지=1소유자 가정(실제 소유관계·지분 확인 필요)",
            }
        return {
            "applicable": True,
            "scheme": recommended.get("scheme"),
            "consent_required": m.get("consent_required"),
            "consent_threshold_pct": thr,
            "claimable_remainder_pct": remainder,
            "basis": m.get("basis"),
            "note": m.get("note"),
            "parcel_estimate": parcel_est,
        }

    @staticmethod
    def _blended_far(parcels: list[dict], key: str = "max_far") -> float | None:
        """면적가중 평균 용적률. key='max_far'면 실효(현행·조례 반영, 시나리오 기준),
        key='max_far_legal'이면 법정상한(라벨 구분용)."""
        w = [(p.get("area"), p.get(key)) for p in parcels if p.get(key)]
        if not w:
            return None
        if all(a for a, _ in w):
            tot = sum(a for a, _ in w)
            return round(sum(a * f for a, f in w) / tot, 1) if tot else None
        fars = [f for _, f in w]
        return round(sum(fars) / len(fars), 1)

    @staticmethod
    def _resolution_from_gate(special_gate: dict) -> tuple[list[str], list[str], list[str]]:
        """특이부지 게이트에서 '개발가능 방안(선행절차)'·법령키·대안을 집계.

        ★사용자 피드백: '개발 불가'로 끝내지 말고 인허가·도시계획 변경 등 개발가능 방법을 제시.
        special_parcel이 보유한 resolution_paths(게이트)·permit_prerequisites(각 factor)·alternatives를
        중복 없이 모은다. 반환: (methods, legal_ref_keys, alternatives).
        """
        methods: list[str] = []
        ref_keys: list[str] = []
        for p in (special_gate.get("resolution_paths") or []):
            if p and p not in methods:
                methods.append(p)
        for f in (special_gate.get("factors") or []):
            for pre in (f.get("permit_prerequisites") or []):
                if pre and pre not in methods:
                    methods.append(pre)
            for k in (f.get("legal_ref_keys") or []):
                if k and k not in ref_keys:
                    ref_keys.append(k)
        alternatives = [a for a in (special_gate.get("alternatives") or []) if a]
        return methods, ref_keys, alternatives

    # 평수 티어 경계(㎡) — scenario 면적 게이트 상수와 정합(SINGLE_SMALL_MAX_SQM=1000 등 재사용 의미).
    #   T1<165(50평) T2<330(100평) T3<1000(300평) T4<3300(1000평) T5≥3300.
    _PYEONG_TIERS = (
        (165.0, "T1", "~50평(<165㎡)", "단순건축만(단독·다가구·다세대)"),
        (330.0, "T2", "50~100평(<330㎡)", "+자율주택정비(주거)"),
        (1000.0, "T3", "100~300평(<1000㎡)", "단독 정비 하한 직전 — 인접 통합 권고"),
        (3300.0, "T4", "300~1000평(<3300㎡)", "+모아주택(≥1500㎡)·지구단위 편입"),
        (float("inf"), "T5", "1000평+(≥3300㎡)", "+지구단위 단독(≥5000)·도시개발(≥10000)·정비사업"),
    )

    @staticmethod
    def _classify_by_pyeong_tier(area_sqm: float | None, scenarios: list[dict]) -> dict[str, Any]:
        """현 부지 면적을 평수 티어로 분류 + 시나리오 판정을 가능/조건부/불가 매트릭스로 재집계.

        ★순수 additive 뷰 — _scenarios 의 applicable 판정(이미 면적 게이트 반영)을 평수 축으로
        재구성할 뿐, 신규 게이트·상수를 만들지 않는다(결정론·기존 판정 무회귀).
        사용자 요청="소규모 단일/다필지의 총평수별 가능·불가 개발방식 상세 분류"의 백엔드 계약.
        """
        area = float(area_sqm or 0)
        pyeong = round(area / 3.3058, 1) if area else 0.0
        tier, tier_label = "T1", "~50평(<165㎡)"
        for boundary, t, label, _unlocks in DevelopmentScenarioSimulator._PYEONG_TIERS:
            if area < boundary:
                tier, tier_label = t, label
                break
        rank = {"가능": 0, "조건부": 1, "불가": 2}
        matrix = sorted(
            ({
                "scheme": s["scheme"],
                "status": s.get("applicable"),          # 가능 | 조건부 | 불가
                "reason": s.get("notes") or (s.get("cons") or [""])[0],
                "est_far_pct": s.get("est_far"),
            } for s in scenarios),
            key=lambda m: rank.get(m["status"], 3),
        )
        possible = [m["scheme"] for m in matrix if m["status"] == "가능"]
        conditional = [m["scheme"] for m in matrix if m["status"] == "조건부"]
        blocked = [m["scheme"] for m in matrix if m["status"] == "불가"]
        self_standing_only = possible == ["단순 건축"] and not conditional
        return {
            "area_sqm": round(area, 1), "pyeong": pyeong,
            "tier": tier, "tier_label": tier_label,
            "matrix": matrix,
            "possible": possible, "conditional": conditional, "blocked": blocked,
            "self_standing_only": self_standing_only,
            "tier_guide": [
                {"tier": t, "label": label, "unlocks": unlocks}
                for _b, t, label, unlocks in DevelopmentScenarioSimulator._PYEONG_TIERS
            ],
            "note": (
                f"단일 소규모 필지(약 {pyeong:g}평)는 단순건축 외 통합·정비·지구단위·역세권형 사업의 "
                "단독 검토대상이 아닙니다 — 인접 필지 통합 또는 기존 지구단위/정비구역 편입 시 "
                "가능 방식이 확장됩니다."
                if self_standing_only else
                f"약 {pyeong:g}평({tier}) 기준 — 가능 {len(possible)}·조건부 {len(conditional)}·불가 "
                f"{len(blocked)} 방식. 다필지 통합 시 상위 티어 방식 검토 가능."
            ),
        }

    # ── 규칙기반 시나리오 ──
    def _scenarios(self, c: dict) -> list[dict]:
        area = c.get("total_area_sqm") or 0
        zone = c.get("primary_zone") or ""
        # ★시나리오 est_far 기준 = 실효 용적률(현행·조례 반영). 미산정 시 법정상한 폴백(회귀0).
        far = c.get("far_effective_blended") or c.get("far_legal_blended") or 0
        multi = c.get("multi")
        station = c.get("near_station")
        integration_ok = c.get("integration_feasible", True)
        adj_note = (c.get("adjacency") or {}).get("note", "")
        res = _is_residential(zone)
        com = _is_commercial(zone)
        region = c.get("region") or ""
        seoul = "서울" in region  # 서울시 조례 고유 방식의 지역 적용가능성 판정
        # 건축물 실데이터(노후도·세대수) — 블록(주변) 우선, 없으면 입력필지
        b = c.get("buildings") or {}
        blk = c.get("block_aging") or {}
        block_ratio = blk.get("old_ratio")
        block_units = blk.get("total_units")
        parcel_ratio = b.get("old_ratio")
        oldest = b.get("oldest_age")
        units = block_units or b.get("total_units")

        def reno_note() -> str:
            parts = []
            if block_ratio is not None:
                meets = " · 2/3 충족" if blk.get("meets_2_3") else " · 2/3 미달"
                parts.append(f"블록 노후도 {int(block_ratio * 100)}%(반경{blk.get('radius_m', 100)}m·{blk.get('buildings_found')}동{meets})")
            elif parcel_ratio is not None:
                parts.append(f"필지 노후도 {int(parcel_ratio * 100)}%")
            if units:
                parts.append(f"세대수 {units}")
            return (" · 실데이터: " + ", ".join(parts)) if parts else ""

        S: list[dict] = []

        # 통합개발(합필/일단지)이 필요한 정책은 다필지 비인접 시 불가
        INTEGRATION_SCHEMES = {
            "지구단위계획 연계", "도시개발사업(도시개발법)", "가로주택정비사업",
            "모아주택/모아타운", "재개발·재건축(정비사업)", "역세권 활성화사업",
            "역세권 장기전세주택(시프트)", "도심복합개발사업",
            "소규모재개발사업", "주거환경개선사업", "공공재개발·공공재건축",
            "입지규제최소구역", "대지조성사업",
        }
        # ★단일 소규모 필지가 '단독'으로 추진 가능한 방식(나머지는 인접 통합/구역 편입/기존
        #   건축물·세대수 요건이 있어 단독 검토대상이 못 됨). 단순건축만 자립 가능.
        SELF_STANDING_SCHEMES = {"단순 건축"}
        # 단일 필지가 통합·정비·지구단위·역세권형 사업의 '단독' 검토대상이 되는 현실 하한(약 300평).
        #   이 미만의 '단일' 필지는 가로구역/블록/구역을 단독으로 구성할 수 없어 단독 추진 불가
        #   (인접 필지 통합 또는 기존 지구단위/정비구역 편입 시에만 가능).
        SINGLE_SMALL_MAX_SQM = 1000.0
        single_small = (not multi) and 0 < area < SINGLE_SMALL_MAX_SQM
        _pyeong = round(area / 3.3058) if area else 0

        def add(scheme, applicable, est_far, contrib, requirements, pros, cons, notes):
            # 다필지인데 비인접이면 통합개발 정책은 불가로 강등
            if multi and not integration_ok and scheme in INTEGRATION_SCHEMES and applicable != "불가":
                applicable = "불가"
                cons = [*(cons or []), "필지 비인접 — 통합개발 불가"]
                notes = f"⚠ {adj_note}. 통합개발 불가 — 필지별 개별개발 검토"
            # ★단일 소규모 필지: 통합·정비·지구단위·역세권형 사업은 단독 검토대상 아님(불가 강등).
            #   사용자가 지적한 "50~100평에 지구단위/도시개발/역세권 제시" 오류의 근본 차단.
            elif single_small and scheme not in SELF_STANDING_SCHEMES and applicable != "불가":
                applicable = "불가"
                cons = [*(cons or []),
                        f"단일 소규모 필지({round(area):,}㎡·약 {_pyeong:,}평) — 단독 추진 규모 미달"]
                notes = (f"⚠ 단일 {round(area):,}㎡(약 {_pyeong:,}평) 필지는 단독으로 통합·정비·"
                         "지구단위·역세권형 사업의 검토대상이 될 수 없습니다 — 인접 필지 통합(합필/"
                         "일단지) 또는 기존 지구단위계획구역·정비구역 편입 시에만 가능. "
                         "현 단계 현실적 추진방안: 단순 건축(현 용도지역 한도 내).")
            S.append({"scheme": scheme, "applicable": applicable,
                      "est_far": round(est_far) if est_far else None,
                      "contribution_pct": contrib, "requirements": requirements,
                      "pros": pros, "cons": cons, "notes": notes,
                      "magdo": _magdo(scheme)})  # 매도청구권 분석(해당 시)

        # 1) 단순 건축 (항상 가능 — 폴백 기준)
        add("단순 건축", "가능", far or None, 0,
            ["현 용도지역 허용용도·건폐율/용적률 한도 내 건축"],
            ["인허가 절차 단순·신속", "별도 정비/지정 절차 불필요"],
            ["용적률 인센티브 없음(현 한도)"],
            "특별 개발정책 미적용 시 기본 추진방안")

        # 2) 지구단위계획 연계
        if area >= 5000 or multi:
            add("지구단위계획 연계", "가능", (far or 0) * 1.2, 12,
                ["대지 5,000㎡ 이상 또는 다필지 통합", "지구단위계획 수립·심의"],
                ["용적률 인센티브(통상 +10~20%)", "용도·획지 유연화", "다필지 통합개발 적합"],
                ["계획 수립·심의 기간 소요", "공공기여 수반"],
                "다필지 통합개발의 핵심 수단. 기부채납 약 10~15%로 용적 상향")
        else:
            add("지구단위계획 연계", "조건부", (far or 0) * 1.15, 12,
                ["소규모는 인접 지구단위계획구역 편입 여부 확인"],
                ["편입 시 인센티브 가능"], ["단독 수립은 규모상 비효율"],
                "면적 5,000㎡ 미만 — 인접 구역 편입/특별계획구역 검토")

        # 3) 도시개발사업(도시개발법)
        if area >= 10000:
            add("도시개발사업(도시개발법)", "가능", (far or 0) * 1.3, 25,
                ["도시지역 1만㎡ 이상(비도시 3만㎡)", "도시개발구역 지정"],
                ["환지/수용 방식 대규모 개발", "기반시설 일체 정비", "용적 상향 여지 큼"],
                ["구역지정·실시계획 등 장기 절차", "공공기여 큼"],
                "대규모 통합개발에 적합. 구역지정 요건 충족")
        else:
            add("도시개발사업(도시개발법)", "불가", None, None,
                ["도시지역 1만㎡ 이상 필요"], [], ["면적 미달"],
                f"총면적 {round(area):,}㎡ < 1만㎡ — 도시개발구역 지정 요건 미달")

        # 4) 가로주택정비사업
        if res and 0 < area < 10000:
            add("가로주택정비사업", "조건부", (far or 0) * 1.2, 0,
                ["가로구역(폭6m이상 도로로 둘러싸임)", "노후·불량건축물 2/3 이상",
                 "기존 주택 단독10/공동20세대 이상", "면적 1만㎡ 미만"],
                ["소규모·신속(정비계획 생략)", "용적률 법적상한까지 완화 가능", "공공임대 시 추가 인센티브"],
                ["노후도·세대수 요건 충족 필요", "주민 동의 필요"],
                "노후 저층주거지 소규모 통합정비에 적합 — 요건 현장확인 필요" + reno_note())
        else:
            add("가로주택정비사업", "불가", None, None,
                ["주거지역·면적1만㎡ 미만·노후2/3·가로구역 필요"], [], ["요건 미해당"],
                "주거지역 아님 또는 면적 1만㎡ 이상")

        # 5) 모아주택(소규모주택정비) / 모아타운
        if res and 1500 <= area <= 100000:
            add("모아주택/모아타운", "조건부", (far or 0) * 1.2, 0,
                ["소규모주택정비 관리지역(모아타운) 지정", "노후·불량 2/3 이상", "면적 1,500㎡~"],
                ["블록단위 통합·지하주차 공유", "용적률·층수 완화", "기반시설 국비 지원"],
                ["관리지역 지정 필요", "주민 합의"],
                ("다세대·연립 밀집지 블록 통합개발 — 모아타운 지정 여부 확인"
                 if seoul else
                 f"⚠ '모아주택/모아타운'은 서울시 브랜드 — {region or '해당 지역'}은 동일 근거(빈집·소규모주택정비특례법)의 "
                 "'소규모주택정비 관리지역'으로 추진 가능(명칭·세부기준은 해당 시·도 조례 확인)") + reno_note())
        else:
            add("모아주택/모아타운", "불가", None, None,
                ["주거지역·면적 1,500㎡ 이상·노후 필요"], [], ["요건 미해당"], "")

        # 6) 역세권 활성화사업 / 역세권 장기전세주택 — ★서울시 조례 고유 제도
        if station and seoul:
            add("역세권 활성화사업", "조건부", (far or 0) * 1.5 if not com else (far or 0) * 1.2, 50,
                ["역 승강장 350m 이내", "용도지역 상향(일반→준주거/상업)", "증가용적 50% 공공기여", "★서울시 조례 적용지역"],
                ["용도지역 종상향으로 용적 대폭 상향", "복합개발 허용"],
                ["증가용적의 50% 공공기여(임대·생활SOC)", "심의 절차"],
                "역세권 입지 — 용도상향+공공기여로 고밀복합(서울시 역세권 활성화사업 운영기준)")
            if res:
                add("역세권 장기전세주택(시프트)", "조건부", 500, 50,
                    ["역세권 350m 이내", "준주거 상향", "증가용적 50% 장기전세 공급", "★서울시(SH)·운영지역 한정"],
                    ["준주거 상향(용적 500%)으로 사업성↑", "공공성 확보"],
                    ["임대주택 기부채납 부담", "서울시 등 운영지역 한정"],
                    "주거 역세권 — 준주거 상향 + 장기전세 연계(서울시 SH 고유)")
        elif station and not seoul:
            # 역세권이나 비-서울 — 서울 고유 제도는 불가, 전국 가능한 대체 제도 안내
            add("역세권 활성화사업", "불가", None, None,
                ["서울특별시 조례(역세권 활성화사업 운영기준) 적용지역 필요"], [],
                [f"{region or '해당 지역'}은 서울시 역세권 활성화사업 미적용"],
                f"⚠ 역세권 활성화사업은 서울시 고유 제도 — {region or '해당 지자체'}는 미적용. "
                "대체: 지구단위계획(역세권 용적 완화)·입지규제최소구역·도심복합개발사업 또는 해당 시·도 역세권 관련 조례 확인")
            add("역세권 장기전세주택(시프트)", "불가", None, None,
                ["서울특별시(SH) 운영지역 필요"], [], ["서울시 고유 제도(시프트)"],
                f"⚠ 장기전세(시프트)는 서울시(SH) 고유 — {region or '해당 지역'} 미적용. "
                "대체: 공공지원민간임대(뉴스테이)·국민임대 등 전국 임대제도 검토")
        else:
            add("역세권 활성화사업", "불가", None, None,
                ["역 승강장 350m 이내 필요"], [], ["역세권 범위 밖"],
                f"인근 역 거리 {c.get('near_station_m') or '미상'} — 역세권(350m) 미해당")

        # 7) 재개발·재건축(정비사업)
        if area >= 10000:
            add("재개발·재건축(정비사업)", "조건부", (far or 0) * 1.2, 15,
                ["정비구역 지정", "노후·불량건축물 2/3 이상", "면적 1만㎡ 이상"],
                ["대규모 정비·기반시설 확보", "용적률 상향"],
                ["정비구역 지정·조합설립 등 장기", "분담금·분쟁 리스크"],
                ("노후 시가지 대규모 정비 — 노후도 요건 확인"
                 + reno_note()
                 + (f" · 최고건물연령 {oldest}년" if oldest is not None else "")))
        else:
            add("재개발·재건축(정비사업)", "불가", None, None,
                ["면적 1만㎡ 이상·노후 필요"], [], ["면적 미달"], "")

        # 8) 도심복합개발사업 (도심 공공주택 복합사업 / 도심복합개발지원법 혁신지구·2024)
        primary_zone = c.get("primary_zone") or ""
        semi_ind = "준공업" in primary_zone
        if station or semi_ind:
            # 용도지역 상향 의제 → 역세권 최대 700%, 준공업 등 대폭 상향. 노후·면적·지구지정·시행자.
            est = min(700, max((far or 0) * 1.8, 500)) if station else max((far or 0) * 1.6, 400)
            add("도심복합개발사업", "조건부", est, 30,
                ["역세권/준공업/저층주거 + 노후도(통상 20년경과 60% 이상)",
                 "도심복합개발혁신지구 지정 또는 도심 공공주택 복합지구 지정",
                 "면적요건(주거상업혁신지구 약 5천㎡↑·성장거점형 1만㎡↑)", "공공 또는 지정개발자 시행"],
                ["용도지역 상향 의제로 용적률 대폭 완화(역세권 최대 700%)",
                 "주택·상업·업무 복합 고밀개발", "지구지정 시 인허가 통합·신속"],
                ["지구지정·계획 심의 절차", "공공기여·임대 비율 부담", "노후도·주민동의 요건"],
                ("도심 역세권/준공업 노후지 고밀복합 — 도심복합개발지원법(2024) 혁신지구 또는 "
                 "도심 공공주택 복합사업 검토" + reno_note()))
        else:
            add("도심복합개발사업", "불가", None, None,
                ["역세권/준공업/저층주거 + 노후도 + 지구지정 필요"], [], ["입지·용도 미해당"],
                "역세권/준공업 등 도심복합 대상 입지 아님 — 도심복합개발지원법 지구 요건 미해당")

        # 9) 자율주택정비사업 (빈집 및 소규모주택 정비 특례법)
        if res and 0 < area < 2000:
            add("자율주택정비사업", "조건부", (far or 0) * 1.1, 0,
                ["단독 10호 미만 또는 공동 20세대 미만(합 20 미만)", "노후·불량 2/3 이상", "주민합의체 구성", "비-정비예정구역"],
                ["주민합의체 자율시행·신속", "기금융자·기반시설 지원"],
                ["소규모 한정", "전원 합의 부담"],
                "노후 단독·다세대 소규모 자율정비" + reno_note())
        else:
            add("자율주택정비사업", "불가", None, None,
                ["주거지·단독10/공동20세대 미만·노후 필요"], [], ["규모·용도 미해당"], "")

        # 10) 소규모재개발사업 (2022 신설, 소규모주택정비 특례법)
        if (station or semi_ind) and 0 < area < 5000:
            add("소규모재개발사업", "조건부", (far or 0) * 1.4, 20,
                ["역세권(승강장 350m) 또는 준공업지역", "면적 5,000㎡ 미만", "노후·불량 2/3 이상"],
                ["역세권/준공업 소규모 신속정비", "용도지역 상향·용적 완화", "공공임대 시 인센티브"],
                ["노후도·면적 요건", "동의 필요"],
                "역세권/준공업 소규모 노후지 신속 정비(2022 신설)" + reno_note())
        else:
            add("소규모재개발사업", "불가", None, None,
                ["역세권/준공업·5천㎡ 미만·노후 필요"], [], ["요건 미해당"], "")

        # 11) 소규모재건축사업 (빈집 및 소규모주택 정비 특례법)
        if res and 0 < area < 10000:
            add("소규모재건축사업", "조건부", (far or 0) * 1.2, 0,
                ["기존 공동주택 200세대 미만", "노후·불량 2/3 이상", "면적 1만㎡ 미만·도로 요건"],
                ["조합·신속 절차(정비계획 생략)", "용적률 완화"],
                ["기존 공동주택·노후 요건", "동의 필요"],
                "노후 소규모 공동주택(연립·소형아파트) 재건축" + reno_note())
        else:
            add("소규모재건축사업", "불가", None, None,
                ["공동주택 200세대 미만·노후 필요"], [], ["요건 미해당"], "")

        # 12) 주거환경개선사업 (도시 및 주거환경정비법)
        if res:
            add("주거환경개선사업", "조건부", (far or 0) * 1.1, 0,
                ["도시저소득 밀집·기반시설 극히 열악", "노후·불량 과도 밀집", "정비구역 지정(공공 주도)"],
                ["공공 주도 기반시설·공동이용시설 확충", "현지개량/수용/환지/혼용 선택"],
                ["공공지정 필요", "장기 절차"],
                "저소득 노후밀집지 공공 주거환경개선")
        else:
            add("주거환경개선사업", "불가", None, None,
                ["주거지·노후밀집 필요"], [], ["미해당"], "")

        # 13) 공공재개발·공공재건축 (정비법 공공시행 — LH/SH 등)
        if area >= 10000:
            add("공공재개발·공공재건축", "조건부", (far or 0) * 1.4, 20,
                ["기존 정비(예정)구역 또는 해제구역", "LH/SH 등 공공 단독·공동시행", "노후 2/3"],
                ["용적률 법적상한 1.2배·종상향 인센티브", "공공기여 완화·신속·미분양 매입"],
                ["공공시행 동의(조합원 과반)", "임대 비율 부담"],
                "공공시행 정비 — 용적 인센티브·신속(공공재개발/공공재건축)" + reno_note())
        else:
            add("공공재개발·공공재건축", "불가", None, None,
                ["1만㎡↑·노후·공공시행 필요"], [], ["요건 미달"], "")

        # 14) 역세권 청년안심주택 (구 역세권 청년주택) — ★서울시 발원 조례, 타 지자체 유사제도 상이
        if station and res and seoul:
            add("역세권 청년안심주택", "조건부", 500, 30,
                ["역세권(350m) 또는 간선도로변", "준주거/상업 상향", "청년·신혼 임대 공급", "★서울시 조례"],
                ["준주거 상향(용적 대폭↑)", "청년임대 인센티브·기금 지원"],
                ["임대 의무(공공+민간)", "운영지역 한정"],
                "역세권 청년·신혼 임대주택 — 준주거 상향(서울시 역세권 청년안심주택)")
        elif station and res and not seoul:
            add("역세권 청년안심주택", "조건부", (far or 0) * 1.2, 20,
                ["역세권·간선도로변", "해당 시·도 청년·임대주택 조례", "청년·신혼 임대"],
                ["청년임대 기금·세제 지원(전국 공통)"],
                [f"'역세권 청년안심주택'은 서울시 명칭 — {region or '해당 지역'}은 유사 청년·임대 제도로 추진", "조례·요건 상이"],
                f"⚠ 서울시 고유 명칭 — {region or '해당 지역'}은 행복주택·청년매입임대·시도별 청년주택 조례 등 유사제도 확인 필요")
        else:
            add("역세권 청년안심주택", "불가", None, None,
                ["역세권·주거 필요"], [], ["미해당"], "")

        # 15) 공동주택 리모델링 (주택법 — 수직증축)
        if res and oldest is not None and oldest >= 15:
            add("공동주택 리모델링", "조건부", (far or 0) * 1.1, 0,
                ["준공 15년 경과 공동주택", "수직증축 최대 3개층·세대수 15% 증가", "안전진단 B등급 이상"],
                ["전면철거 없이 증축·신속", "이주 부담 적음"],
                ["구조안전·내력 한계", "증가 폭 제한"],
                f"노후 공동주택 리모델링(증축) — 최고건물연령 {oldest}년")
        else:
            add("공동주택 리모델링", "불가", None, None,
                ["기존 공동주택·준공 15년 경과 필요"], [], ["미해당"], "")

        # 16) 결합건축 (건축법 §77의4 — 인접 대지 용적률 결합·이전)
        if multi:
            add("결합건축", "가능" if integration_ok else "조건부", (far or 0) * 1.2, 0,
                ["2개 이상 대지(상호 100m 이내)", "용적률 결합·이전 협정", "지구단위/특별구역 등"],
                ["대지 간 용적 이전으로 한쪽 고밀화", "역사·녹지 보전과 병행"],
                ["대지 간 협정·등기 필요"],
                "인접 대지 용적률 결합·이전(한 대지 고밀화, 다른 대지 보전)")
        else:
            add("결합건축", "불가", None, None,
                ["2개 이상 대지 필요"], [], ["단일 대지"], "")

        # 17) 입지규제최소구역 (국토계획법)
        if area >= 5000 and (station or com):
            add("입지규제최소구역", "조건부", (far or 0) * 1.5, 30,
                ["도시지역 내 거점(역세권·복합환승 등)", "입지규제최소구역 지정", "건축·도시 융복합 계획"],
                ["용도·밀도·높이 제약 최소화", "복합 고밀개발"],
                ["구역지정·계획 심의", "공공기여"],
                "도심 거점 융복합 — 용도·밀도 제약 최소화(지정 필요)")
        else:
            add("입지규제최소구역", "불가", None, None,
                ["도심 거점·5천㎡↑·지정 필요"], [], ["요건 미해당"], "")

        # 18) 도시재생사업 (도시재생 활성화 및 지원에 관한 특별법)
        add("도시재생사업", "조건부", (far or 0) * 1.1, 0,
            ["쇠퇴지역(인구·산업·노후)", "도시재생활성화지역 지정", "마중물 공공지원"],
            ["공공지원·주민참여", "점진적 재생(전면철거 지양)"],
            ["대규모 개발엔 한계", "지정 필요"],
            "쇠퇴지역 활성화 — 공공지원 점진 재생(활성화지역 지정 시)")

        # 19) 공공지원민간임대(뉴스테이) (민간임대주택특별법)
        if area >= 5000:
            add("공공지원민간임대(뉴스테이)", "조건부", (far or 0) * 1.3, 20,
                ["촉진지구 지정(또는 일반형)", "8년 이상 장기 민간임대", "면적·세대 요건"],
                ["용적률·용도 인센티브", "주택기금 지원·안정적 임대수익"],
                ["임대 의무기간", "초기 분양수익 제약"],
                "장기 민간임대 — 촉진지구 용적 인센티브(뉴스테이)")
        else:
            add("공공지원민간임대(뉴스테이)", "불가", None, None,
                ["촉진지구·면적 요건 필요"], [], ["요건 미달"], "")

        # 20) 대지조성사업 (주택법 §15 대지조성 / 택지개발 — 주택건설용 대지 조성·분양)
        if area >= 10000 or (not res and not com):
            add("대지조성사업", "조건부", far or None, 10,
                ["주택건설용 대지 조성(주택법) 또는 택지개발", "기반시설(도로·상하수) 조성", "녹지·관리·비도시는 형질변경/전용 인허가"],
                ["택지 조성 후 단독·단지 용지 분양", "대규모 부지 정형화·단계 개발"],
                ["형질변경·전용 인허가", "기반시설 조성 비용"],
                "대규모 부지·녹지/관리지역 — 대지조성 후 단독·전원·단지 용지 공급")
        else:
            add("대지조성사업", "불가", None, None,
                ["대규모 부지 또는 녹지·관리·비도시 필요"], [], ["소규모 시가지 부적합"], "")

        # 각 방식에 건축 가능 분류(아파트/호텔/상가/지산/빌라/콘도/전원주택 등) 부착.
        _zone = c.get("primary_zone")
        for _s in S:
            _s["buildable_types"] = self._buildable_types(_zone, _s.get("scheme", ""))
            # 시나리오↔규범 일치(가산) — 각 사업방식의 근거법령 verified 딥링크 부착(소비처 옵셔널).
            _s["legal_refs"] = _scheme_legal_refs(_s.get("scheme", ""))

        return S

    # ── 주소 → 시·도(지역) 판정. 서울시 조례 고유 방식의 지역 적용가능성 판정에 사용 ──
    @staticmethod
    def _region(address: str | None) -> str:
        a = (address or "").strip()
        sidos = [
            "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
            "대전광역시", "울산광역시", "세종특별자치시", "경기도",
            "강원특별자치도", "강원도", "충청북도", "충청남도",
            "전북특별자치도", "전라북도", "전라남도",
            "경상북도", "경상남도", "제주특별자치도",
        ]
        for s in sidos:
            if a.startswith(s) or a.startswith(s[:2]):
                return s
        return ""

    # ── 방식·용도지역별 건축 가능 분류(아파트/호텔/상가/지산/빌라/콘도/전원주택 등) 제안 ──
    @staticmethod
    def _buildable_types(zone: str | None, scheme: str) -> list[str]:
        z = zone or ""
        # 1) 용도지역 기준 기본 건축 가능 분류.
        if any(k in z for k in ("중심상업", "일반상업", "근린상업", "유통상업")):
            base = ["상가(근린생활)", "오피스(업무시설)", "오피스텔", "주상복합 아파트", "호텔/생활숙박", "지식산업센터"]
        elif "준주거" in z:
            base = ["주상복합 아파트", "아파트", "오피스텔", "상가", "근린생활"]
        elif "준공업" in z:
            base = ["지식산업센터", "공장/제조", "오피스", "근린생활", "생활숙박(조건부)"]
        elif "전용주거" in z:
            base = ["단독주택", "저층 연립/다세대(빌라)"]
        elif "주거" in z:  # 1·2·3종 일반주거
            base = ["아파트", "연립/다세대(빌라)", "단독주택", "근린생활"]
        elif "계획관리" in z:
            base = ["전원주택", "단독주택", "근린생활", "물류창고", "공장", "콘도/펜션"]
        elif any(k in z for k in ("녹지", "보전관리", "생산관리", "농림", "자연")):
            base = ["단독/전원주택", "근린생활(제한적)", "(개발행위허가 필요)"]
        else:
            base = ["용도지역 확인 필요"]
        # 2) 개발방식 보정(방식 특성상 유리한 분류로 좁힘/추가).
        if "역세권" in scheme or "도심복합" in scheme:
            return ["주상복합 아파트", "오피스텔", "상가", "오피스", "호텔/생활숙박"] + (["청년·신혼 임대주택"] if "청년" in scheme else [])
        if any(k in scheme for k in ("가로주택", "모아", "자율주택", "소규모재건축", "주거환경")):
            return ["저층 아파트", "연립/다세대(빌라)", "단독주택"]
        if "대지조성" in scheme:
            return ["단독/전원주택 용지", "아파트 건설용지", "상가/근생 용지(분양)"]
        if "리모델링" in scheme:
            return ["기존 공동주택 증축(아파트)"]
        if "뉴스테이" in scheme or "장기전세" in scheme or "청년안심" in scheme:
            return ["임대 아파트", "오피스텔", "주상복합"]
        return base

    async def _llm(self, ctx: dict, scenarios: list[dict]) -> dict[str, Any]:
        try:
            from app.services.ai.llm_provider import get_llm
            from app.services.ai.base_interpreter import GROUNDING_RULE
            from langchain_core.messages import HumanMessage, SystemMessage

            sys = ("당신은 부동산개발 사업방식 전문가다. 제공된 부지정보와 규칙기반 후보 시나리오를 "
                   "근거로 가장 합리적인 최적 사업방안을 추천하고 그 이유, 차선책, 주의사항을 제시한다. "
                   "데이터·후보에 근거하고 과장 금지. JSON만 출력." + GROUNDING_RULE)
            usr = (f"## 부지\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
                   f"## 후보 시나리오\n{json.dumps(scenarios, ensure_ascii=False)[:3000]}\n\n"
                   "## 출력 JSON\n{\"summary\":\"종합 판단 3~4문장\",\"best_scheme\":\"추천 사업방식\","
                   "\"why\":\"추천 이유 2~3문장\",\"alternatives\":[\"차선책 1~2개\"],"
                   "\"cautions\":[\"주의사항 1~3개\"]}")
            llm = get_llm(timeout=60, max_tokens=1500)
            resp = await llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=usr)])
            # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="scenario")
            raw = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                raw = raw[4:] if raw.lower().startswith("json") else raw
            data = json.loads(raw.strip())
            data["generated"] = True
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("개발 시나리오 LLM 실패, 폴백", err=str(e)[:100])
            return {"generated": False, "summary": "규칙기반 시나리오를 참고하세요. AI 종합은 일시적으로 미제공.",
                    "best_scheme": None, "why": "", "alternatives": [], "cautions": []}
