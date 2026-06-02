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
        far_legal = self._blended_far(enriched)
        zones = [p.get("zone") for p in enriched if p.get("zone")]
        primary_zone = zones[0] if zones else (site.get("zone_type") or "")
        near_station = (subway_m is not None and subway_m <= 500) or any(
            "역세권" in (p.get("zone") or "") for p in enriched
        )

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
            "address": address, "multi": multi, "parcel_count": len(addrs),
            "total_area_sqm": round(total_area, 1) if total_area else None,
            "primary_zone": primary_zone, "zones": zones,
            "far_legal_blended": far_legal,
            "near_station_m": subway_m, "near_station": near_station,
            "adjacency": adjacency, "integration_feasible": integration_ok,
            "buildings": buildings, "block_aging": block,
            "parcels": [{"address": p.get("address"), "zone": p.get("zone"),
                         "area": p.get("area"), "max_far": p.get("max_far"),
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

        result = {
            "site": ctx,
            "scenarios": scenarios,
            "recommended": {"scheme": recommended["scheme"], "est_far": recommended.get("est_far"),
                            "reason": recommended.get("notes") or recommended.get("pros", [""])[0]},
            "fallback_simple_build": next(s for s in scenarios if s["scheme"] == "단순 건축"),
            "magdo_summary": magdo_summary,
        }
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

        async def one(a: str) -> dict:
            try:
                r = await az.analyze_by_address(a)
                zl = r.get("zone_limits") or {}
                far = zl.get("max_far_pct") or zl.get("max_far")
                if not far and r.get("zone_type"):
                    lim = ZONE_LIMITS.get((r["zone_type"] or "").replace(" ", ""))
                    far = lim.get("max_far") if lim else None
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
                        "area": r.get("land_area_sqm"), "max_far": far,
                        "pnu": pnu, "geometry": geometry, "owner_type": owner_type,
                        "bldg_year": bldg_year, "units": units, "structure": structure,
                        "coords": coords}
            except Exception:  # noqa: BLE001
                return {"address": a, "zone": None, "area": None, "max_far": None, "geometry": None}

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
    def _blended_far(parcels: list[dict]) -> float | None:
        w = [(p.get("area"), p.get("max_far")) for p in parcels if p.get("max_far")]
        if not w:
            return None
        if all(a for a, _ in w):
            tot = sum(a for a, _ in w)
            return round(sum(a * f for a, f in w) / tot, 1) if tot else None
        fars = [f for _, f in w]
        return round(sum(fars) / len(fars), 1)

    # ── 규칙기반 시나리오 ──
    def _scenarios(self, c: dict) -> list[dict]:
        area = c.get("total_area_sqm") or 0
        zone = c.get("primary_zone") or ""
        far = c.get("far_legal_blended") or 0
        multi = c.get("multi")
        station = c.get("near_station")
        integration_ok = c.get("integration_feasible", True)
        adj_note = (c.get("adjacency") or {}).get("note", "")
        res = _is_residential(zone)
        com = _is_commercial(zone)
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
            "역세권 장기전세주택(시프트)",
        }

        def add(scheme, applicable, est_far, contrib, requirements, pros, cons, notes):
            # 다필지인데 비인접이면 통합개발 정책은 불가로 강등
            if multi and not integration_ok and scheme in INTEGRATION_SCHEMES and applicable != "불가":
                applicable = "불가"
                cons = [*(cons or []), "필지 비인접 — 통합개발 불가"]
                notes = f"⚠ {adj_note}. 통합개발 불가 — 필지별 개별개발 검토"
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
                ["관리지역 지정 필요(서울 등)", "주민 합의"],
                "다세대·연립 밀집지 블록 통합개발 — 모아타운 지정 여부 확인" + reno_note())
        else:
            add("모아주택/모아타운", "불가", None, None,
                ["주거지역·면적 1,500㎡ 이상·노후 필요"], [], ["요건 미해당"], "")

        # 6) 역세권 활성화사업 / 역세권 장기전세주택
        if station:
            add("역세권 활성화사업", "조건부", (far or 0) * 1.5 if not com else (far or 0) * 1.2, 50,
                ["역 승강장 350m 이내", "용도지역 상향(일반→준주거/상업)", "증가용적 50% 공공기여"],
                ["용도지역 종상향으로 용적 대폭 상향", "복합개발 허용"],
                ["증가용적의 50% 공공기여(임대·생활SOC)", "심의 절차"],
                "역세권 입지 — 용도상향+공공기여로 고밀복합 가능")
            if res:
                add("역세권 장기전세주택(시프트)", "조건부", 500, 50,
                    ["역세권 350m 이내", "준주거 상향", "증가용적 50% 장기전세 공급"],
                    ["준주거 상향(용적 500%)으로 사업성↑", "공공성 확보"],
                    ["임대주택 기부채납 부담", "서울시 등 운영지역 한정"],
                    "주거 역세권 — 준주거 상향 + 장기전세 연계")
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

        return S

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
