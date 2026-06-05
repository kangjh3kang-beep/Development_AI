"""Flagship B — 이미지융합 AVM (PoC) 서비스 본체.

원칙(정직·할루시네이션 방지):
- 항공 정사영상 취득 + cv2 가용 시 영상특징(green/built/edge)을 추출하고,
  불가 시 필지 기하·NED 지세/형상·주변 POI 밀도·접도로 프록시 특징을 구성한다.
- 융합 보정은 **상한 ±8% 제한·실험적(experimental=true)** 이며 근거 없으면 0%.
- "검증된 CNN/MAPE<x%" 류의 과장 주장은 절대 하지 않는다.

외부호출은 asyncio.wait_for로 가드하여 90초 내 응답한다. cv2 import는
try/except로 미설치 환경에서 graceful 폴백한다(무거운 ML 모델 로드 금지).
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger()

# 보정 상한(과신 방지). 영상/프록시 모두 이 범위로 클램프.
MAX_ADJUST_PCT = 8.0

# 외부 호출 가드(초). 전체는 라우터/타스크 레벨에서 빠르게 유지.
_IMG_TIMEOUT = 12.0
_GEO_TIMEOUT = 12.0
_DESK_TIMEOUT = 30.0
_PROXY_TIMEOUT = 12.0


def _clamp_pct(pct: float) -> float:
    return max(-MAX_ADJUST_PCT, min(MAX_ADJUST_PCT, round(pct, 2)))


# ──────────────────────────────────────────────────────────────────────────
# cv2 영상 특징 추출 (가용 + 이미지 취득 시)
# ──────────────────────────────────────────────────────────────────────────
def _extract_image_features(png_bytes: bytes) -> dict[str, Any] | None:
    """정사영상 PNG에서 식생/시가화/에지밀도 특징을 추출.

    cv2 미설치 시 None(프록시 폴백). numpy 기초 연산만 사용(ML 모델 미로드).
    - green_ratio: HSV 식생 마스크 비율(0~1)
    - built_ratio: 저채도·중간밝기(콘크리트/지붕) 시가화 추정 비율(0~1)
    - edge_density: Canny 에지 픽셀 비율(개발강도 프록시)
    """
    try:
        import cv2  # noqa: PLC0415  (지연 import — 미설치 graceful)
        import numpy as np  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        logger.info("cv2 미설치/불가 — 영상 특징 스킵: %s", str(e)[:120])
        return None

    try:
        arr = np.frombuffer(png_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # BGR
        if img is None or img.size == 0:
            return None
        total = float(img.shape[0] * img.shape[1])
        if total <= 0:
            return None

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

        # 식생: 녹색 계열(OpenCV H 0~179 ≈ 35~85) + 충분한 채도/밝기
        green_mask = (h >= 35) & (h <= 85) & (s >= 40) & (v >= 40)
        green_ratio = float(np.count_nonzero(green_mask)) / total

        # 시가화(콘크리트/지붕/도로): 저채도 + 중간 이상 밝기, 식생 제외
        built_mask = (s < 45) & (v >= 90) & (~green_mask)
        built_ratio = float(np.count_nonzero(built_mask)) / total

        # 에지밀도: Canny(개발강도/건물밀도 프록시)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 180)
        edge_density = float(np.count_nonzero(edges)) / total

        return {
            "green_ratio": round(green_ratio, 4),
            "built_ratio": round(built_ratio, 4),
            "edge_density": round(edge_density, 4),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("영상 특징 추출 실패 — 프록시 폴백: %s", str(e)[:150])
        return None


# ──────────────────────────────────────────────────────────────────────────
# 프록시 특징 (이미지/cv2 불가 시): 필지 기하·NED terrain·POI 밀도·접도
# ──────────────────────────────────────────────────────────────────────────
def _road_frontage_grade(road_side: str | None) -> str | None:
    """NED roadSideCodeNm → good/normal/poor 등급."""
    s = (road_side or "").strip()
    if not s:
        return None
    if any(k in s for k in ("광대", "중로", "각지")):
        return "good"
    if any(k in s for k in ("소로",)):
        return "normal"
    if any(k in s for k in ("세로", "맹지", "불")):
        return "poor"
    return "normal"


async def _build_proxy_features(
    *, pnu: str | None, lat: float | None, lon: float | None
) -> dict[str, Any]:
    """공간 컨텍스트 프록시 특징 구성(영상 미취득 시).

    - terrain: NED 토지특성 지세/형상(get_land_characteristics)
    - road_frontage: NED 도로접면 등급
    - poi_density: 주변 상권 점포 밀도(상권정보, 가용 시) 0~1 정규화
    """
    from app.services.external_api.vworld_service import VWorldService

    feats: dict[str, Any] = {
        "green_ratio": None,
        "built_ratio": None,
        "edge_density": None,
        "road_frontage": None,
        "terrain": None,
        "poi_density": None,
    }
    notes: list[str] = []

    vw = VWorldService()
    lc = None
    if pnu:
        try:
            lc = await asyncio.wait_for(
                vw.get_land_characteristics(pnu), timeout=_PROXY_TIMEOUT
            )
        except Exception as e:  # noqa: BLE001
            logger.info("프록시 토지특성 조회 실패: %s", str(e)[:120])
    if lc:
        terrain_bits = [
            b for b in (lc.get("terrain_height"), lc.get("terrain_form")) if b
        ]
        if terrain_bits:
            feats["terrain"] = " / ".join(terrain_bits)
            notes.append(f"지세·형상 {feats['terrain']}")
        feats["road_frontage"] = _road_frontage_grade(lc.get("road_side"))
        if lc.get("road_side"):
            notes.append(f"도로접면 {lc.get('road_side')}")

    # 주변 POI 밀도(상권정보) — 가용 시
    if lat and lon:
        try:
            from app.services.external_api.commercial_area_service import (
                CommercialAreaService,
            )

            ca = CommercialAreaService()
            stores = await asyncio.wait_for(
                ca.get_stores_in_radius(lat, lon, radius_m=500), timeout=_PROXY_TIMEOUT
            )
            if stores is not None:
                cnt = len(stores)
                # 반경 500m 점포수 → 0~1 정규화(800점 이상=고밀 1.0, 휴리스틱)
                feats["poi_density"] = round(min(1.0, cnt / 800.0), 4)
                notes.append(f"주변 점포 {cnt}개(반경500m)")
        except Exception as e:  # noqa: BLE001
            logger.info("프록시 POI 밀도 조회 실패: %s", str(e)[:120])

    feats["detail"] = (
        "; ".join(notes) if notes else "프록시 공간컨텍스트 데이터 제한 — 보정 보수적"
    )
    feats["source"] = "proxy"
    return feats


# ──────────────────────────────────────────────────────────────────────────
# 융합(보정): 특징 → adjustment_pct · confidence · rationale
# ──────────────────────────────────────────────────────────────────────────
def _fuse_image(feats: dict[str, Any]) -> tuple[float, float, str]:
    """영상 특징 → (adjustment_pct, confidence, rationale).

    경험적 가중치(검증된 모델 아님 — 실험적). 상한 ±8%.
    """
    pct = 0.0
    reasons: list[str] = []

    green = feats.get("green_ratio")
    built = feats.get("built_ratio")
    edge = feats.get("edge_density")

    if green is not None:
        # 식생 과다(저개발/녹지) → 소폭 하향, 적정 녹지(쾌적) → 미세 상향
        if green > 0.55:
            pct -= 4.0
            reasons.append(f"식생비율 과다({green:.0%}, 저개발·녹지) 하향")
        elif green > 0.25:
            pct += 1.0
            reasons.append(f"적정 녹지({green:.0%}, 쾌적) 소폭 상향")

    if built is not None and built > 0.45:
        pct += 3.0
        reasons.append(f"시가화율 높음({built:.0%}) 상향")
    elif built is not None and built < 0.12:
        pct -= 2.0
        reasons.append(f"시가화율 낮음({built:.0%}) 하향")

    if edge is not None and edge > 0.12:
        pct += 2.0
        reasons.append(f"에지밀도 높음({edge:.0%}, 고밀 개발강도) 상향")
    elif edge is not None and edge < 0.04:
        pct -= 1.0
        reasons.append(f"에지밀도 낮음({edge:.0%}, 저개발) 하향")

    pct = _clamp_pct(pct)
    # 신뢰도: 특징 다양성에 따라 0.5~0.7
    n = sum(1 for k in ("green_ratio", "built_ratio", "edge_density") if feats.get(k) is not None)
    confidence = round(min(0.7, 0.5 + 0.07 * n), 3) if n else 0.0
    rationale = (
        "; ".join(reasons)
        if reasons
        else "영상 특징이 중립적이어서 보정 없음(0%)"
    )
    return pct, confidence, rationale


def _fuse_proxy(feats: dict[str, Any]) -> tuple[float, float, str]:
    """프록시 특징 → (adjustment_pct, confidence, rationale). 상한 ±8%, 보수적."""
    pct = 0.0
    reasons: list[str] = []

    rf = feats.get("road_frontage")
    if rf == "good":
        pct += 3.0
        reasons.append("접도 양호(광대/중로/각지) 상향")
    elif rf == "poor":
        pct -= 4.0
        reasons.append("접도 불량(세로/맹지) 하향")

    poi = feats.get("poi_density")
    if poi is not None:
        if poi > 0.5:
            pct += 3.0
            reasons.append(f"주변 POI 고밀({poi:.0%}, 상권 활성) 상향")
        elif poi < 0.1:
            pct -= 1.0
            reasons.append(f"주변 POI 희박({poi:.0%}) 소폭 하향")

    terrain = (feats.get("terrain") or "")
    if any(k in terrain for k in ("급경사", "고지", "험준")):
        pct -= 2.0
        reasons.append("지세 불리(급경사/고지) 하향")
    elif any(k in terrain for k in ("평지",)):
        pct += 1.0
        reasons.append("지세 평지 소폭 상향")

    pct = _clamp_pct(pct)
    # 신뢰도: 프록시는 0.3~0.45
    n = sum(1 for k in ("road_frontage", "poi_density", "terrain") if feats.get(k))
    confidence = round(min(0.45, 0.30 + 0.05 * n), 3) if n else 0.30
    rationale = (
        "; ".join(reasons)
        if reasons
        else "프록시 특징이 중립적이어서 보정 없음(0%)"
    )
    return pct, confidence, rationale


# ──────────────────────────────────────────────────────────────────────────
# 메인 엔트리
# ──────────────────────────────────────────────────────────────────────────
async def analyze_avm_vision(
    *,
    address: str | None = None,
    pnu: str | None = None,
    base_value_won: float | None = None,
    base_value_per_sqm_won: float | None = None,
) -> dict[str, Any]:
    """이미지융합 AVM 분석(실험적). 계약: 11_flagshipB_contract.md.

    1) 좌표/PNU 확보(auto_zoning → geocode 폴백)
    2) 기준값(base) 미제공 시 desk_appraisal 호출
    3) 항공 정사영상 취득 시도(VWorld) → cv2 영상특징 / 불가 시 프록시 특징
    4) 융합 보정(상한 ±8%, experimental=true)
    """
    if not address and not pnu:
        # 422는 라우터에서 처리(여기 도달 전). 방어적.
        return {"ok": False, "message": "address 또는 pnu가 필요합니다."}

    sources: list[str] = []
    resolved_address = address or ""
    resolved_pnu = pnu
    coordinates: dict[str, float] | None = None

    # 1) 좌표/PNU 확보
    try:
        from app.services.zoning.auto_zoning_service import AutoZoningService

        if address:
            zoning = await asyncio.wait_for(
                AutoZoningService().analyze_by_address(address), timeout=_GEO_TIMEOUT
            )
            if zoning:
                resolved_pnu = resolved_pnu or zoning.get("pnu")
                coords = zoning.get("coordinates") or {}
                if coords.get("lat") and coords.get("lon"):
                    coordinates = {"lat": coords["lat"], "lon": coords["lon"]}
                    sources.append("VWorld 지오코딩")
    except Exception as e:  # noqa: BLE001
        logger.info("auto_zoning 좌표 확보 실패: %s", str(e)[:120])

    # 좌표 폴백: geocode 직접 / PNU만 있을 때 필지 중심
    if coordinates is None:
        from app.services.external_api.vworld_service import VWorldService

        vw = VWorldService()
        try:
            if address:
                geo = await asyncio.wait_for(
                    vw.geocode_address(address), timeout=_GEO_TIMEOUT
                )
                if geo and geo.get("lat") and geo.get("lon"):
                    coordinates = {"lat": geo["lat"], "lon": geo["lon"]}
                    resolved_pnu = resolved_pnu or geo.get("pnu")
                    sources.append("VWorld 지오코딩")
        except Exception as e:  # noqa: BLE001
            logger.info("geocode 폴백 실패: %s", str(e)[:120])

    if coordinates is None and resolved_pnu:
        # PNU 필지 기하 중심으로 좌표 추정
        try:
            from app.services.external_api.vworld_service import VWorldService

            parcel = await asyncio.wait_for(
                VWorldService().get_parcel_by_pnu(resolved_pnu), timeout=_GEO_TIMEOUT
            )
            geom = (parcel or {}).get("geometry") or {}
            c = geom.get("coordinates")
            pt = c
            while isinstance(pt, list) and pt and isinstance(pt[0], list):
                pt = pt[0]
            if isinstance(pt, list) and len(pt) >= 2:
                coordinates = {"lat": float(pt[1]), "lon": float(pt[0])}
                sources.append("VWorld 필지 기하")
        except Exception as e:  # noqa: BLE001
            logger.info("필지 중심 좌표 추정 실패: %s", str(e)[:120])

    # 2) 기준값 확보(미제공 시 desk_appraisal)
    base_won = base_value_won
    base_per_sqm = base_value_per_sqm_won
    if base_won is None and base_per_sqm is None and (resolved_pnu or address):
        try:
            from app.services.land_intelligence.desk_appraisal_service import (
                desk_appraisal,
            )

            desk = await asyncio.wait_for(
                desk_appraisal(pnu=resolved_pnu, address=address or ""),
                timeout=_DESK_TIMEOUT,
            )
            if isinstance(desk, dict) and desk.get("ok"):
                base_won = desk.get("appraised_total_won")
                base_per_sqm = desk.get("appraised_price_per_sqm")
                resolved_pnu = resolved_pnu or desk.get("pnu")
                sources.append("탁상감정(desk_appraisal)")
        except Exception as e:  # noqa: BLE001
            logger.info("desk_appraisal 기준값 산출 실패: %s", str(e)[:150])

    # 기준값·좌표 모두 불가 → ok:false (빈결과 금지)
    if base_won is None and base_per_sqm is None and coordinates is None:
        return {
            "ok": False,
            "message": "기준값(공시지가/감정)과 좌표를 모두 확인할 수 없습니다. "
            "PNU 또는 base_value를 입력하세요.",
        }

    # 3) 항공 정사영상 취득 시도
    image_block: dict[str, Any] = {
        "available": False,
        "source": None,
        "bbox": None,
        "thumbnail_url": None,
    }
    img_feats: dict[str, Any] | None = None
    png_bytes: bytes | None = None
    if coordinates:
        try:
            from app.services.external_api.vworld_service import VWorldService

            acq = await asyncio.wait_for(
                VWorldService().get_aerial_image(
                    coordinates["lat"], coordinates["lon"], zoom=18
                ),
                timeout=_IMG_TIMEOUT,
            )
            if acq and acq.get("bytes"):
                png_bytes = acq["bytes"]
                image_block = {
                    "available": True,
                    "source": acq.get("source"),
                    "bbox": None,  # static getmap은 center+zoom 기반(정확 bbox 미제공)
                    "center": acq.get("center"),
                    "zoom": acq.get("zoom"),
                    "thumbnail_url": None,  # 바이트 미보관(PoC) — 프론트는 동일 좌표 재요청 가능
                }
                sources.append("VWorld 항공 정사영상")
        except Exception as e:  # noqa: BLE001
            logger.info("정사영상 취득 실패: %s", str(e)[:120])

    # 4) 특징 추출: 영상(cv2) → 프록시 폴백
    note = ""
    if png_bytes:
        img_feats = _extract_image_features(png_bytes)
    if img_feats is not None:
        features = {
            "source": "image",
            "green_ratio": img_feats.get("green_ratio"),
            "built_ratio": img_feats.get("built_ratio"),
            "edge_density": img_feats.get("edge_density"),
            "road_frontage": None,
            "terrain": None,
            "poi_density": None,
            "detail": "VWorld 항공 정사영상 cv2 분석(식생·시가화·에지밀도)",
        }
        adj_pct, confidence, rationale = _fuse_image(features)
    else:
        if png_bytes is not None:
            note = "영상은 취득했으나 cv2 미가용/디코딩 실패 — 프록시 특징으로 폴백."
        elif image_block["available"]:
            note = "영상 취득 후 특징추출 불가 — 프록시 폴백."
        else:
            note = "항공 정사영상 미취득(키 권한/네트워크) — 프록시 공간컨텍스트로 폴백."
        lat = coordinates["lat"] if coordinates else None
        lon = coordinates["lon"] if coordinates else None
        features = await _build_proxy_features(pnu=resolved_pnu, lat=lat, lon=lon)
        # 계약 키 보장
        features.setdefault("source", "proxy")
        adj_pct, confidence, rationale = _fuse_proxy(features)

    # base가 없으면 보정 적용 불가(과장 금지) → pct는 산출하되 adjusted는 None
    adjusted_value_won: int | None = None
    if base_won is not None:
        adjusted_value_won = int(round(float(base_won) * (1 + adj_pct / 100.0)))

    return {
        "ok": True,
        "address": resolved_address,
        "pnu": resolved_pnu,
        "coordinates": coordinates,
        "image": image_block,
        "features": features,
        "base_value_won": int(base_won) if base_won is not None else None,
        "base_value_per_sqm_won": int(base_per_sqm)
        if base_per_sqm is not None
        else None,
        "adjustment_pct": adj_pct,
        "adjusted_value_won": adjusted_value_won,
        "confidence": confidence,
        "rationale": rationale,
        "experimental": True,
        "sources": sources or ["입력값"],
        "note": note
        or "실험적(EXPERIMENTAL) 영상융합 보정. 검증된 감정평가가 아닙니다.",
    }
