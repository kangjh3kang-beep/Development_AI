"""도형(shapes) → 실(rooms) 역추출기 + bbox 경계 어댑터(UP1 / WI-1·WI-2).

업로드·벡터화된 CAD 도형(닫힌 polygon + 텍스트 label)을 unit_plan_generator가
이미 다루는 "실 배치(rooms) + 경계(boundaries)" 표현으로 **역추출**한다. 이로써
외부 도면을 plan 엔진(classify_boundaries·place_openings·validate_connectivity)의
문법 파이프라인에 그대로 태울 수 있다.

설계 원칙(절대 준수):
- **순수 결정론·LLM 0.** 동일 shapes = 동일 rooms. 외부호출·난수 없음.
- **additive·하위호환.** arch_grammar / unit_plan_generator는 **import만**(읽기전용),
  무수정. 본 모듈은 신규 파일이며 기존 응답 키·정답 테스트를 건드리지 않는다.
- **가짜값·날조 실명 금지.** 라벨 없는 실은 면적·위치 휴리스틱으로 *타입*만 추정하고
  한글 실명은 절대 지어내지 않는다 — name='실(추정)' 고정 + inferred=True +
  confidence(0~1)로 정직 표기. 추정 근거가 없으면 type=None.
- **출처 등급 구분.** 본 모듈의 추정은 '관행 휴리스틱'이며 법령 근거가 아니다.

좌표계(unit_plan_generator와 동일): 원점=북서, +x=동(우), +y=남(하). 단위 m.
입력 polygon 정점은 픽셀이며 scale_px_per_m으로 m 역산한다(px / scale = m).

shapes 입력 계약(WI-1):
  각 shape는 dict. polygon 후보는 kind in {'polygon','poly','room','space','area'}
  또는 (kind 미지정이어도) 정점 리스트를 가진 도형. 정점은 다음 중 하나로 전달:
    - shape['points'] = [[x,y], ...] 또는 [(x,y), ...] 또는 [{'x':..,'y':..}, ...]
    - shape['polygon'] = 동일
    - shape['vertices'] = 동일
  라벨은 kind in {'label','text','annotation'}. 텍스트는 text|label|name|value,
  좌표는 (x,y) | point=[x,y] | points=[[x,y]] | bbox 중심.

  닫힌 polygon만(정점≥3, shoelace 면적>1.0㎡) 실 후보로 채택한다. shape에
  closed 키가 명시돼 있고 falsy면 열린 폴리라인(벽선·치수선 등)으로 보고 실
  후보에서 제외한다(키 부재 시 정점≥3이면 닫힌 것으로 간주 — 하위호환). 면적
  미달·정점 부족·좌표 결손은 warnings로 정직 보고하고 버린다(침묵 폴백 금지).

  편의 입력(additive): dxf_import_service.parse_dxf_to_shapes의 parse_result
  dict({'shapes':[...], 'scale_px_per_m':...})를 그대로 전달해도 된다 —
  cad_upload_hub(UP2)가 이 형태로 호출한다. 내장 scale_px_per_m이 유효(양수)하면
  파라미터보다 우선한다(도면 자기기술 스케일이 정확).
"""

from __future__ import annotations

from typing import Any

# arch_grammar는 읽기전용 import만(무수정). 실명→타입 조회 + 경계 스키마 계약.
from .arch_grammar import (  # noqa: F401  (BOUNDARY_SCHEMA는 계약 문서/참조용)
    BOUNDARY_SCHEMA,
    ROOM_TYPES,
    room_type_of,
)

# ── 상수 ──

_MM = 3  # 좌표 반올림 자릿수(m 소수 3자리 = mm 정밀도) — unit_plan_generator와 동일
_EPS = 1e-6

# 실 후보 polygon으로 볼 shape kind(소문자 비교). kind 미지정이어도 정점이 있으면 채택.
_POLYGON_KINDS: frozenset[str] = frozenset(
    {"polygon", "poly", "room", "space", "area", "lwpolyline", "polyline"}
)
# 라벨(실명 텍스트) shape kind.
_LABEL_KINDS: frozenset[str] = frozenset({"label", "text", "annotation", "mtext"})

# 닫힌 실로 채택할 최소 실면적(㎡) — 가구·벽 두께 미만 잡도형 제거(설계 명시 1.0).
MIN_ROOM_AREA_SQM: float = 1.0

# 미라벨 추정 휴리스틱 임계(통상관행 — 법령 아님, 가짜값 아님):
#   최대 면적 실 → 거실 / <4㎡ & 습식 위치(타일링상 코너·소형) → 욕실.
_INFER_BATH_MAX_AREA_SQM: float = 4.0
_INFER_BATH_TYPE = "bath_common"
_INFER_LIVING_TYPE = "living"
_INFER_GENERIC_TYPE = "bedroom"  # 그 외 거실급 미만 중형 실 — 타입만 침실로(실명 미날조)

# 추정 신뢰도(통상관행 휴리스틱 — 정직 표기용 명목값, 확률 아님)
_CONF_LIVING = 0.6
_CONF_BATH = 0.55
_CONF_GENERIC = 0.3

# 미라벨 실 표시명(한글 실명 날조 금지 — 고정 placeholder)
INFERRED_ROOM_NAME: str = "실(추정)"


def _r(v: float) -> float:
    return round(v, _MM)


# ── 입력 정규화(픽셀 정점 → m 좌표) ──

def _extract_points(shape: dict[str, Any]) -> list[tuple[float, float]] | None:
    """shape에서 정점 리스트를 꺼내 (x,y) float 튜플 목록으로 정규화한다.

    points|polygon|vertices 키를 순서대로 본다. 각 정점은 [x,y]/(x,y)/{x,y} 허용.
    파싱 불가하거나 비어 있으면 None.
    """
    raw = None
    for key in ("points", "polygon", "vertices"):
        if key in shape and shape[key]:
            raw = shape[key]
            break
    if raw is None:
        return None
    pts: list[tuple[float, float]] = []
    try:
        for p in raw:
            if isinstance(p, dict):
                x, y = p.get("x"), p.get("y")
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                x, y = p[0], p[1]
            else:
                return None
            if x is None or y is None:
                return None
            pts.append((float(x), float(y)))
    except (TypeError, ValueError):
        return None
    return pts or None


def _label_point(shape: dict[str, Any]) -> tuple[float, float] | None:
    """라벨 shape의 대표 좌표(텍스트 앵커)를 (x,y) m-전 픽셀로 반환."""
    if "x" in shape and "y" in shape and shape["x"] is not None and shape["y"] is not None:
        try:
            return (float(shape["x"]), float(shape["y"]))
        except (TypeError, ValueError):
            return None
    pt = shape.get("point")
    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
        try:
            return (float(pt[0]), float(pt[1]))
        except (TypeError, ValueError):
            return None
    pts = _extract_points(shape)
    if pts:
        # 다점이면 중심(라벨 박스 등) 사용
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        return (cx, cy)
    bbox = shape.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        try:
            x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]),
                              float(bbox[2]), float(bbox[3]))
            return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        except (TypeError, ValueError):
            return None
    return None


def _label_text(shape: dict[str, Any]) -> str | None:
    for key in ("text", "label", "name", "value"):
        v = shape.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


# ── 기하: shoelace 면적 + point-in-polygon ──

def _shoelace_area(pts: list[tuple[float, float]]) -> float:
    """다각형 면적(부호 없는 절댓값). pts는 좌표(어느 단위든 동일 단위)."""
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _point_in_polygon(px: float, py: float, poly: list[tuple[float, float]]) -> bool:
    """짝수-홀수(ray casting) 내부 판정. 경계상 점은 내부로 간주(관용)."""
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        # 경계(꼭 변 위) 빠른 판정 — 변의 bbox 내·외적 0
        if (min(xi, xj) - _EPS <= px <= max(xi, xj) + _EPS
                and min(yi, yj) - _EPS <= py <= max(yi, yj) + _EPS):
            cross = (xj - xi) * (py - yi) - (yj - yi) * (px - xi)
            if abs(cross) <= 1e-9:
                return True
        intersect = ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / (yj - yi + 0.0) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def _bbox_of(pts: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


# ── ① shapes → rooms (역추출) ──

def extract_rooms(
    shapes: list[dict[str, Any]] | dict[str, Any],
    scale_px_per_m: float = 10.0,
) -> dict[str, Any]:
    """CAD 도형(닫힌 polygon + label) → 실(rooms) 역추출(순수 결정론).

    절차:
      1) shapes를 polygon 후보 / label 로 분류(정규화).
      2) 닫힌 polygon(정점≥3, shoelace 면적>MIN_ROOM_AREA_SQM㎡)만 실 후보 채택.
         closed=False 명시 도형(열린 폴리라인 — 벽선·치수선)은 실 후보 제외.
         정점·좌표·면적 결손은 warnings로 정직 보고하고 버린다.
      3) 각 label(텍스트)을 point-in-polygon으로 실에 귀속 → room_type_of(text)로
         타입·실명 확정.
      4) 미라벨 실은 면적·위치 휴리스틱으로 *타입*만 추정(최대면적→거실,
         <4㎡→욕실, 그 외 중형→침실), name='실(추정)'·inferred=True·confidence.
         라벨로 확정된 거실이 이미 있으면 거실 추정은 억제한다(중복 거실 방지).
         **한글 실명 날조 금지.**
      5) 각 polygon의 bbox를 {name,type,x,y,w,h}(m)로 사각화하되 원본 polygon(m)과
         실면적(area_sqm — shoelace)을 보존한다.

    Args:
        shapes: WI-1 도형 dict 리스트(픽셀 좌표). 또는 parse_dxf_to_shapes의
            parse_result dict({'shapes':[...], 'scale_px_per_m':...}) — additive
            편의 입력(cad_upload_hub UP2 호출 계약).
        scale_px_per_m: 픽셀→m 환산 계수(px / scale = m). 양수여야 함.
            parse_result dict 입력에 유효한 내장 scale_px_per_m이 있으면 그것이 우선.

    Returns:
        {"rooms": [...], "warnings": [...]} — rooms는 x좌표·y좌표 결정론 정렬.
        room dict 키: name, type, x, y, w, h(m, bbox), polygon([[x,y],..] m),
        area_sqm(실면적 m²), inferred(bool), confidence(float|None), label_source.

    Raises:
        ValueError: scale_px_per_m이 0 이하인 경우(명시 오류 — 침묵 폴백 금지).
    """
    # parse_result dict 수용(additive) — cad_upload_hub가 parse_dxf_to_shapes 결과
    # dict를 그대로 전달한다. 내장 scale_px_per_m이 유효(양수)하면 파라미터보다
    # 우선하고, 무효면 정직 경고 후 파라미터 값을 사용한다(침묵 폴백 금지).
    embedded_scale_invalid: Any = None
    if isinstance(shapes, dict):
        embedded = shapes.get("scale_px_per_m", shapes.get("scale"))
        if embedded is not None:
            try:
                emb = float(embedded)
            except (TypeError, ValueError):
                emb = None
            if emb is not None and emb > 0:
                scale_px_per_m = emb
            else:
                embedded_scale_invalid = embedded
        inner = shapes.get("shapes")
        shapes = inner if isinstance(inner, list) else []

    if not (scale_px_per_m and float(scale_px_per_m) > 0):
        raise ValueError(
            f"scale_px_per_m은 양수여야 합니다(입력: {scale_px_per_m})"
        )
    scale = float(scale_px_per_m)
    warnings: list[dict[str, Any]] = []
    if embedded_scale_invalid is not None:
        warnings.append(_warn(
            "scale_px_per_m", "내장 스케일", "양수 float",
            repr(embedded_scale_invalid),
            f"parse_result 내장 scale_px_per_m={embedded_scale_invalid!r} 무효 — "
            f"파라미터 값 {scale}을(를) 사용합니다(정직 경고).",
        ))

    # ── 1) 분류 + 정점 정규화(픽셀) ──
    polys_px: list[tuple[int, list[tuple[float, float]]]] = []  # (원본 인덱스, 픽셀정점)
    labels: list[tuple[str, tuple[float, float]]] = []          # (텍스트, 픽셀좌표)

    for idx, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            warnings.append(_warn(
                "shape", "도형 타입", "dict", type(shape).__name__,
                f"shapes[{idx}]가 dict가 아니어서 건너뜁니다(잡도형 제거).",
            ))
            continue
        kind = str(shape.get("kind") or shape.get("type") or "").strip().lower()

        if kind in _LABEL_KINDS:
            text = _label_text(shape)
            pt = _label_point(shape)
            if text is None or pt is None:
                warnings.append(_warn(
                    "label", "라벨 좌표·텍스트", "text+point",
                    f"text={text!r},point={pt!r}",
                    f"shapes[{idx}] 라벨의 텍스트·좌표가 불완전해 무시합니다.",
                ))
                continue
            labels.append((text, pt))
            continue

        # polygon 후보: kind 일치 또는 (kind 미지정/기타) 정점 보유
        pts = _extract_points(shape)
        if pts is None:
            if kind in _POLYGON_KINDS:
                warnings.append(_warn(
                    "polygon", "정점", "points/polygon/vertices", "없음/파싱불가",
                    f"shapes[{idx}]({kind or '미지정'}) 정점을 읽을 수 없어 버립니다.",
                ))
            # kind도 라벨도 정점도 아니면 조용히 무관 도형 — 경고 불필요(잡선 등)
            continue
        # closed=False 명시 도형은 열린 폴리라인(벽선·치수선 등 무관 도형) —
        # 닫힌 실이 아니므로 후보 제외. 키 부재 시 정점≥3이면 닫힌 것으로
        # 간주한다(WI-1 하위호환). DXF parse_result polyline은 항상 closed 동반.
        if "closed" in shape and not shape["closed"]:
            continue
        if len(pts) < 3:
            warnings.append(_warn(
                "polygon", "정점 수", ">=3", str(len(pts)),
                f"shapes[{idx}] 정점 {len(pts)}개(<3) — 닫힌 실 아님, 버립니다.",
            ))
            continue
        polys_px.append((idx, pts))

    # ── 2) 픽셀→m 환산 + shoelace 면적>1㎡ 필터 ──
    cand: list[dict[str, Any]] = []
    for idx, pts_px in polys_px:
        poly_m = [(_r(x / scale), _r(y / scale)) for (x, y) in pts_px]
        area_sqm = _shoelace_area(poly_m)
        if area_sqm <= MIN_ROOM_AREA_SQM + _EPS:
            warnings.append(_warn(
                "polygon", "최소 실면적", f">{MIN_ROOM_AREA_SQM}㎡",
                f"{round(area_sqm, 3)}㎡",
                f"shapes[{idx}] 실면적 {area_sqm:.3f}㎡ ≤ {MIN_ROOM_AREA_SQM}㎡ — "
                "실 아님(가구·벽 잡도형), 버립니다.",
            ))
            continue
        x0, y0, x1, y1 = _bbox_of(poly_m)
        cand.append({
            "src_index": idx,
            "polygon": [list(p) for p in poly_m],
            "polygon_pts": poly_m,
            "area_sqm": _r(area_sqm),
            "x": _r(x0), "y": _r(y0),
            "w": _r(x1 - x0), "h": _r(y1 - y0),
            "label_text": None,
        })

    # ── 3) 라벨 귀속(point-in-polygon, m 좌표) ──
    for text, (lx_px, ly_px) in labels:
        lx, ly = lx_px / scale, ly_px / scale
        host = None
        for room in cand:
            if _point_in_polygon(lx, ly, room["polygon_pts"]):
                host = room
                break
        if host is None:
            warnings.append(_warn(
                "label", "라벨 귀속", "실 내부 점", f"'{text}'",
                f"라벨 '{text}'이(가) 어떤 실 polygon 내부에도 없어 귀속 실패합니다.",
            ))
            continue
        if host["label_text"] is not None and host["label_text"] != text:
            # 한 실에 라벨 2개 — 첫 라벨 유지(결정론), 충돌 정직 보고
            warnings.append(_warn(
                "label", "라벨 중복", "실당 라벨 1개",
                f"'{host['label_text']}'+'{text}'",
                f"실(src={host['src_index']})에 라벨이 둘 — "
                f"'{host['label_text']}' 유지, '{text}' 무시.",
            ))
            continue
        host["label_text"] = text

    # ── 4) 타입·실명 확정 + 미라벨 추정 ──
    # 면적 최대 미라벨 실 1개를 거실로 추정하기 위해 사전 계산(결정론).
    # 단, 라벨로 확정된 거실이 이미 있으면 거실 추정을 억제한다(중복 거실
    # 추정 방지 — 추정 근거 상실 시 일반 추정 경로로 강등, 날조 방지).
    labeled_types = {
        room_type_of(r["label_text"])
        for r in cand if r["label_text"] is not None
    }
    unlabeled = [r for r in cand if r["label_text"] is None]
    max_area_room = (
        max(unlabeled, key=lambda r: (r["area_sqm"], -r["x"], -r["y"]))
        if unlabeled and _INFER_LIVING_TYPE not in labeled_types else None
    )

    for room in cand:
        text = room["label_text"]
        if text is not None:
            rtype = room_type_of(text)
            room["name"] = text
            room["type"] = rtype  # None 가능(미등록 실명 — 침묵 폴백 금지)
            room["inferred"] = False
            room["confidence"] = None
            room["label_source"] = "label"
            if rtype is None:
                warnings.append(_warn(
                    text, "실명 매핑", "arch_grammar.ROOM_NAME_MAP 등록 실명", text,
                    f"라벨 실명 '{text}' 미등록 — name 보존·type=None(날조 금지).",
                ))
        else:
            rtype, conf = _infer_type(room, room is max_area_room)
            room["name"] = INFERRED_ROOM_NAME  # 한글 실명 날조 금지(고정 placeholder)
            room["type"] = rtype
            room["inferred"] = True
            room["confidence"] = conf
            room["label_source"] = "heuristic"
            warnings.append(_warn(
                INFERRED_ROOM_NAME, "미라벨 추정",
                "라벨 부재 → 타입만 휴리스틱 추정(통상관행)",
                f"type={rtype},area={room['area_sqm']}㎡",
                f"라벨 없는 실(src={room['src_index']}, {room['area_sqm']}㎡) — "
                f"타입 '{rtype}' 추정(confidence={conf}), 실명 미부여(날조 금지).",
            ))

    # ── 5) 출력 사각화(내부 키 제거) + 결정론 정렬 ──
    cand.sort(key=lambda r: (r["y"], r["x"], r["src_index"]))
    rooms_out: list[dict[str, Any]] = []
    for room in cand:
        rooms_out.append({
            "name": room["name"],
            "type": room["type"],
            "x": room["x"], "y": room["y"], "w": room["w"], "h": room["h"],
            "polygon": room["polygon"],
            "area_sqm": room["area_sqm"],
            "inferred": room["inferred"],
            "confidence": room["confidence"],
            "label_source": room["label_source"],
        })
    return {"rooms": rooms_out, "warnings": warnings}


def _infer_type(room: dict[str, Any], is_max_area: bool) -> tuple[str | None, float]:
    """미라벨 실의 타입 추정(면적·위치 휴리스틱 — 통상관행, 가짜값 아님).

    규칙(보수적): 최대면적 실→거실 / <4㎡ 소형→욕실 / 그 외 중형→침실.
    한글 실명은 절대 반환하지 않는다(호출부가 '실(추정)' 고정).
    """
    area = float(room["area_sqm"])
    if area < _INFER_BATH_MAX_AREA_SQM:
        return _INFER_BATH_TYPE, _CONF_BATH
    if is_max_area:
        return _INFER_LIVING_TYPE, _CONF_LIVING
    return _INFER_GENERIC_TYPE, _CONF_GENERIC


def _warn(field: str, rule: str, legal: Any, actual: Any, message: str) -> dict[str, Any]:
    """경고 dict(unit_plan_generator violations/warnings 호환 형태)."""
    return {
        "field": field, "rule": rule, "legal": legal,
        "actual": actual, "message": message,
    }


# ── ② bbox rooms → boundaries (경계 어댑터) ──

def boundaries_from_bbox_rooms(
    rooms: list[dict[str, Any]],
    tol: float = 1e-3,
) -> dict[str, Any]:
    """사각화된 실(bbox) 쌍의 공유변에서 BOUNDARY_SCHEMA 경계를 생성한다(결정론).

    extract_rooms가 만든 rooms({name,type,x,y,w,h,...})를 입력으로 받아,
    unit_plan_generator의 extract_boundaries와 **동일한 BOUNDARY_SCHEMA dict**를
    산출한다. 이후 호출자가 classify_boundaries·place_openings·
    validate_connectivity(unit_plan_generator)를 그대로 재사용할 수 있다.

    내부 공유변: 두 bbox가 변 좌표 일치(±tol) + 진행축 구간 겹침(>tol).
      room_a = 북/서측 실, room_b = 남/동측 실, side = a→b 방향('s'|'e'), orient.
    외기변: 본체 외곽(전체 bbox 경계 x=W0/W1, y=D0/D1)에 접한 실 변. room_b=None,
      side = 방위('n'|'s'|'e'|'w'). 남측(y=D1)=채광면.

    미인접(어떤 실과도 공유변 없음)·갭(타일링 불연속) 실은 warnings로 정직 보고한다.
    boundary 필드는 BOUNDARY_SCHEMA 계약을 따르며 kind/wall_type/door_owner는
    부여하지 않는다(classify_boundaries 담당).

    Args:
        rooms: extract_rooms 결과 rooms 또는 {name,x,y,w,h} 최소 dict 리스트.
        tol: 좌표 일치·겹침 허용 오차(m).

    Returns:
        {"boundaries": [...], "warnings": [...]} — boundaries는 결정론 정렬 후
        id('b###') 부여. extract_boundaries와 동일 키 집합.
    """
    warnings: list[dict[str, Any]] = []
    rects: list[tuple[str, float, float, float, float]] = []
    for r in rooms:
        try:
            rects.append((
                str(r["name"]),
                float(r["x"]), float(r["y"]), float(r["w"]), float(r["h"]),
            ))
        except (KeyError, TypeError, ValueError):
            warnings.append(_warn(
                "room", "실 bbox 필드", "name,x,y,w,h", str(r),
                "실 dict에 bbox 필드(x,y,w,h)가 없어 경계 추출에서 제외합니다.",
            ))
    if not rects:
        return {"boundaries": [], "warnings": warnings}

    # 본체 외곽 bbox(전체 실 합집합의 경계) — 외기변 판정 기준.
    body_x0 = min(rx for _, rx, _, _, _ in rects)
    body_y0 = min(ry for _, _, ry, _, _ in rects)
    body_x1 = max(rx + rw for _, rx, _, rw, _ in rects)
    body_y1 = max(ry + rh for _, _, ry, _, rh in rects)

    raw: list[dict[str, Any]] = []
    # 인접(공유변 1개 이상) 실 추적 — 미인접 경고용
    adjacent: set[int] = set()

    # ── 1) 내부 공유변(쌍당 1회 — a가 북/서측일 때만 기록) ──
    for i, (an, ax, ay, aw, ah) in enumerate(rects):
        for j, (bn, bx, by, bw, bh) in enumerate(rects):
            if i == j:
                continue
            # 수직 공유변: a 동측변(x=ax+aw) == b 서측변(x=bx)
            if abs((ax + aw) - bx) <= tol:
                y1 = max(ay, by)
                y2 = min(ay + ah, by + bh)
                if y2 - y1 > tol:
                    x_line = _r(((ax + aw) + bx) / 2.0)
                    raw.append({
                        "room_a": an, "room_b": bn, "side": "e", "orient": "v",
                        "x1": x_line, "y1": _r(y1), "x2": x_line, "y2": _r(y2),
                        "length_m": _r(y2 - y1), "balcony_front": False,
                    })
                    adjacent.add(i)
                    adjacent.add(j)
            # 수평 공유변: a 남측변(y=ay+ah) == b 북측변(y=by)
            if abs((ay + ah) - by) <= tol:
                x1 = max(ax, bx)
                x2 = min(ax + aw, bx + bw)
                if x2 - x1 > tol:
                    y_line = _r(((ay + ah) + by) / 2.0)
                    raw.append({
                        "room_a": an, "room_b": bn, "side": "s", "orient": "h",
                        "x1": _r(x1), "y1": y_line, "x2": _r(x2), "y2": y_line,
                        "length_m": _r(x2 - x1), "balcony_front": False,
                    })
                    adjacent.add(i)
                    adjacent.add(j)

    # ── 2) 외기변(본체 외곽 접변 — 실별 분리) ──
    for name, x, y, w, h in rects:
        if abs(y - body_y0) <= tol:          # 북측 외기
            raw.append(_ext_boundary(name, "n", "h", x, body_y0, x + w, body_y0, w))
        if abs((y + h) - body_y1) <= tol:    # 남측 외기(채광면)
            raw.append(_ext_boundary(name, "s", "h", x, body_y1, x + w, body_y1, w))
        if abs(x - body_x0) <= tol:          # 서측 외기
            raw.append(_ext_boundary(name, "w", "v", body_x0, y, body_x0, y + h, h))
        if abs((x + w) - body_x1) <= tol:    # 동측 외기
            raw.append(_ext_boundary(name, "e", "v", body_x1, y, body_x1, y + h, h))

    # ── 3) 미인접 경고(외곽 단일 실은 정상 — 2실 이상에서만 의미) ──
    if len(rects) > 1:
        for i, (name, *_rest) in enumerate(rects):
            if i not in adjacent:
                warnings.append(_warn(
                    name, "실 인접성", "최소 1개 실과 공유변", "공유변 없음(갭)",
                    f"'{name}'이(가) 다른 실과 맞닿지 않습니다 — "
                    "타일링 갭/겹침 가능(정직 경고).",
                ))

    # ── 4) 결정론 정렬 + id 부여(extract_boundaries와 동일 키) ──
    raw.sort(key=lambda b: (
        b["y1"], b["x1"], b["y2"], b["x2"], b["orient"],
        b["room_a"], b["room_b"] or "",
    ))
    for k, b in enumerate(raw, start=1):
        b["id"] = f"b{k:03d}"
    return {"boundaries": raw, "warnings": warnings}


def _ext_boundary(
    name: str, side: str, orient: str,
    x1: float, y1: float, x2: float, y2: float, length: float,
) -> dict[str, Any]:
    """외기변 boundary dict(room_b=None) 1건 — BOUNDARY_SCHEMA 계약."""
    return {
        "room_a": name, "room_b": None, "side": side, "orient": orient,
        "x1": _r(x1), "y1": _r(y1), "x2": _r(x2), "y2": _r(y2),
        "length_m": _r(length), "balcony_front": False,
    }
