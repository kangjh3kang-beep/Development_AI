"""UP2 — CAD 업로드 연동 허브.

parse_dxf_to_shapes(dxf_import_service)의 단일 파싱 결과를 다운스트림 네 소비형으로
결정론·멱등 분배한다(외부호출 0·LLM 0). 각 소비형은 기존 모듈의 계약을 그대로
재사용하며, 허브는 형식 변환·라우팅만 담당한다(기하 자체는 변형하지 않음).

소비형:
  - editing_shapes   : CADEditor 재편집용 정제 셰이프(sanitize 통과분).
  - geometry_payload : 표준 geometry(design_reference_geometry.normalize_geometry 재사용).
  - design_raw       : 법규 기하검증용 design_raw(geometry_adapter.design_payload_from_shapes 계약).
  - rooms            : 실(室) 추출(shapes_to_rooms.extract_rooms — UP1 산출, import 사용).
  - params_hint      : 메인 외곽선 bbox·면적에서 역산한 설계 파라미터 힌트(출처='도면추정').
  - diagnostics      : 빈/무효 입력에 대한 정직한 사유 목록.

정직 원칙: 파싱 결과가 비거나 무효면 가짜 기하·기본값을 만들지 않고 None +
diagnostics로 명시한다. UP1(rooms) 미배포 환경에서도 허브 자체는 동작하며,
rooms는 None + diagnostics로 정직하게 비활성된다(다른 소비형 무영향).
"""

from __future__ import annotations

from typing import Any

import structlog

# 동일 패키지(cad) 모듈 — import만 재사용(파일 비중첩, 기하 변형 없음).
from app.services.cad.design_reference_geometry import (
    GeometryError,
    normalize_geometry,
)
from app.services.design_audit.geometry_adapter import design_payload_from_shapes

logger = structlog.get_logger(__name__)

# parse_dxf_to_shapes 기본 스케일과 동일(키 부재 시 폴백) — 1m = 10px.
_DEFAULT_SCALE_PX_PER_M = 10.0

# params_hint 출처 라벨 — brief 등 상위 출처에 병합 시 하위 우선(도면추정).
_PARAMS_SOURCE = "도면추정"


# ─────────────────────────────────────────────────────────────────────────────
# 내부 유틸 — 좌표/면적
# ─────────────────────────────────────────────────────────────────────────────
def _finite(value: Any) -> float | None:
    """유한 실수만 통과(bool·NaN·inf·비수치 → None)."""
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # NaN/inf 차단(NaN != NaN, inf는 비교로 검출).
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _shape_xy_points(shape: dict[str, Any]) -> list[tuple[float, float]] | None:
    """polyline 셰이프의 정점을 (x, y) 튜플 목록으로 추출(유한값만). 무효면 None."""
    raw = shape.get("points")
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    out: list[tuple[float, float]] = []
    for p in raw:
        if not isinstance(p, dict):
            return None
        x, y = _finite(p.get("x")), _finite(p.get("y"))
        if x is None or y is None:
            return None
        out.append((x, y))
    return out


def _shoelace_area_px(pts: list[tuple[float, float]]) -> float:
    """px 폴리곤의 신발끈 면적(절댓값). 점 3개 미만은 0."""
    n = len(pts)
    if n < 3:
        return 0.0
    area2 = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                for i in range(n))
    return abs(area2) / 2.0


def _scale_of(parse_result: dict[str, Any]) -> float:
    """parse_result에서 scale_px_per_m을 안전 추출(무효 시 기본 10.0)."""
    scale = _finite(parse_result.get("scale_px_per_m"))
    if scale is None or scale <= 0:
        return _DEFAULT_SCALE_PX_PER_M
    return scale


# ─────────────────────────────────────────────────────────────────────────────
# 소비형 1 — editing_shapes (sanitize)
# ─────────────────────────────────────────────────────────────────────────────
def _sanitize_shapes(shapes: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """CADEditor 재편집용 셰이프 정제 — kind별 필수 필드·유한 좌표 검증.

    무효 항목은 폐기하고 사유를 issues에 남긴다(조용한 무시 금지). 기하 좌표는
    변형하지 않는다(검증 패스스루). 알 수 없는 kind는 제외.
    """
    out: list[dict[str, Any]] = []
    issues: list[str] = []
    for i, s in enumerate(shapes):
        if not isinstance(s, dict):
            issues.append(f"shapes[{i}] 무효(객체 아님) — 제외")
            continue
        kind = s.get("kind")
        if kind == "polyline":
            pts = _shape_xy_points(s)
            if pts is None:
                issues.append(f"shapes[{i}] polyline 정점 무효(2점 미만/좌표 결손) — 제외")
                continue
            out.append(s)
        elif kind == "line":
            coords = [_finite(s.get(k)) for k in ("x1", "y1", "x2", "y2")]
            if any(c is None for c in coords):
                issues.append(f"shapes[{i}] line 좌표 결손 — 제외")
                continue
            out.append(s)
        elif kind == "circle":
            cx, cy, r = _finite(s.get("cx")), _finite(s.get("cy")), _finite(s.get("r"))
            if cx is None or cy is None or r is None or r <= 0:
                issues.append(f"shapes[{i}] circle 좌표/반경 무효 — 제외")
                continue
            out.append(s)
        elif kind == "label":
            x, y = _finite(s.get("x")), _finite(s.get("y"))
            if x is None or y is None:
                issues.append(f"shapes[{i}] label 좌표 결손 — 제외")
                continue
            out.append(s)
        else:
            issues.append(f"shapes[{i}] 알 수 없는 kind={kind!r} — 제외")
    return out, issues


# ─────────────────────────────────────────────────────────────────────────────
# 소비형 2 — geometry_payload (normalize_geometry 재사용)
# ─────────────────────────────────────────────────────────────────────────────
def _geometry_payload(
    sanitized: list[dict[str, Any]], scale: float
) -> tuple[dict[str, Any] | None, str | None]:
    """정제 셰이프를 normalize_geometry 입력(shapes 형)으로 변환해 표준 geometry 생성.

    parse 결과 좌표(px)를 scale_px_per_m으로 m 역산해 unit='m'로 전달한다 —
    normalize_geometry가 표준 10px/m로 재변환하므로 임의 scale 입력에도 안전하다.
    polyline은 정점·closed를 그대로, line은 2점 개방 셰이프로 매핑한다(circle/label은
    점 형상이 아니므로 기하 정규화 대상에서 제외 — normalize_geometry 계약과 동일).

    Returns: (표준 geometry | None, note | None). 점 추출 실패는 None + note.
    """
    geom_shapes: list[dict[str, Any]] = []
    for s in sanitized:
        kind = s.get("kind")
        if kind == "polyline":
            pts = _shape_xy_points(s)
            if pts is None:
                continue
            geom_shapes.append({
                "points": [{"x": x / scale, "y": y / scale} for x, y in pts],
                "closed": bool(s.get("closed")),
            })
        elif kind == "line":
            coords = [_finite(s.get(k)) for k in ("x1", "y1", "x2", "y2")]
            if any(c is None for c in coords):
                continue  # sanitize 통과분은 도달 불가 — 방어적 가드
            x1, y1, x2, y2 = coords
            geom_shapes.append({
                "points": [{"x": x1 / scale, "y": y1 / scale},
                           {"x": x2 / scale, "y": y2 / scale}],
                "closed": False,
            })
    if not geom_shapes:
        return None, "점/선 형상이 없어 표준 geometry 생성 불가(circle/label만 존재 또는 빈 도면)"
    try:
        return normalize_geometry({"shapes": geom_shapes, "unit": "m"}), None
    except GeometryError as exc:
        return None, f"geometry 정규화 실패: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
# 소비형 3 — design_raw (geometry_adapter.design_payload_from_shapes 계약)
# ─────────────────────────────────────────────────────────────────────────────
def _design_raw(
    sanitized: list[dict[str, Any]], scale: float
) -> dict[str, Any]:
    """정제 셰이프 → design_payload_from_shapes 입력(points/lines/surfaces, id 자동부여).

    계약: 닫힌 polygon → surface, 전 polyline 정점 → points, 각 변 → lines.
    좌표는 변형하지 않고 px 그대로 둔다(design_payload_from_shapes가 scale로 해석).
    중복 정점은 ID를 공유하지 않고 셰이프·인덱스로 결정론 부여(기하 보존). 그 뒤
    design_payload_from_shapes로 검증 패스스루한다.

    Returns: design_payload_from_shapes 출력({valid, design, issues}).
    """
    points: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    surfaces: list[dict[str, Any]] = []

    for si, s in enumerate(sanitized):
        kind = s.get("kind")
        if kind == "polyline":
            pts = _shape_xy_points(s)
            if pts is None:
                continue
            ids: list[str] = []
            for pi, (x, y) in enumerate(pts):
                pid = f"pt-s{si}-{pi}"
                points.append({"id": pid, "x": x, "y": y})
                ids.append(pid)
            closed = bool(s.get("closed")) and len(ids) >= 3
            seg_count = len(ids) if closed else len(ids) - 1
            for i in range(seg_count):
                lines.append({
                    "id": f"ln-s{si}-{i}",
                    "start_point_id": ids[i],
                    "end_point_id": ids[(i + 1) % len(ids)],
                })
            if closed:
                surfaces.append({"id": f"pg-s{si}", "point_ids": ids})
        elif kind == "line":
            x1, y1 = _finite(s.get("x1")), _finite(s.get("y1"))
            x2, y2 = _finite(s.get("x2")), _finite(s.get("y2"))
            if None in (x1, y1, x2, y2):
                continue
            a, b = f"pt-s{si}-0", f"pt-s{si}-1"
            points.append({"id": a, "x": x1, "y": y1})
            points.append({"id": b, "x": x2, "y": y2})
            lines.append({"id": f"ln-s{si}-0", "start_point_id": a, "end_point_id": b})
        # circle/label은 design_raw(점/면 기반 법규검증) 대상이 아님 — 제외.

    payload = {
        "points": points,
        "lines": lines,
        "surfaces": surfaces,
        "scale": scale,
    }
    return design_payload_from_shapes(payload)


# ─────────────────────────────────────────────────────────────────────────────
# 소비형 4 — rooms (UP1: shapes_to_rooms.extract_rooms — import 사용)
# ─────────────────────────────────────────────────────────────────────────────
def _rooms(
    shapes: list[dict[str, Any]], scale: float
) -> tuple[Any | None, str | None]:
    """UP1 shapes_to_rooms.extract_rooms로 실(室)을 추출한다(import만 사용).

    extract_rooms 계약: (shapes: 도형 dict 리스트, scale_px_per_m) → {rooms, warnings}.
    UP1 모듈은 별도 워크패키지 산출물이다. 미배포(ImportError) 또는 호출 실패 시
    가짜 실 데이터를 만들지 않고 None + 사유를 반환한다(정직). rooms 비활성은
    다른 소비형(editing/geometry/design_raw/params)에 영향을 주지 않는다.

    Returns: (extract_rooms 출력 | None, note | None).
    """
    try:
        from app.services.cad.shapes_to_rooms import extract_rooms
    except ImportError as exc:
        return None, f"실 추출 모듈(shapes_to_rooms) 미배포 — rooms 미산출(가짜 실 금지): {str(exc)[:120]}"
    try:
        return extract_rooms(shapes, scale_px_per_m=scale), None
    except Exception as exc:  # noqa: BLE001 — UP1 내부 예외를 허브 사유로 변환(전파 차단)
        logger.warning("rooms_extract_failed", error=str(exc)[:160])
        return None, f"실 추출 실패 — rooms 미산출: {str(exc)[:120]}"


# ─────────────────────────────────────────────────────────────────────────────
# 소비형 5 — params_hint (메인 외곽선 bbox·면적 역산)
# ─────────────────────────────────────────────────────────────────────────────
def _main_outline_points(
    parse_result: dict[str, Any]
) -> list[tuple[float, float]] | None:
    """parse_result.main_outline_index가 가리키는 닫힌 폴리라인의 정점(px). 무효면 None.

    인덱스는 원본 shapes 기준이므로 원본에서 조회한다(sanitize 후 인덱스 어긋남 방지).
    """
    idx = parse_result.get("main_outline_index")
    if not isinstance(idx, int):
        return None
    shapes = parse_result.get("shapes")
    if not isinstance(shapes, list) or not (0 <= idx < len(shapes)):
        return None
    shape = shapes[idx]
    if not isinstance(shape, dict) or shape.get("kind") != "polyline" or not shape.get("closed"):
        return None
    return _shape_xy_points(shape)


def _params_hint(
    parse_result: dict[str, Any], sanitized: list[dict[str, Any]], scale: float
) -> tuple[dict[str, Any] | None, str | None]:
    """메인 외곽선 bbox → building_width/depth_m(scale 역산), 닫힌폴리곤 면적합 → building_area_sqm.

    - 폭/깊이: 메인 외곽선 bbox의 (max_x-min_x)/scale, (max_y-min_y)/scale.
    - 면적: 모든 닫힌 폴리라인 신발끈 면적(px²) 합 / scale² → sqm.
    - 출처 source='도면추정'(brief 등 상위 입력에 병합 시 하위 우선).

    Returns: (params dict | None, note | None). 산출 불가(닫힌 외곽선 없음)는 None + note.
    """
    params: dict[str, Any] = {}

    outline = _main_outline_points(parse_result)
    if outline:
        xs = [x for x, _ in outline]
        ys = [y for _, y in outline]
        width_m = round((max(xs) - min(xs)) / scale, 2)
        depth_m = round((max(ys) - min(ys)) / scale, 2)
        if width_m > 0:
            params["building_width_m"] = width_m
        if depth_m > 0:
            params["building_depth_m"] = depth_m

    # 면적: 정제 셰이프 중 닫힌 폴리라인 신발끈 면적 합(px²→sqm).
    area_px2 = 0.0
    for s in sanitized:
        if s.get("kind") != "polyline" or not s.get("closed"):
            continue
        pts = _shape_xy_points(s)
        if pts is not None:
            area_px2 += _shoelace_area_px(pts)
    if area_px2 > 0:
        params["building_area_sqm"] = round(area_px2 / (scale * scale), 2)

    if not params:
        return None, "닫힌 외곽선/면적이 없어 파라미터 힌트 산출 불가(메인 외곽선 미검출)"
    params["source"] = _PARAMS_SOURCE
    return params, None


# ─────────────────────────────────────────────────────────────────────────────
# 진입점 — distribute
# ─────────────────────────────────────────────────────────────────────────────
def distribute(parse_result: dict[str, Any] | None) -> dict[str, Any]:
    """parse_dxf_to_shapes 출력을 네 소비형 + params_hint로 결정론·멱등 분배한다.

    멱등: 동일 입력 → 동일 출력(외부호출·LLM·난수 없음). 빈/무효 입력은 각 소비형을
    None으로 두고 diagnostics에 사유를 남긴다(가짜 기하 금지).

    Args:
        parse_result: parse_dxf_to_shapes 반환({shapes, unit, scale_px_per_m,
            main_outline_index, ...}). None/무효도 허용(diagnostics로 보고).

    Returns:
        {
          "editing_shapes":   list[dict],          # sanitize 통과분(빈 리스트 가능)
          "geometry_payload": dict | None,         # normalize_geometry 표준 geometry
          "design_raw":       dict | None,         # design_payload_from_shapes.design
          "rooms":            Any | None,          # UP1 extract_rooms 출력
          "params_hint":      dict | None,         # bbox/면적 역산(source='도면추정')
          "diagnostics":      list[str],           # 빈/무효 사유
        }
    """
    diagnostics: list[str] = []

    # ── 입력 가드 ──
    if not isinstance(parse_result, dict) or not parse_result:
        return {
            "editing_shapes": [],
            "geometry_payload": None,
            "design_raw": None,
            "rooms": None,
            "params_hint": None,
            "diagnostics": ["parse_result 없음/무효 — 모든 소비형 미산출(가짜 기하 금지)"],
        }

    raw_shapes = parse_result.get("shapes")
    if not isinstance(raw_shapes, list) or not raw_shapes:
        return {
            "editing_shapes": [],
            "geometry_payload": None,
            "design_raw": None,
            "rooms": None,
            "params_hint": None,
            "diagnostics": ["shapes 비어 있음 — 모든 소비형 미산출(파싱된 엔티티 없음)"],
        }

    scale = _scale_of(parse_result)

    # ── 1) editing_shapes(sanitize) ──
    editing_shapes, sanitize_issues = _sanitize_shapes(raw_shapes)
    diagnostics.extend(sanitize_issues)
    if not editing_shapes:
        diagnostics.append("정제 후 유효 셰이프 0건 — 다운스트림 소비형 미산출")
        return {
            "editing_shapes": [],
            "geometry_payload": None,
            "design_raw": None,
            "rooms": None,
            "params_hint": None,
            "diagnostics": diagnostics,
        }

    # ── 2) geometry_payload(normalize_geometry) ──
    geometry_payload, geo_note = _geometry_payload(editing_shapes, scale)
    if geo_note:
        diagnostics.append(geo_note)

    # ── 3) design_raw(design_payload_from_shapes 계약) ──
    design_result = _design_raw(editing_shapes, scale)
    design_raw = design_result.get("design") if design_result.get("valid") else None
    for issue in design_result.get("issues", []):
        diagnostics.append(f"design_raw: {issue}")

    # ── 4) rooms(UP1 shapes_to_rooms.extract_rooms — import) ──
    rooms, rooms_note = _rooms(editing_shapes, scale)
    if rooms_note:
        diagnostics.append(rooms_note)

    # ── 5) params_hint(bbox/면적 역산) ──
    params_hint, params_note = _params_hint(parse_result, editing_shapes, scale)
    if params_note:
        diagnostics.append(params_note)

    return {
        "editing_shapes": editing_shapes,
        "geometry_payload": geometry_payload,
        "design_raw": design_raw,
        "rooms": rooms,
        "params_hint": params_hint,
        "diagnostics": diagnostics,
    }
