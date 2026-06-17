"""용도지역별 법정 용적률/건폐율 상한 — 국토계획법 시행령 제84조(건폐율)·제85조(용적률) 기준.

전국 공통 '상한'(1차출처: 시행령). 지자체 조례로 강화(하향)될 수 있어 note로 표면화(무음 단정 금지).
용도지역명 부분매칭(prposArea1Nm '제1종일반주거지역' 등). 결정론(고정 테이블).
"""
from __future__ import annotations

# {용도지역: (용적률 상한 %, 건폐율 상한 %)} — 국토계획법 시행령 상한
ZONE_LIMITS: dict[str, tuple[int, int]] = {
    "제1종전용주거지역": (100, 50),
    "제2종전용주거지역": (150, 50),
    "제1종일반주거지역": (200, 60),
    "제2종일반주거지역": (250, 60),
    "제3종일반주거지역": (300, 50),
    "준주거지역": (500, 70),
    "중심상업지역": (1500, 90),
    "일반상업지역": (1300, 80),
    "근린상업지역": (900, 70),
    "유통상업지역": (1100, 80),
    "전용공업지역": (300, 70),
    "일반공업지역": (350, 70),
    "준공업지역": (400, 70),
    "보전녹지지역": (80, 20),
    "생산녹지지역": (100, 20),
    "자연녹지지역": (100, 20),
    "보전관리지역": (80, 20),
    "생산관리지역": (80, 20),
    "계획관리지역": (100, 40),
    "농림지역": (80, 20),
    "자연환경보전지역": (80, 20),
}


def lookup_zone_limit(zone_name: str | None) -> dict | None:
    """용도지역명 → {zone_matched, far_limit_pct, bcr_limit_pct}. 매칭 실패 None."""
    if not zone_name:
        return None
    for key, (far, bcr) in ZONE_LIMITS.items():
        if key in zone_name or zone_name in key:
            return {"zone_matched": key, "far_limit_pct": far, "bcr_limit_pct": bcr}
    return None
