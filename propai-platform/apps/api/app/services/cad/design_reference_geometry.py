"""표준설계 참조 기하(U3 R2) — design_payload/DXF를 표준 geometry로 정규화·썸네일.

표준 geometry 스키마(좌표 단위 px, scale_px_per_m=10 고정 — 프론트 CAD 스토어 호환):
  {
    "points":   [{"id", "x", "y"}],
    "lines":    [{"id", "start_point_id", "end_point_id"}],
    "surfaces": [{"id", "point_ids"}],
    "bbox":     {"min_x", "min_y", "max_x", "max_y", "width_m", "height_m"},
    "scale_px_per_m": 10.0,
    # 선택(있을 때만): "floor_count", "building_height_m"
  }

원칙(기존 커널 패턴): LLM·외부호출 없이 순수 결정론. 파싱 실패·빈 기하는
GeometryError로 명시 반환한다(침묵 폴백·가짜 기하 금지).
"""

from __future__ import annotations

import io
from typing import Any

import structlog

try:
    import svgwrite
except ImportError:
    svgwrite = None  # type: ignore[assignment]

try:
    import ezdxf
except ImportError:
    ezdxf = None  # type: ignore[assignment]

logger = structlog.get_logger(__name__)

STANDARD_SCALE_PX_PER_M = 10.0  # 1m = 10px (auto_design_engine.to_design_payload 동일)
THUMBNAIL_MAX_BYTES = 50 * 1024  # 썸네일 SVG 50KB 캡


class GeometryError(ValueError):
    """기하 정규화/파싱 실패 — 사유를 담은 명시 예외(침묵 폴백 금지)."""


def _bbox_of(points: list[dict[str, Any]], scale: float) -> dict[str, float]:
    xs = [float(p["x"]) for p in points]
    ys = [float(p["y"]) for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return {
        "min_x": round(min_x, 2), "min_y": round(min_y, 2),
        "max_x": round(max_x, 2), "max_y": round(max_y, 2),
        "width_m": round((max_x - min_x) / scale, 2),
        "height_m": round((max_y - min_y) / scale, 2),
    }


def _normalize_payload_form(payload: dict[str, Any]) -> dict[str, Any]:
    """design_payload 형({points,lines,surfaces[,scale]}) → 표준 geometry."""
    in_scale = float(payload.get("scale") or payload.get("scale_px_per_m")
                     or STANDARD_SCALE_PX_PER_M)
    if in_scale <= 0:
        raise GeometryError(f"scale은 양수여야 합니다(입력: {in_scale})")
    factor = STANDARD_SCALE_PX_PER_M / in_scale

    raw_points = payload.get("points") or []
    points: list[dict[str, Any]] = []
    for i, p in enumerate(raw_points):
        try:
            points.append({
                "id": str(p.get("id") or f"pt-{i}"),
                "x": round(float(p["x"]) * factor, 2),
                "y": round(float(p["y"]) * factor, 2),
            })
        except (KeyError, TypeError, ValueError) as exc:
            raise GeometryError(f"points[{i}] 좌표가 유효하지 않습니다: {p!r}") from exc
    if not points:
        raise GeometryError("기하 점(points)이 없습니다 — 빈 설계는 참조로 저장할 수 없습니다.")

    known = {p["id"] for p in points}
    lines: list[dict[str, Any]] = []
    for i, ln in enumerate(payload.get("lines") or []):
        sid = str(ln.get("start_point_id") or "")
        eid = str(ln.get("end_point_id") or "")
        if sid in known and eid in known:
            lines.append({"id": str(ln.get("id") or f"ln-{i}"),
                          "start_point_id": sid, "end_point_id": eid})
    surfaces: list[dict[str, Any]] = []
    for i, sf in enumerate(payload.get("surfaces") or []):
        pids = [str(pid) for pid in (sf.get("point_ids") or []) if str(pid) in known]
        if len(pids) >= 3:
            surfaces.append({"id": str(sf.get("id") or f"pg-{i}"), "point_ids": pids})

    out: dict[str, Any] = {
        "points": points, "lines": lines, "surfaces": surfaces,
        "bbox": _bbox_of(points, STANDARD_SCALE_PX_PER_M),
        "scale_px_per_m": STANDARD_SCALE_PX_PER_M,
    }
    if payload.get("floor_count"):
        out["floor_count"] = int(payload["floor_count"])
    if payload.get("building_height_m"):
        out["building_height_m"] = float(payload["building_height_m"])
    return out


def _normalize_shapes_form(payload: dict[str, Any]) -> dict[str, Any]:
    """shapes 형({shapes:[{points:[{x,y}],closed}], unit}) → 표준 geometry.

    unit="m"(기본)이면 좌표를 m로 보고 ×10 px 변환, unit="px"면 그대로(스케일 10 가정).
    닫힌 도형(점 3개 이상)은 surface로, 연속 점은 line으로 변환한다.
    """
    unit = str(payload.get("unit") or "m").lower()
    factor = STANDARD_SCALE_PX_PER_M if unit == "m" else 1.0

    points: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    surfaces: list[dict[str, Any]] = []
    for si, shape in enumerate(payload.get("shapes") or []):
        raw = shape.get("points") or []
        if len(raw) < 2:
            continue  # 점 1개 이하는 형상이 아님
        ids: list[str] = []
        for pi, p in enumerate(raw):
            try:
                pid = f"pt-s{si}-{pi}"
                points.append({"id": pid,
                               "x": round(float(p["x"]) * factor, 2),
                               "y": round(float(p["y"]) * factor, 2)})
                ids.append(pid)
            except (KeyError, TypeError, ValueError) as exc:
                raise GeometryError(
                    f"shapes[{si}].points[{pi}] 좌표가 유효하지 않습니다: {p!r}") from exc
        closed = bool(shape.get("closed")) and len(ids) >= 3
        seg_count = len(ids) if closed else len(ids) - 1
        for i in range(seg_count):
            lines.append({"id": f"ln-s{si}-{i}",
                          "start_point_id": ids[i],
                          "end_point_id": ids[(i + 1) % len(ids)]})
        if closed:
            surfaces.append({"id": f"pg-s{si}", "point_ids": ids})

    if not points:
        raise GeometryError("shapes에서 기하 점을 추출하지 못했습니다.")
    return {
        "points": points, "lines": lines, "surfaces": surfaces,
        "bbox": _bbox_of(points, STANDARD_SCALE_PX_PER_M),
        "scale_px_per_m": STANDARD_SCALE_PX_PER_M,
    }


def normalize_geometry(payload: dict[str, Any]) -> dict[str, Any]:
    """design_payload/shapes 양형 입력을 표준 geometry로 정규화한다(멱등).

    - design_payload 형: {points, lines, surfaces[, scale, floor_count, ...]}
    - shapes 형: {shapes: [{points: [{x,y}], closed}], unit: "m"|"px"}
    표준형 재입력 시 동일 결과(라운드트립 안전). 실패는 GeometryError.
    """
    if not isinstance(payload, dict):
        raise GeometryError(f"geometry 입력은 dict여야 합니다(입력: {type(payload).__name__})")
    if payload.get("points"):
        return _normalize_payload_form(payload)
    if payload.get("shapes"):
        return _normalize_shapes_form(payload)
    raise GeometryError("지원 형식이 아닙니다 — points 또는 shapes 키가 필요합니다.")


def mass_dims(geometry: dict[str, Any]) -> dict[str, float]:
    """표준 geometry의 bbox에서 매스 치수를 역산한다(m)."""
    bbox = geometry.get("bbox")
    if not bbox:
        points = geometry.get("points") or []
        if not points:
            raise GeometryError("bbox/points가 없어 매스 치수를 역산할 수 없습니다.")
        scale = float(geometry.get("scale_px_per_m") or geometry.get("scale")
                      or STANDARD_SCALE_PX_PER_M)
        bbox = _bbox_of(points, scale)
    w = float(bbox.get("width_m") or 0.0)
    d = float(bbox.get("height_m") or 0.0)
    return {
        "building_width_m": round(w, 2),
        "building_depth_m": round(d, 2),
        "building_footprint_sqm": round(w * d, 2),
    }


def _render_svg(geometry: dict[str, Any], *, include_lines: bool) -> str:
    bbox = geometry.get("bbox") or _bbox_of(
        geometry["points"], float(geometry.get("scale_px_per_m") or STANDARD_SCALE_PX_PER_M))
    pad = 8.0
    vb_w = max(1.0, bbox["max_x"] - bbox["min_x"] + 2 * pad)
    vb_h = max(1.0, bbox["max_y"] - bbox["min_y"] + 2 * pad)
    dwg = svgwrite.Drawing(size=("240px", "240px"))
    dwg.viewbox(bbox["min_x"] - pad, bbox["min_y"] - pad, vb_w, vb_h)
    pt_map = {p["id"]: (float(p["x"]), float(p["y"])) for p in geometry.get("points", [])}
    for sf in geometry.get("surfaces", []):
        coords = [pt_map[pid] for pid in sf.get("point_ids", []) if pid in pt_map]
        if len(coords) >= 3:
            dwg.add(dwg.polygon(coords, fill="#e2e8f0", stroke="#475569", stroke_width=1))
    if include_lines:
        for ln in geometry.get("lines", []):
            a = pt_map.get(ln.get("start_point_id"))
            b = pt_map.get(ln.get("end_point_id"))
            if a and b:
                dwg.add(dwg.line(start=a, end=b, stroke="#64748b", stroke_width=0.8))
    return dwg.tostring()


def thumbnail_svg(geometry: dict[str, Any],
                  max_bytes: int = THUMBNAIL_MAX_BYTES) -> str | None:
    """표준 geometry의 미니 SVG 썸네일(50KB 캡).

    캡 초과 시 단계 축소(라인 제외 → 그래도 초과면 None) — 잘린 가짜 SVG 금지.
    svgwrite 미설치 시 None(썸네일은 부가 정보 — 기하 저장 자체는 영향 없음).
    """
    if svgwrite is None:
        return None
    if not geometry.get("points"):
        return None
    try:
        svg = _render_svg(geometry, include_lines=True)
        if len(svg.encode("utf-8")) <= max_bytes:
            return svg
        svg = _render_svg(geometry, include_lines=False)  # 단계 축소: 면만 렌더
        if len(svg.encode("utf-8")) <= max_bytes:
            return svg
        logger.warning("thumbnail_svg_over_cap", bytes=len(svg.encode("utf-8")))
        return None
    except Exception:  # noqa: BLE001 — 썸네일 실패는 저장 자체를 막지 않는다
        logger.warning("thumbnail_svg_render_failed", exc_info=True)
        return None


def dxf_to_geometry(data: bytes) -> dict[str, Any]:
    """DXF 바이트 → 표준 geometry(도면 단위 1=1m 가정, 결정론).

    LWPOLYLINE/POLYLINE(닫힘 → surface)·LINE 엔티티를 추출한다.
    ezdxf 미설치·파싱 실패·기하 엔티티 0건은 GeometryError(명시 예외).
    """
    if ezdxf is None:
        raise GeometryError("ezdxf 미설치 — DXF 기하 추출을 사용할 수 없습니다.")
    if not data:
        raise GeometryError("빈 DXF 데이터입니다.")
    try:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        doc = ezdxf.read(io.StringIO(text))
    except GeometryError:
        raise
    except Exception as exc:  # noqa: BLE001 — ezdxf 내부 예외를 도메인 예외로 변환
        raise GeometryError(f"DXF 파싱 실패: {exc}") from exc

    shapes: list[dict[str, Any]] = []
    for entity in doc.modelspace():
        kind = entity.dxftype()
        if kind == "LWPOLYLINE":
            pts = [{"x": float(p[0]), "y": float(p[1])} for p in entity.get_points()]
            if len(pts) >= 2:
                shapes.append({"points": pts, "closed": bool(entity.closed)})
        elif kind == "POLYLINE":
            pts = [{"x": float(v.dxf.location.x), "y": float(v.dxf.location.y)}
                   for v in entity.vertices]
            if len(pts) >= 2:
                shapes.append({"points": pts, "closed": bool(entity.is_closed)})
        elif kind == "LINE":
            shapes.append({"points": [
                {"x": float(entity.dxf.start.x), "y": float(entity.dxf.start.y)},
                {"x": float(entity.dxf.end.x), "y": float(entity.dxf.end.y)},
            ], "closed": False})

    if not shapes:
        raise GeometryError(
            "DXF에서 기하 엔티티(LWPOLYLINE/POLYLINE/LINE)를 찾지 못했습니다.")
    geometry = _normalize_shapes_form({"shapes": shapes, "unit": "m"})
    logger.info("dxf_to_geometry", shapes=len(shapes),
                points=len(geometry["points"]), surfaces=len(geometry["surfaces"]))
    return geometry
