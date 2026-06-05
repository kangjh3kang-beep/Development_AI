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


def _legal_limits(zone_type: Optional[str]) -> dict[str, Any]:
    """용도지역 → 법정 건폐율/용적률/높이 한도(국토계획법 제78조)."""
    if not zone_type:
        return {"bcr_pct": None, "far_pct": None, "height_m": None, "source": "미확인"}
    key = _normalize_zone(zone_type)
    limits = ZONE_LIMITS.get(key)
    if not limits:
        return {"bcr_pct": None, "far_pct": None, "height_m": None, "source": "법정한도 미매핑"}
    return {
        "bcr_pct": limits.get("max_bcr"),
        "far_pct": limits.get("max_far"),
        "height_m": limits.get("max_height_m"),
        "source": "국토의 계획 및 이용에 관한 법률 제78조",
    }


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
    except asyncio.TimeoutError:
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

    # ── 2) 법정 한도 + 후보 개발방식 ──
    legal = _legal_limits(zone_type)
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
        text = getattr(resp, "content", None)
        if isinstance(text, list):  # 일부 프로바이더는 블록 리스트 반환
            text = " ".join(str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in text)
        text = (text or "").strip()
        return text[:200] or None
    except Exception:  # noqa: BLE001
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
