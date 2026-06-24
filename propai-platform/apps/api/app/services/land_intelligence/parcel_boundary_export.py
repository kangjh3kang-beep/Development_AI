"""구획도(필지 경계) export 직렬화/렌더 — GeoJSON(무의존)·PNG(matplotlib).

parcel_boundaries() 결과(features+merged_geometry)를 입력받아 다운로드 산출물로 변환한다.
라우터(fastapi)와 분리해 단위 테스트 가능하게 한다. PDF는 parcel_boundary_pdf(reportlab, prod 전용).
"""
from __future__ import annotations

from typing import Any

# 용도지역별 채움색(토지이음 범례 근사) — 구획도 렌더 공용.
ZONE_COLORS: dict[str, str] = {
    "제1종전용주거지역": "#8B9DC3", "제2종전용주거지역": "#7A8DB8",
    "제1종일반주거지역": "#A8C8A0", "제2종일반주거지역": "#C0D8B0", "제3종일반주거지역": "#D4E8A0",
    "준주거지역": "#E8D490", "중심상업지역": "#F0C860", "일반상업지역": "#F0D870",
    "근린상업지역": "#F4E080", "유통상업지역": "#F4E8A0",
    "전용공업지역": "#C8B0D0", "일반공업지역": "#D0B8D8", "준공업지역": "#D8C0E0",
    "보전녹지지역": "#50A050", "생산녹지지역": "#70B870", "자연녹지지역": "#90C890",
}


def zone_fill(zone: str | None) -> str:
    if not zone:
        return "#cccccc"
    for k, v in ZONE_COLORS.items():
        if k in zone or zone in k:
            return v
    return "#cbd5e1"


def export_geojson(result: dict[str, Any]) -> dict[str, Any]:
    """features + merged_geometry → GeoJSON FeatureCollection(무의존·결정론)."""
    feats: list[dict] = []
    for i, f in enumerate(result.get("features") or []):
        if not f.get("geometry"):
            continue
        a = f.get("area_sqm")
        feats.append({
            "type": "Feature",
            "geometry": f["geometry"],
            "properties": {
                "index": i + 1, "pnu": f.get("pnu"), "address": f.get("address"),
                "area_sqm": a,
                "area_pyeong": round(a / 3.305785, 1) if a else None,
                "zone_type": f.get("zone_type"), "jimok": f.get("jimok"),
            },
        })
    if result.get("merged_geometry"):
        feats.append({
            "type": "Feature", "geometry": result["merged_geometry"],
            "properties": {"role": "merged_boundary", "label": "통합개발 외곽선",
                           "total_area_sqm": result.get("total_area_sqm")},
        })
    return {
        "type": "FeatureCollection", "features": feats,
        "properties": {"total_area_sqm": result.get("total_area_sqm"),
                       "parcel_count": result.get("parcel_count"),
                       "generated_by": "PropAI 구획도 export"},
    }


def export_png(result: dict[str, Any]) -> bytes:
    """구획도 PNG(matplotlib) — 필지 폴리곤(용도지역 색)+통합 외곽선(빨강 점선)+번호.

    지도 라벨은 번호+면적(㎡)만(한글 폰트 의존 회피 — 주소 매핑은 GeoJSON/PDF가 보유).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import shape
    from io import BytesIO

    fig, ax = plt.subplots(figsize=(8, 8))
    for i, f in enumerate(result.get("features") or []):
        geom = f.get("geometry")
        if not geom:
            continue
        g = shape(geom).buffer(0)
        polys = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
        for poly in polys:
            xs, ys = poly.exterior.xy
            ax.fill(xs, ys, alpha=0.45, fc=zone_fill(f.get("zone_type")), ec="#3b82f6", lw=1.2)
        c = g.centroid
        a = f.get("area_sqm")
        ax.annotate(f"{i + 1}\n{round(a)}m2" if a else f"{i + 1}", (c.x, c.y),
                    ha="center", va="center", fontsize=8, fontweight="bold", color="#1e293b")
    if result.get("merged_geometry"):
        mg = shape(result["merged_geometry"]).buffer(0)
        polys = [mg] if mg.geom_type == "Polygon" else list(getattr(mg, "geoms", []))
        for poly in polys:
            xs, ys = poly.exterior.xy
            ax.plot(xs, ys, color="#ef4444", lw=2.0, ls="--")
    ax.set_aspect("equal")
    ax.axis("off")
    ta = result.get("total_area_sqm") or 0
    ax.set_title(f"Parcel boundary ({result.get('parcel_count')} lots, "
                 f"{round(ta):,}m2 / {round(ta / 3.305785):,}py)", fontsize=11)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
