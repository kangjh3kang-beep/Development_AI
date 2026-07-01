"""DXF 가져오기 서비스 — 외부 DXF를 CAD2.0 셰이프(캔버스 px 좌표)로 역변환.

parse_dxf_to_shapes는 ParametricCADService.create_dxf_from_edited_points의
정확한 역변환(m→px, y축 반전, bbox 정규화)을 수행한다 — 내보낸 DXF를
다시 가져와도 좌표가 보존된다(왕복 무결성, ±0.01).

정직 원칙:
- 파싱 불가(손상/비DXF)면 ValueError — 가짜 셰이프 생성 금지.
- 지원하지 않는 엔티티는 버리지 않고 ignored:[{type,count}]로 투명 보고.
- 단위는 $INSUNITS 헤더 우선, 0/미상이면 bbox 휴리스틱(출처를 unit.source에 명시).
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

try:
    import ezdxf
    from ezdxf import recover as _ezdxf_recover
except ImportError:
    ezdxf = None  # type: ignore[assignment]
    _ezdxf_recover = None  # type: ignore[assignment]

import structlog

logger = structlog.get_logger()

# ── 단위 ──

# $INSUNITS 코드 → (단위명, m 환산계수). 지원 외 코드/0(무단위)은 bbox 휴리스틱.
_INSUNITS_TO_M: dict[int, tuple[str, float]] = {
    1: ("inch", 0.0254),
    4: ("mm", 0.001),
    5: ("cm", 0.01),
    6: ("m", 1.0),
}

# bbox 최대변이 이 값을 넘으면 mm 도면으로 추정(한 변 500m 초과 건축도면은 비현실적)
_HEURISTIC_MM_THRESHOLD = 500.0

# DXF 표준 레이어 → CAD2.0 셰이프 레이어 역매핑
# (parametric_cad_service.SHAPE_LAYER_MAP의 역 — 왕복 시 레이어 보존)
_DXF_LAYER_TO_SHAPE: dict[str, str] = {
    "WALL": "outline",
    "WALL_INTERIOR": "wall",
    "DIM": "dim",
    "TEXT": "note",
}


def _read_document(dxf_bytes: bytes) -> Any:
    """DXF 바이트 → ezdxf 문서. readfile 실패 시 recover로 복구 재시도.

    그래도 실패하면 ValueError(정직 — 가짜 문서 생성 금지).
    """
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(dxf_bytes)
            tmp_path = tmp.name
        try:
            return ezdxf.readfile(tmp_path)
        except Exception as first_err:  # noqa: BLE001 — 손상 파일은 recover로 재시도
            logger.info("DXF readfile 실패 — recover 재시도", error=str(first_err)[:120])
            try:
                doc, _auditor = _ezdxf_recover.readfile(tmp_path)
                return doc
            except Exception as rec_err:  # noqa: BLE001
                raise ValueError(
                    f"DXF 파싱 불가(손상/비DXF 파일): {str(rec_err)[:120]}"
                ) from rec_err
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _extract_raw_entities(
    msp: Any, max_entities: int
) -> tuple[list[dict[str, Any]], dict[str, int], bool]:
    """모델스페이스에서 지원 엔티티를 원시좌표(도면 단위)로 추출한다.

    반환: (raw 엔트리 목록, ignored {타입: 개수}, truncated 여부).
    개별 엔티티 결함은 전체 실패 대신 ignored로 계수(부분 성공 허용).
    """
    raw: list[dict[str, Any]] = []
    ignored: dict[str, int] = {}
    truncated = False
    scanned = 0

    for e in msp:
        if scanned >= max_entities:
            truncated = True
            break
        scanned += 1
        dxftype = e.dxftype()
        try:
            if dxftype == "LWPOLYLINE":
                pts = [(float(x), float(y)) for x, y in e.get_points("xy")]
                if len(pts) < 2:
                    continue
                raw.append({"kind": "polyline", "layer": e.dxf.layer,
                            "points": pts, "closed": bool(e.closed)})
            elif dxftype == "POLYLINE":
                pts = [(float(v.dxf.location.x), float(v.dxf.location.y))
                       for v in e.vertices]
                if len(pts) < 2:
                    continue
                raw.append({"kind": "polyline", "layer": e.dxf.layer,
                            "points": pts, "closed": bool(e.is_closed)})
            elif dxftype == "LINE":
                raw.append({"kind": "line", "layer": e.dxf.layer,
                            "p1": (float(e.dxf.start.x), float(e.dxf.start.y)),
                            "p2": (float(e.dxf.end.x), float(e.dxf.end.y))})
            elif dxftype == "CIRCLE":
                raw.append({"kind": "circle", "layer": e.dxf.layer,
                            "center": (float(e.dxf.center.x), float(e.dxf.center.y)),
                            "r": float(e.dxf.radius)})
            elif dxftype == "TEXT":
                ins = e.dxf.insert
                raw.append({"kind": "label", "layer": e.dxf.layer,
                            "pos": (float(ins.x), float(ins.y)),
                            "text": str(e.dxf.text or "")})
            elif dxftype == "MTEXT":
                ins = e.dxf.insert
                try:
                    text = e.plain_text()
                except Exception:  # noqa: BLE001 — 인라인코드 결함 시 원문 폴백
                    text = str(getattr(e, "text", "") or "")
                raw.append({"kind": "label", "layer": e.dxf.layer,
                            "pos": (float(ins.x), float(ins.y)), "text": text})
            else:
                ignored[dxftype] = ignored.get(dxftype, 0) + 1
        except Exception:  # noqa: BLE001 — 개별 엔티티 결함은 ignored로 보고
            ignored[dxftype] = ignored.get(dxftype, 0) + 1

    return raw, ignored, truncated


def _anchors_of(entry: dict[str, Any]) -> list[tuple[float, float]]:
    """bbox 정규화 기준 앵커 좌표 — create_dxf_from_edited_points와 동일 규약.

    폴리라인=꼭짓점, 선=양 끝점, 원=중심(반경 제외), 라벨=삽입점.
    """
    kind = entry["kind"]
    if kind == "polyline":
        return list(entry["points"])
    if kind == "line":
        return [entry["p1"], entry["p2"]]
    if kind == "circle":
        return [entry["center"]]
    return [entry["pos"]]  # label


def _detect_unit(doc: Any, anchors: list[tuple[float, float]]) -> tuple[str, float, str]:
    """단위 확정: $INSUNITS 매핑 우선, 0/미상은 bbox 최대변 휴리스틱.

    반환: (단위명, m 환산계수, 출처 "insunits"|"heuristic").
    """
    try:
        code = int(doc.header.get("$INSUNITS", 0))
    except (ValueError, TypeError):
        code = 0
    if code in _INSUNITS_TO_M:
        name, factor = _INSUNITS_TO_M[code]
        return name, factor, "insunits"

    # 휴리스틱: bbox 최대변 > 500 → mm 도면(건축도면 관행), 이하 → m
    if anchors:
        xs = [x for x, _ in anchors]
        ys = [y for _, y in anchors]
        max_edge = max(max(xs) - min(xs), max(ys) - min(ys))
    else:
        max_edge = 0.0
    if max_edge > _HEURISTIC_MM_THRESHOLD:
        return "mm", 0.001, "heuristic"
    return "m", 1.0, "heuristic"


def _shoelace_area_px(points: list[dict[str, float]]) -> float:
    """px 폴리곤의 신발끈 면적(절댓값)."""
    n = len(points)
    if n < 3:
        return 0.0
    area2 = sum(
        points[i]["x"] * points[(i + 1) % n]["y"]
        - points[(i + 1) % n]["x"] * points[i]["y"]
        for i in range(n)
    )
    return abs(area2) / 2.0


def _main_outline_index(shapes: list[dict[str, Any]]) -> int | None:
    """닫힌 폴리라인 중 신발끈 면적 최대 셰이프의 인덱스(메인 외곽선). 없으면 None."""
    best_idx: int | None = None
    best_area = 0.0
    for i, s in enumerate(shapes):
        if s.get("kind") != "polyline" or not s.get("closed"):
            continue
        area = _shoelace_area_px(s.get("points") or [])
        if area > best_area:
            best_area = area
            best_idx = i
    return best_idx


def parse_dxf_to_shapes(
    dxf_bytes: bytes,
    scale_px_per_m: float = 10.0,
    max_entities: int = 5000,
) -> dict[str, Any]:
    """DXF 바이트를 CAD2.0 셰이프(px 좌표, 캔버스 y축 하향)로 파싱한다.

    - 좌표 변환: 도면단위 → m(단위 확정) → x_px=(x−minX)·scale,
      y_px=(maxY−y)·scale — create_dxf_from_edited_points의 정확한 역변환.
    - 추출: LWPOLYLINE/POLYLINE→polyline(closed,points), LINE→line,
      CIRCLE→circle, TEXT/MTEXT→label. 그 외는 ignored:[{type,count}].
    - 레이어: WALL→outline, WALL_INTERIOR→wall, DIM→dim, TEXT→note 역매핑.
      미상 레이어는 label→note, 그 외→wall(원본은 source_layer에 보존).
    - max_entities 초과 시 truncated=True로 중단(폭주 방지).

    반환: {shapes, unit:{detected,source}, scale_px_per_m, main_outline_index,
           ignored, truncated, shape_count, bounds_px:{width,height}}
    파싱 불가/빈 입력/잘못된 scale → ValueError(정직).
    """
    if scale_px_per_m <= 0:
        raise ValueError("scale_px_per_m는 0보다 커야 합니다")
    if max_entities <= 0:
        raise ValueError("max_entities는 0보다 커야 합니다")
    if not dxf_bytes:
        raise ValueError("빈 DXF 데이터")
    if ezdxf is None:
        raise ValueError("ezdxf 미설치 — DXF 가져오기를 사용할 수 없습니다")

    doc = _read_document(dxf_bytes)
    raw, ignored, truncated = _extract_raw_entities(doc.modelspace(), max_entities)

    all_anchors = [pt for entry in raw for pt in _anchors_of(entry)]
    unit_name, factor, unit_source = _detect_unit(doc, all_anchors)

    if all_anchors:
        min_x_m = min(x for x, _ in all_anchors) * factor
        max_x_m = max(x for x, _ in all_anchors) * factor
        min_y_m = min(y for _, y in all_anchors) * factor
        max_y_m = max(y for _, y in all_anchors) * factor
    else:
        min_x_m = max_x_m = min_y_m = max_y_m = 0.0

    def to_px(raw_pt: tuple[float, float]) -> tuple[float, float]:
        x_m = raw_pt[0] * factor
        y_m = raw_pt[1] * factor
        return (round((x_m - min_x_m) * scale_px_per_m, 4),
                round((max_y_m - y_m) * scale_px_per_m, 4))

    shapes: list[dict[str, Any]] = []
    for entry in raw:
        kind = entry["kind"]
        layer_raw = str(entry.get("layer") or "")
        shape_layer = _DXF_LAYER_TO_SHAPE.get(
            layer_raw.upper(), "note" if kind == "label" else "wall")
        if kind == "polyline":
            pts = [to_px(p) for p in entry["points"]]
            shapes.append({
                "kind": "polyline", "layer": shape_layer, "source_layer": layer_raw,
                "closed": entry["closed"],
                "points": [{"x": x, "y": y} for x, y in pts],
            })
        elif kind == "line":
            (x1, y1), (x2, y2) = to_px(entry["p1"]), to_px(entry["p2"])
            shapes.append({"kind": "line", "layer": shape_layer,
                           "source_layer": layer_raw,
                           "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        elif kind == "circle":
            cx, cy = to_px(entry["center"])
            shapes.append({"kind": "circle", "layer": shape_layer,
                           "source_layer": layer_raw, "cx": cx, "cy": cy,
                           "r": round(entry["r"] * factor * scale_px_per_m, 4)})
        else:  # label
            x, y = to_px(entry["pos"])
            shapes.append({"kind": "label", "layer": shape_layer,
                           "source_layer": layer_raw,
                           "x": x, "y": y, "text": entry["text"]})

    return {
        "shapes": shapes,
        "unit": {"detected": unit_name, "source": unit_source},
        "scale_px_per_m": scale_px_per_m,
        "main_outline_index": _main_outline_index(shapes),
        "ignored": [{"type": t, "count": c} for t, c in sorted(ignored.items())],
        "truncated": truncated,
        "shape_count": len(shapes),
        "bounds_px": {
            "width": round((max_x_m - min_x_m) * scale_px_per_m, 4),
            "height": round((max_y_m - min_y_m) * scale_px_per_m, 4),
        },
    }
