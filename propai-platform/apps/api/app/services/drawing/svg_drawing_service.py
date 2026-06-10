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


import re as _re


def _make_responsive(svg: str) -> str:
    """고정 px <svg width/height> → viewBox + 100% 로 바꿔 컨테이너에 꽉 차게(가독성).

    기존 도면들이 작은 고정 px로 렌더돼 화면 중앙에 작게 떠 보이던 문제 해결.
    """
    if not svg or "<svg" not in svg:
        return svg
    # svgwrite는 속성을 알파벳순 출력 → width/height가 인접하지 않으므로 각각 탐색.
    mw = _re.search(r'\bwidth="(\d+(?:\.\d+)?)(?:px)?"', svg)
    mh = _re.search(r'\bheight="(\d+(?:\.\d+)?)(?:px)?"', svg)
    if not (mw and mh):
        return svg
    w, h = mw.group(1), mh.group(1)
    if "viewBox" not in svg:
        svg = svg.replace(
            "<svg ",
            f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" '
            'style="width:100%;height:100%;display:block" ',
            1,
        )
    return svg


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

        # B-02-UNIT: 단위세대 평면도(실배치·실명·면적·문스윙·창호·치수·방위·표제란) — 대표 평형
        _units = project_data.get("units") or []
        if _units:
            _rep = max(_units, key=lambda u: float(u.get("area_sqm") or 0))
            _utype = str(_rep.get("type") or "84A")
            _uarea = float(_rep.get("area_sqm") or 84.0)
        else:
            _utype, _uarea = "84A", 84.0
        _total_units = int(sum(float(u.get("total_count") or 0) for u in _units)) if _units else 0
        drawings["B-02-UNIT"] = self.generate_unit_plan(
            _utype, _uarea, project_name=name, floors=int(fc or 0), total_units=_total_units,
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

        # 모든 도면을 반응형(viewBox+100%)으로 — 화면에 작게 뜨던 문제 해결
        for _code in list(drawings.keys()):
            drawings[_code] = _make_responsive(drawings[_code])

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

    # ── 단위세대 평면도(실배치·실명·면적·문스윙·창호·치수·방위·표제란) ──

    def generate_unit_plan(
        self,
        unit_type: str = "84A",
        area_sqm: float = 84.0,
        project_name: str = "PropAI",
        drawing_no: str = "A-201",
        floors: int = 0,
        total_units: int = 0,
    ) -> str:
        """실제 건축 평면도에 부합하는 단위세대 평면도 SVG.

        벽=poché(채워진 두께), 실=실명+전용면적, 문=개구부+문짝+90°스윙호,
        창=외벽 3선, 치수체인, 방위표(N), 표제란, 스케일바. 한국 공동주택 판상형 관례.
        "어두운 본체 − 흰 실 = 벽(poché)" 기법으로 내·외벽을 한 번에 표현.
        """
        if svgwrite is None:
            return SVG_PLACEHOLDER

        PXM = 36.0            # 1m = 36px (1:100 화면 가독 스케일)
        EXT = 0.20           # 외벽 200mm
        big = area_sqm >= 72.0

        # ── 전용면적에 맞춰 본체 치수 추정(판상형 전면 8.4m 기준) ──
        body_w = 8.4 if big else 8.4
        body_d = max(6.0, round(area_sqm / body_w, 1))  # 전용면적/전면폭 ≈ 깊이
        bal_h = min(1.5, round(body_d * 0.14, 2))

        # ── 실배치(파라메트릭 판상형) — 남측(아래)=거실·침실, 북측(위)=주방·욕실·현관 ──
        n_h = round(body_d * 0.30, 2)
        c_h = round(body_d * 0.16, 2)
        s_y = round(n_h + c_h, 2)
        s_h = round(body_d - s_y, 2)

        rooms: list[dict] = []
        doors: list[dict] = []
        windows: list[dict] = []

        south_cols = ([("안방", 0.38), ("거실", 0.34), ("침실2", 0.28)]
                      if big else [("안방", 0.45), ("거실", 0.55)])
        x = 0.0
        for name, frac in south_cols:
            cw = round(body_w * frac, 2)
            rooms.append({"name": name, "x": x, "y": s_y, "w": cw, "h": s_h})
            doors.append({"cx": round(x + cw / 2, 2), "y": s_y, "w": 0.8, "hinge": "l"})  # 복도측
            windows.append({"x": round(x + 0.25, 2), "w": round(cw - 0.5, 2), "y": body_d, "wall": "s"})
            x = round(x + cw, 2)
        # 폭 잔차 보정(마지막 실 폭에 합산)
        if rooms and abs(x - body_w) > 0.01:
            rooms[len(south_cols) - 1]["w"] = round(rooms[len(south_cols) - 1]["w"] + (body_w - x), 2)

        north_cols = ([("현관", 0.18), ("욕실", 0.18), ("주방·식당", 0.36), ("침실3", 0.28)]
                      if big else [("현관", 0.20), ("욕실", 0.20), ("주방·식당", 0.60)])
        x = 0.0
        ncount = len(north_cols)
        for i, (name, frac) in enumerate(north_cols):
            cw = round(body_w * frac, 2)
            if i == ncount - 1:
                cw = round(body_w - x, 2)
            rooms.append({"name": name, "x": x, "y": 0.0, "w": cw, "h": n_h})
            if name == "현관":
                # 외부 진입문(북측 외벽) + 세대 진입문(복도측) 둘 다 — 현관이 막히지 않게.
                doors.append({"cx": round(x + cw / 2, 2), "y": 0.0, "w": 0.95, "hinge": "l", "entry": True})
                doors.append({"cx": round(x + cw / 2, 2), "y": n_h, "w": 0.9, "hinge": "l"})
            else:
                doors.append({"cx": round(x + cw / 2, 2), "y": n_h, "w": 0.75, "hinge": "l"})
            if name in ("주방·식당", "침실3"):
                windows.append({"x": round(x + 0.25, 2), "w": round(cw - 0.5, 2), "y": 0.0, "wall": "n"})
            x = round(x + cw, 2)

        rooms.append({"name": "복도", "x": 0.0, "y": n_h, "w": body_w, "h": c_h, "hall": True})

        # ── 캔버스/여백 ──
        MX, MTOP, MBOT, MR = 78.0, 64.0, 128.0, 40.0
        cw_px = body_w * PXM + MX + MR
        ch_px = (body_d + bal_h) * PXM + MTOP + MBOT
        dwg = svgwrite.Drawing(size=(f"{cw_px:.0f}px", f"{ch_px:.0f}px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(cw_px, ch_px), fill="#ffffff"))
        g = dwg.g(transform=f"translate({MX},{MTOP})")
        dwg.add(g)

        def px(m: float) -> float:
            return m * PXM

        # 1) 발코니(남) — 본체 밖, 옅은 해칭
        g.add(dwg.rect(insert=(0, px(body_d)), size=(px(body_w), px(bal_h)),
                       fill="#eef1f4", stroke="#9aa4ad", stroke_width=0.8))
        g.add(dwg.text("발코니", insert=(px(body_w / 2), px(body_d) + px(bal_h) / 2 + 4),
                       font_size="10px", font_family=FONT, fill="#7a838c", text_anchor="middle"))

        # 2) 본체 = 어두운 면(=벽 poché 베이스)
        g.add(dwg.rect(insert=(0, 0), size=(px(body_w), px(body_d)), fill="#1a1a1a"))

        # 3) 각 실 = 흰 면(내벽 두께만큼 inset → 사이 어두운 띠가 칸막이벽 poché)
        P = 0.07  # 칸막이 절반(→ 실간벽 ~140mm)
        for r in rooms:
            fill = "#f0f2f4" if r.get("hall") else "#fafafa"
            g.add(dwg.rect(
                insert=(px(r["x"] + P), px(r["y"] + P)),
                size=(px(max(0.1, r["w"] - 2 * P)), px(max(0.1, r["h"] - 2 * P))),
                fill=fill,
            ))

        # 4) 외벽 poché(두껍게) — 본체 둘레 EXT 띠를 실 위에 덮음
        g.add(dwg.rect(insert=(0, 0), size=(px(body_w), px(EXT)), fill="#1a1a1a"))                  # 북(상)
        g.add(dwg.rect(insert=(0, px(body_d - EXT)), size=(px(body_w), px(EXT)), fill="#1a1a1a"))    # 남(하)
        g.add(dwg.rect(insert=(0, 0), size=(px(EXT), px(body_d)), fill="#1a1a1a"))                   # 좌
        g.add(dwg.rect(insert=(px(body_w - EXT), 0), size=(px(EXT), px(body_d)), fill="#1a1a1a"))    # 우

        # 5) 개구부(문) 흰색 절단 + 문짝 + 90° 스윙호
        for dd in doors:
            cx = dd["cx"]; y = dd["y"]; dw = dd["w"]
            x0 = cx - dw / 2
            # 벽 절단(가로벽: y 중심으로 ±0.13)
            g.add(dwg.rect(insert=(px(x0), px(y - 0.13)), size=(px(dw), px(0.26)), fill="#ffffff"))
            # 문짝(열린 위치) + 스윙호 — 현관/실문 모두 가로벽
            hinge_x = x0 if dd.get("hinge", "l") == "l" else x0 + dw
            sign = 1 if dd.get("hinge", "l") == "l" else -1
            # 문짝: 경첩에서 아래(실 안쪽)로 수직
            g.add(dwg.line(start=(px(hinge_x), px(y)), end=(px(hinge_x), px(y + dw)),
                           stroke="#222222", stroke_width=1.0))
            # 스윙 1/4원
            sweep = 1 if sign > 0 else 0
            g.add(dwg.path(
                d=f"M {px(hinge_x + sign * dw):.1f},{px(y):.1f} "
                  f"A {px(dw):.1f},{px(dw):.1f} 0 0,{sweep} {px(hinge_x):.1f},{px(y + dw):.1f}",
                stroke="#9aa4ad", stroke_width=0.7, fill="none"))

        # 6) 창호(외벽 3선) — 흰 절단 후 평행 3선
        for wd in windows:
            wx = wd["x"]; ww = wd["w"]; wall = wd["wall"]
            if wall == "s":
                wy = body_d - EXT
            else:
                wy = 0.0
            g.add(dwg.rect(insert=(px(wx), px(wy)), size=(px(ww), px(EXT)), fill="#ffffff"))
            for k in range(3):
                yy = wy + EXT * (0.25 + 0.25 * k)
                g.add(dwg.line(start=(px(wx), px(yy)), end=(px(wx + ww), px(yy)),
                               stroke="#5a7fa6", stroke_width=0.8))

        # 6.5) 위생기구·가구(옅은 선) — 실명 라벨 아래 레이어로 깔아 도면 현실감↑
        FS = "#9aa4b2"  # 가구/기구 선색(옅은 회청)

        def fr_rect(rx_: float, ry_: float, rw_: float, rh_: float, rad: float = 0.0, fill: str = "none") -> None:
            kw = dict(insert=(px(rx_), px(ry_)), size=(px(max(0.05, rw_)), px(max(0.05, rh_))),
                      fill=fill, stroke=FS, stroke_width=0.7)
            if rad > 0:
                kw["rx"] = px(rad); kw["ry"] = px(rad)
            g.add(dwg.rect(**kw))

        def fr_circle(cx_: float, cy_: float, rr: float) -> None:
            g.add(dwg.circle(center=(px(cx_), px(cy_)), r=px(rr), fill="none", stroke=FS, stroke_width=0.7))

        def fr_line(x1_: float, y1_: float, x2_: float, y2_: float) -> None:
            g.add(dwg.line(start=(px(x1_), px(y1_)), end=(px(x2_), px(y2_)), stroke=FS, stroke_width=0.6))

        for r in rooms:
            if r.get("hall"):
                continue
            nm = r["name"]; rx0 = r["x"]; ry0 = r["y"]; rw0 = r["w"]; rh0 = r["h"]
            mg = 0.28  # 벽 여백
            south = ry0 >= s_y
            if nm == "거실":
                # 소파(복도측) + 등받이 + 좌식테이블 + TV(창측 벽)
                sw_ = min(rw0 - 2 * mg, 2.6); sx_ = rx0 + (rw0 - sw_) / 2
                sy_ = ry0 + mg if south else ry0 + rh0 - mg - 0.85
                fr_rect(sx_, sy_, sw_, 0.85, rad=0.08)
                fr_line(sx_, sy_ + (0.2 if south else 0.65), sx_ + sw_, sy_ + (0.2 if south else 0.65))
                fr_rect(rx0 + (rw0 - 1.0) / 2, ry0 + rh0 / 2 - 0.25, 1.0, 0.5, rad=0.05)  # 테이블
                tvy = ry0 + rh0 - mg - 0.12 if south else ry0 + mg
                fr_rect(rx0 + (rw0 - 1.6) / 2, tvy, 1.6, 0.12)  # TV
            elif nm == "안방":
                bw_ = min(rw0 - 2 * mg, 1.6); bx_ = rx0 + (rw0 - bw_) / 2
                by_ = ry0 + mg if south else ry0 + rh0 - mg - 2.0
                fr_rect(bx_, by_, bw_, 2.0, rad=0.05)  # 더블침대
                ply = by_ if south else by_ + 2.0 - 0.32
                fr_rect(bx_ + 0.05, ply, bw_ * 0.46, 0.32)  # 베개1
                fr_rect(bx_ + bw_ * 0.5, ply, bw_ * 0.46, 0.32)  # 베개2
                fr_rect(rx0 + mg, ry0 + rh0 - mg - 0.55, 1.2, 0.55)  # 옷장
            elif nm.startswith("침실"):
                bw_ = min(rw0 - 2 * mg, 1.1); bx_ = rx0 + mg
                by_ = ry0 + mg if south else ry0 + rh0 - mg - 2.0
                fr_rect(bx_, by_, bw_, 2.0, rad=0.05)  # 싱글침대
                fr_rect(bx_, by_ if south else by_ + 1.7, bw_, 0.3)  # 베개
                fr_rect(rx0 + rw0 - mg - 0.55, ry0 + mg, 0.55, 1.2)  # 책상/옷장
            elif nm in ("주방·식당", "주방"):
                cyc = ry0 + mg if not south else ry0 + rh0 - mg - 0.6  # 카운터는 외벽측
                fr_rect(rx0 + mg, cyc, rw0 - 2 * mg, 0.6)  # 싱크대 카운터
                fr_rect(rx0 + mg + 0.25, cyc + 0.12, 0.55, 0.36, rad=0.05)  # 싱크볼
                for ii in range(2):
                    for jj in range(2):
                        fr_circle(rx0 + mg + 1.35 + ii * 0.3, cyc + 0.18 + jj * 0.26, 0.1)  # 레인지 4구
                tx_ = rx0 + (rw0 - 1.0) / 2; ty_ = ry0 + rh0 / 2
                fr_rect(tx_, ty_, 1.0, 0.7, rad=0.05)  # 식탁
                for cxs in (tx_ - 0.22, tx_ + 1.0 + 0.02):
                    fr_rect(cxs, ty_ + 0.18, 0.2, 0.34, rad=0.03)  # 의자
            elif nm in ("욕실", "공용욕실"):
                tubw = min(rw0 - 2 * mg, 1.5)
                fr_rect(rx0 + mg, ry0 + rh0 - mg - 0.7, tubw, 0.7, rad=0.12)  # 욕조
                fr_rect(rx0 + mg + 0.08, ry0 + rh0 - mg - 0.62, tubw - 0.16, 0.54, rad=0.1)
                fr_rect(rx0 + mg, ry0 + mg, 0.5, 0.4, rad=0.05)  # 세면대
                fr_circle(rx0 + mg + 0.25, ry0 + mg + 0.2, 0.06)
                fr_rect(rx0 + rw0 - mg - 0.4, ry0 + mg, 0.36, 0.22)  # 변기 탱크
                fr_circle(rx0 + rw0 - mg - 0.22, ry0 + mg + 0.45, 0.17)  # 변기 보울
            elif nm == "부속욕실":
                fr_rect(rx0 + mg, ry0 + mg, 0.45, 0.36, rad=0.05)  # 세면대
                fr_rect(rx0 + rw0 - mg - 0.34, ry0 + mg, 0.32, 0.2)  # 변기 탱크
                fr_circle(rx0 + rw0 - mg - 0.18, ry0 + mg + 0.4, 0.15)  # 변기 보울
                fr_rect(rx0 + mg, ry0 + rh0 - mg - 0.75, 0.75, 0.75)  # 샤워부스
                fr_line(rx0 + mg, ry0 + rh0 - mg - 0.75, rx0 + mg + 0.75, ry0 + rh0 - mg)  # 샤워 대각
            elif nm == "현관":
                fr_rect(rx0 + mg, ry0 + mg, 0.35, max(0.6, rh0 - 2 * mg))  # 신발장(측벽)
            elif nm == "드레스룸":
                fr_rect(rx0 + mg, ry0 + mg, rw0 - 2 * mg, 0.4)  # 붙박이장
                fr_line(rx0 + mg + (rw0 - 2 * mg) / 2, ry0 + mg, rx0 + mg + (rw0 - 2 * mg) / 2, ry0 + mg + 0.4)
            elif nm == "다용도실":
                fr_rect(rx0 + mg, ry0 + mg, 0.5, 0.5)  # 세탁기

        # 7) 실명 + 전용면적
        for r in rooms:
            if r.get("hall"):
                continue
            cx = px(r["x"] + r["w"] / 2)
            cy = px(r["y"] + r["h"] / 2)
            g.add(dwg.text(r["name"], insert=(cx, cy - 1), font_size="13px", font_family=FONT,
                           fill="#1a1a1a", text_anchor="middle", font_weight="bold"))
            ar = r["w"] * r["h"]
            g.add(dwg.text(f"{ar:.1f}㎡", insert=(cx, cy + 13), font_size="10px",
                           font_family=FONT, fill="#6b7480", text_anchor="middle"))

        # 8) 치수선 — 전체 폭(하단)·전체 깊이(좌측) + 남측 실폭 체인
        def dim_h(x1: float, x2: float, y_off: float, text: str) -> None:
            y = px(body_d + bal_h) + y_off
            g.add(dwg.line(start=(px(x1), y), end=(px(x2), y), stroke="#666666", stroke_width=0.5))
            for xe in (x1, x2):
                g.add(dwg.line(start=(px(xe), y - 4), end=(px(xe), y + 4), stroke="#666666", stroke_width=0.5))
            g.add(dwg.text(text, insert=((px(x1) + px(x2)) / 2, y - 3), font_size="10px",
                           font_family=FONT, fill="#333333", text_anchor="middle"))

        def dim_v(y1: float, y2: float, x_off: float, text: str) -> None:
            xx = x_off
            g.add(dwg.line(start=(xx, px(y1)), end=(xx, px(y2)), stroke="#666666", stroke_width=0.5))
            for ye in (y1, y2):
                g.add(dwg.line(start=(xx - 4, px(ye)), end=(xx + 4, px(ye)), stroke="#666666", stroke_width=0.5))
            g.add(dwg.text(text, insert=(xx - 6, (px(y1) + px(y2)) / 2),
                           font_size="10px", font_family=FONT, fill="#333333",
                           text_anchor="middle", transform=f"rotate(-90 {xx - 6} {(px(y1) + px(y2)) / 2})"))

        # 남측 실폭 체인
        cxacc = 0.0
        for name, frac in south_cols:
            cwid = round(body_w * frac, 2)
            dim_h(cxacc, cxacc + cwid, 22, f"{int(cwid * 1000)}")
            cxacc = round(cxacc + cwid, 2)
        dim_h(0, body_w, 44, f"{int(body_w * 1000)}")          # 전체 폭
        dim_v(0, body_d, -26, f"{int(body_d * 1000)}")          # 전체 깊이

        # 9) 방위표(N) — 우상단
        nax = px(body_w) - 16
        nay = -34
        g.add(dwg.circle(center=(nax, nay), r=12, fill="none", stroke="#222222", stroke_width=0.8))
        g.add(dwg.polygon(points=[(nax, nay - 11), (nax - 4, nay + 2), (nax + 4, nay + 2)], fill="#222222"))
        g.add(dwg.text("N", insert=(nax, nay + 13), font_size="9px", font_family=FONT,
                       fill="#222222", text_anchor="middle", font_weight="bold"))

        # 10) 표제란 + 축척 + 스케일바(하단)
        tb_y = px(body_d + bal_h) + 64
        g.add(dwg.rect(insert=(0, tb_y), size=(px(body_w), 40), fill="none",
                       stroke="#333333", stroke_width=0.8))
        g.add(dwg.line(start=(px(body_w) * 0.62, tb_y), end=(px(body_w) * 0.62, tb_y + 40),
                       stroke="#333333", stroke_width=0.6))
        g.add(dwg.text(f"{unit_type} 단위세대 평면도", insert=(8, tb_y + 17),
                       font_size="12px", font_family=FONT, fill="#1a1a1a", font_weight="bold"))
        # 실제 프로젝트 기하 반영: 전용면적·프로젝트명 + (있으면)층수·총세대수
        _ctx = f"전용 {area_sqm:.0f}㎡ · {project_name}"
        if floors > 0:
            _ctx += f" · 지상 {floors}층"
        if total_units > 0:
            _ctx += f" · 총 {total_units}세대"
        g.add(dwg.text(_ctx, insert=(8, tb_y + 32),
                       font_size="9px", font_family=FONT, fill="#6b7480"))
        g.add(dwg.text("축척 1:100", insert=(px(body_w) * 0.62 + 8, tb_y + 15),
                       font_size="9px", font_family=FONT, fill="#333333"))
        g.add(dwg.text(f"도면 {drawing_no}", insert=(px(body_w) * 0.62 + 8, tb_y + 30),
                       font_size="9px", font_family=FONT, fill="#333333"))
        # 스케일바(0~5m, 1m 칸)
        sb_x = px(body_w) * 0.62 + 70
        for k in range(5):
            g.add(dwg.rect(insert=(sb_x + k * (PXM * 0.5), tb_y + 24),
                           size=(PXM * 0.5, 5),
                           fill="#333333" if k % 2 == 0 else "#ffffff",
                           stroke="#333333", stroke_width=0.4))

        return _make_responsive(dwg.tostring())

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
