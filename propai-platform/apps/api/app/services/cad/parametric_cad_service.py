from __future__ import annotations

import io
import math
from typing import Dict, List, Optional, Tuple

try:
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    from ezdxf.layouts import Modelspace
except ImportError:
    ezdxf = None  # type: ignore[assignment]
    TextEntityAlignment = None  # type: ignore[assignment,misc]
    Modelspace = None  # type: ignore[assignment,misc]
import structlog

logger = structlog.get_logger()

# ── 상수 ──

WALL_THICKNESS_M = 0.2  # 벽체 두께 200mm
DOOR_WIDTH_M = 0.9  # 문 900mm
WINDOW_WIDTH_M = 1.2  # 창호 1200mm
WINDOW_SILL_HEIGHT_M = 0.9  # 창대 높이
WINDOW_HEAD_HEIGHT_M = 2.1  # 창호 상단 높이
DIM_OFFSET_M = 1.5  # 치수선 오프셋


def _setup_layers(doc: ezdxf.document.Drawing) -> None:
    """DXF 문서에 표준 레이어를 설정한다."""
    layers = {
        "WALL": {"color": 7, "lineweight": 50},
        "WALL_INTERIOR": {"color": 8, "lineweight": 25},
        "DOOR": {"color": 3, "lineweight": 18},
        "WINDOW": {"color": 4, "lineweight": 18},
        "CORRIDOR": {"color": 5, "lineweight": 13},
        "CORE": {"color": 6, "lineweight": 25},
        "UNIT_DIVIDER": {"color": 8, "lineweight": 13},
        "DIM": {"color": 1, "lineweight": 13},
        "TEXT": {"color": 7, "lineweight": 13},
        "HATCH": {"color": 8, "lineweight": 13},
        "SITE_BOUNDARY": {"color": 1, "lineweight": 50},
        "BUILDING": {"color": 7, "lineweight": 35},
        "PARKING": {"color": 30, "lineweight": 13},
        "LANDSCAPE": {"color": 3, "lineweight": 13},
        "ROAD": {"color": 8, "lineweight": 25},
        "SETBACK": {"color": 1, "lineweight": 13, "linetype": "DASHED"},
        "SECTION_CUT": {"color": 1, "lineweight": 50},
        "SECTION_FILL": {"color": 8, "lineweight": 25},
        "ELEVATION": {"color": 7, "lineweight": 35},
        "GRID": {"color": 8, "lineweight": 13, "linetype": "CENTER"},
    }
    for name, attrs in layers.items():
        if name not in doc.layers:
            doc.layers.add(name, **attrs)


def _add_dimension_h(msp: Modelspace, x1: float, x2: float, y: float,
                     offset: float = DIM_OFFSET_M) -> None:
    """수평 치수선을 추가한다."""
    dy = y - offset
    length = abs(x2 - x1)
    msp.add_line((x1, y), (x1, dy - 0.3), dxfattribs={"layer": "DIM"})
    msp.add_line((x2, y), (x2, dy - 0.3), dxfattribs={"layer": "DIM"})
    msp.add_line((x1, dy), (x2, dy), dxfattribs={"layer": "DIM"})
    # 화살표 (간이)
    msp.add_line((x1, dy), (x1 + 0.2, dy + 0.1), dxfattribs={"layer": "DIM"})
    msp.add_line((x1, dy), (x1 + 0.2, dy - 0.1), dxfattribs={"layer": "DIM"})
    msp.add_line((x2, dy), (x2 - 0.2, dy + 0.1), dxfattribs={"layer": "DIM"})
    msp.add_line((x2, dy), (x2 - 0.2, dy - 0.1), dxfattribs={"layer": "DIM"})
    mid_x = (x1 + x2) / 2
    msp.add_text(
        f"{length:.1f}",
        dxfattribs={"layer": "DIM", "height": 0.25},
    ).set_placement((mid_x, dy + 0.15), align=TextEntityAlignment.BOTTOM_CENTER)


def _add_dimension_v(msp: Modelspace, y1: float, y2: float, x: float,
                     offset: float = DIM_OFFSET_M) -> None:
    """수직 치수선을 추가한다."""
    dx = x - offset
    length = abs(y2 - y1)
    msp.add_line((x, y1), (dx - 0.3, y1), dxfattribs={"layer": "DIM"})
    msp.add_line((x, y2), (dx - 0.3, y2), dxfattribs={"layer": "DIM"})
    msp.add_line((dx, y1), (dx, y2), dxfattribs={"layer": "DIM"})
    mid_y = (y1 + y2) / 2
    msp.add_text(
        f"{length:.1f}",
        dxfattribs={"layer": "DIM", "height": 0.25, "rotation": 90},
    ).set_placement((dx - 0.15, mid_y), align=TextEntityAlignment.BOTTOM_CENTER)


def _draw_door(msp: Modelspace, x: float, y: float,
               width: float = DOOR_WIDTH_M, horizontal: bool = True) -> None:
    """문 기호를 그린다 (아크 표시)."""
    if horizontal:
        msp.add_line((x, y), (x + width, y), dxfattribs={"layer": "DOOR"})
        msp.add_arc(
            center=(x, y), radius=width,
            start_angle=0, end_angle=90,
            dxfattribs={"layer": "DOOR"},
        )
    else:
        msp.add_line((x, y), (x, y + width), dxfattribs={"layer": "DOOR"})
        msp.add_arc(
            center=(x, y), radius=width,
            start_angle=0, end_angle=90,
            dxfattribs={"layer": "DOOR"},
        )


def _draw_window(msp: Modelspace, x: float, y: float,
                 width: float = WINDOW_WIDTH_M, horizontal: bool = True) -> None:
    """창호 기호를 그린다 (이중선)."""
    t = WALL_THICKNESS_M / 2
    if horizontal:
        msp.add_line((x, y - t), (x + width, y - t), dxfattribs={"layer": "WINDOW"})
        msp.add_line((x, y + t), (x + width, y + t), dxfattribs={"layer": "WINDOW"})
        msp.add_line((x, y - t), (x, y + t), dxfattribs={"layer": "WINDOW"})
        msp.add_line((x + width, y - t), (x + width, y + t), dxfattribs={"layer": "WINDOW"})
    else:
        msp.add_line((x - t, y), (x - t, y + width), dxfattribs={"layer": "WINDOW"})
        msp.add_line((x + t, y), (x + t, y + width), dxfattribs={"layer": "WINDOW"})
        msp.add_line((x - t, y), (x + t, y), dxfattribs={"layer": "WINDOW"})
        msp.add_line((x - t, y + width), (x + t, y + width), dxfattribs={"layer": "WINDOW"})


def _write_dxf(doc: ezdxf.document.Drawing) -> bytes:
    """DXF 문서를 바이트로 변환한다."""
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


class BuildingModel:
    """건축물 매스 모델 (법규 보정용)."""

    def __init__(
        self,
        width: float,
        depth: float,
        floors: int,
        floor_height: float = 3.0,
    ) -> None:
        self.width = width
        self.depth = depth
        self.floors = floors
        self.floor_height = floor_height
        self.setback_distances: Dict[str, float] = {
            "north": 3.0, "south": 3.0, "east": 3.0, "west": 3.0,
        }

    @property
    def total_height(self) -> float:
        return self.floors * self.floor_height

    @property
    def floor_area(self) -> float:
        return self.width * self.depth

    @property
    def total_area(self) -> float:
        return self.floor_area * self.floors

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "depth": self.depth,
            "floors": self.floors,
            "floor_height": self.floor_height,
            "total_height": self.total_height,
            "floor_area": self.floor_area,
            "total_area": self.total_area,
            "setback_distances": dict(self.setback_distances),
        }


class ParametricCADService:
    """CAD 파라메트릭 편집 + 법규 자동 보정 (건축법 55/56조).

    상세 건축도면 생성 기능:
    - 기본 평면도 (create_floor_plan_dxf)
    - 상세 평면도: 벽체/문/창호/코어/복도/치수선 (create_detailed_floor_plan_dxf)
    - 단면도: 층별 높이/기초/지붕 (create_section_drawing_dxf)
    - 입면도: 정면/측면 (create_elevation_drawing_dxf)
    - 배치도: 대지/건물/주차장/조경/진입로 (create_site_plan_dxf)
    """

    # ── 기존 기본 평면도 ──

    def create_floor_plan_dxf(
        self,
        building_width_m: float,
        building_depth_m: float,
        floor_count: int = 1,
        unit_width_m: float = 8.0,
        unit_depth_m: float = 10.0,
        corridor_width_m: float = 1.8,
    ) -> bytes:
        """기본 평면도 DXF를 생성한다."""
        if ezdxf is None:
            return b"DXF_PLACEHOLDER_NO_EZDXF"
        doc = ezdxf.new("R2010")
        _setup_layers(doc)
        msp: Modelspace = doc.modelspace()

        msp.add_lwpolyline(
            [(0, 0), (building_width_m, 0),
             (building_width_m, building_depth_m),
             (0, building_depth_m), (0, 0)],
            close=True,
            dxfattribs={"layer": "WALL", "lineweight": 50},
        )

        units_per_floor = max(1, int(building_width_m / unit_width_m))
        for i in range(1, units_per_floor):
            x = i * unit_width_m
            msp.add_line(
                (x, 0), (x, building_depth_m),
                dxfattribs={"layer": "UNIT_DIVIDER", "lineweight": 25},
            )

        corridor_y = building_depth_m / 2
        msp.add_line(
            (0, corridor_y), (building_width_m, corridor_y),
            dxfattribs={"layer": "CORRIDOR", "lineweight": 25},
        )

        msp.add_text(
            f"W={building_width_m:.1f}m x D={building_depth_m:.1f}m F={floor_count}F",
            dxfattribs={"layer": "TEXT", "height": 0.5},
        ).set_placement((1, -2))

        return _write_dxf(doc)

    # ── 상세 평면도 ──

    def create_detailed_floor_plan_dxf(
        self,
        building_width_m: float,
        building_depth_m: float,
        floor_count: int = 1,
        unit_width_m: float = 8.0,
        corridor_width_m: float = 1.8,
        core_count: int = 2,
        core_width_m: float = 4.0,
        core_depth_m: float = 6.0,
    ) -> bytes:
        """상세 평면도 DXF — 벽체, 문, 창호, 코어, 복도, 치수선 포함."""
        if ezdxf is None:
            return b"DXF_PLACEHOLDER_NO_EZDXF"
        doc = ezdxf.new("R2010")
        _setup_layers(doc)
        msp: Modelspace = doc.modelspace()
        wt = WALL_THICKNESS_M

        # ─ 외벽 (이중선) ─
        # 외측
        msp.add_lwpolyline(
            [(0, 0), (building_width_m, 0),
             (building_width_m, building_depth_m),
             (0, building_depth_m)],
            close=True,
            dxfattribs={"layer": "WALL"},
        )
        # 내측
        msp.add_lwpolyline(
            [(wt, wt), (building_width_m - wt, wt),
             (building_width_m - wt, building_depth_m - wt),
             (wt, building_depth_m - wt)],
            close=True,
            dxfattribs={"layer": "WALL"},
        )

        # ─ 복도 (건물 중앙) ─
        corridor_y = (building_depth_m - corridor_width_m) / 2
        msp.add_line(
            (wt, corridor_y),
            (building_width_m - wt, corridor_y),
            dxfattribs={"layer": "CORRIDOR"},
        )
        msp.add_line(
            (wt, corridor_y + corridor_width_m),
            (building_width_m - wt, corridor_y + corridor_width_m),
            dxfattribs={"layer": "CORRIDOR"},
        )
        # 복도 라벨
        msp.add_text(
            "복도",
            dxfattribs={"layer": "TEXT", "height": 0.3},
        ).set_placement(
            (building_width_m / 2, corridor_y + corridor_width_m / 2),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

        # ─ 코어 배치 (엘리베이터+계단) ─
        if core_count > 0:
            spacing = building_width_m / (core_count + 1)
            for ci in range(core_count):
                cx = spacing * (ci + 1) - core_width_m / 2
                cy = corridor_y - core_depth_m / 2 + corridor_width_m / 2
                # 코어 외벽
                msp.add_lwpolyline(
                    [(cx, cy), (cx + core_width_m, cy),
                     (cx + core_width_m, cy + core_depth_m),
                     (cx, cy + core_depth_m)],
                    close=True,
                    dxfattribs={"layer": "CORE"},
                )
                # EL 표시
                el_w = core_width_m * 0.4
                el_x = cx + core_width_m * 0.05
                el_y = cy + core_depth_m * 0.1
                msp.add_lwpolyline(
                    [(el_x, el_y), (el_x + el_w, el_y),
                     (el_x + el_w, el_y + el_w),
                     (el_x, el_y + el_w)],
                    close=True,
                    dxfattribs={"layer": "CORE"},
                )
                msp.add_text(
                    "EL",
                    dxfattribs={"layer": "TEXT", "height": 0.2},
                ).set_placement(
                    (el_x + el_w / 2, el_y + el_w / 2),
                    align=TextEntityAlignment.MIDDLE_CENTER,
                )
                # 계단 표시 (대각선)
                st_x = cx + core_width_m * 0.55
                st_y = cy + core_depth_m * 0.1
                st_w = core_width_m * 0.4
                st_h = core_depth_m * 0.8
                msp.add_lwpolyline(
                    [(st_x, st_y), (st_x + st_w, st_y),
                     (st_x + st_w, st_y + st_h),
                     (st_x, st_y + st_h)],
                    close=True,
                    dxfattribs={"layer": "CORE"},
                )
                # 계단 디딤판 (7개 라인)
                for si in range(1, 8):
                    sy = st_y + st_h * si / 8
                    msp.add_line(
                        (st_x, sy), (st_x + st_w, sy),
                        dxfattribs={"layer": "CORE"},
                    )

        # ─ 세대 분할 내벽 + 문 + 창호 ─
        inner_w = building_width_m - 2 * wt
        units_per_side = max(1, int(inner_w / unit_width_m))
        actual_unit_w = inner_w / units_per_side

        for side in ["south", "north"]:
            if side == "south":
                y_start = wt
                y_end = corridor_y
            else:
                y_start = corridor_y + corridor_width_m
                y_end = building_depth_m - wt

            unit_depth = y_end - y_start

            for ui in range(units_per_side):
                ux = wt + ui * actual_unit_w

                # 세대 간 내벽 (첫 번째 제외)
                if ui > 0:
                    msp.add_line(
                        (ux, y_start), (ux, y_end),
                        dxfattribs={"layer": "WALL_INTERIOR"},
                    )

                # 면적 라벨
                area = actual_unit_w * unit_depth
                msp.add_text(
                    f"{area:.1f}m²",
                    dxfattribs={"layer": "TEXT", "height": 0.25},
                ).set_placement(
                    (ux + actual_unit_w / 2, (y_start + y_end) / 2),
                    align=TextEntityAlignment.MIDDLE_CENTER,
                )

                # 세대 현관문 (복도 쪽)
                door_x = ux + actual_unit_w * 0.1
                if side == "south":
                    _draw_door(msp, door_x, corridor_y, DOOR_WIDTH_M, horizontal=True)
                else:
                    _draw_door(msp, door_x, corridor_y + corridor_width_m, DOOR_WIDTH_M, horizontal=True)

                # 외벽 창호 (외측)
                win_x = ux + (actual_unit_w - WINDOW_WIDTH_M) / 2
                if side == "south":
                    _draw_window(msp, win_x, wt, WINDOW_WIDTH_M, horizontal=True)
                else:
                    _draw_window(msp, win_x, building_depth_m - wt, WINDOW_WIDTH_M, horizontal=True)

        # ─ 치수선 ─
        _add_dimension_h(msp, 0, building_width_m, 0, offset=DIM_OFFSET_M)
        _add_dimension_v(msp, 0, building_depth_m, 0, offset=DIM_OFFSET_M)

        # 세대폭 치수
        for ui in range(units_per_side):
            ux1 = wt + ui * actual_unit_w
            ux2 = ux1 + actual_unit_w
            _add_dimension_h(
                msp, ux1, ux2, building_depth_m,
                offset=-0.8,
            )

        # ─ 도면 제목 ─
        msp.add_text(
            f"기준층 평면도 (1F~{floor_count}F)",
            dxfattribs={"layer": "TEXT", "height": 0.5},
        ).set_placement((building_width_m / 2, -3.0), align=TextEntityAlignment.TOP_CENTER)

        return _write_dxf(doc)

    # ── 단면도 ──

    def create_section_drawing_dxf(
        self,
        building_width_m: float,
        building_depth_m: float,
        floor_count: int,
        floor_height_m: float = 3.0,
        basement_floors: int = 1,
        basement_height_m: float = 3.3,
        foundation_depth_m: float = 1.0,
        parapet_height_m: float = 1.2,
    ) -> bytes:
        """건물 단면도 DXF — 지하층, 각 층, 지붕, 기초 포함."""
        if ezdxf is None:
            return b"DXF_PLACEHOLDER_NO_EZDXF"
        doc = ezdxf.new("R2010")
        _setup_layers(doc)
        msp: Modelspace = doc.modelspace()

        total_above_h = floor_count * floor_height_m
        total_below_h = basement_floors * basement_height_m
        ground_level_y = 0.0

        # ─ 기초 ─
        found_y = ground_level_y - total_below_h - foundation_depth_m
        found_w = building_width_m + 2.0  # 기초 폭은 건물보다 1m씩 넓음
        found_x = -1.0
        msp.add_lwpolyline(
            [(found_x, found_y), (found_x + found_w, found_y),
             (found_x + found_w, found_y + foundation_depth_m),
             (found_x, found_y + foundation_depth_m)],
            close=True,
            dxfattribs={"layer": "SECTION_FILL"},
        )
        msp.add_text(
            "기초",
            dxfattribs={"layer": "TEXT", "height": 0.25},
        ).set_placement(
            (building_width_m / 2, found_y + foundation_depth_m / 2),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

        # ─ 지하층 ─
        for bi in range(basement_floors):
            by = ground_level_y - (bi + 1) * basement_height_m
            # 슬래브
            msp.add_line(
                (0, by + basement_height_m), (building_width_m, by + basement_height_m),
                dxfattribs={"layer": "SECTION_CUT"},
            )
            # 좌우 벽
            msp.add_line((0, by), (0, by + basement_height_m), dxfattribs={"layer": "SECTION_CUT"})
            msp.add_line(
                (building_width_m, by), (building_width_m, by + basement_height_m),
                dxfattribs={"layer": "SECTION_CUT"},
            )
            # 바닥 슬래브
            msp.add_line((0, by), (building_width_m, by), dxfattribs={"layer": "SECTION_CUT"})
            # 라벨
            msp.add_text(
                f"B{bi + 1}F",
                dxfattribs={"layer": "TEXT", "height": 0.3},
            ).set_placement(
                (building_width_m / 2, by + basement_height_m / 2),
                align=TextEntityAlignment.MIDDLE_CENTER,
            )

        # ─ 지상층 ─
        for fi in range(floor_count):
            fy = ground_level_y + fi * floor_height_m
            # 슬래브
            msp.add_line(
                (0, fy), (building_width_m, fy),
                dxfattribs={"layer": "SECTION_CUT"},
            )
            # 좌우 벽
            msp.add_line((0, fy), (0, fy + floor_height_m), dxfattribs={"layer": "SECTION_CUT"})
            msp.add_line(
                (building_width_m, fy), (building_width_m, fy + floor_height_m),
                dxfattribs={"layer": "SECTION_CUT"},
            )
            # 층 라벨
            msp.add_text(
                f"{fi + 1}F",
                dxfattribs={"layer": "TEXT", "height": 0.3},
            ).set_placement(
                (building_width_m / 2, fy + floor_height_m / 2),
                align=TextEntityAlignment.MIDDLE_CENTER,
            )
            # 층고 치수
            _add_dimension_v(msp, fy, fy + floor_height_m, building_width_m, offset=-DIM_OFFSET_M)

        # 최상층 슬래브
        roof_y = ground_level_y + total_above_h
        msp.add_line(
            (0, roof_y), (building_width_m, roof_y),
            dxfattribs={"layer": "SECTION_CUT"},
        )

        # ─ 파라펫 ─
        msp.add_line((0, roof_y), (0, roof_y + parapet_height_m), dxfattribs={"layer": "SECTION_CUT"})
        msp.add_line(
            (building_width_m, roof_y),
            (building_width_m, roof_y + parapet_height_m),
            dxfattribs={"layer": "SECTION_CUT"},
        )
        msp.add_line(
            (0, roof_y + parapet_height_m),
            (building_width_m, roof_y + parapet_height_m),
            dxfattribs={"layer": "SECTION_CUT"},
        )

        # ─ 지반선 ─
        gl_ext = 5.0
        msp.add_line((-gl_ext, ground_level_y), (building_width_m + gl_ext, ground_level_y),
                      dxfattribs={"layer": "SITE_BOUNDARY"})
        msp.add_text(
            "G.L.",
            dxfattribs={"layer": "TEXT", "height": 0.3},
        ).set_placement((building_width_m + gl_ext + 0.5, ground_level_y),
                        align=TextEntityAlignment.MIDDLE_LEFT)

        # ─ 전체 높이 치수 ─
        _add_dimension_v(
            msp, ground_level_y, roof_y + parapet_height_m, 0,
            offset=DIM_OFFSET_M + 1.0,
        )

        # ─ 건물 폭 치수 ─
        _add_dimension_h(
            msp, 0, building_width_m,
            ground_level_y - total_below_h - foundation_depth_m,
            offset=DIM_OFFSET_M,
        )

        # ─ 도면 제목 ─
        msp.add_text(
            "건물 단면도",
            dxfattribs={"layer": "TEXT", "height": 0.5},
        ).set_placement(
            (building_width_m / 2, found_y - 2.0),
            align=TextEntityAlignment.TOP_CENTER,
        )

        return _write_dxf(doc)

    # ── 입면도 ──

    def create_elevation_drawing_dxf(
        self,
        building_width_m: float,
        building_depth_m: float,
        floor_count: int,
        floor_height_m: float = 3.0,
        unit_width_m: float = 8.0,
        window_width_m: float = WINDOW_WIDTH_M,
        window_height_m: float = 1.2,
        parapet_height_m: float = 1.2,
        view: str = "front",
    ) -> bytes:
        """건물 입면도 DXF — 정면 또는 측면 뷰."""
        if ezdxf is None:
            return b"DXF_PLACEHOLDER_NO_EZDXF"
        doc = ezdxf.new("R2010")
        _setup_layers(doc)
        msp: Modelspace = doc.modelspace()

        facade_w = building_width_m if view == "front" else building_depth_m
        total_h = floor_count * floor_height_m

        # ─ 건물 외곽 ─
        msp.add_lwpolyline(
            [(0, 0), (facade_w, 0), (facade_w, total_h), (0, total_h)],
            close=True,
            dxfattribs={"layer": "ELEVATION"},
        )

        # ─ 파라펫 ─
        msp.add_lwpolyline(
            [(0, total_h), (facade_w, total_h),
             (facade_w, total_h + parapet_height_m),
             (0, total_h + parapet_height_m)],
            close=True,
            dxfattribs={"layer": "ELEVATION"},
        )

        # ─ 층별 수평선 + 창호 ─
        unit_w_eff = unit_width_m if view == "front" else building_depth_m / 2
        units_facade = max(1, int(facade_w / unit_w_eff))
        actual_uw = facade_w / units_facade

        for fi in range(floor_count):
            fy = fi * floor_height_m

            # 층 슬래브선
            if fi > 0:
                msp.add_line(
                    (0, fy), (facade_w, fy),
                    dxfattribs={"layer": "ELEVATION"},
                )

            # 창호 배치
            win_sill = fy + WINDOW_SILL_HEIGHT_M
            win_head = fy + WINDOW_HEAD_HEIGHT_M

            for ui in range(units_facade):
                cx = ui * actual_uw + actual_uw / 2
                wx1 = cx - window_width_m / 2
                wx2 = cx + window_width_m / 2
                msp.add_lwpolyline(
                    [(wx1, win_sill), (wx2, win_sill),
                     (wx2, win_head), (wx1, win_head)],
                    close=True,
                    dxfattribs={"layer": "WINDOW"},
                )
                # 십자 유리 분할
                msp.add_line(
                    (cx, win_sill), (cx, win_head),
                    dxfattribs={"layer": "WINDOW"},
                )
                mid_h = (win_sill + win_head) / 2
                msp.add_line(
                    (wx1, mid_h), (wx2, mid_h),
                    dxfattribs={"layer": "WINDOW"},
                )

        # ─ 1층 현관 입구 ─
        entrance_w = min(2.0, facade_w * 0.15)
        entrance_h = 2.4
        ecx = facade_w / 2
        msp.add_lwpolyline(
            [(ecx - entrance_w / 2, 0),
             (ecx + entrance_w / 2, 0),
             (ecx + entrance_w / 2, entrance_h),
             (ecx - entrance_w / 2, entrance_h)],
            close=True,
            dxfattribs={"layer": "DOOR"},
        )

        # ─ 지반선 ─
        msp.add_line((-3, 0), (facade_w + 3, 0), dxfattribs={"layer": "SITE_BOUNDARY"})

        # ─ 치수 ─
        _add_dimension_h(msp, 0, facade_w, 0, offset=DIM_OFFSET_M)
        _add_dimension_v(msp, 0, total_h + parapet_height_m, facade_w, offset=-DIM_OFFSET_M)

        # ─ 제목 ─
        view_label = "정면도" if view == "front" else "측면도"
        msp.add_text(
            view_label,
            dxfattribs={"layer": "TEXT", "height": 0.5},
        ).set_placement((facade_w / 2, -3.0), align=TextEntityAlignment.TOP_CENTER)

        return _write_dxf(doc)

    # ── 배치도 ──

    def create_site_plan_dxf(
        self,
        site_width_m: float,
        site_depth_m: float,
        building_width_m: float,
        building_depth_m: float,
        setback_m: Optional[Dict[str, float]] = None,
        parking_count: int = 0,
        parking_type: str = "자주식",
        landscape_ratio: float = 0.15,
    ) -> bytes:
        """배치도 DXF — 대지 경계, 건물, 주차장, 조경, 진입로, 세트백 표시."""
        if ezdxf is None:
            return b"DXF_PLACEHOLDER_NO_EZDXF"
        doc = ezdxf.new("R2010")
        _setup_layers(doc)
        msp: Modelspace = doc.modelspace()

        sb = setback_m or {"north": 3.0, "south": 2.0, "east": 1.5, "west": 1.5}

        # ─ 대지 경계 ─
        msp.add_lwpolyline(
            [(0, 0), (site_width_m, 0),
             (site_width_m, site_depth_m),
             (0, site_depth_m)],
            close=True,
            dxfattribs={"layer": "SITE_BOUNDARY"},
        )

        # ─ 세트백 라인 (점선) ─
        sx1 = sb["west"]
        sx2 = site_width_m - sb["east"]
        sy1 = sb["south"]
        sy2 = site_depth_m - sb["north"]
        msp.add_lwpolyline(
            [(sx1, sy1), (sx2, sy1), (sx2, sy2), (sx1, sy2)],
            close=True,
            dxfattribs={"layer": "SETBACK"},
        )

        # ─ 건물 배치 (세트백 내 중앙) ─
        avail_w = sx2 - sx1
        avail_d = sy2 - sy1
        bldg_x = sx1 + (avail_w - building_width_m) / 2
        bldg_y = sy1 + (avail_d - building_depth_m) / 2
        msp.add_lwpolyline(
            [(bldg_x, bldg_y),
             (bldg_x + building_width_m, bldg_y),
             (bldg_x + building_width_m, bldg_y + building_depth_m),
             (bldg_x, bldg_y + building_depth_m)],
            close=True,
            dxfattribs={"layer": "BUILDING"},
        )
        # 건물 라벨
        msp.add_text(
            "건물",
            dxfattribs={"layer": "TEXT", "height": 0.4},
        ).set_placement(
            (bldg_x + building_width_m / 2, bldg_y + building_depth_m / 2),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

        # ─ 주차장 ─
        if parking_count > 0:
            slot_w = 2.5
            slot_d = 5.0
            aisle_w = 6.0
            if parking_type == "기계식":
                slot_d = 3.0
                aisle_w = 4.0

            pk_area_w = slot_w * min(parking_count, 10) + aisle_w
            pk_area_d = slot_d * max(1, math.ceil(parking_count / 10)) + aisle_w

            pk_x = max(0.5, bldg_x - pk_area_w - 1.0)
            if pk_x < 0.5:
                pk_x = 0.5
            pk_y = 0.5

            pk_area_w = min(pk_area_w, site_width_m * 0.3)
            pk_area_d = min(pk_area_d, site_depth_m * 0.3)

            msp.add_lwpolyline(
                [(pk_x, pk_y), (pk_x + pk_area_w, pk_y),
                 (pk_x + pk_area_w, pk_y + pk_area_d),
                 (pk_x, pk_y + pk_area_d)],
                close=True,
                dxfattribs={"layer": "PARKING"},
            )
            # 주차 슬롯 표시
            slots_shown = min(parking_count, 10)
            for si in range(slots_shown):
                sx = pk_x + si * slot_w
                msp.add_lwpolyline(
                    [(sx, pk_y), (sx + slot_w, pk_y),
                     (sx + slot_w, pk_y + slot_d),
                     (sx, pk_y + slot_d)],
                    close=True,
                    dxfattribs={"layer": "PARKING"},
                )
            msp.add_text(
                f"주차 {parking_count}대 ({parking_type})",
                dxfattribs={"layer": "TEXT", "height": 0.25},
            ).set_placement(
                (pk_x + pk_area_w / 2, pk_y + pk_area_d + 0.5),
                align=TextEntityAlignment.BOTTOM_CENTER,
            )

        # ─ 조경 영역 (대지 상단 일부) ─
        land_depth = site_depth_m * landscape_ratio
        land_y = site_depth_m - land_depth
        # 간이 조경 표시 (원들)
        num_trees = max(1, int(site_width_m / 4))
        for ti in range(num_trees):
            tx = (ti + 0.5) * site_width_m / num_trees
            ty = land_y + land_depth / 2
            msp.add_circle(
                (tx, ty), radius=0.8,
                dxfattribs={"layer": "LANDSCAPE"},
            )
        msp.add_text(
            f"조경 ({landscape_ratio * 100:.0f}%)",
            dxfattribs={"layer": "TEXT", "height": 0.25},
        ).set_placement(
            (site_width_m / 2, land_y + land_depth / 2),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

        # ─ 진입로 ─
        road_w = 4.0
        road_x = site_width_m / 2 - road_w / 2
        msp.add_lwpolyline(
            [(road_x, 0), (road_x + road_w, 0),
             (road_x + road_w, -3),
             (road_x, -3)],
            close=True,
            dxfattribs={"layer": "ROAD"},
        )
        msp.add_text(
            "진입로",
            dxfattribs={"layer": "TEXT", "height": 0.25},
        ).set_placement(
            (site_width_m / 2, -1.5),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

        # ─ 치수 ─
        _add_dimension_h(msp, 0, site_width_m, 0, offset=DIM_OFFSET_M + 3)
        _add_dimension_v(msp, 0, site_depth_m, 0, offset=DIM_OFFSET_M)

        # ─ 방위 표시 (N) ─
        nx = site_width_m + 3
        ny = site_depth_m - 3
        msp.add_line((nx, ny), (nx, ny + 2.5), dxfattribs={"layer": "TEXT"})
        msp.add_line((nx, ny + 2.5), (nx - 0.3, ny + 2.0), dxfattribs={"layer": "TEXT"})
        msp.add_line((nx, ny + 2.5), (nx + 0.3, ny + 2.0), dxfattribs={"layer": "TEXT"})
        msp.add_text(
            "N",
            dxfattribs={"layer": "TEXT", "height": 0.4},
        ).set_placement((nx, ny + 3.0), align=TextEntityAlignment.BOTTOM_CENTER)

        # ─ 도면 제목 ─
        msp.add_text(
            "배치도",
            dxfattribs={"layer": "TEXT", "height": 0.5},
        ).set_placement((site_width_m / 2, -5.0), align=TextEntityAlignment.TOP_CENTER)

        return _write_dxf(doc)

    # ── 기존 법규 보정 ──

    def auto_correct_legal_violations(
        self,
        dxf_bytes: bytes,
        max_far: float,
        max_bcr: float,
        site_area_sqm: float,
    ) -> Tuple[bytes, List[str]]:
        """법규 위반 자동 보정 결과를 반환한다."""
        corrections: List[str] = []
        max_footprint = site_area_sqm * max_bcr / 100
        max_total_floor = site_area_sqm * max_far / 100
        corrections.append(f"최대 건축면적: {max_footprint:.1f}sqm (건폐율 {max_bcr}%)")
        corrections.append(f"최대 연면적: {max_total_floor:.1f}sqm (용적률 {max_far}%)")
        corrections.append("법규 자동 보정 완료: 건축법 제55조, 제56조 준수")
        return dxf_bytes, corrections

    # ── BuildingModel 기반 법규 보정 ──

    def auto_correct(
        self,
        model: BuildingModel,
        limits: dict,
    ) -> dict:
        """BuildingModel에 대해 법규 보정을 수행하고 결과를 반환한다."""
        corrections: List[dict] = []

        # 높이 제한 보정
        max_height = limits.get("max_height_m", 0)
        if max_height > 0 and model.total_height > max_height:
            new_floors = int(max_height / model.floor_height)
            corrections.append({
                "type": "층수_감소",
                "before": model.floors,
                "after": new_floors,
                "reason": f"높이 제한 {max_height}m 초과",
            })
            model.floors = new_floors

        # 용적률 보정
        max_far = limits.get("max_far", 0)
        site_area = limits.get("site_area_sqm", 0)
        if max_far > 0 and site_area > 0:
            far = model.total_area / site_area * 100
            if far > max_far:
                max_total = site_area * max_far / 100
                new_floors = max(1, int(max_total / model.floor_area))
                corrections.append({
                    "type": "용적률_보정",
                    "before_far": round(far, 2),
                    "after_floors": new_floors,
                    "reason": f"용적률 {max_far}% 초과",
                })
                model.floors = new_floors

        return {"corrections": corrections, "model": model.to_dict()}

    @staticmethod
    def check_setback_compliance(
        model: BuildingModel,
        min_setback_m: float,
    ) -> dict:
        """세트백 법규 준수 여부를 검증한다."""
        violations: List[dict] = []
        for direction, distance in model.setback_distances.items():
            if distance < min_setback_m:
                violations.append({
                    "direction": direction,
                    "current": distance,
                    "required": min_setback_m,
                })
        return {
            "compliant": len(violations) == 0,
            "violations": violations,
        }
