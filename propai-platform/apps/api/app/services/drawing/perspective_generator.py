"""아이소메트릭 투시도 SVG 생성기."""

from __future__ import annotations

import math
from typing import Any

try:
    import svgwrite
except ImportError:
    svgwrite = None  # type: ignore[assignment]


def _iso(x: float, y: float, z: float,
         cx: float, cy: float, sc: float = 1.0) -> tuple[float, float]:
    """3D → 아이소메트릭 30도 투영 좌표 변환."""
    cos30 = math.cos(math.radians(30))
    sin30 = math.sin(math.radians(30))
    sx = (x - y) * cos30 * sc + cx
    sy = -(x + y) * sin30 * sc - z * sc + cy
    return round(sx, 1), round(sy, 1)


class PerspectiveGenerator:
    """건물 아이소메트릭 투시도 SVG 생성."""

    def generate(self, params: dict[str, Any]) -> str:
        """params: building_w, building_d, floor_count, floor_height,
        basement_floors, facade_material, project_name."""
        if svgwrite is None:
            return self._fallback_svg(params)

        bw = params.get("building_w", 30.0)
        bd = params.get("building_d", 20.0)
        fc = params.get("floor_count", 5)
        fh = params.get("floor_height", 3.0)
        bf = params.get("basement_floors", 1)
        mat = params.get("facade_material", "concrete")
        name = params.get("project_name", "PropAI")

        total_h = fc * fh
        sc = 2.5  # 스케일 팩터
        cx, cy = 350, 400

        canvas_w = 700
        canvas_h = 600
        dwg = svgwrite.Drawing(size=(f"{canvas_w}px", f"{canvas_h}px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(canvas_w, canvas_h), fill="white"))

        g = dwg.g()
        dwg.add(g)

        # 색상 결정
        face_color = "#74b9ff" if mat == "glass" else "#b2bec3"
        side_color = "#0984e3" if mat == "glass" else "#636e72"
        top_color = "#dfe6e9"

        # 건물 본체 — 면 3개 (앞면, 옆면, 윗면)
        # 바닥 4꼭짓점
        p0 = _iso(0, 0, 0, cx, cy, sc)
        p1 = _iso(bw, 0, 0, cx, cy, sc)
        p2 = _iso(bw, bd, 0, cx, cy, sc)
        p3 = _iso(0, bd, 0, cx, cy, sc)
        # 상단 4꼭짓점
        t0 = _iso(0, 0, total_h, cx, cy, sc)
        t1 = _iso(bw, 0, total_h, cx, cy, sc)
        t2 = _iso(bw, bd, total_h, cx, cy, sc)
        t3 = _iso(0, bd, total_h, cx, cy, sc)

        # 앞면 (남측)
        front = [p0, p1, t1, t0]
        g.add(dwg.polygon(points=front, fill=face_color, stroke="#2d3436",
                          stroke_width=1.5, opacity=0.85))

        # 오른쪽 면 (동측)
        right = [p1, p2, t2, t1]
        g.add(dwg.polygon(points=right, fill=side_color, stroke="#2d3436",
                          stroke_width=1.5, opacity=0.85))

        # 윗면 (지붕)
        top = [t0, t1, t2, t3]
        g.add(dwg.polygon(points=top, fill=top_color, stroke="#2d3436",
                          stroke_width=1.5, opacity=0.9))

        # 층별 수평선 (앞면)
        for fi in range(1, fc):
            fz = fi * fh
            fl = _iso(0, 0, fz, cx, cy, sc)
            fr = _iso(bw, 0, fz, cx, cy, sc)
            g.add(dwg.line(start=fl, end=fr, stroke="#2d3436",
                           stroke_width=0.5, opacity=0.6))

        # 층별 수평선 (옆면)
        for fi in range(1, fc):
            fz = fi * fh
            fl = _iso(bw, 0, fz, cx, cy, sc)
            fr = _iso(bw, bd, fz, cx, cy, sc)
            g.add(dwg.line(start=fl, end=fr, stroke="#2d3436",
                           stroke_width=0.5, opacity=0.6))

        # 창호 패턴 (앞면)
        win_w = min(2.0, bw * 0.1)
        win_h = 1.2
        for fi in range(fc):
            for wi in range(max(1, int(bw / 8))):
                wx = 3.0 + wi * 8.0
                if wx + win_w > bw - 1.0:
                    break
                wz = fi * fh + 0.9
                wp0 = _iso(wx, 0, wz, cx, cy, sc)
                wp1 = _iso(wx + win_w, 0, wz, cx, cy, sc)
                wp2 = _iso(wx + win_w, 0, wz + win_h, cx, cy, sc)
                wp3 = _iso(wx, 0, wz + win_h, cx, cy, sc)
                g.add(dwg.polygon(points=[wp0, wp1, wp2, wp3],
                                  fill="#0984e3", stroke="#0984e3",
                                  stroke_width=0.3, opacity=0.4))

        # 지반선
        gl_y = _iso(0, 0, 0, cx, cy, sc)[1]
        g.add(dwg.line(start=(50, gl_y), end=(canvas_w - 50, gl_y),
                       stroke="#2d3436", stroke_width=1.5,
                       stroke_dasharray="5,3"))
        g.add(dwg.text("G.L.", insert=(canvas_w - 45, gl_y + 4),
                        font_size="9px", fill="#2d3436"))

        # 높이 라벨
        g.add(dwg.text(f"{total_h:.1f}m",
                        insert=(t0[0] - 30, (t0[1] + p0[1]) / 2),
                        font_size="10px", fill="#d63031", text_anchor="middle"))

        # 제목
        g.add(dwg.text(f"{name} 투시도 ({fc}F / {total_h:.1f}m)",
                        insert=(canvas_w / 2, 25),
                        font_size="12px", fill="#2d3436",
                        text_anchor="middle", font_weight="bold"))

        return dwg.tostring()

    @staticmethod
    def _fallback_svg(params: dict) -> str:
        """svgwrite 미설치 시 순수 문자열 SVG."""
        name = params.get("project_name", "PropAI")
        fc = params.get("floor_count", 5)
        fh = params.get("floor_height", 3.0)
        total_h = fc * fh
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="700" height="600">'
            f'<rect width="700" height="600" fill="white"/>'
            f'<rect x="150" y="100" width="400" height="350" fill="#b2bec3" '
            f'stroke="#2d3436" stroke-width="2"/>'
            f'<text x="350" y="25" text-anchor="middle" font-size="12" '
            f'font-weight="bold">{name} 투시도 ({fc}F / {total_h:.1f}m)</text>'
            f'</svg>'
        )
