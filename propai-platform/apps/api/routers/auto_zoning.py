"""자동 용도지역 감지 + 종합 토지정보 라우터."""

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.billing_deps import enforce_llm_quota
from apps.api.app.services.land_intelligence.land_info_service import LandInfoService
from apps.api.app.services.zoning.auto_zoning_service import AutoZoningService

logger = logging.getLogger(__name__)
router = APIRouter()


class ZoningAnalyzeRequest(BaseModel):
    """용도지역 분석 요청."""

    address: str
    pnu: str | None = None
    bcode: str | None = None  # 카카오 법정동 코드 (10자리)
    jibun_address: str | None = None  # 카카오 지번 주소
    refresh: bool = False  # True면 저장된 조례 해석을 무시하고 재조사(사용자 '재분석' 실행)
    # ★다필지 통합 컨텍스트(옵셔널) — 다필지일 때 AI 해석이 대표번지가 아니라 '통합 N필지'
    #   기준으로 종합 판단하도록 주입. 미전달 시 기존(단일/대표) 동작 무회귀.
    parcel_count: int | None = None         # 통합 필지 수(>1이면 다필지 통합 해석)
    integrated_area_sqm: float | None = None  # 통합 대지면적(㎡) — 면적가중 합
    integrated_far_pct: float | None = None   # 통합(면적가중) 실효 용적률(%)
    integrated_bcr_pct: float | None = None   # 통합(면적가중) 실효 건폐율(%)


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
    if isinstance(zl, dict) and (zl.get("ordinance_far_pct") or zl.get("ordinance_bcr_pct")):
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
    - zone_type은 서비스가 표기한 zone_source 실값을 우선 사용(W-C ③):
      keyword_inference → estimated/low(PNU 유무 무관 — has_pnu 휴리스틱이 추론을
      vworld/high로 거짓 표기하던 문제 교정), vworld_* 실조회 → auto/high.
    - zone_source 미표기(구버전 응답)는 기존 has_pnu 휴리스틱 유지(하위호환).
    - 값이 비어 있으면 confidence='none'(있는 그대로 표기, 목업 금지).
    """
    pnu = result.get("pnu")
    has_pnu = bool(pnu)

    # zone_type 출처: zone_source(서비스 표기 실값) > has_pnu 휴리스틱(하위호환).
    zone_type = result.get("zone_type")
    zone_source = result.get("zone_source")
    if not zone_type:
        zone_prov = _provenance(None, "미수집", "fallback", "none")
    elif zone_source == "keyword_inference":
        # 주소키워드 추론값 — PNU가 있어도 추론은 추론으로 정직 표기.
        zone_prov = _provenance(zone_type, "keyword_inference", "estimated", "low")
    elif zone_source:
        # 실조회 출처(vworld_land_info/vworld_land_use_plan/vworld_ned 등) 그대로 표기.
        zone_prov = _provenance(zone_type, zone_source, "auto", "high")
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

    # ── 조례 용적률 SSOT(단일출처) ──
    # regulation/analyze 와 동일한 ordinance_service 를 조회해 local_ordinance(조례 한도)를 주입한다.
    # 이전: local_ordinance 가 비어 far_tier 가 법정상한(예 일반상업 1300%)으로 폴백 → regulation 의
    # 조례값(의정부 일반상업 900%)과 같은 필지에서 400%p 충돌·최대연면적 60,000㎡ 괴리. 단일출처로 통일.
    try:
        lo = result.get("local_ordinance")
        has_ord = isinstance(lo, dict) and lo.get("ordinance_far")
        if not has_ord and result.get("zone_type"):
            from app.services.land_intelligence.ordinance_service import OrdinanceService

            _ord = await OrdinanceService().get_ordinance_limits(
                req.address, result.get("zone_type") or "", force_refresh=bool(req.refresh))
            if isinstance(_ord, dict) and _ord.get("ordinance_far"):
                result["local_ordinance"] = _ord  # far_tier 가 effective_far=min(법정,조례) 로 채택
                result["ordinance_provenance"] = _ord.get("provenance")  # 출처·신뢰도·재확인 표기(정직)
    except Exception:  # noqa: BLE001 — 조례 조회 실패 시 기존 폴백 유지(무손상)
        pass

    # ── 특이부지 감지(규칙기반·additive) ──
    # 지목/용도/구역/접도에서 비일상 토지상태(학교용지·공공용지·농지·산지·맹지·규제구역)를 잡아
    # 법적·인허가 특이사항 + 개발가능성 게이트 + 해결방안 + 정직 고지를 부착한다.
    # 이로써 '학교용지를 일반상업지처럼 최대 연면적 가능'으로 오분석하는 할루시네이션을 차단.
    try:
        from app.services.zoning.special_parcel import detect_special_parcel

        special = detect_special_parcel(result)
        if special:
            result["special_parcel"] = special
            result["warnings"] = list(result.get("warnings") or []) + special.get("warnings", [])
            result["developability"] = special.get("developability")
    except Exception:  # noqa: BLE001 — 감지 실패는 기존 결과를 손상하지 않는다.
        special = None

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

        # ★다필지 통합 컨텍스트: parcel_count>1 + 통합면적이 오면 인터프리터가 대표번지가 아니라
        #   '통합 N필지' 기준으로 종합 판단하게 land_area_sqm을 통합값으로 대체하고 메타를 주입한다.
        #   (미전달 시 단일/대표 동작 무회귀 — 통합분석 미구현 근본해소.)
        _is_multi = bool(req.parcel_count and req.parcel_count > 1 and req.integrated_area_sqm and req.integrated_area_sqm > 0)
        _interp_area = float(req.integrated_area_sqm) if (_is_multi and req.integrated_area_sqm is not None) else result.get("land_area_sqm")

        interp_input = {
            "address": result.get("address"),
            "zone_type": zt,
            "land_area_sqm": _interp_area,
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
            # 특이부지(학교용지 등): LLM이 '최대 연면적 가능'을 무근거로 단언하지 않도록 그라운딩.
            "special_parcel": special,
            # ★다필지 통합: 대표번지가 아니라 '통합 N필지' 기준임을 명시(LLM이 통합 종합판단).
            "integrated": ({
                "is_multi_parcel": True,
                "parcel_count": req.parcel_count,
                "total_area_sqm": _interp_area,
                "blended_far_pct": req.integrated_far_pct,
                "blended_bcr_pct": req.integrated_bcr_pct,
                "note": f"이 분석은 대표 1필지가 아니라 통합 {req.parcel_count}필지(합계 "
                        f"{round(float(_interp_area or 0)):,}㎡) 기준입니다. 대지면적·개발규모는 통합값으로 판단하세요.",
            } if _is_multi else None),
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


@router.post("/special-parcels")
async def special_parcels_check(body: dict):
    """다필지 특이부지 종합 워크플로우 — 필지별 특이성 감지 → 대안·해결방안 → 해결불가 시 정직 고지.

    body.parcels: [{address, land_category?, zone_type?, special_districts?, pnu?}, ...]
    body.analyze(bool): true 면 land_category 미제공 필지를 주소로 실분석(느림). 기본 false(제공값 사용).

    한 필지라도 통상 절차로 해결 불가능(개발제한구역·공공기반시설 등)하면 사업 전체를 '개발 불가'로
    정직 고지하여 무리한 개발규모 산정(할루시네이션)을 차단한다.
    """
    from app.services.zoning.special_parcel import detect_multi_parcel

    parcels = body.get("parcels") or []
    if not isinstance(parcels, list) or not parcels:
        from fastapi import HTTPException
        raise HTTPException(400, "parcels(필지 배열)가 필요합니다.")

    do_analyze = bool(body.get("analyze"))
    enriched: list[dict] = []
    for p in parcels[:30]:  # 과도 호출 방지(최대 30필지)
        p = dict(p or {})
        if do_analyze and not p.get("land_category") and p.get("address"):
            try:
                p = {**(await AutoZoningService().analyze_by_address(p["address"])), **p}
            except Exception:  # noqa: BLE001 — 개별 실패는 정직하게 미분석으로 둠
                p.setdefault("warnings", []).append("분석 실패(주소 해석 불가)")
        enriched.append(p)

    return detect_multi_parcel(enriched)


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


class GeocodeRequest(BaseModel):
    """지번/주소 직접검색 — VWorld 지오코딩(Daum이 못 찾는 지번·산·농지도 해석)."""
    query: str


@router.post("/geocode")
async def geocode_query(req: GeocodeRequest):
    """주소/지번 텍스트 → 좌표·PNU·법정동코드 해석(VWorld).

    Daum 우편번호 위젯이 못 찾는 지번(산·농지·나대지 등)을 직접 입력으로 해석한다.
    무목업: 못 찾으면 found=false 정직 반환(가짜 좌표 생성 금지).
    """
    from apps.api.app.services.external_api.vworld_service import VWorldService

    q = (req.query or "").strip()
    if not q:
        return {"found": False, "query": q, "reason": "검색어가 비었습니다."}
    vworld = VWorldService()
    geo = await vworld.geocode_address(q)
    if not geo or not geo.get("lat"):
        return {"found": False, "query": q,
                "reason": "VWorld에서도 해당 주소/지번을 찾지 못했습니다. 지번 형식(예: 의정부동 224, 산 12-3)을 확인해 주세요."}
    pnu = geo.get("pnu")
    bcode = (pnu[:10] if pnu and len(pnu) >= 10 else None)
    return {
        "found": True,
        "query": q,
        "address": geo.get("address") or q,
        "jibun_address": geo.get("address") or q,
        "pnu": pnu,
        "bcode": bcode,
        "lat": geo.get("lat"),
        "lon": geo.get("lon"),
    }


class AddressSearchRequest(BaseModel):
    """지번/도로명 검색 — 다음 주소검색처럼 후보 목록(자동완성)."""
    query: str
    size: int = 8


@router.post("/search")
async def search_address(req: AddressSearchRequest):
    """지번/주소 자동완성 검색 → 후보 목록(주소·PNU·좌표).

    토지지번입력에서 타이핑하면 후보를 띄워 선택하게 한다(Daum 주소검색 UX).
    무목업: 후보 없으면 빈 배열 정직 반환(가짜 후보 생성 금지).
    """
    from apps.api.app.services.external_api.vworld_service import VWorldService

    q = (req.query or "").strip()
    if len(q) < 2:
        return {"query": q, "candidates": []}
    size = max(1, min(20, req.size or 8))
    candidates = await VWorldService().search_address(q, size=size)
    return {"query": q, "candidates": candidates}


class LandShareRequest(BaseModel):
    """대지지분(대지권) 분석 요청 — 공동주택/집합건물 호별 대지지분 산정.

    토지조서 정확화: 세대(동·호)별 대지지분 합 = 대지(필지)면적 검증.
    pnu 우선, 없으면 address/jibun을 VWorld 지오코딩으로 PNU 확보.
    """
    pnu: str | None = None
    address: str | None = None


@router.post("/land-share")
async def land_share(req: LandShareRequest):
    """공동주택/집합건물 세대별 대지지분 분석(토지조서 보강).

    건축물대장 표제부(대지면적)+전유공용면적(호별 전유면적)으로 호별 대지지분을
    전유 비례 산정하고, Σ세대 대지지분 = 대지면적 정합을 검증한다.
    무목업: 전유부 무자료=토지/단독으로 정직 분기(is_aggregate=false).
    """
    from apps.api.app.services.land_intelligence.land_share_service import LandShareService

    svc = LandShareService()
    pnu = (req.pnu or "").strip()
    addr = (req.address or "").strip()
    if not (pnu and len(pnu) >= 19) and not addr:
        return {"is_aggregate": False, "reason": "pnu(19자리) 또는 address가 필요합니다."}
    # 예외를 raw 500으로 흘리지 않고 무목업 정직 분기로 반환(가짜 생성 금지).
    try:
        if pnu and len(pnu) >= 19:
            return await svc.analyze_by_pnu(pnu)
        return await svc.analyze_by_address(addr)
    except Exception as e:  # noqa: BLE001
        logger.warning("대지지분 분석 실패: %s (%s)", pnu or addr, str(e))
        return {"is_aggregate": False, "pnu": pnu or None, "address": addr or None,
                "reason": "대지지분 분석 중 오류가 발생했습니다. 잠시 후 다시 시도하세요."}


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
    from datetime import datetime

    from apps.api.app.services.external_api.building_registry_service import BuildingRegistryService
    from apps.api.app.services.external_api.vworld_service import VWorldService

    # 입력 정규화: parcels 배열 우선, 없으면 단일(address/pnu)
    items: list[dict] = list(req.parcels or [])
    if not items and (req.address or req.pnu):
        items = [{"address": req.address, "pnu": req.pnu}]
    if not items:
        return {"features": [], "center": None, "total_area_sqm": 0}

    vworld = VWorldService()
    building_registry = BuildingRegistryService()
    current_year = datetime.now().year
    enable_building_age = len(items) <= 40

    async def _resolve_one(it: dict) -> dict | None:
        """단일 필지의 경계·면적·용도지역을 조회해 feature dict를 만든다.

        ★의존순서 보존: PNU 미확보 시 geocode_address → (좌표 의존) get_parcel_by_point는
        순차로 수행해야 한다(뒤 호출이 앞 결과에 의존). PNU 확보 이후의 get_land_info(경계)와
        get_land_characteristics(용도/면적)는 서로 독립이므로 asyncio.gather로 병렬 호출한다.
        한 필지 실패는 None을 돌려 전체를 깨지 않는다(상위 gather에서 격리).
        """
        pnu = it.get("pnu")
        address = it.get("address") or ""
        if not pnu and it.get("bcode") and it.get("jibun_address"):
            pnu = _build_pnu_from_bcode(it["bcode"], it["jibun_address"])
        coords = None
        point_geom = None
        # PNU가 없으면 주소 지오코딩 (이후 좌표 폴백이 이 결과에 의존 → 순차 유지)
        if not pnu and address:
            try:
                geo = await vworld.geocode_address(address)
                if geo:
                    pnu = geo.get("pnu")
                    coords = {"lat": geo.get("lat"), "lon": geo.get("lon")}
            except Exception:  # noqa: BLE001
                pass
        # 도로명주소 등 PNU 미확보 시: 좌표로 필지 직접 조회(점 기반) — geocode 좌표에 의존
        if not pnu and coords and coords.get("lat") and coords.get("lon"):
            try:
                pp = await vworld.get_parcel_by_point(coords["lat"], coords["lon"])
                if pp:
                    pnu = pp.get("pnu")
                    point_geom = pp.get("geometry")
            except Exception:  # noqa: BLE001
                pass
        if not pnu:
            return None

        geometry = point_geom
        zone_type = zone_type_2 = None
        # ── 면적 다출처 교차검증 ──
        #  ① 지적/등록면적: VWorld get_land_info(properties.area)
        #  ② 공부상(토지대장) 면적: NED 토지특성 get_land_characteristics(lndpclAr)
        #  → 토지대장(공부상)을 권위 출처로 우선, 지적도와 대조해 일치도·신뢰도 산출.
        #  ★두 호출은 PNU만 필요하고 서로 독립 → gather로 동시에(순차 30s+15s 대신 병렬).
        li_area = 0.0
        lc_area = 0.0
        need_li = geometry is None  # point_geom이 이미 있으면 land_info 생략
        # PNU만 필요한 두 호출을 동시에. land_info는 geometry 없을 때만 코루틴을 추가한다.
        coros = []
        if need_li:
            coros.append(vworld.get_land_info(pnu))
        coros.append(vworld.get_land_characteristics(pnu))
        gathered = await asyncio.gather(*coros, return_exceptions=True)
        li_res = gathered[0] if need_li else None
        lc_res = gathered[-1]
        if need_li and isinstance(li_res, dict):
            geometry = li_res.get("geometry")
            li_area = float((li_res.get("properties") or {}).get("area") or 0)
        official_price_per_sqm = None
        jimok = land_use_situation = terrain = None
        building_name = main_purpose = use_approval_date = None
        built_year = building_age_years = None
        if isinstance(lc_res, dict):
            lc_area = float(lc_res.get("area_sqm") or 0)
            zone_type = lc_res.get("zone_type") or None
            zone_type_2 = lc_res.get("zone_type_2") or None
            # 공시지가(개별공시지가, 원/㎡) — get_land_characteristics가 이미 반환(추가 호출 0).
            #  P4 공시지가 레이어용. 0/누락은 None(가짜값 금지).
            _op = lc_res.get("official_price_per_sqm")
            official_price_per_sqm = int(_op) if _op else None
            # 다필지 종합분석용 필지속성·형질(이미 fetch된 토지특성 재사용·추가 호출 0).
            jimok = lc_res.get("land_category") or None             # 지목(대/전/답…)
            land_use_situation = lc_res.get("land_use_situation") or None  # 이용상황
            terrain = lc_res.get("terrain_form") or lc_res.get("terrain_height") or None  # 형상·지세
        # 건축물 노후도: 건축물대장 표제부 사용승인일 기반. 키/무자료/대량은 None(가짜 생성 금지).
        if enable_building_age:
            try:
                bldg = await building_registry.get_title_by_pnu(pnu)
                if isinstance(bldg, dict):
                    building_name = bldg.get("building_name") or None
                    main_purpose = bldg.get("main_purpose") or None
                    use_approval_date = str(bldg.get("use_approval_date") or "").strip() or None
                    year_str = (use_approval_date or "")[:4]
                    if year_str.isdigit():
                        built_year = int(year_str)
                        if 1800 <= built_year <= current_year:
                            building_age_years = current_year - built_year
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

        # 좌표(중심) 보강 — 위에서 좌표를 못 구한 경우에만 추가 지오코딩(순차)
        if not coords:
            try:
                geo = await vworld.geocode_address(address) if address else None
                if geo:
                    coords = {"lat": geo.get("lat"), "lon": geo.get("lon")}
            except Exception:  # noqa: BLE001
                pass

        return {
            "_coords": coords if (coords and coords.get("lat") and coords.get("lon")) else None,
            "_area_sqm": area_sqm,
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
            "official_price_per_sqm": official_price_per_sqm,
            "jimok": jimok,                          # 지목(다필지 종합분석)
            "land_use_situation": land_use_situation,  # 이용상황
            "terrain": terrain,                      # 형상·지세
            "building_name": building_name,
            "main_purpose": main_purpose,
            "use_approval_date": use_approval_date,
            "built_year": built_year,
            "building_age_years": building_age_years,
            "geometry": geometry,
        }

    # ★다필지면 필지 간 완전 독립 → 병렬 처리(가장 느린 한 필지 시간으로 수렴).
    #  한 필지 예외는 return_exceptions로 격리해 나머지 필지를 살린다(항상 200 보존).
    results = await asyncio.gather(
        *[_resolve_one(it) for it in items], return_exceptions=True
    )

    features: list[dict] = []
    total_area = 0.0
    lat_sum = lon_sum = 0.0
    coord_n = 0
    for r in results:
        if not isinstance(r, dict):
            continue
        coords = r.pop("_coords", None)
        area_sqm = r.pop("_area_sqm", 0.0)
        if coords:
            lat_sum += coords["lat"]
            lon_sum += coords["lon"]
            coord_n += 1
        total_area += area_sqm
        features.append(r)

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

    # ── 다필지 종합분석 — 필지별 속성·형질 차이 + 통합 지표(개발사업분석 기반) ──
    integrated_analysis = None
    if features:
        zone_set = sorted({f["zone_type"] for f in features if f.get("zone_type")})
        jimok_set = sorted({f["jimok"] for f in features if f.get("jimok")})
        priced = [(f["official_price_per_sqm"], f.get("area_sqm") or 0)
                  for f in features if f.get("official_price_per_sqm")]
        pvals = [p for p, _a in priced]
        wsum = sum(p * a for p, a in priced)
        asum = sum(a for _p, a in priced if a)
        notes: list[str] = []
        if len(zone_set) > 1:
            notes.append(f"용도지역 상이({'·'.join(zone_set)}) — 필지별 건폐율·용적률 한도 차이, 통합 시 가중·분리 검토")
        if len(jimok_set) > 1:
            notes.append(f"지목 상이({'·'.join(jimok_set)}) — 형질변경·지목변경 필요 가능")
        if adjacency.get("contiguous") is False:
            notes.append("필지 비인접 — 통합개발 제약(분리개발 또는 진입로 확보 검토)")
        elif adjacency.get("contiguous") is True and len(features) >= 2:
            notes.append("필지 인접 — 통합개발 가능(합필·공동개발 검토)")
        # ── 면적가중 실질 건폐율·용적률 + 가능 건축규모(개발사업분석 핵심) ──
        #  필지별 용도지역 한도가 다르면 단순 적용 불가 → 면적가중으로 통합 실질치를 산정한다.
        #  통합 건축면적 = Σ(필지면적×건폐율), 통합 연면적 = Σ(필지면적×용적률) → 합을 총면적으로 나눠 실질%.
        lim = [(f.get("area_sqm") or 0, (f.get("zone_limits") or {})) for f in features]
        a_for_limit = sum(a for a, zl in lim if a and zl.get("max_bcr_pct"))
        buildable_area = sum(a * (zl.get("max_bcr_pct") or 0) / 100 for a, zl in lim)
        total_gfa = sum(a * (zl.get("max_far_pct") or 0) / 100 for a, zl in lim)
        eff_bcr = round(buildable_area / a_for_limit * 100, 1) if a_for_limit else None
        eff_far = round(total_gfa / a_for_limit * 100, 1) if a_for_limit else None

        # ── 개발가능방법 + 최적추진방안 제안(총면적·인접성·용도혼재 기반) ──
        methods: list[str] = []
        recommendation = ""
        if adjacency.get("contiguous") is False:
            methods.append("분리개발(필지별)")
            recommendation = ("필지가 비인접 — 통합개발 전 합필·진입로(맹지 해소) 선행 또는 필지별 분리개발. "
                              "인접성 확보 시 아래 통합방안 적용 가능.")
        else:
            if total_area >= 10000:
                methods += ["지구단위계획", "도시개발사업"]
                recommendation = f"총 {round(total_area/3.305785):,}평(대규모) — 지구단위계획/도시개발사업으로 통합개발 권장."
            elif total_area >= 1000:
                methods += ["가로주택정비사업", "소규모재건축", "지구단위계획"]
                recommendation = f"총 {round(total_area/3.305785):,}평(중소규모) — 가로주택정비·소규모정비 또는 지구단위 검토."
            else:
                methods.append("일반 건축(소규모)")
                recommendation = f"총 {round(total_area/3.305785):,}평(소규모) — 일반 건축허가로 단독·통합 개발."
            if len(zone_set) > 1:
                methods.append("지구단위계획(용도혼재 통합관리)")
                recommendation += " 용도지역 혼재로 실질 한도는 면적가중치이며, 지구단위계획으로 통합 관리 시 최적."

        integrated_analysis = {
            "parcel_count": len(features),
            "total_area_sqm": round(total_area, 1),
            "total_area_pyeong": round(total_area / 3.305785, 1),
            "zone_types": zone_set,
            "zone_mixed": len(zone_set) > 1,        # ★용도지역 혼재 여부(종합분석 핵심)
            "jimoks": jimok_set,
            "official_price_min": min(pvals) if pvals else None,
            "official_price_max": max(pvals) if pvals else None,
            "official_price_weighted_avg": round(wsum / asum) if asum else None,  # 면적가중 평균공시지가
            "contiguous": adjacency.get("contiguous"),
            # ★실질 건폐율·용적률(면적가중) + 가능 건축규모 — 다필지 통합 개발 기준.
            "effective_bcr_pct": eff_bcr,
            "effective_far_pct": eff_far,
            "buildable_area_sqm": round(buildable_area, 1) if buildable_area else None,
            "total_gfa_sqm": round(total_gfa, 1) if total_gfa else None,
            # ★개발가능방법 + 최적추진방안.
            "development_methods": methods,
            "recommendation": recommendation,
            "methods_note": "정밀 적용판정은 /development-methods/scenarios(인접성·정책 시뮬)로 확인하세요.",
            "notes": notes,
        }

    return {
        "features": features,
        "center": center,
        "total_area_sqm": round(total_area, 1),
        "parcel_count": len(features),
        "integrated_analysis": integrated_analysis,  # ★다필지 종합분석(속성·형질 차이+통합지표)
        "adjacency": adjacency,
        "neighbors": neighbors,            # A+D: 주변 필지·도로(연회색/도로색) 벡터 지적도
        "merged_geometry": merged_geometry,  # B: 통합개발 외곽선
        "min_gap_m": min_gap_m,            # C: 실제 최소 이격(m)
    }


# ── 구획도(필지 경계) 다운로드 — GeoJSON / PNG / PDF (P3) ──
#   기존 parcel_boundaries() 결과(features + merged_geometry)를 재사용. 직렬화/렌더는 서비스
#   모듈(parcel_boundary_export·parcel_boundary_pdf)에 위임해 라우터를 슬림·테스트 가능하게 한다.
class ParcelExportRequest(ParcelBoundariesRequest):
    format: str = "geojson"  # geojson | png | pdf


@router.post("/parcel-boundaries/export")
async def parcel_boundaries_export(req: ParcelExportRequest):
    """구획도(필지 경계) 다운로드 — format: geojson | png | pdf.

    parcel_boundaries() 결과(features+merged_geometry)를 재사용. GeoJSON은 무의존(항상 가능),
    PNG는 matplotlib, PDF는 reportlab(미설치 시 415 정직 안내). 무목업: 데이터 없으면 400.
    """
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse, Response

    from app.services.land_intelligence.parcel_boundary_export import export_geojson, export_png

    base = ParcelBoundariesRequest(parcels=req.parcels, address=req.address, pnu=req.pnu)
    result = await parcel_boundaries(base)
    if not result.get("features"):
        raise HTTPException(400, "구획도를 생성할 필지가 없습니다(주소/PNU 확인).")

    fmt = (req.format or "geojson").lower()
    fname = f"parcel_boundary_{result.get('parcel_count', 0)}lots"

    if fmt == "geojson":
        return JSONResponse(
            export_geojson(result),
            headers={"Content-Disposition": f'attachment; filename="{fname}.geojson"'},
            media_type="application/geo+json",
        )
    if fmt == "png":
        try:
            png = export_png(result)
        except Exception as e:  # noqa: BLE001 — 렌더 실패는 정직 안내(가짜 이미지 금지)
            raise HTTPException(415, f"PNG 렌더 실패: {str(e)[:120]}") from e
        return Response(png, media_type="image/png",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.png"'})
    if fmt == "pdf":
        try:
            from app.services.land_intelligence.parcel_boundary_pdf import build_parcel_boundary_pdf
            pdf = build_parcel_boundary_pdf(result)
        except ImportError:
            raise HTTPException(
                415, "PDF 생성 모듈(reportlab) 미설치 — GeoJSON/PNG로 다운로드하세요.") from None
        except Exception as e:  # noqa: BLE001
            raise HTTPException(415, f"PDF 생성 실패: {str(e)[:120]}") from e
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})
    raise HTTPException(400, f"지원하지 않는 형식: {fmt} (geojson|png|pdf)")


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
    # 지도 중심 힌트: 아래 지오코딩(주소→좌표)에서 확보한 좌표를 보관해 서비스에 넘긴다.
    #   ★서비스 내부의 주소 재지오코딩이 일시 실패해도 이 힌트로 center를 채워, 지도가
    #    선택 필지 위치로 이동한다(백엔드 지오코딩 실패 시 서울 폴백 고착 제거).
    center_hint: dict[str, float] | None = None
    # ★프론트가 pnu/bcode를 못 넘기는 경우(스토어 미보유·약식검색 등)에도 빈 결과가
    #  나오지 않도록, 주소를 VWORLD 지오코딩해 PNU→LAWD_CD를 직접 구한다
    #  (parcel-boundaries와 동일 폴백). 이게 없어 강남이어도 거래 0건으로 보였음.
    #  그리고 이때 얻은 좌표를 center_hint로 보관해, 서비스 내부 재지오코딩이 실패해도
    #  center가 서울로 폴백되지 않게 한다(pnu 이미 확보돼 이 블록을 건너뛴 경우는 프론트가
    #  parcel-boundaries geometry center로 폴백 — 이중 안전망).
    if (not lawd_cd or len(lawd_cd) < 5) and req.address:
        try:
            from apps.api.app.services.external_api.vworld_service import VWorldService
            vworld = VWorldService()
            geo = await vworld.geocode_address(req.address)
            cand_pnu = (geo or {}).get("pnu")
            if geo and geo.get("lat") and geo.get("lon"):
                center_hint = {"lat": float(geo["lat"]), "lon": float(geo["lon"])}
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
        center_hint=center_hint,
    )


# ─────────────────────────────────────────────────────────────
# 다필지 토지조서 엑셀 — 표준 양식 다운로드 + 업로드 파싱(주소·필지 추출)
# ─────────────────────────────────────────────────────────────
@router.get("/land-schedule-template")
async def land_schedule_template():
    """플랫폼 최적 다필지 토지조서 엑셀 양식 다운로드(작성안내 포함)."""
    from apps.api.app.services.land_intelligence.parcel_excel_service import (
        build_template_xlsx,
    )

    data = build_template_xlsx()
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="PropAI_land_schedule_template.xlsx"'},
    )


def _zone_legal_limits(zone: str | None) -> tuple[int | None, int | None]:
    """용도지역명 → 법정 (건폐율, 용적률) 상한(ZONE_LIMITS). 정확일치 우선·최장명 폴백."""
    from apps.api.app.services.zoning.auto_zoning_service import ZONE_LIMITS
    if not zone:
        return (None, None)
    z = zone.replace(" ", "").strip()
    # 정확일치 우선 → '입력값이 정식 용도지역명을 포함'(key in z)만 폴백.
    #   (z in k 방향은 짧은/깨진 문자열의 과매칭 위험이라 제거. 후보 다수면 최장명 우선.)
    if z in ZONE_LIMITS:
        key = z
    else:
        cands = [k for k in ZONE_LIMITS if k in z]
        key = max(cands, key=len) if cands else None
    if not key:
        return (None, None)
    return (ZONE_LIMITS[key]["max_bcr"], ZONE_LIMITS[key]["max_far"])


async def _enrich_effective_and_special(enriched: list[dict]) -> None:
    """enrich_parcel_list 결과 각 필지에 실효 용적률/건폐율(조례 반영)+특이부지 게이트를 in-place 부착.

    ★parcels-info·land-report 공용(단일출처) — 두 소비처가 far_pct/bcr_pct(실효)·
    far_legal_pct/bcr_legal_pct(법정상한)·special_parcel을 동일한 의미로 받게 한다.
    각 dict에 채우는 키: bcr_legal/far_legal·bcr_eff/far_eff·far_basis·special.
    calc_effective_far는 순수 동기 함수(이벤트루프 미접촉)라 async 핸들러에서 await 없이 안전.
    OrdinanceService.get_ordinance_limits만 async → await. 무목업: 실패는 법정값 폴백(정직).
    """
    from apps.api.app.services.land_intelligence.far_tier_service import calc_effective_far
    from apps.api.app.services.land_intelligence.ordinance_service import OrdinanceService
    from apps.api.app.services.zoning.special_parcel import detect_special_parcel

    # ── 조례(실효 용적률/건폐율) 조회는 시·군·구별로 1회만(필지마다 외부콜 금지).
    #    같은 (지역 키, 용도지역) 조합은 캐시 재사용해 대량 다필지에서도 외부콜을 최소화한다.
    ord_svc = OrdinanceService()
    ord_cache: dict[tuple[str, str], dict | None] = {}

    async def _ordinance_for(addr: str | None, zone: str | None) -> dict | None:
        """주소(시군구 추출)+용도지역 → 조례 effective_far/bcr. (지역,용도) 캐시 재사용."""
        if not zone or not addr:
            return None
        # 지역 키: OrdinanceService 와 동일한 시군구 추출을 캐시키로 사용(주소 전체 대신 시군구).
        try:
            region = ord_svc._extract_region(addr)  # noqa: SLF001 — 캐시키 일관성용 내부 추출 재사용
            region_key = f"{region.get('sido') or ''}|{region.get('sigungu') or ''}"
        except Exception:  # noqa: BLE001
            region_key = addr.strip()
        ck = (region_key, zone)
        if ck in ord_cache:
            return ord_cache[ck]
        try:
            res = await ord_svc.get_ordinance_limits(addr, zone)
        except Exception:  # noqa: BLE001 — 조례 조회 실패는 법정값 폴백(정직)
            res = None
        ord_cache[ck] = res
        return res

    for p in enriched:
        zone = p.get("zone_type")
        bcr_legal, far_legal = _zone_legal_limits(zone)

        # ── 실효 용적률/건폐율(조례 반영) — 미확보 지역은 effective=legal 폴백(정직).
        bcr_eff = bcr_legal
        far_eff = far_legal
        far_basis = None
        if zone:
            ordinance = await _ordinance_for(p.get("address") or p.get("jibun"), zone)
            try:
                eff = calc_effective_far(
                    {"local_ordinance": ordinance or {}, "zone_limits": {}, "special_districts": []},
                    zone_type=zone,
                    land_area=float(p.get("area_sqm") or 0) or 0,
                )
                # 실효값은 calc_effective_far 가 용도지역 법정 SSOT(legal_*)로 산출 — 값이 나오면 채택.
                if eff.get("effective_far_pct") is not None:
                    far_eff = eff.get("effective_far_pct")
                if eff.get("effective_bcr_pct") is not None:
                    bcr_eff = eff.get("effective_bcr_pct")
                far_basis = eff.get("far_basis")
            except Exception:  # noqa: BLE001 — 실효 산출 실패는 법정값 유지(무손상)
                pass

        # ── 특이부지 감지(임야/산지·농지·GB·맹지·학교용지 등) — 단일분석과 동일 게이트.
        #    입력은 보유값으로만 구성(road 정보 None → 맹지 오탐 방지, special_districts 미보유=[]).
        special = None
        sp = None
        try:
            sp = detect_special_parcel({
                "zone_type": zone,
                "land_category": p.get("jimok"),
                "special_districts": [],
                "road_contact": None,
                "road_width_m": None,
            })
        except Exception:  # noqa: BLE001 — 감지 실패는 정직하게 미표기(가짜 생성 금지)
            sp = None
        if sp and sp.get("is_special"):
            # 카드용 요약(가벼운 핵심만) — 상세는 단일분석 화면에서 제공.
            special = {
                "is_special": True,
                "developability": sp.get("developability"),
                "resolvable": sp.get("resolvable"),
                "severity_label": sp.get("severity_label"),
                # factors 의 category 만 추려 배지 라벨로(전체 implications/legal_basis 는 제외해 페이로드 경량화).
                "factors": [f.get("category") for f in (sp.get("factors") or []) if f.get("category")],
                "honest_disclosure": sp.get("honest_disclosure"),
            }
            # 특이부지면 경고를 필지 reason 에도 합류(기존 reason 보존 — 앞에 덧붙임).
            warn = (sp.get("warnings") or [None])[0] or sp.get("development_caveat")
            if warn:
                special["warning"] = warn

        # in-place 부착(소비처가 동일 의미로 꺼내 쓴다).
        p["_bcr_legal"] = bcr_legal
        p["_far_legal"] = far_legal
        p["_bcr_eff"] = bcr_eff
        p["_far_eff"] = far_eff
        p["_far_basis"] = far_basis
        p["_special"] = special


class ParcelsInfoRequest(BaseModel):
    """다필지 토지정보 일괄 보강 요청 — 개별등록·엑셀 공통."""
    parcels: list[dict] = []  # [{address?, jibun?, pnu?, bcode?}]


@router.post("/parcels-info")
async def parcels_info(req: ParcelsInfoRequest):
    """다필지 각각의 토지정보(면적·용도지역·건폐율·용적률·지목·공시지가)+집합건물 여부 일괄 보강.

    ★처음 1필지만 분석되던 문제 근본수정: 등록된 모든 필지가 부지정보를 갖도록 일괄 조회.
    건폐율/용적률(far_pct/bcr_pct)은 실효값(조례 반영, 단일분석 수준)으로 산출하고, 법정상한은
    far_legal_pct/bcr_legal_pct로 분리 노출(land-report와 동일 의미·공용 헬퍼). 공동주택(빌라)이면
    building 플래그로 호실·대지지분 안내. 무목업: 실패 필지는 status로 정직표기(가짜값 금지).
    LLM 미사용=과금 없음.
    """
    from apps.api.app.services.land_intelligence.parcel_excel_service import ParcelExcelService

    items = (req.parcels or [])[:120]  # 1회 상한(필지당 최대 3 외부콜 — 대량은 클라가 분할 호출)
    if not items:
        return {"parcels": []}

    enriched = await ParcelExcelService().enrich_parcel_list(items, with_building=True)
    # 실효 용적률/건폐율(조례 반영)+특이부지 게이트를 공용 헬퍼로 부착(land-report와 동일 의미).
    await _enrich_effective_and_special(enriched)

    out = []
    for p in enriched:
        out.append({
            "__rid": p.get("rid"),  # 호출측 행 식별자 echo — 주소 충돌 없이 정확 매칭
            "address": p.get("address"), "jibun": p.get("jibun"), "pnu": p.get("pnu"),
            "area_sqm": p.get("area_sqm"), "zone_type": p.get("zone_type"),
            # 입력 면적이 공부상과 크게 달라 보정한 경우 — 입력값·경고를 함께 노출(정직 교차검증).
            "area_input_sqm": p.get("area_input_sqm"), "area_warning": p.get("area_warning"),
            "jimok": p.get("jimok"), "official_price_per_sqm": p.get("official_price_per_sqm"),
            # ★ far_pct/bcr_pct = 실효값(조례 반영) — 카드 하단요약과 일치(단일분석 수준).
            #    법정상한은 far_legal_pct/bcr_legal_pct 로 분리 노출(보조 라벨용). 실효=법정이면 동일.
            "bcr_pct": p.get("_bcr_eff"), "far_pct": p.get("_far_eff"),
            "bcr_legal_pct": p.get("_bcr_legal"), "far_legal_pct": p.get("_far_legal"),
            "bcr_effective_pct": p.get("_bcr_eff"), "far_effective_pct": p.get("_far_eff"),
            "far_basis": p.get("_far_basis"),
            "special_parcel": p.get("_special"),  # None 이면 일상 필지(특이 없음)
            "building": p.get("building"),
            "status": p.get("status", "ok"), "reason": p.get("reason"),
        })
    return {"parcels": out}


class IntegratedAnalysisRequest(BaseModel):
    """다필지 통합분석 요청 — 통합 용도지역·실효/법정 한도·통합 GFA·인접성·게이트·시나리오.

    parcels: [{pnu?, address?, jibun?, bcode?, area_sqm?, land_category?, zone_type?, geometry?}]
    equity_won: 시나리오 위임(auto_recommend_top3)용 자기자본(미지정 시 서비스 기본).
    use_llm: 기본 false(무과금). True일 때만 시나리오 AI 내러티브 포함(규칙기반 통합집계는 무과금).
    """
    parcels: list[dict] = []
    equity_won: int | None = None
    use_llm: bool = False


@router.post("/integrated-analysis")
async def integrated_analysis(req: IntegratedAnalysisRequest):
    """다필지 '통합분석'(통합면적이 아니라 통합 용도/건폐/용적/개발방향) — additive·정직.

    파이프라인(전부 기존함수 재사용):
      enrich_parcel_list 보강 → _enrich_effective_and_special(필지별 실효+특이 in-place)
      → detect_multi_parcel(통합 게이트) → _parcel_adjacency(인접성) → _aggregate_integrated_zoning(집계).
    시나리오(BE-3): 게이트/인접성에 따라 blocked·tentative·computed로 분기. computed 시
      FeasibilityServiceV2.auto_recommend_top3에 통합면적·dominant 용도·blended 한도로 1회 위임.
    무목업: 미확보·degrade는 null + warnings(가짜값 금지). 무과금: use_llm 기본 false.
    """
    from app.services.zoning.special_parcel import (
        _aggregate_integrated_zoning,
        detect_multi_parcel,
        gate_decision,
    )
    from apps.api.app.services.land_intelligence.parcel_excel_service import ParcelExcelService

    raw_parcels = req.parcels or []
    if not isinstance(raw_parcels, list) or not raw_parcels:
        from fastapi import HTTPException
        raise HTTPException(400, "parcels(필지 배열)가 필요합니다.")

    warnings: list[str] = []
    items = raw_parcels[:120]  # 1회 상한(대량은 클라가 분할 호출)

    # ── 1) enrich_parcel_list 보강(면적·용도지역·지목·공시지가). 입력 override는 보강 후 우선 적용.
    enriched = await ParcelExcelService().enrich_parcel_list(items, with_building=True)
    # 입력에서 사용자가 직접 준 zone_type/land_category/area_sqm/geometry override를 병합(정직 우선).
    #   enrich가 채운 값이 없거나 입력값이 명시되면 입력을 채택(가짜 생성 아님 — 사용자 제공 실값).
    for src, p in zip(items, enriched, strict=False):
        if src.get("zone_type") and not p.get("zone_type"):
            p["zone_type"] = src["zone_type"]
        # land_category: enrich는 jimok 키로 채운다 → detect_*가 읽는 land_category로 정렬.
        lc = src.get("land_category") or p.get("jimok")
        if lc:
            p.setdefault("land_category", lc)
        if src.get("geometry") is not None:
            p["geometry"] = src["geometry"]
        if src.get("area_sqm") and not p.get("area_sqm"):
            p["area_sqm"] = src["area_sqm"]

    # ── 2) 필지별 실효(조례)+법정+특이 게이트 in-place 부착(공용 헬퍼 — land-report와 동일 의미).
    await _enrich_effective_and_special(enriched)

    # ── 3) 통합 게이트(detect_multi_parcel) — land_category 키로 특이부지 종합 판정.
    #     detect_*는 land_category/zone_type/pnu/address를 읽으므로 jimok→land_category 보강.
    gate_input: list[dict] = []
    for p in enriched:
        gate_input.append({
            **p,
            "land_category": p.get("land_category") or p.get("jimok"),
        })
    multi = detect_multi_parcel(gate_input)
    developability = multi.get("developability")
    resolvable = multi.get("resolvable")
    blocking_parcels = multi.get("blocking_parcels") or []
    honest_disclosure = multi.get("honest_disclosure")

    # ── 4) 인접성(_parcel_adjacency) — geometry 부족 다수면 contiguous=None(미확정 정직고지).
    geoms = [p.get("geometry") for p in enriched]
    present = [g for g in geoms if g]
    if len(present) < 2 and len(enriched) >= 2:
        # 형상 데이터가 2개 미만 → 인접성 확인 불가(가짜 True 금지).
        adjacency = {"contiguous": None, "components": None,
                     "note": "형상(geometry) 데이터 부족 — 인접성 확인 불가(통합개발 가능 여부 미확정)"}
        warnings.append("필지 형상(geometry) 미확보 다수 — 인접성 미확정으로 통합 시나리오는 잠정 처리됩니다.")
    else:
        adjacency = _parcel_adjacency(geoms)

    # ── 5) 통합 용도/건폐/용적/GFA 집계(순수함수·외부콜 0).
    integrated_zoning = _aggregate_integrated_zoning(enriched)
    warnings.extend(integrated_zoning.get("warnings") or [])

    # per_parcel(정직·경량) — 필지별 실효/법정/특이 요약(통합 산출 근거 추적용).
    per_parcel: list[dict] = []
    for p in enriched:
        per_parcel.append({
            "pnu": p.get("pnu"), "address": p.get("address"),
            "area_sqm": p.get("area_sqm"), "zone_type": p.get("zone_type"),
            "land_category": p.get("land_category") or p.get("jimok"),
            "bcr_eff_pct": p.get("_bcr_eff"), "far_eff_pct": p.get("_far_eff"),
            "bcr_legal_pct": p.get("_bcr_legal"), "far_legal_pct": p.get("_far_legal"),
            "far_basis": p.get("_far_basis"),
            "special_parcel": p.get("_special"),
            "status": p.get("status", "ok"), "reason": p.get("reason"),
        })

    # ── 6) 통합 시나리오(BE-3) — 게이트·인접성에 따라 blocked / tentative / computed.
    contiguous = adjacency.get("contiguous")
    gate = gate_decision(developability, resolvable)
    total_area = integrated_zoning.get("total_area_sqm")
    dominant_zone = integrated_zoning.get("dominant_zone")
    scenario: dict = {}

    if gate == "BLOCK" or contiguous is False:
        # 원천 차단 — 시나리오 미산정(가짜 개발규모 금지), 정직고지.
        reason = honest_disclosure or "통합개발 제약(개발 불가 또는 필지 비인접)으로 개발규모를 산정하지 않습니다."
        if contiguous is False:
            reason = (honest_disclosure + " " if honest_disclosure else "") + \
                "필지가 비인접하여 통합개발이 불가합니다(분리개발 또는 진입로 확보 선행)."
        scenario = {"status": "blocked", "disclosure": reason, "recommendations": []}
    elif contiguous is None:
        # 인접성 미확정 — 시나리오 잠정(정직고지). 확정 % 억제.
        scenario = {
            "status": "tentative",
            "disclosure": "필지 인접성이 미확정(형상 데이터 부족)이라 통합 시나리오는 잠정치입니다(확정 아님). "
                          "지적도 형상 확보 후 통합개발 가능 여부를 확정하십시오.",
            "recommendations": [],
        }
    elif gate == "TENTATIVE":
        # 조건부(인허가·전용·협의·선행절차 전제) — 시나리오 산정하되 확정 % 억제 신호.
        scenario = {
            "status": "tentative",
            "disclosure": honest_disclosure
            or "선행절차 통과를 전제로 한 잠정치입니다(확정 아님). 확정 % 표시는 억제됩니다.",
            "recommendations": [],
        }
    else:
        # POSSIBLE + contiguous=True → 원칙적으로 computed.
        # ★단, 용도지역 '혼재'(dominant 미확정/면적가중 동률 또는 zone_mix 2종+)면 'tentative'로 강등한다:
        #   시나리오 위임(auto_recommend_top3)은 통합면적만 입력받고 용도/한도는 '대표주소'로 재도출하므로,
        #   혼재 부지에서 단일 대표 용도 기준 수지를 confirmed처럼 보이면 신뢰를 과대표시한다(정직 위배).
        #   통합 blended 한도는 표시·검증용이며, 혼재는 용도지역별 분리 검토가 필요함을 정직 고지한다.
        zone_mix = integrated_zoning.get("zone_mix") or []
        is_mixed = (
            dominant_zone is None
            or integrated_zoning.get("dominant_basis") == "mixed_review_required"
            or len(zone_mix) >= 2
        )
        if is_mixed:
            scenario = {
                "status": "tentative",
                "disclosure": "용도지역이 혼재(2종 이상 또는 면적가중 동률)되어 통합 시나리오는 잠정치입니다 — "
                              "시나리오 수지는 대표 용도 기준이고 통합 한도(blended)는 표시·검증용입니다. "
                              "용도지역별 분리 검토를 권고합니다(확정 아님).",
            }
        else:
            scenario = {"status": "computed"}

    # computed·tentative(차단 아님)일 때만 시나리오 위임(auto_recommend_top3) 1회.
    if scenario.get("status") in ("computed", "tentative"):
        try:
            from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

            # 대표 주소·시군구: 첫 개발가능 필지 주소를 site 라벨로, 시군구는 _extract_sigungu.
            # ★위임(auto_recommend_top3)에는 '통합면적(total_area)'만 입력으로 반영된다. zone_type/한도는
            #   위임 내부에서 대표주소로 재도출되므로, 아래 dominant_zone·blended_*는 '표시·검증용'(위임 미주입)이며
            #   site.zone_basis='representative_parcel'로 실계산 기준이 대표필지임을 명시한다(표시값↔실계산 구분).
            rep_addr = next((p.get("address") for p in enriched if p.get("address")), "")
            region = _extract_sigungu({"address": rep_addr}) or "서울"
            site = {
                "total_area_sqm": total_area,
                "zone_type": dominant_zone,
                "far": integrated_zoning.get("blended_far_eff_pct"),
                "bcr": integrated_zoning.get("blended_bcr_eff_pct"),
                "zone_basis": "representative_parcel",  # 위임 수지는 대표 용도 기준(통합 blended는 표시·검증용)
            }
            kwargs: dict = {
                "address": rep_addr,
                "land_area_sqm": total_area,
                "region": region,
                "use_llm": req.use_llm,
            }
            if req.equity_won is not None:
                kwargs["equity_won"] = req.equity_won
            top3 = await FeasibilityServiceV2().auto_recommend_top3(**kwargs)
            # 신뢰블록 additive 부착(zone_type/zone_limits 보유 → 법령링크·근거 트레이스).
            if isinstance(top3, dict):
                _attach_trust_blocks(top3)
            scenario["site"] = site
            scenario["top3"] = top3
        except Exception as e:  # noqa: BLE001 — 위임 실패는 시나리오 degrade(정직), 통합집계는 유지.
            logger.warning("통합 시나리오 위임 실패: %s", str(e)[:160])
            scenario["status"] = "tentative" if scenario.get("status") == "computed" else scenario.get("status")
            scenario["disclosure"] = (scenario.get("disclosure") or "") + \
                " 시나리오 산정 위임에 실패해 통합 한도만 제공합니다(개발규모 미산정)."
            warnings.append("시나리오 산정(auto_recommend_top3) 위임 실패 — 통합 집계만 반환합니다.")

    # ── 7) 통합 종상향(upzoning) 1회 산출(additive·정직) — 통합 면적/필지수/인접성 주입.
    #     ★근본수정: 단일필지 경로는 calc_upzoning을 대표 1필지(작은 면적·parcel_count=1)로 호출해
    #     "면적 미달"로 종상향 가능성을 과소판정했다. 다필지에서는 통합 면적(total_area)·통합 필지수
    #     (parcel_count)·인접성(contiguous)을 주입해 통합 기준으로 가능성을 산정한다.
    #     무목업: 대표 용도지역이 미확정/혼재(dominant_zone None·mixed_review_required)면 단일 zone 종상향
    #     경로를 적용할 수 없으므로 산출하지 않는다(null + 정직고지). 결정론 산출만(수치 생성 X).
    upzoning: dict = {}
    upzoning_scenarios: list = []
    potential_far_range = None
    if (
        dominant_zone
        and dominant_zone != "mixed_review_required"
        and total_area
        and contiguous is not False  # 비인접(False)이면 통합개발 불가 → 통합 종상향 미적용
    ):
        try:
            from app.services.land_intelligence import far_tier_service

            # 시군구: 대표(첫 유효주소) 필지 주소로 도출(조례 용적률 resolver 입력).
            up_addr = next((p.get("address") for p in enriched if p.get("address")), "")
            up_sigungu = _extract_sigungu({"address": up_addr})
            # 통합 special_districts 집계(규제/특수구역 → 종상향 제약). 필지별 합집합(중복 제거).
            agg_sd: list = []
            for p in enriched:
                for sd in (p.get("special_districts") or []):
                    if sd not in agg_sd:
                        agg_sd.append(sd)
            # calc_upzoning은 base.local_ordinance.sigungu로 시군구를, base.special_districts로
            # 규제구역을 읽는다 → 통합값을 담은 경량 base를 구성해 주입(외부콜 0·결정론).
            up_base = {
                "local_ordinance": {"sigungu": up_sigungu} if up_sigungu else {},
                "special_districts": agg_sd,
            }
            upzoning = far_tier_service.calc_upzoning(
                up_base,
                dominant_zone,
                float(total_area),
                None,
                None,
                parcel_count=int(integrated_zoning.get("parcel_count") or len(enriched) or 1),
                adjacency_contiguous=contiguous,  # True/None(미확정) 그대로 전달(가짜 True 금지)
            )
            if isinstance(upzoning, dict):
                upzoning_scenarios = upzoning.get("scenarios", []) or []
                potential_far_range = upzoning.get("potential_far_range")
        except Exception as e:  # noqa: BLE001 — 종상향 산출 실패는 통합집계를 손상하지 않는다(정직 null).
            logger.warning("통합 종상향(upzoning) 산출 실패: %s", str(e)[:160])
            upzoning = {}
            upzoning_scenarios = []
            potential_far_range = None

    return {
        "parcel_count": integrated_zoning.get("parcel_count"),
        "special_count": multi.get("special_count"),
        "zone_mix": integrated_zoning.get("zone_mix"),
        "dominant_zone": dominant_zone,
        "dominant_basis": integrated_zoning.get("dominant_basis"),
        "integrated": {
            "total_area_sqm": total_area,
            "blended_bcr_eff_pct": integrated_zoning.get("blended_bcr_eff_pct"),
            "blended_far_eff_pct": integrated_zoning.get("blended_far_eff_pct"),
            "blended_bcr_legal_pct": integrated_zoning.get("blended_bcr_legal_pct"),
            "blended_far_legal_pct": integrated_zoning.get("blended_far_legal_pct"),
            "far_basis_note": integrated_zoning.get("far_basis_note"),
            "integrated_gfa_sqm": integrated_zoning.get("integrated_gfa_sqm"),
            "integrated_footprint_sqm": integrated_zoning.get("integrated_footprint_sqm"),
            "gfa_basis": integrated_zoning.get("gfa_basis"),
        },
        "adjacency": adjacency,
        "developability": developability,
        "resolvable": resolvable,
        "blocking_parcels": blocking_parcels,
        "honest_disclosure": honest_disclosure,
        "scenario": scenario,
        # ── 통합 종상향(upzoning) — 단일 /zoning/analyze 응답과 동형 키(additive). 미산출 시 null·빈배열(무목업).
        "upzoning": upzoning or None,
        "upzoning_scenarios": upzoning_scenarios,
        "potential_far_range": potential_far_range,
        "per_parcel": per_parcel,
        "warnings": warnings,
    }


class ParcelAtPointRequest(BaseModel):
    """지도 클릭 좌표 → 필지 조회(다필지 지도 클릭선택용)."""
    lat: float
    lon: float


@router.post("/parcel-at-point")
async def parcel_at_point(req: ParcelAtPointRequest):
    """지도에서 클릭한 좌표(lat/lon)가 속한 필지를 조회·보강(지번·면적·용도지역·건폐/용적·구획도).

    지도 클릭선택 입력 UX 지원. 무목업: 필지 미확인 시 found=false 정직 반환(가짜 생성 금지).
    """
    from apps.api.app.services.external_api.vworld_service import VWorldService
    from apps.api.app.services.zoning.auto_zoning_service import ZONE_LIMITS

    if not (-90 <= req.lat <= 90 and -180 <= req.lon <= 180):
        return {"found": False, "reason": "좌표 범위 오류."}
    vworld = VWorldService()
    try:
        pp = await vworld.get_parcel_by_point(req.lat, req.lon)
    except Exception as e:  # noqa: BLE001
        logger.warning("점→필지 조회 실패: %s,%s (%s)", req.lat, req.lon, str(e))
        pp = None
    if not pp or not pp.get("pnu"):
        return {"found": False, "reason": "클릭 지점에서 필지를 찾지 못했습니다(지적도 외 영역일 수 있음)."}
    pnu = str(pp["pnu"])
    from apps.api.app.services.external_api.building_registry_service import BuildingRegistryService

    area_sqm = zone_type = jimok = None
    official_price_per_sqm = None
    built_year = building_age_years = None
    # 토지특성(NED)과 건축물대장 표제부(건축HUB)는 독립 API → 병렬 조회(클릭 지연 최소화).
    # 각각 best-effort: 한쪽 실패해도 나머지 필드는 정상 반환(무자료·오류는 None, 무날조).
    lc, title = await asyncio.gather(
        vworld.get_land_characteristics(pnu),
        BuildingRegistryService().get_title_by_pnu(pnu),
        return_exceptions=True,
    )
    if isinstance(lc, dict):
        area_sqm = lc.get("area_sqm") or None
        zone_type = lc.get("zone_type") or None
        jimok = lc.get("land_category") or None
        # 개별공시지가(원/㎡) — get_land_characteristics가 이미 반환(추가 호출 0). 공시지가
        #   레이어(㎡당 단가)가 지도에 반영되려면 이 필드가 필요하다. 0/누락은 None(가짜값 금지).
        _op = lc.get("official_price_per_sqm")
        official_price_per_sqm = int(_op) if _op else None
    if isinstance(title, dict):
        # 노후도 레이어용 — 표제부 사용승인일(YYYYMMDD) 앞 4자리 = 준공연도 → 연식 산출.
        #   나대지/미준공(사용승인일 공란)·멸실·파싱불가는 None(정직 — 가짜 연식 금지).
        _uad = str(title.get("use_approval_date") or "").strip()
        if len(_uad) >= 4 and _uad[:4].isdigit() and not title.get("is_demolished"):
            from datetime import date as _date
            _y, _now = int(_uad[:4]), _date.today().year
            if 1900 <= _y <= _now:
                built_year = _y
                building_age_years = _now - _y
    bcr = far = None
    if zone_type:
        z = zone_type.replace(" ", "").strip()
        key = z if z in ZONE_LIMITS else max([k for k in ZONE_LIMITS if k in z] or [""], key=len) or None
        if key:
            bcr, far = ZONE_LIMITS[key]["max_bcr"], ZONE_LIMITS[key]["max_far"]
    return {
        "found": True, "pnu": pnu,
        "address": pp.get("address") or "", "jibun": pp.get("address") or "",
        "bcode": pnu[:10], "area_sqm": area_sqm, "zone_type": zone_type, "jimok": jimok,
        "bcr_pct": bcr, "far_pct": far, "geometry": pp.get("geometry"),
        "official_price_per_sqm": official_price_per_sqm,
        "built_year": built_year, "building_age_years": building_age_years,
        "lat": req.lat, "lon": req.lon,
    }


class DevelopmentFacilitiesRequest(BaseModel):
    """주변 개발계획(도시계획시설 — 철도·역사 등) 자동수집 요청."""
    lat: float
    lon: float
    radius_m: int = 1000


@router.post("/development-facilities")
async def development_facilities(req: DevelopmentFacilitiesRequest):
    """입지 좌표 주변의 도시계획시설(특히 철도·역사·도시철도 계획결정)을 best-effort로 자동수집.

    VWorld 공간정보로 반경 내 도시계획시설을 조회해 '주변 개발계획' 후보로 반환한다.
    무목업·정직표기: 데이터가 없으면 가짜 시설을 생성하지 않고 빈 배열 + note로 정직 고지한다.
    """
    from apps.api.app.services.external_api.vworld_service import VWorldService

    if not (-90 <= req.lat <= 90 and -180 <= req.lon <= 180):
        return {"facilities": [], "note": "좌표 범위 오류 — 위도(-90~90)/경도(-180~180)를 확인하세요."}
    radius_m = max(100, min(5000, req.radius_m or 1000))  # 1회 조회 부담 낮게(과도 반경 제한)
    try:
        facilities = await VWorldService().get_planning_facilities(req.lat, req.lon, radius_m=radius_m)
    except Exception as e:  # noqa: BLE001 — 외부 조회 실패는 정직 empty로(가짜 생성 금지).
        logger.warning("주변 도시계획시설 자동수집 실패: %s,%s (%s)", req.lat, req.lon, str(e))
        facilities = []
    if facilities:
        note = f"VWorld 도시계획시설 {len(facilities)}건(참고 — 확정 고시 여부는 별도 확인)"
    else:
        note = ("주변 도시계획시설(철도 등) 자동수집 결과 없음 — 계획 고시 전이거나 "
                "공간정보 미등재일 수 있습니다. 수동으로 개발계획을 입력하세요.")
    return {"facilities": facilities, "note": note}


class LandReportRequest(BaseModel):
    """토지분석보고서 PDF 생성 요청 — 토지조서 필지 목록."""
    project_name: str = "토지분석보고서"
    parcels: list[dict] = []  # [{address?, jibun?, pnu?, bcode?}]


@router.post("/land-report")
async def land_report(req: LandReportRequest, format: str = "pdf"):
    """다필지 → 종합 토지분석보고서(PDF/PPTX/DOCX·필지요약·토지정보·권리안내·규제/개발가능성·대지지분·종합).

    필지별 토지정보(/parcels-info 로직 재사용)+집합건물 세대 대지지분(land-share)을 모아 통합 보고서
    생성엔진으로 렌더(format 으로 포맷 선택). 무목업: 무자료는 '-'/'보완필요'로 정직 표기.
    """
    from fastapi.responses import StreamingResponse as _SR

    from app.services.report.render import build_report_model_from_land, render_report
    from apps.api.app.services.land_intelligence.land_share_service import LandShareService
    from apps.api.app.services.land_intelligence.parcel_excel_service import ParcelExcelService

    items = (req.parcels or [])[:120]
    if not items:
        return {"error": "필지가 없습니다."}

    enriched = await ParcelExcelService().enrich_parcel_list(items, with_building=True)
    # 실효 용적률/건폐율(조례 반영)+특이부지를 공용 헬퍼로 부착(parcels-info와 동일 의미).
    #   ★PDF가 bcr_pct/far_pct로 건축면적·연면적을 산출하므로 법정 과대표기 제거 위해 실효값 사용.
    await _enrich_effective_and_special(enriched)
    parcels = []
    units_by: dict[str, dict] = {}
    svc = LandShareService()
    for p in enriched:
        bcr, far = p.get("_bcr_eff"), p.get("_far_eff")  # 실효(조례 반영) — 법정상한 과대표기 제거
        bld = p.get("building") or None
        is_agg = bool(bld and bld.get("is_aggregate"))
        jb = p.get("jibun") or p.get("address") or ""
        parcels.append({
            "jibun": jb, "address": p.get("address"), "area_sqm": p.get("area_sqm"),
            "zone_type": p.get("zone_type"), "bcr_pct": bcr, "far_pct": far,
            "bcr_legal_pct": p.get("_bcr_legal"), "far_legal_pct": p.get("_far_legal"),
            "jimok": p.get("jimok"), "official_price_per_sqm": p.get("official_price_per_sqm"),
            "parcel_case": "aggregate" if is_agg else ("building" if bld else "land"),
            "building": bld, "status": p.get("status", "ok"), "reason": p.get("reason"),
        })
        # 집합건물은 세대 대지지분 상세 부착(전유부 전수).
        if is_agg and p.get("pnu"):
            try:
                ls = await svc.analyze_by_pnu(str(p["pnu"]))
                if ls.get("is_aggregate"):
                    units_by[jb] = {
                        "plat_area_sqm": ls.get("plat_area_sqm"), "unit_count": ls.get("unit_count"),
                        "units": ls.get("units") or [], "validation": ls.get("validation") or {},
                    }
            except Exception as e:  # noqa: BLE001
                logger.warning("보고서 대지지분 조회 실패: %s (%s)", jb, str(e))

    try:
        model = build_report_model_from_land(
            {"project_name": req.project_name, "parcels": parcels, "units_by_parcel": units_by})
        data, media_type, ext = render_report(model, format)
    except Exception as e:  # noqa: BLE001
        logger.warning("토지분석보고서 생성 실패: %s", str(e))
        return {"error": "보고서 생성에 실패했습니다."}
    return _SR(iter([data]), media_type=media_type,
               headers={"Content-Disposition": f'attachment; filename="land_analysis_report.{ext}"'})


@router.post("/parse-parcels")
async def parse_parcels(file: UploadFile = File(...)):
    """업로드된 토지조서 엑셀/CSV → 필지 목록(주소·PNU·bcode·면적·지목·소유구분) 추출.

    PNU 우선순위: PNU열 > 법정동코드+지번 구성 > 주소 지오코딩. 무자료/실패는 status로 정직 표기.
    표준 양식은 규칙기반 컬럼감지(LLM 미사용). ★비표준 양식이라 규칙기반이 필수컬럼을 못 찾을
    때만 LLM 에이전트가 컬럼을 1회 분류(헤더 시그니처 캐시로 재호출 방지). LLM 토큰은
    _record_llm_billing으로 계측·귀속(service=parcel_excel_column_detect). 과금 정책상 컬럼분류는
    저비용 보조기능으로 별도 차감 게이트 없음(관리자 미설정 시 무료 원칙).
    """
    from apps.api.app.services.land_intelligence.parcel_excel_service import (
        ParcelExcelService,
    )

    try:
        raw = await file.read()
    except Exception as e:  # noqa: BLE001
        return {"error": f"파일 읽기 실패: {str(e)[:120]}", "parcels": []}
    if not raw:
        return {"error": "빈 파일입니다.", "parcels": []}
    return await ParcelExcelService().parse(raw, file.filename or "upload.xlsx")
