"""일영분석 시뮬레이터 — 태양 고도/방위각 기반 건물 그림자 SVG 생성."""

from __future__ import annotations

import math
from typing import Any

try:
    import svgwrite
except ImportError:
    svgwrite = None  # type: ignore[assignment]

# 태양 적위 (declination) 근사값
DECLINATION = {
    "winter_solstice": -23.45,  # 동지 (12월 22일)
    "summer_solstice": 23.45,   # 하지 (6월 21일)
    "equinox": 0.0,              # 춘/추분
}


def sun_position(latitude: float, hour: float, declination: float
                 ) -> tuple[float, float]:
    """태양 고도(altitude)와 방위각(azimuth)을 계산한다.

    Returns:
        (altitude_deg, azimuth_deg) — 고도 0~90, 방위각 0~360 (남=180)
    """
    lat_rad = math.radians(latitude)
    dec_rad = math.radians(declination)
    # 시간각 (hour angle): 정오=0, 오전=음수, 오후=양수
    ha_rad = math.radians((hour - 12.0) * 15.0)

    # 태양 고도
    sin_alt = (math.sin(lat_rad) * math.sin(dec_rad) +
               math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    altitude = math.degrees(math.asin(sin_alt))

    # 태양 방위각
    cos_alt = math.cos(math.radians(altitude))
    if cos_alt == 0:
        azimuth = 180.0
    else:
        cos_az = ((math.sin(dec_rad) - math.sin(lat_rad) * sin_alt) /
                  (math.cos(lat_rad) * cos_alt))
        cos_az = max(-1.0, min(1.0, cos_az))
        azimuth = math.degrees(math.acos(cos_az))
        if hour > 12.0:
            azimuth = 360.0 - azimuth

    return round(altitude, 2), round(azimuth, 2)


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone chain 볼록껍질(결정론·math만, numpy 불요).

    내부점·변 위 공선점을 제거해 그림자 다각형이 비볼록/자기교차로 음영을 과대 산정하는 것을 막는다.
    점이 3개 미만이면 입력을 그대로 반환(축퇴 방지).
    """
    pts = sorted(set(points))
    if len(pts) < 3:
        return list(points)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def shadow_polygon(sun_alt: float, sun_az: float,
                   bw: float, bd: float, bh: float
                   ) -> list[tuple[float, float]]:
    """건물 그림자 다각형 꼭짓점을 계산한다 (평면 2D 볼록껍질).

    건물 바닥 좌하단이 (0,0), x=동, y=북 기준. 단일 직육면체 매스의 평면투영 근사이며
    지형 기복·반사·인접 건물 차폐는 미반영(보수적 단순화) — 정밀 분석은 IFC/지형 결합 필요.
    """
    if sun_alt <= 0:
        return []

    tan_alt = math.tan(math.radians(sun_alt))
    if tan_alt == 0:
        return []

    shadow_len = bh / tan_alt
    az_rad = math.radians(sun_az)

    # 그림자 이동 벡터 (태양 반대 방향)
    dx = -shadow_len * math.sin(az_rad)
    dy = -shadow_len * math.cos(az_rad)

    # 건물 바닥 4꼭짓점
    corners = [(0, 0), (bw, 0), (bw, bd), (0, bd)]
    # 그림자 투영점
    shadow_pts = [(x + dx, y + dy) for x, y in corners]

    # 건물 + 그림자 꼭짓점의 진짜 볼록껍질(내부점·공선점 제거 — 비볼록/자기교차 과대 음영 방지).
    hull = _convex_hull(corners + shadow_pts)
    return [(round(x, 1), round(y, 1)) for x, y in hull]


class ShadowSimulator:
    """일영분석 SVG 생성."""

    def generate(self, params: dict[str, Any]) -> str:
        """일영분석 SVG를 생성한다.

        params: latitude, building_w, building_d, building_h,
                analysis_date (winter_solstice/summer_solstice/equinox),
                time_slots (list[float], 시간 e.g. [9,10,11,12,13,14,15])
        """
        lat = params.get("latitude", 37.5)
        bw = params.get("building_w", 30.0)
        bd = params.get("building_d", 20.0)
        bh = params.get("building_h", 15.0)
        date_key = params.get("analysis_date", "winter_solstice")
        times = params.get("time_slots", [9, 10, 11, 12, 13, 14, 15])

        dec = DECLINATION.get(date_key, -23.45)

        if svgwrite is None:
            return self._fallback_svg(params, dec)

        scale = 3.0  # 1m = 3px
        margin = 120
        canvas_w = int(bw * scale + margin * 4)
        canvas_h = int(bd * scale + margin * 4)

        dwg = svgwrite.Drawing(size=(f"{canvas_w}px", f"{canvas_h}px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(canvas_w, canvas_h), fill="white"))

        # 건물 원점 (캔버스 중앙 부근)
        ox = canvas_w / 2 - bw * scale / 2
        oy = canvas_h / 2 - bd * scale / 2

        g = dwg.g(transform=f"translate({ox},{oy})")
        dwg.add(g)

        # 그림자 색상 그래디언트
        shadow_colors = [
            "#fdcb6e", "#f39c12", "#e67e22", "#d35400",
            "#e74c3c", "#c0392b", "#8e44ad",
        ]

        for i, hour in enumerate(times):
            alt, az = sun_position(lat, hour, dec)
            if alt <= 0:
                continue

            poly = shadow_polygon(alt, az, bw, bd, bh)
            if not poly:
                continue

            svg_pts = [(x * scale, -y * scale + bd * scale) for x, y in poly]
            color = shadow_colors[i % len(shadow_colors)]
            g.add(dwg.polygon(points=svg_pts, fill=color, opacity=0.25,
                              stroke=color, stroke_width=0.5))
            # 시간 라벨
            if svg_pts:
                lx = sum(p[0] for p in svg_pts) / len(svg_pts)
                ly = sum(p[1] for p in svg_pts) / len(svg_pts)
                g.add(dwg.text(f"{int(hour)}:00",
                               insert=(lx, ly),
                               font_size="8px", fill=color,
                               text_anchor="middle", font_weight="bold"))

        # 건물 (하늘색 직사각형)
        g.add(dwg.rect(insert=(0, 0), size=(bw * scale, bd * scale),
                        fill="#74b9ff", stroke="#2d3436", stroke_width=2,
                        opacity=0.8))
        g.add(dwg.text("건물", insert=(bw * scale / 2, bd * scale / 2 + 4),
                        font_size="10px", fill="#2d3436",
                        text_anchor="middle", font_weight="bold"))

        # 방위
        g.add(dwg.text("N", insert=(bw * scale / 2, -15),
                        font_size="12px", fill="#2d3436",
                        text_anchor="middle", font_weight="bold"))

        # 날짜 라벨
        date_labels = {
            "winter_solstice": "동지 (12/22)",
            "summer_solstice": "하지 (6/21)",
            "equinox": "춘추분 (3/21, 9/23)",
        }
        date_label = date_labels.get(date_key, date_key)

        # 제목
        g.add(dwg.text(
            f"일영분석 — {date_label} / 위도 {lat}°",
            insert=(bw * scale / 2, -35),
            font_size="11px", fill="#2d3436",
            text_anchor="middle", font_weight="bold",
        ))

        return dwg.tostring()

    @staticmethod
    def _fallback_svg(params: dict, dec: float) -> str:
        bw = params.get("building_w", 30.0)
        bd = params.get("building_d", 20.0)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="500">'
            f'<rect width="600" height="500" fill="white"/>'
            f'<rect x="200" y="150" width="{bw*3}" height="{bd*3}" '
            f'fill="#74b9ff" stroke="#2d3436" stroke-width="2"/>'
            f'<text x="300" y="30" text-anchor="middle" font-size="11" '
            f'font-weight="bold">일영분석 (declination={dec})</text>'
            f'</svg>'
        )
