"""자동 용도지역 감지 + 종합 토지정보 라우터."""

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.app.services.zoning.auto_zoning_service import AutoZoningService
from apps.api.app.services.land_intelligence.land_info_service import LandInfoService
from app.core.billing_deps import enforce_llm_quota

router = APIRouter()


class ZoningAnalyzeRequest(BaseModel):
    """용도지역 분석 요청."""

    address: str
    pnu: str | None = None
    bcode: str | None = None  # 카카오 법정동 코드 (10자리)
    jibun_address: str | None = None  # 카카오 지번 주소


def _zone_limits_compact(zone_type: str | None) -> dict | None:
    """용도지역명 → 법정 건폐율/용적률 한도(간략)."""
    if not zone_type:
        return None
    from apps.api.app.services.zoning.auto_zoning_service import ZONE_LIMITS

    key = zone_type.replace(" ", "").strip()
    limits = ZONE_LIMITS.get(key) or next(
        (v for k, v in ZONE_LIMITS.items() if k in key or key in k), None
    )
    if not limits:
        return None
    return {"max_bcr_pct": limits.get("max_bcr"), "max_far_pct": limits.get("max_far")}


def _build_pnu_from_bcode(bcode: str, jibun_address: str) -> str | None:
    """법정동 코드(10자리) + 지번 주소에서 PNU(19자리)를 구성한다.

    PNU 구조: 법정동코드(10) + 대지구분(1, 1=대지/2=산) + 본번(4) + 부번(4)
    예: 4115010100 + 1 + 0226 + 0002 = 4115010100102260002
    """
    if not bcode or len(bcode) < 10:
        return None

    # 지번에서 본번/부번 추출 (예: "226-2", "224", "산123-4")
    jibun = jibun_address or ""
    # 지번 주소에서 마지막 번지 부분 추출
    match = re.search(r"(산)?(\d+)(?:-(\d+))?(?:\s|$)", jibun)
    if not match:
        return None

    is_mountain = "2" if match.group(1) else "1"  # 산=2, 대지=1
    main_num = match.group(2).zfill(4)  # 본번 4자리
    sub_num = (match.group(3) or "0").zfill(4)  # 부번 4자리

    return f"{bcode}{is_mountain}{main_num}{sub_num}"


@router.post("/analyze", dependencies=[Depends(enforce_llm_quota)])
async def analyze_zoning(req: ZoningAnalyzeRequest):
    """주소 기반 자동 용도지역 감지 및 법적 한도 매핑.

    구조화 분석 결과에 SiteAnalysisInterpreter(LLM) 해석을 ai_interpretation으로
    덧붙인다. LLM 실패 시에도 구조화 결과는 정상 반환(graceful fallback).
    """
    service = AutoZoningService()
    result = await service.analyze_by_address(req.address)

    # ── SiteAnalysisInterpreter(Claude) 자연어 해석 부착 ──
    # 그라운딩: 법정한도 + 실효용적률 계층(far_tier_service 단일출처) + 종상향 잠재
    #          컨텍스트를 인터프리터에 주입한다. (zone_type만 전달 → 200% 무근거 차단)
    try:
        from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter
        from app.services.land_intelligence import far_tier_service

        zone_limits = result.get("zone_limits") or {}
        zt = result.get("zone_type") or ""
        la = float(result.get("land_area_sqm") or 0)

        # 실효용적률 계층 + 종상향: AutoZoning 결과(zone_type·zone_limits·special_districts)를
        # base로 사용해 법정범위·far_basis_detail·종상향 시나리오를 산출(외부 LLM 무호출).
        effective_far_tier: dict = {
            "effective_far_pct": zone_limits.get("max_far_pct"),
            "effective_bcr_pct": zone_limits.get("max_bcr_pct"),
        }
        upzoning: dict = {}
        if zt:
            try:
                effective_far_tier = far_tier_service.calc_effective_far(result, zt, la)
                upzoning = far_tier_service.calc_upzoning(result, zt, la, None, None)
            except Exception:  # noqa: BLE001
                pass

        interp_input = {
            "address": result.get("address"),
            "zone_type": zt,
            "land_area_sqm": result.get("land_area_sqm"),
            # 법정한도(그라운딩): 인터프리터가 무근거 상향 서술을 못 하도록 명시.
            "zone_limits": {
                "max_far_pct": zone_limits.get("max_far_pct"),
                "max_bcr_pct": zone_limits.get("max_bcr_pct"),
                "legal_basis": zone_limits.get("legal_basis"),
            },
            "effective_far": effective_far_tier,
            "upzoning": upzoning,
            "upzoning_scenarios": upzoning.get("scenarios", []),
            "potential_far_range": upzoning.get("potential_far_range"),
            "land_prices": {
                "official_price_per_sqm": result.get("official_price_per_sqm"),
            },
            "development_plans": {
                "special_districts": result.get("special_districts", []),
            },
        }
        # 화면 경로에서도 계층/종상향을 캡처하도록 응답에 동봉(프론트 옵셔널 렌더).
        result.setdefault("effective_far", effective_far_tier)
        if upzoning:
            result.setdefault("upzoning", upzoning)
            result.setdefault("upzoning_scenarios", upzoning.get("scenarios", []))
            result.setdefault("potential_far_range", upzoning.get("potential_far_range"))

        interp = await SiteAnalysisInterpreter().generate_interpretation(interp_input)
        if isinstance(interp, dict) and interp:
            result["ai_interpretation"] = interp
    except Exception as e:  # noqa: BLE001
        import structlog

        structlog.get_logger().warning("부지분석 AI 해석 스킵", error=str(e)[:120])

    # 서비스 사용료(LLM 별개): 토지분석 1건 차감(로그인 사용자, best-effort)
    try:
        from app.core.request_context import get_current_user_id

        uid = get_current_user_id()
        if uid:
            from app.core.database import async_session_factory
            from app.services.billing import billing_service

            async with async_session_factory() as _db:
                charge = await billing_service.charge_service(_db, uid, "land_analysis")
            result["service_charge"] = charge  # 프론트 표시용(차감/무료/잔여)
    except Exception:  # noqa: BLE001
        pass

    return result


@router.post("/comprehensive")
async def comprehensive_land_analysis(req: ZoningAnalyzeRequest):
    """종합 토지정보 수집 — 토지대장+공시지가+토지이용계획+조례 통합.

    카카오 주소 검색의 bcode(법정동 코드)가 전달되면 PNU를 직접 구성하여
    VWORLD 지오코딩 없이 토지정보를 조회한다.
    """
    # PNU 결정: 직접 전달 > bcode로 구성 > VWORLD 지오코딩
    pnu = req.pnu
    if not pnu and req.bcode and req.jibun_address:
        pnu = _build_pnu_from_bcode(req.bcode, req.jibun_address)

    service = LandInfoService()
    return await service.collect_comprehensive(req.address, pnu=pnu)


class ParcelBoundariesRequest(BaseModel):
    """필지 경계(구획도) 요청 — 단필지/다필지."""

    parcels: list[dict] = []  # [{pnu?, address?, bcode?, jibun_address?}]
    address: str | None = None  # 단일 주소 단축 입력
    pnu: str | None = None


@router.post("/parcel-boundaries")
async def parcel_boundaries(req: ParcelBoundariesRequest):
    """단/다필지의 경계 폴리곤(GeoJSON)+면적+용도지역을 지도용으로 반환.

    각 필지에 대해 VWORLD 지적도(geometry)와 토지특성(면적·용도지역)을 조회.
    반환: {features:[{pnu, address, area_sqm, zone_type, zone_type_2, geometry}],
           center:{lat,lon}, total_area_sqm}
    """
    from apps.api.app.services.external_api.vworld_service import VWorldService

    # 입력 정규화: parcels 배열 우선, 없으면 단일(address/pnu)
    items: list[dict] = list(req.parcels or [])
    if not items and (req.address or req.pnu):
        items = [{"address": req.address, "pnu": req.pnu}]
    if not items:
        return {"features": [], "center": None, "total_area_sqm": 0}

    vworld = VWorldService()
    features: list[dict] = []
    total_area = 0.0
    lat_sum = lon_sum = 0.0
    coord_n = 0

    for it in items:
        pnu = it.get("pnu")
        address = it.get("address") or ""
        if not pnu and it.get("bcode") and it.get("jibun_address"):
            pnu = _build_pnu_from_bcode(it["bcode"], it["jibun_address"])
        coords = None
        point_geom = None
        # PNU가 없으면 주소 지오코딩
        if not pnu and address:
            try:
                geo = await vworld.geocode_address(address)
                if geo:
                    pnu = geo.get("pnu")
                    coords = {"lat": geo.get("lat"), "lon": geo.get("lon")}
            except Exception:  # noqa: BLE001
                pass
        # 도로명주소 등 PNU 미확보 시: 좌표로 필지 직접 조회(점 기반)
        if not pnu and coords and coords.get("lat") and coords.get("lon"):
            try:
                pp = await vworld.get_parcel_by_point(coords["lat"], coords["lon"])
                if pp:
                    pnu = pp.get("pnu")
                    point_geom = pp.get("geometry")
            except Exception:  # noqa: BLE001
                pass
        if not pnu:
            continue

        geometry = point_geom
        area_sqm = 0.0
        zone_type = zone_type_2 = None
        try:
            if geometry is None:
                li = await vworld.get_land_info(pnu)
                if li:
                    geometry = li.get("geometry")
                    area_sqm = float((li.get("properties") or {}).get("area") or 0)
        except Exception:  # noqa: BLE001
            pass
        try:
            lc = await vworld.get_land_characteristics(pnu)
            if lc:
                area_sqm = area_sqm or float(lc.get("area_sqm") or 0)
                zone_type = lc.get("zone_type") or None
                zone_type_2 = lc.get("zone_type_2") or None
        except Exception:  # noqa: BLE001
            pass

        # 좌표(중심) 보강
        if not coords:
            try:
                geo = await vworld.geocode_address(address) if address else None
                if geo:
                    coords = {"lat": geo.get("lat"), "lon": geo.get("lon")}
            except Exception:  # noqa: BLE001
                pass
        if coords and coords.get("lat") and coords.get("lon"):
            lat_sum += coords["lat"]; lon_sum += coords["lon"]; coord_n += 1

        total_area += area_sqm
        features.append({
            "pnu": pnu,
            "address": address,
            "area_sqm": round(area_sqm, 1),
            "zone_type": zone_type,
            "zone_type_2": zone_type_2,
            "zone_limits": _zone_limits_compact(zone_type),
            "geometry": geometry,
        })

    center = {"lat": lat_sum / coord_n, "lon": lon_sum / coord_n} if coord_n else None
    # 중심 폴백: 첫 폴리곤 첫 좌표
    if not center:
        for f in features:
            g = f.get("geometry") or {}
            c = g.get("coordinates")
            try:
                pt = c
                while isinstance(pt, list) and pt and isinstance(pt[0], list):
                    pt = pt[0]
                if isinstance(pt, list) and len(pt) >= 2:
                    center = {"lat": pt[1], "lon": pt[0]}
                    break
            except Exception:  # noqa: BLE001
                continue

    # 인접성: 통합개발(합필/일단지)은 필지가 맞닿아야 가능
    adjacency = _parcel_adjacency([f.get("geometry") for f in features]) if len(features) >= 2 else \
        {"contiguous": True, "components": 1, "note": "단일 필지"}

    return {
        "features": features,
        "center": center,
        "total_area_sqm": round(total_area, 1),
        "parcel_count": len(features),
        "adjacency": adjacency,
    }


def _parcel_adjacency(geoms: list) -> dict:
    """필지 폴리곤 인접성(연결요소) 판정 — shapely."""
    present = [g for g in geoms if g]
    if len(present) < 2:
        return {"contiguous": True, "components": 1, "note": "단일 필지"}
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
            return {"contiguous": None, "components": None, "note": "형상 데이터 부족 — 인접성 확인 불가"}
        tol = 0.00006  # ~6m
        n = len(idx)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a in range(n):
            for b in range(a + 1, n):
                if polys[idx[a]].distance(polys[idx[b]]) <= tol:
                    parent[find(a)] = find(b)
        comps = len({find(i) for i in range(n)})
        return {
            "contiguous": comps == 1, "components": comps,
            "note": "모든 필지가 맞닿아 통합개발 가능" if comps == 1
            else f"{comps}개 그룹으로 분리 — 비인접 필지는 통합개발 불가",
        }
    except Exception:  # noqa: BLE001
        return {"contiguous": None, "components": None, "note": "인접성 분석 실패"}


class NearbyMapRequest(BaseModel):
    """주변 실거래 지도 요청."""

    address: str
    pnu: str | None = None
    bcode: str | None = None
    jibun_address: str | None = None
    radius_m: int = 1000
    months: int = 3


@router.post("/nearby-map")
async def nearby_transactions_map(req: NearbyMapRequest):
    """대상 지번 주변 실거래를 카테고리별·건물단위로 지오코딩하여 지도 페이로드 반환.

    center(중심좌표)+radius_m+categories(매매6·전월세4, 건물별 좌표·집계·거래목록).
    """
    from apps.api.app.services.land_intelligence.nearby_map_service import NearbyMapService

    # lawd_cd 결정: pnu[:5] > bcode[:5]
    pnu = req.pnu
    if not pnu and req.bcode and req.jibun_address:
        pnu = _build_pnu_from_bcode(req.bcode, req.jibun_address)
    lawd_cd = (pnu or "")[:5] if pnu else (req.bcode or "")[:5]
    if not lawd_cd or len(lawd_cd) < 5:
        return {"error": "법정동코드(LAWD_CD) 결정 불가 — bcode 또는 pnu 필요",
                "center": None, "categories": {}}

    # sigungu 힌트(지오코딩 폴백용): 주소 앞 2토큰
    parts = (req.address or "").split()
    sigungu_hint = " ".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "")

    service = NearbyMapService()
    return await service.build(
        address=req.address, lawd_cd=lawd_cd,
        months=req.months, radius_m=req.radius_m, sigungu_hint=sigungu_hint,
    )
