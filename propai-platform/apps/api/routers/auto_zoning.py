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


# ─────────────────────────────────────────────────────────────────────────────
# 신뢰 레이어(additive): 법령링크·필드 출처(provenance)·근거 트레이스.
# 기존 응답 필드는 1개도 변경하지 않고 legal_refs/inputs/evidence 3블록만 가산한다.
# law.go.kr URL은 반드시 legal_reference_registry.get_legal_refs 출력만 사용하며
# (프론트/여기서 URL 직접 조립 금지), zone_type 미확정 시 legal_refs는 빈 배열(가짜 링크 금지).
# ─────────────────────────────────────────────────────────────────────────────
def _extract_sigungu(result: dict) -> str | None:
    """응답/주소에서 시군구명을 정직하게 추출(조례 url 치환용).

    우선순위: local_ordinance.sigungu(조례서비스 추출값) → zone_limits.sigungu →
    주소 정규식("OO시/군/구"). 추출 실패 시 None(레지스트리에 sigungu 미전달 → 조례
    url_status='pending'). '미확인'은 ordinance_service의 sentinel이므로 None 취급.
    """
    lo = result.get("local_ordinance")
    if isinstance(lo, dict):
        sgg = lo.get("sigungu")
        if sgg and str(sgg).strip() and str(sgg).strip() != "미확인":
            return str(sgg).strip()
    zl = result.get("zone_limits")
    if isinstance(zl, dict):
        sgg = zl.get("sigungu")
        if sgg and str(sgg).strip() and str(sgg).strip() != "미확인":
            return str(sgg).strip()
    addr = str(result.get("address") or "")
    if addr:
        m = re.search(r"(\S{2,4}[시군구])(?:\s|$)", addr)
        if m:
            cand = m.group(1)
            if "특별" not in cand and "광역" not in cand:
                return cand
    return None


def _zone_limits_ref_keys(result: dict) -> list[str]:
    """zone_type 한도의 법령 근거키를 legal_zone_limits.legal_limits_for로 결정.

    반환은 legal_reference_registry 키 목록(중복 없는 순서 보존). zone_type 미확정·
    미매칭이면 빈 리스트(→ legal_refs 빈 배열). 조례 적용이 확인되면(아래) 호출부에서
    ordinance_far/ordinance_bcr 키를 추가한다.
    """
    zone_type = result.get("zone_type")
    if not zone_type:
        return []
    try:
        from app.services.zoning.legal_zone_limits import legal_limits_for

        legal = legal_limits_for(zone_type)
    except Exception:  # noqa: BLE001
        legal = None
    if not legal:
        return []
    ref_keys = legal.get("legal_ref_keys") or {}
    keys: list[str] = []
    # 용적률·건폐율 순으로 부착(zone_use는 일반 한도 근거가 아니라 생략 — 한도키만).
    for k in ("far", "bcr"):
        v = ref_keys.get(k)
        if v and v not in keys:
            keys.append(v)
    return keys


def _ordinance_applied(result: dict) -> bool:
    """조례 실효값이 응답에 실제로 반영되었는지 판정(가짜 조례링크 방지).

    zone_limits.ordinance_far_pct/ordinance_bcr_pct(land_info_service가 effective_*로
    주입) 또는 local_ordinance.effective_*가 raw 조례값(ordinance_far/bcr)에서 유래해
    존재하면 조례 근거 있음으로 본다. 단순히 법정상한을 그대로 쓴 경우(source=='법정상한')는
    조례 적용으로 보지 않는다.
    """
    zl = result.get("zone_limits")
    if isinstance(zl, dict):
        if zl.get("ordinance_far_pct") or zl.get("ordinance_bcr_pct"):
            return True
    lo = result.get("local_ordinance")
    if isinstance(lo, dict):
        # raw 조례값이 실제로 조회된 경우에만(법정상한 폴백은 제외).
        if lo.get("ordinance_far") or lo.get("ordinance_bcr"):
            return True
    return False


def _build_legal_refs(result: dict) -> list[dict]:
    """zone 한도·조례 근거를 레지스트리(get_legal_refs)로 직렬화해 반환(additive).

    - zone_type 미확정/미매칭 → 빈 배열(할루시네이션 링크 금지).
    - 조례 실효값이 반영된 경우 ordinance_far/ordinance_bcr 키를 추가하고 sigungu를
      전달해 조례 url을 치환(미상이면 sigungu 미전달 → url_status='pending').
    - URL은 전적으로 get_legal_refs 출력만 사용한다(여기서 URL 조립 금지).
    """
    keys = _zone_limits_ref_keys(result)
    if not keys:
        return []
    if _ordinance_applied(result):
        for ok in ("ordinance_far", "ordinance_bcr"):
            if ok not in keys:
                keys.append(ok)
    sigungu = _extract_sigungu(result)
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs(keys, sigungu=sigungu)
    except Exception:  # noqa: BLE001
        return []


def _provenance(value, source: str, method: str, confidence: str) -> dict:
    """필드 provenance 1건 구성 — value/source/method/confidence."""
    return {"value": value, "source": source, "method": method, "confidence": confidence}


def _build_inputs(result: dict) -> dict:
    """필드별 provenance(zone_type/land_area_sqm/official_price_per_sqm/pnu).

    실제 result에서 값 출처를 정직 매핑한다.
    - pnu 존재 → 외부 권위 출처(VWorld 토지특성/개별공시지가)에서 자동수집(auto, high).
    - pnu 부재 → 주소키워드 추론 폴백(_detect_zone_from_address): zone_type은 estimated/low.
    - 값이 비어 있으면 confidence='none'(있는 그대로 표기, 목업 금지).
    """
    pnu = result.get("pnu")
    has_pnu = bool(pnu)

    # zone_type 출처: PNU 있으면 VWorld 토지특성, 없으면 주소 추론.
    zone_type = result.get("zone_type")
    if not zone_type:
        zone_prov = _provenance(None, "미수집", "fallback", "none")
    elif has_pnu:
        zone_prov = _provenance(zone_type, "vworld_land_characteristics", "auto", "high")
    else:
        zone_prov = _provenance(zone_type, "추론", "estimated", "low")

    # 대지면적: land_register.area_sqm(comprehensive) 또는 land_area_sqm(analyze).
    land_area = result.get("land_area_sqm")
    if not land_area:
        lr = result.get("land_register")
        if isinstance(lr, dict):
            land_area = lr.get("area_sqm") or None
    if not land_area:
        area_prov = _provenance(None, "미수집", "fallback", "none")
    else:
        area_prov = _provenance(land_area, "vworld_land_characteristics", "auto", "high")

    # 공시지가: official_price_per_sqm 또는 official_prices[0].price_per_sqm.
    price = result.get("official_price_per_sqm")
    if not price:
        ops = result.get("official_prices")
        if isinstance(ops, list) and ops and isinstance(ops[0], dict):
            price = ops[0].get("price_per_sqm") or ops[0].get("official_price") or None
        if not price:
            lr = result.get("land_register")
            if isinstance(lr, dict):
                price = lr.get("official_price_per_sqm") or None
    if not price:
        price_prov = _provenance(None, "미수집", "fallback", "none")
    else:
        price_prov = _provenance(price, "vworld_individual_land_price", "auto", "high")

    # PNU: bcode로 구성됐는지(bcode_pnu) vs VWorld 지오코딩 — 응답엔 출처표식이 없어
    # 보수적으로 자동수집 통칭. 부재 시 none.
    if not has_pnu:
        pnu_prov = _provenance(None, "미수집", "fallback", "none")
    else:
        pnu_prov = _provenance(pnu, "vworld_geocode", "auto", "high")

    return {
        "zone_type": zone_prov,
        "land_area_sqm": area_prov,
        "official_price_per_sqm": price_prov,
        "pnu": pnu_prov,
    }


def _fmt_pct(v) -> str | None:
    """퍼센트 표기 — 250 → '250%'. None/빈값 → None."""
    if v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n == int(n):
        return f"{int(n)}%"
    return f"{n:g}%"


def _build_evidence(result: dict, legal_refs: list[dict]) -> list[dict]:
    """한도 산출 트레이스(EvidencePanel 소비 구조).

    {label, value, basis, legal_ref_key}. 법정 상한(far/bcr)을 부착하고, 조례 실효값이
    법정과 다르면 둘 다 트레이스(법정 + 조례적용). zone_type 미확정 시 빈 배열.
    """
    zone_type = result.get("zone_type")
    if not zone_type:
        return []
    try:
        from app.services.zoning.legal_zone_limits import legal_limits_for

        legal = legal_limits_for(zone_type)
    except Exception:  # noqa: BLE001
        legal = None
    if not legal:
        return []

    zone_key = legal.get("zone_type") or zone_type
    far_key = (legal.get("legal_ref_keys") or {}).get("far")
    bcr_key = (legal.get("legal_ref_keys") or {}).get("bcr")
    # legal_refs에서 조문 표기(law_name·article)를 가져와 basis를 구성(레지스트리 단일출처).
    ref_by_key = {r.get("key"): r for r in (legal_refs or [])}

    def _basis(ref_key: str) -> str:
        ref = ref_by_key.get(ref_key) or {}
        law = ref.get("law_name") or ""
        art = ref.get("article") or ""
        tail = f"{law} {art}".strip()
        return f"{zone_key} · {tail}".strip(" ·") if tail else zone_key

    evidence: list[dict] = []
    far_legal = _fmt_pct(legal.get("max_far_pct"))
    if far_legal and far_key:
        evidence.append({
            "label": "법정 용적률 상한",
            "value": far_legal,
            "basis": _basis(far_key),
            "legal_ref_key": far_key,
        })
    bcr_legal = _fmt_pct(legal.get("max_bcr_pct"))
    if bcr_legal and bcr_key:
        evidence.append({
            "label": "법정 건폐율 상한",
            "value": bcr_legal,
            "basis": _basis(bcr_key),
            "legal_ref_key": bcr_key,
        })

    # 조례 실효값이 법정과 다르면 별도 트레이스(조례 근거키로).
    zl = result.get("zone_limits") if isinstance(result.get("zone_limits"), dict) else {}
    ord_far = zl.get("ordinance_far_pct")
    if ord_far is not None and _fmt_pct(ord_far) != far_legal:
        ord_far_fmt = _fmt_pct(ord_far)
        if ord_far_fmt:
            sigungu = _extract_sigungu(result) or "지자체"
            evidence.append({
                "label": "조례 적용 용적률",
                "value": ord_far_fmt,
                "basis": f"{zone_key} · {sigungu} 도시계획 조례(실효값)",
                "legal_ref_key": "ordinance_far",
            })
    ord_bcr = zl.get("ordinance_bcr_pct")
    if ord_bcr is not None and _fmt_pct(ord_bcr) != bcr_legal:
        ord_bcr_fmt = _fmt_pct(ord_bcr)
        if ord_bcr_fmt:
            sigungu = _extract_sigungu(result) or "지자체"
            evidence.append({
                "label": "조례 적용 건폐율",
                "value": ord_bcr_fmt,
                "basis": f"{zone_key} · {sigungu} 도시계획 조례(실효값)",
                "legal_ref_key": "ordinance_bcr",
            })
    return evidence


def _attach_trust_blocks(result: dict) -> dict:
    """응답 dict에 legal_refs/inputs/evidence 3블록을 additive로 부착(in-place).

    기존 키는 setdefault로 보존(이미 있으면 덮어쓰지 않음). result가 dict가 아니거나
    부착 중 예외가 나면 원본을 그대로 반환(기존 응답 무손상 — graceful).
    """
    if not isinstance(result, dict):
        return result
    try:
        legal_refs = _build_legal_refs(result)
        result.setdefault("legal_refs", legal_refs)
        result.setdefault("inputs", _build_inputs(result))
        result.setdefault("evidence", _build_evidence(result, legal_refs))
    except Exception as e:  # noqa: BLE001
        import structlog

        structlog.get_logger().warning("신뢰 블록 부착 스킵", error=str(e)[:120])
    return result


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

    # 신뢰 레이어(additive): 법령링크·필드 출처·근거 트레이스 부착(기존 필드 무손상).
    _attach_trust_blocks(result)

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
    result = await service.collect_comprehensive(req.address, pnu=pnu)
    # 신뢰 레이어(additive): 법령링크·필드 출처·근거 트레이스 부착(기존 필드 무손상).
    return _attach_trust_blocks(result)


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
        zone_type = zone_type_2 = None
        # ── 면적 다출처 교차검증 ──
        #  ① 지적/등록면적: VWorld get_land_info(properties.area)
        #  ② 공부상(토지대장) 면적: NED 토지특성 get_land_characteristics(lndpclAr)
        #  → 토지대장(공부상)을 권위 출처로 우선, 지적도와 대조해 일치도·신뢰도 산출.
        li_area = 0.0
        lc_area = 0.0
        try:
            if geometry is None:
                li = await vworld.get_land_info(pnu)
                if li:
                    geometry = li.get("geometry")
                    li_area = float((li.get("properties") or {}).get("area") or 0)
        except Exception:  # noqa: BLE001
            pass
        try:
            lc = await vworld.get_land_characteristics(pnu)
            if lc:
                lc_area = float(lc.get("area_sqm") or 0)
                zone_type = lc.get("zone_type") or None
                zone_type_2 = lc.get("zone_type_2") or None
        except Exception:  # noqa: BLE001
            pass
        # 권위 우선: 토지대장(lc_area) → 지적등록(li_area)
        area_sqm = lc_area or li_area
        area_source = "토지대장(토지특성)" if lc_area else ("지적도 등록면적" if li_area else "미확인")
        if lc_area > 0 and li_area > 0:
            diff = abs(lc_area - li_area) / max(lc_area, li_area)
            if diff <= 0.05:
                area_confidence, area_note = "high", "토지대장·지적도 면적 일치(교차검증 통과)"
            else:
                area_confidence = "low"
                area_note = (f"면적 출처 불일치 — 토지대장 {lc_area:,.0f}㎡ vs 지적도 {li_area:,.0f}㎡"
                             f"(차이 {round(diff*100)}%). 공부상(토지대장) 면적을 우선 적용")
        elif area_sqm > 0:
            area_confidence, area_note = "mid", "단일 출처 면적(교차검증 불가)"
        else:
            area_confidence, area_note = "none", "면적 데이터 없음"

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
            # 면적 교차검증 결과(출처·신뢰도·메모) — 프론트가 검증배지로 표기.
            "area_source": area_source,
            "area_confidence": area_confidence,
            "area_note": area_note,
            "area_ledger_sqm": round(lc_area, 1) if lc_area else None,
            "area_cadastral_sqm": round(li_area, 1) if li_area else None,
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

    # ── 정밀 구획도(A+B+C+D): 주변 필지·도로(벡터 지적도) + 통합외곽선(union) + 실제 이격거리 ──
    neighbors: list[dict] = []
    merged_geometry = None
    min_gap_m: float | None = None
    try:
        import itertools
        import math

        from shapely.geometry import mapping, shape
        from shapely.ops import unary_union

        sel_shapes = [shape(f["geometry"]).buffer(0) for f in features if f.get("geometry")]
        sel_pnus = {f.get("pnu") for f in features}
        if sel_shapes:
            union_sel = unary_union(sel_shapes)
            merged_geometry = mapping(union_sel)  # B: 통합개발 외곽선(슬리버 없는 단일 경계)
            minx, miny, maxx, maxy = union_sel.bounds
            mx = max(0.0008, (maxx - minx) * 0.7)
            my = max(0.0008, (maxy - miny) * 0.7)
            # A+D: bbox 내 전체 필지(연속지적도)를 받아 정밀 벡터 지적도로 깔고, 도로 지목을 구분
            try:
                allp = await vworld.get_parcels_in_bbox(minx - mx, miny - my, maxx + mx, maxy + my, max_count=150)
            except Exception:  # noqa: BLE001
                allp = []
            for p in allp:
                if p.get("pnu") in sel_pnus or not p.get("geometry"):
                    continue
                jm = p.get("jimok") or ""
                neighbors.append({
                    "pnu": p.get("pnu"),
                    "jimok": jm,
                    "is_road": ("도로" in jm),
                    "geometry": p.get("geometry"),
                })
            # C: 선택 필지 간 실제 최소 이격(m) — "맞닿음(6m 허용)"의 실제 거리 정직 표기
            if len(sel_shapes) >= 2:
                latc = union_sel.centroid.y
                m_per_deg = 111000 * math.cos(math.radians(latc))
                gaps = [a.distance(b) for a, b in itertools.combinations(sel_shapes, 2)]
                min_gap_m = round(min(gaps) * m_per_deg, 1) if gaps else 0.0
                if adjacency.get("contiguous") and min_gap_m and min_gap_m > 0.3:
                    adjacency = {**adjacency, "note": (
                        f"필지 간 약 {min_gap_m}m 이격(도로 등) — 6m 이내라 통합개발 가능"
                    )}
    except Exception:  # noqa: BLE001 — 정밀 레이어 실패해도 기본 구획도는 반환
        pass

    return {
        "features": features,
        "center": center,
        "total_area_sqm": round(total_area, 1),
        "parcel_count": len(features),
        "adjacency": adjacency,
        "neighbors": neighbors,            # A+D: 주변 필지·도로(연회색/도로색) 벡터 지적도
        "merged_geometry": merged_geometry,  # B: 통합개발 외곽선
        "min_gap_m": min_gap_m,            # C: 실제 최소 이격(m)
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
    # ★프론트가 pnu/bcode를 못 넘기는 경우(스토어 미보유·약식검색 등)에도 빈 결과가
    #  나오지 않도록, 주소를 VWORLD 지오코딩해 PNU→LAWD_CD를 직접 구한다
    #  (parcel-boundaries와 동일 폴백). 이게 없어 강남이어도 거래 0건으로 보였음.
    if (not lawd_cd or len(lawd_cd) < 5) and req.address:
        try:
            from apps.api.app.services.external_api.vworld_service import VWorldService
            vworld = VWorldService()
            geo = await vworld.geocode_address(req.address)
            cand_pnu = (geo or {}).get("pnu")
            # 지번 PARCEL 미발견(역삼동 13 등)이라도 좌표는 나오므로, 좌표로 필지를
            # 직접 조회(point→parcel)해 pnu를 얻는다. parcel-boundaries와 동일 2차 폴백.
            if not cand_pnu and geo and geo.get("lat") and geo.get("lon"):
                pp = await vworld.get_parcel_by_point(geo["lat"], geo["lon"])
                cand_pnu = (pp or {}).get("pnu")
            if cand_pnu:
                pnu = str(cand_pnu)
                lawd_cd = pnu[:5]
        except Exception:  # noqa: BLE001
            pass
    if not lawd_cd or len(lawd_cd) < 5:
        return {"error": "법정동코드(LAWD_CD) 결정 불가 — 주소/pnu 확인 필요",
                "center": None, "categories": {}}

    # sigungu 힌트(지오코딩 폴백용): 주소 앞 2토큰
    parts = (req.address or "").split()
    sigungu_hint = " ".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "")

    service = NearbyMapService()
    return await service.build(
        address=req.address, lawd_cd=lawd_cd,
        months=req.months, radius_m=req.radius_m, sigungu_hint=sigungu_hint,
    )
