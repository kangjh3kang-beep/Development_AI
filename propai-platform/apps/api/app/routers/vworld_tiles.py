"""VWorld 타일 프록시(WMS 연속지적도·WMTS 베이스맵) — 관리자 키 반영 폴백 통로.

★배경(2026-07-17 진단): 관리자 화면(platform_secrets)에서 등록한 VWORLD_API_KEY는
secret_store.load_into_env()로 apps/api 프로세스에만 주입된다 — apps/web(Next.js)
컨테이너는 기동 시점 .env 값만 보므로 "관리자 등록 = 반영"이 web 타일 프록시에는
거짓이었다(사통맵 지적타일 혼란의 2차 원인). 이 라우터가 api측 동일 계약 프록시를
제공하고, web 프록시(vworld-wms-proxy.ts·vworld-wmts-proxy.ts)는 로컬 키 부재 시
여기로 폴백한다 — 관리자 키 갱신이 web 재빌드 없이 타일에 반영된다.

계약은 web 프록시와 동일(드리프트 금지 — 양쪽 테스트가 같은 시나리오를 고정):
  · 레이어 화이트리스트(오픈 프록시 남용 방지) — WMS 연속지적도 2종·WMTS 베이스맵 5종
  · LAYERS 스머글링 방지: 대소문자·중복 변형 전수 수집 검증 후 canonical 값만 상류 전달
  · 200+XML → coverage(투명PNG)/auth(503 + ServiceException code 표면화) 분류
  · 4xx/5xx·비이미지 → 503 JSON(무음 회색타일 금지)
키는 요청 시점 os.environ 우선(관리자 런타임 오버레이) → settings 폴백(ecos_key 관례 —
settings는 import 시점 고정이라 런타임 등록 키를 못 받는다).
"""

from __future__ import annotations

import base64
import logging
import os
import re
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from apps.api.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tiles/vworld", tags=["VWorld 타일 프록시"])

# ★R1 #1(레이트리밋 퍼널): 전역 기본 100/min은 keyless-web 배포에서 치명 — 모든 사용자의
#   타일이 web 서버 단일 egress IP로 귀속돼 지도 몇 뷰(뷰당 수십 타일)만으로 버킷이 소진되고
#   429→광역 회색타일이 된다. 타일 전용 상한을 크게 부여(전면 예외는 두지 않음 — 공개
#   라우트의 남용 방어는 레이어 화이트리스트+이 상한+VWorld 자체 쿼터의 3중으로 유지).
TILE_PROXY_LIMIT = "1200/minute"

VWORLD_WMS_BASE = "https://api.vworld.kr/req/wms"
VWORLD_WMTS_BASE = "https://api.vworld.kr/req/wmts/1.0.0"
VWORLD_REFERER = "https://www.4t8t.net"
VWORLD_DOMAIN = "www.4t8t.net"

# 화이트리스트 — web 프록시(ALLOWED_WMS_LAYERS_ORDER·SUPPORTED_LAYERS)와 동일 유지.
# ★web측(lib/vworld-wms-proxy.ts ALLOWED_WMS_LAYERS_ORDER)과 동기 유지 — LT_C_UQ111은
#   2026-07-17 전국 지적편집도(용도지역 land-use-wide) 컨트롤 도입으로 허용.
# ★레이어명 정본(2026-07-17 GetCapabilities 채증): WMS는 소문자만 인식 — 연속지적도는
#   lp_pa_cbnd_bubun/bonbun(종전 LP_PA_CBND_BUDB/BONB는 실존하지 않는 오기 — LayerNotDefined
#   근본원인). 데이터 API의 LP_PA_CBND_BUBUN(대문자)은 별개 계약이므로 혼동 금지.
ALLOWED_WMS_LAYERS: tuple[str, ...] = (
    "lp_pa_cbnd_bubun",
    "lp_pa_cbnd_bonbun",
    "lp_pa_cbnd_bubun_line",  # V1: 선 전용(위성뷰) — web과 동기
    "lp_pa_cbnd_bonbun_line",
    "lt_c_uq111",
)
SUPPORTED_WMTS_LAYERS: frozenset[str] = frozenset({"Base", "Satellite", "Hybrid", "gray", "midnight"})

# 투명 1x1 PNG — 정상 무제공영역(coverage) 타일 자리 흡수(지도 회색화 방지).
TRANSPARENT_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

# ── 200+XML 분류 — web lib/vworld-xml-exception.ts와 동일 계약(패턴 동기 유지) ──
_COVERAGE_PATTERN = re.compile(r"filenotfound|제공\s*영역", re.IGNORECASE)
# ★경계 필수: <ServiceExceptionReport>(접두 동일)가 매칭되는 오탐 방지 — \s 강제.
_CODE_PATTERN = re.compile(r'<ServiceException\s[^>]*\bcode="([^"]+)"', re.IGNORECASE)


def classify_vworld_xml(xml_text: str) -> str:
    """'coverage'(정상 무제공영역 — 투명타일) 또는 'auth'(그 외 전부 — 503 승격)."""
    return "coverage" if _COVERAGE_PATTERN.search(xml_text or "") else "auth"


def extract_vworld_code(xml_text: str) -> str | None:
    """ServiceException code 추출(INVALID_KEY·INVALID_RANGE·UNREGISTERED_DOMAIN 등)."""
    m = _CODE_PATTERN.search(xml_text or "")
    return m.group(1).strip() if m else None


def _vworld_key() -> str:
    """요청 시점 키 해석 — 관리자 런타임 오버레이(os.environ) 우선, settings 폴백."""
    key = os.getenv("VWORLD_API_KEY")
    if key:
        return key.strip()
    try:
        from app.core.config import settings

        return (settings.VWORLD_API_KEY or "").strip()
    except Exception:  # noqa: BLE001 — 설정 로드 실패 시 키 없음으로 정직 처리
        return ""


def _json_error(message: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"error": message, "status": status},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


def _transparent_tile() -> Response:
    return Response(
        content=TRANSPARENT_PNG,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _relay_tile(resp: httpx.Response, *, kind: str, ctx: dict[str, str]) -> Response:
    """상류 응답 → 타일/오류 변환(web 프록시와 동일 분기)."""
    if resp.status_code >= 400:
        logger.error("[vworld-tiles] %s upstream error (status=%d) %s", kind, resp.status_code, ctx)
        return _json_error(f"VWorld {kind} upstream error", 503)
    content_type = (resp.headers.get("content-type") or "").strip()
    if content_type and not content_type.lower().startswith("image/"):
        if "xml" in content_type.lower():
            body_text = resp.text
            if classify_vworld_xml(body_text) == "coverage":
                logger.warning("[vworld-tiles] %s 200+XML(coverage) → transparent tile %s", kind, ctx)
                return _transparent_tile()
            code = extract_vworld_code(body_text) or "auth/unknown"
            logger.error(
                "[vworld-tiles] %s XML exception (%s) %s body=%s",
                kind, code, ctx, body_text[:200],
            )
            return _json_error(f"VWorld {kind} returned an XML exception ({code})", 503)
        logger.error("[vworld-tiles] %s non-image body (%s) %s", kind, content_type, ctx)
        return _json_error(f"VWorld {kind} returned a non-image body", 503)
    return Response(
        content=resp.content,
        media_type=content_type or "image/png",
        headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"},
    )


@router.get("/wms", summary="VWorld WMS(연속지적도) 타일 프록시 — web 키 부재 폴백")
@limiter.limit(TILE_PROXY_LIMIT)
async def proxy_vworld_wms(request: Request) -> Response:
    key = _vworld_key()
    if not key:
        return _json_error("VWORLD_API_KEY is not configured", 503)

    # LAYERS 스머글링 방지 — 대소문자·중복 키 전 변형 수집 후 화이트리스트 전수 검증.
    requested: set[str] = set()
    for k, v in request.query_params.multi_items():
        if k.lower() != "layers":
            continue
        for token in v.split(","):
            token = token.strip().lower()  # VWorld WMS는 소문자만 인식 — 대문자 유입 정규화
            if token:
                requested.add(token)
    if not requested or not requested.issubset(set(ALLOWED_WMS_LAYERS)):
        return _json_error("Unsupported WMS layer", 400)
    canonical = ",".join(layer for layer in ALLOWED_WMS_LAYERS if layer in requested)

    # 검증된 canonical 값만 상류 전달(원본 layers/styles 변형 전부 폐기) + 키·domain 서버 주입.
    # (타입은 httpx 파라미터 시그니처와 동일하게 str|None — list 불변성 오탐 방지)
    params: list[tuple[str, str | None]] = [
        (k, v)
        for k, v in request.query_params.multi_items()
        if k.lower() not in ("layers", "styles", "key", "domain")
    ]
    params.append(("LAYERS", canonical))
    params.append(("STYLES", canonical))
    params.append(("key", key))
    params.append(("domain", VWORLD_DOMAIN))
    if not any(k.lower() == "service" for k, _ in params):
        params.append(("SERVICE", "WMS"))

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                VWORLD_WMS_BASE,
                # tuple 변환: list 불변성 탓에 정확 일치 원소타입만 허용되는 타입체커 오탐 회피
                # (tuple은 공변 — httpx 시그니처의 tuple[tuple[str, ...], ...] 분기에 안착).
                params=httpx.QueryParams(tuple(params)),
                headers={"Referer": VWORLD_REFERER},
            )
    except Exception as exc:  # noqa: BLE001 — 네트워크 오류 정직 503
        logger.error("[vworld-tiles] WMS proxy fetch failed: %s", exc)
        return _json_error(f"VWorld WMS proxy failed: {exc}", 502)
    return _relay_tile(resp, kind="WMS", ctx={"layers": canonical})


@router.get("/wmts/{layer}/{z}/{y}/{x_file}", summary="VWorld WMTS(베이스맵) 타일 프록시 — web 키 부재 폴백")
@limiter.limit(TILE_PROXY_LIMIT)
async def proxy_vworld_wmts(request: Request, layer: str, z: int, y: int, x_file: str) -> Response:
    key = _vworld_key()
    if not key:
        return _json_error("VWORLD_API_KEY is not configured", 503)

    clean_layer = layer if layer in SUPPORTED_WMTS_LAYERS else "Base"
    x = re.sub(r"\.(png|jpe?g)$", "", x_file, flags=re.IGNORECASE)
    if not x.isdigit():
        return _json_error("Unsupported WMTS tile coordinate", 400)
    # ★위성(Satellite)은 jpeg로만 서빙 — png 요청 시 FileNotFound XML(200)이 온다(web과 동일 규칙).
    ext = "jpeg" if clean_layer == "Satellite" else "png"
    target = f"{VWORLD_WMTS_BASE}/{quote(key, safe='')}/{clean_layer}/{z}/{y}/{x}.{ext}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(target, headers={"Referer": VWORLD_REFERER})
    except Exception as exc:  # noqa: BLE001
        logger.error("[vworld-tiles] WMTS proxy fetch failed: %s", exc)
        return _json_error(f"VWorld WMTS proxy failed: {exc}", 502)
    return _relay_tile(resp, kind="WMTS", ctx={"layer": clean_layer, "z": str(z), "y": str(y), "x": x})
