"""C2R 파운데이션 조립 — 부지 해석 → 인벨로프 → 브리프 → Think-Before(렌더는 별도).

build_foundation 은 좌표(주소/PNU)에서 시작해 결정론 파운데이션을 만든다.
★렌더(이미지)는 기본 호출하지 않는다(render.status='pending_provider'). 실제 이미지 생성은
별도 엔드포인트(/c2r/render)에서 image_provider.render_image 로 수행한다(과금/인증 게이트).

기존 primitive 재사용(새로 만들지 않음):
 - AutoZoningService.analyze_by_address — 주소→PNU→용도지역→건폐/용적/높이 한도.
 - VWorldService.get_land_info / get_parcel_by_pnu — 필지 geometry(graceful).
 - compute_buildable_envelope + dims_from_polygon — 정북일조 건축가능 인벨로프.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services.cad.provenance import compute_geometry_hash

logger = structlog.get_logger(__name__)


async def _resolve_parcel(pnu_or_address: str) -> dict[str, Any]:
    """주소/PNU → 부지 해석(용도지역·면적·한도·좌표). AutoZoningService 재사용.

    PNU 형태(숫자 19자리)면 주소 대신 그대로 전달해도 analyze_by_address 가 geocode 시도.
    """
    from app.services.zoning.auto_zoning_service import AutoZoningService

    try:
        parcel = await AutoZoningService().analyze_by_address(pnu_or_address)
    except Exception as e:  # noqa: BLE001 — 해석 실패는 정직한 빈 부지로 진행
        logger.warning("c2r 부지 해석 실패", err=str(e)[:140])
        parcel = {"address": pnu_or_address, "zone_type": None, "zone_limits": None,
                  "land_area_sqm": None, "warnings": [f"부지 해석 실패: {str(e)[:80]}"]}
    return parcel


async def _fetch_geometry(parcel: dict[str, Any]) -> dict[str, Any] | None:
    """필지 geometry(GeoJSON) 조회 — VWorldService 재사용(graceful, 키 없으면 None)."""
    pnu = parcel.get("pnu")
    if not pnu:
        return None
    try:
        from app.services.external_api.vworld_service import VWorldService

        info = await VWorldService().get_land_info(pnu)
        if info and info.get("geometry"):
            return info["geometry"]
    except Exception as e:  # noqa: BLE001 — geometry 미확보는 인벨로프 폴백(정사각 가정)
        logger.warning("c2r geometry 조회 실패", err=str(e)[:120])
    return None


def _compute_envelope(parcel: dict[str, Any], geometry: dict[str, Any] | None) -> dict[str, Any]:
    """compute_buildable_envelope 호출 — 면적/치수/한도를 부지 해석에서 채워 전달."""
    from app.services.site_score.solar_envelope_service import (
        compute_buildable_envelope,
        dims_from_polygon,
    )

    zone = parcel.get("zone_type") or ""
    zl = parcel.get("zone_limits") or {}
    land_area = parcel.get("land_area_sqm")

    dims = dims_from_polygon(geometry) if geometry else None
    if dims and not land_area:
        land_area = dims.get("area_sqm")
    if not land_area or land_area <= 0:
        # 면적 미확보 — 인벨로프 산출 불가(정직 표기, 가짜 면적 금지).
        return {"error": "대지면적 미확보 — 인벨로프 산출 불가(부지 해석에서 면적을 얻지 못함).",
                "applies_north_light": None}

    coords = parcel.get("coordinates") or {}
    lat = coords.get("lat") if isinstance(coords, dict) else None

    return compute_buildable_envelope(
        land_area_sqm=float(land_area),
        zone=zone,
        land_width_m=(dims or {}).get("width_m"),
        land_depth_m=(dims or {}).get("depth_m"),
        bcr_limit_pct=zl.get("max_bcr_pct"),
        far_limit_pct=zl.get("max_far_pct"),
        latitude=float(lat) if isinstance(lat, (int, float)) else 37.5,
    )


# 기하 지문에 넣을 '인벨로프의 결정적 수치 키' — 같은 부지·같은 한도면 항상 같은 값.
#  ★결정론만 담는다(날짜·uuid·랜덤 금지). 없는 키(None)는 지문에서 제외(가짜 수치 금지).
_GEOM_FINGERPRINT_KEYS = (
    "far_pct",            # 법정 용적률 상한(%)
    "bcr_pct",            # 법정 건폐율 상한(%)
    "realistic_far_pct",  # 현실 용적률(층수제한 반영, %)
    "max_height_m",       # 인벨로프 최고 높이(m)
    "max_floors",         # 인벨로프 현실 층수
    "effective_gfa_sqm",  # 현실 연면적(㎡)
    "envelope_gfa_sqm",   # 인벨로프 연면적(㎡)
)


def _attach_geometry_hash(
    brief: dict[str, Any], parcel: dict[str, Any], envelope: dict[str, Any]
) -> None:
    """브리프에 geometry_hash·geometry_fingerprint 를 부착한다(2키만 additive·기존 키 무변경).

    왜(쉬운 설명): 렌더 가드가 '이 브리프가 정말 우리 인벨로프에서 나왔나'를 확인하려면,
      인벨로프의 결정적 수치를 한데 모은 '기하요약(fingerprint)'과 그 sha256 지문(hash)이 필요하다.
      대지면적은 인벨로프 dict 에 echo 되지 않으므로 부지 해석(parcel)에서 보강한다.

    ★결정론: 같은 입력이면 항상 같은 fingerprint → 같은 geometry_hash(멱등·재현·변조탐지).
    ★무날조: 값이 없는 항목은 지문에 넣지 않는다(가짜 0/추정 금지). footprint 도 있을 때만 포함.
    """
    geom_fp: dict[str, Any] = {}

    # 인벨로프의 결정적 수치 — 실제로 있는(None 아님) 키만 담는다.
    for k in _GEOM_FINGERPRINT_KEYS:
        v = envelope.get(k)
        if v is not None:
            geom_fp[k] = v

    # 대지면적 — 인벨로프엔 echo 안 되므로 envelope→parcel 순으로 확보(있을 때만).
    land_area = envelope.get("land_area_sqm") or parcel.get("land_area_sqm")
    if land_area is not None:
        geom_fp["land_area_sqm"] = land_area

    # 1층 바닥면적(footprint) — 브리프 program 에 이미 결정론으로 산출돼 있으면 재사용(있을 때만).
    footprint = (brief.get("program") or {}).get("footprint_sqm")
    if footprint is not None:
        geom_fp["footprint_sqm"] = footprint

    # ★핵심 기하키(인벨로프의 far/bcr/연면적/층수 등)를 하나도 못 담았으면 — 인벨로프 산출이
    #   실패(대지면적 미확보 등)한 빈 지문이다. 이런 브리프엔 hash를 붙이지 않는다(가드가 '검증 안 된
    #   브리프'로 정직하게 차단하도록). 빈 지문에 hash를 붙이면 '빈 일치'로 가드를 우회한다(MEDIUM 수정).
    core_keys = set(_GEOM_FINGERPRINT_KEYS)
    if not any(k in core_keys for k in geom_fp):
        return  # 검증할 기하 신호 없음 → hash 미부착(brief 무변경)

    # 2키만 additive 부착 — 기존 브리프 구조·키는 그대로.
    brief["geometry_fingerprint"] = geom_fp
    brief["geometry_hash"] = compute_geometry_hash(geom_fp)


async def build_foundation(
    pnu_or_address: str,
    options: dict[str, Any] | None = None,
    *,
    use_llm: bool = False,
) -> dict[str, Any]:
    """좌표(주소/PNU)에서 C2R 파운데이션을 조립한다(렌더는 pending — 별도 엔드포인트).

    Args:
        pnu_or_address: 분석 대상 주소 또는 PNU.
        options:        program 옵션 {building_use, scale, style, materials, ...}.
        use_llm:        True면 DesignInterpreter로 브리프 자연어 보강(graceful).

    Returns:
        {parcel, envelope, brief, think_before, render:{status:'pending_provider'|...}}.
    """
    options = options or {}
    parcel = await _resolve_parcel(pnu_or_address)
    geometry = await _fetch_geometry(parcel)
    envelope = _compute_envelope(parcel, geometry)

    from app.services.c2r.render_brief import enrich_brief_with_llm, synthesize_brief
    from app.services.c2r.think_before import evaluate

    brief = synthesize_brief(parcel=parcel, envelope=envelope, program=options)
    if use_llm:
        brief = await enrich_brief_with_llm(brief)

    # 렌더 가드용 기하 지문 부착 — 우리 파이프라인 브리프는 '검증된 브리프'임을 증명하는 표식.
    #  ★LLM 보강이 brief 를 새 dict 로 갈아끼울 수 있어, 보강 '이후'에 부착해야 살아남는다.
    _attach_geometry_hash(brief, parcel, envelope)

    gate = evaluate(brief)

    # 렌더는 기본 호출하지 않는다 — Think-Before가 막으면 그 사유를, 통과면 'pending_provider'.
    if not gate.get("proceed"):
        render_status = {
            "status": "blocked_by_think_before",
            "reason": "명료화/근거가 필요합니다(think_before 참조).",
        }
    else:
        render_status = {
            "status": "pending_provider",
            "note": "렌더는 /api/v1/c2r/render 에서 provider 키로 별도 수행(과금/인증 게이트).",
        }

    return {
        "parcel": parcel,
        "envelope": envelope,
        "brief": brief,
        "think_before": gate,
        "render": render_status,
    }
