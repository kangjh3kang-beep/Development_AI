from __future__ import annotations

import math
from typing import Dict, List, Optional

try:
    import svgwrite
except ImportError:
    svgwrite = None  # type: ignore[assignment]
import structlog

logger = structlog.get_logger()

# ── 상수 ──
SVG_PLACEHOLDER = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><text x="10" y="30" font-size="8">svgwrite 미설치</text></svg>'
SCALE_PX_PER_M = 8  # 1m = 8px (상세 도면 기본 스케일)
WALL_PX = 1.6  # 벽체 두께 (200mm × 8px/m)
MARGIN = 60  # 여백 (px)
FONT = "sans-serif"

# 색상 팔레트
C_WALL = "#2d3436"
C_WALL_INT = "#636e72"
C_WINDOW = "#0984e3"
C_DOOR = "#00b894"
C_CORRIDOR = "#dfe6e9"
C_CORE = "#b2bec3"
C_TEXT = "#2d3436"
C_DIM = "#d63031"
C_SITE = "#ffeaa7"
C_BUILDING = "#74b9ff"
C_PARKING = "#a29bfe"
C_LANDSCAPE = "#00b894"
C_ROAD = "#b2bec3"
C_SETBACK = "#d63031"


def _s(m: float) -> float:
    """미터 → 픽셀 변환."""
    return m * SCALE_PX_PER_M


def _dim_h(dwg: svgwrite.Drawing, group, x1: float, x2: float, y: float,
           offset: float = 12) -> None:
    """수평 치수선 (px 단위 좌표)."""
    dy = y + offset
    length_m = abs(x2 - x1) / SCALE_PX_PER_M
    group.add(dwg.line(start=(x1, y), end=(x1, dy + 4), stroke=C_DIM, stroke_width=0.5))
    group.add(dwg.line(start=(x2, y), end=(x2, dy + 4), stroke=C_DIM, stroke_width=0.5))
    group.add(dwg.line(start=(x1, dy), end=(x2, dy), stroke=C_DIM, stroke_width=0.5))
    mid = (x1 + x2) / 2
    group.add(dwg.text(
        f"{length_m:.1f}m", insert=(mid, dy - 2),
        font_size="7px", font_family=FONT, fill=C_DIM, text_anchor="middle",
    ))


def _dim_v(dwg: svgwrite.Drawing, group, y1: float, y2: float, x: float,
           offset: float = -12) -> None:
    """수직 치수선 (px 단위 좌표)."""
    dx = x + offset
    length_m = abs(y2 - y1) / SCALE_PX_PER_M
    group.add(dwg.line(start=(x, y1), end=(dx - 4, y1), stroke=C_DIM, stroke_width=0.5))
    group.add(dwg.line(start=(x, y2), end=(dx - 4, y2), stroke=C_DIM, stroke_width=0.5))
    group.add(dwg.line(start=(dx, y1), end=(dx, y2), stroke=C_DIM, stroke_width=0.5))
    mid = (y1 + y2) / 2
    group.add(dwg.text(
        f"{length_m:.1f}m", insert=(dx - 2, mid),
        font_size="7px", font_family=FONT, fill=C_DIM, text_anchor="end",
        transform=f"rotate(-90,{dx - 2},{mid})",
    ))


class SVGDrawingService:
    """SVG 기반 건축 도면 자동 생성 서비스.

    메서드:
    - generate_site_plan: 간이 배치도 (기존)
    - generate_floor_plan: 간이 평면도 (기존)
    - generate_detailed_floor_plan: 상세 평면도 (벽체/문/창호/코어/복도/치수선)
    - generate_section_drawing: 건물 단면도
    - generate_elevation_drawing: 건물 입면도
    - generate_parking_layout: 주차장 배치도
    - generate_full_drawing_set: 전체 도면 세트 일괄 생성 (v61)
    """

    def generate_full_drawing_set(self, project_data: dict) -> dict[str, str]:
        """프로젝트 데이터로 전체 도면 세트를 일괄 생성한다.

        Args:
            project_data: site_width_m, site_depth_m, building_width_m,
                building_depth_m, floor_count, floor_height_m,
                basement_floors, unit_width_m, setback_m, facade_material,
                project_name 등

        Returns:
            {drawing_code: svg_string} 딕셔너리
        """
        sw = project_data.get("site_width_m", 60.0)
        sd = project_data.get("site_depth_m", 40.0)
        bw = project_data.get("building_width_m", 40.0)
        bd = project_data.get("building_depth_m", 20.0)
        fc = project_data.get("floor_count", 5)
        fh = project_data.get("floor_height_m", 3.0)
        bf = project_data.get("basement_floors", 1)
        uw = project_data.get("unit_width_m", 8.0)
        sb = project_data.get("setback_m", 3.0)
        name = project_data.get("project_name", "PropAI")

        drawings: dict[str, str] = {}

        # svgwrite 미설치 시 fallback
        if svgwrite is None:
            placeholder = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
                '<rect width="400" height="300" fill="white"/>'
                f'<text x="200" y="150" text-anchor="middle">{name}</text>'
                '</svg>'
            )
            for code in ["B-01", "B-02-STD", "B-03", "B-04-F", "B-04-S", "C-03"]:
                drawings[code] = placeholder
            # C-01/C-02 는 자체 fallback 있음
            try:
                from app.services.drawing.perspective_generator import PerspectiveGenerator
                drawings["C-01"] = PerspectiveGenerator().generate({
                    "building_w": bw, "building_d": bd,
                    "floor_count": fc, "floor_height": fh,
                    "project_name": name,
                })
            except (ImportError, ValueError):
                drawings["C-01"] = placeholder
            try:
                from app.services.drawing.shadow_simulator import ShadowSimulator
                drawings["C-02"] = ShadowSimulator().generate({
                    "building_w": bw, "building_d": bd,
                    "building_h": fc * fh,
                })
            except (ImportError, ValueError):
                drawings["C-02"] = placeholder
            return drawings

        # B-01: 배치도
        drawings["B-01"] = self.generate_site_plan(sw, sd, bw, bd, sb)

        # B-02-STD: 기준층 평면도 (units 제공 시 실제 평형믹스로 분할)
        drawings["B-02-STD"] = self.generate_detailed_floor_plan(
            bw, bd, floor_label="기준층", unit_width_m=uw,
            units=project_data.get("units"),
        )

        # B-03: 단면도
        drawings["B-03"] = self.generate_section_drawing(
            bw, fc, fh, basement_floors=bf,
        )

        # B-04-F: 정면도
        drawings["B-04-F"] = self.generate_elevation_drawing(
            bw, fc, fh, unit_width_m=uw, view="front",
        )

        # B-04-S: 측면도
        drawings["B-04-S"] = self.generate_elevation_drawing(
            bd, fc, fh, unit_width_m=uw, view="side",
        )

        # C-01: 투시도 (lazy import)
        try:
            from app.services.drawing.perspective_generator import PerspectiveGenerator
            pg = PerspectiveGenerator()
            drawings["C-01"] = pg.generate({
                "building_w": bw, "building_d": bd,
                "floor_count": fc, "floor_height": fh,
                "basement_floors": bf,
                "facade_material": project_data.get("facade_material", "concrete"),
                "project_name": name,
            })
        except (ImportError, ValueError):
            drawings["C-01"] = ""

        # C-02: 일영분석
        try:
            from app.services.drawing.shadow_simulator import ShadowSimulator
            ss = ShadowSimulator()
            drawings["C-02"] = ss.generate({
                "building_w": bw, "building_d": bd,
                "building_h": fc * fh,
                "analysis_date": "winter_solstice",
            })
        except (ImportError, ValueError):
            drawings["C-02"] = ""

        # C-03: 주차장 배치도
        parking_count = project_data.get("parking_count", 50)
        drawings["C-03"] = self.generate_parking_layout(parking_count)

        return drawings

    # ── 기존 간이 배치도 ──

    def generate_site_plan(
        self,
        site_width_m: float,
        site_depth_m: float,
        building_width_m: float,
        building_depth_m: float,
        setback_m: float = 3.0,
    ) -> str:
        if svgwrite is None:
            return SVG_PLACEHOLDER
        canvas_w = int(site_width_m * 5) + 100
        canvas_h = int(site_depth_m * 5) + 100
        dwg = svgwrite.Drawing(size=(f"{canvas_w}px", f"{canvas_h}px"))
        dwg.add(dwg.rect(insert=(50, 50), size=(site_width_m * 5, site_depth_m * 5),
                          stroke="black", stroke_width=2, fill="lightyellow"))
        bx = 50 + setback_m * 5
        by = 50 + setback_m * 5
        dwg.add(dwg.rect(insert=(bx, by), size=(building_width_m * 5, building_depth_m * 5),
                          stroke="navy", stroke_width=2, fill="lightblue", opacity=0.7))
        dwg.add(dwg.text(f"부지 {site_width_m:.1f}m x {site_depth_m:.1f}m",
                          insert=(50, 40), font_size="12px", fill="black"))
        dwg.add(dwg.text(f"건물 {building_width_m:.1f}m x {building_depth_m:.1f}m",
                          insert=(bx, by - 5), font_size="10px", fill="navy"))
        dwg.add(dwg.text(f"이격거리 {setback_m:.1f}m",
                          insert=(50, by + building_depth_m * 5 + 20), font_size="10px", fill="red"))
        dwg.add(dwg.text("N", insert=(canvas_w - 30, 70), font_size="14px", font_weight="bold"))
        return dwg.tostring()

    # ── 하위 호환 래퍼 (기존 dict 기반 API) ──

    def generate_floor_plan_svg(self, data: dict) -> str:
        """기존 호환: dict 기반 평면도 생성."""
        w = data.get("width_m", 20.0)
        d = data.get("depth_m", 15.0)
        rooms = data.get("rooms", [])

        canvas_w, canvas_h = 400, 300
        dwg = svgwrite.Drawing(size=(f"{canvas_w}px", f"{canvas_h}px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(canvas_w, canvas_h), fill="white"))
        sx = (canvas_w - 40) / w
        sy = (canvas_h - 60) / d
        scale = min(sx, sy)

        ox, oy = 20, 40
        dwg.add(dwg.rect(
            insert=(ox, oy), size=(w * scale, d * scale),
            stroke="black", stroke_width=2, fill="none",
        ))
        dwg.add(dwg.text(
            f"평면도 {w:.1f}m x {d:.1f}m",
            insert=(ox, oy - 8), font_size="12px", fill="black",
        ))

        for room in rooms:
            rx = ox + room.get("x", 0) * scale
            ry = oy + room.get("y", 0) * scale
            rw = room.get("w", 5) * scale
            rh = room.get("h", 5) * scale
            dwg.add(dwg.rect(
                insert=(rx, ry), size=(rw, rh),
                stroke="gray", stroke_width=1, fill="lightyellow",
            ))
            dwg.add(dwg.text(
                room.get("name", ""),
                insert=(rx + rw / 2, ry + rh / 2),
                font_size="9px", fill="black", text_anchor="middle",
            ))

        return dwg.tostring()

    def generate_site_plan_svg(self, data: dict) -> str:
        """기존 호환: dict 기반 배치도 생성."""
        dwg = svgwrite.Drawing(size=("400px", "300px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(400, 300), fill="white"))
        dwg.add(dwg.rect(
            insert=(20, 40), size=(360, 240),
            stroke="black", stroke_width=2, fill="lightyellow",
        ))
        dwg.add(dwg.text(
            "대지 평면도", insert=(200, 25),
            font_size="14px", fill="black", text_anchor="middle", font_weight="bold",
        ))
        dwg.add(dwg.rect(
            insert=(80, 80), size=(240, 160),
            stroke="navy", stroke_width=2, fill="lightblue", opacity=0.5,
        ))
        return dwg.tostring()

    # ── 기존 간이 평면도 ──

    def generate_floor_plan(
        self,
        total_floor_area_sqm: float,
        unit_type: str = "84A",
        core_count: int = 2,
        parking_count: int = 50,
    ) -> str:
        if svgwrite is None:
            return SVG_PLACEHOLDER
        canvas_w, canvas_h = 800, 600
        dwg = svgwrite.Drawing(size=(f"{canvas_w}px", f"{canvas_h}px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(canvas_w, canvas_h), fill="white"))
        dwg.add(dwg.rect(insert=(50, 50), size=(700, 500),
                          stroke="black", stroke_width=3, fill="none"))
        core_spacing = 700 // (core_count + 1)
        for i in range(core_count):
            cx = 50 + core_spacing * (i + 1) - 25
            dwg.add(dwg.rect(insert=(cx, 200), size=(50, 100),
                              stroke="black", stroke_width=2, fill="lightgray"))
            dwg.add(dwg.text("CORE", insert=(cx + 5, 255), font_size="9px"))
        unit_sizes = {"59A": 59, "74A": 74, "84A": 84, "114A": 114}
        unit_area = unit_sizes.get(unit_type, 84)
        unit_count = int(total_floor_area_sqm / unit_area)
        dwg.add(dwg.text(f"Type {unit_type} | 세대수: {unit_count}",
                          insert=(50, 30), font_size="14px", font_weight="bold"))
        dwg.add(dwg.text(f"주차 {parking_count}대 | 총 연면적 {total_floor_area_sqm:.0f}sqm",
                          insert=(300, 30), font_size="12px"))
        return dwg.tostring()

    # ── 상세 평면도 ──

    def generate_detailed_floor_plan(
        self,
        building_width_m: float,
        building_depth_m: float,
        floor_label: str = "기준층",
        unit_width_m: float = 8.0,
        corridor_width_m: float = 1.8,
        core_count: int = 2,
        core_width_m: float = 4.0,
        core_depth_m: float = 6.0,
        units: list[dict] | None = None,
    ) -> str:
        """상세 평면도 SVG — 벽체(200mm), 문(900mm), 창호(1200mm), 코어, 복도, 치수선.

        units 제공 시(예: [{type:'59A',area_sqm:59,count_per_floor:2}]) 실제 평형믹스로
        면적비례 분할·타입라벨, 미제공 시 generic 균등분할(기존 호환).
        """
        if svgwrite is None:
            return SVG_PLACEHOLDER
        bw = _s(building_width_m)
        bd = _s(building_depth_m)
        wt = _s(0.2)  # 벽체
        canvas_w = int(bw + MARGIN * 2 + 40)
        canvas_h = int(bd + MARGIN * 2 + 60)

        dwg = svgwrite.Drawing(size=(f"{canvas_w}px", f"{canvas_h}px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(canvas_w, canvas_h), fill="white"))
        g = dwg.g(transform=f"translate({MARGIN},{MARGIN})")
        dwg.add(g)

        # 외벽 (이중선)
        g.add(dwg.rect(insert=(0, 0), size=(bw, bd),
                        stroke=C_WALL, stroke_width=2, fill="none"))
        g.add(dwg.rect(insert=(wt, wt), size=(bw - 2 * wt, bd - 2 * wt),
                        stroke=C_WALL, stroke_width=1, fill="none"))

        # 복도
        corr_y = (bd - _s(corridor_width_m)) / 2
        corr_h = _s(corridor_width_m)
        g.add(dwg.rect(insert=(wt, corr_y), size=(bw - 2 * wt, corr_h),
                        fill=C_CORRIDOR, opacity=0.5))
        g.add(dwg.line(start=(wt, corr_y), end=(bw - wt, corr_y),
                        stroke=C_WALL_INT, stroke_width=0.5))
        g.add(dwg.line(start=(wt, corr_y + corr_h), end=(bw - wt, corr_y + corr_h),
                        stroke=C_WALL_INT, stroke_width=0.5))
        g.add(dwg.text("복도", insert=(bw / 2, corr_y + corr_h / 2 + 3),
                        font_size="8px", font_family=FONT, fill=C_TEXT, text_anchor="middle"))

        # 코어
        if core_count > 0:
            spacing = bw / (core_count + 1)
            cw_px = _s(core_width_m)
            cd_px = _s(core_depth_m)
            for ci in range(core_count):
                cx = spacing * (ci + 1) - cw_px / 2
                cy = corr_y + corr_h / 2 - cd_px / 2
                g.add(dwg.rect(insert=(cx, cy), size=(cw_px, cd_px),
                                stroke=C_WALL, stroke_width=1.5, fill=C_CORE, opacity=0.6))
                # EL
                el_s = cw_px * 0.35
                g.add(dwg.rect(insert=(cx + 2, cy + 2), size=(el_s, el_s),
                                stroke=C_TEXT, stroke_width=0.5, fill="white"))
                g.add(dwg.text("EL", insert=(cx + 2 + el_s / 2, cy + 2 + el_s / 2 + 3),
                                font_size="6px", font_family=FONT, fill=C_TEXT, text_anchor="middle"))
                # 계단
                st_x = cx + cw_px * 0.5
                st_w = cw_px * 0.45
                st_h = cd_px * 0.8
                st_y = cy + cd_px * 0.1
                g.add(dwg.rect(insert=(st_x, st_y), size=(st_w, st_h),
                                stroke=C_TEXT, stroke_width=0.5, fill="white"))
                for si in range(1, 8):
                    ly = st_y + st_h * si / 8
                    g.add(dwg.line(start=(st_x, ly), end=(st_x + st_w, ly),
                                    stroke=C_TEXT, stroke_width=0.3))

        # 세대 분할: units 제공 시 실제 평형믹스(면적비례), 없으면 generic 균등분할
        inner_w = bw - 2 * wt
        door_px = _s(0.9)
        win_px = _s(1.2)

        # 층당 세대 리스트(타입,면적) 구성 → 남/북 2열로 분배
        per_floor: list[tuple[str, float]] = []
        for u in (units or []):
            cnt = int(u.get("count_per_floor") or 0)
            per_floor += [(str(u.get("type") or "세대"), float(u.get("area_sqm") or 0.0))] * max(0, cnt)
        mid = (len(per_floor) + 1) // 2
        side_lists = {"south": per_floor[:mid], "north": per_floor[mid:]}

        for side in ["south", "north"]:
            if side == "south":
                y_s, y_e = wt, corr_y
            else:
                y_s, y_e = corr_y + corr_h, bd - wt
            ud = y_e - y_s

            su = side_lists[side]
            if su:
                # 실제 세대: 면적 비례 폭으로 inner_w 채움 → seg=(타입, 폭px, 면적)
                total_area = sum(a for _, a in su) or 1.0
                segs = [(t, inner_w * (a / total_area), a) for t, a in su]
            else:
                # generic 균등분할(units 미제공 호환)
                ups = max(1, int(inner_w / _s(unit_width_m)))
                act_uw = inner_w / ups
                seg_area = (act_uw / SCALE_PX_PER_M) * (ud / SCALE_PX_PER_M)
                segs = [("", act_uw, seg_area) for _ in range(ups)]

            x = wt
            for idx, (utype, uw_px, uarea) in enumerate(segs):
                # 세대 간 내벽
                if idx > 0:
                    g.add(dwg.line(start=(x, y_s), end=(x, y_e),
                                    stroke=C_WALL_INT, stroke_width=1))

                cx = x + uw_px / 2
                cy = (y_s + y_e) / 2
                if utype:  # 실제 세대: 타입 + 전용면적
                    g.add(dwg.text(utype, insert=(cx, cy - 1), font_size="7px", font_family=FONT,
                                    fill=C_TEXT, text_anchor="middle", font_weight="bold"))
                    g.add(dwg.text(f"{uarea:.0f}\u33a1", insert=(cx, cy + 8), font_size="6px",
                                    font_family=FONT, fill=C_TEXT, text_anchor="middle"))
                else:  # generic: 면적만
                    g.add(dwg.text(f"{uarea:.1f}m\u00b2", insert=(cx, cy + 3), font_size="7px",
                                    font_family=FONT, fill=C_TEXT, text_anchor="middle"))

                # 현관문 (복도 쪽)
                dx = x + uw_px * 0.1
                if side == "south":
                    g.add(dwg.line(start=(dx, corr_y), end=(dx + door_px, corr_y),
                                    stroke=C_DOOR, stroke_width=2))
                    g.add(dwg.path(
                        d=f"M {dx},{corr_y} A {door_px},{door_px} 0 0,0 {dx},{corr_y - door_px}",
                        stroke=C_DOOR, stroke_width=0.5, fill="none",
                    ))
                else:
                    dy = corr_y + corr_h
                    g.add(dwg.line(start=(dx, dy), end=(dx + door_px, dy),
                                    stroke=C_DOOR, stroke_width=2))
                    g.add(dwg.path(
                        d=f"M {dx},{dy} A {door_px},{door_px} 0 0,1 {dx},{dy + door_px}",
                        stroke=C_DOOR, stroke_width=0.5, fill="none",
                    ))

                # 외벽 창호
                wx = x + (uw_px - win_px) / 2
                if side == "south":
                    g.add(dwg.rect(insert=(wx, 0), size=(win_px, wt),
                                    fill=C_WINDOW, opacity=0.6))
                    g.add(dwg.line(start=(wx + win_px / 2, 0), end=(wx + win_px / 2, wt),
                                    stroke="white", stroke_width=0.5))
                else:
                    g.add(dwg.rect(insert=(wx, bd - wt), size=(win_px, wt),
                                    fill=C_WINDOW, opacity=0.6))
                    g.add(dwg.line(start=(wx + win_px / 2, bd - wt), end=(wx + win_px / 2, bd),
                                    stroke="white", stroke_width=0.5))
                x += uw_px

        # 치수선
        _dim_h(dwg, g, 0, bw, bd, offset=15)
        _dim_v(dwg, g, 0, bd, 0, offset=-15)

        # 제목
        g.add(dwg.text(
            f"{floor_label} 평면도",
            insert=(bw / 2, -10), font_size="10px", font_family=FONT,
            fill=C_TEXT, text_anchor="middle", font_weight="bold",
        ))

        return dwg.tostring()

    # ── 단면도 ──

    def generate_section_drawing(
        self,
        building_width_m: float,
        floor_count: int,
        floor_height_m: float = 3.0,
        basement_floors: int = 1,
        basement_height_m: float = 3.3,
        parapet_height_m: float = 1.2,
    ) -> str:
        """건물 단면도 SVG — 지하층, 각 층, 기초, 지붕/파라펫 포함."""
        if svgwrite is None:
            return SVG_PLACEHOLDER
        bw = _s(building_width_m)
        total_above = floor_count * floor_height_m
        total_below = basement_floors * basement_height_m
        total_h = total_above + total_below + parapet_height_m + 1.0  # 기초 1m

        ch = _s(total_h)
        canvas_w = int(bw + MARGIN * 2 + 60)
        canvas_h = int(ch + MARGIN * 2 + 40)

        dwg = svgwrite.Drawing(size=(f"{canvas_w}px", f"{canvas_h}px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(canvas_w, canvas_h), fill="white"))

        # 원점: 좌하단이 GL
        gl_y_canvas = MARGIN + _s(total_above + parapet_height_m)
        g = dwg.g(transform=f"translate({MARGIN},{gl_y_canvas})")
        dwg.add(g)

        # y축은 위가 - (SVG 좌표)
        def ym(m: float) -> float:
            return -_s(m)

        # 지반선
        g.add(dwg.line(start=(-30, 0), end=(bw + 30, 0),
                        stroke=C_TEXT, stroke_width=1.5, stroke_dasharray="5,3"))
        g.add(dwg.text("G.L.", insert=(bw + 35, 4),
                        font_size="8px", font_family=FONT, fill=C_TEXT))

        # 지하층
        for bi in range(basement_floors):
            by_top = _s(bi * basement_height_m)
            by_bot = _s((bi + 1) * basement_height_m)
            # 슬래브
            g.add(dwg.line(start=(0, by_top), end=(bw, by_top),
                            stroke=C_WALL, stroke_width=1.5))
            g.add(dwg.line(start=(0, by_bot), end=(bw, by_bot),
                            stroke=C_WALL, stroke_width=1.5))
            # 벽
            g.add(dwg.line(start=(0, by_top), end=(0, by_bot), stroke=C_WALL, stroke_width=1.5))
            g.add(dwg.line(start=(bw, by_top), end=(bw, by_bot), stroke=C_WALL, stroke_width=1.5))
            # 라벨
            g.add(dwg.text(f"B{bi + 1}F", insert=(bw / 2, (by_top + by_bot) / 2 + 3),
                            font_size="8px", font_family=FONT, fill=C_TEXT, text_anchor="middle"))

        # 기초
        fd = _s(total_below + 1.0)
        g.add(dwg.rect(insert=(-_s(1), fd - _s(1.0)), size=(bw + _s(2), _s(1.0)),
                        stroke=C_WALL, stroke_width=1, fill="#dfe6e9"))
        g.add(dwg.text("기초", insert=(bw / 2, fd - _s(0.5) + 3),
                        font_size="7px", font_family=FONT, fill=C_TEXT, text_anchor="middle"))

        # 지상층
        for fi in range(floor_count):
            fy_bot = ym(fi * floor_height_m)
            fy_top = ym((fi + 1) * floor_height_m)
            # 슬래브
            g.add(dwg.line(start=(0, fy_bot), end=(bw, fy_bot),
                            stroke=C_WALL, stroke_width=1.5))
            # 벽
            g.add(dwg.line(start=(0, fy_bot), end=(0, fy_top), stroke=C_WALL, stroke_width=1.5))
            g.add(dwg.line(start=(bw, fy_bot), end=(bw, fy_top), stroke=C_WALL, stroke_width=1.5))
            # 라벨
            g.add(dwg.text(f"{fi + 1}F", insert=(bw / 2, (fy_bot + fy_top) / 2 + 3),
                            font_size="8px", font_family=FONT, fill=C_TEXT, text_anchor="middle"))

        # 지붕 슬래브
        roof_y = ym(total_above)
        g.add(dwg.line(start=(0, roof_y), end=(bw, roof_y),
                        stroke=C_WALL, stroke_width=2))

        # 파라펫
        par_y = ym(total_above + parapet_height_m)
        g.add(dwg.line(start=(0, roof_y), end=(0, par_y), stroke=C_WALL, stroke_width=1.5))
        g.add(dwg.line(start=(bw, roof_y), end=(bw, par_y), stroke=C_WALL, stroke_width=1.5))
        g.add(dwg.line(start=(0, par_y), end=(bw, par_y), stroke=C_WALL, stroke_width=1.5))

        # 치수
        _dim_v(dwg, g, 0, ym(total_above + parapet_height_m), 0, offset=-20)
        _dim_h(dwg, g, 0, bw, _s(total_below + 1.0), offset=15)

        # 제목
        g.add(dwg.text("건물 단면도", insert=(bw / 2, _s(total_below + 1.0) + 35),
                        font_size="10px", font_family=FONT, fill=C_TEXT,
                        text_anchor="middle", font_weight="bold"))

        return dwg.tostring()

    # ── 입면도 ──

    def generate_elevation_drawing(
        self,
        building_width_m: float,
        floor_count: int,
        floor_height_m: float = 3.0,
        unit_width_m: float = 8.0,
        window_width_m: float = 1.2,
        window_height_m: float = 1.2,
        parapet_height_m: float = 1.2,
        view: str = "front",
    ) -> str:
        """건물 입면도 SVG — 창호 패턴, 현관 표시."""
        if svgwrite is None:
            return SVG_PLACEHOLDER
        facade_m = building_width_m
        total_h_m = floor_count * floor_height_m + parapet_height_m

        fw = _s(facade_m)
        fh = _s(total_h_m)
        canvas_w = int(fw + MARGIN * 2 + 40)
        canvas_h = int(fh + MARGIN * 2 + 40)

        dwg = svgwrite.Drawing(size=(f"{canvas_w}px", f"{canvas_h}px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(canvas_w, canvas_h), fill="white"))

        # 원점: 좌하단
        g = dwg.g(transform=f"translate({MARGIN},{MARGIN + fh})")
        dwg.add(g)

        def ym(m: float) -> float:
            return -_s(m)

        # 건물 외곽
        body_h = _s(floor_count * floor_height_m)
        g.add(dwg.rect(insert=(0, ym(floor_count * floor_height_m)),
                        size=(fw, body_h),
                        stroke=C_WALL, stroke_width=2, fill="#f5f6fa"))

        # 파라펫
        par_h = _s(parapet_height_m)
        g.add(dwg.rect(insert=(0, ym(total_h_m)), size=(fw, par_h),
                        stroke=C_WALL, stroke_width=1.5, fill="#dcdde1"))

        # 층별 창호
        units_facade = max(1, int(facade_m / unit_width_m))
        act_uw = fw / units_facade

        for fi in range(floor_count):
            fy = fi * floor_height_m
            # 슬래브선
            if fi > 0:
                g.add(dwg.line(start=(0, ym(fy)), end=(fw, ym(fy)),
                                stroke=C_WALL_INT, stroke_width=0.5, stroke_dasharray="3,2"))
            # 창호
            sill_y = ym(fy + 0.9)
            win_h_px = _s(window_height_m)
            win_w_px = _s(window_width_m)
            for ui in range(units_facade):
                cx = ui * act_uw + act_uw / 2
                wx = cx - win_w_px / 2
                g.add(dwg.rect(insert=(wx, sill_y - win_h_px), size=(win_w_px, win_h_px),
                                stroke=C_WINDOW, stroke_width=1, fill=C_WINDOW, opacity=0.3))
                # 십자 분할
                g.add(dwg.line(start=(cx, sill_y - win_h_px), end=(cx, sill_y),
                                stroke=C_WINDOW, stroke_width=0.5))
                mid_wy = sill_y - win_h_px / 2
                g.add(dwg.line(start=(wx, mid_wy), end=(wx + win_w_px, mid_wy),
                                stroke=C_WINDOW, stroke_width=0.5))

        # 1층 현관
        ent_w = _s(min(2.0, facade_m * 0.15))
        ent_h = _s(2.4)
        ecx = fw / 2
        g.add(dwg.rect(insert=(ecx - ent_w / 2, ym(2.4)),
                        size=(ent_w, ent_h),
                        stroke=C_DOOR, stroke_width=1.5, fill=C_DOOR, opacity=0.3))

        # 지반선
        g.add(dwg.line(start=(-20, 0), end=(fw + 20, 0),
                        stroke=C_TEXT, stroke_width=1.5))

        # 치수
        _dim_h(dwg, g, 0, fw, 0, offset=15)
        _dim_v(dwg, g, 0, ym(total_h_m), fw, offset=15)

        # 제목
        view_label = "정면도" if view == "front" else "측면도"
        g.add(dwg.text(view_label, insert=(fw / 2, 30),
                        font_size="10px", font_family=FONT, fill=C_TEXT,
                        text_anchor="middle", font_weight="bold"))

        return dwg.tostring()

    # ── 주차장 배치도 ──

    def generate_parking_layout(
        self,
        parking_count: int,
        parking_type: str = "자주식",
        total_area_sqm: float = 0,
    ) -> str:
        """주차장 배치도 SVG — 자주식(2.5×5.0m)/기계식(2.5×3.0m), 통로 6m/4m."""
        if svgwrite is None:
            return SVG_PLACEHOLDER
        slot_w_m = 2.5
        slot_d_m = 5.0 if parking_type == "자주식" else 3.0
        aisle_w_m = 6.0 if parking_type == "자주식" else 4.0

        cols = min(parking_count, 10)
        rows = max(1, math.ceil(parking_count / 10))

        layout_w_m = cols * slot_w_m + aisle_w_m
        layout_h_m = rows * slot_d_m * 2 + (rows) * aisle_w_m

        lw = _s(layout_w_m)
        lh = _s(layout_h_m)
        canvas_w = int(lw + MARGIN * 2)
        canvas_h = int(lh + MARGIN * 2 + 30)

        dwg = svgwrite.Drawing(size=(f"{canvas_w}px", f"{canvas_h}px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(canvas_w, canvas_h), fill="white"))
        g = dwg.g(transform=f"translate({MARGIN},{MARGIN})")
        dwg.add(g)

        # 외곽
        g.add(dwg.rect(insert=(0, 0), size=(lw, lh),
                        stroke=C_WALL, stroke_width=1.5, fill="none"))

        slot_count = 0
        for ri in range(rows):
            aisle_y = _s(ri * (slot_d_m * 2 + aisle_w_m) + slot_d_m)
            # 통로
            g.add(dwg.rect(insert=(0, aisle_y), size=(lw, _s(aisle_w_m)),
                            fill=C_ROAD, opacity=0.3))
            g.add(dwg.text(f"통로 {aisle_w_m:.0f}m",
                            insert=(lw / 2, aisle_y + _s(aisle_w_m) / 2 + 3),
                            font_size="7px", font_family=FONT, fill=C_TEXT, text_anchor="middle"))

            # 상단 주차 슬롯
            for ci in range(cols):
                if slot_count >= parking_count:
                    break
                sx = _s(ci * slot_w_m)
                sy = aisle_y - _s(slot_d_m)
                g.add(dwg.rect(insert=(sx, sy), size=(_s(slot_w_m), _s(slot_d_m)),
                                stroke=C_PARKING, stroke_width=0.5, fill=C_PARKING, opacity=0.2))
                slot_count += 1

            # 하단 주차 슬롯
            for ci in range(cols):
                if slot_count >= parking_count:
                    break
                sx = _s(ci * slot_w_m)
                sy = aisle_y + _s(aisle_w_m)
                g.add(dwg.rect(insert=(sx, sy), size=(_s(slot_w_m), _s(slot_d_m)),
                                stroke=C_PARKING, stroke_width=0.5, fill=C_PARKING, opacity=0.2))
                slot_count += 1

        # 제목
        area_text = f" ({total_area_sqm:.0f}m\u00b2)" if total_area_sqm > 0 else ""
        g.add(dwg.text(
            f"주차장 배치도 — {parking_count}대 {parking_type}{area_text}",
            insert=(lw / 2, -8), font_size="10px", font_family=FONT,
            fill=C_TEXT, text_anchor="middle", font_weight="bold",
        ))

        return dwg.tostring()
