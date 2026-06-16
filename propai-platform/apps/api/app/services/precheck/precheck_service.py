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
from typing import Any, Optional

from app.services.feasibility.permit_validator import (
    DEVELOPMENT_TYPE_NAMES,
    get_permit_complexity,
    get_permitted_types,
)
from app.services.zoning.auto_zoning_service import ZONE_LIMITS, AutoZoningService

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


async def _legal_limits(zone_type: Optional[str], address: Optional[str] = None) -> dict[str, Any]:
    """용도지역 → 법정 건폐율/용적률/높이 한도(국토계획법 제78조) + 조례 실효값(가산).

    기존 반환 키(bcr_pct/far_pct/height_m/source)는 전부 보존한다(_area_checks·프론트 무영향).
    address가 주어지면 OrdinanceService로 조례 실효값을 조회해 applicable_limits_for로
    계층 적용 한도(법정범위→조례→도시군관리계획)를 산정하고, 다음 키를 **가산**한다:
      applied_bcr_pct / applied_far_pct / ordinance_confirmed / far_source /
      sigungu / legal_ref_keys(법령 원문링크 근거키 목록).
    조례 조회 실패·미확인 시 법정상한으로 폴백(현행 동작과 동일값), ordinance_confirmed=False.
    """
    if not zone_type:
        return {"bcr_pct": None, "far_pct": None, "height_m": None, "source": "미확인",
                "legal_ref_keys": []}
    key = _normalize_zone(zone_type)
    limits = ZONE_LIMITS.get(key)
    if not limits:
        return {"bcr_pct": None, "far_pct": None, "height_m": None, "source": "법정한도 미매핑",
                "legal_ref_keys": []}

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
    sigungu = _extract_sigungu_from_address(address)
    legal["sigungu"] = sigungu
    legal["ordinance_confirmed"] = False
    legal["applied_bcr_pct"] = legal["bcr_pct"]
    legal["applied_far_pct"] = legal["far_pct"]
    legal["far_source"] = "법정범위 상한(조례·도시군관리계획 확인 필요)"

    regulation_payload: Any = None
    if address:
        try:
            from app.services.land_intelligence.ordinance_service import OrdinanceService

            ord_result = await asyncio.wait_for(
                OrdinanceService().get_ordinance_limits(address, zone_type),
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

    legal["legal_ref_keys"] = ref_keys
    return legal


def _extract_sigungu_from_address(address: Optional[str]) -> Optional[str]:
    """주소 문자열에서 시군구명을 정직 추출(조례 url 치환용).

    특별시/광역시(시군구 아님)는 건너뛰고 첫 시군구 토큰을 반환한다. 모든 후보를
    순회(finditer)하므로 '서울특별시 강남구 …'에서 '강남구'를 정확히 잡는다.
    추출 실패 시 None(레지스트리에 sigungu 미전달 → 조례 url_status='pending').
    """
    addr = str(address or "")
    if not addr:
        return None
    for m in re.finditer(r"(\S{2,4}[시군구])(?:\s|$)", addr):
        cand = m.group(1)
        if "특별" not in cand and "광역" not in cand:
            return cand
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
    zone_type: Optional[str],
    resolved_pnu: Optional[str],
    resolved_area: Optional[float],
    official_price: Optional[float] = None,
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


def _fmt_pct(v) -> Optional[str]:
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
    area_sqm: Optional[float],
    feasibility_band: Optional[dict] = None,
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

    # (1) 적용 용적률 트레이스(법정 vs 조례 min).
    far_legal_fmt = _fmt_pct(far_legal)
    applied_far_fmt = _fmt_pct(applied_far)
    if far_legal_fmt:
        if ordinance_confirmed and applied_far_fmt and applied_far_fmt != far_legal_fmt:
            formula = f"적용 용적률 = min(법정상한 {far_legal_fmt}, {sigungu} 조례 {applied_far_fmt})"
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


def _area_checks(area_sqm: Optional[float], legal: dict[str, Any]) -> list[dict[str, str]]:
    """면적 기반 건폐율/용적률 개략 검토 체크.

    면적이 있으면 법정한도 존재 여부로 정보성 pass, 없으면 warn("면적 미입력").
    실제 배치설계 전이므로 정량 위반은 단정하지 않고 한도값을 안내한다.
    """
    checks: list[dict[str, str]] = []
    bcr = legal.get("bcr_pct")
    far = legal.get("far_pct")
    height = legal.get("height_m")

    if area_sqm:
        if bcr is not None:
            buildable = round(area_sqm * bcr / 100.0)
            checks.append({
                "rule": "건폐율",
                "status": "pass",
                "detail": f"법정 건폐율 {bcr}% → 1층 최대 건축면적 약 {buildable:,}㎡",
            })
        else:
            checks.append({"rule": "건폐율", "status": "warn", "detail": "법정 건폐율 한도 미매핑"})
        if far is not None:
            gfa = round(area_sqm * far / 100.0)
            checks.append({
                "rule": "용적률",
                "status": "pass",
                "detail": f"법정 용적률 {far}% → 연면적 최대 약 {gfa:,}㎡",
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
    pnu: Optional[str] = None,
    area_sqm: Optional[float] = None,
    use_llm: bool = False,
) -> dict[str, Any]:
    """즉시 룰체크(계약 A). 90초 SLA — 외부 호출 1회(+선택 LLM 1회)."""
    t0 = time.perf_counter()
    sources: list[str] = ["permit_validator", "ZONE_LIMITS(국토계획법 제78조)"]

    # ── 1) 주소→용도지역·면적(외부 1회, wait_for 가드) ──
    zone_type: Optional[str] = None
    resolved_pnu = pnu
    resolved_area = area_sqm
    try:
        zoning = await asyncio.wait_for(
            AutoZoningService().analyze_by_address(address), timeout=_ZONING_TIMEOUT
        )
        zone_type = zoning.get("zone_type")
        resolved_pnu = resolved_pnu or zoning.get("pnu")
        if resolved_area is None:
            resolved_area = zoning.get("land_area_sqm")
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

    # ── 2) 법정 한도(조례 실효값 가산) + 후보 개발방식 ──
    legal = await _legal_limits(zone_type, address)
    permitted_codes = get_permitted_types(zone_type)
    area_checks = _area_checks(resolved_area, legal)

    # 후보군: 허용된 코드 우선, 불허는 제외(계약은 "해당 용도지역 후보").
    # 단 전부 불허(녹지 등)면 대표 후보 일부를 fail로 보여 변별.
    candidates = permitted_codes if permitted_codes else ["M06", "M08", "M10", "M13"]
    methods = [
        _build_method(code, zone_type, permitted_codes, area_checks)
        for code in candidates
    ]
    # 복잡도 오름차순(쉬운 것 먼저) → pass가 상단
    methods.sort(key=lambda m: (m["signal"] != "pass", m["complexity"]))

    # ── 3) 요약 ──
    n_pass = sum(1 for m in methods if m["signal"] == "pass")
    n_warn = sum(1 for m in methods if m["signal"] == "warn")
    n_fail = sum(1 for m in methods if m["signal"] == "fail")
    best = methods[0]["code"] if methods and methods[0]["signal"] != "fail" else None

    summary: dict[str, Any] = {
        "pass": n_pass, "warn": n_warn, "fail": n_fail, "best": best, "llm_note": None,
    }

    # ── 4) 선택적 LLM 1줄 요약(과설계 금지) ──
    if use_llm:
        summary["llm_note"] = await _llm_one_liner(
            address, zone_type, legal, n_pass, n_warn, n_fail,
            DEVELOPMENT_TYPE_NAMES.get(best, best) if best else None,
        )
        if summary["llm_note"]:
            sources.append("llm(anthropic)")

    # ── 5) 신뢰 레이어(additive) — inputs/data_quality/legal_refs/evidence/feasibility_band ──
    # 전부 가산 필드. 조립 실패해도 기존 응답은 무손상(graceful).
    inputs = _build_inputs(
        zone_type=zone_type, resolved_pnu=resolved_pnu, resolved_area=resolved_area,
        official_price=None,
    )
    legal_refs = _build_legal_refs(legal)
    # 정량 신뢰 가능 여부 = 기존 pnu 차단 분기(:194)와 동일 조건(pnu 확인). 여기 도달=확인됨.
    quantitative_reliable = bool(resolved_pnu)
    data_quality = _build_data_quality(
        used_sources=sources, quantitative_reliable=quantitative_reliable,
        ordinance_confirmed=bool(legal.get("ordinance_confirmed")),
    )
    feasibility_band = _build_feasibility_band(
        best_code=best, zone_type=zone_type, legal=legal,
        area_sqm=resolved_area, address=address,
        official_price_per_sqm=None,
        quantitative_reliable=quantitative_reliable,
    )
    evidence = _build_evidence(
        legal=legal, area_checks=area_checks, legal_refs=legal_refs,
        area_sqm=resolved_area, feasibility_band=feasibility_band,
    )

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
    }


async def _llm_one_liner(
    address: str, zone_type: str, legal: dict[str, Any],
    n_pass: int, n_warn: int, n_fail: int, best_name: Optional[str],
) -> Optional[str]:
    """summary.llm_note 1줄만 생성(wait_for 25s, 실패시 None)."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.services.ai.llm_provider import get_llm

        llm = get_llm()
        system = SystemMessage(content=(
            "너는 부동산 개발 인허가 사전검토 전문가다. 사실에 근거해 1문장(80자 이내)으로만 "
            "핵심 결론을 한국어로 답하라. 수치 추정·과장 금지."
        ))
        human = HumanMessage(content=(
            f"부지: {address} / 용도지역: {zone_type} / 법정 건폐율 {legal.get('bcr_pct')}% "
            f"용적률 {legal.get('far_pct')}% / 사전검토 결과 적합 {n_pass}·주의 {n_warn}·불가 {n_fail}건"
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


def _build_band_module_input(
    *,
    best_code: str,
    zone_type: str,
    legal: dict[str, Any],
    area_sqm: float,
    address: Optional[str],
    official_price_per_sqm: Optional[float],
):
    """best 후보 → ModuleInput 구성(auto_recommend_top3 헬퍼 재사용, 새 산식 0).

    적용 용적률(applied_far_pct, 조례 실효값 우선)로 연면적·세대수를 산정한다.
    """
    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
    from app.services.feasibility.modules.base_module import ModuleInput

    svc = FeasibilityServiceV2()
    # 적용 용적률(조례 실효값 우선) 우선, 없으면 법정상한, 그래도 없으면 유형 일반값.
    applied_far = legal.get("applied_far_pct") or legal.get("far_pct")
    typical_far = svc._get_type_typical_far(best_code)
    effective_far = min(float(applied_far), typical_far) if applied_far else typical_far

    total_gfa = area_sqm * effective_far / 100.0
    eff_ratio = svc._get_type_efficiency_ratio(best_code)
    avg_unit_area = svc._get_type_avg_unit_area(best_code)
    total_hh = max(1, int(total_gfa * eff_ratio / avg_unit_area))
    region = (legal.get("sigungu") or _extract_sigungu_from_address(address) or "서울")

    inp = ModuleInput(
        development_type=best_code,
        total_land_area_sqm=area_sqm,
        total_gfa_sqm=total_gfa,
        total_households=total_hh,
        avg_sale_price_per_pyeong=svc._get_regional_price(best_code, region, address or ""),
        avg_area_pyeong=(avg_unit_area / eff_ratio) / 3.305785,
        sale_ratio=0.95 if best_code not in ("M14", "M15") else 0.0,
        official_price_per_sqm=official_price_per_sqm or 1_500_000,
        price_multiplier=1.1,
        building_type=svc._get_building_type(best_code),
        sido_name=region,
        sigungu_name="",
        project_months=svc._get_type_project_months(best_code),
        discount_rate=0.08,
    )
    return svc, inp


def _build_feasibility_band(
    *,
    best_code: Optional[str],
    zone_type: Optional[str],
    legal: dict[str, Any],
    area_sqm: Optional[float],
    address: Optional[str],
    official_price_per_sqm: Optional[float] = None,
    quantitative_reliable: bool = True,
) -> Optional[dict]:
    """최저/기본/최대 3시나리오 밴드 — 검증된 수지엔진 호출만(새 계산로직 금지).

    best 후보 1건에 대해 분양가(±15%)·공사비(∓)·분양률(0.85~1.0)을 흔들어
    run_sensitivity_analysis(custom 3점)로 NPV/이익률/ROI/등급을 산출한다.
    best 없거나 면적 미확정·정량 신뢰불가면 None(밴드 생략 — 빈 결과/과장 금지).
    """
    if not best_code or not zone_type or not area_sqm or not quantitative_reliable:
        return None
    try:
        svc, base_inp = _build_band_module_input(
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
    address: Optional[str] = None,
    pnu: Optional[str] = None,
    radius_m: int = 300,
) -> dict[str, Any]:
    """주변 기회필지 시그널(계약 B). 주변 필지 0이면 signals=[] + note."""
    from app.services.external_api.vworld_service import VWorldService

    vworld = VWorldService()
    sources: list[str] = ["auto_zoning_service", "vworld(연속지적도)"]

    # ── 1) 대상 필지(좌표·용도지역) ──
    target_zone: Optional[str] = None
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
    target_zone: str, nearby: list[dict], contiguous: Optional[bool],
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
