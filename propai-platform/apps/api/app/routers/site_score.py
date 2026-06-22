"""PropAI SiteScore 라우터 — 설명가능 학습형 입지 점수(베팅 C)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.site_score.site_score_service import compute_site_score
from app.services.site_score.solar_envelope_service import compute_buildable_envelope

router = APIRouter(prefix="/api/v1/site-score", tags=["입지점수(SiteScore)"])


class SiteScoreRequest(BaseModel):
    context: dict[str, Any]                       # 부지 분석 결과(infrastructure/zone_type/공시지가 등)
    region_baseline: dict[str, float] | None = None  # 지역 평균(상권·실거래·지가) — 자가보정용(선택)


@router.post("")
async def site_score(req: SiteScoreRequest):
    """부지 컨텍스트에서 0~100 입지 점수 + 피처별 기여도(설명가능)를 산출."""
    result = compute_site_score(req.context, req.region_baseline)
    # ── 전역정책 Phase0: 근거·법령·신선도 공용 블록 가산(additive, graceful) ──
    # 기존 score/grade/factors 무손상, evidence/legal_refs/provenance만 추가.
    try:
        from app.services.site_score.site_score_service import build_site_score_evidence

        ev = build_site_score_evidence(result)
        result.setdefault("evidence", ev.get("evidence", []))
        result.setdefault("legal_refs", ev.get("legal_refs", []))
        result.setdefault("provenance", ev.get("provenance", []))
    except Exception:  # noqa: BLE001 — 근거 블록 실패해도 입지점수 결과 무손상
        pass
    return result


class PoiInfraRequest(BaseModel):
    address: str | None = None     # 주소/지번(좌표 없으면 VWorld 지오코딩)
    lat: float | None = None
    lon: float | None = None
    radius_m: int = 1000
    context: dict[str, Any] | None = None  # 부지분석 결과(주면 site_score와 통합 입지점수 합산)


# 입지 POI 카테고리 가중치(접근성 점수용) — 지하철·교육·의료·생활·공원 비중.
_POI_WEIGHTS: dict[str, float] = {
    "SW8": 2.2, "SC4": 1.6, "HP8": 1.4, "MT1": 1.2, "PARK": 1.1, "PM9": 0.9, "BK9": 0.9,
    "PO3": 0.8, "CT1": 0.8, "CS2": 0.6, "AC5": 0.7, "AT4": 0.5, "FD6": 0.5, "CE7": 0.4,
}


def _poi_accessibility_score(categories: dict[str, Any]) -> dict[str, Any]:
    """POI 인벤토리 → 0~100 접근성 점수(거리감쇠×가중). 설명가능 기여도 동반."""
    def band(m: float | None) -> float:
        if m is None:
            return 0.0
        for thr, n in [(250, 1.0), (500, 0.85), (1000, 0.6), (1500, 0.35), (2500, 0.1)]:
            if m <= thr:
                return n
        return 0.0

    contribs: list[dict[str, Any]] = []
    wsum = 0.0
    acc = 0.0
    for code, w in _POI_WEIGHTS.items():
        c = categories.get(code) or {}
        nearest = c.get("nearest_m")
        cnt = c.get("count") or 0
        # 근접도 + 밀도(개수) 약간 가산.
        n = band(nearest)
        if cnt > 1:
            n = min(1.0, n + min(0.12, 0.02 * (cnt - 1)))
        wsum += w
        acc += w * n
        if cnt > 0:
            contribs.append({"category": c.get("label", code), "count": cnt,
                             "nearest_m": nearest, "norm": round(n, 2)})
    score = round(100 * acc / wsum, 1) if wsum else 0.0
    contribs.sort(key=lambda x: -(x["norm"] or 0))
    return {"poi_accessibility_score": score, "contributions": contribs}


@router.post("/poi-infra")
async def poi_infra(req: PoiInfraRequest):
    """입지 인프라(POI) 인벤토리 + 접근성 점수 — Kakao Local 카테고리 반경검색.

    좌표 미지정 시 주소/지번을 VWorld 로 지오코딩(Daum 미검색 지번도 OK).
    무목업: Kakao 키 미설정/조회 실패 시 정직 표기.
    """
    lat, lon = req.lat, req.lon
    geocoded_from: str | None = None
    if (lat is None or lon is None) and req.address:
        from app.services.external_api.vworld_service import VWorldService
        geo = await VWorldService().geocode_address(req.address.strip())
        if geo and geo.get("lat"):
            lat, lon = geo["lat"], geo["lon"]
            geocoded_from = "vworld"
    if lat is None or lon is None:
        return {"available": False, "reason": "좌표 또는 지오코딩 가능한 주소가 필요합니다."}

    from app.services.external_api.kakao_local_service import KakaoLocalService
    kakao = KakaoLocalService()
    inv = await kakao.poi_inventory(lat, lon, radius=req.radius_m)
    if not inv.get("available"):
        return {**inv, "coordinates": {"lat": lat, "lon": lon}, "geocoded_from": geocoded_from}

    cats = inv.get("categories", {})

    # 공원(녹지) — 카테고리 코드가 없어 키워드 검색으로 보강.
    park = await kakao.keyword_search(lat, lon, "공원", radius=req.radius_m)
    if park is not None:
        cats["PARK"] = {"label": "공원", **park}

    # 실소요시간 — 최근접 지하철역까지 자동차 길찾기(Kakao Mobility). 미가용 시 None(정직).
    transit_time = None
    sw = cats.get("SW8") or {}
    sw_items = sw.get("items") or []
    if sw_items and sw_items[0].get("lat") and sw_items[0].get("lon"):
        d = await kakao.driving_duration_sec(lat, lon, sw_items[0]["lat"], sw_items[0]["lon"])
        if d and d.get("duration_sec") is not None:
            transit_time = {
                "to": sw_items[0].get("name"),
                "driving_min": round(d["duration_sec"] / 60, 1),
                "distance_m": d.get("distance_m"),
            }

    scored = _poi_accessibility_score(cats)
    poi_score = scored["poi_accessibility_score"]

    # 통합 입지점수 — context 제공 시 site_score(상권·실거래·용도지역 등)와 가중 합산.
    integrated = None
    site = None
    if req.context:
        try:
            from app.services.site_score.site_score_service import compute_site_score
            site = compute_site_score(req.context)
            site_total = site.get("score") if isinstance(site, dict) else None
            if isinstance(site_total, (int, float)):
                # POI 접근성 55% + 종합 입지(site_score) 45%.
                integrated = round(0.55 * poi_score + 0.45 * float(site_total), 1)
        except Exception:  # noqa: BLE001 - site_score 실패는 POI 결과를 막지 않는다
            site = None

    resp: dict[str, Any] = {
        "available": True, "radius_m": req.radius_m,
        "coordinates": {"lat": lat, "lon": lon}, "geocoded_from": geocoded_from,
        "categories": cats,
        "transit_time": transit_time,
        "poi_accessibility_score": poi_score,
        "contributions": scored["contributions"],
        "site_score": site,
        "integrated_location_score": integrated,
        "score_basis": "통합=POI접근성55%+종합입지45%" if integrated is not None else "POI접근성 단독(context 미제공)",
    }

    # ── 전역정책 Phase0: 근거·법령·신선도 공용 블록 가산(additive, graceful) ──
    # POI 접근성·통합점수 근거 트레이스 + site_score factors 근거(용도지역=zone_use 법령)
    # 를 합쳐 한 블록으로 부착. 기존 키 무손상, evidence/legal_refs/provenance만 추가.
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block
        from app.services.site_score.site_score_service import build_site_score_evidence

        items: list[dict[str, Any]] = [{
            "label": "POI 접근성 점수",
            "value": f"{poi_score}점",
            "basis": "POI 카테고리 가중치 × 거리감쇠 밴딩(250m=1.0~2500m=0.1) + 밀도보너스 — Kakao Local 반경검색",
        }]
        if integrated is not None:
            items.append({
                "label": "통합 입지점수",
                "value": f"{integrated}점",
                "basis": "POI 접근성 55% + 종합입지(상권·실거래·용도지역·지가) 45% 가중평균(연구기반)",
            })
        # 종합입지(site_score) factors 근거 — zone_use 법령키 포함.
        # POI 항목("POI 접근성 점수"·"통합 입지점수")과 factor 라벨은 겹치지 않아 그대로 합친다.
        ref_keys: list[str] = []
        if isinstance(site, dict):
            site_ev = build_site_score_evidence(site)
            for it in site_ev.get("evidence", []) or []:
                items.append(it)
            for r in site_ev.get("legal_refs", []) or []:
                k = r.get("key") if isinstance(r, dict) else None
                if k:
                    ref_keys.append(str(k))
        ev = build_evidence_block(
            items=items,
            legal_ref_keys=ref_keys or None,
            sources=["kakao_local", "vworld_zoning", "vworld_land_info", "molit_transactions"],
        )
        resp.setdefault("evidence", ev.get("evidence", []))
        resp.setdefault("legal_refs", ev.get("legal_refs", []))
        resp.setdefault("provenance", ev.get("provenance", []))
    except Exception:  # noqa: BLE001 — 근거 블록 실패해도 POI 결과 무손상
        pass

    return resp


class EnvelopeRequest(BaseModel):
    land_area_sqm: float = 0
    zone: str = ""
    land_width_m: float | None = None
    land_depth_m: float | None = None
    floor_height_m: float = 3.0
    bcr_limit_pct: float | None = None
    far_limit_pct: float | None = None
    pnu: str | None = None                 # 주면 VWorld 실측 폴리곤으로 치수 정밀화
    geometry: dict | None = None           # 직접 GeoJSON geometry 입력(선택)
    latitude: float | None = None          # 위도(동지 일영 계산, 미지정 시 37.5)


@router.post("/envelope")
async def buildable_envelope(req: EnvelopeRequest):
    """한국 정북일조 빌더블 인벨로프 — 건축가능 최대 연면적·층수·일조 손실률.

    PNU(또는 geometry) 제공 시 VWorld 실측 필지 폴리곤으로 남북깊이·동서폭·면적을
    정밀 도출(√면적 정사각 근사 대체). 부정형 필지도 실측 반영.
    """
    from app.services.site_score.solar_envelope_service import dims_from_polygon

    width, depth, area = req.land_width_m, req.land_depth_m, req.land_area_sqm
    geom_source = "입력값/근사"
    geometry = req.geometry

    road_side = None
    if req.pnu and geometry is None:
        try:
            from app.services.external_api.vworld_service import VWorldService
            vw = VWorldService()
            parcel = await vw.get_parcel_by_pnu(req.pnu)
            geometry = (parcel or {}).get("geometry")
            lc = await vw.get_land_characteristics(req.pnu)
            if lc:
                road_side = lc.get("road_side") or None  # 접도 유형(광대로/중로/세로 등)
        except Exception:  # noqa: BLE001
            geometry = None

    if geometry is not None:
        dims = dims_from_polygon(geometry)
        if dims:
            width, depth = dims["width_m"], dims["depth_m"]
            if not area or area <= 0:
                area = dims["area_sqm"]
            geom_source = f"VWorld 실측 폴리곤(부정형도 {round(dims['irregularity']*100,1)}%)"

    if not area or area <= 0:
        return {"error": "대지면적 또는 PNU/geometry가 필요합니다."}

    result = compute_buildable_envelope(
        land_area_sqm=area, zone=req.zone,
        land_width_m=width, land_depth_m=depth,
        floor_height_m=req.floor_height_m,
        bcr_limit_pct=req.bcr_limit_pct, far_limit_pct=req.far_limit_pct,
        latitude=req.latitude if req.latitude is not None else 37.5,
    )
    result["geometry_source"] = geom_source
    if road_side:
        result["road_side"] = road_side   # 접도 유형(가로구역 최고높이·개발여건 참고)
    # ── 전역정책 Phase0: 근거·법령 공용 블록 가산(additive·graceful·다른 site-score 엔드포인트 동일 패턴) ──
    #   건축가능범위 산출근거에 용적률/건폐율(국토계획법 제76·78조·시행령 제85조)·정북일조(건축법
    #   제61조·시행령 제86조) 법령링크를 제공한다(진실원천 배선 누락 해소). § 기호 대신 '제N조' 통상어.
    #   기존 키(far_pct·daylight_ceiling_m 등) 무손상, evidence/legal_refs만 추가. 산식(solar_envelope) 미접촉.
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs
        far_pct = result.get("far_pct")
        bcr_pct = result.get("bcr_pct")
        dc_m = result.get("daylight_ceiling_m")
        result.setdefault("evidence", [
            {"label": "용적률 허용 연면적", "value": f"{round(result.get('far_gfa_sqm') or 0):,}㎡",
             "basis": f"대지면적 × 용적률 {far_pct if far_pct is not None else '—'}%", "legal_ref_key": "far_limit"},
            {"label": "법정 건폐율", "value": f"{bcr_pct if bcr_pct is not None else '—'}%",
             "basis": "용도지역 안에서의 건폐율(국토계획법 시행령 제84조)", "legal_ref_key": "bcr_limit"},
            {"label": "일조 규제 높이 한도", "value": (f"{dc_m}m" if dc_m is not None else "—"),
             "basis": "정북방향 인접대지경계선 일조 사선제한(건축법 제61조·시행령 제86조)",
             "legal_ref_key": "daylight_height_dec"},
        ])
        result.setdefault("legal_refs", get_legal_refs(
            ["far_law", "far_limit", "bcr_law", "bcr_limit", "daylight_height", "daylight_height_dec"]
        ))
    except Exception:  # noqa: BLE001 — 근거 블록 실패해도 인벨로프 결과 무손상
        pass
    return result
