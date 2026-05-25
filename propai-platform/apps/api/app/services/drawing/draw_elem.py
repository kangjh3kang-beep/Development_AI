"""DrawElem 데이터클래스 + KS A ISO 13567 레이어 + 세대 평형 상수."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DrawElem:
    """도면 요소 단일 단위 (SVG/DXF 공통)."""

    id: str
    type: str  # LINE/POLYLINE/RECT/CIRCLE/ARC/TEXT/HATCH/DIM
    layer: str
    color: str | None = None
    lw: float | None = None  # 선 굵기 mm
    pts: list[dict] = field(default_factory=list)  # [{x,y}, ...]
    text: str | None = None
    h: float | None = None  # 텍스트 높이
    rot: float = 0.0  # 회전 (도)
    cx: float | None = None  # 원 중심 x
    cy: float | None = None  # 원 중심 y
    r: float | None = None  # 원 반지름
    hatch: str | None = None  # 해치 패턴
    dim_val: float | None = None  # 치수값
    props: dict = field(default_factory=dict)  # 추가 속성


# ── KS A ISO 13567 기반 22개 건축 도면 레이어 ──

LAYERS: dict[str, dict] = {
    "A-WALL": {"c": "#000000", "w": 0.50, "d": "외벽/내벽"},
    "A-WALL-INT": {"c": "#636e72", "w": 0.35, "d": "내벽(경량)"},
    "A-DOOR": {"c": "#0000FF", "w": 0.35, "d": "문"},
    "A-WIND": {"c": "#0984e3", "w": 0.35, "d": "창호"},
    "A-STRS": {"c": "#2d3436", "w": 0.25, "d": "계단"},
    "A-ELEV": {"c": "#2d3436", "w": 0.25, "d": "엘리베이터"},
    "A-CLNG": {"c": "#b2bec3", "w": 0.18, "d": "천장"},
    "A-FLOR": {"c": "#dfe6e9", "w": 0.18, "d": "바닥"},
    "A-COLS": {"c": "#2d3436", "w": 0.50, "d": "기둥"},
    "A-BEAM": {"c": "#636e72", "w": 0.35, "d": "보"},
    "A-SLAB": {"c": "#b2bec3", "w": 0.25, "d": "슬래브"},
    "A-DIMS": {"c": "#d63031", "w": 0.18, "d": "치수선"},
    "A-TEXT": {"c": "#2d3436", "w": 0.18, "d": "문자"},
    "A-ANNO": {"c": "#636e72", "w": 0.18, "d": "주석"},
    "A-SITE": {"c": "#ffeaa7", "w": 0.25, "d": "대지"},
    "A-HATC": {"c": "#dfe6e9", "w": 0.13, "d": "해치"},
    "A-FURN": {"c": "#a29bfe", "w": 0.18, "d": "가구"},
    "A-PLMB": {"c": "#00cec9", "w": 0.25, "d": "배관"},
    "A-ELEC": {"c": "#e17055", "w": 0.25, "d": "전기"},
    "A-HVAC": {"c": "#fdcb6e", "w": 0.25, "d": "냉난방"},
    "A-FIRE": {"c": "#d63031", "w": 0.25, "d": "소방"},
    "A-GRID": {"c": "#b2bec3", "w": 0.13, "d": "그리드"},
}


# ── 7개 대표 세대 평형 ──

UNIT_DIMS: dict[str, dict] = {
    "39A": {"w": 6.0, "d": 8.5, "area": 39.2},
    "49A": {"w": 6.6, "d": 9.5, "area": 49.5},
    "59A": {"w": 7.2, "d": 10.5, "area": 59.7},
    "74A": {"w": 8.4, "d": 11.0, "area": 74.4},
    "84A": {"w": 8.4, "d": 12.5, "area": 84.0},
    "102A": {"w": 9.6, "d": 13.0, "area": 102.0},
    "114A": {"w": 10.2, "d": 14.0, "area": 114.0},
}
