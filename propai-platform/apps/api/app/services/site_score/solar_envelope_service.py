"""한국 정북일조 빌더블 인벨로프(베팅 D) — 실제 건축가능 최대 볼륨·층수 산정.

건축법 시행령 제86조(정북방향 일조 확보 이격):
 - 전용/일반주거지역: 높이 9m 이하 부분은 정북 인접대지경계에서 1.5m 이상,
   9m 초과 부분은 그 부분 높이의 1/2 이상 이격.  → 거리 d에서 최대높이 H(d)=max(9, 2·(d−1.5)+9)? 보수적으로 H≤2d.
정북사선을 남북깊이에 대해 스트립 적분해 '일조로 실제 지을 수 있는' 최대 연면적을 구하고,
용적률(FAR) 한도와 비교해 '바인딩 제약'과 '일조 손실률'을 제시한다.

한계(v1 근사): 직사각형 대지 가정(W×D, 정북=깊이방향), 단일 매스, 측면이격 간이.
글로벌 툴(Forma/Zoneomics)이 모르는 '한국 정북일조'를 정량화하는 것이 핵심 차별점.
향후: VWorld 실측 PARCEL 폴리곤(shapely)·도로사선·인동간격·IFC 결합으로 정밀화.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.permit.building_code_rules import ZONE_DEFAULTS

# 정북일조 적용 용도지역(전용/일반주거). 준주거·상업·공업은 통상 미적용/완화.
_NORTH_LIGHT_ZONES = ("전용주거", "일반주거", "1종", "2종", "3종", "제1종", "제2종", "제3종")


def _zone_limits(zone: str) -> dict[str, Any]:
    for k, v in ZONE_DEFAULTS.items():
        if k in (zone or "") or (zone or "") in k:
            return v
    return {"max_bcr": 60, "max_far": 250, "max_height": 0}


def compute_buildable_envelope(
    *,
    land_area_sqm: float,
    zone: str = "",
    land_width_m: float | None = None,
    land_depth_m: float | None = None,
    floor_height_m: float = 3.0,
    bcr_limit_pct: float | None = None,
    far_limit_pct: float | None = None,
    side_setback_m: float = 0.5,
) -> dict[str, Any]:
    """정북일조 인벨로프 기반 최대 건축가능 연면적·층수·볼륨과 용적률 대비 손실 산정."""
    if land_area_sqm <= 0:
        return {"error": "대지면적이 필요합니다."}

    lim = _zone_limits(zone)
    bcr = (bcr_limit_pct if bcr_limit_pct is not None else lim.get("max_bcr", 60)) / 100.0
    far = (far_limit_pct if far_limit_pct is not None else lim.get("max_far", 250)) / 100.0
    fh = max(2.4, floor_height_m)

    # 대지 치수: 미입력 시 정사각형 가정(정북=깊이 D)
    if not land_width_m or not land_depth_m:
        side = math.sqrt(land_area_sqm)
        W = land_width_m or side
        D = land_depth_m or side
    else:
        W, D = land_width_m, land_depth_m

    far_gfa = land_area_sqm * far               # 용적률 허용 연면적
    bcr_footprint = land_area_sqm * bcr          # 건폐율 허용 1층 바닥면적

    applies = any(k in (zone or "") for k in _NORTH_LIGHT_ZONES)

    if not applies:
        # 정북일조 미적용(준주거·상업 등) → 용적률·건폐율로 층수 추정
        floors = max(1, round(far / bcr)) if bcr > 0 else 1
        return {
            "applies_north_light": False,
            "zone": zone, "bcr_pct": round(bcr * 100, 1), "far_pct": round(far * 100, 1),
            "far_gfa_sqm": round(far_gfa), "envelope_gfa_sqm": round(far_gfa),
            "effective_gfa_sqm": round(far_gfa), "binding": "용적률",
            "daylight_loss_pct": 0.0,
            "max_height_m": round(floors * fh, 1), "max_floors": floors,
            "note": "정북일조 미적용 용도지역 — 용적률/건폐율이 한도. (정밀 높이는 가로구역 최고높이 별도 확인)",
        }

    # ── 정북일조 스트립 적분 ──
    usable_W = max(0.0, W - 2 * side_setback_m)
    strips = 200
    dz = D / strips
    envelope_volume = 0.0
    max_h = 0.0
    for i in range(strips):
        d = (i + 0.5) * dz  # 정북 경계로부터 거리
        if d < 1.5:
            h = 0.0
        else:
            # 9m 초과는 H/2 이격 → H ≤ 2d (보수적). 9m 이하는 1.5m 이격으로 허용.
            h = max(9.0, 2.0 * d)
        max_h = max(max_h, h)
        envelope_volume += usable_W * dz * h

    # 인벨로프 연면적(전부 채움 가정) = 볼륨/층고. 건폐율로 층당 바닥 상한 반영(개략).
    envelope_gfa = envelope_volume / fh
    effective_gfa = min(envelope_gfa, far_gfa)
    binding = "정북일조" if envelope_gfa < far_gfa else "용적률"
    loss = max(0.0, 1 - envelope_gfa / far_gfa) * 100 if far_gfa > 0 else 0.0
    # 현실 층수: 유효 연면적 ÷ 건폐율 바닥(전층 동일 가정 근사)
    realistic_floors = max(1, round(effective_gfa / bcr_footprint)) if bcr_footprint > 0 else 1
    daylight_ceiling_floors = max(1, int(max_h / fh))

    return {
        "applies_north_light": True,
        "zone": zone, "bcr_pct": round(bcr * 100, 1), "far_pct": round(far * 100, 1),
        "lot_width_m": round(W, 1), "lot_depth_m": round(D, 1),
        "far_gfa_sqm": round(far_gfa),
        "envelope_gfa_sqm": round(envelope_gfa),
        "effective_gfa_sqm": round(effective_gfa),
        "binding": binding,
        "daylight_loss_pct": round(loss, 1),
        "buildable_volume_m3": round(envelope_volume),
        "daylight_ceiling_m": round(max_h, 1),            # 정북일조 사선 최고선
        "daylight_ceiling_floors": daylight_ceiling_floors,
        "max_floors": realistic_floors,                    # 용적률·건폐율 기준 현실 층수
        "max_height_m": round(realistic_floors * fh, 1),
        "bcr_footprint_sqm": round(bcr_footprint),
        "note": (
            "정북일조 사선(9m↓ 1.5m·9m↑ H/2 이격)을 남북깊이 적분한 최대 건축가능 연면적. "
            "직사각형 대지 근사(v1) — 부정형 필지는 VWorld 폴리곤 정밀화 예정."
            + (f" 일조로 용적률 대비 약 {round(loss,1)}% 건축면적 손실." if binding == "정북일조" else " 용적률이 한도(일조 여유).")
        ),
    }
