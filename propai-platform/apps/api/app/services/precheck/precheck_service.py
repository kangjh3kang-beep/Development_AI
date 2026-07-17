"""Flagship A — 90초 AI PreCheck 로직 본체.

규칙기반 우선(90초 SLA). 외부 API 호출은 asyncio.wait_for로 가드, LLM은 선택적
1줄 요약만 사용한다. 라우터는 얇게 유지하고 모든 산정 로직을 이 모듈에 둔다.

재사용:
- app/services/zoning/auto_zoning_service.py: 주소→PNU→용도지역·면적(analyze_by_address),
  ZONE_LIMITS(법정 건폐/용적/높이 한도).
- app/services/feasibility/permit_validator.py: get_permitted_types/PERMIT_COMPLEXITY/
  DEVELOPMENT_TYPE_NAMES/check_permit_feasibility.
- app/services/external_api/vworld_service.py: geocode_address/get_parcels_in_bbox/
  get_land_characteristics(조닝 시그널 주변 필지).
- routers/auto_zoning.py: _parcel_adjacency(shapely 연결요소 인접성).
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from app.services.feasibility.permit_validator import (
    DEVELOPMENT_TYPE_NAMES,
    get_permit_complexity,
    get_permitted_types,
)
from app.services.zoning.auto_zoning_service import ZONE_LIMITS, AutoZoningService
from app.services.zoning.special_parcel import detect_special_parcel

# 외부 API 가드 타임아웃(90초 SLA 보장)
_ZONING_TIMEOUT = 30.0
_BBOX_TIMEOUT = 25.0
_LLM_TIMEOUT = 25.0
# 조례 실효값 조회(법제처 API/캐시) 가드 — 실패 시 법정상한 폴백.
_ORDINANCE_TIMEOUT = 8.0

# 모든 후보 개발방식 코드(M01~M15)
_ALL_METHODS = [f"M{n:02d}" for n in range(1, 16)]


def _normalize_zone(zone_type: str) -> str:
    """용도지역명 → ZONE_LIMITS/ZONE_PERMIT_MATRIX 표준 키."""
    key = (zone_type or "").replace(" ", "").strip()
    if key in ZONE_LIMITS:
        return key
    for k in ZONE_LIMITS:
        if k in key or key in k:
            return k
    return key


async def _legal_limits(
    zone_type: str | None, address: str | None = None, pnu: str | None = None,
) -> dict[str, Any]:
    """용도지역 → 법정 건폐율/용적률/높이 한도(국토계획법 제78조) + 실효값(SSOT, 가산).

    기존 반환 키(bcr_pct/far_pct/height_m/source)는 전부 보존한다(_area_checks·프론트 무영향).
    address가 주어지면 OrdinanceService로 조례 실효값을 조회해 applicable_limits_for로
    계층 적용 한도(법정범위→조례→도시군관리계획)를 산정하고, 다음 키를 **가산**한다:
      applied_bcr_pct / applied_far_pct / ordinance_confirmed / far_source /
      sigungu / legal_ref_keys(법령 원문링크 근거키 목록).
    조례 조회 실패·미확인 시 법정상한으로 폴백(현행 동작과 동일값), ordinance_confirmed=False.

    ★실효 용적률 SSOT 단일화(WP-U1b): 최종 적용값(applied_far_pct/applied_bcr_pct)은
    far_tier_service.calc_effective_far(법정범위→조례→계획상한→인센티브→**구조상한**)를
    단일경유해 산정한다 — 재계산 금지·소비만. 과거 이 경로는 applicable_limits_for
    (법정→조례 min)까지만 적용하고 구조상한(건폐율×층수)을 누락해 자연녹지(건폐 20%×4층
    =80% < 법정 100%)를 100%로 과대표시했다(90초진단 과대낙관 — "2026-06-19 산/임야
    과대표시" 버그클래스). 수지(feasibility_v2:302)·종합(comprehensive:427)·규제(PR#333)·
    인허가(PR#334) 표면과 교차 일치. 가산 키:
      far_basis(실효 산정근거) / far_reliable(SSOT 산정 성공 여부) /
      structural_cap_pct / floor_cap / floor_cap_basis.
    SSOT 산정 실패 시 applicable_limits_for 값 유지 + far_reliable=False(정직강등 —
    침묵 폴백으로 과대값이 '실효'로 승격되지 않게 신뢰도 신호를 함께 내린다).
    """
    if not zone_type:
        return {"bcr_pct": None, "far_pct": None, "height_m": None, "source": "미확인",
                "legal_ref_keys": [], "far_basis": None, "far_reliable": False}
    key = _normalize_zone(zone_type)
    limits = ZONE_LIMITS.get(key)
    if not limits:
        return {"bcr_pct": None, "far_pct": None, "height_m": None, "source": "법정한도 미매핑",
                "legal_ref_keys": [], "far_basis": None, "far_reliable": False}

    legal: dict[str, Any] = {
        "bcr_pct": limits.get("max_bcr"),
        "far_pct": limits.get("max_far"),
        "height_m": limits.get("max_height_m"),
        "source": "국토의 계획 및 이용에 관한 법률 제78조",
        "zone_type": key,
    }

    # ── 조례 실효값 적용(가산) — applicable_limits_for 경유(새 산식 0) ──
    # 법령 한도 근거키는 항상 부착(zone 매칭 시), 조례 적용은 확인된 경우에만 표기.
    ref_keys: list[str] = ["far_limit", "bcr_limit"]
    sigungu = await _extract_sigungu_from_address(address, pnu)
    legal["sigungu"] = sigungu
    legal["ordinance_confirmed"] = False
    legal["applied_bcr_pct"] = legal["bcr_pct"]
    legal["applied_far_pct"] = legal["far_pct"]
    legal["far_source"] = "법정상한 적용(조례 확인 필요)"

    regulation_payload: Any = None
    if address:
        try:
            from app.services.land_intelligence.ordinance_service import OrdinanceService

            ord_result = await asyncio.wait_for(
                # resolved_sigungu: 위에서 이미 해석한 값 하향 전달 — 동일주소 중복 지오코딩 방지.
                OrdinanceService().get_ordinance_limits(
                    address, zone_type, pnu=pnu, resolved_sigungu=sigungu,
                ),
                timeout=_ORDINANCE_TIMEOUT,
            )
            regulation_payload = ord_result
        except Exception:  # noqa: BLE001 — 조례 조회 실패 시 법정상한 폴백(SLA 보호)
            regulation_payload = None

    try:
        from app.services.zoning.legal_zone_limits import applicable_limits_for

        applied = applicable_limits_for(
            zone_type, sigungu=sigungu, regulation_payload=regulation_payload
        )
    except Exception:  # noqa: BLE001
        applied = None

    if applied:
        if applied.get("applied_bcr_pct") is not None:
            legal["applied_bcr_pct"] = applied["applied_bcr_pct"]
        if applied.get("applied_far_pct") is not None:
            legal["applied_far_pct"] = applied["applied_far_pct"]
        legal["ordinance_confirmed"] = bool(applied.get("ordinance_confirmed"))
        legal["far_source"] = applied.get("far_source") or legal["far_source"]
        if applied.get("ordinance_far_pct") is not None:
            legal["ordinance_far_pct"] = applied["ordinance_far_pct"]
        if applied.get("ordinance_bcr_pct") is not None:
            legal["ordinance_bcr_pct"] = applied["ordinance_bcr_pct"]
        # 조례가 실제로 확인되면 조례 근거키를 가산(가짜 조례링크 방지).
        if legal["ordinance_confirmed"]:
            # 조례 결과의 sigungu(권위적)를 우선 사용해 조례 url 치환 정확도를 높인다.
            if isinstance(regulation_payload, dict):
                rp_sgg = regulation_payload.get("sigungu")
                if rp_sgg and str(rp_sgg).strip() and str(rp_sgg).strip() != "미확인":
                    legal["sigungu"] = str(rp_sgg).strip()
            for ok in ("ordinance_far", "ordinance_bcr"):
                if ok not in ref_keys:
                    ref_keys.append(ok)

    # ── ★실효 용적률 SSOT 단일경유(WP-U1b) — calc_effective_far(구조상한 포함) 소비 ──
    # 위 applicable_limits_for는 법정→조례→계획 계층만 산정하고 구조상한(건폐율×층수)을
    # 모른다. 최종 적용값은 SSOT가 min(…, 구조상한)까지 확정한 값을 그대로 소비한다.
    # 층수제한 없는 zone(제2종일반주거 250%·일반상업 1300% 등)은 structural_cap=None으로
    # 완전 무영향(값 불변). 산정 실패 시 위 값 유지 + far_reliable=False(정직강등).
    legal["far_basis"] = None
    legal["far_reliable"] = False
    legal["structural_cap_pct"] = None
    legal["floor_cap"] = None
    legal["floor_cap_basis"] = None
    try:
        from app.services.land_intelligence.far_tier_service import calc_effective_far

        eff = calc_effective_far(
            {
                # 법정한도는 SSOT가 용도지역 라벨(legal_limits_for)로 재확인한다 — 여기 값은 보조.
                "zone_limits": {"max_bcr_pct": legal["bcr_pct"], "max_far_pct": legal["far_pct"]},
                # OrdinanceService 결과(flat)를 local_ordinance로 주입 — PR#334와 동일 패턴.
                "local_ordinance": regulation_payload if isinstance(regulation_payload, dict) else {},
                # precheck는 plan payload(지구단위계획 상한) 미수집 — 빈 리스트(기존과 동일,
                # 계획상한은 상향 계층이므로 미반영은 보수적/정직 방향. 과대낙관 없음).
                "special_districts": [],
            },
            key,
            0,
        )
        _eff_far = eff.get("effective_far_pct")
        if _eff_far is not None and float(_eff_far) > 0:
            legal["applied_far_pct"] = float(_eff_far)  # 실효(구조상한 포함) — 재계산 금지·소비만
            legal["far_reliable"] = True
        _eff_bcr = eff.get("effective_bcr_pct")
        if _eff_bcr is not None and float(_eff_bcr) > 0:
            legal["applied_bcr_pct"] = float(_eff_bcr)
        legal["far_basis"] = eff.get("far_basis")
        legal["structural_cap_pct"] = eff.get("structural_cap_pct")
        legal["floor_cap"] = eff.get("floor_cap")
        legal["floor_cap_basis"] = eff.get("floor_cap_basis")
        # 구조상한이 최종 바인딩되면 far_source도 정직 갱신 — "법정상한 적용" 문구가 80% 값과
        # 모순되지 않게(수치-서술 불일치 방지). 조례 확인 필요 여부는 기존 문구를 보존해 이어붙인다.
        if legal["far_basis"] == "구조상한(건폐율×층수)":
            _suffix = "" if legal.get("ordinance_confirmed") else " · 조례 확인 필요"
            legal["far_source"] = (
                f"구조상한(건폐율×{legal['floor_cap']}층) 적용{_suffix}"
            )
    except Exception:  # noqa: BLE001 — SSOT 실패 시 법정/조례 값 유지(far_reliable=False 정직강등)
        pass

    legal["legal_ref_keys"] = ref_keys
    return legal


async def _extract_sigungu_from_address(
    address: str | None, pnu: str | None = None,
) -> str | None:
    """주소 문자열에서 시군구명을 정직 추출(조례 url 치환용 + 조례 캐시 매칭 키).

    (a) 정규식 우선(기존 동작 무변경) — 특별시/광역시(시군구 아님)는 건너뛰고 첫 시군구
    토큰을 반환한다. 모든 후보를 순회(finditer)하므로 '서울특별시 강남구 …'에서 '강남구'를
    정확히 잡는다.
    (b) 정규식 실패 시 PNU 폴백 — '의정부동 224'처럼 시/군/구 토큰 자체가 없는 동 단위
    주소는 (a)가 항상 None이 되어 정적 조례캐시(ORDINANCE_CACHE)에 이미 있는 정답을 못 찾고
    법정상한으로 과대 폴백한다(2026-07-17 조례 미반영 근본원인). ordinance_service의 공용
    헬퍼(resolve_region_via_pnu_fallback — VWorld 재지오코딩 refined.structure 재사용,
    코드→명칭 표 새로 발명 없음)로 폴백한다.
    (c) 그래도 실패 시 기존 동작(None → 레지스트리에 sigungu 미전달, 조례 url_status='pending').
    """
    addr = str(address or "")
    if not addr:
        return None
    for m in re.finditer(r"(\S{2,4}[시군구])(?:\s|$)", addr):
        cand = m.group(1)
        if "특별" not in cand and "광역" not in cand:
            return cand
    try:
        from app.services.land_intelligence.ordinance_service import (
            resolve_region_via_pnu_fallback,
        )
        fb = await resolve_region_via_pnu_fallback(addr, pnu)
        return fb.get("sigungu")
    except Exception:  # noqa: BLE001 — 폴백 실패는 기존 동작(None) 보존
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 신뢰 레이어(additive) 조립 헬퍼 — inputs/data_quality/legal_refs/evidence/feasibility_band
# 원칙: 새 계산/조닝/검증 엔진 0개. 기존 함수 rewire + 데이터 매핑만. URL은 레지스트리만.
# 모든 헬퍼는 graceful(예외 시 안전 폴백) — 기존 응답을 절대 깨지 않는다.
# ─────────────────────────────────────────────────────────────────────────────
def _prov(value, source: str, method: str, confidence: str, **extra) -> dict:
    """필드 provenance 1건 — value/source/method/confidence (+선택 메타)."""
    rec = {"value": value, "source": source, "method": method, "confidence": confidence}
    rec.update(extra)
    return rec


def _build_inputs(
    *,
    zone_type: str | None,
    resolved_pnu: str | None,
    resolved_area: float | None,
    official_price: float | None = None,
) -> dict[str, Any]:
    """필드별 provenance(zone_type/area_sqm/official_price/pnu) — auto_zoning과 동일 패턴.

    - pnu 존재 → 외부 권위 출처에서 자동수집(auto, high). (이 함수 도달 시 pnu 확인됨이 정상)
    - pnu 부재 → zone_type은 주소키워드 추론 폴백(estimated/low).
    - 값이 없으면 confidence='none'(있는 그대로 표기, 목업 금지). method ∈
      {auto(공공API)|estimated(테이블/추론)|user(사용자입력)|fallback}.
    """
    has_pnu = bool(resolved_pnu)

    if not zone_type:
        zone_prov = _prov(None, "미수집", "fallback", "none")
    elif has_pnu:
        zone_prov = _prov(zone_type, "vworld_land_characteristics(NED)", "auto", "high")
    else:
        zone_prov = _prov(zone_type, "추론(주소 키워드)", "estimated", "low")

    if not resolved_area:
        area_prov = _prov(None, "미수집", "fallback", "none")
    elif has_pnu:
        area_prov = _prov(resolved_area, "vworld_land_characteristics(NED)", "auto", "high")
    else:
        area_prov = _prov(resolved_area, "사용자입력", "user", "medium")

    if not official_price:
        price_prov = _prov(None, "미수집", "fallback", "none")
    else:
        price_prov = _prov(official_price, "vworld_individual_land_price", "auto", "high")

    if not has_pnu:
        pnu_prov = _prov(None, "미수집", "fallback", "none")
    else:
        pnu_prov = _prov(resolved_pnu, "vworld_geocode(PARCEL)", "auto", "high")

    return {
        "zone_type": zone_prov,
        "area_sqm": area_prov,
        "official_price": price_prov,
        "pnu": pnu_prov,
    }


def _build_legal_refs(legal: dict[str, Any]) -> list[dict]:
    """_legal_limits의 legal_ref_keys를 레지스트리(get_legal_refs)로 직렬화(additive).

    - zone_type 미확정/미매칭 → legal_ref_keys 빈 리스트 → 빈 배열(할루시네이션 링크 금지).
    - 조례 확인 시 ordinance_far/bcr 키 포함(=_legal_limits가 부착) + sigungu 치환.
    - URL은 전적으로 get_legal_refs 출력만 사용한다(여기서 URL 조립 금지).
    """
    keys = legal.get("legal_ref_keys") or []
    if not keys:
        return []
    sigungu = legal.get("sigungu")
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs(keys, sigungu=sigungu)
    except Exception:  # noqa: BLE001
        return []


def _build_data_quality(
    *,
    used_sources: list[str],
    quantitative_reliable: bool,
    ordinance_confirmed: bool = False,
) -> dict[str, Any]:
    """데이터 품질·할루시네이션 검증 메타(G2) — CalculationMetadata + PublicDataRegistry 조립.

    - confidence_level: CalculationMetadata가 하드코딩 소스 사용 시 자동 강등(high→medium).
    - quantitative_reliable: 기존 pnu 차단 분기(:194)와 동일 조건(중복 로직 0).
    - sources_meta/warnings/disclaimer: 레지스트리·메타에서 조회. 과하지 않게 핵심 소스만.
    """
    try:
        from app.services.data_validation.calculation_metadata import CalculationMetadata
        from app.services.data_validation.public_data_registry import PublicDataRegistry

        meta = CalculationMetadata("precheck")
        # 정량 진단에 실제 기여한 핵심 소스(자동수집 1 + 하드코딩 한도 1).
        meta.add_source("vworld_zoning", "공공API", is_live=True)
        meta.add_source("zone_bcr_far_limits", "하드코딩", is_live=False)  # 자동 경고+강등
        if ordinance_confirmed:
            meta.add_source("local_ordinance", "공공API", is_live=True)

        registry = PublicDataRegistry.get_instance()
        # sources_meta: 사용 소스의 타입·실시간 여부(간이 표기).
        sources_meta: list[dict] = []
        for name in ("vworld_zoning", "zone_bcr_far_limits"):
            st = registry.get_status(name)
            if st is not None:
                sources_meta.append({
                    "name": st.name,
                    "type": "하드코딩" if st.source_type == "hardcoded" else "공공API",
                    "is_live": st.source_type != "hardcoded",
                    "update_frequency": st.update_frequency,
                })

        confidence = meta.confidence_level
        # 정량 신뢰불가(pnu 미확인)면 보수적으로 low.
        if not quantitative_reliable:
            confidence = "low"

        warnings = list(meta.warnings)
        if not quantitative_reliable:
            warnings.append(
                "필지(PNU)가 확인되지 않아 정량 진단을 신뢰할 수 없습니다(참고용)."
            )

        return {
            "confidence_level": confidence,
            "quantitative_reliable": quantitative_reliable,
            "warnings": warnings,
            "sources_meta": sources_meta,
            "disclaimer": "본 진단은 참고용이며, 실제 의사결정 시 전문가 확인을 권장합니다.",
        }
    except Exception:  # noqa: BLE001 — 검증 모듈 실패 시 간이 표기로 폴백(graceful).
        return {
            "confidence_level": "medium" if quantitative_reliable else "low",
            "quantitative_reliable": quantitative_reliable,
            "warnings": (
                [] if quantitative_reliable
                else ["필지(PNU) 미확인 — 정량 진단 신뢰 불가(참고용)."]
            ),
            "sources_meta": [],
            "disclaimer": "본 진단은 참고용이며, 실제 의사결정 시 전문가 확인을 권장합니다.",
        }


def _fmt_pct(v) -> str | None:
    """퍼센트 표기 — 250 → '250%'. None/빈값 → None."""
    if v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return f"{int(n)}%" if n == int(n) else f"{n:g}%"


def _build_evidence(
    *,
    legal: dict[str, Any],
    area_checks: list[dict[str, str]],
    legal_refs: list[dict],
    area_sqm: float | None,
    feasibility_band: dict | None = None,
) -> list[dict]:
    """한도·면적 산출 트레이스(EvidencePanel 소비 구조).

    {id, target, inputs[], formula, result, legal_ref_keys[]}. zone_type 미확정(법정한도
    미매핑) 시 빈 배열. 조례 실효값이 법정과 다르면 적용값 트레이스를 추가한다.
    """
    far_legal = legal.get("far_pct")
    bcr_legal = legal.get("bcr_pct")
    if far_legal is None and bcr_legal is None:
        return []

    ref_keys = legal.get("legal_ref_keys") or []
    applied_far = legal.get("applied_far_pct")
    sigungu = legal.get("sigungu") or "지자체"
    ordinance_confirmed = bool(legal.get("ordinance_confirmed"))

    evidence: list[dict] = []

    # (1) 적용 용적률 트레이스 — SSOT(calc_effective_far) 산정값 소비.
    #     min() 인자에 실제 바인딩 후보(법정·조례·구조상한)를 정직 나열한다. 과거엔
    #     min(법정,조례)만 표기해 구조상한(건폐율×층수)으로 낮아진 값을 설명하지 못했다.
    far_legal_fmt = _fmt_pct(far_legal)
    applied_far_fmt = _fmt_pct(applied_far)
    structural_cap_fmt = _fmt_pct(legal.get("structural_cap_pct"))
    structurally_bound = (
        legal.get("far_basis") == "구조상한(건폐율×층수)" and structural_cap_fmt is not None
    )
    if far_legal_fmt:
        bound_parts = [f"법정상한 {far_legal_fmt}"]
        if ordinance_confirmed and legal.get("ordinance_far_pct") is not None:
            bound_parts.append(f"{sigungu} 조례 {_fmt_pct(legal.get('ordinance_far_pct'))}")
        if structurally_bound:
            bound_parts.append(
                f"구조상한 {structural_cap_fmt}"
                f"(건폐율 {_fmt_pct(legal.get('applied_bcr_pct'))}×{legal.get('floor_cap')}층)"
            )
        if applied_far_fmt and applied_far_fmt != far_legal_fmt and len(bound_parts) > 1:
            formula = f"적용 용적률 = min({', '.join(bound_parts)})"
            result = applied_far_fmt
            keys = [k for k in ref_keys if k in ("far_limit", "ordinance_far")]
        else:
            formula = f"법정 용적률 상한 = {far_legal_fmt}"
            result = far_legal_fmt
            keys = [k for k in ref_keys if k == "far_limit"]
        far_inputs = [f"zone_type={legal.get('zone_type') or ''}".rstrip("=")]
        if ordinance_confirmed:
            far_inputs.append(f"sigungu={sigungu}")
        evidence.append({
            "id": "ev_far",
            "target": "legal_limits.far_pct",
            "inputs": far_inputs,
            "formula": formula,
            "result": result,
            "legal_ref_keys": keys,
        })

    # (2) 건폐율 트레이스.
    bcr_legal_fmt = _fmt_pct(bcr_legal)
    if bcr_legal_fmt:
        evidence.append({
            "id": "ev_bcr",
            "target": "legal_limits.bcr_pct",
            "inputs": [f"sigungu={sigungu}"],
            "formula": f"법정 건폐율 상한 = {bcr_legal_fmt}",
            "result": bcr_legal_fmt,
            "legal_ref_keys": [k for k in ref_keys if k == "bcr_limit"],
        })

    # (3) 가용 연면적 트레이스(면적 확정 시).
    if area_sqm and applied_far is not None:
        try:
            gfa = round(float(area_sqm) * float(applied_far) / 100.0)
            evidence.append({
                "id": "ev_buildable",
                "target": "methods[].checks.용적률",
                "inputs": [f"area_sqm={area_sqm:g}", f"applied_far={_fmt_pct(applied_far)}"],
                "formula": f"연면적 = 대지면적 × 적용용적률 = {area_sqm:g} × {float(applied_far) / 100:g}",
                "result": f"{gfa:,}㎡",
                "legal_ref_keys": [k for k in ref_keys if k in ("far_limit", "ordinance_far")],
            })
        except (TypeError, ValueError):
            pass

    # (4) 수지 밴드 트레이스(feasibility_band 산출 시).
    if feasibility_band and feasibility_band.get("scenarios", {}).get("base"):
        base = feasibility_band["scenarios"]["base"]
        evidence.append({
            "id": "ev_feasibility",
            "target": "feasibility_band.base",
            "inputs": [
                f"method={feasibility_band.get('method_code')}",
                f"npv={base.get('npv_won')}",
            ],
            "formula": "aggregate_feasibility(revenue - (land+construction+finance+other+tax))",
            "result": (
                f"NPV {base.get('npv_won')}원 / 이익률 {base.get('profit_rate_pct')}% / "
                f"{base.get('grade')}등급"
            ),
            "legal_ref_keys": [],
        })

    return evidence


def _area_checks(area_sqm: float | None, legal: dict[str, Any]) -> list[dict[str, str]]:
    """면적 기반 건폐율/용적률 개략 검토 체크.

    면적이 있으면 법정한도 존재 여부로 정보성 pass, 없으면 warn("면적 미입력").
    실제 배치설계 전이므로 정량 위반은 단정하지 않고 한도값을 안내한다.

    ★최대 건축면적/연면적은 **적용(실효) 한도**(applied_*, SSOT calc_effective_far 소비값)로
    산정한다 — 과거엔 법정상한으로 계산해 자연녹지(실효 80%)의 최대 연면적을 법정 100%
    기준으로 25% 과대 안내했다(동일 버그클래스 파일 내 스윕). 실효가 법정과 다르면
    산정근거(far_basis)와 법정상한을 함께 정직 표기한다.
    """
    checks: list[dict[str, str]] = []
    bcr_legal = legal.get("bcr_pct")
    far_legal = legal.get("far_pct")
    bcr = legal.get("applied_bcr_pct") if legal.get("applied_bcr_pct") is not None else bcr_legal
    far = legal.get("applied_far_pct") if legal.get("applied_far_pct") is not None else far_legal
    height = legal.get("height_m")

    if area_sqm:
        if bcr is not None:
            buildable = round(area_sqm * bcr / 100.0)
            checks.append({
                "rule": "건폐율",
                "status": "pass",
                "detail": f"적용 건폐율 {bcr:g}% → 1층 최대 건축면적 약 {buildable:,}㎡",
            })
        else:
            checks.append({"rule": "건폐율", "status": "warn", "detail": "법정 건폐율 한도 미매핑"})
        if far is not None:
            gfa = round(area_sqm * far / 100.0)
            far_note = ""
            if far_legal is not None and float(far) != float(far_legal):
                far_note = (
                    f" ({legal.get('far_basis') or '조례/구조상한'} 반영 — 법정상한 {far_legal:g}%)"
                )
            checks.append({
                "rule": "용적률",
                "status": "pass",
                "detail": f"적용 용적률 {far:g}% → 연면적 최대 약 {gfa:,}㎡{far_note}",
            })
        else:
            checks.append({"rule": "용적률", "status": "warn", "detail": "법정 용적률 한도 미매핑"})
    else:
        checks.append({"rule": "건폐율", "status": "warn", "detail": "면적 미입력 — 정량 검토 보류"})
        checks.append({"rule": "용적률", "status": "warn", "detail": "면적 미입력 — 정량 검토 보류"})

    # 높이: 한도 있으면 정보성, 없으면(주거 일조사선 등) warn
    if height is not None:
        checks.append({"rule": "높이", "status": "pass", "detail": f"법정 높이 한도 {height}m"})
    else:
        checks.append({"rule": "높이", "status": "warn", "detail": "절대 높이 한도 없음 — 일조·사선 별도 검토"})

    return checks


def _build_method(code: str, zone_type: str, permitted_codes: list[str],
                  area_checks: list[dict[str, str]]) -> dict[str, Any]:
    """단일 개발방식의 신호등 카드 구성."""
    name = DEVELOPMENT_TYPE_NAMES.get(code, code)
    permitted = code in permitted_codes
    complexity = get_permit_complexity(code)
    complexity_label = ["", "매우쉬움", "쉬움", "보통", "어려움", "매우어려움"][complexity]

    checks: list[dict[str, str]] = []
    # 용도지역 허용 체크(1순위)
    checks.append({
        "rule": "용도지역 허용",
        "status": "pass" if permitted else "fail",
        "detail": f"{zone_type}에서 {name} {'허용' if permitted else '불허'}",
    })

    if not permitted:
        # 불허면 정량 검토 불필요 — fail 단정
        return {
            "code": code, "name": name, "signal": "fail",
            "permitted": False, "complexity": complexity, "complexity_label": complexity_label,
            "checks": checks,
            "reason": f"{zone_type}에서 {name}은(는) 인허가 불가",
        }

    # 허용된 경우 정량(면적) 체크 결합
    checks.extend(area_checks)
    # 주차·일조는 배치설계 전이라 정보성 warn(데이터 없음)
    checks.append({"rule": "주차", "status": "warn", "detail": "주차대수는 세대수·연면적 확정 후 산정"})
    checks.append({"rule": "일조", "status": "warn", "detail": "정북 일조·인동간격은 배치설계 단계 검토"})

    # signal: 허용+복잡도≤3→pass / 허용+복잡도4~5(심의)→warn
    signal = "pass" if complexity <= 3 else "warn"
    if signal == "pass":
        reason = f"{name} 허용 · 인허가 복잡도 {complexity_label}(원활)"
    else:
        reason = f"{name} 허용 · 복잡도 {complexity_label} — 심의/조합 등 절차 부담"

    return {
        "code": code, "name": name, "signal": signal,
        "permitted": True, "complexity": complexity, "complexity_label": complexity_label,
        "checks": checks,
        "reason": reason,
    }


async def run_instant_precheck(
    address: str,
    pnu: str | None = None,
    area_sqm: float | None = None,
    use_llm: bool = False,
) -> dict[str, Any]:
    """즉시 룰체크(계약 A). 90초 SLA — 외부 호출 1회(+선택 LLM 1회)."""
    t0 = time.perf_counter()
    sources: list[str] = ["permit_validator", "ZONE_LIMITS(국토계획법 제78조)"]

    # ── 1) 주소→용도지역·면적(외부 1회, wait_for 가드) ──
    zone_type: str | None = None
    resolved_pnu = pnu
    resolved_area = area_sqm
    # 특이부지 감지 입력(지목·구역) — analyze_by_address가 함께 채워주므로 재호출 0건.
    land_category: str | None = None
    special_districts: list = []
    # 공시지가(개별공시지가, 원/㎡) — 수지 밴드의 토지비 산정 근거. 없으면 밴드는 생략(과대 ROI 방지).
    official_price: float | None = None
    try:
        zoning = await asyncio.wait_for(
            AutoZoningService().analyze_by_address(address), timeout=_ZONING_TIMEOUT
        )
        zone_type = zoning.get("zone_type")
        resolved_pnu = resolved_pnu or zoning.get("pnu")
        if resolved_area is None:
            resolved_area = zoning.get("land_area_sqm")
        land_category = zoning.get("land_category")
        special_districts = zoning.get("special_districts") or []
        official_price = zoning.get("official_price_per_sqm")
        sources.append("auto_zoning_service")
    except TimeoutError:
        sources.append("auto_zoning_service(timeout)")
    except Exception:  # noqa: BLE001
        sources.append("auto_zoning_service(error)")

    if not zone_type:
        # 빈 결과 금지 — ok:false + message
        return {
            "ok": False,
            "message": "용도지역을 확인할 수 없습니다. 주소를 정확히 입력하거나 PNU를 함께 제공해 주세요.",
            "address": address,
            "pnu": resolved_pnu,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "sources": sources,
        }

    # PNU 미확인(지오코딩 실패) 시 용도지역은 주소 키워드 추론 기본값이라 정량 진단을 신뢰할 수 없음.
    # 할루시네이션 방지: 실제 필지가 확인되지 않으면 차단(빈 결과 금지 원칙과 동일선상).
    if not resolved_pnu:
        return {
            "ok": False,
            "message": "입력하신 주소를 실제 필지(PNU)로 확인하지 못했습니다. 정확한 지번 주소를 입력하거나 PNU를 함께 제공해 주세요. (필지 미확인 상태에서는 정량 진단을 제공하지 않습니다.)",
            "address": address,
            "pnu": None,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "sources": sources,
        }

    # ── 2) 법정 한도(실효값 SSOT 가산) + 후보 개발방식 ──
    legal = await _legal_limits(zone_type, address, pnu=resolved_pnu)
    permitted_codes = get_permitted_types(zone_type)
    area_checks = _area_checks(resolved_area, legal)

    # ── ★A-3/G8 법정초과 경량 가드 확산 — comprehensive analyze()의 P0-3 패턴을 공용
    #   헬퍼(hotpath_guard)로 실효율 카드(legal_limits.applied_*_pct)에도 적용(additive).
    #   regulation_payload: legal이 이미 ordinance_confirmed(실제 조례 취득 여부)를 판정해뒀으므로
    #   그 신호를 재사용한다(허위 조례 생성 아님·산식복제 0).
    from app.services.verification.hotpath_guard import apply_legal_hotpath_guard

    _guard_reg_payload = (
        {"local_ordinance": {"source": "조례",
                              "effective_far": legal.get("ordinance_far_pct"),
                              "effective_bcr": legal.get("ordinance_bcr_pct")}}
        if legal.get("ordinance_confirmed") else None
    )
    integrity_warnings = apply_legal_hotpath_guard(
        {},  # 응답 splice는 return dict에서 직접 처리 — 이 dict는 헬퍼 계약 충족용(미사용)
        zone_type=zone_type, bcr_pct=legal.get("applied_bcr_pct"), far_pct=legal.get("applied_far_pct"),
        regulation_payload=_guard_reg_payload,
        confidence_target=legal,
    )

    # 후보군: 허용된 코드 우선, 불허는 제외(계약은 "해당 용도지역 후보").
    # 단 전부 불허(녹지 등)면 대표 후보 일부를 fail로 보여 변별.
    candidates = permitted_codes if permitted_codes else ["M06", "M08", "M10", "M13"]
    methods = [
        _build_method(code, zone_type, permitted_codes, area_checks)
        for code in candidates
    ]
    # 복잡도 오름차순(쉬운 것 먼저) → pass가 상단
    methods.sort(key=lambda m: (m["signal"] != "pass", m["complexity"]))

    # ── 2-B) 특이부지 게이트(가산) — 지목/용도지역/구역 기반 비일상 토지 감지 ──
    # 산지·학교용지·GB·맹지 등은 용도지역 신호등만으로 개발가능을 단정하면 할루시네이션이다.
    # detect_special_parcel(규칙기반)로 개발가능성 게이트를 산정해 신호등에 경고/차단을 반영하고,
    # 결과(developability·factors·warning)를 응답에 가산한다(기존 필드 불변).
    # road_contact/road_width_m는 precheck 단계에서 미수집 → 미전달(None)로 맹지 오탐 방지.
    special_parcel = detect_special_parcel({
        "zone_type": zone_type,
        "land_category": land_category,
        "special_districts": special_districts,
    })

    # ── 3) 요약 ──
    n_pass = sum(1 for m in methods if m["signal"] == "pass")
    n_warn = sum(1 for m in methods if m["signal"] == "warn")
    n_fail = sum(1 for m in methods if m["signal"] == "fail")
    best = methods[0]["code"] if methods and methods[0]["signal"] != "fail" else None

    summary: dict[str, Any] = {
        "pass": n_pass, "warn": n_warn, "fail": n_fail, "best": best, "llm_note": None,
    }

    # 특이부지면 신호등에 경고/차단을 반영 — BLOCKED/해결불가(NO)는 best 추천을 거두고
    # 전 후보를 warn 이하로 강등(과대 추천 차단), 그 외 특이는 경고 동반(best 유지).
    if special_parcel:
        gate = special_parcel.get("developability")
        resolvable = special_parcel.get("resolvable")
        blocking = gate == "BLOCKED" or resolvable == "NO"
        for m in methods:
            if blocking:
                # 원칙적 개발 불가 — pass/warn을 warn으로 강등, 사유에 게이트 명시.
                if m["signal"] == "pass":
                    m["signal"] = "warn"
                m["special_parcel_caveat"] = special_parcel.get("severity_label")
        if blocking:
            best = None
            n_pass = sum(1 for m in methods if m["signal"] == "pass")
            n_warn = sum(1 for m in methods if m["signal"] == "warn")
            n_fail = sum(1 for m in methods if m["signal"] == "fail")
            summary.update({"pass": n_pass, "warn": n_warn, "fail": n_fail, "best": best})
        summary["special_parcel_warning"] = special_parcel.get("honest_disclosure")
        summary["developability"] = gate

    # ── 5) 신뢰 레이어(additive) — inputs/data_quality/legal_refs/evidence/feasibility_band ──
    # 전부 가산 필드. 조립 실패해도 기존 응답은 무손상(graceful).
    inputs = _build_inputs(
        zone_type=zone_type, resolved_pnu=resolved_pnu, resolved_area=resolved_area,
        official_price=official_price,
    )
    legal_refs = _build_legal_refs(legal)
    # 정량 신뢰 가능 여부 = 기존 pnu 차단 분기(:194)와 동일 조건(pnu 확인). 여기 도달=확인됨.
    quantitative_reliable = bool(resolved_pnu)
    data_quality = _build_data_quality(
        used_sources=sources, quantitative_reliable=quantitative_reliable,
        ordinance_confirmed=bool(legal.get("ordinance_confirmed")),
    )
    feasibility_band = await _build_feasibility_band(
        best_code=best, zone_type=zone_type, legal=legal,
        area_sqm=resolved_area, address=address,
        official_price_per_sqm=official_price,
        quantitative_reliable=quantitative_reliable,
    )
    evidence = _build_evidence(
        legal=legal, area_checks=area_checks, legal_refs=legal_refs,
        area_sqm=resolved_area, feasibility_band=feasibility_band,
    )

    # ── 6) 선택적 LLM 해석(과설계 금지·전부 가산) — dead-path 복구(CR-1) ──
    # 기존엔 use_llm 시 _llm_one_liner 80자 한 줄만 나왔다. 우량 전용 인터프리터
    # SiteAnalysisInterpreter를 공용 컨텍스트 빌더(build_interpreter_context)로 배선해
    # 실효한도·공시지가·근거·법령링크·특이부지를 그라운딩한 다변량 해석을 ai_interpretation로
    # 가산한다. 기존 키(summary.llm_note 포함)는 전부 불변. 인터프리터 None/실패 시 graceful.
    ai_interpretation: dict | None = None
    if use_llm:
        try:
            from app.services.ai.interpreter_context import build_interpreter_context
            from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter

            collected = {
                "address": address,
                "zone_type": zone_type,
                "area_sqm": resolved_area,
                "legal": legal,
                "official_price": official_price,
                "evidence": evidence,
                "legal_refs": legal_refs,
                "sources": sources,
                "special_parcel": special_parcel,
            }
            ctx = build_interpreter_context(collected)
            ai_interpretation = await SiteAnalysisInterpreter().generate_interpretation(
                ctx["analysis_data"],
                evidence_text=ctx["evidence_text"],
                prior_context=ctx["prior_context"],
            )
            # 인터프리터가 빈 dict(호출 실패)면 None으로 정규화(graceful).
            if not ai_interpretation:
                ai_interpretation = None
        except Exception:  # noqa: BLE001 — 어떤 실패도 기존 응답 무손상(정직 폴백).
            ai_interpretation = None

        # summary.llm_note 파생: 인터프리터 성공 시 overall_summary에서 1줄 파생,
        # 실패 시 기존 규칙 폴백(_llm_one_liner 80자) — 무목업·정직.
        if ai_interpretation and ai_interpretation.get("overall_summary"):
            summary["llm_note"] = str(ai_interpretation["overall_summary"])[:200]
            sources.append("llm(site_analysis_interpreter)")
        else:
            summary["llm_note"] = await _llm_one_liner(
                address, zone_type, legal, n_pass, n_warn, n_fail,
                DEVELOPMENT_TYPE_NAMES.get(best, best) if best else None,
            )
            if summary["llm_note"]:
                sources.append("llm(anthropic)")

    return {
        "ok": True,
        "address": address,
        "pnu": resolved_pnu,
        "zone_type": zone_type,
        "area_sqm": resolved_area,
        "legal_limits": legal,
        "methods": methods,
        "summary": summary,
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "sources": sources,
        # ── additive 신뢰 블록(선택적 렌더) ──
        "inputs": inputs,
        "data_quality": data_quality,
        "legal_refs": legal_refs,
        "evidence": evidence,
        "feasibility_band": feasibility_band,
        # 특이부지 게이트(가산) — None이면 일상부지(특이 없음). 정직 고지.
        "special_parcel": special_parcel,
        # 선택적 LLM 다변량 해석(가산) — use_llm=False면 None(기본). 인터프리터 실패도 None.
        "ai_interpretation": ai_interpretation,
        # ★A-3/G8(additive) — 법정초과 경량 가드 검출 시만 채워짐(빈 배열=검출 없음, 기존 키 불변).
        "integrity_warnings": integrity_warnings,
    }


async def _llm_one_liner(
    address: str, zone_type: str, legal: dict[str, Any],
    n_pass: int, n_warn: int, n_fail: int, best_name: str | None,
) -> str | None:
    """summary.llm_note 1줄만 생성(wait_for 25s, 실패시 None)."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.services.ai.llm_provider import get_llm

        llm = get_llm()
        system = SystemMessage(content=(
            "너는 부동산 개발 인허가 사전검토 전문가다. 사실에 근거해 1문장(80자 이내)으로만 "
            "핵심 결론을 한국어로 답하라. 수치 추정·과장 금지."
        ))
        # ★적용(실효) 한도를 그라운딩 — 법정상한(자연녹지 100%)을 그대로 주면 LLM 요약이
        #   과대낙관한다. 실효값+산정근거를 명시해 상향 재해석을 차단한다(PR#334 동일 패턴).
        _bcr = legal.get("applied_bcr_pct") if legal.get("applied_bcr_pct") is not None else legal.get("bcr_pct")
        _far = legal.get("applied_far_pct") if legal.get("applied_far_pct") is not None else legal.get("far_pct")
        human = HumanMessage(content=(
            f"부지: {address} / 용도지역: {zone_type} / 적용 건폐율 {_bcr}% "
            f"적용 용적률 {_far}%(산정근거: {legal.get('far_basis') or '법정/조례 상한'} — "
            "이미 실효치이므로 상향 낙관 금지)"
            f" / 사전검토 결과 적합 {n_pass}·주의 {n_warn}·불가 {n_fail}건"
            + (f" / 최우선 후보: {best_name}." if best_name else ".")
            + " 한 문장 요약."
        ))
        resp = await asyncio.wait_for(llm.ainvoke([system, human]), timeout=_LLM_TIMEOUT)
        # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
        from app.services.ai.base_interpreter import record_llm_response_billing
        await record_llm_response_billing(llm, resp, service="precheck")
        text = getattr(resp, "content", None)
        if isinstance(text, list):  # 일부 프로바이더는 블록 리스트 반환
            text = " ".join(str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in text)
        text = (text or "").strip()
        return text[:200] or None
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# feasibility_band(최저/기본/최대) — best 후보 1건만 3시나리오(90초 SLA 보호).
# 새 계산로직 0: ModuleInput → FeasibilityServiceV2.calculate(검증된 엔진)를
# run_sensitivity_analysis의 calculate_fn 클로저로 감싸 분양가·공사비·분양률을 밴드로 흔든다.
# ─────────────────────────────────────────────────────────────────────────────
# 밴드 가정(최저/기본/최대) — 분양가 ±15%, 공사비 ∓(상승/하락), 분양률 0.85~1.0.
_BAND_ASSUMPTIONS: dict[str, dict[str, float]] = {
    "min":  {"sale_price_delta_pct": -15.0, "construction_cost_delta_pct": 10.0, "sale_ratio": 0.85},
    "base": {"sale_price_delta_pct": 0.0,   "construction_cost_delta_pct": 0.0,  "sale_ratio": 0.95},
    "max":  {"sale_price_delta_pct": 15.0,  "construction_cost_delta_pct": -10.0, "sale_ratio": 1.0},
}


async def _build_band_module_input(
    *,
    best_code: str,
    zone_type: str,
    legal: dict[str, Any],
    area_sqm: float,
    address: str | None,
    official_price_per_sqm: float | None,
):
    """best 후보 → ModuleInput 구성(auto_recommend_top3 헬퍼 재사용, 새 산식 0).

    적용 용적률(applied_far_pct, 조례 실효값 우선)로 연면적·세대수를 산정한다.
    """
    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
    from app.services.feasibility.modules.base_module import ModuleInput

    svc = FeasibilityServiceV2()
    # 적용 용적률 = SSOT(calc_effective_far) 실효값(_legal_limits가 applied_far_pct로 소비 —
    # 구조상한(건폐율×층수) 포함). 없으면 법정상한, 그래도 없으면 유형 일반값.
    # 과거엔 applied가 min(법정,조례)까지만이라 자연녹지 수지밴드 연면적이 100%/80%=25% 과대였다.
    applied_far = legal.get("applied_far_pct") or legal.get("far_pct")
    typical_far = svc._get_type_typical_far(best_code)
    effective_far = min(float(applied_far), typical_far) if applied_far else typical_far

    total_gfa = area_sqm * effective_far / 100.0
    eff_ratio = svc._get_type_efficiency_ratio(best_code)
    avg_unit_area = svc._get_type_avg_unit_area(best_code)
    total_hh = max(1, int(total_gfa * eff_ratio / avg_unit_area))
    region = (legal.get("sigungu") or await _extract_sigungu_from_address(address) or "서울")

    inp = ModuleInput(
        development_type=best_code,
        total_land_area_sqm=area_sqm,
        total_gfa_sqm=total_gfa,
        total_households=total_hh,
        avg_sale_price_per_pyeong=svc._get_regional_price(best_code, region, address or ""),
        # ★D1 규약: 전용평(공급 환산은 revenue_block 담당 — 매출 라운드트립 무회귀).
        avg_area_pyeong=avg_unit_area / 3.305785,
        sale_ratio=0.95 if best_code not in ("M14", "M15") else 0.0,
        official_price_per_sqm=official_price_per_sqm,
        price_multiplier=1.1,
        building_type=svc._get_building_type(best_code),
        sido_name=region,
        sigungu_name="",
        project_months=svc._get_type_project_months(best_code),
        discount_rate=0.08,
    )
    return svc, inp


async def _build_feasibility_band(
    *,
    best_code: str | None,
    zone_type: str | None,
    legal: dict[str, Any],
    area_sqm: float | None,
    address: str | None,
    official_price_per_sqm: float | None = None,
    quantitative_reliable: bool = True,
) -> dict | None:
    """최저/기본/최대 3시나리오 밴드 — 검증된 수지엔진 호출만(새 계산로직 금지).

    best 후보 1건에 대해 분양가(±15%)·공사비(∓)·분양률(0.85~1.0)을 흔들어
    run_sensitivity_analysis(custom 3점)로 NPV/이익률/ROI/등급을 산출한다.
    best 없거나 면적 미확정·정량 신뢰불가면 None(밴드 생략 — 빈 결과/과장 금지).
    """
    if not best_code or not zone_type or not area_sqm or not quantitative_reliable:
        return None
    # ★가격 신뢰성 게이트: 개별공시지가(토지비 근거)가 없으면 밴드를 생략한다.
    #   과거 결함 — 공시지가 미확보 시 1,500,000원/㎡ 묵시폴백으로 토지비가 실가의 1/10이 되어
    #   ROI가 비현실적으로 과대(예: 강남 235%·전부 grade A)하게 산출됐다. 토지비 없는 수지는
    #   해석 불가 → 가짜 낙관 대신 정직하게 밴드를 비운다(할루시네이션 방지).
    if not official_price_per_sqm or official_price_per_sqm <= 0:
        return None
    try:
        svc, base_inp = await _build_band_module_input(
            best_code=best_code, zone_type=zone_type, legal=legal,
            area_sqm=float(area_sqm), address=address,
            official_price_per_sqm=official_price_per_sqm,
        )
        # 입력 검증(엔진 가드) — 실패 시 밴드 생략.
        if base_inp.total_gfa_sqm <= 0 or base_inp.total_land_area_sqm <= 0:
            return None

        import dataclasses

        from app.services.feasibility.sensitivity_engine import (
            SensitivityScenario,
            run_sensitivity_analysis,
        )

        base_sale_price = base_inp.avg_sale_price_per_pyeong

        base_cost_index = float(base_inp.params.get("cost_index_factor", 1.0) or 1.0)

        def calculate_fn(values: dict[str, float]) -> dict[str, Any]:
            """값 dict → {profit_rate_pct, npv_won, roi_pct, grade}. 검증된 엔진만 호출.

            공사비 변동은 construction_cost_engine이 실제로 읽는 params.cost_index_factor로
            반영한다(밴드 단조성 보장). 분양가는 avg_sale_price_per_pyeong, 분양률은 sale_ratio.
            """
            sale_price = values.get("sale_price", base_sale_price)
            cost_mult = values.get("construction_cost", 1.0)
            sale_ratio = values.get("sale_ratio", base_inp.sale_ratio)
            inp = dataclasses.replace(
                base_inp,
                avg_sale_price_per_pyeong=sale_price,
                sale_ratio=sale_ratio,
                params={**base_inp.params, "cost_index_factor": base_cost_index * cost_mult},
            )
            out = svc.calculate(inp)
            return {
                "profit_rate_pct": out.profit_rate_pct,
                "npv_won": out.npv_won,
                "roi_pct": out.roi_pct,
                "grade": out.grade,
            }

        # 3점 커스텀 시나리오(분양가/공사비). 분양률은 시나리오별 base_values로 직접 주입.
        scenarios = [
            SensitivityScenario("분양가 변동", "sale_price", [-15.0, 0.0, 15.0]),
            SensitivityScenario("공사비 변동", "construction_cost", [-10.0, 0.0, 10.0]),
        ]

        def _scenario_result(key: str) -> dict[str, Any]:
            a = _BAND_ASSUMPTIONS[key]
            values = {
                "sale_price": base_sale_price * (1 + a["sale_price_delta_pct"] / 100.0),
                "construction_cost": 1 + a["construction_cost_delta_pct"] / 100.0,
                "sale_ratio": a["sale_ratio"],
            }
            r = calculate_fn(values)
            return {
                "npv_won": r["npv_won"],
                "profit_rate_pct": r["profit_rate_pct"],
                "roi_pct": r["roi_pct"],
                "grade": r["grade"],
                "assumptions": dict(a),
            }

        scn = {k: _scenario_result(k) for k in ("min", "base", "max")}

        # band_drivers: 토네이도(base 기준 ±delta 스프레드 상위).
        sens = run_sensitivity_analysis(
            base_values={
                "sale_price": base_sale_price,
                "construction_cost": 1.0,
                "sale_ratio": base_inp.sale_ratio,
            },
            calculate_fn=calculate_fn,
            scenarios=scenarios,
        )
        band_drivers = [
            {"variable": t["variable"], "name": t["name"], "spread_pct": round(t["spread"], 2)}
            for t in sens.get("tornado", [])
        ]

        from app.services.feasibility.permit_validator import DEVELOPMENT_TYPE_NAMES

        return {
            "method_code": best_code,
            "method_name": DEVELOPMENT_TYPE_NAMES.get(best_code, best_code),
            "scenarios": scn,
            "band_drivers": band_drivers,
            "evidence_ref": "ev_feasibility",
            "note": "best 후보 1건의 3시나리오(최저/기본/최대) — 검증된 수지엔진 산출(참고용).",
        }
    except Exception:  # noqa: BLE001 — 밴드 산출 실패 시 생략(기존 응답 무손상).
        import structlog

        structlog.get_logger().warning("feasibility_band 산출 스킵")
        return None


# ──────────────────────────────────────────────────────────────────────────
# B. 조닝 시그널(기회필지)
# ──────────────────────────────────────────────────────────────────────────

# 저밀 주거(통합개발/재건축·용도상향 후보 판정용)
_LOW_DENSITY = {
    "제1종전용주거지역", "제2종전용주거지역", "제1종일반주거지역",
    "제2종일반주거지역", "제3종일반주거지역",
}


async def run_zoning_signals(
    address: str | None = None,
    pnu: str | None = None,
    radius_m: int = 300,
) -> dict[str, Any]:
    """주변 기회필지 시그널(계약 B). 주변 필지 0이면 signals=[] + note."""
    from app.services.external_api.vworld_service import VWorldService

    vworld = VWorldService()
    sources: list[str] = ["auto_zoning_service", "vworld(연속지적도)"]

    # ── 1) 대상 필지(좌표·용도지역) ──
    target_zone: str | None = None
    target_pnu = pnu
    lat = lon = None
    if address:
        try:
            zoning = await asyncio.wait_for(
                AutoZoningService().analyze_by_address(address), timeout=_ZONING_TIMEOUT
            )
            target_zone = zoning.get("zone_type")
            target_pnu = target_pnu or zoning.get("pnu")
            coords = zoning.get("coordinates") or {}
            lat, lon = coords.get("lat"), coords.get("lon")
        except Exception:  # noqa: BLE001
            pass
    # 좌표 미확보 시 지오코딩 폴백
    if (lat is None or lon is None) and address:
        try:
            geo = await asyncio.wait_for(vworld.geocode_address(address), timeout=_BBOX_TIMEOUT)
            if geo:
                lat, lon = geo.get("lat"), geo.get("lon")
                target_pnu = target_pnu or geo.get("pnu")
        except Exception:  # noqa: BLE001
            pass

    if not target_zone:
        return {
            "ok": False,
            "message": "대상 필지의 용도지역을 확인할 수 없습니다. 주소 또는 PNU를 확인해 주세요.",
            "target": {"pnu": target_pnu, "zone_type": None, "address": address or ""},
            "signals": [],
            "sources": sources,
        }

    target = {"pnu": target_pnu or "", "zone_type": target_zone, "address": address or ""}

    if lat is None or lon is None:
        return {
            "ok": True,
            "target": target,
            "signals": [],
            "geojson": None,
            "note": "좌표를 확보하지 못해 주변 필지 분석을 생략했습니다(VWorld 키 미설정 가능).",
            "sources": sources,
        }

    # ── 2) 반경 내 주변 필지(bbox) ──
    deg = radius_m / 111_320.0  # 위경도 1도 ≈ 111.32km
    nearby: list[dict] = []
    try:
        nearby = await asyncio.wait_for(
            vworld.get_parcels_in_bbox(
                lon - deg, lat - deg, lon + deg, lat + deg, max_count=80
            ),
            timeout=_BBOX_TIMEOUT,
        )
    except Exception:  # noqa: BLE001
        nearby = []

    # 대상 필지 제외
    nearby = [p for p in nearby if p.get("pnu") and p.get("pnu") != target_pnu]

    if not nearby:
        return {
            "ok": True,
            "target": target,
            "signals": [],
            "geojson": None,
            "note": "반경 내 주변 필지를 찾지 못했습니다(데이터 부족 또는 VWorld 키 미설정).",
            "sources": sources,
        }

    # ── 3) 인접성(연결요소) 판정 — routers/auto_zoning._parcel_adjacency 재사용 ──
    from routers.auto_zoning import _parcel_adjacency

    geoms = [p.get("geometry") for p in nearby]
    adjacency = _parcel_adjacency(geoms)
    contiguous = adjacency.get("contiguous")

    signals = _derive_signals(target_zone, nearby, contiguous)

    # ── 4) GeoJSON(주변 필지 경계, 지도용) ──
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": p.get("geometry"),
             "properties": {"pnu": p.get("pnu"), "jimok": p.get("jimok")}}
            for p in nearby if p.get("geometry")
        ],
    }

    return {
        "ok": True,
        "target": target,
        "signals": signals,
        "geojson": geojson,
        "adjacency": adjacency,
        "sources": sources,
    }


def _derive_signals(
    target_zone: str, nearby: list[dict], contiguous: bool | None,
) -> list[dict[str, Any]]:
    """규칙기반 기회 시그널 산정.

    bbox 필지는 용도지역 정보가 없어(연속지적도=지목만) 대상 용도지역 기준으로
    유형을 판정한다. 인접(contiguous) 여부로 통합개발 가능성을 가른다.
    """
    signals: list[dict[str, Any]] = []
    n = len(nearby)
    norm_target = _normalize_zone(target_zone)

    def parcels_payload(adj: bool) -> list[dict]:
        return [
            {"pnu": p.get("pnu"), "zone_type": target_zone, "adjacent": adj}
            for p in nearby[:12]
        ]

    # (1) 통합개발 후보: 주변 필지가 맞닿아 있고(동일 용도지역 가정) 다수
    if contiguous is True and n >= 2:
        score = min(100.0, 50.0 + n * 5.0)
        signals.append({
            "type": "통합개발후보",
            "score": round(score, 1),
            "level": "high" if score >= 75 else "mid",
            "parcels": parcels_payload(True),
            "rationale": f"반경 내 {n}개 인접 필지가 연결되어 합필·일단지 통합개발이 가능합니다.",
        })
    elif n >= 2:
        signals.append({
            "type": "통합개발후보",
            "score": 40.0,
            "level": "low",
            "parcels": parcels_payload(False),
            "rationale": f"주변 {n}개 필지가 존재하나 비인접 그룹으로 분리되어 부분 통합만 가능합니다.",
        })

    # (2) 용도상향 기회: 대상이 주거인데 인접에 고밀(준주거/상업) 가능성
    if norm_target in _LOW_DENSITY:
        signals.append({
            "type": "용도상향기회",
            "score": 60.0,
            "level": "mid",
            "parcels": parcels_payload(contiguous is True),
            "rationale": f"{target_zone}은 용도지역 상향(준주거·상업) 또는 지구단위계획으로 밀도 상향 여지가 있습니다.",
        })

    # (3) 저밀 재건축: 1·2종 저밀 주거의 노후 단지 재건축 기회
    if norm_target in {"제1종전용주거지역", "제2종전용주거지역", "제1종일반주거지역", "제2종일반주거지역"}:
        signals.append({
            "type": "저밀재건축",
            "score": 55.0,
            "level": "mid",
            "parcels": parcels_payload(contiguous is True),
            "rationale": f"{target_zone}의 저밀 특성상 노후도 충족 시 재건축·소규모정비 사업 후보입니다.",
        })

    # (4) 역세권 개발: 역세권/준주거/상업이면
    if norm_target in {"역세권개발구역", "준주거지역"} or "역세권" in target_zone:
        signals.append({
            "type": "역세권개발",
            "score": 70.0,
            "level": "high",
            "parcels": parcels_payload(contiguous is True),
            "rationale": f"{target_zone}은 역세권 고밀복합개발(주상복합·오피스텔) 적지입니다.",
        })

    # 점수 내림차순
    signals.sort(key=lambda s: s["score"], reverse=True)
    return signals
