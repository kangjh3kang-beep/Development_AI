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
